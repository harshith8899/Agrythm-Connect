import React, { useState } from 'react';
import { ExternalLink, Loader2, Power, Server, XCircle } from 'lucide-react';
import { API_BASE } from '../utils/constants';
import { SliderLoader } from './SliderLoader';

const DIAGNOSE_AFTER_S = 40;      // a cold start answers within about 25 s: past this, show what the connection is really saying

// Shown on the dashboard while the sign-in is still being finished in the background (the server may be waking up).
// info: { phase: 'waking' | 'signing' | 'unconfigured', seconds, last: { status, message } | null }
const WAKE_TIMEOUT_MS = 90000;

// The Wake button: asks the server (through the Worker, which knows the Render address) to answer, and says what came back.
const useWake = () => {
  const [wake, setWake] = useState({ busy: false, text: '' });
  const run = async () => {
    setWake({ busy: true, text: 'Asking the server to wake up (this can take up to a minute)...' });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), WAKE_TIMEOUT_MS);
    try {
      const res = await fetch(`${API_BASE}/api/wake`, { cache: 'no-store', signal: controller.signal });
      let body = {};
      try { body = await res.json(); } catch { /* not JSON */ }
      if (body.status === 200) setWake({ busy: false, text: 'The server answered: it is awake. The data will appear in a moment.' });
      else if (body.status) setWake({ busy: false, text: `The server answered HTTP ${body.status}. It may still be starting: try again in a few seconds.` });
      else setWake({ busy: false, text: body.error || 'The server did not answer yet. Try again in a few seconds.' });
    } catch {
      setWake({ busy: false, text: 'No answer yet. The server may still be starting: try again in a few seconds.' });
    } finally {
      clearTimeout(timer);
    }
  };
  return [wake, run];
};

export const SignInStatus = ({ username, info, onCancel }) => {
  const { phase, seconds, last } = info;
  const [wake, runWake] = useWake();
  if (phase === 'unconfigured') {
    return (
      <div className="bg-rose-50 border border-rose-200 p-4 rounded-2xl text-rose-900 shadow-xs flex items-start justify-between gap-3" role="alert">
        <div className="flex items-start gap-3">
          <XCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <div className="text-sm font-bold">This dashboard is not connected to the server</div>
            In Cloudflare, open the Worker, Settings, Variables and Secrets, and check that BACKEND_URL and API_TOKEN are both there
            (type Secret), then deploy. Signing in continues by itself once that is fixed.
          </div>
        </div>
        <button type="button" onClick={onCancel} className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center whitespace-nowrap shrink-0 bg-white border border-rose-200 text-xs font-semibold cursor-pointer">Cancel</button>
      </div>
    );
  }
  return (
    <div className="bg-amber-50 border border-amber-200 p-4 rounded-2xl text-amber-950 shadow-xs space-y-3" role="status" aria-live="polite">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center text-amber-700 shrink-0">
            {phase === 'signing' ? <Loader2 className="w-5 h-5 animate-spin" /> : <Server className="w-5 h-5" />}
          </div>
          <div className="min-w-0 text-xs leading-relaxed">
            <div className="text-sm font-bold">{phase === 'signing' ? 'Checking your sign-in...' : `Signing you in${username ? ` as ${username}` : ''}...`}</div>
            {phase === 'signing'
              ? 'The server is awake. Your details are being checked.'
              : 'The server is waking up (it sleeps when idle and can take up to a minute). You are in: the data appears by itself as soon as it is ready.'}{' '}
            {seconds} s
            {phase === 'waking' && seconds >= DIAGNOSE_AFTER_S && last && (
              <span className="block mt-1.5 font-mono text-[11px] text-amber-900/80">
                Last answer from the connection to the server: {last.status ? `HTTP ${last.status}` : 'no answer'}{last.message ? ` (${last.message})` : ''}.{' '}
                {last.status === 0
                  ? 'The request is not being answered at all: check that the Cloudflare Worker is deployed.'
                  : 'The Worker answers but cannot reach the server: check that BACKEND_URL on the Cloudflare Worker is exactly the Render address (https, no path).'}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
          {phase === 'waking' && (
            <>
              <button type="button" onClick={runWake} disabled={wake.busy} className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center gap-1.5 whitespace-nowrap bg-amber-600 text-white border border-amber-700 text-xs font-semibold cursor-pointer disabled:opacity-60 disabled:cursor-wait">
                {wake.busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}Wake the server
              </button>
              <a href={`${API_BASE}/api/wake?open=1`} target="_blank" rel="noreferrer" className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center gap-1.5 whitespace-nowrap bg-white border border-amber-200 text-xs font-semibold no-underline text-amber-950" title="Opens the server's own address in a new tab; opening it also wakes it">
                <ExternalLink className="w-3.5 h-3.5" />Open server
              </a>
            </>
          )}
          <button type="button" onClick={onCancel} className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center whitespace-nowrap bg-white border border-amber-200 text-xs font-semibold cursor-pointer">Cancel</button>
        </div>
      </div>
      {wake.text && <div className="text-xs font-semibold text-amber-900" role="status">{wake.text}</div>}
      <SliderLoader tone="amber" />
    </div>
  );
};
