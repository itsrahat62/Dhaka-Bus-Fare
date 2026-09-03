/* গালি ছাঁকনি।

   দুই জায়গায় দুই রকম আচরণ:
   • রিভিউ — লেখাটা থাকে, গালিটুকু **** হয়ে যায়। মানুষের আসল অভিযোগটা
     হারায় না ("কন্ডাক্টর ***** দিল" — কথাটা তো ঠিকই বোঝা যায়)।
   • বাস যোগ করা — একেবারে আটকে যায়। বাসের নাম তালিকায় স্থায়ীভাবে
     বসে, ওখানে গালি ঢেকে রাখারও মানে হয় না।

   ঢাকার লেখায় মানুষ বাংলা হরফেও লেখে, ইংরেজি হরফেও ("চুতিয়া" / "chutia")।
   তাই দুইটাই ধরা হয়, আর কিছু সাধারণ ফাঁকি (অক্ষর দুইবার, মাঝে ফাঁকা
   জায়গা বা ডট) সরিয়ে তারপর মেলানো হয়।

   এটা নিখুঁত নয়, নিখুঁত হওয়া সম্ভবও নয় — মানুষ চাইলে বানান ঘুরিয়ে
   এড়াতে পারবে। তাই এর পাশাপাশি অ্যাডমিনের চোখ থাকেই। */

(() => {
"use strict";

// বাংলা হরফে
const BANGLA = [
  "খানকি", "খানকী", "মাগি", "মাগী", "বেশ্যা", "বেশ্যার",
  "চুদ", "চোদ", "চুদি", "চোদা", "চুদা", "চুদির", "চোদার",
  "চুতমারানি", "চুতমারানী", "চুতিয়া", "চুদনা",
  "বাঞ্চোত", "বানচোদ", "বাঞ্চোদ", "শুয়োরের", "শুওরের",
  "হারামজাদা", "হারামজাদি", "হারামির", "হারামী", "হারামি",
  "কুত্তার", "কুত্তা", "কুকুরের বাচ্চা",
  "শালার", "শালা", "শালী",
  "গাধার বাচ্চা", "জারজ", "নষ্টা",
  "লুচ্চা", "বদমাশ", "বদমায়েশ",
  "পোঙ্গা", "ভোদা", "ভোদাই",
  // "ধোন"/"ধন" রাখা হয়নি — "রংধনু", "ধন্যবাদ"-এর ভেতরেই পড়ে যায়
];

// ইংরেজি হরফে বাংলা গালি + ইংরেজি গালি
const ROMAN = [
  "khanki", "khankir", "magi", "beshya",
  "chud", "chod", "chudi", "choda", "chuda", "chudir", "chodar",
  "chutmarani", "chutia", "chutiya", "chudna",
  "banchot", "banchod", "bainchod", "shuorer", "shuwarer",
  "haramjada", "haramjadi", "haramir", "harami",
  "kuttar", "kutta", "kukurer bacha",
  "shalar", "shala", "shali",
  "jaroj", "nosta", "lucha", "badmash", "badmayesh",
  "ponga", "bhoda", "bhodai",   // "dhon" নয় — "Rongdhonu" আটকে যেত
  "fuck", "fucking", "fucker", "shit", "bitch", "bastard",
  "asshole", "motherfucker", "dickhead", "cunt", "whore", "slut",
];

/* মেলানোর আগে লেখাটা সরল করি — ফাঁকি ধরার জন্য।
   "চু দ" / "c.h.u.d" / "chuuud" সবই "chud" হয়ে যায়। */
function normalize(s) {
  return s
    .toLowerCase()
    // অক্ষরের মাঝে ফাঁকা জায়গা, ডট, ড্যাশ, তারা — সরিয়ে দিই
    .replace(/[\s._\-*+#@|/\\]+/g, "")
    // একই অক্ষর পরপর অনেকবার → একবার
    .replace(/(.)\1{1,}/g, "$1");
}

// বড় শব্দ আগে মেলাই, যাতে "চুদির" ধরা পড়ে "চুদ"-এর আগে
const WORDS = [...BANGLA, ...ROMAN]
  .map((w) => ({ raw: w, norm: normalize(w) }))
  .filter((w) => w.norm.length >= 3)
  .sort((a, b) => b.norm.length - a.norm.length);

/** লেখায় গালি আছে কি না */
function has(text) {
  if (!text) return false;
  const n = normalize(text);
  return WORDS.some((w) => n.includes(w.norm));
}

/** কোন কোন গালি আছে (বার্তা দেখানোর জন্য) */
function found(text) {
  if (!text) return [];
  const n = normalize(text);
  return WORDS.filter((w) => n.includes(w.norm)).map((w) => w.raw);
}

/** গালিটুকু তারা দিয়ে ঢেকে দিই, বাকি লেখা অক্ষত থাকে।

    মূল লেখার উপরেই কাজ করি (normalize করা লেখায় নয়), কারণ
    ব্যবহারকারীর বানান-ফাঁকা-যতিচিহ্ন সব ঠিক রাখতে হবে। প্রতিটা
    গালির জন্য একটা নমনীয় প্যাটার্ন বানাই — অক্ষরগুলোর মাঝে ফাঁকা
    জায়গা বা পুনরাবৃত্তি থাকলেও ধরা পড়ে। */
function mask(text) {
  if (!text) return text;
  let out = text;
  for (const w of WORDS) {
    const chars = [...w.norm].map((c) => {
      const esc = c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return `${esc}+`;                       // অক্ষর একাধিকবার থাকলেও চলবে
    }).join("[\\s._\\-*+#@|/\\\\]*");          // মাঝে ফাঁকি-চিহ্ন থাকলেও
    try {
      out = out.replace(new RegExp(chars, "gi"), (m) => "*".repeat(Math.max(3, m.length)));
    } catch { /* কোনো প্যাটার্ন গোলমাল করলে ওটা বাদ */ }
  }
  return out;
}

window.BadWords = { has, found, mask };

})();
