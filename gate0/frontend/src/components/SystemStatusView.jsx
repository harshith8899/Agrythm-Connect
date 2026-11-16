import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, XCircle, MinusCircle } from 'lucide-react';
import { getSystemChecks, getAlerts } from '../utils';
import { CostAnalyticsView } from './CostAnalyticsView';

const STATUS_STYLE = {
  ok: { icon: CheckCircle2, color: 'text-emerald-600', label: 'OK' },
  fail: { icon: XCircle, color: 'text-rose-600', label: 'Problem' },
  off: { icon: MinusCircle, color: 'text-slate-400', label: 'Not active' },
};

/**
 * Unified System & Telephony View:
 * Merges compact system connectivity status, alerts, and the full CostAnalyticsView.
 */
export const SystemStatusView = ({ isBackendOnline = true, callLogs = [] }) => {
  const [systemReport, setSystemReport] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [systemError, setSystemError] = useState('');
  const [systemLoading, setSystemLoading] = useState(false);

  const loadSystem = useCallback(async (refresh = false) => {
    setSystemLoading(true);
    try {
      const [checks, al] = await Promise.all([getSystemChecks(refresh), getAlerts().catch(() => [])]);
      setSystemReport(checks);
      setAlerts(al);
      setSystemError('');
    } catch (err) {
      setSystemError(err.message || 'Could not reach the backend');
    } finally {
      setSystemLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSystem(false);
    const timer = setInterval(() => loadSystem(false), 60000);
    return () => clearInterval(timer);
  }, [loadSystem]);

  const overallOk = systemReport && systemReport.overall === 'ok';
  const okCount = systemReport ? systemReport.checks.filter((c) => c.status === 'ok').length : 0;
  const failCount = systemReport ? systemReport.checks.filter((c) => c.status === 'fail').length : 0;
  const offCount = systemReport ? systemReport.checks.filter((c) => c.status === 'off').length : 0;

  return (
    <div className="space-y-4">
      {/* 1. Compact System & Telephony Health Status */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-4 shadow-2xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">System & Telephony Status</span>
              {overallOk ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-emerald-50 text-trust-green px-2 py-0.5 rounded-full border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-trust-green animate-pulse" />
                  All Systems Operational
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full border border-amber-200">
                  Attention Needed
                </span>
              )}
            </div>
            <h2 className="text-xl font-bold text-slate-900 mt-0.5">
              {systemError ? 'Backend Unreachable' : !systemReport ? 'Checking connections...' : overallOk ? 'Core Telephony & Weather Services Connected' : 'Configuration Attention Needed'}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {systemReport ? `Last checked ${String(systemReport.checked_at).replace('T', ' ').slice(0, 19)} (IST) · ${okCount} of ${systemReport.checks.length} OK` : ''}
              {failCount > 0 ? `, ${failCount} issues` : ''}
              {offCount > 0 ? `, ${offCount} inactive` : ''}
            </p>
          </div>
          <button
            onClick={() => loadSystem(true)}
            disabled={systemLoading || !isBackendOnline}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${systemLoading ? 'animate-spin' : ''}`} />
            <span>Check Connections</span>
          </button>
        </div>

        {/* Alerts if any */}
        {alerts.length > 0 && (
          <div className="bg-amber-50/70 rounded-xl border border-amber-200 divide-y divide-amber-100">
            <div className="p-3 text-[11px] font-bold tracking-wider text-amber-800 uppercase">
              Needs Attention ({alerts.length})
            </div>
            {alerts.slice(0, 5).map((a, i) => (
              <div key={`${a.at}-${i}`} className="p-3 text-xs text-slate-700">
                <span className="font-semibold text-slate-900">{a.farmer_name || a.farmer_id || 'System'}</span>
                <span className="text-slate-400"> · {String(a.at).replace('T', ' ').slice(0, 16)}</span>
                <p className="mt-0.5">{a.text}</p>
              </div>
            ))}
          </div>
        )}

        {/* Compact Connections Grid */}
        {systemReport && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {systemReport.checks.map((c) => {
              const style = STATUS_STYLE[c.status] || STATUS_STYLE.off;
              const Icon = style.icon;
              return (
                <div key={c.id} className="flex items-start justify-between p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs">
                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                    <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${style.color}`} />
                    <div className="min-w-0 flex-1 break-words leading-snug">
                      <span className="font-bold text-slate-800 block text-xs">{c.name}</span>
                      <span className="text-[10px] text-slate-500 block break-words mt-0.5" title={c.detail}>
                        {c.detail}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-2 self-start pt-0.5">
                    <span className={`text-[10px] font-bold uppercase ${style.color}`}>{style.label}</span>
                    {c.ms != null && <span className="text-[9px] text-slate-400 block">{c.ms}ms</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 2. Consolidated Telephony & Voice AI Cost Analytics Suite */}
      <CostAnalyticsView isBackendOnline={isBackendOnline} callLogs={callLogs} />
    </div>
  );
};

export default SystemStatusView;
