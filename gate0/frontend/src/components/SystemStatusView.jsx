import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, XCircle, MinusCircle, X } from 'lucide-react';
import { getSystemChecks, getAlerts, getMessages, dismissAlerts } from '../utils';
import { CostAnalyticsView } from './CostAnalyticsView';

const MESSAGE_LABEL = {
  weather: 'Weather update',
  missed: 'We tried to call you',
  callback_weather: 'Weather after the requested call',
  callback_missed: 'Missed the requested call',
};
const MESSAGE_STATUS_STYLE = {
  sent: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  skipped: 'bg-amber-50 text-amber-700 border-amber-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  sending: 'bg-slate-50 text-slate-600 border-slate-200',
};
// a test call's key looks like "test:weather:ab12cd34": show the situation, tagged Test
const describeMessage = (kind) => {
  const isTest = String(kind).startsWith('test:');
  const base = isTest ? String(kind).split(':')[1] : kind;
  return { label: MESSAGE_LABEL[base] || base, isTest };
};

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
  const [messages, setMessages] = useState([]);
  const [systemError, setSystemError] = useState('');
  const [systemLoading, setSystemLoading] = useState(false);

  const loadSystem = useCallback(async (refresh = false) => {
    setSystemLoading(true);
    try {
      const [checks, al, msgs] = await Promise.all([getSystemChecks(refresh), getAlerts().catch(() => []), getMessages().catch(() => [])]);
      setSystemReport(checks);
      setAlerts(al);
      setMessages(Array.isArray(msgs) ? msgs : []);
      setSystemError('');
    } catch (err) {
      setSystemError(err.message || 'Could not reach the backend');
    } finally {
      setSystemLoading(false);
    }
  }, []);

  // remove one note, or all of them; the list is updated at once and the server confirms in the background
  const handleDismiss = async (id) => {
    setAlerts((prev) => (id == null ? [] : prev.filter((a) => a.id !== id)));
    try {
      await dismissAlerts(id);
    } catch {
      loadSystem(false);        // it did not go through: show what is really there
    }
  };

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
          <div className="bg-amber-50/70 rounded-xl border border-amber-200">
            <div className="p-3 flex items-center justify-between gap-2 border-b border-amber-100">
              <span className="text-[11px] font-bold tracking-wider text-amber-800 uppercase">Needs Attention ({alerts.length})</span>
              <button
                onClick={() => handleDismiss(null)}
                className="px-2.5 py-1 rounded-lg bg-white border border-amber-200 text-[11px] font-semibold text-amber-800 hover:bg-amber-100 transition-colors cursor-pointer"
              >
                Clear all
              </button>
            </div>
            <div className="max-h-72 overflow-y-auto divide-y divide-amber-100">
              {alerts.map((a, i) => (
                <div key={`${a.id ?? a.at}-${i}`} className="p-3 text-xs text-slate-700 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <span className="font-semibold text-slate-900">{a.farmer_name || a.farmer_id || 'System'}</span>
                    <span className="text-slate-400"> · {String(a.at).replace('T', ' ').slice(0, 16)}</span>
                    <p className="mt-0.5 break-words">{a.text}</p>
                  </div>
                  {a.id != null && (
                    <button
                      onClick={() => handleDismiss(a.id)}
                      title="Dismiss this note"
                      aria-label="Dismiss this note"
                      className="shrink-0 p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-white transition-colors cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Emails sent after calls */}
        <div className="rounded-xl border border-slate-100">
          <div className="p-3 text-[11px] font-bold tracking-wider text-slate-500 uppercase border-b border-slate-100">
            Emails after calls ({messages.length})
          </div>
          {messages.length === 0 ? (
            <p className="p-3 text-xs text-slate-500">
              None yet. An email goes out after a call where the farmer understood the weather, after the last unanswered attempt, and after a
              callback that was missed. A test call sends one only when a test address is set on the server.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400">
                    <th className="px-3 py-2">When</th>
                    <th className="px-3 py-2">Farmer</th>
                    <th className="px-3 py-2">Email</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Why</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {messages.slice(0, 15).map((m, i) => {
                    const d = describeMessage(m.kind);
                    return (
                      <tr key={`${m.at}-${m.kind}-${i}`}>
                        <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{String(m.at).replace('T', ' ').slice(0, 16)}</td>
                        <td className="px-3 py-2 font-medium text-slate-800">{m.farmer_name || m.farmer_id}</td>
                        <td className="px-3 py-2 text-slate-700">
                          {d.label}
                          {d.isTest && <span className="ml-1.5 text-[10px] font-semibold text-slate-400 uppercase">Test</span>}
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-block px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase ${MESSAGE_STATUS_STYLE[m.status] || MESSAGE_STATUS_STYLE.sending}`}>
                            {m.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-500">{m.note || ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

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
