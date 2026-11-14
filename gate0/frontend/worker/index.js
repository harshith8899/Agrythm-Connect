// Cloudflare Worker for the dashboard: it serves the built dashboard (the "assets" in wrangler.jsonc) and, for /api/*, forwards the
// request to the Render backend and adds the API token on the server side, so the token never reaches the browser.
//
// wrangler.jsonc sets run_worker_first to /api/*, so only API calls reach this code; every other path is served from the assets.
// Protect the whole site with Cloudflare Access (docs/DEPLOY.md), otherwise anyone who finds the address could use this proxy.
//
// Settings (Worker, Settings, Variables and Secrets), both as Secret: BACKEND_URL (the Render address) and API_TOKEN.
export default {
  async fetch(request, env) {
    const backend = String(env.BACKEND_URL || '').replace(/\/+$/, '');
    if (!backend || !env.API_TOKEN) {
      return Response.json({ error: 'API proxy is not configured' }, { status: 503 });
    }
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) {
      return env.ASSETS.fetch(request);
    }
    const headers = new Headers(request.headers);
    for (const name of ['host', 'cookie', 'cf-access-jwt-assertion', 'cf-connecting-ip', 'x-forwarded-for']) headers.delete(name);
    headers.set('X-API-Token', env.API_TOKEN);
    const hasBody = !['GET', 'HEAD'].includes(request.method);
    try {
      const answer = await fetch(backend + url.pathname + url.search, {
        method: request.method,
        headers,
        body: hasBody ? request.body : undefined,
      });
      const out = new Response(answer.body, answer);
      out.headers.set('Cache-Control', 'no-store');
      return out;
    } catch {
      return Response.json({ error: 'Backend not reachable' }, { status: 502 });
    }
  },
};
