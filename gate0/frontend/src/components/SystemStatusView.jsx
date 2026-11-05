import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, XCircle, MinusCircle, AlertTriangle } from 'lucide-react';
import { getSystemChecks, getUsage } from '../utils';

const STATUS_STYLE = {
  ok: { icon: CheckCircle2, color: 'text-emerald-600', label: 'OK' },
  fail: { icon: XCircle, color: 'text-rose-600', label: 'Problem' },
  off: { icon: MinusCircle, color: 'text-slate-400', label: 'Not set up' },
};

const UsageCell = ({ title, data }) => (
  <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
    <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">{title}</div>
    <div className="text-2xl font-bold text-slate-900 mt-1">{data ? data.billed_minutes : '-'}</div>
    <div className="text-[11px] text-slate-500">
      billed minutes{data ? `, ${data.calls} calls (${data.connected} connected)` : ''}
    </div>
  </div>
);

// One simple page: is each part connected, and how much has been used. Reads /api/system/checks and /api/usage.
export const SystemStatusView = ({ isBackendOnline = true }) => {
  const [report, setReport] = useState(null);
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const [checks, use] = await Promise.all([getSystemChecks(refresh), getUsage(refresh)]);
      setReport(checks);
      setUsage(use);
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

  return (
    <div className="space-y-6">
      {/* Overall status */}
      <div className={`rounded-2xl border p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
        error || (report && !overallOk) ? 'bg-rose-50 border-rose-200' : 'bg-emerald-50/60 border-emerald-200'
      }`}>
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

      {/* The connections */}
      <div className="bg-white rounded-2xl border border-slate-200/80 divide-y divide-slate-100">
        {(report ? report.checks : []).map((c) => {
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

      {/* Usage from Sarvam's own call records */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-4">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Sarvam Usage</span>
          <h3 className="text-base font-bold text-slate-900">Calls and billed minutes</h3>
        </div>

        {usage && usage.exhausted && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>Sarvam has reported that credits are used up in the last 7 days. Add credits on Sarvam (Settings, Billing); calls resume at once.</span>
          </div>
        )}

        {usage && !usage.configured && (
          <p className="text-xs text-slate-500">Usage is read from Sarvam, so it is not available while the backend is in simulated mode.</p>
        )}
        {usage && usage.configured && usage.error && (
          <p className="text-xs text-rose-700">Could not read usage from Sarvam: {usage.error}</p>
        )}

        {usage && usage.window && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <UsageCell title="Today" data={usage.today} />
              <UsageCell title="Last 7 days" data={usage.week} />
              <UsageCell title={`Last ${usage.window_days} days`} data={usage.window} />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="py-2 pr-4">Day</th>
                    <th className="py-2 pr-4">Calls</th>
                    <th className="py-2 pr-4">Connected</th>
                    <th className="py-2">Billed minutes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {usage.days.map((d) => (
                    <tr key={d.date}>
                      <td className="py-2 pr-4 font-mono text-slate-700">{d.date}</td>
                      <td className="py-2 pr-4">{d.calls}</td>
                      <td className="py-2 pr-4">{d.connected}</td>
                      <td className="py-2 font-semibold text-slate-900">{d.billed_minutes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <p className="text-[11px] text-slate-500 leading-relaxed">
          {usage ? usage.note : 'Remaining credits are shown only on Sarvam, under Settings, Billing ("Credits Left").'}
        </p>
      </div>
    </div>
  );
};
