# -*- coding: utf-8 -*-
"""স্টপেজের অবস্থান ঠিক আছে কিনা যাচাই করি।

ধারণাটা সোজা: একই রুটের পরপর দুই স্টপেজ কাছাকাছিই থাকে। অনেক দূরে
দেখালে বুঝতে হবে দুইটার একটা ভুল জায়গায় বসেছে। যে স্টপেজ বারবার এমন
লাফের সাথে জড়িত, সেটাই দোষী।

শহরের ভেতরে স্টপেজ ঘন, তাই সেখানে সীমা কড়া (৪ কিমি)। বাইরে বাসস্ট্যান্ড
দূরে দূরে, তাই ঢিলা (১২ কিমি)। এই ভাগটা জরুরি — ১২ কিমি সীমায় "কাকলী
শ্যামলীতে বসে আছে" বা "কলেজ গেট খিলগাঁওয়ে" ধরা পড়ে না।
"""
import collections
import json
import math
import os

import stoppos

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CENTRE = (23.78, 90.40)
INNER_RADIUS_KM = 18.0
INNER_JUMP_KM = 4.0
OUTER_JUMP_KM = 12.0


def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def gc(a, b):
    """দুই বিন্দুর সরলরেখার দূরত্ব, কিলোমিটারে।"""
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main():
    routes = load(os.path.join(ROOT, "data", "routes-clean.json"))
    geo = load(os.path.join(ROOT, "data", "geocode-cache.json"), {}) or {}
    snap = load(os.path.join(ROOT, "data", "busstop-snap.json"), {}) or {}
    ov = load(os.path.join(HERE, "overrides.json"), {}) or {}
    pos = stoppos.positions()

    inner = {k for k, p in pos.items() if gc(p, CENTRE) < INNER_RADIUS_KM}

    blame = collections.Counter()
    worst = []
    for r in routes:
        seq = [s for s in r["stops"] if s in pos]
        for a, b in zip(seq, seq[1:]):
            limit = INNER_JUMP_KM if (a in inner and b in inner) else OUTER_JUMP_KM
            d = gc(pos[a], pos[b])
            if d > limit:
                blame[a] += 1
                blame[b] += 1
                worst.append((d, a, b, r["name_en"]))

    worst.sort(reverse=True)
    print(f"সন্দেহজনক লাফ: {len(worst)}টি "
          f"(শহরে {INNER_JUMP_KM} কিমি, বাইরে {OUTER_JUMP_KM} কিমির বেশি)\n")

    def source(name):
        if name in ov:
            return "হাতে বসানো (override)"
        if name in snap:
            return "বাস স্টপে বসানো: " + (snap[name].get("osm_name") or "")
        return (geo.get(name) or {}).get("display", "")

    print("যেসব স্টপেজ বারবার জড়িত (আগে এগুলো দেখুন):")
    for name, n in blame.most_common(18):
        p = pos[name]
        print(f"  {n:3d}×  {name:22s} {p[0]:.4f},{p[1]:.4f}  {source(name)[:52]}")

    print("\nসবচেয়ে বড় লাফ:")
    for d, a, b, rt in worst[:12]:
        print(f"  {d:6.1f} km  {a} → {b}   ({rt})")

    if not worst:
        print("সব ঠিক আছে।")


if __name__ == "__main__":
    main()
