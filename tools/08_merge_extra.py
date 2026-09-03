# -*- coding: utf-8 -*-
"""অন্য একটা সাইটের রুট তালিকা থেকে বাড়তি বাসগুলো নিয়ে আসে।

dhakabusroute.vercel.app-এর ডেটাও busroutebd থেকেই আসা, কিন্তু তাদের
snapshot-টা বড় (১৮৪ বনাম ১৫৬)। যেসব বাস আমাদের তালিকায় নেই, সেগুলো
যোগ করে নিই।

ইনপুট : data/extra-source.json  (ওই সাইটের JS চাঙ্ক থেকে বের করা)
আউটপুট: data/extra-routes.json  (যা যা নতুন)
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def parse_chunk(path):
    """Next.js-এর বান্ডল থেকে {id, bus, route} রেকর্ডগুলো তুলে আনি।"""
    with open(path, encoding="utf-8", errors="replace") as f:
        s = f.read()
    out = []
    for m in re.finditer(r'\{id:(\d+),bus:"([^"]*)",route:"([^"]*)"', s):
        _id, bus, route = m.group(1), m.group(2), m.group(3)
        stops = [x.strip() for x in route.split("⇄") if x.strip()]
        if len(stops) < 2:
            continue
        # "Achim Paribahan Bus Route (আছিম পরিবহন)" → ইংরেজি নাম + বাংলা নাম
        bn = ""
        mb = re.search(r"\(([^)]*)\)\s*$", bus)
        if mb:
            bn = mb.group(1).strip()
        en = re.sub(r"\([^)]*\)\s*$", "", bus)
        en = re.sub(r"\s*Bus Route\s*$", "", en).strip()
        out.append({"en": en, "bn": bn, "stops": stops})
    return out


def key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    src = os.path.join(ROOT, "data", "extra-source.js")
    if not os.path.exists(src):
        raise SystemExit(f"পাওয়া যায়নি: {src}")

    theirs = parse_chunk(src)
    mine = load(os.path.join(ROOT, "data", "routes-clean.json"))
    have = {key(r["name_en"]) for r in mine}

    new = [t for t in theirs if key(t["en"]) not in have]
    print(f"তাদের রুট      : {len(theirs)}")
    print(f"আমাদের রুট     : {len(mine)}")
    print(f"নতুন যোগ হবে   : {len(new)}")

    with open(os.path.join(ROOT, "data", "extra-routes.json"), "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, indent=1)

    for t in new[:20]:
        print(f"   {t['en']:34s} {t['bn']:26s} {len(t['stops'])} স্টপেজ")

    # নতুন কোন কোন স্টপেজের নাম আসছে
    mystops = set()
    for r in mine:
        mystops.update(r["stops"])
    fresh = sorted({s for t in new for s in t["stops"]} - mystops)
    print(f"\nনতুন স্টপেজের নাম: {len(fresh)}")
    print("  " + ", ".join(fresh[:40]))


if __name__ == "__main__":
    main()
