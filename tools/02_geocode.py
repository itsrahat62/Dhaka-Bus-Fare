# -*- coding: utf-8 -*-
"""প্রতিটা স্টপেজের lat/lng + বাংলা নাম আনে (OpenStreetMap Nominatim, ফ্রি)।

ফলাফল data/geocode-cache.json-এ জমা থাকে, তাই বারবার চালালেও নতুন করে
রিকোয়েস্ট যায় না। Nominatim-এর নিয়ম: সেকেন্ডে সর্বোচ্চ ১টা রিকোয়েস্ট,
আর আসল User-Agent দিতে হয়।

ইনপুট : data/stops-english.txt, tools/overrides.json
আউটপুট: data/geocode-cache.json
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "geocode-cache.json")

UA = "DhakaBusFare/1.0 (open-source bus fare map; contact via github)"
# বৃহত্তর ঢাকা: সাভার, গাজীপুর, নারায়ণগঞ্জ, মানিকগঞ্জ, মাওয়া সব ধরে
VIEWBOX = "89.70,24.25,90.95,23.35"  # left,top,right,bottom


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def search(query, bounded=True):
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": "5",
        "namedetails": "1",
        "addressdetails": "1",
        "accept-language": "bn,en",
        "viewbox": VIEWBOX,
    }
    if bounded:
        params["bounded"] = "1"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    return http_json(url)


def pick(results):
    """সবচেয়ে মানানসই ফলাফল বাছি — রাস্তা/এলাকা/মোড়কে অগ্রাধিকার।"""
    if not results:
        return None
    good = {"suburb", "neighbourhood", "quarter", "residential", "town", "village",
            "city_district", "bus_stop", "bus_station", "junction", "square",
            "marketplace", "administrative", "locality", "hamlet"}
    ranked = sorted(
        results,
        key=lambda r: (
            0 if r.get("type") in good or r.get("category") in ("place", "highway") else 1,
            -float(r.get("importance") or 0),
        ),
    )
    return ranked[0]


def main():
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)

    overrides = {}
    ov_path = os.path.join(HERE, "overrides.json")
    if os.path.exists(ov_path):
        with open(ov_path, encoding="utf-8") as f:
            overrides = json.load(f)

    with open(os.path.join(ROOT, "data", "stops-english.txt"), encoding="utf-8") as f:
        stops = [l.strip() for l in f if l.strip()]

    todo = [s for s in stops if s not in cache and s not in overrides]
    print(f"মোট {len(stops)} স্টপেজ, ক্যাশে আছে {len(stops) - len(todo)}, আনতে হবে {len(todo)}")

    for i, name in enumerate(todo, 1):
        # প্রথমে ঢাকার ভেতরে খুঁজি, না পেলে বাংলাদেশজুড়ে
        entry = None
        for query, bounded in (
            (f"{name}, Dhaka, Bangladesh", True),
            (f"{name}, Bangladesh", False),
        ):
            try:
                hit = pick(search(query, bounded))
            except Exception as e:  # নেটওয়ার্ক হেঁচকি — পরের বার আবার চেষ্টা হবে
                print(f"  ! {name}: {e}", file=sys.stderr)
                hit = None
            time.sleep(1.1)
            if hit:
                nd = hit.get("namedetails") or {}
                entry = {
                    "lat": float(hit["lat"]),
                    "lon": float(hit["lon"]),
                    "bn": nd.get("name:bn") or "",
                    "osm_name": hit.get("name") or "",
                    "type": f"{hit.get('category')}/{hit.get('type')}",
                    "display": hit.get("display_name", ""),
                    "query": query,
                }
                break
        cache[name] = entry
        mark = "OK " if entry else "-- "
        bn = (entry or {}).get("bn") or ""
        print(f"[{i}/{len(todo)}] {mark}{name} {bn}")
        if i % 20 == 0:
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    found = sum(1 for s in stops if cache.get(s))
    withbn = sum(1 for s in stops if (cache.get(s) or {}).get("bn"))
    print(f"\nপাওয়া গেছে {found}/{len(stops)}, বাংলা নাম সহ {withbn}")
    missing = [s for s in stops if not cache.get(s) and s not in overrides]
    if missing:
        print("পাওয়া যায়নি:", ", ".join(missing))


if __name__ == "__main__":
    main()
