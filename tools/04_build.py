# -*- coding: utf-8 -*-
"""সব টুকরো জোড়া দিয়ে সাইটের জন্য একটাই ডেটা ফাইল বানায়।

ইনপুট : data/routes-clean.json, data/geocode-cache.json, data/osrm-cache.json,
         tools/bangla-names.json, tools/overrides.json
আউটপুট: site/data/data.json
"""
import json
import math
import re
import os
import datetime

import polyline
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


def route_key(route_id):
    """রুটের স্থায়ী চাবি — Firestore-এ ভোট/রিভিউ এর নিচে জমা হয়।

    "BRTC#9" → "brtc_9"। Firestore-এর ফিল্ড-পাথে ফাঁকা জায়গা বা # চলে না,
    তাই অক্ষর-সংখ্যা ছাড়া সব আন্ডারস্কোর।
    """
    k = re.sub(r"[^a-z0-9]+", "_", route_id.lower()).strip("_")
    return k or "unknown"


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

# ম্যাপের লাইন কতটা হালকা করব। ১০ মিটারে শহরের জুমে পার্থক্য চোখে পড়ে না,
# অথচ ডেটা ৭৩৫ KB থেকে ১৪৮ KB-তে নামে।
LINE_TOLERANCE_M = 10.0


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
    lines = []          # ম্যাপের লাইন, রুটের ক্রমেই
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
            # ভোট-রিভিউ এই চাবির নিচে জমা হয়। ডেটা আবার বানালেও যেন
            # ভোট হারিয়ে না যায়, তাই নামভিত্তিক ও স্থায়ী — সূচক নয়।
            "k": route_key(r["id"]),
            "multi": r.get("multi", False),
            "bn": r["name_bn"] or r["name_en"],
            "type": r["service_type"],
            "s": [stop_ids[s] for s in seq],
            "km": cum,
        }
        # ম্যাপের লাইন আলাদা ফাইলে যায় — প্রথম লোডে দরকার নেই
        lines.append(polyline.shrink(o["geometry"], LINE_TOLERANCE_M))
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

    # ৪. বিআরটিএ-র চার্টগুলো নিজেরাই — যেকোনো দুই স্টপেজের হুবহু সরকারি
    #    ভাড়া বলার জন্য। চার্টের কিলোমিটার থেকেই ছকের ভাড়া বেরোয়:
    #    ভাড়া = max(সর্বনিম্ন, round(|কিমি_খ − কিমি_ক| × হার))
    resolved = load(os.path.join(ROOT, "data", "chart-resolved.json"), {}) or {}
    index = {p["page"]: p for p in
             (load(os.path.join(ROOT, "data", "chart-index.json"), {}) or {}).get("pages", [])}
    stop_index = dict(stop_ids)
    remap_stop = {old: new for old, new in remap.items()}

    out_charts, bad_charts = [], []
    for page, rows in sorted(resolved.items()):
        meta = index.get(page)
        if not meta:
            continue
        pts = []
        for en, chart_name, km in rows:
            sid = None
            if en in stop_index and stop_index[en] in remap_stop:
                sid = remap_stop[stop_index[en]]
            pts.append([sid, chart_name, km])
        if sum(1 for p in pts if p[0] is not None) < 2:
            continue

        # পাহারা: চার্টের কোনো স্টপেজ ভুল জায়গায় বসে গেলে ভাড়া কয়েকগুণ
        # ভুল হয়ে যায়। যেমন "দিয়াবাড়ী" — মিরপুরেরটা, নাকি উত্তরারটা?
        # ধরার উপায়: চার্টে লেখা দূরত্ব সরলরেখার দূরত্বের চেয়ে কম হতে
        # পারে না (রাস্তা সরলরেখার চেয়ে ছোট হয় না)। যে স্টপেজ তার
        # দুই পাশের প্রতিবেশীর সাথেই বেমানান, সেটাই দোষী — পুরো চার্ট
        # বাদ না দিয়ে শুধু ওই স্টপেজটা বাদ দিই, বাকিটা কাজে লাগে।
        def fits(i, j):
            """pts[i] আর pts[j] — চার্টের দূরত্ব বাস্তবসম্মত কি না।"""
            if pts[i][0] is None or pts[j][0] is None:
                return True     # আগেই বাদ পড়েছে, যাচাইয়ের কিছু নেই
            gap = abs(pts[j][2] - pts[i][2])
            crow = straight_km(coords[stops[pts[i][0]]["en"]],
                               coords[stops[pts[j][0]]["en"]])
            return crow <= gap + 2.5

        known = [i for i, p in enumerate(pts) if p[0] is not None]
        for n, i in enumerate(known):
            left = known[n - 1] if n > 0 else None
            right = known[n + 1] if n + 1 < len(known) else None
            ok_left = fits(left, i) if left is not None else None
            ok_right = fits(i, right) if right is not None else None
            checks = [c for c in (ok_left, ok_right) if c is not None]
            if checks and not any(checks):
                bad_charts.append((page, pts[i][1]))
                pts[i][0] = None

        if sum(1 for p in pts if p[0] is not None) < 2:
            continue

        out_charts.append({
            "p": page,
            "no": meta.get("no", ""),
            "f": meta.get("from", ""),
            "t": meta.get("to", ""),
            "km": meta.get("km"),
            "s": pts,
        })

    data = {
        "charts": out_charts,
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

    # ম্যাপের লাইন আলাদা ফাইলে — পাতা খোলার পর পেছনে নামে, তাই প্রথম
    # লোড হালকা থাকে
    lines_out = os.path.join(ROOT, "site", "data", "lines.json")
    with open(lines_out, "w", encoding="utf-8") as f:
        json.dump(lines, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out) / 1024
    lsize = os.path.getsize(lines_out) / 1024
    print(f"স্টপেজ : {len(stops)}")
    print(f"রুট    : {len(out_routes)} / {len(routes)}")
    print(f"ফাইল   : {size:.0f} KB (data.json) + {lsize:.0f} KB (lines.json, পরে নামে)")
    if trimmed[1]:
        print(f"ঘুরপথ  : {trimmed[0]:.0f} / {trimmed[1]:.0f} কিমি ছাঁটা হলো ({trimmed[0] / trimmed[1] * 100:.1f}%)")

    print(f"চার্টের ছক : {len(out_charts)} / {len(resolved)} — যেকোনো দুই স্টপেজের হুবহু সরকারি ভাড়া")
    if bad_charts:
        import collections as _c
        cnt = _c.Counter(why for _, why in bad_charts)
        print(f"সন্দেহে বাদ পড়া স্টপেজ: {len(bad_charts)}টি — " +
              ", ".join(f"{w}({n})" for w, n in cnt.most_common(8)))

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
