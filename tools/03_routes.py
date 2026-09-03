# -*- coding: utf-8 -*-
"""প্রতিটা বাস রুটের আসল রাস্তার দূরত্ব ও ম্যাপে আঁকার লাইন আনে (OSRM, ফ্রি)।

একটা রুটের সব স্টপেজ একসাথে OSRM-এ পাঠাই; ফিরে আসে প্রতি ধাপের (leg)
দূরত্ব আর পুরো পথের geometry। ফলাফল data/osrm-cache.json-এ জমা থাকে।

ইনপুট : data/routes-clean.json, data/geocode-cache.json, tools/overrides.json
আউটপুট: data/osrm-cache.json
"""
import json
import os
import sys
import time
import urllib.request

import stoppos

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "osrm-cache.json")
OSRM = "https://router.project-osrm.org/route/v1/driving/"


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def coords_of(stops, pos):
    """যেসব স্টপেজের অবস্থান জানা আছে সেগুলোই রাখি।

    হাতেগোনা কয়েকটা জায়গা (যেমন নীলা মার্কেট, জারুন) OpenStreetMap-এ
    নেই। অনুমান করে কোঅর্ডিনেট বসানোর চেয়ে ওই স্টপেজটা বাদ দেওয়া ভালো —
    রুটটা তখনো কাজে লাগে, শুধু ওই একটা স্টপেজ তালিকায় থাকে না।
    """
    kept, dropped = [], []
    for s in stops:
        p = pos.get(s)
        if p:
            kept.append((s, (p[1], p[0])))   # OSRM চায় lon,lat
        else:
            dropped.append(s)
    return kept, dropped


def osrm_route(pts):
    """OSRM-এ পুরো রুটটা একবারে পাঠাই।

    continue_straight=false খুব জরুরি। ডিফল্টে OSRM ওয়েপয়েন্টে ইউ-টার্ন
    নিষিদ্ধ করে, ফলে ডিভাইডার দেওয়া রাস্তার দুই পাশে বসা দুইটা স্টপেজের
    মাঝে (যেমন জনপথ মোড় → সায়েদাবাদ, সরলরেখায় ১০০ মিটার) সে পরের
    ইউ-টার্ন পর্যন্ত গিয়ে ঘুরে আসে — ৩ কিলোমিটার! বাস তা করে না।
    """
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in pts)
    url = (f"{OSRM}{path}?overview=full&geometries=polyline"
           f"&annotations=false&steps=false&continue_straight=false")
    req = urllib.request.Request(url, headers={"User-Agent": "DhakaBusFare/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    routes = load(os.path.join(ROOT, "data", "routes-clean.json"))
    pos = stoppos.positions()
    cache = load(CACHE, {}) or {}

    done = skipped = fetched = 0
    for i, r in enumerate(routes, 1):
        key = r["id"]
        kept, dropped = coords_of(r["stops"], pos)
        names = [s for s, _ in kept]
        # স্টপেজের তালিকা আর তাদের অবস্থান — দুইটার যেকোনোটা বদলালেই
        # ক্যাশ বাসি। তাই দুইটার ছাপ মিলিয়ে দেখি।
        stamp = ";".join(f"{lon:.5f},{lat:.5f}" for _, (lon, lat) in kept)

        old = cache.get(key)
        if old and old.get("stops") == names and old.get("stamp") == stamp:
            done += 1
            continue

        if len(kept) < 2:
            print(f"[{i}] SKIP {key} — ২টার কম স্টপেজের অবস্থান জানা")
            skipped += 1
            continue
        if dropped:
            print(f"     ({key}: বাদ গেল {', '.join(dropped)})")
        pts = [p for _, p in kept]

        try:
            res = osrm_route(pts)
        except Exception as e:
            print(f"[{i}] ERR  {key}: {e}", file=sys.stderr)
            time.sleep(2)
            continue

        if res.get("code") != "Ok" or not res.get("routes"):
            print(f"[{i}] FAIL {key}: {res.get('code')}")
            time.sleep(1)
            continue

        route = res["routes"][0]
        legs = [round(l["distance"] / 1000.0, 3) for l in route["legs"]]
        cache[key] = {
            "legs_km": legs,
            "total_km": round(route["distance"] / 1000.0, 3),
            "geometry": route["geometry"],
            "stops": names,
            "stamp": stamp,
        }
        fetched += 1
        print(f"[{i}/{len(routes)}] OK   {key} — {len(names)} স্টপেজ, {cache[key]['total_km']} কিমি")
        if fetched % 10 == 0:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        time.sleep(0.6)

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"\nআগে থেকে ছিল {done}, নতুন আনা {fetched}, বাদ পড়েছে {skipped}, মোট ক্যাশে {len(cache)}")


if __name__ == "__main__":
    main()
