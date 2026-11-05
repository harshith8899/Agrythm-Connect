import React from 'react';
import { 
  ChevronRight, 
  Clock, 
  MapPin, 
  CloudRain, 
  CheckCircle2, 
  AlertCircle, 
  PhoneOutgoing,
  Database,
  ExternalLink,
  ShieldAlert,
  Calendar,
  RefreshCw,
  PhoneCall
} from 'lucide-react';
import { API_CONFIG } from '../utils/constants';
import { maskPhoneNumber } from '../utils';

export const CallHistoryTable = ({ 
  callLogs, 
  onSelectCall, 
  selectedCallId, 
  onResetFilters, 
  isFiltered,
  isBackendOnline = true,
  onRefresh
}) => {
  const getStatusBadge = (status, disposition, skipReason) => {
    const s = String(status || '').toLowerCase();
    switch (s) {
      case 'completed':
      case 'answered':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            <span>Completed</span>
          </span>
        );
      case 'callback scheduled':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <Clock className="w-3 h-3 text-blue-600" />
            <span>Callback Scheduled</span>
          </span>
        );
      case 'not confirmed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertCircle className="w-3 h-3 text-amber-600" />
            <span>Not Confirmed</span>
          </span>
        );
      case 'declined':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <AlertCircle className="w-3 h-3 text-slate-500" />
            <span>Declined</span>
          </span>
        );
      case 'unanswered':
      case 'busy':
      case 'no_answer':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <PhoneOutgoing className="w-3 h-3 text-amber-600" />
            <span>Unanswered</span>
          </span>
        );
      case 'retrying':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <RefreshCw className="w-3 h-3 text-amber-600 animate-spin" />
            <span>Retrying</span>
          </span>
        );
      case 'escalated':
      case 'requires escalation':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
            <ShieldAlert className="w-3 h-3 text-purple-600" />
            <span>Escalated</span>
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertCircle className="w-3 h-3 text-rose-600" />
            <span>Failed</span>
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

  if (!callLogs || callLogs.length === 0) {
    if (!isBackendOnline) {
      return (
        <div className="bg-rose-50/40 rounded-2xl border-2 border-dashed border-rose-200 p-12 text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-600 mx-auto">
            <AlertCircle className="w-7 h-7" />
          </div>
          
          <div>
            <h3 className="text-base font-bold text-rose-900">
              Backend API Offline
            </h3>
            <p className="text-xs text-rose-700 max-w-md mx-auto mt-1 leading-relaxed">
              Unable to reach <code className="bg-rose-100 px-1 py-0.5 rounded font-mono font-bold text-rose-950">{API_CONFIG.callLogsApiUrl}</code>.
              Run <code className="bg-rose-100 px-1.5 py-0.5 rounded font-mono font-bold text-rose-950">npm run backend</code> in your terminal to start the orchestrator and load call logs.
            </p>
          </div>

          {onRefresh && (
            <button
              onClick={onRefresh}
              className="px-4 py-2 rounded-xl bg-rose-600 text-white text-xs font-bold hover:bg-rose-700 transition-colors shadow-xs cursor-pointer inline-flex items-center gap-1.5"
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
            {isFiltered ? 'No Matching Call Records' : 'No Call Records Yet'}
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            {isFiltered 
              ? 'No voice call logs match the selected search or filter criteria. Try adjusting your filters.'
              : 'Import farmers in the Farmer Directory, then click "Send now" in the header to place today\'s calls.'}
          </p>
        </div>

        {isFiltered ? (
          onResetFilters && (
            <button
              onClick={onResetFilters}
              className="px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer"
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
      {/* Table Header Controls */}
      <div className="p-4 sm:p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Live Call History & Telemetry Logs
          </span>
          <h3 className="text-base font-bold text-slate-900">
            Voice Agent 4-Parameter Weather Advisories & Retries
          </h3>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Showing live records from the backend database</span>
        </div>
      </div>

      {/* Responsive Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50/80 text-[11px] font-bold tracking-wider text-slate-500 uppercase border-b border-slate-200/80">
            <tr>
              <th className="px-4 py-3.5">Call ID & Time</th>
              <th className="px-4 py-3.5">Farmer & Contact</th>
              <th className="px-4 py-3.5">District / Village</th>
              <th className="px-4 py-3.5">Language</th>
              <th className="px-4 py-3.5 min-w-[200px]">4-Parameter Weather</th>
              <th className="px-4 py-3.5">Attempts</th>
              <th className="px-4 py-3.5">Duration</th>
              <th className="px-4 py-3.5">Status & Disposition</th>
              <th className="px-4 py-3.5">Callback Requested</th>
              <th className="px-4 py-3.5 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {callLogs.map((call) => {
              const isSelected = selectedCallId === call.call_id;
              const hasCallback = Boolean(call.scheduled_callback_time) || call.disposition === 'Callback Requested';
              const attemptNumber = call.attempts_log?.length || (call.retry_count ? call.retry_count + 1 : 1);
              const attemptLabel = `Attempt ${attemptNumber}/${call.max_attempts || 3}`;

              return (
                <tr
                  key={call.call_id}
                  onClick={() => onSelectCall(call)}
                  className={`cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-blue-50/70 hover:bg-blue-50'
                      : 'hover:bg-slate-50/70'
                  }`}
                >
                  {/* Call ID & Timestamp */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <div className="font-bold text-slate-900 font-mono">{call.call_id}</div>
                    <div className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                      <Clock className="w-3 h-3 text-slate-400" />
                      {call.displayDateTime || call.call_timestamp || 'Just now'}
                    </div>
                  </td>

                  {/* Farmer Details */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <div className="font-bold text-slate-900">{call.farmer_name}</div>
                    <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                      {maskPhoneNumber(call.phone_number || call.phone)}
                    </div>
                  </td>

                  {/* District & Village */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <div className="font-medium text-slate-800">{call.district || 'Mandya'}</div>
                    <div className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                      <MapPin className="w-3 h-3 text-slate-400" />
                      {call.village || 'N/A'}
                    </div>
                  </td>

                  {/* Primary Language */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full font-bold text-[11px] border ${
                        call.primary_language === 'English'
                          ? 'bg-blue-50 text-blue-700 border-blue-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}
                    >
                      {call.primary_language || 'Hindi'}
                    </span>
                  </td>

                  {/* 4-Parameter Weather Advisory */}
                  <td className="px-4 py-3.5">
                    <div className="flex items-start gap-1.5">
                      <CloudRain className="w-3.5 h-3.5 text-trust-navy mt-0.5 shrink-0" />
                      <div>
                        <div className="font-semibold text-slate-800 text-[11px] flex items-center gap-1.5">
                          <span>{call.weather_forecast || 'Weather Report'}</span>
                          {call.weather_temp != null && (
                            <span className="font-mono text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded text-[10px]">
                              {call.weather_temp}°C
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                          {call.advisory_summary || `Temp ${call.temperature || 'N/A'} | Rain ${call.rainfall_chance || 'N/A'}`}
                        </p>
                      </div>
                    </div>
                  </td>

                  {/* Attempts (1/3, 2/3, 3/3) */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <span className={`inline-flex items-center gap-1 font-mono text-[11px] font-bold px-2 py-0.5 rounded-md ${
                      attemptNumber > 1 ? 'bg-amber-50 text-amber-800 border border-amber-200' : 'bg-slate-100 text-slate-700'
                    }`}>
                      {attemptLabel}
                    </span>
                  </td>

                  {/* Duration */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-slate-600 font-mono text-[11px]">
                    {formatDuration(call.duration_seconds || call.duration_sec)}
                  </td>

                  {/* Status & Disposition */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <div className="flex flex-col gap-1 items-start">
                      {getStatusBadge(call.status, call.disposition, call.skip_reason)}
                      {call.disposition && (
                        <span className="text-[10px] text-slate-500 font-medium">
                          {call.disposition}
                        </span>
                      )}
                      {call.next_attempt_at && (
                        <span className="text-[10px] text-amber-700 font-semibold">
                          Next try {String(call.next_attempt_at).split(', ')[1] || call.next_attempt_at}
                        </span>
                      )}
                      {call.status === 'Unanswered' && call.attempts_used > 0 && (
                        <span className="text-[10px] text-slate-400">
                          after {call.attempts_used} attempt{call.attempts_used > 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Dedicated Callback Requested Indicator */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {hasCallback ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold bg-amber-50 text-amber-900 border border-amber-300 shadow-2xs">
                        <Calendar className="w-3 h-3 text-amber-600 shrink-0" />
                        <span>{call.scheduled_callback_time || 'Callback Pending'}</span>
                      </span>
                    ) : (
                      <span className="text-slate-400 font-mono text-[11px]">-</span>
                    )}
                  </td>

                  {/* Action / Inspect */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectCall(call);
                      }}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold text-trust-navy bg-slate-100 hover:bg-trust-navy hover:text-white transition-colors cursor-pointer"
                    >
                      <span>Inspect</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
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
