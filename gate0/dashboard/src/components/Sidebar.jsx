import React from 'react';
import {
  PhoneCall,
  Users,
  CloudRain,
  Activity,
  Radio,
  X
} from 'lucide-react';

export const Sidebar = ({
  activeTab,
  setActiveTab,
  isOpen,
  setIsOpen,
  syncStatus,
  weatherAlertsCount = 0
}) => {
  const navItems = [
    {
      id: 'overview',
      label: 'Screen C01: Call Logs',
      sublabel: 'Overview & Telemetry',
      icon: PhoneCall,
      badge: 'Live',
    },
    {
      id: 'farmers',
      label: 'Farmer Directory',
      sublabel: 'Profiles & Languages',
      icon: Users,
    },
    {
      id: 'weather',
      label: 'Weather Advisories',
      sublabel: 'District Alerts & Rain',
      icon: CloudRain,
      badge: weatherAlertsCount > 0
        ? `${weatherAlertsCount} Alert${weatherAlertsCount > 1 ? 's' : ''}`
        : '0 Alerts',
      badgeColor: weatherAlertsCount > 0
        ? 'bg-amber-100 text-amber-800 border border-amber-200'
        : 'bg-slate-100 text-slate-500 border border-slate-200',
    },
  ];

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40 lg:hidden"
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-72 bg-white border-r border-slate-200/80 flex flex-col transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:z-auto ${isOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
      >
        {/* Brand Header with Agrythm Logo */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <img
              src="/agrythm-logo.png"
              alt="Agrythm Logo"
              className="w-10 h-10 object-contain rounded-xl p-0.5 bg-slate-50 border border-slate-200/80 shadow-xs"
            />
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-extrabold text-slate-900 text-base tracking-tight">
                  Agrythm Connect
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-50 text-trust-green border border-emerald-200">
                  v1.0
                </span>
              </div>
              <p className="text-[11px] font-bold tracking-wider text-slate-500 uppercase mt-0.5">
                Weather Reporter System
              </p>
            </div>
          </div>

          <button
            onClick={() => setIsOpen(false)}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Voice Agent Context Badge */}
        <div className="mx-4 mt-4 p-3 rounded-xl bg-slate-50 border border-slate-200/60 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Radio className="w-4 h-4 text-trust-green animate-pulse" />
            <div>
              <div className="text-xs font-bold text-slate-800">Weather Voice Agent</div>
              <div className="text-[10px] text-slate-500">Post-Call Monitoring</div>
            </div>
          </div>
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-trust-green">
            Active
          </span>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 p-3 space-y-1.5 overflow-y-auto mt-2">
          <div className="px-3 py-1.5 text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Navigation Menu
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-left transition-all duration-150 group cursor-pointer ${isActive
                  ? 'bg-trust-navy text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-700'
                      }`}
                  />
                  <div>
                    <div
                      className={`text-xs font-bold ${isActive ? 'text-white' : 'text-slate-800'
                        }`}
                    >
                      {item.label}
                    </div>
                    <div
                      className={`text-[10px] ${isActive ? 'text-slate-300' : 'text-slate-400'
                        }`}
                    >
                      {item.sublabel}
                    </div>
                  </div>
                </div>

                {item.badge && (
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isActive
                      ? 'bg-white/20 text-white'
                      : item.badgeColor || 'bg-emerald-50 text-trust-green border border-emerald-200'
                      }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Sidebar Footer System Status */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/50 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-600">
            <span className="flex items-center gap-1.5 text-[11px] font-medium">
              <span
                className={`w-2 h-2 rounded-full ${syncStatus === 'connected' ? 'bg-trust-green' : 'bg-amber-500 animate-pulse'
                  }`}
              />
              Google Sheets Sync
            </span>
            <span className="text-[10px] font-bold text-slate-500 capitalize">
              {syncStatus}
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span className="flex items-center gap-1">
              <Activity className="w-3 h-3 text-trust-navy" />
              Field-First Gateway
            </span>
            <span className="text-trust-green font-semibold">Nominal</span>
          </div>
        </div>
      </aside>
    </>
  );
};
