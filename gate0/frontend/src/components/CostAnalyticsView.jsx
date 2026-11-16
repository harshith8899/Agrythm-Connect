import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, AlertTriangle, Info, PieChart, Table, BarChart3 } from 'lucide-react';
import { getUsage, saveUsageRate, didFarmerPickUpAndTalk } from '../utils';
import { RealTimeCostChart } from './RealTimeCostChart';
import { DonutAnalyticsGrid } from './DonutAnalyticsGrid';

const rupees = (n) => `₹${Number(n || 0).toFixed(2)}`;

const pad2 = (n) => String(n).padStart(2, '0');
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

function generateSimulatedUsage(callLogs = [], rate = 3.5, messageRate = 0.2) {
  const dayMap = {};

  const today = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = localDateKey(d);
    dayMap[key] = {
      date: key,
      calls: 0,
      total_attempts: 0,
      connected: 0,
      billed_minutes: 0,
      voice_amount: 0,
      messages_sent: 0,
      message_amount: 0,
      amount: 0,
      targetedSet: new Set(),
      reachedSet: new Set(),
      farmers_targeted: 0,
      farmers_reached: 0,
      retries: 0,
    };
  }

  (callLogs || []).forEach((call) => {
    if (call.is_test) return;
    const dateKey = getCallDateKey(call);
    if (!dateKey) return;

    if (!dayMap[dateKey]) {
      dayMap[dateKey] = {
        date: dateKey,
        calls: 0,
        total_attempts: 0,
        connected: 0,
        billed_minutes: 0,
        voice_amount: 0,
        messages_sent: 0,
        message_amount: 0,
        amount: 0,
        targetedSet: new Set(),
        reachedSet: new Set(),
        farmers_targeted: 0,
        farmers_reached: 0,
        retries: 0,
      };
    }

    const day = dayMap[dateKey];
    day.total_attempts += 1;
    day.calls += 1;

    // 1 advisory SMS / WhatsApp message sent per call outreach
    const msgs = Number(call.messages_sent ?? call.sms_count ?? 1);
    day.messages_sent += msgs;

    const farmerId = String(call.farmer_id || call.phone || call.Farmer_Name || call.name || '').trim();
    if (farmerId) {
      day.targetedSet.add(farmerId);
    }

    const isConnected =
      didFarmerPickUpAndTalk(call) ||
      ['completed', 'delivered', 'connected', 'answered'].includes(
        String(call.call_status || call.status || '').toLowerCase()
      ) ||
      Number(call.duration_sec || call.duration || 0) > 0;

    if (isConnected) {
      day.connected += 1;
      if (farmerId) {
        day.reachedSet.add(farmerId);
      }
      const sec = Number(call.duration_sec ?? call.duration ?? 0);
      const mins = Math.max(1, Math.ceil(sec / 60));
      day.billed_minutes += mins;
    }
  });

  Object.values(dayMap).forEach((day) => {
    day.farmers_targeted = day.targetedSet.size || day.calls;
    day.farmers_reached = day.reachedSet.size || day.connected;
    day.retries = Math.max(0, day.total_attempts - day.farmers_targeted);
    day.voice_amount = Math.round(day.billed_minutes * rate * 100) / 100;
    day.message_amount = Math.round(day.messages_sent * messageRate * 100) / 100;
    day.amount = Math.round((day.voice_amount + day.message_amount) * 100) / 100;
    delete day.targetedSet;
    delete day.reachedSet;
  });

  const sortedDescending = Object.values(dayMap).sort((a, b) => b.date.localeCompare(a.date));
  const days = sortedDescending.slice(0, 14);

  const todayStr = localDateKey(today);
  const todayTotals = dayMap[todayStr] || {
    calls: 0,
    total_attempts: 0,
    connected: 0,
    billed_minutes: 0,
    voice_amount: 0,
    messages_sent: 0,
    message_amount: 0,
    amount: 0,
    farmers_targeted: 0,
    farmers_reached: 0,
    retries: 0,
  };

  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - 6);
  const weekStartKey = localDateKey(weekStart);
  const weekCalls = days.filter((d) => d.date >= weekStartKey);
  const weekTotals = {
    calls: weekCalls.reduce((s, d) => s + d.calls, 0),
    total_attempts: weekCalls.reduce((s, d) => s + (d.total_attempts || d.calls), 0),
    connected: weekCalls.reduce((s, d) => s + d.connected, 0),
    farmers_targeted: weekCalls.reduce((s, d) => s + (d.farmers_targeted || 0), 0),
    farmers_reached: weekCalls.reduce((s, d) => s + (d.farmers_reached || 0), 0),
    retries: weekCalls.reduce((s, d) => s + (d.retries || 0), 0),
    billed_minutes: weekCalls.reduce((s, d) => s + d.billed_minutes, 0),
    voice_amount: Math.round(weekCalls.reduce((s, d) => s + (d.voice_amount || 0), 0) * 100) / 100,
    messages_sent: weekCalls.reduce((s, d) => s + (d.messages_sent || 0), 0),
    message_amount: Math.round(weekCalls.reduce((s, d) => s + (d.message_amount || 0), 0) * 100) / 100,
    amount: Math.round(weekCalls.reduce((s, d) => s + d.amount, 0) * 100) / 100,
  };

  const windowTotals = {
    calls: days.reduce((s, d) => s + d.calls, 0),
    total_attempts: days.reduce((s, d) => s + (d.total_attempts || d.calls), 0),
    connected: days.reduce((s, d) => s + d.connected, 0),
    farmers_targeted: days.reduce((s, d) => s + (d.farmers_targeted || 0), 0),
    farmers_reached: days.reduce((s, d) => s + (d.farmers_reached || 0), 0),
    retries: days.reduce((s, d) => s + (d.retries || 0), 0),
    billed_minutes: days.reduce((s, d) => s + d.billed_minutes, 0),
    voice_amount: Math.round(days.reduce((s, d) => s + (d.voice_amount || 0), 0) * 100) / 100,
    messages_sent: days.reduce((s, d) => s + (d.messages_sent || 0), 0),
    message_amount: Math.round(days.reduce((s, d) => s + (d.message_amount || 0), 0) * 100) / 100,
    amount: Math.round(days.reduce((s, d) => s + d.amount, 0) * 100) / 100,
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
    messageRate,
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

export const InteractiveUsageChart = ({
  days = [],
  rate = 3.5,
  messageRate = 0.2,
  isSimulated = false,
  callLogs = [],
  timeframe = '14d',
  onTimeframeChange,
  customDate = '',
  onCustomDateChange,
}) => {
  // Primary view switcher: Breakdown | Intraday Activity | Daily Trends | Daily Table
  const [chartView, setChartView] = useState('breakdown'); // 'breakdown' | 'realtime' | 'daily' | 'table'
  const [dailyMetric, setDailyMetric] = useState('reach'); // 'reach' (Unique Farmer Reach) | 'spend'
  const [hoveredIdx, setHoveredIdx] = useState(null);

  const chronologicalDays = useMemo(() => {
    if (!days || !days.length) return [];
    return [...days].sort((a, b) => a.date.localeCompare(b.date));
  }, [days]);

  const n = chronologicalDays.length;

  const svgWidth = 660;
  const svgHeight = 220;
  const padLeft = 40;
  const padRight = 16;
  const padTop = 26;
  const padBottom = 34;
  const chartW = svgWidth - padLeft - padRight;
  const chartH = svgHeight - padTop - padBottom;

  const maxFarmers = useMemo(() => {
    return Math.max(...chronologicalDays.map((d) => d.farmers_targeted || d.calls || 0), 4);
  }, [chronologicalDays]);
  const yMaxFarmers = Math.ceil(maxFarmers * 1.15);

  const maxAmount = useMemo(() => {
    return Math.max(...chronologicalDays.map((d) => d.amount || 0), 10);
  }, [chronologicalDays]);
  const yMaxAmount = Math.ceil(maxAmount * 1.2);

  const avgAmount = useMemo(() => {
    if (!chronologicalDays.length) return 0;
    const sum = chronologicalDays.reduce((acc, d) => acc + Number(d.amount || 0), 0);
    return sum / chronologicalDays.length;
  }, [chronologicalDays]);
  const avgY = padTop + chartH - (avgAmount / (yMaxAmount || 1)) * chartH;

  const slotW = chartW / (n || 1);

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
    <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 space-y-4 shadow-2xs">
      {/* Top Header & Single Primary View Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div className="flex flex-wrap items-center gap-2">
          {chartView === 'realtime' && (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
          )}
          <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
            {chartView === 'breakdown'
              ? 'Cost & Call Breakdown'
              : chartView === 'realtime'
              ? 'Intraday Activity (₹)'
              : chartView === 'daily'
              ? dailyMetric === 'reach'
                ? 'Daily Farmer Reach & Coverage'
                : 'Daily Spend Trend (₹)'
              : 'Daily Telemetry Table'}
          </h3>
          {chartView !== 'realtime' && chartView !== 'breakdown' && (
            <span className="text-[11px] font-medium text-slate-400">(last {n} days with calls)</span>
          )}
          {isSimulated && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
              Simulated Data
            </span>
          )}
        </div>

        {/* Primary View Switcher */}
        <div className="inline-flex flex-wrap p-1 rounded-xl bg-slate-100 border border-slate-200/60 self-start sm:self-auto gap-0.5">
          <button
            type="button"
            onClick={() => {
              setChartView('breakdown');
              setHoveredIdx(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'breakdown'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <PieChart className="w-3.5 h-3.5 text-trust-green" />
            Breakdown
          </button>
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
            Intraday Activity
          </button>
          <button
            type="button"
            onClick={() => {
              setChartView('daily');
              setHoveredIdx(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'daily'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5 text-slate-600" />
            Daily Trends
          </button>
          <button
            type="button"
            onClick={() => {
              setChartView('table');
              setHoveredIdx(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
              chartView === 'table'
                ? 'bg-white text-trust-navy shadow-xs border border-slate-200/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            <Table className="w-3.5 h-3.5" />
            Daily Table
          </button>
        </div>
      </div>

      {/* View 1: Cost & Call Breakdown (4 Standardized Donut Cards) */}
      {chartView === 'breakdown' && (
        <DonutAnalyticsGrid
          callLogs={callLogs}
          rate={rate}
          messageRate={messageRate}
          embedded={true}
          dayFilter={timeframe}
          onDayFilterChange={onTimeframeChange}
          customDate={customDate}
          onCustomDateChange={onCustomDateChange}
        />
      )}

      {/* View 2: Intraday Activity Curve */}
      {chartView === 'realtime' && (
        <RealTimeCostChart
          callLogs={callLogs}
          rate={rate}
          messageRate={messageRate}
          isLive={true}
          embedded={true}
        />
      )}

      {/* View 3: 14-Day Daily Telemetry Table */}
      {chartView === 'table' && (
        <div className="overflow-x-auto">
          {n === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-slate-100">
              No daily call records found in this window.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100">
                  <th className="py-2.5 pr-4">Date</th>
                  <th className="py-2.5 pr-4">Farmers Targeted</th>
                  <th className="py-2.5 pr-4">Farmers Reached</th>
                  <th className="py-2.5 pr-4">Farmer Reach %</th>
                  <th className="py-2.5 pr-4">Dial Attempts (Retries)</th>
                  <th className="py-2.5 pr-4">Messages Sent</th>
                  <th className="py-2.5 pr-4">Billed Minutes</th>
                  <th className="py-2.5 pr-4">Voice AI Spend</th>
                  <th className="py-2.5 pr-4">SMS Spend</th>
                  <th className="py-2.5">Total Spend</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {chronologicalDays.map((day) => {
                  const targeted = day.farmers_targeted || day.calls;
                  const reached = day.farmers_reached || day.connected;
                  const reachPct = targeted > 0 ? Math.round((reached / targeted) * 100) : 0;
                  const msgs = day.messages_sent || day.calls || 0;
                  const voiceSpend = day.voice_amount !== undefined ? day.voice_amount : Math.round(day.billed_minutes * rate * 100) / 100;
                  const smsSpend = day.message_amount !== undefined ? day.message_amount : Math.round(msgs * messageRate * 100) / 100;
                  return (
                    <tr key={day.date} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-2.5 pr-4 font-medium text-slate-700">{formatDayLabel(day.date)}</td>
                      <td className="py-2.5 pr-4 font-mono font-medium text-slate-800">{targeted}</td>
                      <td className="py-2.5 pr-4 font-mono text-trust-green font-semibold">{reached}</td>
                      <td className="py-2.5 pr-4 font-mono text-slate-700 font-bold">{reachPct}%</td>
                      <td className="py-2.5 pr-4 font-mono text-slate-500">
                        {day.total_attempts || day.calls}
                        {day.retries > 0 && (
                          <span className="text-[10px] text-amber-600 font-semibold ml-1">({day.retries} retries)</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-sky-700 font-medium">{msgs} sent</td>
                      <td className="py-2.5 pr-4 font-mono">{day.billed_minutes}m</td>
                      <td className="py-2.5 pr-4 font-mono font-medium text-slate-700">{rupees(voiceSpend)}</td>
                      <td className="py-2.5 pr-4 font-mono font-medium text-sky-800">{rupees(smsSpend)}</td>
                      <td className="py-2.5 font-mono font-bold text-slate-900">{rupees(day.amount)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* View 4: Unified 14-Day Daily Trends Chart */}
      {chartView === 'daily' && (
        <>
          {n === 0 ? (
            <div className="p-8 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-slate-100">
              No daily call telemetry available to chart.
            </div>
          ) : (
            <div className="space-y-2.5">
              {/* Secondary Metric Filter: Farmer Reach vs. Spend */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <span className="text-[11px] text-slate-500 font-medium">
                  {dailyMetric === 'reach'
                    ? 'Unique farmer coverage vs. reached rate (retries to same farmer do not penalize reach %)'
                    : 'Chronological AI spend and daily average burn'}
                </span>
                <div className="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-slate-100 border border-slate-200/60 text-[11px] self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={() => setDailyMetric('reach')}
                    className={`px-3 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                      dailyMetric === 'reach'
                        ? 'bg-white text-trust-navy shadow-2xs font-semibold'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    Farmer Reach
                  </button>
                  <button
                    type="button"
                    onClick={() => setDailyMetric('spend')}
                    className={`px-3 py-1 rounded-md font-medium transition-colors cursor-pointer ${
                      dailyMetric === 'spend'
                        ? 'bg-white text-trust-navy shadow-2xs font-semibold'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    Spend (₹)
                  </button>
                </div>
              </div>

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
                    <div className="bg-slate-900/95 text-white rounded-xl shadow-xl px-3.5 py-2.5 border border-slate-700 min-w-[200px] space-y-1.5 text-xs backdrop-blur-xs">
                      <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-1">
                        <span className="font-semibold text-slate-200">{formatFullDate(hoveredDay.date)}</span>
                        <span className="font-mono text-emerald-400 font-bold">{rupees(hoveredDay.amount)}</span>
                      </div>
                      <div className="space-y-1 text-[11px]">
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1.5 text-slate-300">
                            <span className="w-2.5 h-2.5 rounded-xs bg-trust-navy inline-block border border-slate-500" />
                            Farmers Targeted:
                          </span>
                          <span className="font-bold text-white">{hoveredDay.farmers_targeted || hoveredDay.calls} farmers</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="flex items-center gap-1.5 text-slate-300">
                            <span className="w-2.5 h-2.5 rounded-xs bg-trust-green inline-block" />
                            Farmers Reached:
                          </span>
                          <span className="font-bold text-emerald-400">
                            {hoveredDay.farmers_reached || hoveredDay.connected}
                            {' '}
                            ({(hoveredDay.farmers_targeted || hoveredDay.calls) > 0
                              ? `${Math.round(((hoveredDay.farmers_reached || hoveredDay.connected) / (hoveredDay.farmers_targeted || hoveredDay.calls)) * 100)}%`
                              : '0%'})
                          </span>
                        </div>
                        <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-[10px] text-slate-400">
                          <span>
                            Dial Attempts: {hoveredDay.total_attempts || hoveredDay.calls}
                            {(hoveredDay.retries || 0) > 0 && ` (${hoveredDay.retries} retries)`}
                          </span>
                          <span>Billed: {hoveredDay.billed_minutes}m</span>
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
                  {[0, 0.5, 1].map((pct) => {
                    const yVal = padTop + chartH * (1 - pct);
                    const farmerLabel = Math.round(yMaxFarmers * pct);
                    const costLabel = Math.round(yMaxAmount * pct);

                    return (
                      <g key={`grid-line-${pct}`}>
                        <line
                          x1={padLeft}
                          y1={yVal}
                          x2={padLeft + chartW}
                          y2={yVal}
                          stroke="#F1F5F9"
                          strokeWidth="1"
                        />
                        {/* Left Y-axis Label */}
                        <text
                          x={padLeft - 8}
                          y={yVal + 3}
                          textAnchor="end"
                          fill="#94A3B8"
                          fontSize="9"
                          fontWeight="500"
                        >
                          {dailyMetric === 'spend' ? `₹${costLabel}` : farmerLabel}
                        </text>
                      </g>
                    );
                  })}

                  {/* X Axis Baseline */}
                  <line
                    x1={padLeft}
                    y1={padTop + chartH}
                    x2={padLeft + chartW}
                    y2={padTop + chartH}
                    stroke="#CBD5E1"
                    strokeWidth="1"
                  />

                  {/* Grouped Bars for Farmer Reach */}
                  {dailyMetric === 'reach' && (
                    <>
                      {chronologicalDays.map((d, i) => {
                        const xSlot = padLeft + i * slotW;
                        const xCenter = xSlot + slotW / 2;
                        const barW = Math.max(3, Math.min(13, (slotW - 8) / 2));

                        const targetedCount = d.farmers_targeted || d.calls || 0;
                        const reachedCount = d.farmers_reached || d.connected || 0;

                        const totalH = targetedCount > 0 ? Math.max(3, (targetedCount / yMaxFarmers) * chartH) : 0;
                        const connH = reachedCount > 0 ? Math.max(3, (reachedCount / yMaxFarmers) * chartH) : 0;
                        const yTotal = padTop + chartH - totalH;
                        const yConn = padTop + chartH - connH;
                        const isHovered = hoveredIdx === i;

                        return (
                          <g key={`bar-${d.date}`}>
                            {isHovered && (
                              <rect
                                x={xSlot + 2}
                                y={padTop}
                                width={slotW - 4}
                                height={chartH}
                                fill="#0F2444"
                                opacity="0.04"
                                rx="4"
                              />
                            )}
                            {totalH > 0 && (
                              <rect
                                x={xCenter - barW - 1}
                                y={yTotal}
                                width={barW}
                                height={totalH}
                                fill={isHovered ? '#0B1B33' : '#0F2444'}
                                rx="2"
                              />
                            )}
                            {connH > 0 && (
                              <rect
                                x={xCenter + 1}
                                y={yConn}
                                width={barW}
                                height={connH}
                                fill={isHovered ? '#165734' : '#1E6F43'}
                                rx="2"
                              />
                            )}
                          </g>
                        );
                      })}
                    </>
                  )}

                  {/* Area Gradient & Spend Curve */}
                  {dailyMetric === 'spend' && (
                    <>
                      {areaPath && <path d={areaPath} fill="url(#costGradientMerged)" />}
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
                      {costPoints.map((p) => {
                        const isHovered = hoveredIdx === p.i;
                        return (
                          <circle
                            key={`dot-${p.day.date}`}
                            cx={p.x}
                            cy={p.y}
                            r={isHovered ? 5 : 3}
                            fill={isHovered ? '#165734' : '#1E6F43'}
                            stroke="#FFFFFF"
                            strokeWidth={isHovered ? 2.5 : 1.5}
                          />
                        );
                      })}
                      {avgAmount > 0 && (
                        <g>
                          <line
                            x1={padLeft}
                            y1={avgY}
                            x2={padLeft + chartW}
                            y2={avgY}
                            stroke="#94A3B8"
                            strokeWidth="1.2"
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

                  {/* Interactive Hit Rectangles */}
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

              {/* Chart Legend */}
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500 pt-2 border-t border-slate-100">
                {dailyMetric === 'reach' ? (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-navy inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Farmers Targeted ({maxFarmers} peak)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-green inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Farmers Reached (Unique)</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-xs bg-trust-green inline-block shadow-2xs" />
                      <span className="text-slate-700 font-medium">Daily Spend (₹{maxAmount.toFixed(0)} peak)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="w-4 h-0.5 border-t-2 border-dashed border-slate-400 inline-block" />
                      <span className="text-slate-600 font-medium">Average ({rupees(avgAmount)}/day)</span>
                    </div>
                  </div>
                )}
                <div className="text-[11px] text-slate-400">
                  Unique farmer reach eliminates retry skew · Hover any day to inspect retries & spend
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/**
 * Clean Cost Analytics View:
 * 1. 3 Top Summary Cards (Today, Last 7 Days, Last 14 Days)
 * 2. Efficiency & Rate Configurator Bar (Answer Rate, Cost/Connected Call, Number Rental, and Rate input)
 * 3. Unified Chart Hub with Single Primary View Switcher
 */
export const CostAnalyticsView = ({ isBackendOnline = true, callLogs = [] }) => {
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [rateInput, setRateInput] = useState('');
  const [smsRateInput, setSmsRateInput] = useState(() => {
    try {
      return localStorage.getItem('gate0_sms_rate') || '0.20';
    } catch {
      return '0.20';
    }
  });
  const [rateMessage, setRateMessage] = useState(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState('14d'); // 'today' | 'yesterday' | '7d' | '14d' | 'custom'
  const [customDate, setCustomDate] = useState('');

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
      try {
        localStorage.setItem('gate0_sms_rate', smsRateInput);
      } catch {
        // ignore
      }
      setRateMessage({ ok: true, text: 'Rates saved.' });
    } catch (err) {
      setRateMessage({ ok: false, text: err.message });
    }
  };

  const activeUsage = useMemo(() => {
    if (usage && usage.configured) return { ...usage, isSimulated: false };
    if (!usage && !error) return null;
    const rate = Number(rateInput) || (usage && usage.rate) || 3.5;
    const smsRate = Number(smsRateInput) || 0.20;
    return generateSimulatedUsage(callLogs, rate, smsRate);
  }, [usage, error, callLogs, rateInput, smsRateInput]);

  // Dynamic Telemetry filtered strictly according to user selection (Today, Yesterday, 7d, 14d, or Custom Date)
  const dynamicTimeframeStats = useMemo(() => {
    const today = new Date();
    const todayStr = localDateKey(today);
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = localDateKey(yesterday);
    const d7 = new Date(today);
    d7.setDate(d7.getDate() - 6);
    const d7Str = localDateKey(d7);
    const d14 = new Date(today);
    d14.setDate(d14.getDate() - 13);
    const d14Str = localDateKey(d14);

    const validCalls = (callLogs || []).filter((c) => !c.is_test);

    const periodCalls = validCalls.filter((c) => {
      const callDate = getCallDateKey(c);
      if (!callDate) return false;
      if (selectedTimeframe === 'today') return callDate === todayStr;
      if (selectedTimeframe === 'yesterday') return callDate === yesterdayStr;
      if (selectedTimeframe === '7d') return callDate >= d7Str && callDate <= todayStr;
      if (selectedTimeframe === '14d') return callDate >= d14Str && callDate <= todayStr;
      if (selectedTimeframe === 'custom' && customDate) return callDate === customDate;
      return true;
    });

    const targetedSet = new Set();
    const reachedSet = new Set();
    let totalBilledMins = 0;
    let totalMessages = 0;
    let retryCount = 0;

    periodCalls.forEach((c) => {
      const farmerId = String(c.farmer_id || c.phone || c.Farmer_Name || c.name || '').trim();
      if (farmerId) targetedSet.add(farmerId);

      const msgs = Number(c.messages_sent ?? c.sms_count ?? 1);
      totalMessages += msgs;

      if (Number(c.retry_count || c.attempt_number || 1) > 1) {
        retryCount += 1;
      }

      const isConnected =
        didFarmerPickUpAndTalk(c) ||
        ['completed', 'delivered', 'connected', 'answered'].includes(
          String(c.call_status || c.status || '').toLowerCase()
        ) ||
        Number(c.duration_sec || c.duration || 0) > 0;

      if (isConnected) {
        if (farmerId) reachedSet.add(farmerId);
        const sec = Number(c.duration_sec ?? c.duration ?? 0);
        totalBilledMins += Math.max(1, Math.ceil(sec / 60));
      }
    });

    const targetedCount = targetedSet.size || periodCalls.length;
    const reachedCount = reachedSet.size;
    const reachPct = targetedCount > 0 ? (reachedCount / targetedCount) * 100 : 0;
    const dialAttempts = periodCalls.length;
    const retries = retryCount || Math.max(0, dialAttempts - targetedCount);

    const voiceRate = Number(rateInput || 3.5);
    const smsRate = Number(smsRateInput || 0.2);
    const voiceSpend = Math.round(totalBilledMins * voiceRate * 100) / 100;
    const messageSpend = Math.round(totalMessages * smsRate * 100) / 100;
    const operationalSpend = Math.round((voiceSpend + messageSpend) * 100) / 100;

    const costPerReachedFarmer = reachedCount > 0 ? operationalSpend / reachedCount : 0;

    let timeframeLabel = 'Last 14 Days';
    if (selectedTimeframe === 'today') timeframeLabel = 'Today';
    else if (selectedTimeframe === 'yesterday') timeframeLabel = 'Yesterday';
    else if (selectedTimeframe === '7d') timeframeLabel = 'Last 7 Days';
    else if (selectedTimeframe === '14d') timeframeLabel = 'Last 14 Days';
    else if (selectedTimeframe === 'custom' && customDate) timeframeLabel = `Date: ${customDate}`;

    return {
      periodCalls,
      targetedCount,
      reachedCount,
      reachPct,
      dialAttempts,
      retries,
      totalBilledMins,
      totalMessages,
      voiceSpend,
      messageSpend,
      operationalSpend,
      costPerReachedFarmer,
      timeframeLabel,
    };
  }, [callLogs, selectedTimeframe, customDate, rateInput, smsRateInput]);

  const noCalls = activeUsage && activeUsage.window && (activeUsage.days || []).length === 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-2xl border border-slate-200/80 bg-white p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Cost Analytics</span>
          <h2 className="text-xl font-bold text-slate-900">Telephony & AI Expenditure</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Sarvam Voice AI usage (₹{Number(rateInput || 3.5).toFixed(2)}/min), advisory messages (₹{Number(smsRateInput || 0.2).toFixed(2)}/msg), and fixed monthly number rental (₹59.00/mo, billed separately).
          </p>
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

      {usage && usage.exhausted && (
        <div className="flex items-start gap-2 p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs shadow-2xs">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Sarvam reported that credits are exhausted in the last 7 days. Add credits on Sarvam Settings &gt; Billing to resume live calling.
          </span>
        </div>
      )}

      {activeUsage?.isSimulated && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-amber-50/70 border border-amber-200/80 text-amber-800 text-xs shadow-2xs">
          <Info className="w-4 h-4 shrink-0 text-amber-600" />
          <span>
            Telemetry simulated from local farmer call records in this database (Sarvam live credentials not configured on backend).
          </span>
        </div>
      )}

      {activeUsage && activeUsage.window && (
        <>
          {/* 1. Top 3 Summary Cards (Interactive Period Switchers) */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Today */}
            <button
              type="button"
              onClick={() => {
                setSelectedTimeframe('today');
                setCustomDate('');
              }}
              className={`text-left rounded-2xl p-4 sm:p-5 transition-all cursor-pointer flex flex-col justify-between ${
                selectedTimeframe === 'today' && !customDate
                  ? 'bg-emerald-50/30 border-2 border-trust-green ring-2 ring-trust-green/20 shadow-xs'
                  : 'bg-white border border-slate-200/80 hover:border-slate-300 hover:shadow-2xs'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Today</div>
                {selectedTimeframe === 'today' && !customDate && (
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-100 text-trust-green uppercase tracking-wide">
                    Active Period
                  </span>
                )}
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{rupees(activeUsage.today?.amount)}</div>
              <div className="text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-100 break-words leading-relaxed">
                {activeUsage.today?.billed_minutes || 0}m voice ({rupees(activeUsage.today?.voice_amount)}) · {activeUsage.today?.messages_sent || activeUsage.today?.calls || 0} SMS ({rupees(activeUsage.today?.message_amount)}) · {activeUsage.today?.farmers_reached || activeUsage.today?.connected || 0} of {activeUsage.today?.farmers_targeted || activeUsage.today?.calls || 0} farmers reached
              </div>
            </button>

            {/* Last 7 Days */}
            <button
              type="button"
              onClick={() => {
                setSelectedTimeframe('7d');
                setCustomDate('');
              }}
              className={`text-left rounded-2xl p-4 sm:p-5 transition-all cursor-pointer flex flex-col justify-between ${
                selectedTimeframe === '7d' && !customDate
                  ? 'bg-slate-50/70 border-2 border-trust-navy ring-2 ring-trust-navy/15 shadow-xs'
                  : 'bg-white border border-slate-200/80 hover:border-slate-300 hover:shadow-2xs'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Last 7 Days</div>
                {selectedTimeframe === '7d' && !customDate && (
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-slate-200 text-trust-navy uppercase tracking-wide">
                    Active Period
                  </span>
                )}
              </div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{rupees(activeUsage.week?.amount)}</div>
              <div className="text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-100 break-words leading-relaxed">
                {activeUsage.week?.billed_minutes || 0}m voice ({rupees(activeUsage.week?.voice_amount)}) · {activeUsage.week?.messages_sent || activeUsage.week?.calls || 0} SMS ({rupees(activeUsage.week?.message_amount)}) · {activeUsage.week?.farmers_reached || activeUsage.week?.connected || 0} of {activeUsage.week?.farmers_targeted || activeUsage.week?.calls || 0} farmers reached
              </div>
            </button>

            {/* Last 14 Days */}
            <button
              type="button"
              onClick={() => {
                setSelectedTimeframe('14d');
                setCustomDate('');
              }}
              className={`text-left rounded-2xl p-4 sm:p-5 transition-all cursor-pointer flex flex-col justify-between ${
                selectedTimeframe === '14d' && !customDate
                  ? 'bg-slate-50/70 border-2 border-trust-navy ring-2 ring-trust-navy/15 shadow-xs'
                  : 'bg-white border border-slate-200/80 hover:border-slate-300 hover:shadow-2xs'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Last 14 Days</div>
                {selectedTimeframe === '14d' && !customDate && (
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-slate-200 text-trust-navy uppercase tracking-wide">
                    Active Period
                  </span>
                )}
              </div>
              <div className="text-2xl font-bold text-trust-green mt-1">{rupees(activeUsage.window?.amount)}</div>
              <div className="text-[11px] text-slate-500 mt-2.5 pt-2 border-t border-slate-100 break-words leading-relaxed">
                {activeUsage.window?.billed_minutes || 0}m voice ({rupees(activeUsage.window?.voice_amount)}) · {activeUsage.window?.messages_sent || activeUsage.window?.calls || 0} SMS ({rupees(activeUsage.window?.message_amount)}) · {activeUsage.window?.farmers_reached || activeUsage.window?.connected || 0} of {activeUsage.window?.farmers_targeted || activeUsage.window?.calls || 0} farmers reached
              </div>
            </button>
          </div>

          {/* 2. Combined Cost Efficiency & Rate Configurator Bar (Dynamic by Timeframe) */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-4 sm:p-5 shadow-2xs">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
              {/* Key Dynamic Efficiency Telemetry */}
              <div className="flex flex-wrap items-center gap-3 sm:gap-5 text-xs text-slate-600">
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-800 font-bold border border-slate-200/80 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-trust-green shrink-0" />
                  <span>{dynamicTimeframeStats.timeframeLabel}</span>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Farmer Reach:</span>
                  <span className="font-bold text-slate-900 text-sm">{dynamicTimeframeStats.reachPct.toFixed(1)}%</span>
                  <span className="text-slate-400 text-[11px]">
                    ({dynamicTimeframeStats.reachedCount} of {dynamicTimeframeStats.targetedCount} unique farmers)
                  </span>
                </div>

                <div className="h-4 w-px bg-slate-200 hidden sm:block" />

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Cost / Reached Farmer:</span>
                  <span className="font-bold text-trust-green text-sm">{rupees(dynamicTimeframeStats.costPerReachedFarmer)}</span>
                </div>

                <div className="h-4 w-px bg-slate-200 hidden sm:block" />

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Dial Attempts:</span>
                  <span className="font-bold text-trust-navy text-sm">{dynamicTimeframeStats.dialAttempts}</span>
                  {dynamicTimeframeStats.retries > 0 && (
                    <span className="text-slate-400 text-[11px]">({dynamicTimeframeStats.retries} retries)</span>
                  )}
                </div>

                <div className="h-4 w-px bg-slate-200 hidden sm:block" />

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Messages Sent:</span>
                  <span className="font-bold text-sky-700 text-sm">{dynamicTimeframeStats.totalMessages}</span>
                  <span className="text-slate-400 text-[11px]">
                    ({rupees(dynamicTimeframeStats.messageSpend)})
                  </span>
                </div>

                <div className="h-4 w-px bg-slate-200 hidden sm:block" />

                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Number Rental:</span>
                  <span className="font-bold text-trust-navy text-sm">₹59.00/mo</span>
                  <span className="text-slate-400 text-[11px]">(Fixed DID · separate monthly base)</span>
                </div>
              </div>

              {/* Clean Dual-Rate Editor (Voice AI & SMS) */}
              <div className="flex items-center gap-3 bg-slate-50 border border-slate-200/80 px-3 py-2 rounded-xl text-xs shrink-0 self-start lg:self-auto">
                <div className="flex items-center gap-1.5">
                  <label htmlFor="rate" className="font-semibold text-slate-700 whitespace-nowrap">
                    Voice:
                  </label>
                  <span className="text-slate-400 font-medium">₹</span>
                  <input
                    id="rate"
                    type="number"
                    min="0"
                    step="0.05"
                    value={rateInput}
                    onChange={(e) => setRateInput(e.target.value)}
                    className="w-14 px-1.5 py-0.5 bg-white border border-slate-200 rounded-md text-xs font-bold text-slate-900 text-center focus:ring-1 focus:ring-trust-navy focus:outline-hidden"
                  />
                  <span className="text-slate-500 text-[11px]">/m</span>
                </div>

                <div className="h-4 w-px bg-slate-200" />

                <div className="flex items-center gap-1.5">
                  <label htmlFor="smsRate" className="font-semibold text-slate-700 whitespace-nowrap">
                    SMS:
                  </label>
                  <span className="text-slate-400 font-medium">₹</span>
                  <input
                    id="smsRate"
                    type="number"
                    min="0"
                    step="0.01"
                    value={smsRateInput}
                    onChange={(e) => setSmsRateInput(e.target.value)}
                    className="w-14 px-1.5 py-0.5 bg-white border border-slate-200 rounded-md text-xs font-bold text-slate-900 text-center focus:ring-1 focus:ring-trust-navy focus:outline-hidden"
                  />
                  <span className="text-slate-500 text-[11px]">/msg</span>
                </div>

                <button
                  onClick={handleSaveRate}
                  className="px-2.5 py-1 rounded-lg bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer"
                >
                  Save
                </button>
                {rateMessage && (
                  <span className={`text-[11px] font-semibold ${rateMessage.ok ? 'text-emerald-700' : 'text-rose-700'}`}>
                    {rateMessage.text}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* 3. Interactive Charts Hub (Default: Cost & Call Breakdown) */}
          {noCalls ? (
            <div className="p-8 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200/80 shadow-2xs">
              No calls recorded in the last {activeUsage.window_days || 14} days.
            </div>
          ) : (
            <InteractiveUsageChart
              days={activeUsage.days || []}
              rate={Number(activeUsage.rate || 3.5)}
              messageRate={Number(smsRateInput || 0.2)}
              isSimulated={Boolean(activeUsage.isSimulated)}
              callLogs={callLogs}
              timeframe={selectedTimeframe}
              onTimeframeChange={setSelectedTimeframe}
              customDate={customDate}
              onCustomDateChange={setCustomDate}
            />
          )}
        </>
      )}
    </div>
  );
};

export default CostAnalyticsView;
