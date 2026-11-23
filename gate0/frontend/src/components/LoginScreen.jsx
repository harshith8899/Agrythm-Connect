import React, { useState } from 'react';
import { Lock, User, Eye, EyeOff, ShieldCheck, Server, CheckCircle2 } from 'lucide-react';
import { WakeServerControls } from './WakeServerControls';

const NOT_CONNECTED = 'This dashboard is not connected to the server. In Cloudflare, open the Worker, Settings, Variables and Secrets, and check that BACKEND_URL and API_TOKEN are both there (type Secret), then deploy.';
const DIAGNOSE_AFTER_S = 40;      // a cold start answers within about 25 s: past this, show what the connection is really saying
const SLOW_AFTER_S = 180;         // a start normally takes under a minute; after this the note changes, but waking never stops

// Collects the username and password. Pressing Sign in goes straight into the dashboard (App finishes the sign-in in the background,
// waiting for the server if it is asleep); a wrong password brings the person back here with initialError.
export const LoginScreen = ({ onSignIn, initialError = '', wake }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const { server, seconds, last: lastAnswer } = wake;                // the shared wake-up (useServerWake), started when this page opened

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter both username and password.');
      return;
    }
    setError('');
    onSignIn(username.trim(), password);
  };
  const shownError = error || initialError;

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
                {seconds >= DIAGNOSE_AFTER_S && lastAnswer && (
                  <span className="block mt-1.5 font-mono text-[11px] text-amber-900/80">
                    Last answer from the connection to the server: {lastAnswer.status ? `HTTP ${lastAnswer.status}` : 'no answer'}
                    {lastAnswer.message ? ` (${lastAnswer.message})` : ''}.{' '}
                    {lastAnswer.status === 0
                      ? 'The request is not being answered at all: check that the Cloudflare Worker is deployed.'
                      : lastAnswer.status === 429
                        ? 'The host says too many requests (HTTP 429) while the server starts. This is not a wrong setting: the page waits longer between tries and carries on by itself. If it lasts more than a few minutes, open the service in Render and check that it is Live.'
                        : 'The Worker answers but cannot reach the server: check that BACKEND_URL on the Cloudflare Worker is exactly the Render address (https, no path).'}
                  </span>
                )}
                <span className="block mt-2"><WakeServerControls /></span>
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

          {shownError && (
            <div
              className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200/80 text-rose-800 text-xs font-medium flex items-center gap-2"
              role="alert"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-rose-600 shrink-0" />
              <span>{shownError}</span>
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
              className="w-full mt-2 inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-trust-navy hover:bg-slate-800 text-white text-xs font-bold tracking-wide transition-all duration-150 shadow-xs hover:shadow-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <span>Sign In to Dashboard</span>
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

