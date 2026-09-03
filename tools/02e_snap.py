# -*- coding: utf-8 -*-
"""স্টপেজগুলোকে OSM-এর আসল বাস স্টপে বসাই।

কেন দরকার: Nominatim এলাকার নাম দিলে তার কেন্দ্রবিন্দু ফেরত দেয় —
"মতিঝিল" মানে পাড়াটার মাঝখান, কোনো গলির ভেতর। বাস তো ওখানে যায় না।
ফলে OSRM প্রতি ধাপে মূল সড়ক থেকে গলিতে ঢুকে আবার বেরোয়, আর দূরত্ব
(তাই ভাড়াও) ফুলে যায়।

OpenStreetMap-এ ঢাকার হাজারখানেক আসল বাস স্টপ ট্যাগ করা আছে। প্রতিটা
স্টপেজের জন্য সবচেয়ে মানানসই বাস স্টপ খুঁজে সেখানেই বসিয়ে দিই।

আউটপুট: data/busstop-snap.json
"""
import json
import math
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "osm-busstops.json")
OUT = os.path.join(ROOT, "data", "busstop-snap.json")

NAME_MAX_KM = 2.0    # নাম মিললে এতদূর পর্যন্ত মানি
NEAR_MAX_KM = 0.45   # নাম না মিললে এত কাছের বাস স্টপে বসাই


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gc(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


BN2LAT = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u", "ঋ": "ri",
    "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "ch", "জ": "j", "ঝ": "jh", "ঞ": "n",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "ph", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "j", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t", "ং": "ng", "ঃ": "h", "ঁ": "",
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri",
    "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou", "্": "",
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
    "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
}

# নামের সাথে লেগে থাকা শব্দ, মেলানোর সময় ফেলে দিই
NOISE = re.compile(r"\b(bus|stop|stand|station|counter|terminal|bazar road|mor|more|moor|chattar)\b")


def fold(s):
    s = "".join(BN2LAT.get(c, c) for c in s).lower()
    s = NOISE.sub(" ", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    for a, b in (("ph", "f"), ("f", "p"), ("sh", "s"), ("ch", "c"), ("kh", "k"),
                 ("gh", "g"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("jh", "j"),
                 ("z", "j"), ("v", "b"), ("q", "k"), ("c", "k"), ("w", "o"),
                 ("y", "i"), ("h", "")):
        s = s.replace(a, b)
    # শুধু অক্ষর জোড়া কমাই — সংখ্যা নয়। নইলে "মিরপুর ১১" হয়ে যায়
    # "মিরপুর ১", আর সেটা "মিরপুর ১২"-র ভেতরে মিলে যায়।
    s = re.sub(r"([a-z])\1+", r"\1", s)
    return s


def digits(s):
    return "".join(c for c in s if c.isdigit())


def fetch_busstops():
    """বৃহত্তর ঢাকার সব নামওয়ালা বাস স্টপ একবারে নামাই।"""
    if os.path.exists(RAW):
        return load(RAW)
    q = """[out:json][timeout:180];
    (
     node["highway"="bus_stop"](23.35,89.70,24.25,90.95);
     node["amenity"="bus_station"](23.35,89.70,24.25,90.95);
     node["public_transport"="platform"]["bus"="yes"](23.35,89.70,24.25,90.95);
    );
    out body;"""
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=data,
                                 headers={"User-Agent": "DhakaBusFare/1.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=200).read().decode("utf-8"))
    stops = [
        {"lat": e["lat"], "lon": e["lon"],
         "name": (e.get("tags") or {}).get("name", ""),
         "en": (e.get("tags") or {}).get("name:en", "")}
        for e in d["elements"]
    ]
    with open(RAW, "w", encoding="utf-8") as f:
        json.dump(stops, f, ensure_ascii=False)
    return stops


def main():
    busstops = fetch_busstops()
    named = [(b, fold(b["name"]), fold(b["en"])) for b in busstops if b["name"] or b["en"]]
    print(f"OSM-এ বাস স্টপ: {len(busstops)} (নাম আছে {len(named)}টির)")

    geo = load(os.path.join(ROOT, "data", "geocode-cache.json"), {}) or {}
    ov = load(os.path.join(HERE, "overrides.json"), {}) or {}
    bn_names = load(os.path.join(HERE, "bangla-names.json"), {}) or {}

    pos = {k: (v["lat"], v["lon"]) for k, v in geo.items() if v}
    pos.update({k: (v["lat"], v["lon"]) for k, v in ov.items()
                if isinstance(v, dict) and "lat" in v})

    # আমার নিজের সব স্টপেজের নাম — একটার জায়গায় আরেকটা যেন না বসে
    own_folds = {fold(s) for s in pos} | {fold(v) for v in bn_names.values()}
    own_folds.discard("")

    snap, by_name, by_near, kept = {}, 0, 0, 0
    for stop, p in sorted(pos.items()):
        keys = {fold(stop), fold(bn_names.get(stop, ""))} - {""}

        def matches(k, cand):
            """স্টপেজের নাম k আর OSM-এর নাম cand — এক জায়গা কি না।

            চারটা পাহারা:
            • খালি স্ট্রিং বাদ — name:en না থাকলে cand খালি হয়, আর ""
              সব লেখার ভেতরেই 'পাওয়া যায়'।
            • সংখ্যা হুবহু মিলতে হবে — মিরপুর ১২ আর মিরপুর ১১ এক নয়।
            • অংশ-মিলে দুই নামের দৈর্ঘ্য কাছাকাছি হতে হবে — নইলে
              "টঙ্গী" মিলে যায় "এনা কাউন্টার টঙ্গী"-র সাথে।
            • cand যদি হুবহু আমারই অন্য কোনো স্টপেজের নাম হয়, বাদ —
              "Airport" যেন "Old Airport"-এ গিয়ে না বসে।
            """
            if not k or not cand:
                return False
            if digits(k) != digits(cand):
                return False
            if k == cand:
                return True
            if cand in own_folds and cand not in keys:
                return False
            if len(k) < 5 or len(cand) < 5:
                return False
            if not (k in cand or cand in k):
                return False
            return min(len(k), len(cand)) / max(len(k), len(cand)) >= 0.6

        best_named, best_near = None, None
        for b, bfold, befold in named:
            d = gc(p, (b["lat"], b["lon"]))
            if d > NAME_MAX_KM:
                continue
            hit = any(matches(k, bfold) or matches(k, befold) for k in keys)
            if hit and (best_named is None or d < best_named[0]):
                best_named = (d, b)

        if best_named is None:
            for b in busstops:
                d = gc(p, (b["lat"], b["lon"]))
                if d <= NEAR_MAX_KM and (best_near is None or d < best_near[0]):
                    best_near = (d, b)

        pick = best_named or best_near
        if pick:
            d, b = pick
            snap[stop] = {
                "lat": round(b["lat"], 6), "lon": round(b["lon"], 6),
                "moved_km": round(d, 3),
                "how": "নাম মিলেছে" if best_named else "সবচেয়ে কাছের বাস স্টপ",
                "osm_name": b["name"] or b["en"],
            }
            if best_named:
                by_name += 1
            else:
                by_near += 1
        else:
            kept += 1

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    print(f"নাম মিলিয়ে বসানো : {by_name}")
    print(f"কাছের স্টপে বসানো: {by_near}")
    print(f"অপরিবর্তিত        : {kept}")
    far = sorted(((v["moved_km"], k, v) for k, v in snap.items()), reverse=True)[:12]
    print("\nসবচেয়ে বেশি সরেছে যেগুলো (চোখে দেখে নেওয়া ভালো):")
    for d, k, v in far:
        print(f"  {d:5.2f} km  {k:22s} → {v['osm_name'][:40]:40s} [{v['how']}]")


if __name__ == "__main__":
    main()
