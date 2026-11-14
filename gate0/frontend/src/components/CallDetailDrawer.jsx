import React from 'react';
import { 
  X, 
  CloudRain, 
  Thermometer, 
  Wind, 
  Droplets, 
  Phone, 
  MapPin, 
  MessageSquare,
  Clock,
  Calendar,
  User,
  Bot
} from 'lucide-react';

import { maskPhoneNumber } from '../utils';

const LANG_CODES = { Hindi: 'hi', Kannada: 'kn', Telugu: 'te', English: 'en' };
// Fonts that carry the Indian scripts, so Kannada, Telugu and Hindi are drawn properly on every device
const INDIC_FONTS = "'Noto Sans Kannada', 'Noto Sans Telugu', 'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', Inter, system-ui, sans-serif";

export const CallDetailDrawer = ({ call, onClose }) => {

  if (!call) return null;

  const rawTranscript = call.transcript_preview || call.transcript || '';

  const formatDuration = (seconds) => {
    const s = parseInt(seconds, 10);
    if (isNaN(s) || s <= 0) return '0s';
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  const isCallback = Boolean(call.scheduled_callback_time) || call.disposition === 'Callback Requested';
  const attempts = Array.isArray(call.attempts_log) ? call.attempts_log : [];

  // Why the call is not finished, in plain words (a rejected call and an unpicked one look the same to the network)
  const lastAttempt = attempts.length > 0 ? attempts[attempts.length - 1] : null;
  const retryNote = (() => {
    if (!lastAttempt || !['Retrying', 'Unanswered', 'Not Confirmed', 'Failed'].includes(call.status)) return null;
    const attemptText = `attempt ${call.attempts_used || attempts.length} of ${call.max_attempts || 3}`;
    const when = call.next_attempt_at ? `Next try: ${call.next_attempt_at}.` : 'No attempts are left for today.';
    if (['No Answer or Rejected', 'Busy'].includes(lastAttempt.status)) {
      return { title: 'Not picked up or rejected', text: `The phone network reports a rejected call and an unpicked call the same way, so each counts as a missed attempt (${attemptText}). ${when}` };
    }
    if (lastAttempt.status === 'Answered') {
      return { title: 'Picked up, not confirmed', text: `The farmer answered but did not confirm they understood the weather (${attemptText}). ${when}` };
    }
    if (lastAttempt.status === 'Failed') {
      return { title: 'Call could not be placed', text: `A provider or number problem. A failed call is retried once, then shown to the team (${attemptText}). ${when}` };
    }
    return null;
  })();

  // Parse transcript array or text
  let transcriptItems = [];
  if (Array.isArray(call.transcript)) {
    transcriptItems = call.transcript;
  } else if (typeof call.transcript === 'string') {
    try {
      const parsed = JSON.parse(call.transcript);
      if (Array.isArray(parsed)) transcriptItems = parsed;
    } catch {
      // plain string
    }
  }

  const tempDisplay = call.weather_temp != null ? `${call.weather_temp}°C` : (call.temperature || 'N/A');
  const windDisplay = call.weather_windspeed != null ? `${call.weather_windspeed} km/h` : (call.wind || 'N/A');
  const rainDisplay = call.weather_rainfall != null ? `${call.weather_rainfall}%` : (call.rainfall_chance || 'N/A');
  const humidityDisplay = call.weather_humidity != null ? `${call.weather_humidity}%` : (call.humidity || 'N/A');

  return (
    <>
      {/* Backdrop */}
      <div 
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 transition-opacity"
      />

      {/* Drawer Container */}
      <aside className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-2xl bg-white shadow-2xl flex flex-col border-l border-slate-200 animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-sm text-slate-900">
                {call.call_id}
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                {call.displayDateTime || call.call_timestamp || 'Active Call'}
              </span>
            </div>
            <p className="text-[11px] font-bold tracking-wider text-slate-500 uppercase mt-0.5">
              Call Inspection
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drawer Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-5 md:p-6 space-y-6">
          {(call.status === 'In Call' || call.status === 'In Queue') && (
            <div className="p-4 rounded-2xl bg-blue-50 border border-blue-200 text-blue-900 text-xs font-semibold" role="status">
              {call.status === 'In Call' ? 'This call is in progress.' : 'This call is waiting in the queue.'} The result, transcript and weather appear here when it ends.
            </div>
          )}
          {/* Farmer Profile Card */}
          <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80">
            <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
              Farmer Profile & Contact
            </span>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-2">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-2xl bg-trust-navy text-white flex items-center justify-center font-bold text-base shadow-xs">
                  {(call.farmer_name || 'F').charAt(0)}
                </div>
                <div>
                  <h4 className="text-base font-bold text-slate-900">
                    {call.farmer_name || 'Unassigned'}
                  </h4>
                  <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                    <span className="flex items-center gap-1">
                      <Phone className="w-3 h-3 text-slate-400" />
                      <span className="font-mono">{maskPhoneNumber(call?.phone_number || call?.phone)}</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-slate-400" />
                      {call.village || 'N/A'}, {call.district || 'Mandya'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`px-2.5 py-1 rounded-xl text-xs font-bold border ${
                    call.primary_language === 'English'
                      ? 'bg-blue-50 text-blue-700 border-blue-200'
                      : call.primary_language === 'Kannada'
                      ? 'bg-purple-50 text-purple-700 border-purple-200'
                      : 'bg-amber-50 text-amber-700 border-amber-200'
                  }`}
                >
                  {call.primary_language || 'Hindi'}
                </span>
                <span className="px-2.5 py-1 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-trust-green font-mono">
                  {call.farmer_id || 'N/A'}
                </span>
                <span className="px-2.5 py-1 rounded-xl bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700 flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3 text-slate-400" />
                  {formatDuration(call.duration_seconds || call.duration_sec)}
                </span>
              </div>
            </div>
          </div>

          {/* Callback Requested Highlight (if present) */}
          {isCallback && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 space-y-1.5">
              <div className="flex items-center gap-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
                <Calendar className="w-4 h-4 text-amber-700" />
                <span>Specific Reschedule / Callback Requested</span>
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-amber-800">Scheduled Callback Slot:</span>
                <span className="font-bold font-mono text-amber-900 bg-amber-100 px-2.5 py-0.5 rounded-lg border border-amber-300">
                  {call.scheduled_callback_time || 'Today, 5:00 PM'}
                </span>
              </div>
              <p className="text-[11px] text-amber-700 leading-relaxed pt-0.5">
                Callback status: <strong>{call.callback_status || 'pending'}</strong>
                {call.callback_requested_text ? ` (the farmer said: ${call.callback_requested_text})` : ''}. One call is placed at that time and it is not retried.
              </p>
            </div>
          )}

          {/* Why the call is not finished yet */}
          {retryNote && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 space-y-1">
              <span className="text-[10px] font-bold tracking-wider text-amber-800 uppercase">
                {retryNote.title}
              </span>
              <p className="text-xs text-amber-900 leading-relaxed">{retryNote.text}</p>
            </div>
          )}

          {/* What the voice agent recorded after the call */}
          {(call.summary || call.understood_weather || call.note || call.call_mode) && (
            <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-2">
              <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                Call Result
              </span>
              {call.summary && (
                <p className="text-xs text-slate-700 leading-relaxed">{call.summary}</p>
              )}
              <div className="flex flex-wrap gap-2 text-[11px]">
                {call.understood_weather && (
                  <span className="px-2.5 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-700 font-semibold">
                    Understood: {call.understood_weather}
                  </span>
                )}
                {call.stop_calls_requested === 'yes' && (
                  <span className="px-2.5 py-0.5 rounded-full border bg-rose-50 border-rose-200 text-rose-700 font-semibold">
                    Asked to stop calls
                  </span>
                )}
                {call.call_mode && (
                  <span className="px-2.5 py-0.5 rounded-full border bg-slate-50 border-slate-200 text-slate-500 font-semibold">
                    {call.call_mode}
                  </span>
                )}
              </div>
              {call.note && <p className="text-[11px] text-slate-500 break-words">{call.note}</p>}
            </div>
          )}

          {/* 4-Parameter Weather Delivered */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                4-Parameter Open-Meteo Grounding
              </span>
              <span className="text-xs font-semibold text-emerald-700 flex items-center gap-1 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                <CloudRain className="w-3.5 h-3.5 text-emerald-600" />
                Open-Meteo Ingestion
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {/* 1. Temperature */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 flex items-center gap-1 font-semibold">
                  <Thermometer className="w-3.5 h-3.5 text-amber-500" />
                  1. Temperature
                </span>
                <div className="font-bold text-base text-slate-900 mt-1">{tempDisplay}</div>
              </div>

              {/* 2. Wind Speed */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 flex items-center gap-1 font-semibold">
                  <Wind className="w-3.5 h-3.5 text-slate-500" />
                  2. Wind Speed
                </span>
                <div className="font-bold text-base text-slate-900 mt-1">{windDisplay}</div>
              </div>

              {/* 3. Rainfall Probability */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 flex items-center gap-1 font-semibold">
                  <CloudRain className="w-3.5 h-3.5 text-blue-500" />
                  3. Rain Chance
                </span>
                <div className="font-bold text-base text-slate-900 mt-1">{rainDisplay}</div>
              </div>

              {/* 4. Relative Humidity */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <span className="text-[10px] text-slate-400 flex items-center gap-1 font-semibold">
                  <Droplets className="w-3.5 h-3.5 text-cyan-500" />
                  4. Humidity
                </span>
                <div className="font-bold text-base text-slate-900 mt-1">{humidityDisplay}</div>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-100 text-xs text-slate-700 leading-relaxed">
              <strong className="text-trust-navy block mb-0.5">Forecast Summary:</strong>
              {call.advisory_summary || call.message_text || 'Routine meteorological forecast delivered to farmer.'}
            </div>
          </div>

          {/* Auditability: 2-Retry Cycle Attempt History */}
          {attempts.length > 0 && (
            <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                  Telephony Audit Log (2-Retry Cycle History)
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  {attempts.length} Attempt{attempts.length > 1 ? 's' : ''} Recorded
                </span>
              </div>

              <div className="space-y-2">
                {attempts.map((att, idx) => (
                  <div 
                    key={att.id || idx} 
                    className="p-3 rounded-xl bg-slate-50 border border-slate-200/70 text-xs flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="w-5 h-5 rounded-full bg-slate-200 flex items-center justify-center font-bold text-[10px] text-slate-700 font-mono">
                        {att.attempt_number || idx + 1}
                      </span>
                      <div>
                        <div className="font-bold text-slate-800 flex items-center gap-1.5">
                          <span>Attempt {att.attempt_number || idx + 1}:</span>
                          <span className={`px-2 py-0.2 rounded text-[10px] ${
                            att.status === 'Answered' 
                              ? 'bg-emerald-100 text-emerald-800' 
                              : (att.status === 'Busy' ? 'bg-amber-100 text-amber-800' : 'bg-rose-100 text-rose-800')
                          }`}>
                            {att.status}
                          </span>
                        </div>
                        {att.error_message && (
                          <p className="text-[10px] text-slate-500 mt-0.5">{att.error_message}</p>
                        )}
                      </div>
                    </div>
                    <div className="text-right font-mono text-[11px] text-slate-500">
                      {att.duration_seconds}s
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Conversation: what was actually said, in the language of the call, with the English summary on top */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3.5">
            <div className="flex items-center justify-between gap-2 pb-2 border-b border-slate-100">
              <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Conversation</span>
              {(call.language || call.primary_language) && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                  {call.language || call.primary_language}
                </span>
              )}
            </div>

            {call.summary && (
              <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-100 text-xs text-slate-700 leading-relaxed">
                <strong className="block text-[10px] font-bold tracking-wider text-blue-700 uppercase mb-0.5">In English</strong>
                {call.summary}
              </div>
            )}

            {transcriptItems.length > 0 ? (
              <div className="space-y-3 pt-1">
                {transcriptItems.map((turn, idx) => {
                  // Both schemas: { speaker, text } from the backend and { role, content } from the provider
                  const rawSpeaker = turn.speaker || turn.role || turn.author || (idx % 2 === 0 ? 'Agent' : 'Farmer');
                  const isAgent = /agent|bot|assistant/i.test(rawSpeaker);
                  const isSystem = /system|notice/i.test(rawSpeaker);
                  const text = String(turn.text || turn.content || turn.message || (typeof turn === 'string' ? turn : ''))
                    .replace(/\s*\n\s*/g, '\n').trim();
                  if (!text) return null;

                  if (isSystem) {
                    return (
                      <div key={idx} className="p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs">
                        <strong>Note:</strong> {text}
                      </div>
                    );
                  }

                  return (
                    <div key={idx} className={`flex gap-2.5 ${isAgent ? 'items-start' : 'items-start flex-row-reverse'}`}>
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 shadow-2xs ${
                        isAgent ? 'bg-trust-navy text-white' : 'bg-emerald-600 text-white'
                      }`}>
                        {isAgent ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                      </div>
                      <div className={`px-3.5 py-3 rounded-2xl max-w-[85%] shadow-2xs ${
                        isAgent
                          ? 'bg-slate-50 text-slate-800 border border-slate-200/60 rounded-tl-xs'
                          : 'bg-emerald-50/80 text-emerald-950 border border-emerald-200/80 rounded-tr-xs'
                      }`}>
                        <div className="font-bold text-[10px] uppercase tracking-wider text-slate-400 mb-1">
                          {isAgent ? 'Agent' : (call.farmer_name || 'Farmer')}
                        </div>
                        <p
                          lang={LANG_CODES[call.language || call.primary_language] || undefined}
                          className="whitespace-pre-line text-[14px] leading-7 break-words"
                          style={{ fontFamily: INDIC_FONTS }}
                        >
                          {text}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : rawTranscript ? (
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-800 leading-7 whitespace-pre-line" style={{ fontFamily: INDIC_FONTS }}>
                {String(rawTranscript).trim()}
              </div>
            ) : (
              <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl bg-slate-50/50 text-slate-400 text-xs">
                <MessageSquare className="w-5 h-5 mx-auto mb-1.5 text-slate-400" />
                No conversation was recorded for this call (it may not have been picked up).
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
