import { useEffect, useState } from 'react';
import { pingServer, wakeDirect } from '../utils/api';

const DIRECT_EVERY_MS = 30000;      // the direct request is not repeated more often than this
const ATTEMPT_MS = 30000;           // a sleeping free-plan server normally answers within about 30 s: if one request got no answer by then, ask again
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The one wake-up of the server. It starts when the sign-in page opens (active = no session) and keeps going after Sign in is
 * pressed, so there is never a second wake and the timer never restarts. One request is out at a time.
 * While the server is not answering, the browser also asks it directly (wakeDirect), at once and then every 30 s at most.
 *   - an answer: server 'ready'
 *   - no answer in 30 s: the next request goes out at once (the wake is tried again)
 *   - an error answer (502/503, or 429 too many requests): wait a little, longer after each miss and at least 10 s after a 429
 * Returns { server: 'waking' | 'ready' | 'unconfigured', seconds, last: { status, message } | null, attempts }.
 */
export const useServerWake = (active) => {
  const [state, setState] = useState({ server: 'waking', seconds: 0, last: null, attempts: 0 });

  useEffect(() => {
    if (!active) return undefined;
    let stopped = false;
    const startedAt = Date.now();
    setState({ server: 'waking', seconds: 0, last: null, attempts: 0 });
    const tick = setInterval(() => {
      setState((prev) => (prev.server === 'ready' ? prev : { ...prev, seconds: Math.round((Date.now() - startedAt) / 1000) }));
    }, 1000);
    (async () => {
      let directAt = 0;
      for (let n = 1; !stopped; n += 1) {
        if (Date.now() - directAt >= DIRECT_EVERY_MS) {
          directAt = Date.now();
          wakeDirect();
        }
        const answer = await pingServer(ATTEMPT_MS);
        if (stopped) return;
        const last = { status: answer.status, message: answer.message };
        if (answer.ok) {
          setState((prev) => ({ ...prev, server: 'ready', last, attempts: n }));
          return;
        }
        const unconfigured = answer.status === 503 && /not configured/i.test(answer.message);
        setState((prev) => ({ ...prev, server: unconfigured ? 'unconfigured' : 'waking', last, attempts: n }));
        let pause = Math.min(3000 + n * 2000, 10000);          // an error answered at once
        if (answer.status === 429) pause = 10000;
        if (answer.status === 0) pause = 500;                  // no answer in 30 s: ask again now
        if (unconfigured) pause = 10000;
        await wait(pause);
      }
    })();
    return () => { stopped = true; clearInterval(tick); };
  }, [active]);

  return state;
};

export default useServerWake;
