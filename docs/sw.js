/* docs/sw.js */
"use strict";

const CACHE_NAME = "slot-heatmap-v3"; // ★ 必ず増やす（v1/v2 から更新）
const CORE_ASSETS = [
  "./",
  "./index.html",
  "./unit.html",
  "./assets/style.css",
  "./assets/app.js",
  "./assets/unit.js",
  "./assets/icon.svg",
  "./manifest.webmanifest"
];

// install: コアだけキャッシュ（data jsonは固定キャッシュしない）
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

// activate: 古いキャッシュ削除
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k === CACHE_NAME ? Promise.resolve() : caches.delete(k))))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  if (url.origin !== self.location.origin) return;

  // ★ data配下のjsonは「ネット優先」：常に最新を取りに行く
  const isDataJson = url.pathname.includes("/data/") && url.pathname.endsWith(".json");
  if (isDataJson) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // ページ遷移はネット優先（失敗したらキャッシュ）
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((m) => m || caches.match("./index.html")))
    );
    return;
  }

  // それ以外はキャッシュ優先
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => cached);
    })
  );
});