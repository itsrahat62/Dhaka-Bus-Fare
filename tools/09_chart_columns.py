# -*- coding: utf-8 -*-
"""চার্টের বাঁ পাশের দুই কলাম (স্টপেজের নাম + কিলোমিটার) কেটে আনে।

কেন: চার্টের পুরো ভাড়ার ছকটা আসলে ওই কিলোমিটার কলাম থেকেই বানানো —
    ভাড়া = সর্বোচ্চ(১০, round(|কিমি_খ − কিমি_ক| × ২.৫৩))
১০টা ঘর মিলিয়ে দেখা হয়েছে, ১০টাই মেলে। তাই শুধু ওই কলামটা তুলে আনলেই
যেকোনো দুই স্টপেজের হুবহু সরকারি ভাড়া বলা যায় — আন্দাজ করতে হয় না।

পুরো পাতা পড়ার দরকার নেই, তাই বাঁ দিকের সরু অংশটুকু কেটে বড় করে
কয়েকটা একসাথে শিটে বসাই — পড়তে সুবিধা হয়।

আউটপুট: data/columns/col<n>.png
"""
import json
import os

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "columns")

# পাতার কোন অংশে ছকের বাঁ দুই কলাম থাকে (অনুপাতে)
LEFT, RIGHT = 0.13, 0.46
TOP, BOTTOM = 0.24, 0.80

COL_W = 560        # কেটে আনা প্রতিটা টুকরার চওড়া
PER_SHEET = 3      # এক শিটে কয়টা চার্ট


def pages():
    """সব চার্টের পাতা, ক্রম অনুযায়ী (part1 বাদ — ওটা আন্তঃজেলার সারণি)।"""
    idx = json.load(open(os.path.join(ROOT, "data", "chart-index.json"), encoding="utf-8"))
    return [p["page"] for p in idx["pages"]]


def main():
    os.makedirs(OUT, exist_ok=True)
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:
        font = ImageFont.load_default()

    docs, crops = {}, []
    for page in pages():
        part, pno = page[1:].split("-")
        if part not in docs:
            docs[part] = pymupdf.open(os.path.join(ROOT, "data", "brta", f"part{part}.pdf"))
        pg = docs[part][int(pno) - 1]

        # ভালো করে পড়ার জন্য বড় করে রেন্ডার করি
        zoom = 2600 / pg.rect.width
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        w, h = img.size
        cut = img.crop((int(w * LEFT), int(h * TOP), int(w * RIGHT), int(h * BOTTOM)))
        cut = cut.resize((COL_W, int(cut.height * COL_W / cut.width)))
        crops.append((page, cut))

    band = 34
    for i in range(0, len(crops), PER_SHEET):
        group = crops[i:i + PER_SHEET]
        gap = 14
        width = sum(c.width for _, c in group) + gap * (len(group) - 1)
        height = band + max(c.height for _, c in group)
        sheet = Image.new("L", (width, height), 255)
        x = 0
        for _, c in group:
            sheet.paste(c, (x, band))
            x += c.width + gap
        draw = ImageDraw.Draw(sheet)
        x = 0
        for name, c in group:
            draw.rectangle([x, 0, x + c.width, band - 3], fill=205)
            draw.text((x + 8, 4), f">>> {name} <<<", fill=0, font=font)
            x += c.width + gap
        sheet.save(os.path.join(OUT, f"col{i // PER_SHEET + 1:02d}.png"))

    n = len(range(0, len(crops), PER_SHEET))
    print(f"{len(crops)} চার্ট → {n}টি শিট, data/columns/")


if __name__ == "__main__":
    main()
