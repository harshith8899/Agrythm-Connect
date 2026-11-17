import React, { useCallback, useEffect, useState } from 'react';
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Server,
  Database,
  CloudSun,
  Cpu,
  PhoneCall,
  Clock,
  Activity,
  Zap,
  Mail,
  X,
} from 'lucide-react';
import { getSystemChecks, getAlerts, getMessages, dismissAlerts, dismissMessages, sendTestEmail } from '../utils';

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
  ok: {
    icon: CheckCircle2,
    badgeBg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dotBg: 'bg-emerald-500',
    label: 'Operational',
  },
  fail: {
    icon: XCircle,
    badgeBg: 'bg-rose-50 text-rose-700 border-rose-200',
    dotBg: 'bg-rose-500',
    label: 'Attention Needed',
  },
  off: {
    icon: MinusCircle,
    badgeBg: 'bg-slate-100 text-slate-600 border-slate-200',
    dotBg: 'bg-slate-400',
    label: 'Inactive / Standby',
  },
};

const SERVICE_META = {
  backend: {
    icon: Server,
    category: 'Core API Server',
    description: 'HTTP REST API daemon handling authentication, farmer management, and call dispatching.',
  },
  database: {
    icon: Database,
    category: 'Persistent Storage',
    description: 'Relational data store caching farmer records, call execution logs, and weather forecasts.',
  },
  weather: {
    icon: CloudSun,
    category: 'Forecast Provider',
    description: 'High-resolution meteorological API providing localized temperature, wind, rain, and humidity data.',
  },
  sarvam: {
    icon: Cpu,
    category: 'Voice AI Intelligence',
    description: 'Conversational Kannada & Hindi voice agent engine powering automated farmer dialogue.',
  },
  phone: {
    icon: PhoneCall,
    category: 'Telephony & Outbound DID',
    description: 'Direct Inward Dialing (DID) carrier line providing live PSTN connectivity for farmer calls.',
  },
  email: {
    icon: Mail,
    category: 'Email delivery',
    description: 'Sends the weather email after a call; the test button sends a sample to the test address.',
  },
  timer: {
    icon: Clock,
    category: 'Cron / Wake-up Trigger',
    description: 'Automated background scheduler managing scheduled morning agricultural broadcasts.',
  },
};

/**
 * System Status View:
 * Full-width, vertically stacked infrastructure & service health monitoring covering the entire page.
 */
export const SystemStatusView = ({ isBackendOnline = true }) => {
  const [systemReport, setSystemReport] = useState(null);
  const [systemError, setSystemError] = useState('');
  const [systemLoading, setSystemLoading] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [messages, setMessages] = useState([]);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

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

  // sends one sample email to the test address and shows what happened, so the mail setup can be checked without a call
  const handleTestEmail = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await sendTestEmail();
      setTestResult({ ok: r.status === 'sent', text: r.status === 'sent' ? 'Sent: check the test inbox.' : `${r.status}: ${r.note}` });
      loadSystem(false);
    } catch (err) {
      setTestResult({ ok: false, text: err.message });
    } finally {
      setTesting(false);
    }
  };

  // remove one email log row, or all of them
  const handleDismissMessage = async (key) => {
    setMessages((prev) => (key == null ? [] : prev.filter((m) => m.key !== key)));
    try {
      await dismissMessages(key);
    } catch {
      loadSystem(false);
    }
  };

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

  const checks = systemReport?.checks || [];
  const overallOk = systemReport && systemReport.overall === 'ok';
  const okCount = checks.filter((c) => c.status === 'ok').length;
  const failCount = checks.filter((c) => c.status === 'fail').length;
  const offCount = checks.filter((c) => c.status === 'off').length;

  const latencies = checks.map((c) => c.ms).filter((ms) => typeof ms === 'number');
  const avgLatency = latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : null;

  return (
    <div className="space-y-6 w-full">
      {/* 1. Header & Overview Hero Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 sm:p-6 shadow-2xs">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">System Infrastructure</span>
              {overallOk ? (
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold bg-emerald-50 text-trust-green px-2.5 py-0.5 rounded-full border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-trust-green animate-pulse" />
                  All Core Systems Operational
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold bg-amber-50 text-amber-700 px-2.5 py-0.5 rounded-full border border-amber-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                  Configuration Attention Needed
                </span>
              )}
            </div>
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900 mt-1">
              {systemError
                ? 'Backend API Unreachable'
                : !systemReport
                ? 'Connecting to Services...'
                : overallOk
                ? 'Telephony, Database & Cloud Infrastructure Health'
                : 'Service Health & Connectivity Telemetry'}
            </h1>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Real-time health telemetry across API daemons, SQLite/PostgreSQL storage, Open-Meteo weather APIs, and Sarvam Voice AI carrier links.
              {systemReport && (
                <span className="ml-1 text-slate-400">
                  (Auto-refreshes every 60s · Last poll: {String(systemReport.checked_at).replace('T', ' ').slice(0, 19)} IST)
                </span>
              )}
            </p>
          </div>

          <div className="flex items-center gap-2.5 self-start lg:self-auto shrink-0">
            <button
              onClick={() => loadSystem(true)}
              disabled={systemLoading || !isBackendOnline}
              className="h-9 px-3.5 rounded-xl justify-center whitespace-nowrap inline-flex items-center gap-2 bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50 shadow-2xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${systemLoading ? 'animate-spin' : ''}`} />
              <span>{systemLoading ? 'Checking...' : 'Run Diagnostics'}</span>
            </button>
          </div>
        </div>

        {/* Top 4 KPI Metrics Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-1">
          <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-100 flex flex-col justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Services</span>
            <div className="text-xl font-bold text-slate-900 mt-1">{checks.length || '—'}</div>
            <span className="text-[11px] text-slate-500 mt-0.5">Monitored daemons</span>
          </div>

          <div className="p-3.5 rounded-xl bg-emerald-50/50 border border-emerald-100 flex flex-col justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">Operational</span>
            <div className="text-xl font-bold text-trust-green mt-1">{okCount}</div>
            <span className="text-[11px] text-emerald-600 mt-0.5">Healthy & connected</span>
          </div>

          {failCount > 0 ? (
            <div className="p-3.5 rounded-xl bg-rose-50/50 border border-rose-100 flex flex-col justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-rose-700">Attention Needed</span>
              <div className="text-xl font-bold text-rose-600 mt-1">{failCount}</div>
              <span className="text-[11px] text-rose-600 mt-0.5">Issues detected</span>
            </div>
          ) : (
            <div className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-100 flex flex-col justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Standby / Inactive</span>
              <div className="text-xl font-bold text-slate-700 mt-1">{offCount}</div>
              <span className="text-[11px] text-slate-500 mt-0.5">Simulated / idle</span>
            </div>
          )}

          <div className="p-3.5 rounded-xl bg-sky-50/50 border border-sky-100 flex flex-col justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-sky-800">Avg Roundtrip</span>
            <div className="text-xl font-bold text-sky-900 mt-1">
              {avgLatency !== null ? `${avgLatency} ms` : '< 2 ms'}
            </div>
            <span className="text-[11px] text-sky-700 mt-0.5">Internal service ping</span>
          </div>
        </div>
      </div>

      {/* Needs attention and the emails sent after calls */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-4 shadow-2xs">
        {/* Alerts if any */}
        {alerts.length > 0 && (
          <div className="bg-amber-50/70 rounded-xl border border-amber-200">
            <div className="p-3 flex items-center justify-between gap-2 border-b border-amber-100">
              <span className="text-[11px] font-bold tracking-wider text-amber-800 uppercase">Needs Attention ({alerts.length})</span>
              <button
                onClick={() => handleDismiss(null)}
                className="h-8 px-3 rounded-lg inline-flex items-center justify-center whitespace-nowrap bg-white border border-amber-200 text-[11px] font-semibold text-amber-800 hover:bg-amber-100 transition-colors cursor-pointer"
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
          <div className="p-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100">
            <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Emails after calls ({messages.length})</span>
            <span className="flex items-center gap-2">
              {testResult && (
                <span className={`text-[11px] font-semibold break-words ${testResult.ok ? 'text-emerald-700' : 'text-rose-700'}`}>{testResult.text}</span>
              )}
              {messages.length > 0 && (
                <button
                  onClick={() => handleDismissMessage(null)}
                  className="h-8 px-3 rounded-lg inline-flex items-center justify-center whitespace-nowrap text-[11px] font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer"
                >
                  Clear all
                </button>
              )}
              <button
                onClick={handleTestEmail}
                disabled={testing || !isBackendOnline}
                className="h-8 px-3 rounded-lg inline-flex items-center justify-center whitespace-nowrap bg-white border border-slate-200 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
              >
                {testing ? 'Sending...' : 'Send test email'}
              </button>
            </span>
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
                    <th className="px-3 py-2 w-8"><span className="sr-only">Remove</span></th>
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
                        <td className="px-3 py-2 text-right">
                          {m.key && (
                            <button
                              onClick={() => handleDismissMessage(m.key)}
                              title="Remove this row"
                              aria-label="Remove this row"
                              className="p-1 rounded-md text-slate-400 hover:text-rose-600 hover:bg-slate-50 transition-colors cursor-pointer"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>

      {/* 2. Full-Width Vertically Stacked Service Blocks (Placed Each Below the Other) */}
      <div className="space-y-3.5 w-full">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Monitored Service Components ({checks.length})
          </h2>
          <span className="text-[11px] text-slate-400">Full-stack health matrix</span>
        </div>

        {systemError ? (
          <div className="p-6 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs shadow-2xs">
            <div className="flex items-center gap-2 font-bold text-sm">
              <XCircle className="w-5 h-5 text-rose-600 shrink-0" />
              <span>Cannot connect to local backend API</span>
            </div>
            <p className="mt-1 text-slate-600">{systemError}</p>
          </div>
        ) : checks.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400 bg-white rounded-2xl border border-slate-200/80 shadow-2xs">
            Initializing diagnostic probes...
          </div>
        ) : (
          checks.map((c) => {
            const meta = SERVICE_META[c.id] || {
              icon: Zap,
              category: 'System Service',
              description: 'Background operational module.',
            };
            const Icon = meta.icon;
            const style = STATUS_STYLE[c.status] || STATUS_STYLE.off;
            const StatusIcon = style.icon;

            return (
              <div
                key={c.id}
                className="w-full bg-white rounded-2xl border border-slate-200/80 p-5 shadow-2xs hover:border-slate-300 hover:shadow-xs transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                {/* Left Side: Service Icon & Technical Description */}
                <div className="flex items-start gap-4 min-w-0 flex-1">
                  <div
                    className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 border ${
                      c.status === 'ok'
                        ? 'bg-emerald-50 border-emerald-200 text-trust-green'
                        : c.status === 'fail'
                        ? 'bg-rose-50 border-rose-200 text-rose-600'
                        : 'bg-slate-100 border-slate-200 text-slate-600'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-bold text-slate-900 text-sm">{c.name}</h3>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 uppercase tracking-wide">
                        {meta.category}
                      </span>
                    </div>

                    <p className="text-xs text-slate-700 font-medium mt-1 break-words leading-relaxed">
                      {c.detail}
                    </p>

                    <p className="text-[11px] text-slate-400 mt-1 break-words">
                      {meta.description}
                    </p>
                  </div>
                </div>

                {/* Right Side: Status Badge & Latency Telemetry */}
                <div className="flex sm:flex-row md:flex-col items-center md:items-end justify-between md:justify-center gap-2 shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-slate-100">
                  <div
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-bold ${style.badgeBg}`}
                  >
                    <span className={`w-2 h-2 rounded-full ${style.dotBg} ${c.status === 'ok' ? 'animate-pulse' : ''}`} />
                    <StatusIcon className="w-3.5 h-3.5" />
                    <span>{style.label}</span>
                  </div>

                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
                    {c.ms != null ? (
                      <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-700 px-2 py-0.5 rounded-md font-semibold">
                        <Activity className="w-3 h-3 text-slate-500" />
                        {c.ms} ms latency
                      </span>
                    ) : (
                      <span className="text-slate-400 text-[10px]">Zero overhead</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default SystemStatusView;
