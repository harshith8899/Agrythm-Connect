import React from 'react';

export const OverviewCard = ({ title, value, subtitle, icon: Icon, badge, trend }) => {
  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 p-5 transition-all hover:border-slate-300">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
          {title}
        </span>
        {Icon && (
          <div className="w-8 h-8 rounded-xl bg-slate-50 flex items-center justify-center text-slate-700 border border-slate-200/60">
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="flex items-baseline justify-between mt-1">
        <div className="text-2xl font-bold text-slate-900 tracking-tight">
          {value}
        </div>
        {badge && (
          <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-trust-green border border-emerald-200">
            {badge}
          </span>
        )}
      </div>

      {(subtitle || trend) && (
        <div className="mt-2 text-xs text-slate-500 flex items-center gap-1.5">
          {trend && <span className="font-medium text-trust-green">{trend}</span>}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
