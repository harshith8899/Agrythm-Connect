import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
//
// In development the dashboard calls /api on its own address and this dev server forwards it. By default that is the
// backend on this computer (http://localhost:8000). To use the hosted backend (Render) instead, create
// gate0/frontend/.env.local (never committed) with:
//   GATE0_PROXY_TARGET=https://your-service.onrender.com
//   GATE0_API_TOKEN=the-same-token-the-backend-uses
// The token stays in this dev server: the browser never sees it (these names have no VITE_ prefix on purpose).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = (env.GATE0_PROXY_TARGET || 'http://localhost:8000').replace(/\/+$/, '')
  const token = env.GATE0_API_TOKEN || ''
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
          secure: true,
          // a free Render service takes up to a minute to wake: do not give up before it answers
          timeout: 90000,
          proxyTimeout: 90000,
          headers: token ? { 'X-API-Token': token } : {},
        },
      },
    },
  }
})
