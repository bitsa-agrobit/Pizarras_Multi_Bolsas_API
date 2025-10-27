// frontend/src/apikey-fetch-hook.js
export {};

const KEY = import.meta?.env?.VITE_API_KEY;
if (typeof window !== 'undefined') {
  window.__VITE_API_KEY = KEY || null;           // <-- para chequear en consola
  console.log('[apikey-fetch-hook] KEY is', KEY ? 'set' : 'MISSING');

  if (KEY) {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      let urlStr;
      if (typeof input === 'string') urlStr = input;
      else if (input instanceof URL) urlStr = input.toString();
      else if (input && input.url) urlStr = input.url;

      if (urlStr && urlStr.includes('/api/')) {
        const headers = new Headers(init?.headers || {});
        headers.set('X-API-Key', KEY);
        return originalFetch(input, { ...init, headers });
      }
      return originalFetch(input, init);
    };
  }
}