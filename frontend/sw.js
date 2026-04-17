const CACHE_NAME = 'attendance-v4';
const SHELL_ASSETS = [
  '/app.html',
  '/static/app.css',
  '/static/app.js',
  '/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Always use network for API calls
  if (url.pathname.startsWith('/api/')) return;

  // Cache-first for shell assets
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return (
        cached ||
        fetch(event.request).then((response) => {
          if (response.ok) {
            caches.open(CACHE_NAME).then((cache) =>
              cache.put(event.request, response.clone())
            );
          }
          return response;
        })
      );
    })
  );
});
