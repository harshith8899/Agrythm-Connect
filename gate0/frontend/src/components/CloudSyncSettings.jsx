import React, { useState } from 'react';
import { 
  ExternalLink, 
  RefreshCw, 
  Save, 
  Check, 
  Copy, 
  Download 
} from 'lucide-react';
import { GOOGLE_SHEETS_CONFIG } from '../utils/constants';
import { GOOGLE_APPS_SCRIPT_SAMPLE } from '../utils/googleSheets';
import Papa from 'papaparse';

export const CloudSyncSettings = ({
  syncStatus,
  lastSynced,
  refreshing,
  onRefresh,
  autoPollInterval,
  setAutoPollInterval,
  appsScriptUrl,
  onSaveAppsScriptUrl,
  callLogs,
}) => {
  const [scriptUrlInput, setScriptUrlInput] = useState(appsScriptUrl || '');
  const [copied, setCopied] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSaveUrl = (e) => {
    e.preventDefault();
    onSaveAppsScriptUrl(scriptUrlInput);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2500);
  };

  const copyScript = () => {
    navigator.clipboard.writeText(GOOGLE_APPS_SCRIPT_SAMPLE);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExportCSV = () => {
    const csv = Papa.unparse(callLogs);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `agrythm_call_execution_logs_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Cloud Integration
          </span>
          <h2 className="text-xl font-bold text-slate-900">
            Google Sheets Live Sync & Web App Setup
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Status: <strong className="text-trust-green font-semibold capitalize">{syncStatus}</strong>
            {lastSynced && ` • Last refreshed at ${lastSynced.toLocaleTimeString()}`}
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-bold hover:bg-slate-800 transition-colors shadow-2xs disabled:opacity-60"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span>{refreshing ? 'Syncing Feeds...' : 'Sync & Fetch Now'}</span>
        </button>
      </div>

      {/* Connected Google Sheets Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Sheet 1: Farmers */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Sheet 1 • Farmer Profiles
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-trust-green border border-emerald-200">
              Live Connected
            </span>
          </div>

          <h3 className="text-base font-bold text-slate-900">
            Agrythm Connect — Gate Zero Master
          </h3>
          <p className="text-xs text-slate-500 font-mono break-all bg-slate-50 p-2 rounded-lg border border-slate-100">
            {GOOGLE_SHEETS_CONFIG.farmersCsvUrl}
          </p>

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-slate-500">Columns: ID, Name, Phone, Language, District, Village</span>
            <a
              href={`https://docs.google.com/spreadsheets/d/${GOOGLE_SHEETS_CONFIG.farmersSheetId}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-trust-navy hover:underline font-semibold"
            >
              <span>Open Sheet</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>

        {/* Sheet 2: Call Execution Logs */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Sheet 2 • Call Execution Logs
            </span>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-trust-green border border-emerald-200">
              Live Connected
            </span>
          </div>

          <h3 className="text-base font-bold text-slate-900">
            Weather Voice Agent Call Logs
          </h3>
          <p className="text-xs text-slate-500 font-mono break-all bg-slate-50 p-2 rounded-lg border border-slate-100">
            {GOOGLE_SHEETS_CONFIG.callLogsCsvUrl}
          </p>

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-slate-500">Columns: Call ID, Farmer ID, Timestamp, Weather, Status, Notes</span>
            <a
              href={`https://docs.google.com/spreadsheets/d/${GOOGLE_SHEETS_CONFIG.callLogsSheetId}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-trust-navy hover:underline font-semibold"
            >
              <span>Open Sheet</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>

      {/* Sync Preferences & Writeback Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Polling & Writeback Setup */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 md:p-6 space-y-5">
          <div>
            <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
              Bidirectional Sync
            </span>
            <h3 className="text-base font-bold text-slate-900 mt-0.5">
              Automatic Polling & Google Apps Script Webhook
            </h3>
          </div>

          {/* Polling Interval */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Live Polling Interval (Background Refresh)
            </label>
            <div className="flex gap-2">
              {[
                { val: 0, label: 'Manual Only' },
                { val: 10, label: 'Every 10s' },
                { val: 15, label: 'Every 15s (Default)' },
                { val: 30, label: 'Every 30s' },
              ].map((p) => (
                <button
                  key={p.val}
                  type="button"
                  onClick={() => setAutoPollInterval(p.val)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    autoPollInterval === p.val
                      ? 'bg-trust-navy text-white border-trust-navy shadow-xs'
                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Apps Script Endpoint URL Form */}
          <form onSubmit={handleSaveUrl} className="space-y-3 pt-2 border-t border-slate-100">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Google Apps Script Web App URL (Optional for Direct Writes)
              </label>
              <p className="text-[11px] text-slate-500 mb-2">
                Deploy the script below in your Google Sheet (Extensions &gt; Apps Script &gt; Deploy as Web App) to enable instant saving from the dashboard directly into your sheet.
              </p>
              <input
                type="url"
                value={scriptUrlInput}
                onChange={(e) => setScriptUrlInput(e.target.value)}
                placeholder="https://script.google.com/macros/s/.../exec"
                className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-hidden focus:bg-white focus:border-trust-navy"
              />
            </div>

            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">
                {saveSuccess ? (
                  <span className="text-trust-green font-bold flex items-center gap-1">
                    <Check className="w-3.5 h-3.5" />
                    Web App URL saved locally
                  </span>
                ) : (
                  <span>Stored securely in browser localStorage</span>
                )}
              </span>

              <button
                type="submit"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-green text-white text-xs font-bold hover:bg-emerald-800 transition-colors"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Save Webhook</span>
              </button>
            </div>
          </form>

          {/* Export CSV action */}
          <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-800">Export Call Logs</div>
              <div className="text-[11px] text-slate-500">Download current session records as standard CSV</div>
            </div>
            <button
              onClick={handleExportCSV}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {/* Copy-pasteable Google Apps Script Template */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 md:p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
                Copy-Paste Template
              </span>
              <h3 className="text-base font-bold text-slate-900 mt-0.5">
                Google Apps Script Code
              </h3>
            </div>

            <button
              onClick={copyScript}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-trust-green" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied!' : 'Copy Code'}</span>
            </button>
          </div>

          <p className="text-xs text-slate-600 leading-relaxed">
            In your Google Sheet, go to <strong>Extensions &gt; Apps Script</strong>, paste the code below, and click <strong>Deploy &gt; New deployment &gt; Web app</strong> (Execute as: <em>Me</em>, Who has access: <em>Anyone</em>).
          </p>

          <pre className="p-3.5 rounded-xl bg-slate-900 text-slate-200 font-mono text-[11px] overflow-x-auto max-h-[300px] leading-relaxed">
            {GOOGLE_APPS_SCRIPT_SAMPLE}
          </pre>
        </div>
      </div>
    </div>
  );
};
