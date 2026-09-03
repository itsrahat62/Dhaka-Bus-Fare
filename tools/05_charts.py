# -*- coding: utf-8 -*-
"""বিআরটিএ-র অফিসিয়াল ভাড়ার চার্ট (স্ক্যান করা PDF) → সাইটে দেখানোর ছবি।

প্রতিটা পাতা এক-একটা রুটের চার্ট: উপরে রুটের নাম ও মোট দূরত্ব, নিচে
স্টপেজ-থেকে-স্টপেজ ভাড়ার ছক। এই স্ক্রিপ্ট —

  ১. প্রতিটা পাতাকে সাইটে দেখানোর মতো JPEG বানায় (site/charts/)
  ২. উপরের শিরোনামের অংশটুকু কেটে কয়েকটা একসাথে জুড়ে দেয়, যাতে
     কোন পাতা কোন রুটের সেটা পড়ে তালিকা বানানো যায় (data/headers/)

ধাপ ২-এর ছবিগুলো পড়ে data/chart-index.json হাতে লেখা হয়।
"""
import os
import sys

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PDF_DIR = os.path.join(ROOT, "data", "brta")
CHART_DIR = os.path.join(ROOT, "site", "charts")
HEAD_DIR = os.path.join(ROOT, "data", "headers")

PARTS = 5
PAGE_W = 1400          # সাইটে দেখানোর ছবির চওড়া
HEAD_TOP = 0.06        # শিরোনাম শুরু হয় পাতার এই অংশ থেকে
HEAD_BOT = 0.22        # আর শেষ এখানে
PER_SHEET = 8          # একটা শিটে কয়টা শিরোনাম
SHEET_W = 1150


def render():
    os.makedirs(CHART_DIR, exist_ok=True)
    os.makedirs(HEAD_DIR, exist_ok=True)
    heads = []

    for part in range(1, PARTS + 1):
        path = os.path.join(PDF_DIR, f"part{part}.pdf")
        if not os.path.exists(path):
            sys.exit(f"পাওয়া যায়নি: {path}")
        doc = pymupdf.open(path)
        for pno in range(len(doc)):
            page = doc[pno]
            zoom = PAGE_W / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            name = f"p{part}-{pno + 1:02d}"
            img.convert("L").save(os.path.join(CHART_DIR, name + ".jpg"),
                                  quality=72, optimize=True)
            heads.append((name, img.crop((0, int(img.height * HEAD_TOP),
                                          img.width, int(img.height * HEAD_BOT)))))
        n = len(doc)
        doc.close()
        print(f"part{part}: {n} পাতা")

    # শিরোনামগুলো কয়েকটা করে এক শিটে — পড়ে তালিকা বানানোর জন্য।
    # লেবেল শেষে বসাই, রিসাইজের পরে, নইলে ছোট হয়ে পড়া যায় না।
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:      # পুরোনো Pillow
        font = ImageFont.load_default()

    band = 34
    for i in range(0, len(heads), PER_SHEET):
        group = heads[i:i + PER_SHEET]
        rows = [(name, h.resize((SHEET_W, int(h.height * SHEET_W / h.width))))
                for name, h in group]
        sheet = Image.new("L", (SHEET_W, sum(r.height + band for _, r in rows)), 255)
        y = 0
        for _, row in rows:
            y += band
            sheet.paste(row.convert("L"), (0, y))
            y += row.height

        draw = ImageDraw.Draw(sheet)
        y = 0
        for name, row in rows:
            draw.rectangle([0, y, SHEET_W, y + band - 2], fill=210)
            draw.text((12, y + 4), f">>> {name} <<<", fill=0, font=font)
            y += band + row.height

        sheet.save(os.path.join(HEAD_DIR, f"sheet{i // PER_SHEET + 1:02d}.png"))

    total = sum(os.path.getsize(os.path.join(CHART_DIR, f))
                for f in os.listdir(CHART_DIR)) / 1024 / 1024
    print(f"\nমোট {len(heads)} পাতা → site/charts/ ({total:.1f} MB)")
    print(f"শিরোনামের শিট: {len(range(0, len(heads), PER_SHEET))}টি → data/headers/")


if __name__ == "__main__":
    render()
