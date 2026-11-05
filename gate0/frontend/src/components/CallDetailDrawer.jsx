import React, { useState } from 'react';
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
  ShieldAlert,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  User,
  Bot,
  Languages
} from 'lucide-react';

import { maskPhoneNumber, formatTranscriptText, hasIndicScript } from '../utils';

export const CallDetailDrawer = ({ call, onClose }) => {
  if (!call) return null;

  const [transcriptMode, setTranscriptMode] = useState('romanized'); // 'romanized' | 'translated' | 'original'

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
  const isEscalated = call.status === 'Escalated' || call.disposition === 'Non-Weather Inquiry';
  const attempts = Array.isArray(call.attempts_log) ? call.attempts_log : [];

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
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 transition-opacity"
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
              Call Inspection & SQLite Persistence Telemetry
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
                The farmer indicated unavailability during the morning run. An automated callback is queued in the SQLite orchestrator.
              </p>
            </div>
          )}

          {/* Agronomic Boundary Escalation Highlight (if present) */}
          {isEscalated && (
            <div className="p-4 rounded-2xl bg-purple-50 border border-purple-200 space-y-1.5">
              <div className="flex items-center gap-2 text-purple-900 font-bold text-xs uppercase tracking-wider">
                <ShieldAlert className="w-4 h-4 text-purple-700" />
                <span>Agronomic Boundary Guardrail Enforced</span>
              </div>
              <p className="text-xs text-purple-800 leading-relaxed">
                Disposition: <strong>Non-Weather Inquiry</strong>. The farmer requested chemical/pesticide dosage advice.
                Agrythm Connect strictly limits dialogue to meteorology; advice was declined and the case has been routed to field agronomists.
              </p>
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

          {/* Full Conversation Transcript */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                    Dialogue Transcript
                  </span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                    {call.primary_language || 'Kannada'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {transcriptMode === 'romanized' && 'Showing spoken language in English script'}
                  {transcriptMode === 'translated' && 'Showing English translation'}
                  {transcriptMode === 'original' && 'Showing original regional script'}
                </p>
              </div>

              {/* Segmented Script / Translate Toggle */}
              <div className="inline-flex p-0.5 rounded-lg bg-slate-100 border border-slate-200 text-[11px] font-semibold self-start sm:self-auto shadow-2xs">
                <button
                  type="button"
                  onClick={() => setTranscriptMode('romanized')}
                  className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                    transcriptMode === 'romanized'
                      ? 'bg-white text-trust-navy shadow-xs font-bold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                  title="Display in English text preserving the spoken language (Transliteration)"
                >
                  English Script
                </button>
                <button
                  type="button"
                  onClick={() => setTranscriptMode('translated')}
                  className={`px-2.5 py-1 rounded-md transition-all cursor-pointer flex items-center gap-1 ${
                    transcriptMode === 'translated'
                      ? 'bg-white text-trust-navy shadow-xs font-bold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                  title="Translate dialogue into English"
                >
                  <Languages className="w-3 h-3 text-trust-green" />
                  Translate
                </button>
                <button
                  type="button"
                  onClick={() => setTranscriptMode('original')}
                  className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                    transcriptMode === 'original'
                      ? 'bg-white text-trust-navy shadow-xs font-bold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                  title="View original native script (Kannada / Hindi)"
                >
                  Original
                </button>
              </div>
            </div>

            {transcriptItems.length > 0 ? (
              <div className="space-y-3 pt-1">
                {transcriptItems.map((turn, idx) => {
                  // Normalize both internal schema ({ speaker, text }) and Sarvam Agent schema ({ role, content, language_name })
                  const rawSpeaker = turn.speaker || turn.role || turn.author || (idx % 2 === 0 ? 'Agent' : 'Farmer');
                  const isAgent = /agent|bot|assistant/i.test(rawSpeaker);
                  const isSystem = /system|notice/i.test(rawSpeaker);
                  const displaySpeaker = isSystem ? 'System' : (isAgent ? 'Agent' : 'Farmer');
                  const turnText = turn.text || turn.content || turn.message || (typeof turn === 'string' ? turn : '');

                  if (isSystem) {
                    return (
                      <div key={idx} className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                        <strong>System Notice:</strong> {formatTranscriptText(turnText, transcriptMode)}
                      </div>
                    );
                  }

                  const renderedText = formatTranscriptText(turnText, transcriptMode);

                  return (
                    <div 
                      key={idx} 
                      className={`flex gap-2.5 ${isAgent ? 'items-start' : 'items-start flex-row-reverse'}`}
                    >
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 shadow-2xs ${
                        isAgent ? 'bg-trust-navy text-white' : 'bg-emerald-600 text-white'
                      }`}>
                        {isAgent ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                      </div>
                      <div className={`p-3.5 rounded-2xl max-w-[85%] text-xs leading-relaxed shadow-2xs ${
                        isAgent 
                          ? 'bg-slate-50 text-slate-800 border border-slate-200/60 rounded-tl-xs' 
                          : 'bg-emerald-50/80 text-emerald-950 border border-emerald-200/80 rounded-tr-xs'
                      }`}>
                        <div className="flex items-center justify-between gap-3 mb-1.5">
                          <span className="font-bold text-[10px] uppercase tracking-wider text-slate-400">
                            {displaySpeaker}
                          </span>
                          {transcriptMode !== 'original' && hasIndicScript(turnText) && (
                            <span className="text-[9px] font-medium px-1.5 py-0.2 rounded bg-white text-slate-500 border border-slate-200 shadow-2xs">
                              {transcriptMode === 'romanized' ? 'English script' : 'English translation'}
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-line text-slate-800 font-sans">
                          {renderedText}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : rawTranscript ? (
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-800 leading-relaxed font-sans">
                {formatTranscriptText(rawTranscript, transcriptMode)}
              </div>
            ) : (
              <div className="p-6 text-center border border-dashed border-slate-200 rounded-xl bg-slate-50/50 text-slate-400 text-xs">
                <MessageSquare className="w-5 h-5 mx-auto mb-1.5 text-slate-400" />
                No transcript preview provided in the database for this call.
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
