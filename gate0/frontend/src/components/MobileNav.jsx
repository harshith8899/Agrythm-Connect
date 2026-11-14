import React from 'react';
import { PhoneCall, Users, ShieldCheck, IndianRupee } from 'lucide-react';

const TABS = [
  { id: 'overview', label: 'Calls', icon: PhoneCall },
  { id: 'farmers', label: 'Farmers', icon: Users },
  { id: 'cost', label: 'Cost', icon: IndianRupee },
  { id: 'system', label: 'System', icon: ShieldCheck },
];

// Phones: the pages as a bar at the bottom, within thumb reach. The sidebar is for larger screens.
export const MobileNav = ({ activeTab, setActiveTab }) => (
  <nav
    className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur border-t border-slate-200 grid grid-cols-4"
    style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    aria-label="Main navigation"
  >
    {TABS.map(({ id, label, icon: Icon }) => {
      const active = activeTab === id;
      return (
        <button
          key={id}
          type="button"
          onClick={() => setActiveTab(id)}
          aria-current={active ? 'page' : undefined}
          className={`flex flex-col items-center justify-center gap-0.5 min-h-[56px] text-[11px] font-semibold cursor-pointer ${
            active ? 'text-trust-navy' : 'text-slate-400'
          }`}
        >
          <Icon className={`w-5 h-5 ${active ? 'text-trust-navy' : 'text-slate-400'}`} />
          <span>{label}</span>
        </button>
      );
    })}
  </nav>
);
