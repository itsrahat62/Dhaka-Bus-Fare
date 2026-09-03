# -*- coding: utf-8 -*-
"""ম্যাপের লাইন হালকা করার কাজ।

OSRM যে লাইন দেয় তাতে প্রতি কয়েক মিটারে একটা করে বিন্দু — মোট প্রায়
২,৭০,০০০। শহরের জুমে অত নিখুঁত হওয়ার দরকার নেই; ১০ মিটার সহনশীলতায়
কমিয়ে আনলে চোখে ধরা পড়ে না, অথচ ডেটা ৮০% কমে যায়। ঢাকার মানুষ মোবাইল
ডেটা দিয়ে ঢুকবে — এটা গুরুত্বপূর্ণ।
"""
import math
import sys

DHAKA_LAT = 23.8
DEG_PER_M = 1 / 111000.0


def decode(s, precision=5):
    """Google polyline → [(lat, lon)]"""
    factor = 10 ** precision
    pts, idx, lat, lng = [], 0, 0, 0
    while idx < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[idx]) - 63
                idx += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lng += delta
        pts.append((lat / factor, lng / factor))
    return pts


def encode(pts, precision=5):
    """[(lat, lon)] → Google polyline"""
    factor = 10 ** precision
    out, plat, plng = [], 0, 0

    def one(v):
        v = ~(v << 1) if v < 0 else v << 1
        s = ""
        while v >= 0x20:
            s += chr((0x20 | (v & 0x1f)) + 63)
            v >>= 5
        return s + chr(v + 63)

    for lat, lng in pts:
        la, ln = round(lat * factor), round(lng * factor)
        out.append(one(la - plat))
        out.append(one(ln - plng))
        plat, plng = la, ln
    return "".join(out)


def simplify(pts, tolerance_m=10.0):
    """Douglas–Peucker — যে বিন্দুগুলো লাইনের আকার বদলায় না, বাদ দিই।"""
    if len(pts) < 3:
        return pts
    tol = tolerance_m * DEG_PER_M
    kx = math.cos(math.radians(DHAKA_LAT))   # দ্রাঘিমাংশ অক্ষাংশে সরু হয়

    def perp(p, a, b):
        y0, x0 = p[0], p[1] * kx
        y1, x1 = a[0], a[1] * kx
        y2, x2 = b[0], b[1] * kx
        den = math.hypot(y2 - y1, x2 - x1)
        if not den:
            return math.hypot(y0 - y1, x0 - x1)
        return abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / den

    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, len(pts) + 100))
    try:
        def dp(lo, hi):
            if hi <= lo + 1:
                return []
            dmax, imax = 0.0, lo
            for i in range(lo + 1, hi):
                d = perp(pts[i], pts[lo], pts[hi])
                if d > dmax:
                    dmax, imax = d, i
            if dmax > tol:
                return dp(lo, imax) + [imax] + dp(imax, hi)
            return []

        keep = [0] + dp(0, len(pts) - 1) + [len(pts) - 1]
    finally:
        sys.setrecursionlimit(old)
    return [pts[i] for i in keep]


def shrink(polyline, tolerance_m=10.0):
    """এনকোড করা লাইন → হালকা করা এনকোড করা লাইন।"""
    return encode(simplify(decode(polyline), tolerance_m))
