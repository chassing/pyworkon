/**
 * Service Worker: only exists so iOS/Android treat this as an installable PWA and
 * cache the rarely-changing static assets (icon webfont, app icons) for instant
 * repeat loads. Scope: ONLY GET requests for /fonts/ and /pwa/ assets are ever
 * intercepted — the dashboard page itself, /ingest, and the /ws WebSocket
 * connection always pass straight through untouched, since this is a live view
 * that must never serve stale cached state.
 */

const CACHE_NAME = 'pyworkon-relay-static-v1';
const CACHEABLE_RE = /\/(fonts|pwa)\//;

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((name) => name.startsWith('pyworkon-relay-static-') && name !== CACHE_NAME).map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('fetch', (event) => {
  const url = event.request.url;
  if (event.request.method !== 'GET' || !CACHEABLE_RE.test(url)) {
    return;
  }
  event.respondWith(handleStaticRequest(event));
});

async function handleStaticRequest(event) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(event.request);
  if (cached) {
    return cached;
  }
  const response = await fetch(event.request);
  if (response.ok) {
    event.waitUntil(cache.put(event.request, response.clone()));
  }
  return response;
}
