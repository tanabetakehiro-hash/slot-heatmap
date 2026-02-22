/* docs/sw.js */
"use strict";

const CACHE_NAME = "slot-heatmap-v1";
const CORE_ASSETS = [
  "./",
  "./index.html",
  "./unit.html",
  "./assets/style.css",
  "./assets/app.js",
  "./assets/unit.js",
  "./assets/icon.svg",
  "./manifest.webmanifest",
  "./data/index.json",
  "./data/history.json",
  "./data/prediction_next.json"
];

// インストール時：最低限のファイルをキャッシュ
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

// 有効化時：古いキャッシュ削除
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k === CACHE_NAME ? Promise.resolve() : caches.delete(k))))
    ).then(() => self.clients.claim())
  );
});

// fetch：
// - ナビゲーション（HTML）はネット優先（失敗したらキャッシュ）
// - それ以外は キャッシュ優先 → 無ければネット → 成功したらキャッシュ
self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 同一オリジンだけ対象
  if (url.origin !== self.location.origin) return;

  // HTML（ページ遷移）はネット優先
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

  // その他（js/css/json等）はキャッシュ優先
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;

      return fetch(req)
        .then((res) => {
          // 成功したら保存
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          return res;
        })
        .catch(() => cached);
    })
  );
});