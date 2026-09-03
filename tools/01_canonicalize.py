# -*- coding: utf-8 -*-
"""busroutebd স্ক্র্যাপ ডেটা → পরিষ্কার canonical রুট + স্টপেজ লিস্ট।

ইনপুট : data/source-busroutebd.json, tools/aliases.json
আউটপুট: data/routes-clean.json, data/stops-english.txt
"""
import json
import os
import re
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    """সাদামাটা পরিষ্কার: extra স্পেস, ঝুলে থাকা ড্যাশ/কমা বাদ।"""
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" -,.")
    return s


def main():
    src = load(os.path.join(ROOT, "data", "source-busroutebd.json"))["data"]

    # দ্বিতীয় উৎসে (dhakabusroute) আরও কিছু বাস আছে — সেগুলোও নিই
    extra = load(os.path.join(ROOT, "data", "extra-routes.json"), []) or []
    src = src + [{"english": e["en"], "bangle": e["bn"], "routes": e["stops"],
                  "service_type": ""} for e in extra]
    if extra:
        print(f"দ্বিতীয় উৎস থেকে বাড়তি বাস: {len(extra)}")

    rules = load(os.path.join(HERE, "aliases.json"))
    splits = {norm(k): v for k, v in rules["splits"].items()}
    aliases = {norm(k): v for k, v in rules["aliases"].items()}
    drop = {norm(x) for x in rules["drop"]}

    def canon(raw):
        """একটা raw নাম → ০, ১ বা ২টা canonical নাম।"""
        n = norm(raw)
        if n in splits:
            return [aliases.get(norm(x), norm(x)) for x in splits[n]]
        if n in drop:
            return []
        return [aliases.get(n, n)]

    routes = []
    for r in src:
        stops = []
        for raw in r["routes"]:
            for c in canon(raw):
                # পরপর একই স্টপেজ দুইবার থাকলে একবারই রাখি
                if not c or (stops and stops[-1] == c):
                    continue
                stops.append(c)
        if len(stops) < 2:
            continue
        routes.append(
            {
                "name_en": norm(r["english"]),
                "name_bn": norm(r["bangle"]),
                "service_type": norm(r.get("service_type") or ""),
                "stops": stops,
            }
        )

    # এক কোম্পানির একাধিক রুট থাকতে পারে (বিআরটিসি-র ৯টা, আলিফের ৪টা)।
    # তাই নাম নয়, আলাদা আইডি দিয়ে চিনি — নইলে একটা আরেকটাকে চাপা দেয়।
    seen = collections.Counter()
    for r in routes:
        seen[r["name_en"]] += 1
        n = seen[r["name_en"]]
        r["id"] = r["name_en"] if n == 1 else f"{r['name_en']}#{n}"

    dup_names = {k for k, v in seen.items() if v > 1}
    for r in routes:
        # একই নামের একাধিক রুট আলাদা করে চেনানোর জন্য দুই প্রান্ত জুড়ে দিই
        r["multi"] = r["name_en"] in dup_names

    counts = collections.Counter(s for r in routes for s in r["stops"])
    stops = sorted(counts, key=lambda v: v.lower())

    with open(os.path.join(ROOT, "data", "routes-clean.json"), "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=1)
    with open(os.path.join(ROOT, "data", "stops-english.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(stops))

    print(f"routes : {len(routes)}")
    print(f"stops  : {len(stops)} (আগে ছিল 301)")
    print("রুটে সবচেয়ে বেশি আসা ১৫টি:", ", ".join(f"{k} ({v})" for k, v in counts.most_common(15)))
    once = [k for k, v in counts.items() if v == 1]
    print(f"মাত্র ১টা রুটে আছে এমন স্টপেজ: {len(once)}")


if __name__ == "__main__":
    main()
