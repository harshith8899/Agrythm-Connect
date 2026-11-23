import React, { useState } from 'react';
import { ExternalLink, Loader2, Power } from 'lucide-react';
import { API_BASE } from '../utils/constants';

const WAKE_TIMEOUT_MS = 90000;

// "Wake the server" asks the server (through the Cloudflare Worker, which knows the Render address) to answer and says what came back;
// "Open server" opens the server's own health page in a new tab, which also wakes it. The page's own retries go on meanwhile.
export const WakeServerControls = ({ buttonClass = '', linkClass = '' }) => {
  const [wake, setWake] = useState({ busy: false, text: '' });
  const run = async () => {
    setWake({ busy: true, text: 'Asking the server to wake up (this can take up to a minute)...' });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), WAKE_TIMEOUT_MS);
    try {
      const res = await fetch(`${API_BASE}/api/wake`, { cache: 'no-store', signal: controller.signal });
      let body = {};
      try { body = await res.json(); } catch { /* not JSON */ }
      if (body.status === 200) setWake({ busy: false, text: 'The server answered: it is awake. The page carries on by itself.' });
      else if (body.status === 429) setWake({ busy: false, text: 'The host says too many requests (HTTP 429). Wait a minute and try once more; do not press repeatedly.' });
      else if (body.status) setWake({ busy: false, text: `The server answered HTTP ${body.status}. It may still be starting: try again in a few seconds.` });
      else setWake({ busy: false, text: body.error || 'The server did not answer yet. Try again in a few seconds.' });
    } catch {
      setWake({ busy: false, text: 'No answer yet. The server may still be starting: try again in a few seconds.' });
    } finally {
      clearTimeout(timer);
    }
  };
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={run} disabled={wake.busy} className={buttonClass || 'h-9 px-3.5 rounded-xl inline-flex items-center justify-center gap-1.5 whitespace-nowrap bg-amber-600 text-white border border-amber-700 text-xs font-semibold cursor-pointer disabled:opacity-60 disabled:cursor-wait'}>
          {wake.busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}Wake the server
        </button>
        <a href={`${API_BASE}/api/wake?open=1`} target="_blank" rel="noreferrer" className={linkClass || 'h-9 px-3.5 rounded-xl inline-flex items-center justify-center gap-1.5 whitespace-nowrap bg-white border border-amber-200 text-xs font-semibold no-underline text-amber-950'} title="Opens the server's own address in a new tab; opening it also wakes it">
          <ExternalLink className="w-3.5 h-3.5" />Open server
        </a>
      </div>
      {wake.text && <div className="mt-2 text-xs font-semibold text-amber-900" role="status">{wake.text}</div>}
    </>
  );
};

export default WakeServerControls;
