# -*- coding: utf-8 -*-
"""চার্টের স্টপেজের নামগুলো আমাদের তালিকার সাথে মেলায়।

চার্টে লেখা "মিরপুর-১২", আমাদের তালিকায় "মিরপুর ১২" — এক জায়গা, দুই
বানান। ৩৭১টা নাম মিলিয়ে দেখা হয়। যেগুলো মেলে না সেগুলো বাদ যায় না,
শুধু ওই স্টপেজ দিয়ে খোঁজা যায় না (চার্টের বাকি অংশ কাজ করে)।

আউটপুট: data/chart-resolved.json
    { পাতা: { "stops": [[আমাদের স্টপেজ|null, চার্টের নাম, কিমি], ...] } }
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# নামের সাথে লেগে থাকা শব্দ, মেলানোর সময় ফেলে দিই
NOISE = re.compile(
    r"(বাস\s*স্ট্যান্ড|বাসস্ট্যান্ড|বাস\s*স্টপ|স্ট্যান্ড|ষ্টেশন|স্টেশন|"
    r"ব্রীজ|ব্রিজ|ব্রীজ\s*পাড়|চত্বর|চৌরাস্তা|মোড়|বাজার|নং|"
    r"ফ্লাইওভার|এতিমখানা|মন্দির|হোটেল)"
)


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fold(s, drop_noise=True):
    """বাংলা নামকে মেলানোর উপযোগী রূপে আনি।"""
    s = unicodedata.normalize("NFC", s)
    if drop_noise:
        s = NOISE.sub(" ", s)
    s = re.sub(r"[\s\-–—.,()\[\]/]+", "", s)
    for a, b in (
        ("সায়দাবাদ", "সায়েদাবাদ"), ("সায়েদাবাদ", "সায়েদাবাদ"),
        ("নারায়নগঞ্জ", "নারায়ণগঞ্জ"), ("ধওর", "ধউর"),
        ("কেরাণীগঞ্জ", "কেরানীগঞ্জ"), ("বেড়ীবাঁধ", "বেড়িবাঁধ"),
        ("মোঃপুর", "মোহাম্মদপুর"), ("মোঃবাসস্ট্যান্ড", "মোহাম্মদপুর"),
        ("জসীমউদ্দিন", "জসীমউদ্দীন"), ("সাইন্সল্যাব", "সায়েন্সল্যাব"),
        ("সাইন্সল্যাবঃ", "সায়েন্সল্যাব"), ("এয়ারপোর্ট", "বিমানবন্দর"),
        ("কাওরানবাজার", "কারওয়ানবাজার"), ("কাওরান", "কারওয়ান"),
        ("অরিজিনালদশ", "মিরপুর১০"), ("অরিজিনাল১০", "মিরপুর১০"),
        ("সনিসিনেমাহল", "সনিসিনেমাহল"),
        ("ী", "ি"), ("ূ", "ু"), ("ণ", "ন"), ("ষ", "শ"), ("স", "শ"),
        ("০", "0"), ("১", "1"), ("২", "2"), ("৩", "3"), ("৪", "4"),
        ("৫", "5"), ("৬", "6"), ("৭", "7"), ("৮", "8"), ("৯", "9"),
    ):
        s = s.replace(a, b)
    return s


def build_index(stops_bn):
    """আমাদের স্টপেজের সব সম্ভাব্য রূপ → স্টপেজের নাম।"""
    idx = {}
    for en, bn in stops_bn.items():
        for form in (fold(bn), fold(bn, drop_noise=False), fold(en)):
            if form and form not in idx:
                idx[form] = en
    return idx


def resolve(name, idx, manual, live):
    """চার্টের একটা নাম → আমাদের স্টপেজ, নাহলে None।"""
    # হাতে বসানো তালিকা সবার আগে — ওটাই সবচেয়ে নির্ভরযোগ্য
    hit = manual.get(name.strip())
    if hit:
        return hit if hit in live else None
    for form in (fold(name), fold(name, drop_noise=False)):
        if form in idx:
            return idx[form]
    # আংশিক মিল: চার্টের নাম আমাদের নামের ভেতরে বা উল্টোটা
    f = fold(name)
    if len(f) >= 5:
        best, best_len = None, 0
        for form, en in idx.items():
            if len(form) < 5:
                continue
            if (f in form or form in f) and len(form) > best_len:
                ratio = min(len(f), len(form)) / max(len(f), len(form))
                if ratio >= 0.7:
                    best, best_len = en, len(form)
        return best
    return None


def main():
    charts = load(os.path.join(ROOT, "data", "chart-stops.json"))
    bn = load(os.path.join(HERE, "bangla-names.json"), {}) or {}
    site = load(os.path.join(ROOT, "site", "data", "data.json"))
    live = {s["en"] for s in site["stops"]}

    stops_bn = {en: b for en, b in bn.items() if en in live}
    idx = build_index(stops_bn)
    manual = {k.strip(): v for k, v in
              (load(os.path.join(HERE, "chart-aliases.json"), {}) or {}).items()
              if not k.startswith("_")}

    out, hit, miss = {}, 0, {}
    for page, rows in charts.items():
        if page.startswith("_"):
            continue
        resolved = []
        for name, km in rows:
            en = resolve(name, idx, manual, live)
            resolved.append([en, name, km])
            if en:
                hit += 1
            else:
                miss[name] = miss.get(name, 0) + 1
        out[page] = resolved

    total = sum(len(v) for v in out.values())
    print(f"চার্টের সারি   : {total}")
    print(f"মিলেছে         : {hit} ({hit / total * 100:.0f}%)")
    print(f"মেলেনি         : {total - hit}, আলাদা নাম {len(miss)}টি")

    # প্রতিটা চার্টে অন্তত দুইটা চেনা স্টপেজ আছে কিনা — নইলে কাজে লাগে না
    usable = sum(1 for v in out.values() if sum(1 for r in v if r[0]) >= 2)
    print(f"কাজে লাগবে     : {usable} / {len(out)} চার্ট")

    with open(os.path.join(ROOT, "data", "chart-resolved.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)

    print("\nযে নামগুলো সবচেয়ে বেশি মেলেনি:")
    for name, n in sorted(miss.items(), key=lambda x: -x[1])[:25]:
        print(f"   {n:2d}×  {name}")


if __name__ == "__main__":
    main()
