// Service worker — minimal PWA shell с offline fallback для статики.
//
// Strategy:
// - /api/* и /stream/* → network-first (всегда свежие данные, не кешируем)
// - /assets/* (Vite hashed bundles) → cache-first (immutable)
// - / и navigate requests → network-first c fallback на cached index.html
//
// Версионирование: при изменении CACHE_NAME старые кеши удаляются.

const CACHE_NAME = "crypto-dashboard-v1";
const PRECACHE_URLS = [
  "/",
  "/manifest.webmanifest",
  "/icon-192.svg",
  "/icon-512.svg",
  "/apple-touch-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS).catch(() => {})),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Always bypass cache для API + SSE
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/stream/")) {
    return; // default network behavior
  }

  // Cache-first для immutable Vite assets
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(event.request).then(
        (cached) =>
          cached ||
          fetch(event.request).then((resp) => {
            if (resp.ok) {
              const clone = resp.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return resp;
          }),
      ),
    );
    return;
  }

  // Network-first с offline fallback на index.html для navigate
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match("/")),
    );
  }
});
