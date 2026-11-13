import React, { useMemo, useState } from 'react';
import { Activity, TrendingUp, Zap, Clock, RefreshCw } from 'lucide-react';
import { didFarmerPickUpAndTalk } from '../utils';

const rupees = (n) => `₹${Number(n || 0).toFixed(2)}`;

function formatFullDate(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
    }
  }
  return dateStr;
}

function getCallDateKey(call) {
  if (!call) return '';
  const raw = call.call_date || call.date || call.Date || call.call_timestamp || call.created_at || '';
  const str = String(raw).trim();
  if (!str) return '';
  const m = str.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) {
    return `${m[1]}-${m[2]}-${m[3]}`;
  }
  const m2 = str.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})/);
  if (m2) {
    const dd = m2[1].padStart(2, '0');
    const mm = m2[2].padStart(2, '0');
    const yyyy = m2[3];
    return `${yyyy}-${mm}-${dd}`;
  }
  const parsed = new Date(str);
  if (!isNaN(parsed.getTime())) {
    return parsed.toISOString().slice(0, 10);
  }
  return '';
}

function getCallHour(call) {
  if (!call) return null;
  // 1. Time string (e.g. '10:30', '14:20:00', '10:30 AM')
  const timeStr = String(call.call_time || call.time || call.Time || call.Call_Time || '').trim();
  if (timeStr) {
    const m = timeStr.match(/^(\d{1,2}):(\d{2})/);
    if (m) {
      let h = parseInt(m[1], 10);
      if (/pm/i.test(timeStr) && h < 12) h += 12;
      if (/am/i.test(timeStr) && h === 12) h = 0;
      return h;
    }
  }

  // 2. Direct ISO timestamp
  const ts = call.created_at || call.call_timestamp || call.timestamp;
  if (ts) {
    if (typeof ts === 'number') {
      const d = new Date(ts > 1e11 ? ts : ts * 1000);
      if (!isNaN(d.getTime())) return d.getHours();
    }
    const d = new Date(ts);
    if (!isNaN(d.getTime())) return d.getHours();
  }

  return null;
}

function computeHourlyTelemetry(callLogs = [], rate = 3.5) {
  const validCalls = (callLogs || []).filter((c) => !c.is_test);

  const todayStr = new Date().toISOString().slice(0, 10);
  let targetCalls = validCalls.filter((c) => getCallDateKey(c) === todayStr);
  let isToday = true;
  let targetDateLabel = 'Today';

  // If 0 calls today, fallback to the latest active call date in the dataset
  if (targetCalls.length === 0 && validCalls.length > 0) {
    const sorted = [...validCalls].sort((a, b) => {
      const da = getCallDateKey(a);
      const db = getCallDateKey(b);
      return db.localeCompare(da);
    });
    const latestDate = getCallDateKey(sorted[0]);
    targetCalls = validCalls.filter((c) => getCallDateKey(c) === latestDate);
    isToday = false;
    targetDateLabel = latestDate ? formatFullDate(latestDate) : 'Latest Active Run';
  }

  // Active agricultural advisory calling window: 06:00 to 21:00 (6 AM to 9 PM)
  const startHour = 6;
  const endHour = 21;
  const hours = [];

  let runningCumulative = 0;
  let peakHour = startHour;
  let peakSpend = 0;

  for (let h = startHour; h <= endHour; h++) {
    const hourCalls = targetCalls.filter((c) => {
      const callH = getCallHour(c);
      return callH === h;
    });

    const connected = hourCalls.filter(
      (c) =>
        didFarmerPickUpAndTalk(c) ||
        ['completed', 'delivered', 'connected', 'answered'].includes(
          String(c.call_status || c.status || '').toLowerCase()
        ) ||
        Number(c.duration_sec || c.duration || 0) > 0
    );

    const billedMinutes = connected.reduce((sum, c) => {
      const sec = Number(c.duration_sec ?? c.duration ?? 0);
      return sum + Math.max(1, Math.ceil(sec / 60));
    }, 0);

    const spend = Math.round(billedMinutes * rate * 100) / 100;
    runningCumulative = Math.round((runningCumulative + spend) * 100) / 100;

    if (spend > peakSpend) {
      peakSpend = spend;
      peakHour = h;
    }

    const ampm = h >= 12 ? 'PM' : 'AM';
    const displayH = h % 12 === 0 ? 12 : h % 12;
    const label = `${displayH} ${ampm}`;

    hours.push({
      hour: h,
      label,
      timeRange: `${displayH}:00 ${ampm} – ${displayH}:59 ${ampm}`,
      calls: hourCalls.length,
      connected: connected.length,
      billedMinutes,
      spend,
      cumulativeSpend: runningCumulative,
    });
  }

  // If timestamps lacked explicit hours, distribute across standard morning peak hours (8 AM - 12 PM)
  const totalMappedCalls = hours.reduce((s, h) => s + h.calls, 0);
  if (targetCalls.length > 0 && totalMappedCalls === 0) {
    const morningHours = [8, 9, 10, 11];
    targetCalls.forEach((c, idx) => {
      const assignedH = morningHours[idx % morningHours.length];
      const slot = hours.find((h) => h.hour === assignedH);
      if (slot) {
        slot.calls += 1;
        const isConn = didFarmerPickUpAndTalk(c) || Number(c.duration_sec || 0) > 0;
        if (isConn) {
          slot.connected += 1;
          const mins = Math.max(1, Math.ceil(Number(c.duration_sec || 60) / 60));
          slot.billedMinutes += mins;
          slot.spend = Math.round(slot.billedMinutes * rate * 100) / 100;
        }
      }
    });

    let distributedCum = 0;
    hours.forEach((h) => {
      distributedCum = Math.round((distributedCum + h.spend) * 100) / 100;
      h.cumulativeSpend = distributedCum;
      if (h.spend > peakSpend) {
        peakSpend = h.spend;
        peakHour = h.hour;
      }
    });
    runningCumulative = distributedCum;
  }

  const totalCalls = hours.reduce((s, h) => s + h.calls, 0);
  const totalConnected = hours.reduce((s, h) => s + h.connected, 0);
  const totalBilledMins = hours.reduce((s, h) => s + h.billedMinutes, 0);
  const activeHoursCount = hours.filter((h) => h.calls > 0).length || 1;
  const avgBurnRate = Math.round((runningCumulative / activeHoursCount) * 100) / 100;

  const currentH = new Date().getHours();
  const remainingHours = Math.max(0, endHour - currentH);
  const projectedEod = Math.round((runningCumulative + avgBurnRate * Math.min(remainingHours, 4)) * 100) / 100;

  return {
    isToday,
    targetDateLabel,
    hours,
    totalSpend: runningCumulative,
    totalCalls,
    totalConnected,
    totalBilledMins,
    peakHour,
    peakSpend,
    avgBurnRate,
    projectedEod,
  };
}

export const RealTimeCostChart = ({
  callLogs = [],
  rate = 3.5,
  isLive = false,
  onRefresh = null,
  embedded = false,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const [displayMode, setDisplayMode] = useState('cumulative'); // 'cumulative' | 'hourly'

  const telemetry = useMemo(() => {
    return computeHourlyTelemetry(callLogs, Number(rate || 3.5));
  }, [callLogs, rate]);

  const { hours, totalSpend, totalCalls, totalConnected, totalBilledMins, avgBurnRate, projectedEod } = telemetry;
  const n = hours.length;

  // Coordinate setup for clean responsive vector rendering
  const svgWidth = 660;
  const svgHeight = 220;
  const padLeft = 44;
  const padRight = 16;
  const padTop = 26;
  const padBottom = 34;
  const chartW = svgWidth - padLeft - padRight; // 600
  const chartH = svgHeight - padTop - padBottom; // 160

  const yMaxCumulative = useMemo(() => {
    const maxVal = Math.max(...hours.map((h) => h.cumulativeSpend), 15);
    return Math.ceil(maxVal * 1.2);
  }, [hours]);

  const yMaxHourly = useMemo(() => {
    const maxVal = Math.max(...hours.map((h) => h.spend), 5);
    return Math.ceil(maxVal * 1.25);
  }, [hours]);

  const yMax = displayMode === 'cumulative' ? yMaxCumulative : yMaxHourly;

  const slotW = chartW / n;

  // Build points for cumulative curve
  const points = hours.map((h, i) => {
    const x = padLeft + i * slotW + slotW / 2;
    const yVal = displayMode === 'cumulative' ? h.cumulativeSpend : h.spend;
    const y = padTop + chartH - ((yVal || 0) / (yMax || 1)) * chartH;
    return { x, y, hour: h, i };
  });

  const areaPath =
    points.length > 0
      ? `M ${points[0].x} ${padTop + chartH} L ${points.map((p) => `${p.x} ${p.y}`).join(' L ')} L ${points[points.length - 1].x} ${padTop + chartH} Z`
      : '';

  const linePath = points.length > 0 ? `M ${points.map((p) => `${p.x} ${p.y}`).join(' L ')}` : '';

  // Find latest active hour index
  const lastActiveIdx = useMemo(() => {
    for (let i = hours.length - 1; i >= 0; i--) {
      if (hours[i].calls > 0) return i;
    }
    return 0;
  }, [hours]);

  const lastActivePoint = points[lastActiveIdx];
  const hoveredHour = hoveredIdx !== null ? hours[hoveredIdx] : null;

  // Telephony pulse estimation:
  const voiceCost = totalSpend;
  const telephonyPulseRate = 0.5;
  const carriageCost = Math.round(totalBilledMins * telephonyPulseRate * 100) / 100;
  const totalCombined = voiceCost + carriageCost;

  const containerClass = embedded
    ? 'space-y-4'
    : 'bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-4 shadow-2xs';

  return (
    <div className={containerClass}>
      {/* Top Header Strip when standalone */}
      {!embedded && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
              <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Real-Time Telephony Cost Analytics
              </span>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-trust-green border border-emerald-200">
                {isLive ? 'Active Dispatcher' : 'Live Stream'}
              </span>
              {!telemetry.isToday && (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  {telemetry.targetDateLabel}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Real-time expenditure tracking: Sarvam Voice Agent AI (₹{Number(rate).toFixed(2)}/min) + carrier carriage pulses
            </p>
          </div>

          {/* Display mode buttons & Refresh */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <div className="inline-flex p-0.5 rounded-xl bg-slate-100 border border-slate-200/60">
              <button
                type="button"
                onClick={() => {
                  setDisplayMode('cumulative');
                  setHoveredIdx(null);
                }}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                  displayMode === 'cumulative'
                    ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Cumulative (₹)
              </button>
              <button
                type="button"
                onClick={() => {
                  setDisplayMode('hourly');
                  setHoveredIdx(null);
                }}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                  displayMode === 'hourly'
                    ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                Hourly Burn (₹)
              </button>
            </div>

            {onRefresh && (
              <button
                onClick={onRefresh}
                title="Refresh live telemetry"
                className="p-1.5 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 border border-slate-200/60 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Intraday Sub-bar when embedded */}
      {embedded && (
        <div className="flex items-center justify-between gap-2 pb-1">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <span className="font-semibold text-slate-800">Intraday Window:</span>
            <span>{telemetry.targetDateLabel} (06:00 – 21:00)</span>
          </div>
          <div className="inline-flex p-0.5 rounded-xl bg-slate-100 border border-slate-200/60">
            <button
              type="button"
              onClick={() => {
                setDisplayMode('cumulative');
                setHoveredIdx(null);
              }}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                displayMode === 'cumulative'
                  ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              Cumulative (₹)
            </button>
            <button
              type="button"
              onClick={() => {
                setDisplayMode('hourly');
                setHoveredIdx(null);
              }}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                displayMode === 'hourly'
                  ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              Hourly Burn (₹)
            </button>
          </div>
        </div>
      )}

      {/* 4 Quick Telemetry Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-3">
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total Spend</span>
            <Zap className="w-3.5 h-3.5 text-emerald-600" />
          </div>
          <div className="text-xl font-bold text-slate-900 mt-1">{rupees(totalSpend)}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            {totalBilledMins} billed mins ({totalConnected} of {totalCalls} answered)
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Avg Burn Rate</span>
            <Activity className="w-3.5 h-3.5 text-trust-green" />
          </div>
          <div className="text-xl font-bold text-trust-green mt-1">{rupees(avgBurnRate)}/hr</div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Peak: {rupees(telemetry.peakSpend)}/hr
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Effective Rate</span>
            <Clock className="w-3.5 h-3.5 text-trust-navy" />
          </div>
          <div className="text-xl font-bold text-trust-navy mt-1">{rupees(rate)}/min</div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Voice AI + ~₹0.50 pulse
          </div>
        </div>

        <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Projected EOD</span>
            <TrendingUp className="w-3.5 h-3.5 text-slate-600" />
          </div>
          <div className="text-xl font-bold text-slate-900 mt-1">{rupees(projectedEod)}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Based on active campaign pace
          </div>
        </div>
      </div>

      {/* Responsive SVG Intraday Real-Time Chart Area */}
      <div className="relative w-full">
        {/* Floating Tooltip */}
        {hoveredHour && (
          <div
            className="absolute top-1 z-20 pointer-events-none transition-all duration-100"
            style={{
              left: `${((padLeft + hoveredIdx * slotW + slotW / 2) / svgWidth) * 100}%`,
              transform:
                (padLeft + hoveredIdx * slotW + slotW / 2) / svgWidth < 0.25
                  ? 'translateX(0%)'
                  : (padLeft + hoveredIdx * slotW + slotW / 2) / svgWidth > 0.75
                  ? 'translateX(-100%)'
                  : 'translateX(-50%)',
            }}
          >
            <div className="bg-slate-900/95 text-white rounded-xl shadow-xl px-3.5 py-2.5 border border-slate-700 min-w-[190px] space-y-1.5 text-xs backdrop-blur-xs">
              <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                <span className="font-semibold text-slate-200">{hoveredHour.timeRange}</span>
                <span className="font-mono text-emerald-400 font-bold">{rupees(hoveredHour.cumulativeSpend)}</span>
              </div>
              <div className="space-y-1 text-[11px]">
                <div className="flex items-center justify-between text-slate-200">
                  <span>Hourly Spend:</span>
                  <span className="font-bold text-white">{rupees(hoveredHour.spend)}</span>
                </div>
                <div className="flex items-center justify-between text-slate-200">
                  <span>Cumulative Total:</span>
                  <span className="font-bold text-emerald-300">{rupees(hoveredHour.cumulativeSpend)}</span>
                </div>
                <div className="flex items-center justify-between text-slate-300 pt-0.5 border-t border-slate-800">
                  <span>Calls in Hour:</span>
                  <span className="font-semibold text-white">
                    {hoveredHour.calls} ({hoveredHour.connected} answered)
                  </span>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Billed Minutes:</span>
                  <span className="font-semibold text-amber-300">{hoveredHour.billedMinutes} mins</span>
                </div>
              </div>
            </div>
          </div>
        )}

        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto overflow-visible select-none"
        >
          <defs>
            <linearGradient id="realtimeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1E6F43" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#1E6F43" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Gridlines and Y-axis Labels */}
          {[0, 0.5, 1].map((pct) => {
            const yVal = padTop + chartH * (1 - pct);
            const label = Math.round(yMax * pct);
            return (
              <g key={`rt-grid-${pct}`}>
                <line
                  x1={padLeft}
                  y1={yVal}
                  x2={padLeft + chartW}
                  y2={yVal}
                  stroke="#F1F5F9"
                  strokeWidth="1"
                />
                <text
                  x={padLeft - 8}
                  y={yVal + 3}
                  textAnchor="end"
                  fill="#94A3B8"
                  fontSize="9"
                  fontWeight="500"
                >
                  ₹{label}
                </text>
              </g>
            );
          })}

          {/* X-axis baseline */}
          <line
            x1={padLeft}
            y1={padTop + chartH}
            x2={padLeft + chartW}
            y2={padTop + chartH}
            stroke="#CBD5E1"
            strokeWidth="1"
          />

          {/* Hourly Spend Volume Bars in background */}
          {hours.map((h, i) => {
            const xSlot = padLeft + i * slotW;
            const xCenter = xSlot + slotW / 2;
            const barW = Math.max(4, Math.min(18, slotW - 8));
            const barX = xCenter - barW / 2;
            const barH = h.spend > 0 ? Math.max(3, (h.spend / yMaxHourly) * (chartH * 0.75)) : 0;
            const barY = padTop + chartH - barH;
            const isHovered = hoveredIdx === i;

            return (
              <g key={`rt-bar-${h.hour}`}>
                {isHovered && (
                  <rect
                    x={xSlot + 1}
                    y={padTop}
                    width={slotW - 2}
                    height={chartH}
                    fill="#F8FAFC"
                    rx="4"
                  />
                )}
                {barH > 0 && (
                  <rect
                    x={barX}
                    y={barY}
                    width={barW}
                    height={barH}
                    fill="#0F2444"
                    fillOpacity={isHovered ? 0.7 : 0.25}
                    rx="2"
                    className="transition-all duration-150"
                  />
                )}
              </g>
            );
          })}

          {/* Gradient Area under Cumulative / Spend Curve */}
          {areaPath && <path d={areaPath} fill="url(#realtimeGradient)" />}

          {/* Line Path */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="#1E6F43"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Data Points */}
          {points.map((p) => {
            const isHovered = hoveredIdx === p.i;
            return (
              <circle
                key={`rt-dot-${p.hour.hour}`}
                cx={p.x}
                cy={p.y}
                r={isHovered ? 4.5 : 2.5}
                fill={isHovered ? '#0F2444' : '#1E6F43'}
                stroke="#FFFFFF"
                strokeWidth="1.5"
                className="transition-all duration-150"
              />
            );
          })}

          {/* Pulsing Live Beacon on Last Active Hour */}
          {lastActivePoint && lastActivePoint.hour.cumulativeSpend > 0 && (
            <g>
              <circle
                cx={lastActivePoint.x}
                cy={lastActivePoint.y}
                r="8"
                fill="#1E6F43"
                opacity="0.35"
                className="animate-ping"
              />
              <circle
                cx={lastActivePoint.x}
                cy={lastActivePoint.y}
                r="4.5"
                fill="#1E6F43"
                stroke="#FFFFFF"
                strokeWidth="1.5"
              />
            </g>
          )}

          {/* X-axis Hourly Labels */}
          {hours.map((h, i) => {
            const xSlot = padLeft + i * slotW;
            const xCenter = xSlot + slotW / 2;
            const isHovered = hoveredIdx === i;

            return (
              <text
                key={`rt-label-${h.hour}`}
                x={xCenter}
                y={padTop + chartH + 16}
                textAnchor="middle"
                fill={isHovered ? '#0F2444' : '#64748B'}
                fontSize="9"
                fontWeight={isHovered ? '700' : '500'}
              >
                {h.label}
              </text>
            );
          })}

          {/* Transparent Hover Hit Boxes */}
          {hours.map((h, i) => {
            const xSlot = padLeft + i * slotW;
            return (
              <rect
                key={`rt-hit-${h.hour}`}
                x={xSlot}
                y={padTop}
                width={slotW}
                height={chartH + padBottom}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
                onTouchStart={() => setHoveredIdx(i)}
              />
            );
          })}
        </svg>
      </div>

      {/* Chart Footer: Legend & Carrier Split Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 pt-2 border-t border-slate-100">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-trust-green inline-block shadow-2xs" />
            <span className="text-slate-700 font-medium">
              {displayMode === 'cumulative' ? 'Cumulative Spend (₹)' : 'Hourly Spend (₹)'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-xs bg-trust-navy/30 inline-block shadow-2xs" />
            <span className="text-slate-700 font-medium">Hourly Volume Bar</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse" />
            <span className="text-slate-700 font-medium">Live Active Pulse</span>
          </div>
        </div>

        <div className="text-[11px] text-slate-500 flex items-center gap-2">
          <span>Carrier pulse: <strong className="text-slate-700">{rupees(carriageCost)}</strong></span>
          <span>·</span>
          <span>Voice AI: <strong className="text-slate-700">{rupees(voiceCost)}</strong></span>
          <span>·</span>
          <span>Total: <strong className="text-slate-900">{rupees(totalCombined)}</strong></span>
        </div>
      </div>
    </div>
  );
};
