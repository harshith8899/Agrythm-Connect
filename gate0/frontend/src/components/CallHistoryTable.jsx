import React, { useMemo } from 'react';
import { 
  ChevronRight, 
  Clock, 
  MapPin, 
  CheckCircle2, 
  AlertCircle, 
  PhoneOutgoing,
  PhoneIncoming,
  Database,
  ExternalLink,
  ShieldAlert,
  Calendar,
  RefreshCw,
  PhoneCall,
  MessageSquare
} from 'lucide-react';
import { API_CONFIG } from '../utils/constants';
import { maskPhoneNumber, isTodayDateStr, isCallToday } from '../utils';
import { SliderLoader } from './SliderLoader';
import { CallDirectionBadge } from './CallDirectionBadge';
import { WeatherVisualBadge } from './WeatherVisualBadge';

// Shorten verbose dispositions so log rows remain neat, compact and identical in height
function shortenDisposition(text) {
  if (!text) return 'Delivered';
  const str = String(text).trim();

  // "Callback requested for in 2 hours (not booked: time not understood)" -> "Callback: in 2 hours"
  // "Callback requested for at 3 PM (not booked: time not understood)" -> "Callback: at 3 PM"
  if (/callback requested/i.test(str)) {
    const timeMatch = str.match(/for\s+(?:at\s+)?([^()]+?)(?:\s*\(|$)/i);
    if (timeMatch && timeMatch[1]) {
      return `Callback: ${timeMatch[1].trim()}`;
    }
    return 'Callback requested';
  }

  // "Failed: Carrier telecom pulse timeout / network congestion" -> "Carrier timeout / congestion"
  if (/carrier telecom pulse timeout/i.test(str) || /network congestion/i.test(str)) {
    return 'Carrier timeout / congestion';
  }

  // "Callback not placed in time" -> "Missed callback window"
  if (/callback not placed in time/i.test(str)) {
    return 'Missed callback window';
  }

  // "No Answer or Rejected" -> "No answer / rejected"
  if (/no answer or rejected/i.test(str)) {
    return 'No answer / rejected';
  }

  return str;
}

export const CallHistoryTable = ({ 
  callLogs, 
  onSelectCall, 
  selectedCallId, 
  onResetFilters, 
  isFiltered,
  isBackendOnline = true,
  loading = false,
  refreshing = false,
  onRefresh,
  onCallBack,
}) => {
  // Compute outgoing and incoming counts dynamically from current scoped call logs
  const { outgoingCount, incomingCount } = useMemo(() => {
    let outCount = 0;
    let inCount = 0;
    (callLogs || []).forEach((c) => {
      const isIncoming =
        String(c.direction || '').toLowerCase() === 'inbound' ||
        Boolean(c.has_inbound_callback) ||
        (Array.isArray(c.attempts_log) && c.attempts_log.some((a) => a.direction === 'inbound'));
      if (isIncoming) {
        inCount += 1;
      } else {
        outCount += 1;
      }
    });
    return { outgoingCount: outCount, incomingCount: inCount };
  }, [callLogs]);
  const getStatusBadge = (status, disposition, skipReason) => {
    const s = String(status || '').toLowerCase();
    switch (s) {
      case 'completed':
      case 'answered':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 whitespace-nowrap shrink-0">
            <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
            <span>Completed</span>
          </span>
        );
      case 'callback scheduled':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200 whitespace-nowrap shrink-0">
            <Clock className="w-3 h-3 text-blue-600 shrink-0" />
            <span>Callback Scheduled</span>
          </span>
        );
      case 'callback requested':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-sky-50 text-sky-700 border border-sky-200 whitespace-nowrap shrink-0">
            <Clock className="w-3 h-3 text-sky-600 shrink-0" />
            <span>Callback Requested</span>
          </span>
        );
      case 'not confirmed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap shrink-0">
            <AlertCircle className="w-3 h-3 text-amber-600 shrink-0" />
            <span>Not Confirmed</span>
          </span>
        );
      case 'callback missed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200 whitespace-nowrap shrink-0">
            <Clock className="w-3 h-3 text-rose-600 shrink-0" />
            <span>Callback Missed</span>
          </span>
        );
      case 'callback done':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200 whitespace-nowrap shrink-0">
            <CheckCircle2 className="w-3 h-3 text-slate-500 shrink-0" />
            <span>Callback Done</span>
          </span>
        );
      case 'declined':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600 border border-slate-200 whitespace-nowrap shrink-0">
            <AlertCircle className="w-3 h-3 text-slate-500 shrink-0" />
            <span>Declined</span>
          </span>
        );
      case 'unanswered':
      case 'busy':
      case 'no_answer':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap shrink-0">
            <PhoneOutgoing className="w-3 h-3 text-amber-600 shrink-0" />
            <span>Unanswered</span>
          </span>
        );
      case 'retrying':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap shrink-0">
            <RefreshCw className="w-3 h-3 text-amber-600 animate-spin shrink-0" />
            <span>Retrying</span>
          </span>
        );
      case 'escalated':
      case 'requires escalation':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200 whitespace-nowrap shrink-0">
            <ShieldAlert className="w-3 h-3 text-purple-600 shrink-0" />
            <span>Escalated</span>
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200 whitespace-nowrap shrink-0">
            <AlertCircle className="w-3 h-3 text-rose-600 shrink-0" />
            <span>Failed</span>
          </span>
        );
      case 'in call':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" style={{ transformBox: 'fill-box', transformOrigin: 'center' }} />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600" />
            </span>
            <span>In Call</span>
          </span>
        );
      case 'in queue':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
            <Clock className="w-3 h-3 text-slate-500" />
            <span>In Queue</span>
          </span>
        );
      case 'calling':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <PhoneCall className="w-3 h-3 text-blue-600 animate-pulse" />
            <span>Calling</span>
          </span>
        );
      case 'skipped':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
            <AlertCircle className="w-3 h-3 text-slate-500" />
            <span>Skipped {skipReason ? `(${skipReason})` : ''}</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-200">
            {status || 'Scheduled'}
          </span>
        );
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds && seconds !== 0) return '0s';
    const num = parseInt(seconds, 10);
    if (isNaN(num)) return String(seconds);
    const mins = Math.floor(num / 60);
    const secs = num % 60;
    if (mins === 0) return `${secs}s`;
    return `${mins}m ${secs}s`;
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden shadow-2xs">
        <div className="p-4 sm:p-5 border-b border-slate-100 space-y-3">
          <div>
            <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">Call history</span>
            <h3 className="text-base font-bold text-slate-900">Loading calls…</h3>
          </div>
          <SliderLoader />
        </div>
        <div className="divide-y divide-slate-100" aria-busy="true">
          {[0, 1, 2, 3, 4].map((n) => (
            <div key={n} className="p-4 flex items-center gap-4 animate-pulse">
              <div className="h-9 w-9 rounded-xl bg-slate-200 shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-3 rounded bg-slate-200 w-1/3" />
                <div className="h-2.5 rounded bg-slate-100 w-2/3" />
              </div>
              <div className="hidden sm:block h-5 w-20 rounded-full bg-slate-200" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!callLogs || callLogs.length === 0) {
    if (!isBackendOnline) {
      return (
        <div className="bg-rose-50/40 rounded-2xl border-2 border-dashed border-rose-200 p-12 text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-600 mx-auto">
            <AlertCircle className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-base font-bold text-rose-900">Backend API Offline</h3>
            <p className="text-xs text-rose-700 max-w-md mx-auto mt-1 leading-relaxed">
              Unable to reach <code className="bg-rose-100 px-1 py-0.5 rounded font-mono font-bold text-rose-950">{API_CONFIG.callLogsApiUrl}</code>.
              Run <code className="bg-rose-100 px-1.5 py-0.5 rounded font-mono font-bold text-rose-950">npm run backend</code> in your terminal to start the orchestrator and load call logs.
            </p>
          </div>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="h-9 px-3.5 rounded-xl justify-center whitespace-nowrap bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 transition-colors shadow-xs cursor-pointer inline-flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Connection</span>
            </button>
          )}
        </div>
      );
    }

    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mx-auto">
          {isFiltered ? <PhoneOutgoing className="w-7 h-7" /> : <Database className="w-7 h-7 text-trust-navy" />}
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">
            {isFiltered ? 'No Matching Call Records' : 'No calls for this day yet'}
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            {isFiltered 
              ? 'No voice call logs match the selected search or filter criteria. Try adjusting your filters.'
              : 'Nothing has been called yet. The daily send places the calls, or use Send now in the header. Pick "All Dates" to see earlier days.'}
          </p>
        </div>
        {isFiltered ? (
          onResetFilters && (
            <button
              onClick={onResetFilters}
              className="h-9 px-3.5 rounded-xl inline-flex items-center justify-center whitespace-nowrap bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer"
            >
              Reset Filters
            </button>
          )
        ) : (
          <div className="pt-2">
            <a
              href={API_CONFIG.callLogsApiUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors"
            >
              <span>View live API (/api/calls)</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 overflow-hidden shadow-2xs">
      {refreshing && <SliderLoader />}
      <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Call history
          </span>
          <h3 className="text-base font-bold text-slate-900">
            Incoming & outgoing weather calls
          </h3>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            title={`${outgoingCount} Outgoing Call${outgoingCount === 1 ? '' : 's'}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200/80 text-[11px] font-semibold text-slate-700 shadow-2xs"
          >
            <CallDirectionBadge direction="outbound" compact />
            <span>Outgoing</span>
            <span className="ml-0.5 px-1.5 py-0.2 rounded bg-slate-200/70 text-slate-800 font-mono text-[10px] font-bold tabular-nums">
              {outgoingCount}
            </span>
          </span>
          <span
            title={`${incomingCount} Incoming Call${incomingCount === 1 ? '' : 's'}`}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50/70 border border-emerald-200/80 text-[11px] font-semibold text-emerald-800 shadow-2xs"
          >
            <CallDirectionBadge direction="inbound" compact />
            <span>Incoming</span>
            <span className="ml-0.5 px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-900 font-mono text-[10px] font-bold tabular-nums">
              {incomingCount}
            </span>
          </span>
        </div>
      </div>

      {/* Mobile Cards */}
      <div className="md:hidden divide-y divide-slate-100">
        {callLogs.map((call) => {
          const attemptNumber = call.attempts_log?.length || (call.retry_count ? call.retry_count + 1 : 1);
          const attemptLabel = call.is_test ? 'Test call' : `Attempt ${attemptNumber}/${call.max_attempts || 3}`;
          const hasCallback = Boolean(call.scheduled_callback_time) || call.disposition === 'Callback Requested';
          return (
            <button
              key={call.call_id}
              type="button"
              onClick={() => onSelectCall(call)}
              className={`w-full text-left p-4 space-y-2.5 cursor-pointer ${selectedCallId === call.call_id ? 'bg-blue-50/70' : 'active:bg-slate-50'}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <CallDirectionBadge direction={call.direction} compact />
                  <div className="min-w-0">
                    <div className="font-bold text-sm text-slate-900 truncate" title={call.farmer_name}>{call.farmer_name}</div>
                    <div className="text-[11px] text-slate-500 font-mono">{maskPhoneNumber(call.phone_number || call.phone)}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {getStatusBadge(call.status, call.disposition, call.skip_reason)}
                  {(Number(call.messages_sent || 0) > 0 || call.status === 'Completed' || call.disposition === 'Weather Delivered' || call.understood_weather === 'yes') && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200 shrink-0">
                      <MessageSquare className="w-2.5 h-2.5 text-sky-600 shrink-0" />
                      <span>SMS Sent</span>
                    </span>
                  )}
                  {call.direction === 'incoming' && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-50 text-teal-700 border border-teal-200" title="The farmer rang us">
                      <PhoneIncoming className="w-3 h-3" />Incoming
                    </span>
                  )}
                  {call.is_test && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-violet-50 text-violet-700 border border-violet-200">TEST</span>
                  )}
                </div>
              </div>

              <WeatherVisualBadge call={call} compact />

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />{call.displayDateTime || call.call_timestamp || 'Just now'}</span>
                <span className="inline-flex items-center gap-1"><MapPin className="w-3 h-3" />{[call.village, call.district].filter(Boolean).join(', ') || 'N/A'}</span>
                {call.language && <span>{call.language}</span>}
                <span className="font-mono font-semibold text-slate-700">{attemptLabel}</span>
                <span className="font-mono">{formatDuration(call.duration_seconds || call.duration_sec)}</span>
              </div>

              {(call.disposition || call.next_attempt_at || hasCallback) && (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
                  {call.disposition && <span className="text-slate-500 font-medium">{shortenDisposition(call.disposition)}</span>}
                  {call.next_attempt_at && (
                    <span className="text-amber-700 font-semibold">Next try {String(call.next_attempt_at).split(', ')[1] || call.next_attempt_at}</span>
                  )}
                  {hasCallback && (
                    <span className="inline-flex items-center gap-1 text-amber-900 font-semibold">
                      <Calendar className="w-3 h-3 text-amber-600" />{call.scheduled_callback_time || 'Callback pending'}
                    </span>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Desktop Table (Consolidated 8-column layout with clean balance & zero clipping) */}
      <div className="hidden md:block overflow-x-auto overflow-y-auto max-h-[calc(100vh-9rem)]">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 sticky top-0 z-10 text-[11px] font-bold tracking-wider text-slate-500 uppercase border-b border-slate-200/80">
            <tr>
              <th className="px-3.5 py-3 whitespace-nowrap min-w-[130px]">Call & Time</th>
              <th className="px-3.5 py-3 whitespace-nowrap min-w-[150px]">Farmer & Contact</th>
              <th className="px-3.5 py-3 whitespace-nowrap min-w-[110px]">District / Village</th>
              <th className="px-3.5 py-3 whitespace-nowrap text-center min-w-[80px]">Language</th>
              <th className="px-3.5 py-3 whitespace-nowrap min-w-[195px]">Weather</th>
              <th className="px-3.5 py-3 whitespace-nowrap text-center min-w-[90px]">Attempts</th>
              <th className="px-3.5 py-3 whitespace-nowrap text-center min-w-[75px]">Duration</th>
              <th className="px-3.5 py-3 whitespace-nowrap min-w-[245px]">Status & Disposition</th>
              <th className="px-3.5 py-3 whitespace-nowrap text-right min-w-[130px]">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {callLogs.map((call) => {
              const isSelected = selectedCallId === call.call_id;
              const isToday = call.is_today ?? (isTodayDateStr(call.call_date) || isCallToday(call.call_date || call.created_at || call.call_timestamp));
              const isPendingCb = isToday && (call.status === 'Callback Scheduled' || call.callback_status === 'pending');
              const hasCallback = isPendingCb || (isToday && Boolean(call.scheduled_callback_time));
              const isPastMissedCb = !isToday && (call.status === 'Callback Scheduled' || call.callback_status === 'missed' || call.callback_status === 'pending');
              const attemptNumber = call.attempts_log?.length || (call.retry_count ? call.retry_count + 1 : 1);
              const attemptLabel = call.is_test ? 'Test call' : `Attempt ${attemptNumber}/${call.max_attempts || 3}`;

              return (
                <tr
                  key={call.call_id}
                  onClick={() => onSelectCall(call)}
                  className={`cursor-pointer transition-all h-[62px] ${
                    isSelected ? 'bg-blue-50/70 hover:bg-blue-50' : 'hover:bg-slate-50/70'
                  }`}
                >
                  {/* Direction Arrow Badge (Arrow Only) + Call ID & Timestamp */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap align-middle">
                    <div className="flex items-center gap-1.5">
                      <CallDirectionBadge direction={call.direction} compact />
                      <span className="font-bold text-slate-900 font-mono text-[11px]">{call.call_id}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 flex items-center gap-1 mt-0.5">
                      <Clock className="w-3 h-3 text-slate-400 shrink-0" />
                      <span>{call.displayDateTime || call.call_timestamp || 'Just now'}</span>
                    </div>
                  </td>

                  {/* Farmer Details */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap align-middle">
                    <div className="font-bold text-slate-900">{call.farmer_name}</div>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                      {maskPhoneNumber(call.phone_number || call.phone)}
                    </div>
                  </td>

                  {/* District & Village */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap align-middle">
                    <div className="font-medium text-slate-800">{call.district || 'Mandya'}</div>
                    <div className="text-[10px] text-slate-500 flex items-center gap-1 mt-0.5">
                      <MapPin className="w-2.5 h-2.5 text-slate-400 shrink-0" />
                      <span>{call.village || 'N/A'}</span>
                    </div>
                  </td>

                  {/* Primary Language (Neutral uniform color) */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap text-center align-middle">
                    <span className="inline-flex items-center justify-center px-2.5 py-0.5 rounded-full font-bold text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                      {call.primary_language || 'Hindi'}
                    </span>
                  </td>

                  {/* Pictorial 4-Parameter Weather */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap align-middle min-w-[195px]">
                    <WeatherVisualBadge call={call} compact />
                  </td>

                  {/* Dedicated Attempts Column */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap text-center align-middle">
                    <span className={`inline-flex items-center justify-center font-mono text-[11px] font-bold px-2 py-0.5 rounded-md ${
                      attemptNumber > 1 ? 'bg-amber-50 text-amber-800 border border-amber-200' : 'bg-slate-100 text-slate-700'
                    }`}>
                      {attemptLabel}
                    </span>
                  </td>

                  {/* Dedicated Duration Column */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap text-center align-middle text-slate-600 font-mono text-[11px] font-medium">
                    {formatDuration(call.duration_seconds || call.duration_sec)}
                  </td>

                  {/* Status & Disposition (Uniform 2-line layout with right-aligned SMS Sent in a single straight line) */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap align-middle min-w-[245px]">
                    <div className="flex items-center justify-between gap-2.5 flex-nowrap">
                      <div className="flex items-center gap-1.5 flex-nowrap">
                        {getStatusBadge(
                          isPastMissedCb ? 'Callback Missed' : call.status,
                          isPastMissedCb ? 'Callback not placed in time' : call.disposition,
                          call.skip_reason
                        )}
                        {(call.direction === 'incoming' || call.direction === 'inbound') && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-teal-50 text-teal-700 border border-teal-200 whitespace-nowrap shrink-0" title="The farmer rang us">
                            <PhoneIncoming className="w-3 h-3" />Incoming
                          </span>
                        )}
                        {call.is_test && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-violet-50 text-violet-700 border border-violet-200 whitespace-nowrap shrink-0">
                            TEST
                          </span>
                        )}
                      </div>
                      {(Number(call.messages_sent || 0) > 0 || call.status === 'Completed' || call.disposition === 'Weather Delivered' || call.understood_weather === 'yes') && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200 whitespace-nowrap shrink-0 ml-auto" title="Weather advisory SMS sent to farmer">
                          <MessageSquare className="w-2.5 h-2.5 text-sky-600 shrink-0" />
                          <span>SMS Sent</span>
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-slate-500 font-medium mt-1 leading-normal whitespace-nowrap" title={call.disposition}>
                      {isPastMissedCb ? (
                        <span className="text-rose-700 font-semibold">Missed callback window</span>
                      ) : hasCallback ? (
                        <span className="inline-flex items-center gap-1 text-amber-800 font-semibold">
                          <Calendar className="w-2.5 h-2.5 text-amber-600 shrink-0" />
                          <span>{call.scheduled_callback_time || 'Callback Pending'}</span>
                        </span>
                      ) : (call.next_attempt_at && isToday) ? (
                        <span className="text-amber-700 font-semibold">
                          Next: {String(call.next_attempt_at).split(', ')[1] || call.next_attempt_at}
                        </span>
                      ) : (
                        <span>{shortenDisposition(call.disposition)}</span>
                      )}
                    </div>
                  </td>

                  {/* Action / Inspect & Call Back */}
                  <td className="px-3.5 py-2.5 whitespace-nowrap text-right align-middle min-w-[130px]">
                    <div className="flex items-center justify-end gap-1.5">
                      {isPendingCb && onCallBack && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onCallBack(call);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold text-white bg-trust-green hover:bg-emerald-700 shadow-2xs transition-colors cursor-pointer shrink-0"
                          title="Call back now to fulfill this requested callback"
                        >
                          <PhoneCall className="w-3 h-3" />
                          <span>Call Back</span>
                        </button>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectCall(call);
                        }}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold text-trust-navy bg-slate-100 hover:bg-trust-navy hover:text-white transition-colors cursor-pointer shrink-0"
                      >
                        <span>Inspect</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default CallHistoryTable;
