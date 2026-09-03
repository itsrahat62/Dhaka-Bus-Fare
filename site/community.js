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
    summary = cached.b || cached;      // পুরোনো ক্যাশে শুধু b ছিল
    approved = cached.x || [];
    fire();
  }
  const c = await connect();
  if (!c) return;

  try {
    const { doc, getDoc } = c.store;
    const snap = await getDoc(doc(c.db, "summary", "all"));
    const d = snap.exists() ? snap.data() : {};
    summary = d.b || {};
    approved = d.x || [];        // সবার যাচাই করা নতুন বাসগুলো
    writeCache(LS_SUM, { b: summary, x: approved });
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

  // ক্যাশে {b, x} আকারেই লিখতে হয় — শুধু summary লিখলে অনুমোদিত
  // বাসগুলোর তালিকা (x) মুছে যেত, আর পরের বার পাতা খুললে ওগুলো
  // উধাও হয়ে যেত যতক্ষণ না সার্ভার থেকে নতুন করে আসে
  writeCache(LS_SUM, { b: summary, x: approved });
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

/* ═══════════════ নতুন বাস যোগ করা ═══════════════

   তালিকাটা পুরোনো, নতুন বাস নামছে — তাই যে কেউ বাস যোগ করার প্রস্তাব
   দিতে পারে। তবে সরাসরি সাইটে ঢোকে না:

     ১. প্রস্তাব জমা হয় proposals/<id>-তে, status="pending"
     ২. অন্যরা "চিনি / চিনি না" ভোট দেয় — কোনটা আসল সেটা বোঝা যায়
     ৩. অ্যাডমিন (Google লগইন) চূড়ান্ত হ্যাঁ/না বলেন
     ৪. অনুমোদিত হলে extra/buses ডকুমেন্টে যোগ হয়, সাইট ওখান থেকেই পড়ে

   স্টপেজ চেনাতে ইংরেজি নাম ব্যবহার করা হয়, সূচক নয় — ডেটা আবার তৈরি
   করলে সূচক বদলে যায়, নাম বদলায় না।                                */

// কতজন "চিনি" বললে বাসটা নিজে থেকেই তালিকায় ঢুকবে
const APPROVE_AT = 10;

/* অনুমোদিত বাসগুলো summary/all ডকুমেন্টের ভেতরেই (x ফিল্ডে) রাখা হয়।
   ওই ডকুমেন্ট এমনিতেই প্রতিবার পড়া হয়, তাই এতে একটাও বাড়তি read
   লাগে না — ফ্রি কোটার জন্য এটা বড় ব্যাপার। */
let approved = [];
const approvedBuses = () => approved;

/** নতুন বাসের প্রস্তাব জমা দিই */
async function propose({ bn, en, stops, note }) {
  const c = await connect();
  if (!c) throw new Error("সার্ভারের সাথে যোগাযোগ নেই");
  const { collection, addDoc, serverTimestamp } = c.store;
  return addDoc(collection(c.db, "proposals"), {
    bn: (bn || "").trim().slice(0, 40),
    en: (en || "").trim().slice(0, 40),
    stops: stops.slice(0, 60),
    note: (note || "").trim().slice(0, 200),
    by: c.uid,
    at: serverTimestamp(),
    status: "pending",
    yes: 0,
    no: 0,
  });
}

/** অপেক্ষায় থাকা প্রস্তাবগুলো, নতুনগুলো আগে */
async function proposals(status = "pending", limitTo = 30) {
  const c = await connect();
  if (!c) return [];
  const { collection, query, where, orderBy, limit, getDocs } = c.store;
  const q = query(collection(c.db, "proposals"),
    where("status", "==", status), orderBy("at", "desc"), limit(limitTo));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...d.data(), mine: d.data().by === c.uid }));
}

/** প্রস্তাবে "চিনি / চিনি না" ভোট — এক ফোন, এক ভোট।

    যথেষ্ট মানুষ (APPROVE_AT জন) চিনি বললে বাসটা ওই লেনদেনেই তালিকায়
    ঢুকে যায় — কারও অনুমোদনের অপেক্ষা করতে হয় না। ভুল কিছু ঢুকে গেলে
    অ্যাডমিন পরে সরাতে পারেন। */
async function voteProposal(id, v) {
  const c = await connect();
  if (!c) throw new Error("সার্ভারের সাথে যোগাযোগ নেই");
  const { doc, runTransaction, serverTimestamp } = c.store;
  const pRef = doc(c.db, "proposals", id);
  const vRef = doc(c.db, "proposals", id, "votes", c.uid);
  const sRef = doc(c.db, "summary", "all");
  let becameApproved = false;

  await runTransaction(c.db, async (tx) => {
    // Firestore-এ লেনদেনের সব পড়া আগে, তারপর লেখা
    const prev = await tx.get(vRef);
    const p = await tx.get(pRef);
    if (!p.exists()) throw new Error("প্রস্তাবটা আর নেই");
    const d = p.data();
    const sum = await tx.get(sRef);

    let yes = d.yes || 0, no = d.no || 0;
    const old = prev.exists() ? prev.data().v : null;
    if (old === "yes") yes = Math.max(0, yes - 1);
    if (old === "no") no = Math.max(0, no - 1);
    if (v === "yes") yes += 1; else no += 1;

    tx.set(vRef, { v, at: serverTimestamp() });

    // "চিনি না" যারা বলেছেন তাঁরাও গোনায় ধরা — নইলে ১০ জন জোগাড় করে
    // যা খুশি ঢোকানো যেত
    const ready = d.status === "pending" && (yes - no) >= APPROVE_AT;
    tx.update(pRef, ready ? { yes, no, status: "approved" } : { yes, no });

    if (ready) {
      const list = (sum.exists() ? sum.data().x : null) || [];
      if (!list.some((x) => x.id === id)) {
        list.push({ id, bn: d.bn, stops: d.stops, by: d.by });
        tx.set(sRef, { x: list }, { merge: true });
        approved = list;
        becameApproved = true;
      }
    }
  });

  propVotes[id] = v;
  writeCache(LS_PROP, propVotes);
  if (becameApproved) { writeCache(LS_SUM, { b: summary, x: approved }); fire(); }
  return becameApproved;
}

/* আমি কোন প্রস্তাবে কী ভোট দিয়েছি — এটা এই ফোনেই জমা থাকে।

   আগে প্রতিটা প্রস্তাবের জন্য আলাদা getDoc করা হতো। ৩০টা প্রস্তাব
   থাকলে প্রতিবার পাতা খুললেই ৩০টা read — ফ্রি কোটা (দিনে ৫০ হাজার)
   কয়েকশো ভিজিটেই শেষ। অথচ পরিচয়টা anonymous auth-এর, সেটা এমনিতেই
   এই ব্রাউজারেই বাঁধা; তাই লোকাল হিসাবটাই সমান কাজের।

   কেউ ব্রাউজারের তথ্য মুছে ফেললে আবার জিজ্ঞেস করা হবে, কিন্তু ভোট
   দুইবার গোনা হবে না — লেনদেনে আগের ভোট বাদ দিয়ে নতুনটা বসে। */
const LS_PROP = "dbf.propVotes.v1";
let propVotes = readCache(LS_PROP) || {};

async function myProposalVotes() {
  return propVotes;
}

window.Community = {
  configured, connect, loadSummary, loadMine, submit,
  reviewsOf, recentAll, statusOf, rankOf, myVoteOf, onChange,
  approvedBuses, propose, proposals, voteProposal, myProposalVotes,
  APPROVE_AT,
  get uid() { return fb && fb.uid; },
};

})();
