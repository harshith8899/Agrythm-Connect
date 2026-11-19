import React from 'react';

export const OverviewCard = ({
  title,
  value,
  subtitle,
  icon: Icon,
  badge,
  badgeColor,
  trend,
  className = '',
  loading = false,
  onClick,
  active = false,
}) => {
  const isClickable = Boolean(onClick);

  return (
    <div
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={`bg-white rounded-2xl border transition-all text-left h-full flex flex-col justify-between ${
        active
          ? 'border-trust-navy ring-2 ring-trust-navy/80 shadow-xs bg-slate-50/60'
          : 'border-slate-200/80 hover:border-slate-300 hover:shadow-2xs'
      } ${
        isClickable
          ? 'cursor-pointer active:scale-[0.99] select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-trust-navy'
          : ''
      } p-4 sm:p-5 ${className}`}
    >
      <div>
        <div className="flex items-center justify-between gap-1 mb-2.5">
          <span
            className={`text-[11px] font-bold tracking-wider uppercase truncate ${
              active ? 'text-trust-navy' : 'text-slate-500'
            }`}
          >
            {title}
          </span>
          {Icon && (
            <div
              className={`w-8 h-8 rounded-xl flex items-center justify-center border shrink-0 transition-colors ${
                active
                  ? 'bg-trust-navy text-white border-trust-navy'
                  : 'bg-slate-50 text-slate-600 border-slate-200/60'
              }`}
            >
              <Icon className="w-4 h-4" />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
          {loading ? (
            <div className="h-8 w-14 rounded-lg bg-slate-200 animate-pulse" aria-label="Loading" />
          ) : (
            <div className="text-2xl font-bold text-slate-900 tracking-tight font-mono tabular-nums">
              {value}
            </div>
          )}
          {badge && !loading && (
            <span
              className={`inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full border ${
                badgeColor || 'bg-emerald-50 text-trust-green border-emerald-200'
              }`}
            >
              {badge}
            </span>
          )}
        </div>
      </div>

      {(subtitle || trend) && (
        <div className="mt-3 pt-2 border-t border-slate-100 text-xs text-slate-500 flex items-start gap-1.5 min-w-0">
          {trend && <span className="font-semibold text-trust-green shrink-0">{trend}</span>}
          {subtitle && <span className="truncate leading-snug">{subtitle}</span>}
        </div>
      )}
    </div>
  );
};

export default OverviewCard;
