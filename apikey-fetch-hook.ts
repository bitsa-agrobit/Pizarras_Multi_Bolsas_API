// Global fetch hook to inject X-API-Key only for /api/* requests.
// Usage: place this file at src/apikey-fetch-hook.ts and import it once
// at the very top of your entry (e.g., src/main.tsx or src/main.ts):
//    import './apikey-fetch-hook'
//
// Requires Vite env var: VITE_API_KEY

export {} // ensure this is treated as a module

declare global {
  interface Window {
    fetch: typeof fetch
  }
}

const VITE_API_KEY = (import.meta as any)?.env?.VITE_API_KEY as string | undefined;

if (typeof window !== 'undefined' && VITE_API_KEY) {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    let urlStr: string | undefined;
    if (typeof input === 'string') {
      urlStr = input;
    } else if ((input as URL) instanceof URL) {
      urlStr = (input as URL).toString();
    } else if ((input as Request).url) {
      urlStr = (input as Request).url;
    }

    if (urlStr && urlStr.includes('/api/')) {
      const headers = new Headers(init?.headers || {});
      headers.set('X-API-Key', VITE_API_KEY);
      return originalFetch(input, { ...init, headers });
    }
    return originalFetch(input, init);
  };
}
