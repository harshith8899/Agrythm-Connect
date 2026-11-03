import React from 'react';
import { Menu, RefreshCw, Play, Clock, CheckCircle2, AlertCircle } from 'lucide-react';

export const Header = ({ 
  onToggleSidebar, 
  onRefresh, 
  refreshing, 
  syncStatus, 
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
      case 'trust_ai':
        return 'Trust AI Verification & Model Integrity';
      case 'sync':
        return 'Google Sheets Sync & Setup';
      case 'overview':
      default:
        return 'Screen C01: Agrythm Connect Call Overview';
    }
  };

  const isAutoEnabled = autoDispatcher?.enabled ?? true;

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
              <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-semibold bg-emerald-50 text-trust-green px-2 py-0.5 rounded-full border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-trust-green animate-pulse" />
                Live Sync
              </span>
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
            disabled={triggeringDemo}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-trust-navy hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs disabled:opacity-50 cursor-pointer active:scale-95"
            title="Execute immediate manual batch run across test numbers"
          >
            {triggeringDemo ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-white" />
                <span>Running Demo...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current text-emerald-400" />
                <span>Start Demo</span>
              </>
            )}
          </button>

          {/* Cloud Sync Status Badge */}
          <div className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-600">
            <span
              className={`w-2 h-2 rounded-full ${
                syncStatus === 'connected' ? 'bg-trust-green animate-pulse' : 'bg-amber-500'
              }`}
            />
            <span className="font-medium text-slate-700">
              {syncStatus === 'connected' ? 'Connected (SQLite + Sheets)' : 'Syncing...'}
            </span>
          </div>

          {/* Quick Refresh */}
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
            title="Refresh Live Data from SQLite & Google Sheets"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-trust-navy' : ''}`} />
            <span className="hidden xl:inline">{refreshing ? 'Syncing...' : 'Refresh'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
