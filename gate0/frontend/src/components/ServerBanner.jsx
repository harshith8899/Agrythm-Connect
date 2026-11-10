import React, { useEffect, useState } from 'react';
import { AlertTriangle, Server } from 'lucide-react';
import { SliderLoader } from './SliderLoader';

const GIVE_UP_AFTER_S = 120; // after this long without an answer it is an error, not just a slow start

// Shown while the dashboard is waiting for the backend. On the free hosting plan the server sleeps when idle and takes up to
// a minute to start, so for the first two minutes this is a calm "waking up" message with a slider; after that, a red error.
export const ServerBanner = ({ isOnline, loading, hasConnected, waitingSince, onRetry }) => {
  const waiting = !isOnline || (loading && !hasConnected);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [waiting]);

  if (!waiting) return null;
  const seconds = Math.max(0, Math.round((now - (waitingSince || now)) / 1000));

  if (seconds >= GIVE_UP_AFTER_S) {
    return (
      <div className="bg-rose-50 border border-rose-200 p-4 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-rose-900 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-rose-100 flex items-center justify-center text-rose-600 shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs sm:text-sm font-bold text-rose-950">Backend API Disconnected</div>
            <div className="text-xs text-rose-700 mt-0.5 leading-relaxed">
              No answer after {Math.floor(seconds / 60)} minutes. Check that the Render service shows Live, then press Retry.
            </div>
          </div>
        </div>
        <button
          onClick={onRetry}
          className="shrink-0 px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs transition-colors shadow-2xs cursor-pointer"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  return (
    <div className="bg-amber-50 border border-amber-200 p-4 rounded-2xl text-amber-950 shadow-xs space-y-3" role="status" aria-live="polite">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center text-amber-700 shrink-0">
          <Server className="w-5 h-5" />
        </div>
        <div className="min-w-0">
          <div className="text-xs sm:text-sm font-bold">{hasConnected ? 'Reconnecting to the server…' : 'Waking up the server…'}</div>
          <div className="text-xs text-amber-800 mt-0.5 leading-relaxed">
            The server runs on a free plan and sleeps when it is idle, so the first load can take up to a minute. This page fills in by
            itself when it is ready. Waiting {seconds} s.
          </div>
        </div>
      </div>
      <SliderLoader tone="amber" />
    </div>
  );
};
