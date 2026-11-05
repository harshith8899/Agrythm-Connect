// Cloudflare Pages Function: forwards /api/* to the Render API and adds the API token on the server side,
// so the token never reaches the browser. Protect the whole Pages site with Cloudflare Access (see docs/DEPLOY.md),
// otherwise anyone who finds the site could use this proxy.
// Settings (Pages project, Settings, Variables and Secrets): BACKEND_URL (plain text) and API_TOKEN (secret).
export async function onRequest({ request, env }) {
  const backend = String(env.BACKEND_URL || '').replace(/\/+$/, '');
  if (!backend || !env.API_TOKEN) {
    return Response.json({ error: 'API proxy is not configured' }, { status: 503 });
  }
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  for (const name of ['host', 'cookie', 'cf-access-jwt-assertion', 'cf-connecting-ip', 'x-forwarded-for']) headers.delete(name);
  headers.set('X-API-Token', env.API_TOKEN);
  const hasBody = !['GET', 'HEAD'].includes(request.method);
  try {
    return await fetch(backend + url.pathname + url.search, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
    });
  } catch {
    return Response.json({ error: 'Backend not reachable' }, { status: 502 });
  }
}
