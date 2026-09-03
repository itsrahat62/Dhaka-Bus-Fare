# -*- coding: utf-8 -*-
"""কোন বাসের ভাড়া কোন সরকারি চার্টে — সেটা মিলিয়ে দেয়।

বিআরটিএ-র চার্ট রুট নম্বর ধরে (এ-৩২০), আর আমাদের ডেটা বাস কোম্পানির নাম
ধরে। মেলানোর সূত্র চার্টের দুই প্রান্ত: "চিড়িয়াখানা হতে যাত্রাবাড়ী"
চার্টটা সেই বাসের জন্য প্রযোজ্য যে চিড়িয়াখানা আর যাত্রাবাড়ী — দুইটা
স্টপেজেই যায়।

খেয়াল রাখার বিষয়: কোম্পানির রুট প্রায়ই চার্টের রুটের চেয়ে লম্বা।
"বিকল্প" বাস মিরপুর-১২ থেকে মতিঝিল হয়ে আরও দূরে যায়। তখন চার্টটা
পুরো রুটের নয়, ওই দুই স্টপেজের মাঝের অংশটুকুর। তাই দুই প্রান্ত
রুটের যেকোনো জায়গায় থাকলেই চলে — শুধু শুরু-শেষ হতে হবে না।

আউটপুট: data/chart-match.json
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

NOISE = re.compile(r"(বাস স্ট্যান্ড|বাসস্ট্যান্ড|বাস স্টপ|স্ট্যান্ড|ব্রীজ|ব্রিজ|চত্বর|মোড়|নং)")


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fold(s):
    s = NOISE.sub(" ", s)
    s = re.sub(r"[\s\-–—.,()\[\]]+", "", s)
    for a, b in (("সায়দাবাদ", "সায়েদাবাদ"), ("নারায়নগঞ্জ", "নারায়ণগঞ্জ"),
                 ("ধওর", "ধউর"), ("ভায়ানটেক", "ভাসানটেক"),
                 ("কেরাণীগঞ্জ", "কেরানীগঞ্জ"), ("বেড়ীবাঁধ", "বেড়িবাঁধ"),
                 ("ী", "ি"), ("ূ", "ু"), ("ণ", "ন"), ("ষ", "শ"), ("স", "শ")):
        s = s.replace(a, b)
    return s


def variants(name):
    """"মিরপুর-১ (সনি সিনেমা হল)" → পুরোটা, বাইরের অংশ, ভেতরের অংশ।"""
    out = {fold(name), fold(re.sub(r"\([^)]*\)", " ", name))}
    out.update(fold(x) for x in re.findall(r"\(([^)]*)\)", name))
    return {v for v in out if len(v) >= 3}


def resolve(chart_name, stop_variants):
    """চার্টের একটা জায়গার নাম → আমার কোন স্টপেজ (না মিললে None)।"""
    want = variants(chart_name)
    best, best_score = None, 0.0
    for stop, sv in stop_variants.items():
        score = 0.0
        for a in want:
            for b in sv:
                if a == b:
                    score = 1.0
                elif len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                    score = max(score, 0.75)
        if score > best_score:
            best, best_score = stop, score
    return best if best_score >= 0.75 else None


def main():
    routes = load(os.path.join(ROOT, "data", "routes-clean.json"))
    charts = load(os.path.join(ROOT, "data", "chart-index.json"))["pages"]
    bn = load(os.path.join(HERE, "bangla-names.json"), {}) or {}
    osrm = load(os.path.join(ROOT, "data", "osrm-cache.json"), {}) or {}

    stops = sorted({s for r in routes for s in r["stops"]})
    stop_variants = {s: variants(bn.get(s, s)) | variants(s) for s in stops}

    # ১. চার্টের দুই প্রান্ত আমার কোন স্টপেজ
    resolved, unresolved = [], []
    for c in charts:
        a = resolve(c["from"], stop_variants)
        b = resolve(c["to"], stop_variants)
        if a and b and a != b:
            resolved.append({**c, "a": a, "b": b})
        else:
            unresolved.append(f"{c['page']} {c['from']}↔{c['to']}")
    print(f"চার্টের দুই প্রান্তই চেনা গেছে: {len(resolved)} / {len(charts)}")

    # ২. কোন বাস ওই দুই স্টপেজেই যায়
    match, counts = {}, 0
    for r in routes:
        seq = (osrm.get(r["id"]) or {}).get("stops") or r["stops"]
        idx = {s: i for i, s in enumerate(seq)}
        best = None
        for c in resolved:
            if c["a"] not in idx or c["b"] not in idx:
                continue
            span = abs(idx[c["b"]] - idx[c["a"]])
            if span < 2:
                continue
            # রুটের যত বেশি অংশ চার্টটা ঢাকে, তত ভালো
            if best is None or span > best[0]:
                best = (span, c)
        if best:
            _, c = best
            match[r["id"]] = {"page": c["page"], "no": c["no"], "from": c["from"],
                              "to": c["to"], "a": c["a"], "b": c["b"],
                              "km": c.get("km")}
            counts += 1

    with open(os.path.join(ROOT, "data", "chart-match.json"), "w", encoding="utf-8") as f:
        json.dump(match, f, ensure_ascii=False, indent=1)

    print(f"চার্ট পাওয়া গেছে : {counts} / {len(routes)} বাসে")
    print(f"ব্যবহৃত চার্ট     : {len({v['page'] for v in match.values()})}")
    if unresolved:
        print(f"\nযেসব চার্টের প্রান্ত চেনা গেল না ({len(unresolved)}):")
        print("  " + "\n  ".join(unresolved[:15]))


if __name__ == "__main__":
    main()
