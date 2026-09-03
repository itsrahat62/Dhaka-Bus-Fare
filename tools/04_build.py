# -*- coding: utf-8 -*-
"""সব টুকরো জোড়া দিয়ে সাইটের জন্য একটাই ডেটা ফাইল বানায়।

ইনপুট : data/routes-clean.json, data/geocode-cache.json, data/osrm-cache.json,
         tools/bangla-names.json, tools/overrides.json
আউটপুট: site/data/data.json
"""
import json
import math
import os
import datetime

import stoppos

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# বিআরটিএ, ঢাকা মহানগর — কার্যকর ২৩ এপ্রিল ২০২৬
FARE = {
    "bus_rate": 2.53,
    "bus_min": 10,
    "mini_rate": 2.43,
    "mini_min": 8,
    "effective": "২৩ এপ্রিল ২০২৬",
    "source": "বিআরটিএ (brta.gov.bd)",
}


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def straight_km(a, b):
    """দুই বিন্দুর সরলরেখার দূরত্ব।"""
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# সরলরেখার তুলনায় রাস্তা কতটা ঘোরে। বিআরটিএ-র ১০টা চার্টের সাথে
# মিলিয়ে বের করা — ১.১০ ধরলে সরকারি দূরত্বের ±১০%-এর মধ্যে থাকে।
CIRCUITY = 1.10


def sane_leg(osrm_km, direct_km):
    """দুই স্টপেজের মধ্যে বাস আসলে কত পথ চলে।

    OSRM-কে পুরো রুটটা ওয়েপয়েন্ট ধরে ধরে দিলে সে প্রতিটা স্টপেজে
    হুবহু থামতে গিয়ে ঘুরপথ নেয় — ডিভাইডারের উল্টো পাশ, ওয়ান-ওয়ে,
    ফ্লাইওভার। ফলে দূরত্ব ফুলে যায়। বিআরটিএ-র চার্টের সাথে মিলিয়ে
    দেখা গেছে ওভাবে হিসাব করলে দূরত্ব প্রায় দ্বিগুণ আসে:

        মিরপুর-১২ → মতিঝিল — সরকারি ১৫.৩ কিমি, OSRM চেইনে ২৬.৩

    অথচ OSRM-কে শুধু দুই প্রান্ত দিলে সে দেয় ১৫.২ — একদম ঠিক। মানে
    সমস্যা রাস্তার হিসাবে নয়, ওয়েপয়েন্টে থামানোয়।

    তাই ধরি: সরলরেখার CIRCUITY গুণ। আর OSRM যদি তার চেয়েও কম বলে
    (সোজা মহাসড়কে হয়), তার কথাই মানি।
    """
    return min(osrm_km, direct_km * CIRCUITY)


def main():
    routes = load(os.path.join(ROOT, "data", "routes-clean.json"))
    geo = load(os.path.join(ROOT, "data", "geocode-cache.json"), {}) or {}
    osrm = load(os.path.join(ROOT, "data", "osrm-cache.json"), {}) or {}
    bn = load(os.path.join(HERE, "bangla-names.json"), {}) or {}
    overrides = load(os.path.join(HERE, "overrides.json"), {}) or {}
    syn = load(os.path.join(HERE, "synonyms.json"), {}) or {}
    chart = load(os.path.join(ROOT, "data", "chart-match.json"), {}) or {}

    # ১. যেসব স্টপেজের অবস্থান জানা আছে শুধু সেগুলোই সাইটে যাবে
    coords = stoppos.positions()

    stop_ids, stops = {}, []
    for r in routes:
        for s in r["stops"]:
            if s in stop_ids or s not in coords:
                continue  # যার অবস্থান জানা নেই সে সাইটে যাবে না
            lat, lon = coords[s]
            stop_ids[s] = len(stops)
            entry = {
                "en": s,
                "bn": bn.get(s) or (geo.get(s) or {}).get("bn") or s,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
            # মানুষ যে বিকল্প নামে খোঁজে (উত্তরা, ঢাবি, এয়ারপোর্ট…)
            alt = [a for a in syn.get(s, []) if isinstance(a, str)]
            if alt:
                entry["alt"] = alt
            stops.append(entry)

    # ২. রুট: শুধু সেই রুট যার OSRM দূরত্ব বেরিয়েছে
    out_routes = []
    trimmed = [0.0, 0.0]   # [যতটা ছাঁটা হলো, মোট কাঁচা দূরত্ব]
    rejected = []          # যেসব চার্ট-মিল বিশ্বাসযোগ্য নয়
    verified = []          # যেগুলোর দূরত্ব সরকারি সংখ্যার সাথে মিলেছে

    for r in routes:
        o = osrm.get(r["id"])
        # OSRM-এর তালিকাই আসল — যেসব স্টপেজের অবস্থান জানা যায়নি সেগুলো
        # ওখানেই বাদ পড়ে গেছে
        if not o:
            continue
        seq = o["stops"]
        if len(seq) < 2 or any(s not in stop_ids for s in seq):
            continue
        cum, acc = [0.0], 0.0
        for d, a, b in zip(o["legs_km"], seq, seq[1:]):
            fixed = sane_leg(d, straight_km(coords[a], coords[b]))
            trimmed[0] += d - fixed
            trimmed[1] += d
            acc += fixed
            cum.append(round(acc, 2))
        if len(cum) != len(seq):
            continue
        entry = {
            "en": r["name_en"],
            "id": r["id"],
            "multi": r.get("multi", False),
            "bn": r["name_bn"] or r["name_en"],
            "type": r["service_type"],
            "s": [stop_ids[s] for s in seq],
            "km": cum,
            "g": o["geometry"],
        }
        # বিআরটিএ-র অফিসিয়াল ভাড়ার চার্ট। চার্টটা রুটের একটা নির্দিষ্ট
        # অংশের (a → b) — সেই অংশে আমাদের হিসাব করা দূরত্ব চার্টে লেখা
        # দূরত্বের কাছাকাছি কি না, মিলিয়ে দেখি। না মিললে চার্টটা
        # দেখাই না; ভুল প্রমাণ দেখানোর চেয়ে কিছু না দেখানো ভালো।
        c = chart.get(r["id"])
        if c and c["a"] in seq and c["b"] in seq:
            ia, ib = seq.index(c["a"]), seq.index(c["b"])
            mine = abs(cum[ib] - cum[ia])
            official = c.get("km")
            if official and (official < 0.1 or abs(mine - official) / official > 0.35):
                rejected.append((r["id"], c["page"], round(mine, 1), official))
            else:
                entry["chart"] = {"p": c["page"], "no": c["no"],
                                  "f": c["from"], "t": c["to"],
                                  "i": ia, "j": ib}
                if official:
                    entry["chart"]["km"] = official
                    verified.append((r["id"], round(mine, 1), official))
        out_routes.append(entry)

    # ৩. কোন স্টপেজে কোন রুট যায় — সাইটে খোঁজা দ্রুত করার জন্য
    used = set()
    for i, r in enumerate(out_routes):
        used.update(r["s"])

    # যে স্টপেজে কোনো রুটই যায় না সেটা বাদ, আর id নতুন করে বসাই
    keep = sorted(used)
    remap = {old: new for new, old in enumerate(keep)}
    stops = [stops[i] for i in keep]
    for r in out_routes:
        r["s"] = [remap[i] for i in r["s"]]

    data = {
        "meta": {
            **FARE,
            "generated": datetime.date.today().isoformat(),
            "stops": len(stops),
            "routes": len(out_routes),
        },
        "stops": stops,
        "routes": out_routes,
    }

    out = os.path.join(ROOT, "site", "data", "data.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out) / 1024
    print(f"স্টপেজ : {len(stops)}")
    print(f"রুট    : {len(out_routes)} / {len(routes)}")
    print(f"ফাইল   : {size:.0f} KB → site/data/data.json")
    if trimmed[1]:
        print(f"ঘুরপথ  : {trimmed[0]:.0f} / {trimmed[1]:.0f} কিমি ছাঁটা হলো ({trimmed[0] / trimmed[1] * 100:.1f}%)")

    with_chart = sum(1 for x in out_routes if "chart" in x)
    print(f"চার্ট   : {with_chart} রুটে সরকারি ভাড়ার তালিকা যুক্ত")
    if verified:
        err = [abs(m - o) / o for _, m, o in verified]
        print(f"যাচাই   : {len(verified)} রুটে সরকারি দূরত্বের সাথে মিলিয়ে দেখা হয়েছে, "
              f"গড় হেরফের {sum(err) / len(err) * 100:.0f}%")
        for rid, m, o in sorted(verified, key=lambda v: -abs(v[1] - v[2]) / v[2])[:6]:
            print(f"   {rid:26s} অ্যাপে {m} কিমি, চার্টে {o} কিমি")
    if rejected:
        print(f"চার্ট বাদ ({len(rejected)}টি, দূরত্ব মেলেনি):")
        for rid, pg, mine, off in rejected[:8]:
            print(f"   {rid:26s} {pg}  অ্যাপে {mine} কিমি, চার্টে {off} কিমি")

    built = {x["id"] for x in out_routes}
    dropped = [r["id"] for r in routes if r["id"] not in built]
    if dropped:
        print(f"বাদ পড়া রুট ({len(dropped)}): {', '.join(dropped[:12])}")


if __name__ == "__main__":
    main()
