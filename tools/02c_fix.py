# -*- coding: utf-8 -*-
"""ভুল জায়গায় বসে যাওয়া স্টপেজগুলো ঠিক করি।

সমস্যা: "Kazla" নামে রাজশাহীতেও একটা জায়গা আছে, "Technical" নামে
কাপাসিয়ায় একটা পুকুর আছে। Nominatim ওগুলোই ধরেছিল। তাই এবার প্রতিটার
জন্য নির্দিষ্ট এলাকা বেঁধে দিয়ে খুঁজি, আর ফলাফল চোখে দেখে যাচাই করি।
"""
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UA = "DhakaBusFare/1.0 (open-source bus fare map; contact via github)"

# এলাকার সীমানা: left,top,right,bottom
BOX = {
    "city":    "90.32,23.90,90.50,23.68",   # ঢাকা মহানগর
    "savar":   "90.20,24.00,90.40,23.80",   # সাভার–আশুলিয়া
    "gazipur": "90.15,24.10,90.50,23.90",   # গাজীপুর
}

# স্টপেজ → (কোন এলাকা, কোন কোন নামে খুঁজব)
FIX = {
    "Kazla":         ("city", ["Kazla, Jatrabari, Dhaka", "Kazla, Dhaka"]),
    "ECB Square":    ("city", ["ECB Chattar, Dhaka", "ECB Square, Matikata, Dhaka"]),
    "Technical":     ("city", ["Technical Mor, Darussalam, Dhaka", "Technical, Mirpur, Dhaka"]),
    "MES":           ("city", ["MES, Cantonment, Dhaka", "MES Bus Stop, Dhaka"]),
    "Fulbaria":      ("city", ["Fulbaria, Gulistan, Dhaka", "Fulbaria Bus Terminal, Dhaka"]),
    "Abdullahpur":   ("city", ["Abdullahpur, Uttara, Dhaka", "Abdullahpur Bus Stop, Uttara"]),
    "TT Para":       ("city", ["TT Para, Kamalapur, Dhaka", "Titipara, Khilgaon, Dhaka"]),
    "Ashulia Bazar": ("savar", ["Ashulia Bazar, Ashulia, Savar", "Ashulia, Savar, Dhaka"]),
    "Baipayl":       ("savar", ["Baipail, Ashulia, Savar", "Baipail Bus Stand, Savar"]),
    "Proshika Moor": ("savar", ["Proshika Mor, Ashulia, Savar", "Proshika, Savar, Dhaka"]),
    "Chandra":       ("gazipur", ["Chandra, Kaliakair, Gazipur", "Chandra Bus Stand, Kaliakair"]),
}


def search(q, box):
    params = {
        "q": q, "format": "jsonv2", "limit": "5",
        "namedetails": "1", "accept-language": "bn,en",
        "viewbox": box, "bounded": "1",
    }
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def pick(rs):
    if not rs:
        return None
    good = {"suburb", "neighbourhood", "quarter", "town", "village", "bus_stop",
            "bus_station", "junction", "square", "marketplace", "locality"}
    return sorted(rs, key=lambda r: (0 if r.get("type") in good else 1,
                                     -float(r.get("importance") or 0)))[0]


def main():
    path = os.path.join(ROOT, "data", "geocode-cache.json")
    with open(path, encoding="utf-8") as f:
        cache = json.load(f)

    for name, (area, queries) in FIX.items():
        found = None
        for q in queries:
            try:
                hit = pick(search(q, BOX[area]))
            except Exception as e:
                print(f"  ! {name}: {e}")
                hit = None
            time.sleep(1.1)
            if hit:
                nd = hit.get("namedetails") or {}
                found = {
                    "lat": float(hit["lat"]), "lon": float(hit["lon"]),
                    "bn": nd.get("name:bn") or "",
                    "osm_name": hit.get("name") or "",
                    "type": f"{hit.get('category')}/{hit.get('type')}",
                    "display": hit.get("display_name", ""),
                    "query": q,
                }
                break
        if found:
            old = cache.get(name) or {}
            print(f"OK  {name}")
            print(f"    আগে : {old.get('lat','?')},{old.get('lon','?')}  {old.get('display','')[:60]}")
            print(f"    এখন : {found['lat']:.5f},{found['lon']:.5f}  {found['display'][:60]}\n")
            cache[name] = found
        else:
            print(f"--  {name}: ঠিক করা গেল না\n")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
