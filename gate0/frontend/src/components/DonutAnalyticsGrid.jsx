import React, { useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import { didFarmerPickUpAndTalk, normalizeLanguage } from '../utils';

const rupees = (n) => `₹${Number(n || 0).toFixed(2)}`;

const pad2 = (n) => String(n).padStart(2, '0');
const toDateStr = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const getTodayDateStr = () => toDateStr(new Date());
const getPastDateStr = (daysAgo) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return toDateStr(d);
};

const getCallDateKey = (c) => {
  if (!c) return '';
  if (c.call_date) return String(c.call_date).trim().slice(0, 10);
  if (c.date) return String(c.date).trim().slice(0, 10);
  if (c.Call_Date) return String(c.Call_Date).trim().slice(0, 10);
  const ts = c.call_timestamp ?? c.timestamp ?? c.created_at ?? '';
  return String(ts).trim().slice(0, 10);
};

const DAY_PRESETS = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: '7d', label: 'Last 7 Days' },
  { id: '14d', label: 'Last 14 Days' },
  { id: 'all', label: 'All Days' },
];

/**
 * Interactive pure SVG Donut / Pie Chart Card with hover expansion and dynamic center stats.
 * Standardized header height and baseline for seamless horizontal alignment across all 4 cards.
 */
// The hole of the donut is about 96 px wide: a long label is wrapped onto at most two short lines (and cut with an ellipsis)
// so the text stays inside it when a slice is hovered.
const wrapLabel = (text, maxChars = 13, maxLines = 2) => {
  const words = String(text || '').split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  words.forEach((word) => {
    const w = word.length > maxChars ? `${word.slice(0, maxChars - 1)}…` : word;
    if (!line) line = w;
    else if (`${line} ${w}`.length <= maxChars) line = `${line} ${w}`;
    else {
      lines.push(line);
      line = w;
    }
  });
  if (line) lines.push(line);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    const last = kept[maxLines - 1];
    kept[maxLines - 1] = `${last.slice(0, Math.max(1, maxChars - 1))}…`;
    return kept;
  }
  return lines.length ? lines : [''];
};
export const SvgDonutCard = ({
  title,
  subtitle,
  slices = [],
  centerTitle = 'Total',
  centerValue = '0',
  isCurrency = false,
  footer,
}) => {
  const [hoveredId, setHoveredId] = useState(null);

  const total = useMemo(() => {
    return slices.reduce((sum, s) => sum + (Number(s.value) || 0), 0);
  }, [slices]);

  const size = 180;
  const cx = size / 2;
  const cy = size / 2;
  const outerR = 76;
  const innerR = 48;

  const activeSlice = hoveredId ? slices.find((s) => s.id === hoveredId) : null;
  const labelLines = wrapLabel(activeSlice ? activeSlice.label : centerTitle);
  const valueText = String(activeSlice ? (isCurrency ? rupees(activeSlice.value) : activeSlice.value) : centerValue);
  const valueSize = valueText.length > 10 ? 10 : valueText.length > 8 ? 12 : 14;   // a long number shrinks to stay inside the hole

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
    <div className="bg-slate-50/70 border border-slate-200/80 rounded-2xl p-4 flex flex-col h-full shadow-2xs hover:shadow-xs transition-shadow">
      <div className="border-b border-slate-100 pb-2 min-h-[50px] flex flex-col justify-center shrink-0">
        <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider break-words leading-tight">{title}</h4>
        {subtitle && <p className="text-[11px] text-slate-500 break-words leading-snug mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center justify-center relative shrink-0 h-[196px] my-1">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible select-none">
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
            y={cy - 6 - (labelLines.length - 1) * 11}
            textAnchor="middle"
            fill="#64748B"
            fontSize="9"
            fontWeight="600"
            className="uppercase"
          >
            {labelLines.map((l, i) => (
              <tspan key={i} x={cx} dy={i === 0 ? 0 : 11}>{l}</tspan>
            ))}
          </text>
          <text
            x={cx}
            y={cy + 13}
            textAnchor="middle"
            fill="#0F2444"
            fontSize={valueSize}
            fontWeight="800"
          >
            {valueText}
          </text>
          {activeSlice && (
            <text x={cx} y={cy + 26} textAnchor="middle" fill={activeSlice.color} fontSize="10" fontWeight="700">
              {total > 0 ? `${((activeSlice.value / total) * 100).toFixed(1)}%` : '0%'}
            </text>
          )}
        </svg>
      </div>

      <div className="space-y-1.5 pt-3 border-t border-slate-100 text-xs flex-1 flex flex-col justify-start">
        {slices.map((s) => {
          const isHov = hoveredId === s.id;
          const pct = total > 0 ? (Number(s.value || 0) / total) * 100 : 0;
          return (
            <div
              key={s.id}
              onMouseEnter={() => setHoveredId(s.id)}
              onMouseLeave={() => setHoveredId(null)}
              className={`flex items-start justify-between p-1.5 rounded-lg transition-colors cursor-pointer ${
                isHov ? 'bg-white shadow-2xs' : 'hover:bg-slate-100/60'
              }`}
            >
              <div className="flex items-start gap-2 min-w-0 flex-1">
                <span className="w-2.5 h-2.5 rounded-xs shrink-0 mt-1" style={{ backgroundColor: s.color }} />
                <div className="min-w-0 flex-1 break-words leading-snug">
                  <span className={`font-semibold block text-xs ${isHov ? 'text-slate-900' : 'text-slate-700'}`}>
                    {s.label}
                  </span>
                  {s.secondaryText && (
                    <span className="text-[10px] text-slate-400 block break-words mt-0.5">
                      {s.secondaryText}
                    </span>
                  )}
                </div>
              </div>
              <div className="shrink-0 whitespace-nowrap ml-2 text-right self-start pt-0.5">
                <span className="font-bold text-slate-900 font-mono text-[11px]">
                  {isCurrency ? rupees(s.value) : s.value}
                </span>
                <span className="text-[10px] text-slate-400 ml-1">({pct.toFixed(0)}%)</span>
              </div>
            </div>
          );
        })}
        {footer && <div className="mt-auto pt-1">{footer}</div>}
      </div>
    </div>
  );
};

export const DonutAnalyticsGrid = ({
  callLogs = [],
  rate = 3.5,
  messageRate = 0.2,
  embedded = false,
  initialDayFilter = 'today',
  dayFilter: controlledDayFilter,
  onDayFilterChange,
  customDate: controlledCustomDate,
  onCustomDateChange,
  authoritativeSpend,
  authoritativeVoiceSpend,
  authoritativeBilledMins,
  authoritativeAttempts,
}) => {
  const [internalDayFilter, setInternalDayFilter] = useState(initialDayFilter);
  const [internalCustomDate, setInternalCustomDate] = useState('');

  const dayFilter = controlledDayFilter !== undefined ? controlledDayFilter : internalDayFilter;
  const customDate = controlledCustomDate !== undefined ? controlledCustomDate : internalCustomDate;

  const handlePresetChange = (presetId) => {
    if (onDayFilterChange) onDayFilterChange(presetId);
    else setInternalDayFilter(presetId);

    if (onCustomDateChange) onCustomDateChange('');
    else setInternalCustomDate('');
  };

  const handleCustomDateChange = (e) => {
    const val = e.target.value;
    if (onCustomDateChange) onCustomDateChange(val);
    else setInternalCustomDate(val);

    if (!val) {
      if (onDayFilterChange) onDayFilterChange('today');
      else setInternalDayFilter('today');
    } else {
      if (onDayFilterChange) onDayFilterChange('custom');
      else setInternalDayFilter('custom');
    }
  };

  const filteredCalls = useMemo(() => {
    // Rule 4: Include test calls
    const valid = callLogs || [];
    if (dayFilter === 'all') return valid;

    const todayStr = getTodayDateStr();
    const yesterdayStr = getPastDateStr(1);
    const d7Str = getPastDateStr(6);
    const d14Str = getPastDateStr(13);

    return valid.filter((c) => {
      const callDate = getCallDateKey(c);
      if (!callDate) return false;
      if (dayFilter === 'today') return callDate === todayStr;
      if (dayFilter === 'yesterday') return callDate === yesterdayStr;
      if (dayFilter === '7d') return callDate >= d7Str && callDate <= todayStr;
      if (dayFilter === '14d') return callDate >= d14Str && callDate <= todayStr;
      if (dayFilter === 'custom' && customDate) return callDate === customDate;
      return true;
    });
  }, [callLogs, dayFilter, customDate]);

  const timeframeLabel = useMemo(() => {
    const todayStr = getTodayDateStr();
    const yesterdayStr = getPastDateStr(1);
    const d7Str = getPastDateStr(6);
    const d14Str = getPastDateStr(13);

    if (dayFilter === 'today') return `Today (${todayStr})`;
    if (dayFilter === 'yesterday') return `Yesterday (${yesterdayStr})`;
    if (dayFilter === '7d') return `Last 7 Days (${d7Str} to ${todayStr})`;
    if (dayFilter === '14d') return `Last 14 Days (${d14Str} to ${todayStr})`;
    if (dayFilter === 'custom' && customDate) return `Date: ${customDate}`;
    return 'All Recorded Days';
  }, [dayFilter, customDate]);

  const analytics = useMemo(() => {
    let totalAttemptsCount = 0;
    let totalBilledMins = 0;
    let totalConnectedSec = 0;
    let connectedCount = 0;
    let totalMessages = 0;

    filteredCalls.forEach((c) => {
      const msgs = Number(c.messages_sent ?? c.sms_count ?? 0);
      totalMessages += msgs;

      const attempts = Array.isArray(c.attempts_log) && c.attempts_log.length > 0 ? c.attempts_log : null;
      if (attempts) {
        totalAttemptsCount += attempts.length;
        attempts.forEach((att) => {
          const sec = Number(att.duration_seconds ?? att.duration_sec ?? att.duration_s ?? att.duration ?? 0);
          // Rules 5A & 6A: Bill only when sec > 0, across every attempt
          if (sec > 0) {
            totalBilledMins += Math.ceil(sec / 60);
            totalConnectedSec += sec;
            connectedCount += 1;
          }
        });
      } else {
        const retries = Number(c.retry_count || 0);
        totalAttemptsCount += Math.max(1, retries + 1);
        const sec = Number(c.duration_sec ?? c.duration_seconds ?? c.duration_s ?? c.duration ?? 0);
        if (sec > 0) {
          totalBilledMins += Math.ceil(sec / 60);
          totalConnectedSec += sec;
          connectedCount += 1;
        }
      }
    });

    const effectiveBilledMins =
      authoritativeBilledMins !== undefined && authoritativeBilledMins >= 0
        ? authoritativeBilledMins
        : totalBilledMins;

    const voiceAiCost =
      authoritativeVoiceSpend !== undefined && authoritativeVoiceSpend >= 0
        ? authoritativeVoiceSpend
        : Math.round(effectiveBilledMins * rate * 100) / 100;

    const messageCost = Math.round(totalMessages * messageRate * 100) / 100;

    // Rule 9A: Fixed ₹59/mo rental is NEVER added into operational or total spend
    const totalSpend =
      authoritativeSpend !== undefined && authoritativeSpend >= 0
        ? authoritativeSpend
        : Math.round((voiceAiCost + messageCost) * 100) / 100;

    const displayAttempts =
      authoritativeAttempts !== undefined && authoritativeAttempts > 0
        ? authoritativeAttempts
        : (totalAttemptsCount || filteredCalls.length);

    const avgSec = connectedCount > 0 ? Math.round(totalConnectedSec / connectedCount) : 0;
    const avgMins = Math.floor(avgSec / 60);
    const avgRemSec = avgSec % 60;
    const avgDurationFormatted = `${avgMins}m ${String(avgRemSec).padStart(2, '0')}s`;

    const costSplitSlices = [
      {
        id: 'voice',
        label: 'Sarvam Voice AI',
        value: voiceAiCost,
        color: '#1E6F43',
        secondaryText: `${effectiveBilledMins} billed mins (₹${Number(rate).toFixed(2)}/min)`,
      },
      ...(totalMessages > 0
        ? [
            {
              id: 'messages',
              label: 'Advisory Messages',
              value: messageCost,
              color: '#0284C7',
              secondaryText: `${totalMessages} sent (₹${Number(messageRate).toFixed(2)}/msg)`,
            },
          ]
        : []),
    ];

    // 2. Call Outcomes Data
    let completed = 0;
    let callbacks = 0;
    let unanswered = 0;
    let failed = 0;

    filteredCalls.forEach((c) => {
      const attempts = Array.isArray(c.attempts_log) && c.attempts_log.length > 0 ? c.attempts_log : null;
      if (attempts) {
        attempts.forEach((att, idx) => {
          const raw = String(att.status || '').toLowerCase();
          const isLastAttempt = idx === attempts.length - 1;
          if (isLastAttempt && (String(c.status || '').toLowerCase().includes('callback') || c.callback_time)) {
            callbacks += 1;
          } else if (
            raw.includes('completed') ||
            raw.includes('delivered') ||
            raw.includes('answered') ||
            Number(att.duration_seconds || 0) > 0
          ) {
            completed += 1;
          } else if (raw.includes('fail') || raw.includes('declined') || raw.includes('rejected') || raw.includes('error')) {
            failed += 1;
          } else {
            unanswered += 1;
          }
        });
      } else {
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
      }
    });

    const loggedTotal = completed + callbacks + unanswered + failed;
    if (displayAttempts > loggedTotal) {
      unanswered += displayAttempts - loggedTotal;
    }

    const outcomeSlices = [
      { id: 'completed', label: 'Completed & Answered', value: completed, color: '#1E6F43', secondaryText: 'Weather advisory delivered' },
      { id: 'callbacks', label: 'Callback Scheduled', value: callbacks, color: '#3B82F6', secondaryText: 'Requested callback later' },
      { id: 'unanswered', label: 'Unanswered / Busy', value: unanswered, color: '#F59E0B', secondaryText: 'Ringing or line busy' },
      { id: 'failed', label: 'Needs Attention', value: failed, color: '#EF4444', secondaryText: 'Line dropped or rejected' },
    ];

    // 3. Language Breakdown (sums all attempts per call)
    const langCounts = { Kannada: 0, Hindi: 0, Telugu: 0, English: 0 };
    const langSpend = { Kannada: 0, Hindi: 0, Telugu: 0, English: 0 };

    filteredCalls.forEach((c) => {
      const rawLang = c.language || c.Farmer_Language || c.calling_language || c.Language || 'Kannada';
      const norm = normalizeLanguage(rawLang);
      const attempts = Array.isArray(c.attempts_log) && c.attempts_log.length > 0 ? c.attempts_log : null;

      if (attempts) {
        langCounts[norm] = (langCounts[norm] || 0) + attempts.length;
        let callMins = 0;
        attempts.forEach((att) => {
          const sec = Number(att.duration_seconds ?? att.duration_sec ?? att.duration_s ?? att.duration ?? 0);
          if (sec > 0) callMins += Math.ceil(sec / 60);
        });
        const cost = Math.round(callMins * rate * 100) / 100;
        langSpend[norm] = Math.round(((langSpend[norm] || 0) + cost) * 100) / 100;
      } else {
        langCounts[norm] = (langCounts[norm] || 0) + 1;
        const sec = Number(c.duration_sec ?? c.duration_seconds ?? c.duration_s ?? c.duration ?? 0);
        const mins = sec > 0 ? Math.ceil(sec / 60) : 0;
        const cost = Math.round(mins * rate * 100) / 100;
        langSpend[norm] = Math.round(((langSpend[norm] || 0) + cost) * 100) / 100;
      }
    });

    const languageSlices = [
      { id: 'kannada', label: 'Kannada', value: langCounts.Kannada, color: '#0F2444', secondaryText: `₹${(langSpend.Kannada || 0).toFixed(2)} estimated` },
      { id: 'hindi', label: 'Hindi', value: langCounts.Hindi, color: '#0284C7', secondaryText: `₹${(langSpend.Hindi || 0).toFixed(2)} estimated` },
      { id: 'telugu', label: 'Telugu', value: langCounts.Telugu, color: '#10B981', secondaryText: `₹${(langSpend.Telugu || 0).toFixed(2)} estimated` },
      { id: 'english', label: 'English', value: langCounts.English, color: '#8B5CF6', secondaryText: `₹${(langSpend.English || 0).toFixed(2)} estimated` },
    ];

    // 4. Call Duration Tiers (across all connected attempts)
    let tierShort = 0;
    let tierStandard = 0;
    let tierExtended = 0;
    let tierDeep = 0;

    const bucketDuration = (sec) => {
      if (sec <= 0) return;
      if (sec < 60) tierShort += 1;
      else if (sec < 120) tierStandard += 1;
      else if (sec < 180) tierExtended += 1;
      else tierDeep += 1;
    };

    filteredCalls.forEach((c) => {
      const attempts = Array.isArray(c.attempts_log) && c.attempts_log.length > 0 ? c.attempts_log : null;
      if (attempts) {
        attempts.forEach((att) => bucketDuration(Number(att.duration_seconds ?? att.duration_sec ?? att.duration_s ?? att.duration ?? 0)));
      } else {
        bucketDuration(Number(c.duration_sec ?? c.duration_seconds ?? c.duration_s ?? c.duration ?? 0));
      }
    });

    const durationSlices = [
      { id: 'short', label: 'Under 1 min', value: tierShort, color: '#06B6D4', secondaryText: 'Quick weather delivery' },
      { id: 'standard', label: '1 – 2 mins', value: tierStandard, color: '#1E6F43', secondaryText: 'Full forecast confirmation' },
      { id: 'extended', label: '2 – 3 mins', value: tierExtended, color: '#F59E0B', secondaryText: 'Forecast + Q&A dialogue' },
      { id: 'deep', label: 'Over 3 mins', value: tierDeep, color: '#6366F1', secondaryText: 'Extended advisory consultation' },
    ];

    return {
      displayAttempts,
      totalSpend,
      voiceAiCost,
      messageCost,
      totalMessages,
      avgDurationFormatted,
      costSplitSlices,
      outcomeSlices,
      languageSlices,
      durationSlices,
      connectedCount,
      totalBilledMins: effectiveBilledMins,
    };
  }, [filteredCalls, rate, messageRate, authoritativeSpend, authoritativeVoiceSpend, authoritativeBilledMins, authoritativeAttempts]);

  const containerClass = embedded
    ? 'space-y-4'
    : 'bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-4 shadow-2xs';

  return (
    <div className={containerClass}>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-slate-50 border border-slate-200/70 rounded-xl">
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <Calendar className="w-4 h-4 text-trust-green shrink-0" />
          <span className="text-xs font-bold text-slate-800">Filter:</span>
          <span className="text-xs text-slate-600 font-medium">{timeframeLabel}</span>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-white text-slate-700 border border-slate-200/80 shadow-2xs">
            {analytics.displayAttempts} {analytics.displayAttempts === 1 ? 'attempt' : 'attempts'}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1 self-start sm:self-auto">
          {DAY_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handlePresetChange(preset.id)}
              className={`h-8 px-3 rounded-lg inline-flex items-center justify-center whitespace-nowrap text-xs font-semibold transition-all cursor-pointer ${ dayFilter === preset.id ? 'bg-trust-navy text-white shadow-2xs' : 'bg-white text-slate-600 hover:text-slate-900 border border-slate-200/80 hover:bg-slate-50' }`}
            >
              {preset.label}
            </button>
          ))}

          <div className="flex items-center gap-1 pl-1">
            <input
              type="date"
              value={customDate || ''}
              onChange={handleCustomDateChange}
              aria-label="Pick custom date"
              className="px-2 py-0.5 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-700 focus:outline-hidden focus:border-trust-navy cursor-pointer"
            />
            {customDate && (
              <button
                type="button"
                onClick={() => handlePresetChange('14d')}
                className="text-slate-400 hover:text-slate-600 p-0.5 rounded cursor-pointer text-xs font-bold"
                title="Reset to 14 days"
              >
                ×
              </button>
            )}
          </div>
        </div>
      </div>

      {filteredCalls.length === 0 && (
        <div className="p-4 text-center text-xs text-slate-500 bg-amber-50/60 border border-amber-200/70 rounded-xl">
          No calls recorded for {timeframeLabel}. Pick another timeframe above to inspect breakdowns.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 items-stretch">
        <SvgDonutCard
          title="Spend Split"
          subtitle={analytics.totalMessages > 0 ? 'Voice AI calls vs. advisory messages' : 'Sarvam Voice AI call usage'}
          slices={analytics.costSplitSlices}
          centerTitle="Usage Spend"
          centerValue={rupees(analytics.totalSpend)}
          isCurrency={true}
          footer={
            <div className="space-y-1.5">
              {analytics.totalMessages > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-1 p-1.5 rounded-lg bg-sky-50/70 border border-sky-200/60 text-[11px]">
                  <span className="text-sky-800 font-medium">Messages Dispatched:</span>
                  <span className="font-bold font-mono text-sky-950 shrink-0 whitespace-nowrap">
                    {analytics.totalMessages} sent ({rupees(analytics.messageCost)})
                  </span>
                </div>
              )}
              <div className="flex flex-wrap items-center justify-between gap-1 p-1.5 rounded-lg bg-slate-100/60 border border-slate-200/50 text-[11px]">
                <span className="text-slate-500 font-medium">Connected Calls:</span>
                <span className="font-bold font-mono text-slate-800 shrink-0 whitespace-nowrap">
                  {analytics.connectedCount} calls ({analytics.totalBilledMins} mins)
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-1 p-1.5 rounded-lg bg-blue-50/70 border border-blue-200/60 text-[11px]">
                <span className="text-trust-navy font-semibold">Separate Monthly Base:</span>
                <span className="font-bold font-mono text-trust-navy shrink-0 whitespace-nowrap">₹59.00/mo (Fixed DID)</span>
              </div>
            </div>
          }
        />

        <SvgDonutCard
          title="Call Outcomes"
          subtitle="Attempt engagement & delivery ratios"
          slices={analytics.outcomeSlices}
          centerTitle="Attempts"
          centerValue={String(analytics.displayAttempts)}
        />

        <SvgDonutCard
          title="Language Mix"
          subtitle="Regional dialect distribution"
          slices={analytics.languageSlices}
          centerTitle="Languages"
          centerValue="4"
        />

        <SvgDonutCard
          title="Duration Tiers"
          subtitle="Talk time length distribution"
          slices={analytics.durationSlices}
          centerTitle="Avg Length"
          centerValue={analytics.avgDurationFormatted}
        />
      </div>
    </div>
  );
};

export default DonutAnalyticsGrid;
