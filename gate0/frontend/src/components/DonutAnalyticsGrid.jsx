import React, { useMemo, useState } from 'react';
import { didFarmerPickUpAndTalk, normalizeLanguage } from '../utils';

const rupees = (n) => `₹${Number(n || 0).toFixed(2)}`;

/**
 * Interactive pure SVG Donut / Pie Chart Card with hover expansion and dynamic center stats.
 */
export const SvgDonutCard = ({
  title,
  subtitle,
  slices = [],
  centerTitle = 'Total',
  centerValue = '0',
  isCurrency = false,
  badge = null,
}) => {
  const [hoveredId, setHoveredId] = useState(null);

  const total = useMemo(() => {
    return slices.reduce((sum, s) => sum + (Number(s.value) || 0), 0);
  }, [slices]);

  // Dimensions
  const size = 180;
  const cx = size / 2;
  const cy = size / 2;
  const outerR = 76;
  const innerR = 48;

  // Active slice for dynamic center display
  const activeSlice = hoveredId ? slices.find((s) => s.id === hoveredId) : null;

  // Compute arc segments
  let currentAngle = -Math.PI / 2;
  const arcSegments = slices.map((s) => {
    const val = Number(s.value) || 0;
    const pct = total > 0 ? val / total : 0;
    const a0 = currentAngle;
    const a1 = a0 + pct * 2 * Math.PI;
    currentAngle = a1;

    const isHovered = hoveredId === s.id;
    const R = isHovered ? outerR + 4 : outerR;
    const r = isHovered ? innerR - 2 : innerR;

    const x1 = cx + R * Math.cos(a0);
    const y1 = cy + R * Math.sin(a0);
    const x2 = cx + R * Math.cos(a1);
    const y2 = cy + R * Math.sin(a1);
    const x3 = cx + r * Math.cos(a1);
    const y3 = cy + r * Math.sin(a1);
    const x4 = cx + r * Math.cos(a0);
    const y4 = cy + r * Math.sin(a0);
    const largeArc = a1 - a0 > Math.PI ? 1 : 0;

    const pathD = `M ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${r} ${r} 0 ${largeArc} 0 ${x4} ${y4} Z`;

    return {
      ...s,
      pct,
      pctFormatted: `${(pct * 100).toFixed(1)}%`,
      pathD,
      isHovered,
    };
  });

  return (
    <div className="bg-slate-50/70 border border-slate-200/80 rounded-2xl p-4 flex flex-col justify-between space-y-3.5 shadow-2xs hover:shadow-xs transition-shadow">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
        <div>
          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">{title}</h4>
          {subtitle && <p className="text-[10px] text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {badge && (
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700">
            {badge}
          </span>
        )}
      </div>

      {/* Donut Graphic */}
      <div className="flex items-center justify-center relative py-1">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="overflow-visible select-none"
        >
          {total === 0 ? (
            <circle
              cx={cx}
              cy={cy}
              r={(outerR + innerR) / 2}
              fill="none"
              stroke="#E2E8F0"
              strokeWidth={outerR - innerR}
              strokeDasharray="4 4"
            />
          ) : (
            arcSegments.map((s) => {
              if (s.pct <= 0) return null;
              if (s.pct >= 0.999) {
                return (
                  <circle
                    key={s.id}
                    cx={cx}
                    cy={cy}
                    r={(outerR + innerR) / 2}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={outerR - innerR}
                    className="cursor-pointer transition-all duration-200"
                    onMouseEnter={() => setHoveredId(s.id)}
                    onMouseLeave={() => setHoveredId(null)}
                  />
                );
              }
              return (
                <path
                  key={s.id}
                  d={s.pathD}
                  fill={s.color}
                  stroke="#FFFFFF"
                  strokeWidth="2"
                  className="cursor-pointer transition-all duration-150"
                  onMouseEnter={() => setHoveredId(s.id)}
                  onMouseLeave={() => setHoveredId(null)}
                />
              );
            })
          )}

          {/* Dynamic Center Text */}
          <text
            x={cx}
            y={cy - 6}
            textAnchor="middle"
            fill="#64748B"
            fontSize="10"
            fontWeight="600"
            className="uppercase tracking-wider"
          >
            {activeSlice ? activeSlice.label : centerTitle}
          </text>
          <text
            x={cx}
            y={cy + 13}
            textAnchor="middle"
            fill="#0F2444"
            fontSize="14"
            fontWeight="800"
          >
            {activeSlice
              ? isCurrency
                ? rupees(activeSlice.value)
                : activeSlice.value
              : centerValue}
          </text>
          {activeSlice && (
            <text
              x={cx}
              y={cy + 26}
              textAnchor="middle"
              fill={activeSlice.color}
              fontSize="10"
              fontWeight="700"
            >
              {total > 0 ? `${((activeSlice.value / total) * 100).toFixed(1)}%` : '0%'}
            </text>
          )}
        </svg>
      </div>

      {/* Legend Rows */}
      <div className="space-y-1.5 pt-2 border-t border-slate-100 text-xs">
        {slices.map((s) => {
          const isHov = hoveredId === s.id;
          const pct = total > 0 ? (Number(s.value || 0) / total) * 100 : 0;
          return (
            <div
              key={s.id}
              onMouseEnter={() => setHoveredId(s.id)}
              onMouseLeave={() => setHoveredId(null)}
              className={`flex items-center justify-between p-1.5 rounded-lg transition-colors cursor-pointer ${
                isHov ? 'bg-white shadow-2xs' : 'hover:bg-slate-100/60'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="w-2.5 h-2.5 rounded-xs shrink-0"
                  style={{ backgroundColor: s.color }}
                />
                <div className="truncate">
                  <span className={`font-semibold ${isHov ? 'text-slate-900' : 'text-slate-700'}`}>
                    {s.label}
                  </span>
                  {s.secondaryText && (
                    <span className="text-[10px] text-slate-400 block truncate">{s.secondaryText}</span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0 ml-2">
                <span className="font-bold text-slate-900 font-mono text-[11px]">
                  {isCurrency ? rupees(s.value) : s.value}
                </span>
                <span className="text-[10px] text-slate-400 ml-1">({pct.toFixed(0)}%)</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/**
 * Grid of Donut & Pie Charts visualizing:
 * 1. Sarvam Voice AI vs Telephony Carrier Pulses
 * 2. Call Outcomes & Delivery Ratios
 * 3. Regional / Language Cost Distribution
 * 4. Call Duration & Pulse Tiers
 */
export const DonutAnalyticsGrid = ({
  callLogs = [],
  rate = 3.5,
  embedded = false,
}) => {
  const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'cost' | 'outcomes' | 'languages' | 'durations'

  const analytics = useMemo(() => {
    const validCalls = (callLogs || []).filter((c) => !c.is_test);
    const totalCallsCount = validCalls.length;

    // 1. Cost Split Data
    let totalBilledMins = 0;
    validCalls.forEach((c) => {
      const isConn =
        didFarmerPickUpAndTalk(c) ||
        ['completed', 'delivered', 'connected', 'answered'].includes(
          String(c.call_status || c.status || '').toLowerCase()
        ) ||
        Number(c.duration_sec || c.duration || 0) > 0;
      if (isConn) {
        const sec = Number(c.duration_sec ?? c.duration ?? 0);
        totalBilledMins += Math.max(1, Math.ceil(sec / 60));
      }
    });

    const voiceAiCost = Math.round(totalBilledMins * rate * 100) / 100;
    const carriageCost = Math.round(totalBilledMins * 0.5 * 100) / 100;
    const totalCombinedSpend = voiceAiCost + carriageCost;

    const costSplitSlices = [
      {
        id: 'voice',
        label: 'Sarvam Voice AI',
        value: voiceAiCost,
        color: '#1E6F43', // Trust Green
        secondaryText: `TTS, STT & Dialogue LLM (₹${Number(rate).toFixed(2)}/min)`,
      },
      {
        id: 'carriage',
        label: 'Carrier Telephony',
        value: carriageCost,
        color: '#0F2444', // Trust Navy
        secondaryText: 'Exotel Pulses (~₹0.50/min)',
      },
    ];

    // 2. Call Outcomes Data
    let completed = 0;
    let callbacks = 0;
    let unanswered = 0;
    let failed = 0;

    validCalls.forEach((c) => {
      const raw = String(c.call_status || c.status || '').toLowerCase();
      if (raw.includes('callback') || c.callback_time) {
        callbacks += 1;
      } else if (
        didFarmerPickUpAndTalk(c) ||
        raw.includes('completed') ||
        raw.includes('delivered') ||
        raw.includes('answered')
      ) {
        completed += 1;
      } else if (
        raw.includes('fail') ||
        raw.includes('declined') ||
        raw.includes('rejected') ||
        raw.includes('error')
      ) {
        failed += 1;
      } else {
        unanswered += 1;
      }
    });

    const outcomeSlices = [
      {
        id: 'completed',
        label: 'Completed & Understood',
        value: completed,
        color: '#1E6F43',
        secondaryText: 'Weather advisory delivered',
      },
      {
        id: 'callbacks',
        label: 'Callbacks Scheduled',
        value: callbacks,
        color: '#3B82F6',
        secondaryText: 'Requested call later',
      },
      {
        id: 'unanswered',
        label: 'Unanswered / Busy',
        value: unanswered,
        color: '#F59E0B',
        secondaryText: 'Ringing or line busy',
      },
      {
        id: 'failed',
        label: 'Needs Attention',
        value: failed,
        color: '#EF4444',
        secondaryText: 'Line drop or rejected',
      },
    ];

    // 3. Language Breakdown
    const langCounts = { Kannada: 0, Hindi: 0, Telugu: 0, English: 0 };
    const langSpend = { Kannada: 0, Hindi: 0, Telugu: 0, English: 0 };

    validCalls.forEach((c) => {
      const rawLang = c.language || c.Farmer_Language || c.calling_language || c.Language || 'Kannada';
      const norm = normalizeLanguage(rawLang);
      langCounts[norm] = (langCounts[norm] || 0) + 1;

      const sec = Number(c.duration_sec ?? c.duration ?? 0);
      const mins = Math.max(1, Math.ceil(sec / 60));
      const cost = Math.round(mins * (rate + 0.5) * 100) / 100;
      langSpend[norm] = Math.round(((langSpend[norm] || 0) + cost) * 100) / 100;
    });

    const languageSlices = [
      {
        id: 'kannada',
        label: 'Kannada',
        value: langCounts.Kannada,
        color: '#0F2444',
        secondaryText: `₹${(langSpend.Kannada || 0).toFixed(2)} estimated`,
      },
      {
        id: 'hindi',
        label: 'Hindi',
        value: langCounts.Hindi,
        color: '#0284C7',
        secondaryText: `₹${(langSpend.Hindi || 0).toFixed(2)} estimated`,
      },
      {
        id: 'telugu',
        label: 'Telugu',
        value: langCounts.Telugu,
        color: '#10B981',
        secondaryText: `₹${(langSpend.Telugu || 0).toFixed(2)} estimated`,
      },
      {
        id: 'english',
        label: 'English',
        value: langCounts.English,
        color: '#8B5CF6',
        secondaryText: `₹${(langSpend.English || 0).toFixed(2)} estimated`,
      },
    ];

    // 4. Call Duration Tiers
    let tierShort = 0;
    let tierStandard = 0;
    let tierExtended = 0;
    let tierDeep = 0;

    validCalls.forEach((c) => {
      const sec = Number(c.duration_sec ?? c.duration ?? 0);
      if (sec <= 0) return;
      if (sec < 60) tierShort += 1;
      else if (sec < 120) tierStandard += 1;
      else if (sec < 180) tierExtended += 1;
      else tierDeep += 1;
    });

    const durationSlices = [
      {
        id: 'short',
        label: '< 1 min (1 pulse)',
        value: tierShort,
        color: '#06B6D4',
        secondaryText: 'Quick weather delivery',
      },
      {
        id: 'standard',
        label: '1 – 2 mins (2 pulses)',
        value: tierStandard,
        color: '#1E6F43',
        secondaryText: 'Full forecast confirmation',
      },
      {
        id: 'extended',
        label: '2 – 3 mins (3 pulses)',
        value: tierExtended,
        color: '#F59E0B',
        secondaryText: 'Forecast + Q&A dialogue',
      },
      {
        id: 'deep',
        label: '> 3 mins (4+ pulses)',
        value: tierDeep,
        color: '#6366F1',
        secondaryText: 'Extended advisory consultation',
      },
    ];

    return {
      totalCallsCount,
      totalSpend: totalCombinedSpend,
      costSplitSlices,
      outcomeSlices,
      languageSlices,
      durationSlices,
    };
  }, [callLogs, rate]);

  const containerClass = embedded
    ? 'space-y-4'
    : 'bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-4 shadow-2xs';

  return (
    <div className={containerClass}>
      {/* Sub-header with filter pills */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-100">
        <div>
          <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            Categorical Donut & Pie Analytics
          </span>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Interactive visual breakdowns across telephony costs, engagement outcomes, languages, and durations
          </p>
        </div>

        {/* Filter Pills */}
        <div className="inline-flex flex-wrap p-0.5 rounded-xl bg-slate-100 border border-slate-200/60 self-start sm:self-auto text-xs">
          {[
            { id: 'all', label: 'All Donut Charts' },
            { id: 'cost', label: 'Cost Allocation' },
            { id: 'outcomes', label: 'Call Outcomes' },
            { id: 'languages', label: 'Languages' },
            { id: 'durations', label: 'Duration Tiers' },
          ].map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setActiveFilter(f.id)}
              className={`px-2.5 py-1 font-semibold rounded-lg transition-all cursor-pointer ${
                activeFilter === f.id
                  ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid of Donut Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3.5">
        {(activeFilter === 'all' || activeFilter === 'cost') && (
          <SvgDonutCard
            title="Telephony Cost Allocation"
            subtitle="Voice AI engine vs carrier pulse carriage"
            slices={analytics.costSplitSlices}
            centerTitle="Total Cost"
            centerValue={rupees(analytics.totalSpend)}
            isCurrency={true}
            badge="Rupee Share"
          />
        )}

        {(activeFilter === 'all' || activeFilter === 'outcomes') && (
          <SvgDonutCard
            title="Call Outcome Statuses"
            subtitle="Farmer engagement & delivery ratios"
            slices={analytics.outcomeSlices}
            centerTitle="Total Calls"
            centerValue={String(analytics.totalCallsCount)}
            badge="Outcomes"
          />
        )}

        {(activeFilter === 'all' || activeFilter === 'languages') && (
          <SvgDonutCard
            title="Language Distribution"
            subtitle="Farmer language preference & spend"
            slices={analytics.languageSlices}
            centerTitle="Languages"
            centerValue="4 Dialects"
            badge="Regional Mix"
          />
        )}

        {(activeFilter === 'all' || activeFilter === 'durations') && (
          <SvgDonutCard
            title="Call Duration Tiers"
            subtitle="Conversation duration & pulse billing"
            slices={analytics.durationSlices}
            centerTitle="Calls Billed"
            centerValue={String(analytics.totalCallsCount)}
            badge="Pulse Tiers"
          />
        )}
      </div>
    </div>
  );
};
