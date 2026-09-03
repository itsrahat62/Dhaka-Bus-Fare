/* সবার দেওয়া তথ্য — কোন বাস এখনো চলে, আর বাসের সেবা কেমন।

   কেন দরকার: ঢাকায় বাস কোম্পানি বন্ধ হয়, রুট বদলায়, নতুন বাস নামে।
   কোনো সরকারি তালিকা এত দ্রুত হালনাগাদ হয় না। যারা রোজ চড়েন তারাই
   সবচেয়ে ভালো জানেন — তাই তাঁদেরই জিজ্ঞেস করি।

   Firestore-এ কী কী জমা থাকে
   ───────────────────────────
   summary/all
       { b: { <রুটের চাবি>: { r, n, u, rs, rc } } }
       r  = কতজন বলেছে চলে       n  = কতজন বলেছে চলে না
       u  = কতজন বলেছে জানি না    rs = রেটিংয়ের যোগফল
       rc = কতজন রেটিং দিয়েছে
       পুরো তালিকা এক ডকুমেন্টে, তাই পেজ খুললে মাত্র একটা read লাগে —
       ফ্রি কোটা বাঁচে।

   buses/<রুটের চাবি>/reviews/<uid>
       একজন ব্যবহারকারীর একটা বাস নিয়ে মত — ভোট, রেটিং, লেখা, নাম।
       ডকুমেন্টের আইডি uid, তাই এক ফোন থেকে একবারই ভোট যায় (মত
       বদলালে সেটাই আপডেট হয়)।

   লগইন লাগে না — Firebase-এর anonymous auth প্রতিটা ব্রাউজারকে একটা
   গোপন আইডি দেয়। */

(() => {
"use strict";

const CDN = "https://www.gstatic.com/firebasejs/10.12.2";
const SUMMARY_TTL = 3 * 60 * 1000;   // এতক্ষণ পুরোনো হিসাব চলবে

let fb = null;          // {app, db, auth, uid, api}
let summary = {};       // রুটের চাবি → {r, n, u, rs, rc}
let myVotes = {};       // রুটের চাবি → {v, rating}  (এই ফোনের নিজের মত)
const listeners = [];

const LS_MINE = "dbf.myVotes.v1";
const LS_SUM = "dbf.summary.v1";

/* ───────────────────────── চালু করা ───────────────────────── */

function configured() {
  const c = window.FIREBASE_CONFIG;
  return !!(c && c.apiKey && c.projectId);
}

async function connect() {
  if (fb) return fb;
  if (!configured()) return null;

  const [{ initializeApp }, auth, store] = await Promise.all([
    import(`${CDN}/firebase-app.js`),
    import(`${CDN}/firebase-auth.js`),
    import(`${CDN}/firebase-firestore.js`),
  ]);

  const app = initializeApp(window.FIREBASE_CONFIG);
  const db = store.getFirestore(app);
  const a = auth.getAuth(app);

  // লোকাল এমুলেটরে যাচাই করার সময় (?emulator=1 দিলে) — আসল সাইটে নয়
  if (window.FIREBASE_EMULATOR) {
    store.connectFirestoreEmulator(db, "127.0.0.1", 8080);
    auth.connectAuthEmulator(a, "http://127.0.0.1:9099", { disableWarnings: true });
  }

  // লগইন ছাড়াই একটা স্থায়ী পরিচয় — এক ফোন, এক ভোট
  const cred = await auth.signInAnonymously(a);

  fb = { app, db, uid: cred.user.uid, store };
  return fb;
}

/* ─────────────────── হিসাব আনা ও জমা রাখা ─────────────────── */

function readCache(key, ttl) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const { at, data } = JSON.parse(raw);
    if (ttl && Date.now() - at > ttl) return null;
    return data;
  } catch { return null; }
}

function writeCache(key, data) {
  try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), data })); }
  catch { /* জায়গা না থাকলে কিছু না */ }
}

async function loadSummary() {
  // আগে ক্যাশ দেখাই যাতে পাতা সাথে সাথে ভরে, পরে নতুনটা আনি
  const cached = readCache(LS_SUM, SUMMARY_TTL);
  if (cached) {
    summary = cached;
    fire();
  }
  const c = await connect();
  if (!c) return;

  try {
    const { doc, getDoc } = c.store;
    const snap = await getDoc(doc(c.db, "summary", "all"));
    summary = (snap.exists() ? snap.data().b : null) || {};
    writeCache(LS_SUM, summary);
  } catch (e) {
    console.warn("হিসাব আনা গেল না:", e.message);
  }
  fire();
}

async function loadMine() {
  myVotes = readCache(LS_MINE) || {};
  fire();
}

/* ───────────────────────── ভোট দেওয়া ───────────────────────── */

/** একজনের মত জমা দিই — ভোট, রেটিং আর লেখা একসাথে।
 *  vote: "runs" | "no" | "unsure" | null (null = ভোট বদলাবে না) */
async function submit(routeKey, { vote, rating, text, name } = {}) {
  const c = await connect();
  if (!c) throw new Error("সার্ভারের সাথে যোগাযোগ নেই");

  const { doc, runTransaction, serverTimestamp } = c.store;
  const mineRef = doc(c.db, "buses", routeKey, "reviews", c.uid);
  const sumRef = doc(c.db, "summary", "all");

  await runTransaction(c.db, async (tx) => {
    // Firestore-এ লেনদেনের সব পড়া আগে সারতে হয়, তারপর লেখা
    const prevSnap = await tx.get(mineRef);
    const sumSnap = await tx.get(sumRef);

    const prev = prevSnap.exists() ? prevSnap.data() : null;
    const all = (sumSnap.exists() ? sumSnap.data().b : null) || {};
    const cur = { r: 0, n: 0, u: 0, rs: 0, rc: 0, ...(all[routeKey] || {}) };

    const FIELD = { runs: "r", no: "n", unsure: "u" };

    // আগের ভোট থাকলে সেটা বাদ দিয়ে নতুনটা যোগ করি
    const newVote = vote || (prev && prev.v) || null;
    if (prev && prev.v && FIELD[prev.v]) cur[FIELD[prev.v]] = Math.max(0, cur[FIELD[prev.v]] - 1);
    if (newVote && FIELD[newVote]) cur[FIELD[newVote]] += 1;

    const newRating = rating != null ? rating : (prev ? prev.rating : 0);
    if (prev && prev.rating) { cur.rs -= prev.rating; cur.rc = Math.max(0, cur.rc - 1); }
    if (newRating) { cur.rs += newRating; cur.rc += 1; }

    const mine = {
      v: newVote || null,
      rating: newRating || 0,
      text: (text != null ? text : (prev ? prev.text : "") || "").slice(0, 500),
      name: (name != null ? name : (prev ? prev.name : "") || "").slice(0, 40),
      bus: routeKey,
      at: serverTimestamp(),
    };

    tx.set(mineRef, mine);
    tx.set(sumRef, { b: { [routeKey]: cur } }, { merge: true });

    summary[routeKey] = cur;
    myVotes[routeKey] = { v: mine.v, rating: mine.rating, text: mine.text, name: mine.name };
  });

  writeCache(LS_SUM, summary);
  writeCache(LS_MINE, myVotes);
  fire();
}

/* ──────────────────── অন্যদের মত পড়া ──────────────────── */

/** একটা বাসের সব রিভিউ (নতুনগুলো আগে) */
async function reviewsOf(routeKey, limitTo = 25) {
  const c = await connect();
  if (!c) return [];
  const { collection, query, orderBy, limit, getDocs } = c.store;
  const q = query(
    collection(c.db, "buses", routeKey, "reviews"),
    orderBy("at", "desc"), limit(limitTo)
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ ...d.data(), mine: d.id === c.uid }));
}

/** সব বাস মিলিয়ে সাম্প্রতিক রিপোর্ট — "সবাই কী বলছে" পাতার জন্য */
async function recentAll(limitTo = 40) {
  const c = await connect();
  if (!c) return [];
  const { collectionGroup, query, orderBy, limit, getDocs } = c.store;
  const q = query(collectionGroup(c.db, "reviews"), orderBy("at", "desc"), limit(limitTo));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ ...d.data(), mine: d.id === c.uid }));
}

/* ───────────────────── বাইরের জন্য ───────────────────── */

function statusOf(routeKey) {
  const s = summary[routeKey];
  if (!s) return { state: "unknown", runs: 0, no: 0, unsure: 0, total: 0, rating: 0, ratingCount: 0 };
  const runs = s.r || 0, no = s.n || 0, unsure = s.u || 0;
  const total = runs + no + unsure;
  let state = "unknown";
  if (total >= 1) {
    // যেদিকে বেশি মানুষ, সেটাই। সমান হলে "নিশ্চিত নয়"।
    if (runs > no) state = "runs";
    else if (no > runs) state = "no";
    else state = "mixed";
  }
  return {
    state, runs, no, unsure, total,
    rating: s.rc ? s.rs / s.rc : 0,
    ratingCount: s.rc || 0,
  };
}

/** সাজানোর ওজন — নিশ্চিত চলে সবার উপরে, চলে না সবার নিচে */
function rankOf(routeKey) {
  const st = statusOf(routeKey);
  if (st.state === "runs") return 1000 + Math.min(st.runs - st.no, 500);
  if (st.state === "mixed") return 10;
  if (st.state === "unknown") return 0;
  return -1000 - Math.min(st.no - st.runs, 500);   // চলে না
}

const myVoteOf = (routeKey) => myVotes[routeKey] || null;
const onChange = (fn) => listeners.push(fn);
const fire = () => listeners.forEach((f) => { try { f(); } catch (e) { console.error(e); } });

window.Community = {
  configured, connect, loadSummary, loadMine, submit,
  reviewsOf, recentAll, statusOf, rankOf, myVoteOf, onChange,
  get uid() { return fb && fb.uid; },
};

})();
