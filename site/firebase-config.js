/* Firebase-এর সেটিংস।

   এই কনফিগটা গোপন নয় — Firebase-এর ওয়েব apiKey সবসময় ব্রাউজারে যায়,
   গুগল নিজেই বলে এটা পাবলিক ধরে নিতে। আসল নিরাপত্তা আসে Firestore-এর
   security rules থেকে (দেখুন ../firestore.rules)।

   নিজের প্রজেক্ট বসাতে:
     ১. console.firebase.google.com-এ একটা প্রজেক্ট বানান (ফ্রি Spark প্ল্যান)
     ২. Build → Firestore Database → Create database (production mode)
     ৩. Build → Authentication → Sign-in method → Anonymous চালু করুন
     ৪. Project settings → General → Your apps → Web app যোগ করুন
     ৫. যে snippet দেখাবে তার মানগুলো নিচে বসান
     ৬. firestore.rules ফাইলের নিয়মগুলো Firestore → Rules-এ পেস্ট করুন

   খালি রাখলে সাইট চলবে, শুধু ভোট-রিভিউর অংশটা বন্ধ থাকবে। */

window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyAQQ6_H5X8Sq5-VgPNoPRh1drhM82vu6Rc",
  authDomain: "varakoto-51f66.firebaseapp.com",
  projectId: "varakoto-51f66",
  storageBucket: "varakoto-51f66.firebasestorage.app",
  messagingSenderId: "614306119923",
  appId: "1:614306119923:web:f3dec10de0a72a7c887786",
};

/* লোকাল এমুলেটরে যাচাই: ঠিকানার শেষে ?emulator=1 জুড়ে দিলে আসল
   Firebase-এর বদলে নিজের কম্পিউটারের এমুলেটরে যাবে। আসল সাইটে এর
   কোনো প্রভাব নেই। */
if (new URLSearchParams(location.search).get("emulator") === "1") {
  window.FIREBASE_EMULATOR = true;
  window.FIREBASE_CONFIG = {
    apiKey: "demo-key",
    authDomain: "demo-dhakabus.firebaseapp.com",
    projectId: "demo-dhakabus",
  };
}
