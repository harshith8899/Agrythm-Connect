import React, { useEffect, useRef, useState } from 'react';
import { Lock, User, Eye, EyeOff, Loader2, ShieldCheck, Server, CheckCircle2 } from 'lucide-react';
import { loginAdmin, pingServer } from '../utils';

const NOT_CONNECTED = 'This dashboard is not connected to the server. In Cloudflare, open the Worker, Settings, Variables and Secrets, and check that BACKEND_URL and API_TOKEN are both there (type Secret), then deploy.';
const TOO_LONG = 'The server did not answer. Check that the Render service shows Live, then press Sign in again.';

const SLOW_AFTER_S = 180;         // a start normally takes under a minute; after this the note changes, but waking never stops
const MAX_WAIT_S = 600;           // how long a pressed Sign in waits for the server before it says so
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const LoginScreen = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [server, setServer] = useState('waking');      // waking | ready | unconfigured
  const [seconds, setSeconds] = useState(0);
  const ready = useRef(false);
  const unconfigured = useRef('');

  // Wake the server the moment this page opens (the password can be typed and Sign in pressed meanwhile: it waits for the server).
  // Keeps asking until the server answers; a dashboard that is not connected to a server at all is told apart at once.
  useEffect(() => {
    let stopped = false;
    const startedAt = Date.now();
    const tick = setInterval(() => setSeconds(Math.round((Date.now() - startedAt) / 1000)), 1000);
    (async () => {
      while (!stopped) {
        const answer = await pingServer();
        if (stopped) return;
        if (answer.ok) {
          ready.current = true;
          unconfigured.current = '';
          setServer('ready');
          return;
        }
        if (answer.status === 503 && /not configured/i.test(answer.message)) {
          unconfigured.current = answer.message;
          setServer('unconfigured');
          await wait(10000);                 // maybe the settings are being fixed: keep looking
        } else {
          unconfigured.current = '';
          setServer('waking');
          await wait(3000);
        }
      }
    })();
    return () => { stopped = true; clearInterval(tick); };
  }, []);

  // Resolves when the server answers. Rejects when the dashboard is not connected to a server, or after MAX_WAIT_S.
  const untilReady = async () => {
    const startedAt = Date.now();
    while (!ready.current) {
      if (unconfigured.current) throw Object.assign(new Error(NOT_CONNECTED), { fatal: true });
      if (Date.now() - startedAt > MAX_WAIT_S * 1000) throw Object.assign(new Error(TOO_LONG), { fatal: true });
      await wait(400);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      await untilReady();                                // signs in the moment the server is up
      for (let attempt = 0; ; attempt += 1) {            // a start-up error right after is retried; a wrong password never is
        try {
          await loginAdmin(username.trim(), password);
          break;
        } catch (err) {
          if (!err.transient || attempt >= 10) throw err;
          await wait(3000);
        }
      }
      setError('');
      if (onLoginSuccess) {
        onLoginSuccess();
      }
    } catch (err) {
      setError(err.message === NOT_CONNECTED ? 'Cannot sign in yet: the dashboard is not connected to the server (see above).'
        : (err.fatal ? err.message : (err.transient ? TOO_LONG : (err.message || 'Invalid username or password.'))));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-trust-canvas flex flex-col justify-center items-center p-4 sm:p-6 lg:p-8 antialiased selection:bg-trust-green selection:text-white">
      {/* Background radial accent */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-emerald-100/40 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-slate-200/50 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Card Header with Branding */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center p-2.5 bg-white rounded-2xl border border-slate-200/80 shadow-xs mb-3.5">
            <img
              src="/agrythm-logo.png"
              alt="Agrythm Logo"
              className="w-12 h-12 object-contain rounded-xl"
            />
          </div>
          <h1 className="text-2xl font-black text-trust-navy tracking-tight">
            Agrythm Connect
          </h1>
          <p className="text-xs font-semibold text-slate-500 mt-1 flex items-center justify-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-trust-green" />
            <span>Secure Admin Authentication</span>
          </p>
        </div>

        {/* Login Box */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8">
          <div className="mb-5">
            <h2 className="text-base font-bold text-slate-900">Sign in to console</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Enter authorized administrator credentials to manage campaigns and farmer records.
            </p>
          </div>

          {server === 'waking' && (
            <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2" role="status" aria-live="polite">
              <Server className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
              <span>
                <strong>Waking up the server...</strong>{' '}
                {seconds < SLOW_AFTER_S
                  ? 'It sleeps when idle and can take up to a minute. Type your details and press Sign in: you are signed in as soon as it is ready.'
                  : 'This is taking longer than usual. Still trying; you can keep this page open and press Sign in.'}{' '}
                {seconds} s
              </span>
            </div>
          )}
          {server === 'ready' && (
            <div className="mb-4 p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>Server is ready.</span>
            </div>
          )}
          {server === 'unconfigured' && (
            <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs" role="alert">
              {NOT_CONNECTED}
            </div>
          )}

          {error && (
            <div
              className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs font-medium flex items-center gap-2"
              role="alert"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-rose-600 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-xs font-bold text-slate-700 mb-1.5"
              >
                Admin Username
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <User className="w-4 h-4" />
                </div>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  autoFocus
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter admin username"
                  className="w-full pl-10 pr-3.5 py-2.5 bg-slate-50 border border-slate-200/90 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy focus:ring-2 focus:ring-trust-navy/10 transition-all"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-bold text-slate-700 mb-1.5"
              >
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  className="w-full pl-10 pr-10 py-2.5 bg-slate-50 border border-slate-200/90 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy focus:ring-2 focus:ring-trust-navy/10 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 cursor-pointer"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-trust-navy hover:bg-slate-800 text-white text-xs font-bold tracking-wide transition-all duration-150 shadow-xs hover:shadow-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                  <span>{server === 'ready' ? 'Verifying credentials...' : 'Waiting for the server, then signing in...'}</span>
                </>
              ) : (
                <span>Sign In to Dashboard</span>
              )}
            </button>
          </form>
        </div>

        {/* Security badge footer */}
        <p className="text-center text-[11px] text-slate-400 mt-6 flex items-center justify-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5 text-trust-green" />
          <span>Trust AI Zero-Trust Console &bull; Session Secured</span>
        </p>
      </div>
    </div>
  );
};

