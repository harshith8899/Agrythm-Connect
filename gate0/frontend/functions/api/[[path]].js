// Cloudflare Pages Function: forwards /api/* to the Render API and forwards Authorization headers cleanly.
// When API_TOKEN is set in Cloudflare Pages env, it is also forwarded as X-API-Token.
// Settings (Pages project, Settings, Variables and Secrets): BACKEND_URL (plain text) and optional API_TOKEN (secret).
export async function onRequest({ request, env }) {
  const backend = String(env.BACKEND_URL || '').replace(/\/+$/, '');
  if (!backend) {
    return Response.json({ error: 'API proxy is not configured' }, { status: 503 });
  }
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  for (const name of ['host', 'cookie', 'cf-access-jwt-assertion', 'cf-connecting-ip', 'x-forwarded-for']) {
    headers.delete(name);
  }
  if (env.API_TOKEN) {
    headers.set('X-API-Token', env.API_TOKEN);
  }
  const authHeader = request.headers.get('Authorization');
  if (authHeader) {
    headers.set('Authorization', authHeader);
  }
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
