/* ঢাকার বাস ভাড়া — অ্যাপ লজিক
   ডেটা: data/data.json (স্টপেজ + রুট + কিলোমিটার + ম্যাপের লাইন) */

(() => {
"use strict";

let DATA = null;          // পুরো ডেটাসেট
let STOPS = [];           // [{en, bn, lat, lon, keys:[...]}]
let ROUTES = [];          // [{en, bn, s:[stopId], km:[cumulative], g:polyline}]
let STOP_ROUTES = [];     // stopId → [routeIdx]
let map, layerRoute, layerPins;
let lastFind = null;      // স্টপেজ দেখতে গেলে ফলাফলের তালিকা এখানে জমা থাকে
let lastRun = null;       // শেষ খোঁজাটা আবার চালানোর জন্য (ভোট এলে সাজানো বদলায়)

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ───────────────────────── বাংলা সংখ্যা ───────────────────────── */

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
const toBn = (v) => String(v).replace(/[0-9]/g, (d) => BN_DIGITS[+d]);

/* ───────────────────── নাম মেলানোর কারিগরি ─────────────────────
   লক্ষ্য: "যাত্রাবাড়ী", "jatrabari", "jatrabari", "zatrabari" — সবই
   এক জায়গায় নিয়ে আসা। তাই প্রতিটা নামকে একটা "ধ্বনি-চাবি"তে বদলাই। */

// বাংলা অক্ষর → ইংরেজি ধ্বনি
const BN2LAT = {
  "অ":"o","আ":"a","ই":"i","ঈ":"i","উ":"u","ঊ":"u","ঋ":"ri","এ":"e","ঐ":"oi","ও":"o","ঔ":"ou",
  "ক":"k","খ":"kh","গ":"g","ঘ":"gh","ঙ":"ng",
  "চ":"ch","ছ":"ch","জ":"j","ঝ":"jh","ঞ":"n",
  "ট":"t","ঠ":"th","ড":"d","ঢ":"dh","ণ":"n",
  "ত":"t","থ":"th","দ":"d","ধ":"dh","ন":"n",
  "প":"p","ফ":"ph","ব":"b","ভ":"bh","ম":"m",
  "য":"j","র":"r","ল":"l","শ":"sh","ষ":"sh","স":"s","হ":"h",
  "ড়":"r","ঢ়":"rh","য়":"y","ৎ":"t","ং":"ng","ঃ":"h","ঁ":"",
  "া":"a","ি":"i","ী":"i","ু":"u","ূ":"u","ৃ":"ri","ে":"e","ৈ":"oi","ো":"o","ৌ":"ou","্":"",
  "০":"0","১":"1","২":"2","৩":"3","৪":"4","৫":"5","৬":"6","৭":"7","৮":"8","৯":"9",
};

const translit = (s) => [...s].map((c) => (c in BN2LAT ? BN2LAT[c] : c)).join("");

/* ইংরেজি বানানের হেরফের মুছে ফেলি — বাঙালিরা এক শব্দ বহুভাবে লেখে */
function fold(s) {
  let x = s.toLowerCase();
  x = x.replace(/[^a-z0-9ঀ-৿]/g, "");
  if (/[ঀ-৿]/.test(x)) x = translit(x).replace(/[^a-z0-9]/g, "");
  x = x
    .replace(/ph/g, "f").replace(/f/g, "p")     // ফ ↔ ph ↔ f
    .replace(/sh/g, "s").replace(/ch/g, "c")    // শ/স, চ/ছ
    .replace(/kh/g, "k").replace(/gh/g, "g")
    .replace(/th/g, "t").replace(/dh/g, "d")
    .replace(/bh/g, "b").replace(/jh/g, "j")
    .replace(/z/g, "j").replace(/v/g, "b")      // z↔j, v↔bh
    .replace(/x/g, "ks").replace(/q/g, "k").replace(/c/g, "k")
    .replace(/w/g, "o").replace(/y/g, "i")      // Kawran/Karoan, Joy/Joi
    .replace(/h/g, "")                           // Shahbag / Sahbag
    .replace(/([a-z])\1+/g, "$1")               // দুইবার একই অক্ষর
    .replace(/[aeiou]+/g, (m) => m[0]);         // পরপর স্বরধ্বনি
  return x;
}

/* দুই শব্দ কতটা আলাদা — ছাপার ভুল ক্ষমা করার জন্য */
function editDist(a, b, cap) {
  if (Math.abs(a.length - b.length) > cap) return cap + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (cur[j] < best) best = cur[j];
    }
    if (best > cap) return cap + 1;
    prev = cur;
  }
  return prev[b.length];
}

/* একটা স্টপেজের সব খোঁজার-চাবি */
function stopKeys(st) {
  const set = new Set();
  const add = (v) => { if (v) { set.add(v.toLowerCase()); set.add(fold(v)); } };
  add(st.bn);
  add(st.en);
  add(translit(st.bn));
  // "মিরপুর ১০" যেন "mirpur 10" লিখলেও আসে
  add(st.bn.replace(/[০-৯]/g, (d) => BN_DIGITS.indexOf(d)));
  // মানুষের চেনা বিকল্প নাম: উত্তরা → আজমপুর, ঢাবি → শাহবাগ
  (st.alt || []).forEach(add);
  return [...set].filter(Boolean);
}

/* খোঁজার ফলাফল, ভালো মিল আগে।

   আগে সোজা মিল খুঁজি (হুবহু / শুরুতে / ভেতরে)। সেভাবে যথেষ্ট ফল না
   পেলে তবেই বানান-ভুল ক্ষমা করে ঝাপসা মিল দেখি — নইলে "ইউনিভার্সিটি"
   লিখলে "মহাখালী" চলে আসে। */
function searchStops(q, limit = 8) {
  const raw = q.trim().toLowerCase();
  if (!raw) return [];
  const key = fold(raw);
  if (!key) return [];
  const solid = [];

  for (let i = 0; i < STOPS.length; i++) {
    let score = 99;
    for (const k of STOPS[i].keys) {
      if (k === key || k === raw) { score = 0; break; }
      if (k.startsWith(key) || k.startsWith(raw)) score = Math.min(score, 1);
      else if (k.includes(key) || k.includes(raw)) score = Math.min(score, 2);
    }
    if (score < 99) solid.push({ id: i, score, n: STOP_ROUTES[i].length });
  }

  const rank = (a, b) =>
    a.score - b.score || b.n - a.n || STOPS[a.id].bn.length - STOPS[b.id].bn.length;

  if (solid.length >= 3 || key.length < 4) return solid.sort(rank).slice(0, limit);

  // ঝাপসা মিল: শব্দ যত ছোট, ভুল তত কম সহ্য করি
  const cap = Math.min(2, Math.floor(key.length / 4));
  const near = [];
  if (cap >= 1) {
    const already = new Set(solid.map((s) => s.id));
    for (let i = 0; i < STOPS.length; i++) {
      if (already.has(i)) continue;
      let d = cap + 1;
      for (const k of STOPS[i].keys) {
        // দৈর্ঘ্যে বেশি ফারাক হলে মিলবেই না, সময় নষ্ট না করি
        if (Math.abs(k.length - key.length) > cap) continue;
        d = Math.min(d, editDist(key, k, cap));
        if (d === 0) break;
      }
      if (d <= cap) near.push({ id: i, score: 3 + d / 10, n: STOP_ROUTES[i].length });
    }
  }

  const hits = [...solid, ...near].sort(rank).slice(0, limit);
  if (hits.length) return hits;

  // পুরো লেখাটা না মিললে শব্দ ধরে ধরে দেখি — "কমলাপুর রেলস্টেশন" লিখলেও
  // যেন "কমলাপুর" বেরোয়
  const words = raw.split(/\s+/).filter((w) => fold(w).length >= 3);
  if (words.length > 1) {
    const seen = new Set();
    const merged = [];
    for (const w of words.sort((a, b) => b.length - a.length)) {
      for (const h of searchStops(w, limit)) {
        if (seen.has(h.id)) continue;
        seen.add(h.id);
        merged.push(h);
      }
    }
    return merged.slice(0, limit);
  }
  return [];
}

/* ───────────────────────── ভাড়ার হিসাব ───────────────────────── */

/* বিআরটিএ-র চার্ট থেকে হুবহু সরকারি ভাড়া।

   চার্টে প্রতিটা স্টপেজের পাশে শুরু থেকে কত কিলোমিটার তা লেখা থাকে, আর
   ছকের ভাড়া ওখান থেকেই বানানো — চার্টের ১০টা ঘর মিলিয়ে দেখা হয়েছে।
   তাই দুই স্টপেজের কিলোমিটার বিয়োগ করলেই ওই চার্টের ভাড়া পাওয়া যায়।

   একই দুই জায়গা একাধিক রুটে পড়তে পারে, আর রুট ভেদে পথের দৈর্ঘ্য আলাদা।
   তাই সবগুলোই ফেরত দিই — কমেরটা আগে। */
function officialFares(fromId, toId) {
  if (!DATA.charts) return [];
  const out = [];
  for (const c of DATA.charts) {
    let a = null, b = null;
    for (const [sid, , km] of c.s) {
      if (sid === fromId) a = km;
      else if (sid === toId) b = km;
    }
    if (a == null || b == null) continue;
    const km = Math.abs(b - a);
    out.push({
      page: c.p, no: c.no, from: c.f, to: c.t, km,
      fare: Math.max(DATA.meta.bus_min, Math.round(km * DATA.meta.bus_rate)),
      mini: Math.max(DATA.meta.mini_min, Math.round(km * DATA.meta.mini_rate)),
    });
  }
  out.sort((x, y) => x.fare - y.fare || x.km - y.km);
  return out;
}

function fare(km, mini = false) {
  const m = DATA.meta;
  const rate = mini ? m.mini_rate : m.bus_rate;
  const min = mini ? m.mini_min : m.bus_min;
  return Math.max(min, Math.round(km * rate));
}

/* ────────────────────── রুট খোঁজার লজিক ────────────────────── */

/* সবার মত অনুযায়ী স্তর: ২ = চলে, ১ = কেউ বলেনি/দ্বিমত, ০ = চলে না।
   যে বাস চলে না বলে মানুষ জানিয়েছে, সেটা যত কাছেই হোক নিচেই থাকবে। */
function tierOf(r) {
  if (!window.Community) return 1;
  const s = Community.statusOf(r.k).state;
  if (s === "runs") return 2;
  if (s === "no") return 0;
  return 1;
}

/* সরাসরি: এক বাসেই যাওয়া যায় */
function findDirect(from, to) {
  const res = [];
  for (let ri = 0; ri < ROUTES.length; ri++) {
    const r = ROUTES[ri];
    const i = r.s.indexOf(from);
    const j = r.s.indexOf(to);
    if (i < 0 || j < 0 || i === j) continue;
    const km = Math.abs(r.km[j] - r.km[i]);
    if (km <= 0) continue;
    res.push({ kind: "direct", route: ri, i, j, km, stops: Math.abs(j - i) });
  }
  // আগে "চলে কি না", তারপর কাছের পথ
  res.sort((a, b) =>
    tierOf(ROUTES[b.route]) - tierOf(ROUTES[a.route]) || a.km - b.km);
  return res;
}

/* এক জায়গায় বাস বদলে: from → X (বাস ১), X → to (বাস ২) */
function findTransfer(from, to, directRoutes) {
  const toRoutes = new Set(STOP_ROUTES[to]);
  const best = new Map();   // "rA|rB" → সবচেয়ে কম দূরত্বের বিকল্প

  for (const ra of STOP_ROUTES[from]) {
    if (directRoutes.has(ra)) continue;          // সরাসরিই যায়, বদলানোর দরকার নেই
    const A = ROUTES[ra];
    const ai = A.s.indexOf(from);
    for (let k = 0; k < A.s.length; k++) {
      const x = A.s[k];
      if (k === ai || x === to || x === from) continue;
      const km1 = Math.abs(A.km[k] - A.km[ai]);
      if (km1 <= 0) continue;

      for (const rb of STOP_ROUTES[x]) {
        if (rb === ra || !toRoutes.has(rb)) continue;
        const B = ROUTES[rb];
        const bi = B.s.indexOf(x);
        const bj = B.s.indexOf(to);
        if (bi < 0 || bj < 0 || bi === bj) continue;
        const km2 = Math.abs(B.km[bj] - B.km[bi]);
        if (km2 <= 0) continue;

        const key = ra + "|" + rb;
        const cur = best.get(key);
        const total = km1 + km2;
        if (!cur || total < cur.km) {
          best.set(key, {
            kind: "transfer", km: total,
            a: { route: ra, i: ai, j: k, km: km1 },
            b: { route: rb, i: bi, j: bj, km: km2 },
            via: x,
          });
        }
      }
    }
  }

  const out = [...best.values()].sort((p, q) => p.km - q.km);
  // একই বাস দিয়ে শুরু হওয়া বিকল্প বেশি না দেখাই
  const seen = new Map();
  return out.filter((o) => {
    const c = (seen.get(o.a.route) || 0) + 1;
    seen.set(o.a.route, c);
    return c <= 2;
  }).slice(0, 8);
}

/* ────────────────────────── ম্যাপ ────────────────────────── */

/* OSRM-এর এনকোড করা লাইন খুলে ফেলি */
function decodePolyline(str, precision = 5) {
  const factor = Math.pow(10, precision);
  const pts = [];
  let idx = 0, lat = 0, lng = 0;
  while (idx < str.length) {
    let b, shift = 0, result = 0;
    do { b = str.charCodeAt(idx++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);
    shift = 0; result = 0;
    do { b = str.charCodeAt(idx++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);
    pts.push([lat / factor, lng / factor]);
  }
  return pts;
}

/* রুটের প্রতিটা স্টপেজ লাইনের কোন বিন্দুতে পড়ে — সামনে এগোতে এগোতে খুঁজি,
   তাই একই এলাকা দুইবার পড়লেও ভুল হয় না */
function snapStops(line, stopIds) {
  const idx = [];
  let start = 0;
  for (let n = 0; n < stopIds.length; n++) {
    const st = STOPS[stopIds[n]];
    let bi = start, bd = Infinity;
    const last = n === stopIds.length - 1 ? line.length - 1 : line.length - 1;
    for (let i = start; i <= last; i++) {
      const dy = line[i][0] - st.lat, dx = line[i][1] - st.lon;
      const d = dy * dy + dx * dx;
      if (d < bd) { bd = d; bi = i; }
    }
    idx.push(bi);
    start = bi;
  }
  return idx;
}

/* ম্যাপের লাইনগুলো আলাদা ফাইলে, পাতা খোলার পর পেছনে নামে।
   প্রথম লোডে ওগুলো লাগে না, আর ওরাই সবচেয়ে ভারী — তাই আলাদা রাখলে
   পাতা অনেক দ্রুত খোলে (মোবাইল ডেটায় এটা বড় ব্যাপার)। */
let LINES = null;
let linesPromise = null;

function loadLines() {
  if (!linesPromise) {
    linesPromise = fetch("data/lines.json?v=6")
      .then((r) => r.json())
      .then((v) => { LINES = v; return v; })
      .catch((e) => { console.warn("ম্যাপের লাইন আনা গেল না:", e); return null; });
  }
  return linesPromise;
}

const routeLineCache = new Map();
function routeLine(ri) {
  if (!LINES || !LINES[ri]) return null;
  if (!routeLineCache.has(ri)) {
    const line = decodePolyline(LINES[ri]);
    routeLineCache.set(ri, { line, snap: snapStops(line, ROUTES[ri].s) });
  }
  return routeLineCache.get(ri);
}

function initMap() {
  map = L.map("map", { zoomControl: true, attributionControl: true }).setView([23.78, 90.40], 12);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  layerRoute = L.layerGroup().addTo(map);
  layerPins = L.layerGroup().addTo(map);
}

const pin = (cls) => L.divIcon({ className: "", html: `<div class="pin ${cls}"></div>`, iconSize: [15, 15], iconAnchor: [7, 7] });

/* এক বা একাধিক ধাপ ম্যাপে আঁকি */
function drawLegs(legs) {
  // লাইনের ফাইল এখনো নামেনি? নামুক, তারপর আবার চেষ্টা
  if (!LINES) {
    loadLines().then((v) => { if (v) drawLegs(legs); });
    return;
  }
  layerRoute.clearLayers();
  layerPins.clearLayers();
  const colors = ["#0b7a5b", "#d97706"];
  const bounds = [];

  legs.forEach((leg, n) => {
    const rl = routeLine(leg.route);
    if (!rl) return;
    const { line, snap } = rl;
    const a = Math.min(snap[leg.i], snap[leg.j]);
    const b = Math.max(snap[leg.i], snap[leg.j]);
    const seg = line.slice(a, b + 1);
    if (seg.length < 2) return;

    L.polyline(seg, { color: "#fff", weight: 9, opacity: .85 }).addTo(layerRoute);
    L.polyline(seg, { color: colors[n % 2], weight: 5, opacity: .95 }).addTo(layerRoute);
    bounds.push(...seg);

    // মাঝের স্টপেজগুলো ছোট বিন্দু
    const [lo, hi] = leg.i < leg.j ? [leg.i, leg.j] : [leg.j, leg.i];
    for (let k = lo + 1; k < hi; k++) {
      const st = STOPS[ROUTES[leg.route].s[k]];
      L.marker([st.lat, st.lon], { icon: pin("pin-mid"), interactive: true })
        .bindPopup(`<b>${st.bn}</b><br><small>${st.en}</small>`)
        .addTo(layerPins);
    }
  });

  // শুরু ও শেষ
  const first = legs[0], last = legs[legs.length - 1];
  const sA = STOPS[ROUTES[first.route].s[first.i]];
  const sB = STOPS[ROUTES[last.route].s[last.j]];
  L.marker([sA.lat, sA.lon], { icon: pin("pin-from"), zIndexOffset: 900 })
    .bindPopup(`<b>${sA.bn}</b><br><small>যাত্রা শুরু</small>`).addTo(layerPins);
  L.marker([sB.lat, sB.lon], { icon: pin("pin-to"), zIndexOffset: 900 })
    .bindPopup(`<b>${sB.bn}</b><br><small>গন্তব্য</small>`).addTo(layerPins);

  if (legs.length === 2) {
    const v = STOPS[legs[1] && ROUTES[legs[1].route].s[legs[1].i]];
    if (v) L.marker([v.lat, v.lon], { icon: pin("pin-mid"), zIndexOffset: 800 })
      .bindPopup(`<b>${v.bn}</b><br><small>এখানে বাস বদলাতে হবে</small>`).addTo(layerPins);
  }

  if (bounds.length) map.fitBounds(L.latLngBounds(bounds).pad(0.12), { animate: true });
  $("#mapNote").hidden = true;
}

/* পুরো একটা বাসের রুট আঁকি */
function drawWholeRoute(ri) {
  const r = ROUTES[ri];
  drawLegs([{ route: ri, i: 0, j: r.s.length - 1 }]);
}

/* ──────────────────── ফলাফল দেখানো ──────────────────── */

const kmTxt = (km) => toBn(km.toFixed(1)) + " কিমি";

/* ───────────── সবার দেওয়া তথ্য: চলে কি চলে না ───────────── */

const STATE_LOOK = {
  runs:    { cls: "st-yes", icon: "✅", word: "চলে" },
  no:      { cls: "st-no",  icon: "🚫", word: "চলে না" },
  mixed:   { cls: "st-mix", icon: "❔", word: "কেউ বলছে চলে, কেউ বলছে না" },
  unknown: { cls: "st-unk", icon: "❓", word: "কেউ এখনো জানায়নি" },
};

/* বাসের নামের পাশে ছোট ব্যাজ */
function statusPill(r) {
  if (!window.Community) return "";
  const s = Community.statusOf(r.k);
  const look = STATE_LOOK[s.state];
  const who = s.state === "unknown" ? "" :
    ` <span class="st-n">${toBn(s.state === "no" ? s.no : s.runs)} জন</span>`;
  const star = s.ratingCount
    ? ` <span class="st-star">★ ${toBn(s.rating.toFixed(1))}</span>` : "";
  return `<span class="st ${look.cls}">${look.icon} ${look.word}${who}</span>${star}`;
}

/* কার্ডে "আপনি জানেন?" বোতাম */
function voteButton(routeIdx) {
  if (!window.Community || !Community.configured()) return "";
  const r = ROUTES[routeIdx];
  const mine = Community.myVoteOf(r.k);
  const label = mine
    ? `✏️ আপনার মত বদলান`
    : `🗳️ চলে কি না জানান`;
  return `<button class="act act-vote" data-vote="${routeIdx}">${label}</button>`;
}

/* বিআরটিসি-র ৯টা রুট, আলিফের ৪টা — একই নাম। তাই দুই প্রান্ত জুড়ে আলাদা করি */
function routeLabel(r) {
  if (!r.multi) return r.bn;
  return `${r.bn} <span class="route-tag">${STOPS[r.s[0]].bn} ↔ ${STOPS[r.s[r.s.length - 1]].bn}</span>`;
}

function legLine(leg) {
  const r = ROUTES[leg.route];
  const a = STOPS[r.s[leg.i]].bn, b = STOPS[r.s[leg.j]].bn;
  return `<b>${a}</b> → <b>${b}</b>`;
}

/* কার্ডের নিচের সারি: স্টপেজ দেখা আর সরকারি চার্ট দেখা */
function cardActions(routeIdx) {
  const r = ROUTES[routeIdx];
  const chart = r.chart
    ? `<button class="act act-chart" data-chart="${routeIdx}">📋 ভাড়া চার্ট দেখুন</button>`
    : "";
  return `<div class="card-acts">
      <button class="act" data-stops="${routeIdx}">🚏 সব স্টপেজ</button>${chart}${voteButton(routeIdx)}
    </div>`;
}

function cardDirect(o) {
  const r = ROUTES[o.route];
  const f = fare(o.km), fm = fare(o.km, true);
  const path = pathPreview(r, o.i, o.j);
  return `
    <div class="card${tierOf(r) === 0 ? " is-dead" : ""}" data-kind="direct" data-route="${o.route}" data-i="${o.i}" data-j="${o.j}">
      <div class="card-top">
        <div>
          <div class="card-name">${routeLabel(r)}</div>
          <div class="card-en">${r.en}</div>
        </div>
        <div class="card-fare">
          <div class="fare-big">৳${toBn(f)}</div>
          <div class="fare-sub">বাসভাড়া</div>
        </div>
      </div>
      <div class="card-meta">
        ${statusPill(r)}
        <span class="pill pill-km">${kmTxt(o.km)}</span>
        <span class="pill">${toBn(o.stops)} স্টপেজ</span>
        <span class="pill pill-mini">মিনিবাস ৳${toBn(fm)}</span>
        ${r.chart ? `<span class="pill pill-ok">সরকারি চার্ট আছে</span>` : ""}
      </div>
      <div class="card-path">${path}</div>
      ${cardActions(o.route)}
    </div>`;
}

function cardTransfer(o) {
  const A = ROUTES[o.a.route], B = ROUTES[o.b.route];
  const f = fare(o.a.km) + fare(o.b.km);
  const via = STOPS[o.via].bn;
  return `
    <div class="card" data-kind="transfer"
         data-a="${o.a.route}" data-ai="${o.a.i}" data-aj="${o.a.j}"
         data-b="${o.b.route}" data-bi="${o.b.i}" data-bj="${o.b.j}">
      <div class="card-top">
        <div>
          <div class="card-name">${A.bn} <span style="color:var(--ink-3);font-weight:500">+</span> ${B.bn}</div>
          <div class="card-en">${via}-তে বাস বদলাতে হবে</div>
        </div>
        <div class="card-fare">
          <div class="fare-big">৳${toBn(f)}</div>
          <div class="fare-sub">৳${toBn(fare(o.a.km))} + ৳${toBn(fare(o.b.km))}</div>
        </div>
      </div>
      <div class="card-meta">
        <span class="pill pill-km">${kmTxt(o.km)}</span>
        <span class="pill pill-hop">১ বার বদল</span>
      </div>
      <div class="card-path">
        <b>${A.bn}</b>-এ ${kmTxt(o.a.km)} → <b>${via}</b> → <b>${B.bn}</b>-এ ${kmTxt(o.b.km)}
      </div>
      <div class="card-acts">
        <button class="act" data-stops="${o.a.route}">🚏 ${A.bn}-এর স্টপেজ</button>
        <button class="act" data-stops="${o.b.route}">🚏 ${B.bn}-এর স্টপেজ</button>
      </div>
    </div>`;
}

/* কার্ডে মাঝের কয়েকটা স্টপেজের ঝলক */
function pathPreview(r, i, j) {
  const step = i < j ? 1 : -1;
  const mid = [];
  for (let k = i + step; k !== j; k += step) mid.push(STOPS[r.s[k]].bn);
  if (!mid.length) return "সরাসরি পরের স্টপেজ";
  if (mid.length <= 4) return mid.join(" · ");
  return `${mid.slice(0, 2).join(" · ")} … ${mid.slice(-2).join(" · ")} <b>(+${toBn(mid.length - 4)})</b>`;
}

const complainBox = () => `
  <div class="complain">
    <h3>ভাড়া বেশি চাইলে কী করবেন?</h3>
    <p>তালিকার চেয়ে বেশি নিলে সাথে সাথেই অভিযোগ করা যায়। বাসের নম্বর, রুট আর কত নিল — এটুকু বলুন।</p>
    <div class="tel-row">
      <a class="tel" href="tel:16107">📞 ১৬১০৭<small>বিআরটিএ হটলাইন</small></a>
      <a class="tel" href="tel:16121">📞 ১৬১২১<small>ভোক্তা অধিকার, ২৪ ঘণ্টা</small></a>
      <a class="tel" href="tel:999">📞 ৯৯৯<small>জরুরি সেবা</small></a>
    </div>
  </div>`;

/* এই দুই জায়গার জন্য সরকারি চার্টে যা যা লেখা আছে, সবই দেখাই।
   এক জোড়া জায়গা একাধিক রুটে পড়ে, আর রুট ভেদে পথ আলাদা — তাই
   ভাড়াও আলাদা। কোনটা আপনার বাসের, সেটা চার্ট খুলে মিলিয়ে নিন। */
function officialBlock(from, to) {
  const rows = officialFares(from, to);
  if (!rows.length) {
    return `<div class="note note-plain">এই দুই জায়গার ভাড়া বিআরটিএ-র প্রকাশিত
      কোনো চার্টে সরাসরি পাওয়া যায়নি, তাই নিচের ভাড়া কিলোমিটার-হারে হিসাব করা।</div>`;
  }
  const same = rows.every((r) => r.fare === rows[0].fare);
  const range = same ? `৳${toBn(rows[0].fare)}`
    : `৳${toBn(rows[0].fare)} – ৳${toBn(rows[rows.length - 1].fare)}`;

  return `<div class="official">
    <div class="off-head">
      <div>
        <span class="off-tag">সরকারি ভাড়া</span>
        <h3>${range}</h3>
      </div>
      <p>বিআরটিএ-র প্রকাশিত ভাড়ার চার্ট থেকে${
        same ? "" : ` — ${toBn(rows.length)}টি রুটে পথের দৈর্ঘ্য আলাদা, তাই ভাড়াও আলাদা`}</p>
    </div>
    <div class="off-list">
      ${rows.map((r) => `
        <button class="off-row" data-page="${r.page}" data-no="${esc(r.no)}"
                data-f="${esc(r.from)}" data-t="${esc(r.to)}">
          <span class="off-fare">৳${toBn(r.fare)}</span>
          <span class="off-rt">
            <b>${esc(r.from)} ↔ ${esc(r.to)}</b>
            <small>রুট ${esc(r.no)} · ${kmTxt(r.km)} · মিনিবাসে ৳${toBn(r.mini)}</small>
          </span>
          <span class="off-go">চার্ট&nbsp;›</span>
        </button>`).join("")}
    </div>
  </div>`;
}

function renderFind(from, to) {
  const box = $("#results");
  const direct = findDirect(from, to);
  const directSet = new Set(direct.map((d) => d.route));
  const transfer = direct.length >= 3 ? [] : findTransfer(from, to, directSet);

  const A = STOPS[from].bn, B = STOPS[to].bn;
  let html = `<div class="res-head"><h2>${A} → ${B}</h2>
    <span class="count">${direct.length ? toBn(direct.length) + "টি সরাসরি বাস" : "সরাসরি বাস নেই"}</span></div>`;

  // সরকারি চার্টে এই দুই জায়গার ভাড়া লেখা আছে কিনা — থাকলে সেটাই আগে
  html += officialBlock(from, to);

  if (direct.length) {
    const km = direct[0].km;
    html += `<div class="note">সবচেয়ে কম পথ <b>${kmTxt(km)}</b> — বিআরটিএ-র হারে হিসাব করলে
      ভাড়া <b>৳${toBn(fare(km))}</b> (মিনিবাসে ৳${toBn(fare(km, true))})।</div>`;
    html += direct.slice(0, 25).map(cardDirect).join("");
  } else if (!transfer.length) {
    html += `<div class="empty"><p class="empty-big">এই দুই জায়গার মধ্যে কোনো বাস পাওয়া গেল না</p>
      <p>ডেটাসেটে ${A} বা ${B}-এর রুট কম থাকতে পারে। কাছাকাছি বড় কোনো মোড় দিয়ে চেষ্টা করুন।</p></div>`;
  }

  if (transfer.length) {
    html += `<div class="section-title">এক বার বাস বদলে যাওয়া যায়</div>`;
    html += transfer.map(cardTransfer).join("");
  }

  html += complainBox();
  box.innerHTML = html;
  box.scrollTop = 0;

  // প্রথম ফলাফলটা ম্যাপে দেখিয়ে দিই
  const firstCard = $(".card", box);
  if (firstCard) selectCard(firstCard);
}

function selectCard(el) {
  $$(".card.is-on").forEach((c) => c.classList.remove("is-on"));
  el.classList.add("is-on");
  if (el.dataset.kind === "transfer") {
    drawLegs([
      { route: +el.dataset.a, i: +el.dataset.ai, j: +el.dataset.aj },
      { route: +el.dataset.b, i: +el.dataset.bi, j: +el.dataset.bj },
    ]);
  } else if (el.dataset.kind === "direct") {
    drawLegs([{ route: +el.dataset.route, i: +el.dataset.i, j: +el.dataset.j }]);
  } else if (el.dataset.kind === "route") {
    drawWholeRoute(+el.dataset.route);
  }
}

/* ──────────────────── সাজেশন বাক্স ──────────────────── */

function attachSuggest(field, onPick) {
  const input = $("input", field);
  const list = $(".suggest", field);
  const clear = $(".clear", field);
  let items = [], active = -1, picked = null;

  const close = () => { list.hidden = true; list.innerHTML = ""; active = -1; };

  const paint = () => {
    if (!items.length) { close(); return; }
    list.innerHTML = items.map((m, n) => {
      const st = STOPS[m.id];
      return `<li data-id="${m.id}" class="${n === active ? "is-active" : ""}">
        <span class="s-bn">${st.bn}</span>
        <span class="s-en">${st.en}</span>
        <span class="s-n">${toBn(STOP_ROUTES[m.id].length)} বাস</span>
      </li>`;
    }).join("");
    list.hidden = false;
  };

  const choose = (id) => {
    picked = id;
    input.value = STOPS[id].bn;
    clear.hidden = false;
    close();
    onPick(id);
  };

  input.addEventListener("input", () => {
    picked = null;
    clear.hidden = !input.value;
    items = searchStops(input.value);
    active = items.length ? 0 : -1;
    paint();
  });

  input.addEventListener("keydown", (e) => {
    if (list.hidden || !items.length) {
      if (e.key === "Enter" && !picked && input.value.trim()) {
        const hit = searchStops(input.value, 1)[0];
        if (hit) choose(hit.id);
      }
      return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; paint(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; paint(); }
    else if (e.key === "Enter") { e.preventDefault(); if (active >= 0) choose(items[active].id); }
    else if (e.key === "Escape") close();
  });

  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li");
    if (li) { e.preventDefault(); choose(+li.dataset.id); }
  });

  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("focus", () => { if (items.length && !picked) paint(); });

  clear.addEventListener("click", () => {
    input.value = ""; picked = null; items = []; clear.hidden = true; close();
    input.focus(); onPick(null);
  });

  return {
    get value() { return picked; },
    set(id) {
      picked = id;
      input.value = id == null ? "" : STOPS[id].bn;
      clear.hidden = id == null;
    },
  };
}

/* ──────────────────── ট্যাব ২: সব বাস ──────────────────── */

function renderBusList(q = "") {
  const key = fold(q);
  const raw = q.trim().toLowerCase();
  let list = ROUTES.map((r, i) => ({ r, i }));
  if (raw) {
    list = list.filter(({ r }) => {
      const keys = [r.bn.toLowerCase(), r.en.toLowerCase(), fold(r.bn), fold(r.en)];
      return keys.some((k) => k.includes(raw) || (key && k.includes(key)));
    });
  }
  // চলে বলে যাদের কথা জানা, তারা আগে; চলে না বলে জানা যারা, সবার শেষে
  list.sort((a, b) =>
    tierOf(b.r) - tierOf(a.r) || a.r.bn.localeCompare(b.r.bn, "bn"));

  const box = $("#busList");
  const dead = list.filter(({ r }) => tierOf(r) === 0).length;
  box.innerHTML =
    `<div class="res-head"><h2>সব বাস</h2><span class="count">${toBn(list.length)}টি` +
    (dead ? ` · ${toBn(dead)}টি চলে না` : "") + `</span></div>` +
    (list.length
      ? list.map(({ r, i }) => {
          const total = r.km[r.km.length - 1];
          return `<div class="card${tierOf(r) === 0 ? " is-dead" : ""}" data-kind="route" data-route="${i}">
            <div class="card-top">
              <div>
                <div class="card-name">${routeLabel(r)}</div>
                <div class="card-en">${r.en}</div>
              </div>
              <div class="card-fare">
                <div class="fare-big">৳${toBn(fare(total))}</div>
                <div class="fare-sub">পুরো পথ</div>
              </div>
            </div>
            <div class="card-meta">
              ${statusPill(r)}
              <span class="pill pill-km">${kmTxt(total)}</span>
              <span class="pill">${toBn(r.s.length)} স্টপেজ</span>
              ${r.chart ? `<span class="pill pill-ok">সরকারি চার্ট আছে</span>` : ""}
            </div>
            <div class="card-path"><b>${STOPS[r.s[0]].bn}</b> → <b>${STOPS[r.s[r.s.length - 1]].bn}</b></div>
            ${cardActions(i)}
          </div>`;
        }).join("")
      : `<div class="empty"><p class="empty-big">এই নামে কোনো বাস নেই</p></div>`);
}

/* একটা বাসের পুরো স্টপেজ তালিকা।
   hi = [শুরু, শেষ] — খোঁজা যাত্রার অংশটুকু আলাদা করে দেখানোর জন্য */
function showRouteDetail(ri, container, hi) {
  const r = ROUTES[ri];
  const total = r.km[r.km.length - 1];
  const [lo, up] = hi ? [Math.min(hi[0], hi[1]), Math.max(hi[0], hi[1])] : [-1, -1];
  const base = hi ? hi[0] : 0;   // দূরত্ব কোন স্টপেজ থেকে গোনা হবে

  const trip = hi
    ? `<div class="note">আপনার যাত্রা <b>${STOPS[r.s[hi[0]]].bn}</b> থেকে
        <b>${STOPS[r.s[hi[1]]].bn}</b> — ${kmTxt(Math.abs(r.km[hi[1]] - r.km[hi[0]]))},
        ভাড়া <b>৳${toBn(fare(Math.abs(r.km[hi[1]] - r.km[hi[0]])))}</b>।
        নিচে সবুজ দাগ দেওয়া অংশটুকুই আপনার পথ।</div>`
    : `<div class="note">পুরো পথ <b>${kmTxt(total)}</b>, ভাড়া <b>৳${toBn(fare(total))}</b>
        (মিনিবাসে ৳${toBn(fare(total, true))})। নিচের কিলোমিটার প্রথম স্টপেজ থেকে গোনা।</div>`;

  container.innerHTML = `
    <div class="res-head">
      <h2>${routeLabel(r)}</h2>
      <span class="count">${r.en}</span>
      <button class="chip" id="backBtn" style="margin-left:auto">← ফিরে যান</button>
    </div>
    ${trip}
    ${r.chart ? `<button class="act act-chart wide" data-chart="${ri}">📋 এই রুটের সরকারি ভাড়া চার্ট দেখুন</button>` : ""}
    <ul class="stoplist">
      ${r.s.map((id, k) => {
        const inTrip = lo >= 0 && k >= lo && k <= up;
        const edge = k === lo || k === up || (lo < 0 && (k === 0 || k === r.s.length - 1));
        // দূরত্ব যেখান থেকে গোনা: যাত্রা থাকলে যাত্রার শুরু, নইলে রুটের শুরু
        const d = Math.abs(r.km[k] - r.km[base]);
        return `<li class="${edge ? "on" : ""}${inTrip ? " trip" : ""}">
          <span class="km">${toBn(d.toFixed(1))} কিমি · ৳${toBn(fare(d))}</span>
          ${STOPS[id].bn} <span class="st-en">${STOPS[id].en}</span>
        </li>`;
      }).join("")}
    </ul>
    <p class="tiny-note">ভাড়া ও দূরত্ব <b>${STOPS[r.s[base]].bn}</b> থেকে গোনা।
      অন্য দুই স্টপেজের ভাড়া জানতে দুইটার কিলোমিটার বিয়োগ করে
      ৳${toBn(DATA.meta.bus_rate.toFixed(2))} দিয়ে গুণ করুন (সর্বনিম্ন ৳${toBn(DATA.meta.bus_min)})।</p>
    ${complainBox()}`;

  if (hi) drawLegs([{ route: ri, i: hi[0], j: hi[1] }]);
  else drawWholeRoute(ri);
  container.scrollTop = 0;
}

/* বিআরটিএ-র অফিসিয়াল চার্ট দেখানো */
function showChart(page, title, sub) {
  const src = `charts/${page}.jpg`;
  $("#chartTitle").textContent = title;
  $("#chartSub").textContent = sub;
  $("#chartImg").src = src;
  $("#chartOpen").href = src;
  $("#chartSheet").hidden = false;
  document.body.classList.add("no-scroll");
}

function openChart(ri) {
  const r = ROUTES[ri];
  if (!r.chart) return;
  const km = r.chart.km ? ` · মোট ${toBn(r.chart.km)} কিমি` : "";
  showChart(r.chart.p, `${r.chart.f} ↔ ${r.chart.t}`,
    `বিআরটিএ রুট ${r.chart.no}${km} — ${r.bn} এই পথ দিয়েই যায়। ` +
    `চার্টে যেকোনো দুই স্টপেজ মেলালেই সরকারি ভাড়া পাবেন।`);
}

function closeChart() {
  $("#chartSheet").hidden = true;
  $("#chartImg").removeAttribute("src");
  document.body.classList.remove("no-scroll");
}

/* ──────────── বাস নিয়ে মত দেওয়া ও অন্যদের মত পড়া ──────────── */

let voteFor = null;      // এখন কোন বাসের জানালা খোলা
let voteDraft = { vote: null, rating: 0 };

const timeAgo = (d) => {
  if (!d) return "";
  const s = (Date.now() - d) / 1000;
  if (s < 90) return "এইমাত্র";
  if (s < 3600) return `${toBn(Math.round(s / 60))} মিনিট আগে`;
  if (s < 86400) return `${toBn(Math.round(s / 3600))} ঘণ্টা আগে`;
  if (s < 2592000) return `${toBn(Math.round(s / 86400))} দিন আগে`;
  return `${toBn(Math.round(s / 2592000))} মাস আগে`;
};

const esc = (s) => String(s || "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const STAR_WORDS = ["", "খুব খারাপ", "খারাপ", "মোটামুটি", "ভালো", "খুব ভালো"];

function paintVoteForm() {
  $$("#voteBtns .vbtn").forEach((b) =>
    b.classList.toggle("is-on", b.dataset.v === voteDraft.vote));
  $$("#starRow button").forEach((b) =>
    b.classList.toggle("is-on", +b.dataset.s <= voteDraft.rating));
  $("#starLabel").textContent = voteDraft.rating
    ? STAR_WORDS[voteDraft.rating] : "রেটিং দিন";
}

async function openVote(ri) {
  const r = ROUTES[ri];
  voteFor = r;
  const mine = Community.myVoteOf(r.k) || {};
  voteDraft = { vote: mine.v || null, rating: mine.rating || 0 };

  $("#voteTitle").textContent = r.bn;
  const s = Community.statusOf(r.k);
  $("#voteSub").textContent = s.total
    ? `এ পর্যন্ত ${toBn(s.total)} জন জানিয়েছেন — ${toBn(s.runs)} জন বলেছেন চলে, ${toBn(s.no)} জন বলেছেন চলে না`
    : "এই বাস নিয়ে এখনো কেউ কিছু জানাননি — আপনিই প্রথম";
  $("#voteText").value = mine.text || "";
  $("#voteName").value = mine.name || "";
  $("#textCount").textContent = toBn((mine.text || "").length);
  $("#voteMsg").textContent = "";
  $("#voteMsg").className = "vote-msg";
  paintVoteForm();

  $("#reviewList").innerHTML = `<p class="rv-loading">অন্যদের মত আসছে…</p>`;
  $("#voteSheet").hidden = false;
  document.body.classList.add("no-scroll");

  try {
    const rows = await Community.reviewsOf(r.k);
    renderReviews(rows);
  } catch (e) {
    $("#reviewList").innerHTML =
      `<p class="rv-loading">অন্যদের মত আনা গেল না। ${esc(e.message)}</p>`;
  }
}

function renderReviews(rows) {
  const withText = rows.filter((x) => (x.text || "").trim());
  if (!withText.length) {
    $("#reviewList").innerHTML =
      `<div class="rv-head">অন্যরা কী বলছেন</div>
       <p class="rv-loading">এখনো কেউ কিছু লেখেননি।</p>`;
    return;
  }
  $("#reviewList").innerHTML =
    `<div class="rv-head">অন্যরা কী বলছেন <span>${toBn(withText.length)}টি</span></div>` +
    withText.map((x) => {
      const when = x.at && x.at.toMillis ? timeAgo(x.at.toMillis()) : "";
      const stars = x.rating ? "★".repeat(x.rating) + "☆".repeat(5 - x.rating) : "";
      const vote = x.v === "runs" ? `<span class="rv-v yes">চলে</span>`
                 : x.v === "no" ? `<span class="rv-v no">চলে না</span>` : "";
      return `<div class="rv${x.mine ? " mine" : ""}">
        <div class="rv-top">
          <b>${esc(x.name) || "একজন যাত্রী"}</b>${x.mine ? ' <span class="rv-me">আপনি</span>' : ""}
          ${vote}
          <span class="rv-when">${when}</span>
        </div>
        ${stars ? `<div class="rv-stars">${stars}</div>` : ""}
        <p>${esc(x.text)}</p>
      </div>`;
    }).join("");
}

function closeVote() {
  $("#voteSheet").hidden = true;
  voteFor = null;
  document.body.classList.remove("no-scroll");
}

async function saveVote() {
  if (!voteFor) return;
  const btn = $("#voteSubmit");
  const msg = $("#voteMsg");
  const text = $("#voteText").value.trim();

  if (!voteDraft.vote && !voteDraft.rating && !text) {
    msg.textContent = "অন্তত একটা কিছু জানান — চলে কি না, রেটিং, বা দুই লাইন লিখুন।";
    msg.className = "vote-msg bad";
    return;
  }

  btn.disabled = true;
  btn.textContent = "জমা হচ্ছে…";
  try {
    await Community.submit(voteFor.k, {
      vote: voteDraft.vote,
      rating: voteDraft.rating,
      text,
      name: $("#voteName").value.trim(),
    });
    msg.textContent = "ধন্যবাদ! আপনার মত সবাই দেখতে পাবে।";
    msg.className = "vote-msg good";
    renderReviews(await Community.reviewsOf(voteFor.k));
  } catch (e) {
    msg.textContent = "জমা দেওয়া গেল না — ইন্টারনেট দেখে আবার চেষ্টা করুন। " + e.message;
    msg.className = "vote-msg bad";
  } finally {
    btn.disabled = false;
    btn.textContent = "জমা দিন";
  }
}

/* ──────────────── ট্যাব ৩: সবাই কী বলছে ──────────────── */

async function renderReports() {
  const box = $("#reportList");
  if (!Community.configured()) {
    box.innerHTML = `<div class="empty">
      <p class="empty-big">এই অংশটা এখনো চালু হয়নি</p>
      <p>সবার মত জমা রাখতে একটা ফ্রি Firebase প্রজেক্ট লাগে।
         <code>site/firebase-config.js</code> ফাইলে সেটিংস বসালেই কাজ করবে।</p></div>`;
    return;
  }
  box.innerHTML = `<div class="res-head"><h2>সবাই কী বলছেন</h2></div>
    <p class="rv-loading">আনা হচ্ছে…</p>`;

  const byKey = {};
  ROUTES.forEach((r, i) => { byKey[r.k] = { r, i }; });

  try {
    const rows = await Community.recentAll(40);
    if (!rows.length) {
      box.innerHTML = `<div class="res-head"><h2>সবাই কী বলছেন</h2></div>
        <div class="empty"><p class="empty-big">এখনো কেউ কিছু জানাননি</p>
        <p>যেকোনো বাসের কার্ডে <b>চলে কি না জানান</b> চেপে আপনিই প্রথম হতে পারেন।</p></div>`;
      return;
    }
    box.innerHTML =
      `<div class="res-head"><h2>সবাই কী বলছেন</h2>
         <span class="count">সাম্প্রতিক ${toBn(rows.length)}টি</span></div>` +
      `<div class="note">এগুলো যাত্রীদের নিজের কথা — যাচাই করা হয়নি।</div>` +
      rows.map((x) => {
        const hit = byKey[x.bus];
        const when = x.at && x.at.toMillis ? timeAgo(x.at.toMillis()) : "";
        const vote = x.v === "runs" ? `<span class="rv-v yes">চলে</span>`
                   : x.v === "no" ? `<span class="rv-v no">চলে না</span>`
                   : x.v === "unsure" ? `<span class="rv-v idk">জানি না</span>` : "";
        const stars = x.rating ? `<span class="rv-stars">${"★".repeat(x.rating)}</span>` : "";
        return `<div class="card rv-card"${hit ? ` data-kind="route" data-route="${hit.i}"` : ""}>
          <div class="rv-top">
            <b>${hit ? esc(hit.r.bn) : esc(x.bus)}</b> ${vote} ${stars}
            <span class="rv-when">${when}</span>
          </div>
          ${x.text ? `<p class="rv-text">${esc(x.text)}</p>` : ""}
          <div class="rv-by">— ${esc(x.name) || "একজন যাত্রী"}${x.mine ? " (আপনি)" : ""}</div>
        </div>`;
      }).join("");
  } catch (e) {
    box.innerHTML = `<div class="res-head"><h2>সবাই কী বলছেন</h2></div>
      <div class="empty"><p class="empty-big">আনা গেল না</p>
      <p>${esc(e.message)}</p></div>`;
  }
}

/* ──────────────────────── চালু করা ──────────────────────── */

async function boot() {
  const res = await fetch("data/data.json?v=6");
  DATA = await res.json();
  STOPS = DATA.stops;
  ROUTES = DATA.routes;

  STOP_ROUTES = STOPS.map(() => []);
  ROUTES.forEach((r, i) => new Set(r.s).forEach((s) => STOP_ROUTES[s].push(i)));
  STOPS.forEach((st) => { st.keys = stopKeys(st); });

  const m = DATA.meta;
  $("#rateChip").textContent = `৳${toBn(m.bus_rate.toFixed(2))}/কিমি · সর্বনিম্ন ৳${toBn(m.bus_min)}`;
  $("#footRate").textContent =
    `বাস ৳${toBn(m.bus_rate.toFixed(2))}/কিমি (সর্বনিম্ন ৳${toBn(m.bus_min)}), ` +
    `মিনিবাস ৳${toBn(m.mini_rate.toFixed(2))}/কিমি (সর্বনিম্ন ৳${toBn(m.mini_min)}), কার্যকর ${m.effective}`;

  initMap();
  // পাতা দেখানো শুরু হয়ে গেছে; ম্যাপের লাইনগুলো এখন পেছনে নামুক
  loadLines();

  // ট্যাব ১
  const fromF = attachSuggest($('.field[data-role="from"]'), () => {});
  const toF = attachSuggest($('.field[data-role="to"]'), () => {});
  const run = () => {
    if (fromF.value == null || toF.value == null) return;
    if (fromF.value === toF.value) {
      $("#results").innerHTML = `<div class="empty"><p class="empty-big">দুই জায়গা একই</p>
        <p>আলাদা গন্তব্য বাছুন।</p></div>`;
      return;
    }
    renderFind(fromF.value, toF.value);
  };
  // ভোটের খবর এলে সাজানো বদলায়, তাই ফলাফল আবার আঁকা দরকার।
  // তবে কেউ যদি স্টপেজের তালিকা দেখছে, তার পড়া নষ্ট করি না।
  lastRun = () => {
    if (fromF.value == null || toF.value == null) return;
    if ($(".stoplist", $("#results"))) return;
    renderFind(fromF.value, toF.value);
  };
  $("#goBtn").addEventListener("click", run);
  $("#swapBtn").addEventListener("click", () => {
    const a = fromF.value, b = toF.value;
    fromF.set(b); toF.set(a);
    if (a != null && b != null) run();
  });
  // দুইটা বাছা হয়ে গেলে নিজেই খুঁজে ফেলুক
  ["fromInput", "toInput"].forEach((idn) =>
    $("#" + idn).addEventListener("change", () => setTimeout(run, 40)));
  $("#results").addEventListener("click", (e) => {
    // সরকারি ভাড়ার সারিতে চাপ দিলে ওই রুটের চার্ট
    const off = e.target.closest(".off-row");
    if (off) {
      showChart(off.dataset.page, `${off.dataset.f} ↔ ${off.dataset.t}`,
        `বিআরটিএ রুট ${off.dataset.no} — এই চার্টে আপনার দুই স্টপেজ খুঁজে ` +
        `যেখানে সারি ও কলাম মেলে, সেই ঘরের সংখ্যাই সরকারি ভাড়া।`);
      return;
    }
    // নিচের ছোট বোতামগুলো আগে দেখি, নইলে কার্ড বাছাই হয়ে যাবে
    const act = e.target.closest(".act");
    if (act) {
      e.stopPropagation();
      if (act.dataset.chart != null) { openChart(+act.dataset.chart); return; }
      if (act.dataset.vote != null) { openVote(+act.dataset.vote); return; }
      if (act.dataset.stops != null) {
        const card = act.closest(".card");
        // সরাসরি বাস হলে যাত্রার অংশটুকু দাগ দিয়ে দেখাই
        const hi = card && card.dataset.kind === "direct"
          ? [+card.dataset.i, +card.dataset.j] : null;
        lastFind = $("#results").innerHTML;
        showRouteDetail(+act.dataset.stops, $("#results"), hi);
      }
      return;
    }
    if (e.target.id === "backBtn" && lastFind != null) {
      $("#results").innerHTML = lastFind;
      const first = $(".card", $("#results"));
      if (first) selectCard(first);
      return;
    }
    const card = e.target.closest(".card");
    if (card && card.dataset.kind) selectCard(card);
  });
  $('.field[data-role="from"] .suggest').addEventListener("mouseup", () => setTimeout(run, 60));
  $('.field[data-role="to"] .suggest').addEventListener("mouseup", () => setTimeout(run, 60));

  // জনপ্রিয় জোড়া
  const quick = [["Gabtoli", "Jatrabari"], ["Mirpur 10", "Motijheel"], ["Uttar Badda", "Farmgate"],
                 ["Abdullahpur", "Sadarghat"], ["Mohammadpur", "Kuril Bishwa Road"]];
  $("#quickChips").innerHTML = quick.map(([a, b]) => {
    const ia = STOPS.findIndex((s) => s.en === a), ib = STOPS.findIndex((s) => s.en === b);
    if (ia < 0 || ib < 0) return "";
    return `<button class="chip" data-a="${ia}" data-b="${ib}">${STOPS[ia].bn} → ${STOPS[ib].bn}</button>`;
  }).join("");
  $("#quickChips").addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    fromF.set(+b.dataset.a); toF.set(+b.dataset.b); run();
  });

  // ট্যাব ২ — সব বাস ও তাদের স্টপেজ
  renderBusList();
  $("#busSearch").addEventListener("input", (e) => renderBusList(e.target.value));
  $("#busList").addEventListener("click", (e) => {
    const act = e.target.closest(".act");
    if (act) {
      e.stopPropagation();
      if (act.dataset.chart != null) openChart(+act.dataset.chart);
      else if (act.dataset.vote != null) openVote(+act.dataset.vote);
      else if (act.dataset.stops != null) showRouteDetail(+act.dataset.stops, $("#busList"));
      return;
    }
    if (e.target.id === "backBtn") { renderBusList($("#busSearch").value); return; }
    const card = e.target.closest(".card");
    if (card && card.dataset.route != null) showRouteDetail(+card.dataset.route, $("#busList"));
  });

  // চার্টের জানালা বন্ধ করা
  $("#chartClose").addEventListener("click", closeChart);
  $("#chartSheet").addEventListener("click", (e) => {
    if (e.target.id === "chartSheet") closeChart();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#voteSheet").hidden) closeVote();
    else if (!$("#chartSheet").hidden) closeChart();
  });

  // ── সবার মত: ভোটের জানালা ──
  $("#voteClose").addEventListener("click", closeVote);
  $("#voteSheet").addEventListener("click", (e) => {
    if (e.target.id === "voteSheet") closeVote();
  });
  $("#voteBtns").addEventListener("click", (e) => {
    const b = e.target.closest(".vbtn");
    if (!b) return;
    // একই বোতামে আবার চাপলে ভোট তুলে নেওয়া
    voteDraft.vote = voteDraft.vote === b.dataset.v ? null : b.dataset.v;
    paintVoteForm();
  });
  $("#starRow").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    voteDraft.rating = voteDraft.rating === +b.dataset.s ? 0 : +b.dataset.s;
    paintVoteForm();
  });
  $("#voteText").addEventListener("input", (e) =>
    $("#textCount").textContent = toBn(e.target.value.length));
  $("#voteSubmit").addEventListener("click", saveVote);

  $("#reportList").addEventListener("click", (e) => {
    const card = e.target.closest(".card[data-route]");
    if (card) { switchTab("buses"); showRouteDetail(+card.dataset.route, $("#busList")); }
  });

  // ওয়ার্নিং বন্ধ করলে মনে রাখি
  if (localStorage.getItem("dbf.staleHidden") === "1") $("#staleNote").hidden = true;
  $("#staleClose").addEventListener("click", () => {
    $("#staleNote").hidden = true;
    try { localStorage.setItem("dbf.staleHidden", "1"); } catch {}
  });

  // সবার মত এলে/বদলালে তালিকা নতুন করে আঁকি
  Community.onChange(() => {
    if ($("#pane-buses").classList.contains("is-on") && !$(".stoplist", $("#busList")))
      renderBusList($("#busSearch").value);
    if (lastRun) lastRun();
  });
  Community.loadMine();
  Community.loadSummary();

  // ট্যাব বদল
  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    switchTab(t.dataset.tab);
    if (t.dataset.tab === "reports") renderReports();
  }));

  // ফোনে ম্যাপ ছোট থাকে; বোতামে চাপ দিলে পুরো পর্দা জুড়ে
  $("#mapToggle").addEventListener("click", () => {
    const big = document.body.classList.toggle("map-big");
    $("#mapToggleIcon").textContent = big ? "⤡" : "⤢";
    $("#mapToggleText").textContent = big ? "ছোট করুন" : "ম্যাপ বড় করুন";
    // Leaflet-কে নতুন মাপ জানাতে হয়, নইলে টাইল অর্ধেক ফাঁকা থাকে
    setTimeout(() => map.invalidateSize({ animate: false }), 300);
  });

  $("#loading").hidden = true;
}

function switchTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("is-on", t.dataset.tab === name));
  $$(".tabpane").forEach((p) => p.classList.toggle("is-on", p.id === "pane-" + name));
}

boot().catch((err) => {
  console.error(err);
  $("#loading").innerHTML = "<p>ডেটা আনা গেল না। পেজটা রিফ্রেশ করুন।</p>";
});

})();
