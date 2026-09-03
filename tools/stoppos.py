# -*- coding: utf-8 -*-
"""প্রতিটা স্টপেজের চূড়ান্ত অবস্থান — এক জায়গায়।

তিনটা উৎস, এই অগ্রাধিকারে:

১. overrides.json  — হাতে যাচাই করা। Nominatim যেখানে ভুল জেলায় বসিয়েছিল
                     বা রুটের প্রতিবেশী দেখে ঠিকটা বাছতে হয়েছে।
২. busstop-snap    — OSM-এর আসল বাস স্টপ। এলাকার কেন্দ্রবিন্দুর বদলে
                     রাস্তার উপরের বিন্দু, তাই দূরত্ব বাস্তবসম্মত হয়।
৩. geocode-cache   — Nominatim যা দিয়েছিল, শেষ ভরসা।
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(p):
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def positions():
    """{স্টপেজের নাম: (lat, lon)}"""
    pos = {}
    for name, g in _load(os.path.join(ROOT, "data", "geocode-cache.json")).items():
        if g:
            pos[name] = (g["lat"], g["lon"])
    for name, s in _load(os.path.join(ROOT, "data", "busstop-snap.json")).items():
        pos[name] = (s["lat"], s["lon"])
    for name, o in _load(os.path.join(HERE, "overrides.json")).items():
        if isinstance(o, dict) and "lat" in o:
            pos[name] = (o["lat"], o["lon"])
    return pos
