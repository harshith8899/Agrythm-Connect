import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, AlertTriangle, Info, PieChart } from 'lucide-react';
import { getUsage, saveUsageRate, didFarmerPickUpAndTalk, pulsesFor, telephonyAmount } from '../utils';
import { RealTimeCostChart } from './RealTimeCostChart';
import { DonutAnalyticsGrid } from './DonutAnalyticsGrid';

const rupees = (n) => `₹${Number(n || 0).toFixed(2)}`;

const pad2 = (n) => String(n).padStart(2, '0');
// The day as the person at the screen sees it (toISOString would give the UTC day: the wrong one in the early morning in India)
const localDateKey = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

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
    return localDateKey(parsed);
  }
  return '';
}

function generateSimulatedUsage(callLogs = [], rate = 3.5) {
  const dayMap = {};

  // Build a rolling 14-day date map ending today
  const today = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = localDateKey(d);
    dayMap[key] = { date: key, calls: 0, connected: 0, billed_minutes: 0, amount: 0, telephony_pulses: 0, telephony_amount: 0 };
  }

  // Aggregate stats from local callLogs
  (callLogs || []).forEach((call) => {
    if (call.is_test) return;
    const dateKey = getCallDateKey(call);
    if (!dateKey) return;

    if (!dayMap[dateKey]) {
      dayMap[dateKey] = { date: dateKey, calls: 0, connected: 0, billed_minutes: 0, amount: 0, telephony_pulses: 0, telephony_amount: 0 };
    }

    const day = dayMap[dateKey];
    day.calls += 1;

    const isConnected =
      didFarmerPickUpAndTalk(call) ||
      ['completed', 'delivered', 'connected', 'answered'].includes(
        String(call.call_status || call.status || '').toLowerCase()
      ) ||
      Number(call.duration_sec || call.duration || 0) > 0;

    if (isConnected) {
      day.connected += 1;
      const sec = Number(call.duration_sec ?? call.duration ?? 0);
      const mins = Math.max(1, Math.ceil(sec / 60));
      day.billed_minutes += mins;
      day.amount = Math.round(day.billed_minutes * rate * 100) / 100;
      day.telephony_pulses += pulsesFor(sec);
      day.telephony_amount = telephonyAmount(day.telephony_pulses);
    }
  });

  const sortedDescending = Object.values(dayMap).sort((a, b) => b.date.localeCompare(a.date));
  const days = sortedDescending.slice(0, 14);

  const todayStr = localDateKey(today);
  const todayTotals = dayMap[todayStr] || { calls: 0, connected: 0, billed_minutes: 0, amount: 0, telephony_pulses: 0, telephony_amount: 0 };

  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - 6); // today and the 6 days before it
  const weekStartKey = localDateKey(weekStart);
  const weekCalls = days.filter((d) => d.date >= weekStartKey);
  const weekTotals = {
    calls: weekCalls.reduce((s, d) => s + d.calls, 0),
    connected: weekCalls.reduce((s, d) => s + d.connected, 0),
    billed_minutes: weekCalls.reduce((s, d) => s + d.billed_minutes, 0),
    amount: Math.round(weekCalls.reduce((s, d) => s + d.amount, 0) * 100) / 100,
    telephony_pulses: weekCalls.reduce((s, d) => s + d.telephony_pulses, 0),
    telephony_amount: Math.round(weekCalls.reduce((s, d) => s + d.telephony_amount, 0) * 100) / 100,
  };

  const windowTotals = {
    calls: days.reduce((s, d) => s + d.calls, 0),
    connected: days.reduce((s, d) => s + d.connected, 0),
    billed_minutes: days.reduce((s, d) => s + d.billed_minutes, 0),
    amount: Math.round(days.reduce((s, d) => s + d.amount, 0) * 100) / 100,
    telephony_pulses: days.reduce((s, d) => s + d.telephony_pulses, 0),
    telephony_amount: Math.round(days.reduce((s, d) => s + d.telephony_amount, 0) * 100) / 100,
  };

  return {
    configured: false,
    isSimulated: true,
    error: '',
    exhausted: false,
    today: todayTotals,
    week: weekTotals,
    window: windowTotals,
    window_days: 14,
    days,
    rate,
    currency: 'INR',
    note: 'Simulated usage calculated from local farmer call history records at the configured rate.',
  };
}

function formatDayLabel(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[parseInt(parts[1], 10) - 1] || parts[1];
    const day = parseInt(parts[2], 10);
    return `${day} ${month}`;
  }
  return dateStr;
}

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

const UsageCell = ({ title, data }) => (
  <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
    <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">{title}</div>
    <div className="text-2xl font-bold text-slate-900 mt-1">{data ? rupees(data.amount) : '-'}</div>
    <div className="text-[11px] text-slate-500">
      {data ? `${data.billed_minutes} billed minutes, ${data.calls} calls (${data.connected} connected)` : ''}
    </div>
  </div>
);

const CostEfficiencyStrip = ({ usage }) => {
  const windowData = usage?.window || {
    calls: (usage?.days || []).reduce((s, d) => s + d.calls, 0),
    connected: (usage?.days || []).reduce((s, d) => s + d.connected, 0),
    billed_minutes: (usage?.days || []).reduce((s, d) => s + d.billed_minutes, 0),
    amount: (usage?.days || []).reduce((s, d) => s + d.amount, 0),
    telephony_pulses: (usage?.days || []).reduce((s, d) => s + (d.telephony_pulses || 0), 0),
    telephony_amount: (usage?.days || []).reduce((s, d) => s + (d.telephony_amount || 0), 0),
  };

  const totalCalls = windowData.calls || 0;
  const connected = windowData.connected || 0;
  const unanswered = Math.max(0, totalCalls - connected);
  const answerRate = totalCalls > 0 ? (connected / totalCalls) * 100 : 0;
  const effectiveCostPerConnected = connected > 0 ? windowData.amount / connected : 0;
  const billedMins = windowData.billed_minutes || 0;
  const avgMinsPerCall = connected > 0 ? (billedMins / connected).toFixed(1) : '0.0';

  // Sarvam voice agent (started minutes at the plan rate) plus Sarvam telephony (Rs 0.20 per started 30-second pulse of connected
  // calls). Both are Sarvam's own rates, before GST; they come from Sarvam's call records when Sarvam is set up.
  const rate = Number(usage?.rate || 3.5);
  const voiceCost = windowData.amount || billedMins * rate;
  const telephonyPulses = windowData.telephony_pulses ?? billedMins * 2;      // an upper bound when the pulses are not known
  const telephonyCost = windowData.telephony_amount ?? telephonyAmount(telephonyPulses);
  const totalTelephonyCombined = voiceCost + telephonyCost;
  const voiceSharePct = totalTelephonyCombined > 0 ? Math.round((voiceCost / totalTelephonyCombined) * 100) : 88;
  const carriageSharePct = 100 - voiceSharePct;

  return (
    <div className="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
        <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
          Cost Efficiency & Telephony Pulse Analysis
        </span>
        <span className="text-[11px] text-slate-500">
          Aggregated across {totalCalls} calls ({usage?.window_days || 14}-day window). Telephony is Sarvam's rate, ₹0.20 per started 30 seconds of a connected call; all prices are before GST.
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
        {/* Metric 1: Answer Rate */}
        <div className="bg-white rounded-xl p-3.5 border border-slate-100 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Answer Rate</span>
              <span className="text-base font-bold text-trust-green">{answerRate.toFixed(1)}%</span>
            </div>
            {/* Visual breakdown bar */}
            <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden flex mt-2.5">
              <div
                className="h-full bg-trust-green transition-all duration-300"
                style={{ width: `${answerRate}%` }}
                title={`Connected: ${connected} calls (${answerRate.toFixed(1)}%)`}
              />
              <div
                className="h-full bg-slate-200 transition-all duration-300"
                style={{ width: `${100 - answerRate}%` }}
                title={`Unanswered/Failed: ${unanswered} calls`}
              />
            </div>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-50">
            <span className="text-trust-green font-semibold">{connected} connected</span>
            <span className="text-slate-400">{unanswered} unanswered / failed</span>
          </div>
        </div>

        {/* Metric 2: Effective Cost per Connected Call */}
        <div className="bg-white rounded-xl p-3.5 border border-slate-100 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Cost / Connected Call</span>
              <span className="text-base font-bold text-slate-900">{rupees(effectiveCostPerConnected)}</span>
            </div>
            <div className="text-[11px] text-slate-600 mt-2">
              Across <strong className="text-slate-900">{billedMins}</strong> total billed minutes
            </div>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-50">
            <span className="text-slate-600">Avg duration:</span>
            <span className="font-semibold text-slate-800">{avgMinsPerCall} min / connected call</span>
          </div>
        </div>

        {/* Metric 3: Cost Split Breakdown */}
        <div className="bg-white rounded-xl p-3.5 border border-slate-100 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Cost Split Breakdown</span>
              <span className="text-[11px] font-bold text-slate-700">{rupees(totalTelephonyCombined)} est.</span>
            </div>
            {/* Visual two-tone split bar */}
            <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden flex mt-2.5">
              <div
                className="h-full bg-trust-green transition-all duration-300"
                style={{ width: `${voiceSharePct}%` }}
                title={`Sarvam Voice Agent: ${voiceSharePct}%`}
              />
              <div
                className="h-full bg-trust-navy transition-all duration-300"
                style={{ width: `${carriageSharePct}%` }}
                title={`Sarvam telephony: ${carriageSharePct}%`}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[10px] text-slate-600 mt-2.5 pt-2 border-t border-slate-50">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-trust-green inline-block shrink-0" />
              Voice AI: <strong className="text-slate-800">{rupees(voiceCost)}</strong>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-trust-navy inline-block shrink-0" />
              Telephony ({telephonyPulses} × ₹0.20): <strong className="text-slate-800">{rupees(telephonyCost)}</strong>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

const InteractiveUsageChart = ({ days = [], rate = 3.5, isSimulated = false, callLogs = [] }) => {
  const [chartView, setChartView] = useState('realtime'); // 'realtime' | 'donuts' | 'volume' | 'cost'
  const [hoveredIdx, setHoveredIdx] = useState(null);

  const chronologicalDays = useMemo(() => {
    if (!days || !days.length) return [];
    return [...days].sort((a, b) => a.date.localeCompare(b.date));
  }, [days]);

  const n = chronologicalDays.length;

  // Coordinate setup for clean responsive vector rendering
  const svgWidth = 660;
  const svgHeight = 220;
  const padLeft = 40;
  const padRight = 16;
  const padTop = 26;
  const padBottom = 34;
  const chartW = svgWidth - padLeft - padRight; // 604
  const chartH = svgHeight - padTop - padBottom; // 160

  const maxCalls = useMemo(() => {
    return Math.max(...chronologicalDays.map((d) => d.calls), 4);
  }, [chronologicalDays]);
  const yMaxCalls = Math.ceil(maxCalls * 1.15);

  const maxAmount = useMemo(() => {
    return Math.max(...chronologicalDays.map((d) => d.amount), 10);
  }, [chronologicalDays]);
  const yMaxAmount = Math.ceil(maxAmount * 1.2);

  const avgAmount = useMemo(() => {
    if (!chronologicalDays.length) return 0;
    const sum = chronologicalDays.reduce((acc, d) => acc + Number(d.amount || 0), 0);
    return sum / chronologicalDays.length;
  }, [chronologicalDays]);
  const avgY = padTop + chartH - (avgAmount / (yMaxAmount || 1)) * chartH;

  const slotW = chartW / (n || 1);

  // Build points for cost area and line
  const costPoints = chronologicalDays.map((d, i) => {
    const x = padLeft + i * slotW + slotW / 2;
    const y = padTop + chartH - ((d.amount || 0) / (yMaxAmount || 1)) * chartH;
    return { x, y, day: d, i };
  });

  const areaPath =
    costPoints.length > 0
      ? `M ${costPoints[0].x} ${padTop + chartH} L ${costPoints.map((p) => `${p.x} ${p.y}`).join(' L ')} L ${costPoints[costPoints.length - 1].x} ${padTop + chartH} Z`
      : '';

  const linePath = costPoints.length > 0 ? `M ${costPoints.map((p) => `${p.x} ${p.y}`).join(' L ')}` : '';

  const hoveredDay = hoveredIdx !== null ? chronologicalDays[hoveredIdx] : null;

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-4">
      {/* Top Header & Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          {chartView === 'realtime' && (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
          )}
          <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            {chartView === 'realtime'
              ? 'Real-Time Intraday Cost Analytics'
              : chartView === 'donuts'
              ? 'Categorical Donut & Pie Analytics'
              : chartView === 'volume'
              ? 'Daily Call Volume & Connectivity'
              : 'Daily Cost Trend (₹)'}
          </span>
          {chartView !== 'realtime' && chartView !== 'donuts' && (
            <span className="text-[11px] font-medium text-slate-400">(last {n} days with calls)</span>
          )}
          {isSimulated && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
              Simulated Data
            </span>
          )}
        </div>

        {/* View toggle buttons */}
        <div className="inline-flex flex-wrap p-1 rounded-xl bg-slate-100 border border-slate-200/60 self-start sm:self-auto gap-0.5">
          <button
            type="button"
            onClick={() => {
              setChartView('realtime');
              setHoveredIdx(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'realtime'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            Real-Time Intraday (₹)
          </button>
          <button
            type="button"
            onClick={() => {
              setChartView('donuts');
              setHoveredIdx(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'donuts'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <PieChart className="w-3.5 h-3.5 text-trust-green" />
            Pie & Donut Charts
          </button>
          <button
            type="button"
            onClick={() => {
              setChartView('volume');
              setHoveredIdx(null);
            }}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'volume'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            Daily Volume
          </button>
          <button
            type="button"
            onClick={() => {
              setChartView('cost');
              setHoveredIdx(null);
            }}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'cost'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            Cost Trend
          </button>
        </div>
      </div>

      {/* 1. Real-Time Intraday View */}
      {chartView === 'realtime' && (
        <RealTimeCostChart
          callLogs={callLogs}
          rate={rate}
          isLive={true}
          embedded={true}
        />
      )}

      {/* 2. Categorical Donut & Pie Analytics View */}
      {chartView === 'donuts' && (
        <DonutAnalyticsGrid
          callLogs={callLogs}
          rate={rate}
          embedded={true}
        />
      )}

      {/* 3 & 4. 14-Day Chronological Daily Charts */}
      {chartView !== 'realtime' && chartView !== 'donuts' && (
        <>
          {n === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-slate-100">
              No daily call telemetry available to chart.
            </div>
          ) : (
            <>
              {/* Responsive SVG Chart Area */}
              <div className="relative w-full">
                {/* Floating Tooltip */}
                {hoveredDay && (
                  <div
                    className="absolute top-1 z-20 pointer-events-none"
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
                    <div className="bg-slate-900/95 text-white rounded-xl shadow-xl px-3.5 py-2.5 border border-slate-700 min-w-[185px] space-y-1.5 text-xs backdrop-blur-xs">
                      <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                        <span className="font-semibold text-slate-200">{formatFullDate(hoveredDay.date)}</span>
                        <span className="font-mono text-emerald-400 font-bold">{rupees(hoveredDay.amount)}</span>
                      </div>
                      <div className="space-y-1 text-[11px]">
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1.5 text-slate-300">
                            <span className="w-2.5 h-2.5 rounded-xs bg-trust-navy inline-block border border-slate-500" />
                            Total Calls:
                          </span>
                          <span className="font-bold text-white">{hoveredDay.calls}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1.5 text-slate-300">
                            <span className="w-2.5 h-2.5 rounded-xs bg-trust-green inline-block" />
                            Connected:
                          </span>
                          <span className="font-bold text-emerald-400">{hoveredDay.connected}</span>
                        </div>
                        <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-[10px] text-slate-400">
                          <span>Billed: {hoveredDay.billed_minutes} mins</span>
                          <span>
                            {hoveredDay.calls > 0
                              ? `${Math.round((hoveredDay.connected / hoveredDay.calls) * 100)}% conn`
                              : '0%'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* SVG Visual Canvas */}
                <svg
                  viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                  className="w-full h-auto overflow-visible select-none"
                  style={{ maxHeight: '240px' }}
                >
                  <defs>
                    <linearGradient id="costGradientMerged" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1E6F43" stopOpacity="0.28" />
                      <stop offset="100%" stopColor="#1E6F43" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal Guide Lines */}
                  {chartView === 'volume' ? (
                    <>
                      {[0, 0.5, 1].map((pct) => {
                        const yVal = padTop + chartH * (1 - pct);
                        const label = Math.round(yMaxCalls * pct);
                        return (
                          <g key={`grid-vol-${pct}`}>
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
                              {label}
                            </text>
                          </g>
                        );
                      })}
                    </>
                  ) : (
                    <>
                      {[0, 0.5, 1].map((pct) => {
                        const yVal = padTop + chartH * (1 - pct);
                        const label = Math.round(yMaxAmount * pct);
                        return (
                          <g key={`grid-cost-${pct}`}>
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
                    </>
                  )}

                  {/* X Axis Baseline */}
                  <line
                    x1={padLeft}
                    y1={padTop + chartH}
                    x2={padLeft + chartW}
                    y2={padTop + chartH}
                    stroke="#CBD5E1"
                    strokeWidth="1"
                  />

                  {/* CHART VIEW 1: Volume & Connectivity (Grouped Bars) */}
                  {chartView === 'volume' && (
                    <>
                      {chronologicalDays.map((d, i) => {
                        const xSlot = padLeft + i * slotW;
                        const xCenter = xSlot + slotW / 2;
                        const barW = Math.max(3, Math.min(13, (slotW - 8) / 2));

                        const totalH = d.calls > 0 ? Math.max(3, (d.calls / yMaxCalls) * chartH) : 0;
                        const connH = d.connected > 0 ? Math.max(3, (d.connected / yMaxCalls) * chartH) : 0;

                        const totalX = xCenter - barW - 1;
                        const connX = xCenter + 1;
                        const totalY = padTop + chartH - totalH;
                        const connY = padTop + chartH - connH;

                        const isHovered = hoveredIdx === i;

                        return (
                          <g key={`bars-${d.date}`} className="transition-all duration-150">
                            {/* Hover background column */}
                            {isHovered && (
                              <rect
                                x={xSlot + 1}
                                y={padTop}
                                width={slotW - 2}
                                height={chartH}
                                fill="#F1F5F9"
                                rx="4"
                                opacity="0.7"
                              />
                            )}

                            {/* Total Calls Bar (#0F2444 Navy) */}
                            {totalH > 0 && (
                              <rect
                                x={totalX}
                                y={totalY}
                                width={barW}
                                height={totalH}
                                fill="#0F2444"
                                rx="2"
                                opacity={isHovered ? 1 : 0.85}
                                className="transition-all duration-150"
                              />
                            )}

                            {/* Connected Calls Bar (#1E6F43 Emerald Green) */}
                            {connH > 0 && (
                              <rect
                                x={connX}
                                y={connY}
                                width={barW}
                                height={connH}
                                fill="#1E6F43"
                                rx="2"
                                opacity={isHovered ? 1 : 0.9}
                                className="transition-all duration-150"
                              />
                            )}
                          </g>
                        );
                      })}
                    </>
                  )}

                  {/* CHART VIEW 2: Cost Trend Area Chart (₹) */}
                  {chartView === 'cost' && (
                    <>
                      {/* Gradient fill area */}
                      {areaPath && <path d={areaPath} fill="url(#costGradientMerged)" />}

                      {/* Vertical highlight on hover */}
                      {hoveredIdx !== null && costPoints[hoveredIdx] && (
                        <line
                          x1={costPoints[hoveredIdx].x}
                          y1={padTop}
                          x2={costPoints[hoveredIdx].x}
                          y2={padTop + chartH}
                          stroke="#CBD5E1"
                          strokeWidth="1"
                          strokeDasharray="3 3"
                        />
                      )}

                      {/* Cost trend bars (subtle background volume) */}
                      {chronologicalDays.map((d, i) => {
                        const xSlot = padLeft + i * slotW;
                        const barW = Math.max(4, Math.min(18, slotW - 6));
                        const x = xSlot + (slotW - barW) / 2;
                        const barH = d.amount > 0 ? Math.max(3, (d.amount / yMaxAmount) * chartH) : 0;
                        const y = padTop + chartH - barH;
                        const isHovered = hoveredIdx === i;

                        return (
                          <g key={`cost-bar-${d.date}`}>
                            {isHovered && (
                              <rect
                                x={xSlot + 1}
                                y={padTop}
                                width={slotW - 2}
                                height={chartH}
                                fill="#F1F5F9"
                                rx="4"
                                opacity="0.6"
                              />
                            )}
                            {barH > 0 && (
                              <rect
                                x={x}
                                y={y}
                                width={barW}
                                height={barH}
                                fill="#1E6F43"
                                rx="2"
                                opacity={isHovered ? 0.45 : 0.22}
                                className="transition-opacity duration-150"
                              />
                            )}
                          </g>
                        );
                      })}

                      {/* Stroke trend line */}
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

                      {/* Data points */}
                      {costPoints.map((p) => (
                        <circle
                          key={`dot-${p.day.date}`}
                          cx={p.x}
                          cy={p.y}
                          r={hoveredIdx === p.i ? 4.5 : 3}
                          fill={hoveredIdx === p.i ? '#0F2444' : '#1E6F43'}
                          stroke="#FFFFFF"
                          strokeWidth="1.5"
                          className="transition-all duration-150"
                        />
                      ))}

                      {/* Dashed Average Daily Spend Reference Line */}
                      {avgY >= padTop && avgY <= padTop + chartH && (
                        <g>
                          <line
                            x1={padLeft}
                            y1={avgY}
                            x2={padLeft + chartW}
                            y2={avgY}
                            stroke="#94A3B8"
                            strokeWidth="1.5"
                            strokeDasharray="4 4"
                          />
                          <text
                            x={padLeft + chartW}
                            y={Math.max(padTop + 10, avgY - 5)}
                            textAnchor="end"
                            fill="#64748B"
                            fontSize="9"
                            fontWeight="600"
                          >
                            Avg: {rupees(avgAmount)}/day
                          </text>
                        </g>
                      )}
                    </>
                  )}

                  {/* X Axis Date Labels */}
                  {chronologicalDays.map((d, i) => {
                    const xSlot = padLeft + i * slotW;
                    const xCenter = xSlot + slotW / 2;
                    const isHovered = hoveredIdx === i;

                    return (
                      <text
                        key={`lbl-${d.date}`}
                        x={xCenter}
                        y={padTop + chartH + 18}
                        textAnchor="middle"
                        fill={isHovered ? '#0F2444' : '#64748B'}
                        fontWeight={isHovered ? '700' : '500'}
                        fontSize="9"
                        className="transition-colors duration-150"
                      >
                        {formatDayLabel(d.date)}
                      </text>
                    );
                  })}

                  {/* Transparent Interactive Overlay Rectangles */}
                  {chronologicalDays.map((d, i) => {
                    const xSlot = padLeft + i * slotW;
                    return (
                      <rect
                        key={`hit-${d.date}`}
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

              {/* Chart Legend & Telemetry Guide */}
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 pt-2 border-t border-slate-100">
                {chartView === 'volume' ? (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-navy inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Total Calls ({maxCalls} peak)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-green inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Connected Calls</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-green inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Daily Spend (₹)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-4 h-0.5 border-t-2 border-dashed border-slate-400 inline-block" />
                      <span className="text-slate-600 font-medium">Average ({rupees(avgAmount)}/day)</span>
                    </div>
                  </div>
                )}
                <div className="text-[11px] text-slate-400">
                  Hover or tap any day to inspect exact duration, connectivity and spend
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

// Everything about money: Sarvam usage and the estimated amount, answer rate, the charts (hourly, daily, pie and donut) and the
// daily table. Reads /api/usage (Sarvam's own call records). Without Sarvam set up it works from the calls on this dashboard.
export const CostAnalyticsView = ({ isBackendOnline = true, callLogs = [] }) => {
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rateInput, setRateInput] = useState('');
  const [rateMessage, setRateMessage] = useState(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const use = await getUsage(refresh);
      setUsage(use);
      setRateInput((prev) => (prev === '' ? String(use.rate) : prev));
      setError('');
    } catch (err) {
      setError(err.message || 'Could not reach the backend');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(false);
    const timer = setInterval(() => load(false), 60000);
    return () => clearInterval(timer);
  }, [load]);

  const handleSaveRate = async () => {
    setRateMessage(null);
    try {
      const updated = await saveUsageRate(Number(rateInput));
      setUsage(updated);
      setRateInput(String(updated.rate));
      setRateMessage({ ok: true, text: 'Rate saved.' });
    } catch (err) {
      setRateMessage({ ok: false, text: err.message });
    }
  };

  const activeUsage = useMemo(() => {
    if (usage && usage.configured) return { ...usage, isSimulated: false };
    if (!usage && !error) return null;
    const rate = Number(rateInput) || (usage && usage.rate) || 3.5;
    return generateSimulatedUsage(callLogs, rate);
  }, [usage, error, callLogs, rateInput]);

  const noCalls = activeUsage && activeUsage.window && (activeUsage.days || []).length === 0;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Cost Analytics</span>
          <h2 className="text-xl font-bold text-slate-900">Usage, spend and answer rate</h2>
          <p className="text-xs text-slate-500 mt-0.5">{error || 'Sarvam usage, cost split, daily and hourly charts, and the daily table.'}</p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={loading || !isBackendOnline}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* 4. Sarvam Usage & Telephony Cost Analytics */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-4">
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Sarvam Usage & Telephony Cost</span>
              {activeUsage?.isSimulated && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  Estimated from this dashboard
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Counted from Sarvam's call records, the way Sarvam bills: started 60-second minutes of connected calls.
            </p>
          </div>
        </div>

        {usage && usage.exhausted && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Sarvam has reported that credits are used up in the last 7 days. Add credits on Sarvam (Settings,
              Billing); calls resume at once.
            </span>
          </div>
        )}

        {activeUsage?.isSimulated && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-50/70 border border-amber-200/80 text-amber-800 text-xs">
            <Info className="w-4 h-4 shrink-0 text-amber-600" />
            <span>
              Sarvam is not set up on this backend, so the figures below are worked out from the {callLogs.length} calls
              shown on this dashboard.
            </span>
          </div>
        )}

        {usage && usage.configured && usage.error && (
          <p className="text-xs text-rose-700">Could not read usage from Sarvam: {usage.error}</p>
        )}

        {!activeUsage && !error && <p className="text-xs text-slate-500">Loading usage...</p>}

        {activeUsage && activeUsage.window && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <UsageCell title="Today" data={activeUsage.today} />
              <UsageCell title="Last 7 days" data={activeUsage.week} />
              <UsageCell title={`Last ${activeUsage.window_days || 14} days`} data={activeUsage.window} />
            </div>

            <CostEfficiencyStrip usage={activeUsage} />

            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 bg-slate-50 p-3 rounded-xl border border-slate-100">
              <label htmlFor="rate" className="font-semibold text-slate-700">
                Rate per billed minute (₹)
              </label>
              <input
                id="rate"
                type="number"
                min="0"
                step="0.05"
                value={rateInput}
                onChange={(e) => setRateInput(e.target.value)}
                className="w-24 px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs font-medium focus:ring-1 focus:ring-trust-navy focus:outline-hidden"
              />
              <button
                onClick={handleSaveRate}
                className="px-3 py-1 rounded-lg bg-trust-navy text-white font-semibold hover:bg-slate-800 transition-colors cursor-pointer text-xs"
              >
                Save rate
              </button>
              {rateMessage && (
                <span className={rateMessage.ok ? 'text-emerald-700 font-semibold text-xs' : 'text-rose-700 font-semibold text-xs'}>
                  {rateMessage.text}
                </span>
              )}
              <span className="text-slate-400 text-[11px] ml-auto">
                Sarvam pay-as-you-go is ₹3.50 (Pro 3.25, Growth 3.15), before GST.
              </span>
            </div>

            {noCalls ? (
              <p className="p-6 text-center text-xs text-slate-500 bg-slate-50 rounded-xl border border-slate-100">
                No calls in the last {activeUsage.window_days || 60} days, so there is nothing to chart yet.
              </p>
            ) : (
              <>
                <p className="text-[11px] text-slate-500">
                  The hourly chart below is built from the calls listed on the Call Logs tab (test calls left out), so it can differ from
                  Sarvam's totals above, which count every call Sarvam placed.
                </p>
                <InteractiveUsageChart
                  days={activeUsage.days || []}
                  rate={Number(activeUsage.rate || 3.5)}
                  isSimulated={Boolean(activeUsage.isSimulated)}
                  callLogs={callLogs}
                />
              </>
            )}

            {!noCalls && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                      <th className="py-2.5 pr-4">Day</th>
                      <th className="py-2.5 pr-4">Calls</th>
                      <th className="py-2.5 pr-4">Connected</th>
                      <th className="py-2.5 pr-4">Billed minutes</th>
                      <th className="py-2.5">Amount (estimate)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(activeUsage.days || []).map((day) => (
                      <tr key={day.date} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-2.5 pr-4 font-medium text-slate-700">{formatDayLabel(day.date)}</td>
                        <td className="py-2.5 pr-4 font-mono">{day.calls}</td>
                        <td className="py-2.5 pr-4 font-mono text-trust-green font-semibold">{day.connected}</td>
                        <td className="py-2.5 pr-4 font-mono">{day.billed_minutes}</td>
                        <td className="py-2.5 font-mono font-bold text-slate-900">{rupees(day.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
