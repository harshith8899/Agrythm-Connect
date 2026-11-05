import React from 'react';
import { Menu, RefreshCw, Play, Clock, CheckCircle2, AlertCircle } from 'lucide-react';

export const Header = ({ 
  onToggleSidebar, 
  onRefresh, 
  refreshing, 
  syncStatus, 
  isBackendOnline = true,
  activeTab,
  onTriggerDemo,
  triggeringDemo,
  autoDispatcher,
  onToggleAutoDispatcher
}) => {
  const getTabTitle = () => {
    switch (activeTab) {
      case 'farmers':
        return 'Farmer Profiles Directory';
      case 'weather':
        return 'District Weather Advisories & Alerts';
      case 'overview':
      default:
        return 'Screen C01: Agrythm Connect Call Overview';
    }
  };

  const isAutoEnabled = autoDispatcher?.enabled ?? false;
  const isLive = Boolean(autoDispatcher?.live);

  return (
    <header className="w-full bg-white border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 py-3 sticky top-0 z-30 shadow-2xs">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Left: Mobile Toggle & Active Title */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="lg:hidden p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            aria-label="Toggle Navigation Menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <img
            src="/agrythm-logo.png"
            alt="Agrythm Logo"
            className="w-8 h-8 object-contain rounded-lg p-0.5 bg-slate-50 border border-slate-200/80 shadow-2xs lg:hidden"
          />

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-bold text-slate-900 leading-tight">
                {getTabTitle()}
              </h1>
              {isBackendOnline ? (
                <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-semibold bg-emerald-50 text-trust-green px-2 py-0.5 rounded-full border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-trust-green animate-pulse" />
                  Live Sync
                </span>
              ) : (
                <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-bold bg-rose-50 text-rose-700 px-2 py-0.5 rounded-full border border-rose-200 shadow-2xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-600 animate-ping" />
                  Backend Offline
                </span>
              )}
            </div>
            <p className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
              Agrythm Connect • Weather Voice Agent System
            </p>
          </div>
        </div>

        {/* Right: Triggers, Controls & Status */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Auto Dispatcher (9:00 AM) Indicator / Toggle */}
          <button
            onClick={onToggleAutoDispatcher}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer ${
              isAutoEnabled 
                ? 'bg-emerald-50/80 border-emerald-200 text-emerald-800 hover:bg-emerald-100' 
                : 'bg-slate-100 border-slate-200 text-slate-600 hover:bg-slate-200'
            }`}
            title="Toggle Automated 9:00 AM IST Daily Dispatcher"
          >
            <Clock className={`w-3.5 h-3.5 ${isAutoEnabled ? 'text-emerald-600' : 'text-slate-400'}`} />
            <span className="hidden md:inline">Auto Dispatcher (9:00 AM):</span>
            <span className="md:hidden">Auto:</span>
            <span className={`inline-flex items-center gap-1 font-bold ${isAutoEnabled ? 'text-emerald-700' : 'text-slate-500'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${isAutoEnabled ? 'bg-emerald-600 animate-pulse' : 'bg-slate-400'}`} />
              {isAutoEnabled ? 'Active' : 'Paused'}
            </span>
          </button>

          {/* Start Demo Button */}
          <button
            onClick={onTriggerDemo}
            disabled={triggeringDemo || !isBackendOnline}
            className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shadow-xs cursor-pointer active:scale-95 ${
              !isBackendOnline
                ? 'bg-slate-300 text-slate-500 cursor-not-allowed opacity-60'
                : 'bg-trust-navy hover:bg-slate-800 text-white disabled:opacity-50'
            }`}
            title={
              !isBackendOnline
                ? "The backend API is offline. Start it with 'npm run backend'."
                : isLive
                  ? "Send today's calls now to every eligible farmer (real calls)"
                  : "Send today's calls now (simulated: no real calls are placed)"
            }
          >
            {triggeringDemo ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-white" />
                <span>Sending...</span>
              </>
            ) : (
              <>
                <Play className={`w-3.5 h-3.5 fill-current ${isBackendOnline ? 'text-emerald-400' : 'text-slate-400'}`} />
                <span>Send now{isLive ? '' : ' (simulated)'}</span>
              </>
            )}
          </button>

          {/* Cloud Sync Status Badge */}
          <div className={`hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs ${
            isBackendOnline
              ? 'bg-emerald-50/80 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-700'
          }`}>
            <span
              className={`w-2 h-2 rounded-full ${
                isBackendOnline ? 'bg-trust-green animate-pulse' : 'bg-rose-600 animate-ping'
              }`}
            />
            <span className="font-semibold">
              {isBackendOnline ? 'Connected (Port 8000)' : 'Backend Offline (Port 8000)'}
            </span>
          </div>

          {/* Quick Refresh */}
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
            title="Refresh live data from the backend"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-trust-navy' : ''}`} />
            <span className="hidden xl:inline">{refreshing ? 'Syncing...' : 'Refresh'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
