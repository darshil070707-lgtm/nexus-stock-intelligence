/**
 * NEXUS Edge Worker — Cloudflare
 * Global cache layer + rate limiting
 */

const BACKEND_URL = 'https://nexus-api.onrender.com';
const CACHE_DURATION = {
  '/analyze/': 45,     // 45 seconds
  '/indices': 10,      // 10 seconds
  '/macro': 60,        // 1 minute
  '/fear-greed': 60,
  '/sectors': 60,
  '/health': 5,
};

export default {
  async fetch(request, env) {
    // Rate limiting: 100 requests per IP per minute
    const ip = request.headers.get('cf-connecting-ip') || 'unknown';
    const rateKey = `rate:${ip}`;
    const rateLimiter = env.CACHE;

    const currentCount = await rateLimiter.get(rateKey);
    const count = currentCount ? parseInt(currentCount) : 0;

    if (count > 100) {
      return new Response('Rate limit exceeded', { status: 429 });
    }

    // Increment counter
    await rateLimiter.put(rateKey, count + 1, { expirationTtl: 60 });

    // CORS headers
    const headers = new Headers({
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'X-Powered-By': 'NEXUS',
    });

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace('/api', '');

    // Cache GET requests only
    if (request.method === 'GET') {
      // Check cache
      const cacheKey = new Request(path, { method: 'GET' });
      const cached = await caches.default.match(cacheKey);

      if (cached) {
        const response = new Response(cached.body, cached);
        response.headers.append('CF-Cache-Status', 'HIT');
        response.headers.set('Access-Control-Allow-Origin', '*');
        return response;
      }

      // Determine cache duration
      let cacheTtl = 60;
      for (const [pattern, ttl] of Object.entries(CACHE_DURATION)) {
        if (path.includes(pattern)) {
          cacheTtl = ttl;
          break;
        }
      }

      // Fetch from backend
      const backendUrl = `${BACKEND_URL}${path}${url.search}`;
      const backendRequest = new Request(backendUrl, {
        method: request.method,
        headers: request.headers,
      });

      let response = await fetch(backendRequest);
      response = new Response(response.body, response);

      // Add cache headers
      response.headers.set('Cache-Control', `public, max-age=${cacheTtl}`);
      response.headers.set('CF-Cache-Status', 'MISS');
      response.headers.set('Access-Control-Allow-Origin', '*');

      // Cache response
      const cacheResponse = new Response(response.body, response);
      await caches.default.put(cacheKey, cacheResponse);

      return response;
    }

    // POST/PUT/DELETE — pass through without caching
    const backendUrl = `${BACKEND_URL}${path}${url.search}`;
    const body = request.method !== 'GET' ? await request.text() : null;

    const backendRequest = new Request(backendUrl, {
      method: request.method,
      headers: request.headers,
      body: body,
    });

    const response = await fetch(backendRequest);
    const newResponse = new Response(response.body, response);
    newResponse.headers.set('Access-Control-Allow-Origin', '*');

    return newResponse;
  },
};
