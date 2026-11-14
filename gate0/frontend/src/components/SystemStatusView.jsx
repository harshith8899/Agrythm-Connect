import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, XCircle, MinusCircle } from 'lucide-react';
import { getSystemChecks, getAlerts } from '../utils';

const STATUS_STYLE = {
  ok: { icon: CheckCircle2, color: 'text-emerald-600', label: 'OK' },
  fail: { icon: XCircle, color: 'text-rose-600', label: 'Problem' },
  off: { icon: MinusCircle, color: 'text-slate-400', label: 'Not active' },
};

// Is each part connected? Backend, database, wake-up timer, weather, Sarvam and the phone line, and what needs the team.
// Money lives on the Cost Analytics tab. Reads /api/system/checks and /api/alerts.
export const SystemStatusView = ({ isBackendOnline = true }) => {
  const [report, setReport] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const [checks, al] = await Promise.all([getSystemChecks(refresh), getAlerts().catch(() => [])]);
      setReport(checks);
      setAlerts(al);
      setError('');
    } catch (err) {
      setError(err.message || 'Could not reach the backend');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(false);
    const timer = setInterval(() => load(false), 60000);
    return () => clearInterval(timer);
  }, [load]);

  const overallOk = report && report.overall === 'ok';
  const okCount = report ? report.checks.filter((c) => c.status === 'ok').length : 0;
  const failCount = report ? report.checks.filter((c) => c.status === 'fail').length : 0;
  const offCount = report ? report.checks.filter((c) => c.status === 'off').length : 0;

  return (
    <div className="space-y-6">
      <div
        className={`rounded-2xl border p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
          error || (report && !overallOk) ? 'bg-rose-50 border-rose-200' : 'bg-emerald-50/60 border-emerald-200'
        }`}
      >
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">System Status</span>
          <h2 className="text-xl font-bold text-slate-900">
            {error ? 'Backend not reachable' : !report ? 'Checking...' : overallOk ? 'Everything is connected' : 'Something needs attention'}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {error || (report ? `Checked ${String(report.checked_at).replace('T', ' ').slice(0, 19)} (India time)` : '')}
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={loading || !isBackendOnline}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Check now</span>
        </button>
      </div>

      {alerts.length > 0 && (
        <div className="bg-white rounded-2xl border border-amber-200 divide-y divide-amber-100">
          <div className="p-4 text-[11px] font-bold tracking-wider text-amber-700 uppercase">Needs the team ({alerts.length})</div>
          {alerts.slice(0, 10).map((a, i) => (
            <div key={`${a.at}-${i}`} className="p-4 text-xs text-slate-700">
              <span className="font-semibold text-slate-900">{a.farmer_name || a.farmer_id || 'System'}</span>
              <span className="text-slate-400"> · {String(a.at).replace('T', ' ').slice(0, 16)}</span>
              <p className="mt-0.5">{a.text}</p>
            </div>
          ))}
        </div>
      )}

      {report && (
        <div className="bg-white rounded-2xl border border-slate-200/80">
          <div className="flex flex-wrap items-center gap-3 p-4 border-b border-slate-100">
            <span className="text-sm font-bold text-slate-900">Connections</span>
            <span className={`text-xs font-semibold ${failCount > 0 ? 'text-rose-600' : offCount > 0 ? 'text-slate-500' : 'text-emerald-600'}`}>
              {okCount} of {report.checks.length} OK
              {failCount > 0 && `, ${failCount} with a problem`}
              {offCount > 0 && `, ${offCount} not set up`}
            </span>
          </div>
          <div className="divide-y divide-slate-100">
            {report.checks.map((c) => {
              const style = STATUS_STYLE[c.status] || STATUS_STYLE.off;
              const Icon = style.icon;
              return (
                <div key={c.id} className="flex items-start gap-3 p-4">
                  <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${style.color}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-900">{c.name}</span>
                      <span className={`text-[10px] font-bold uppercase ${style.color}`}>{style.label}</span>
                      {c.ms != null && <span className="text-[10px] text-slate-400">{c.ms} ms</span>}
                    </div>
                    <p className="text-xs text-slate-600 mt-0.5 break-words">{c.detail}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
