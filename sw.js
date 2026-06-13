// 고물시세앱 Service Worker
// 오프라인 지원 + 빠른 재방문 위해 핵심 자산 캐싱.
// 자산(파일)을 바꾸면 CACHE_NAME 버전을 올려야 새 SW가 옛 캐시를 정리한다.

const CACHE_NAME = 'gomul-v8';
const CORE_ASSETS = [
  './',
  './index.html',
  './tailwind.css',
  './style.css',
  './app.js',
  './data.js',
  './manifest.json',
  './icon.svg',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './apple-touch-icon.png',
];

// 캐시에 넣어도 되는 응답인지 — 성공(2xx)한 동일출처/CORS 응답만.
// CDN의 5xx 에러페이지나 opaque(cross-origin no-cors) 응답이 캐시에 박혀
// 영구히 잘못된 자산으로 서빙되는 것을 막는다.
function isCacheable(res) {
  return res && res.ok && (res.type === 'basic' || res.type === 'cors');
}

function putInCache(req, res) {
  if (!isCacheable(res)) return;
  const copy = res.clone();
  caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
}

self.addEventListener('install', (event) => {
  // addAll은 하나라도 실패하면 전체 설치가 실패한다.
  // 자산별 개별 캐싱(allSettled)으로 하나가 404여도 나머지는 캐시되게 한다.
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.allSettled(
        CORE_ASSETS.map((url) =>
          fetch(url, { cache: 'no-cache' }).then((res) => {
            if (isCacheable(res)) return cache.put(url, res);
          })
        )
      ).then(() => self.skipWaiting())
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;

  // data.json: 네트워크 우선 (매일 갱신)
  if (sameOrigin && url.pathname.endsWith('/data.json')) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          putInCache(req, res);
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // 동일 출처 자산: 캐시 우선 → 네트워크 폴백
  if (sameOrigin) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req)
          .then((res) => {
            putInCache(req, res);
            return res;
          })
          .catch(() => cached);
      })
    );
    return;
  }

  // CDN(외부): 네트워크 우선 → 실패 시 캐시
  event.respondWith(
    fetch(req)
      .then((res) => {
        putInCache(req, res);
        return res;
      })
      .catch(() => caches.match(req))
  );
});
