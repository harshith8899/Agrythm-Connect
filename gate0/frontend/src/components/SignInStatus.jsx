import React from 'react';
import { Loader2, Server, XCircle } from 'lucide-react';
import { SliderLoader } from './SliderLoader';

const DIAGNOSE_AFTER_S = 40;      // a cold start answers within about 25 s: past this, show what the connection is really saying

// Shown on the dashboard while the sign-in is still being finished in the background (the server may be waking up).
// info: { phase: 'waking' | 'signing' | 'unconfigured', seconds, last: { status, message } | null }
export const SignInStatus = ({ username, info, onCancel }) => {
  const { phase, seconds, last } = info;
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
        <button type="button" onClick={onCancel} className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center whitespace-nowrap shrink-0 bg-white border border-amber-200 text-xs font-semibold cursor-pointer">Cancel</button>
      </div>
      <SliderLoader tone="amber" />
    </div>
  );
};
