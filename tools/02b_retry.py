# -*- coding: utf-8 -*-
"""যেসব স্টপেজ প্রথম চেষ্টায় পাওয়া যায়নি, সেগুলো বিকল্প নামে খুঁজি।

Nominatim-এ অনেক জায়গার নাম অন্যভাবে লেখা — "Chiriyakhana" নেই কিন্তু
"Bangladesh National Zoo" আছে। ফলাফল চোখে দেখে যাচাই করার জন্য
display_name সহ ছাপা হয়; ঠিক থাকলে overrides.json-এ বসে।
"""
import json
import os
import time

import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

spec = importlib.util.spec_from_file_location("geo", os.path.join(HERE, "02_geocode.py"))
geo_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo_mod)

# স্টপেজ → যেসব নামে খুঁজে দেখব (প্রথমে যেটা পাওয়া যায় সেটাই নেওয়া হয়)
ALT = {
    "Arambagh Kingdom":   ["Arambagh, Motijheel, Dhaka", "Arambagh, Dhaka"],
    "Baromi":             ["Baromi Bazar, Sreepur, Gazipur", "Barmi, Sreepur, Gazipur"],
    "Chiriyakhana":       ["Bangladesh National Zoo, Mirpur, Dhaka", "National Zoo Dhaka"],
    "Dainik Bangla Moor": ["Dainik Bangla Mor, Dhaka", "Dainik Bangla, Motijheel, Dhaka"],
    "Gazipur Chourasta":  ["Chowrasta, Gazipur", "Gazipur Chowrasta, Gazipur Sadar"],
    "Golapbag Chourasta": ["Golapbagh, Dhaka", "Golap Bagh, Jatrabari, Dhaka"],
    "Ittefaq Moor":       ["Ittefaq Mor, Dhaka", "Ittefaq, Tikatuli, Dhaka"],
    "Jakir Hossen Road":  ["Zakir Hossain Road, Mohammadpur, Dhaka", "Jakir Hossain Road, Dhaka"],
    "Janapath Moor":      ["Jonopoth Mor, Uttara, Dhaka", "Janapath Road, Uttara, Dhaka"],
    "Jarun":              ["Jarun, Konabari, Gazipur", "Jarun, Gazipur"],
    "Kanchan Bridge":     ["Kanchan Bridge, Rupganj, Narayanganj", "Kanchan Setu, Narayanganj"],
    "Kuchimura":          ["Kuchimura, Savar, Dhaka", "Kuchimuri, Savar"],
    "Kuril Chourasta":    ["Kuril, Dhaka", "Kuril Chowrasta, Dhaka"],
    "Madhya Badda":       ["Middle Badda, Dhaka", "Madhya Badda, Badda, Dhaka"],
    "Matsya Bhaban":      ["Matshya Bhaban, Dhaka", "Matsya Bhaban intersection, Ramna, Dhaka"],
    "Nila Market":        ["Nilar Market, Purbachal, Dhaka", "Nila Market, Rupganj"],
    "Shanir Akhra":       ["Shanir Akhra, Dhaka", "Sanir Akhra, Jatrabari, Dhaka"],
    "Shia Mosque":        ["Shia Masjid, Mohammadpur, Dhaka", "Shia Mosque, Mohammadpur"],
}


def main():
    cache_path = os.path.join(ROOT, "data", "geocode-cache.json")
    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)

    todo = [k for k in ALT if not cache.get(k)]
    print(f"আবার চেষ্টা করব {len(todo)}টি\n")

    for name in todo:
        found = None
        for q in ALT[name]:
            try:
                hit = geo_mod.pick(geo_mod.search(q, bounded=False))
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
        cache[name] = found
        if found:
            print(f"OK  {name}\n    → {found['lat']:.5f}, {found['lon']:.5f}  [{found['query']}]\n    {found['display'][:110]}\n")
        else:
            print(f"--  {name}: কিছুই মিলল না\n")

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    still = [k for k, v in cache.items() if not v]
    print(f"এখনো বাকি {len(still)}: {', '.join(still)}")


if __name__ == "__main__":
    main()
