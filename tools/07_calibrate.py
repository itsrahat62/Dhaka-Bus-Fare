# -*- coding: utf-8 -*-
"""সরকারি চার্টে লেখা মোট দূরত্বের অংশটুকু কেটে আনে — মিলিয়ে দেখার জন্য।

চার্টের মাথায় লেখা থাকে "রুটের মোট দূরত্ব ১৫.৩ কিলোমিটার"। সেই লাইনটা
পড়তে পারলে আমাদের হিসাব করা দূরত্ব কতটা ঠিক, তা যাচাই করা যায়।

যেসব চার্ট কোনো না কোনো বাসের সাথে মিলেছে, শুধু সেগুলোরই শিরোনাম-অংশ
কেটে কয়েকটা শিটে সাজায়।

আউটপুট: data/headers/total<n>.png
"""
import json
import os

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TOP, BOT = 0.10, 0.30      # শিরোনাম + "মোট দূরত্ব" লাইন
PER_SHEET = 7
SHEET_W = 1100


def main():
    match = json.load(open(os.path.join(ROOT, "data", "chart-match.json"), encoding="utf-8"))
    pages = sorted({v["page"] for v in match.values()})
    print(f"যেসব চার্ট কাজে লেগেছে: {len(pages)}টি")

    crops = []
    docs = {}
    for page in pages:
        part, pno = page[1:].split("-")
        if part not in docs:
            docs[part] = pymupdf.open(os.path.join(ROOT, "data", "brta", f"part{part}.pdf"))
        pg = docs[part][int(pno) - 1]
        zoom = SHEET_W / pg.rect.width
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        crops.append((page, img.crop((0, int(img.height * TOP), img.width, int(img.height * BOT)))))

    try:
        font = ImageFont.load_default(size=24)
    except TypeError:
        font = ImageFont.load_default()

    band = 30
    for i in range(0, len(crops), PER_SHEET):
        group = crops[i:i + PER_SHEET]
        sheet = Image.new("L", (SHEET_W, sum(c.height + band for _, c in group)), 255)
        y = 0
        for _, c in group:
            y += band
            sheet.paste(c, (0, y))
            y += c.height
        draw = ImageDraw.Draw(sheet)
        y = 0
        for name, c in group:
            draw.rectangle([0, y, SHEET_W, y + band - 2], fill=205)
            draw.text((10, 3), f">>> {name} <<<", fill=0, font=font)
            y += band + c.height
        sheet.save(os.path.join(ROOT, "data", "headers", f"total{i // PER_SHEET + 1:02d}.png"))

    print(f"শিট: {len(range(0, len(crops), PER_SHEET))}টি → data/headers/total*.png")
    print("পাতা:", ", ".join(pages))


if __name__ == "__main__":
    main()
