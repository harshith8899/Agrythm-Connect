import React, { useState, useMemo } from 'react';
import { 
  X, 
  Phone, 
  PhoneCall,
  PhoneIncoming,
  Languages,
  MapPin, 
  MessageSquare,
  Clock,
  Calendar,
  User,
  Bot,
  Info
} from 'lucide-react';

import { maskPhoneNumber, getCallTranslation, formatTranscriptText, hasIndicScript, isTodayDateStr, isCallToday } from '../utils';
import { CallDirectionBadge } from './CallDirectionBadge';
import { WeatherVisualBadge } from './WeatherVisualBadge';

const LANG_CODES = { Hindi: 'hi', Kannada: 'kn', Telugu: 'te', English: 'en' };
const INDIC_FONTS = "'Noto Sans Kannada', 'Noto Sans Telugu', 'Noto Sans Devanagari', 'Nirmala UI', 'Mangal', Inter, system-ui, sans-serif";

const AttemptRowWithHover = ({ attempt, isCurrent, onSelect }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const durationStr = (() => {
    const s = parseInt(attempt.duration_seconds || attempt.duration_sec, 10);
    if (isNaN(s) || s <= 0) return '0s';
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  })();

  const weatherText = attempt.weather_temp
    ? `${attempt.weather_temp}°C · Rain: ${attempt.weather_rainfall ?? 0}% · Wind: ${attempt.weather_windspeed ?? 0}km/h`
    : (attempt.temperature ? `${attempt.temperature}` : 'No weather data');

  return (
    <div
      className={`relative p-3 rounded-xl border transition-all ${
        isCurrent
          ? 'bg-blue-50/70 border-blue-200 ring-1 ring-blue-300/40 shadow-2xs'
          : 'bg-slate-50/60 border-slate-200/80 hover:bg-white hover:border-slate-300 hover:shadow-2xs'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <CallDirectionBadge direction={attempt.direction} compact />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-xs text-slate-900 truncate">
                {attempt.call_id}
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                {attempt.created_at ? attempt.created_at.slice(0, 16).replace('T', ' ') : (attempt.call_date || '')}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-500">
              <span className={`font-semibold ${
                attempt.status === 'Completed' || attempt.status === 'Answered'
                  ? 'text-emerald-700'
                  : (attempt.status === 'Retrying' || attempt.status === 'Unanswered' ? 'text-amber-700' : 'text-slate-700')
              }`}>
                {attempt.status}
              </span>
              {attempt.disposition && (
                <>
                  <span>•</span>
                  <span className="text-slate-500 truncate max-w-[140px]">{attempt.disposition}</span>
                </>
              )}
              <span>•</span>
              <span className="font-mono">{durationStr}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {isCurrent ? (
            <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-200">
              Active
            </span>
          ) : (
            <>
              <button
                type="button"
                onClick={onSelect}
                className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-trust-navy bg-white border border-slate-200 hover:bg-trust-navy hover:text-white transition-colors cursor-pointer shadow-2xs"
              >
                Inspect
              </button>

              {/* Hover Button for Note preview (only on other attempts with notes) */}
              {(attempt.summary || attempt.note) && (
                <div 
                  className="relative"
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                >
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold text-slate-600 bg-white border border-slate-200/90 hover:text-trust-navy hover:border-slate-300 hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
                    title="Hover to preview attempt note"
                  >
                    <Info className="w-3.5 h-3.5 text-trust-navy" />
                    <span>Note</span>
                  </button>

                  {/* Hover Floating Popover with strictly the note (no redundant parameters) */}
                  {showTooltip && (
                    <div className="absolute right-0 bottom-full mb-2 z-50 w-72 p-3 rounded-xl bg-slate-900/95 backdrop-blur-md text-white shadow-xl text-xs space-y-1.5 pointer-events-none animate-in fade-in zoom-in-95 duration-150 border border-slate-800">
                      <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-800 pb-1">
                        <span className="font-semibold uppercase tracking-wider">Attempt Note</span>
                        <span className="font-mono">{attempt.call_id}</span>
                      </div>
                      <p className="text-[11px] text-slate-200 leading-relaxed font-normal">
                        {attempt.summary || attempt.note}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export const CallDetailDrawer = ({ call, onClose, onCallBack, allCalls = [], onSelectCall }) => {
  const [callingBack, setCallingBack] = useState(false);
  const [callNote, setCallNote] = useState(null);
  const [english, setEnglish] = useState({ show: false, loading: false, turns: null, error: '' });   // the English under each turn
  const [transcriptMode, setTranscriptMode] = useState('romanized');

  const toggleEnglish = async () => {
    if (english.show) {
      setEnglish((e) => ({ ...e, show: false }));
      return;
    }
    if (english.turns) {
      setEnglish((e) => ({ ...e, show: true }));
      return;
    }
    setEnglish({ show: true, loading: true, turns: null, error: '' });
    try {
      const r = await getCallTranslation(call.call_id);
      setEnglish({ show: true, loading: false, turns: r.turns || [], error: r.error || '' });
    } catch (err) {
      setEnglish({ show: true, loading: false, turns: null, error: err.message || 'Could not translate' });
    }
  };

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

  const isToday = call.is_today ?? (isTodayDateStr(call.call_date) || isCallToday(call.call_date || call.created_at || call.call_timestamp));
  const isPendingCallback = isToday && (call.status === 'Callback Scheduled' || call.callback_status === 'pending');
  const isCallback = (isToday && (Boolean(call.scheduled_callback_time) || call.disposition === 'Callback Requested' || isPendingCallback)) || call.callback_status === 'pending';
  const isPastMissedCb = !isToday && (call.status === 'Callback Scheduled' || call.callback_status === 'missed' || call.callback_status === 'pending');
  const attempts = Array.isArray(call.attempts_log) ? call.attempts_log : [];

  // All recorded attempts/calls for this farmer strictly on the current day of the clicked call
  const farmerAttempts = useMemo(() => {
    if (!call) return [];
    const fid = String(call.farmer_id || '').trim();
    const phone = String(call.phone_number || call.phone || '').trim();
    const getCallDateString = (c) => {
      if (!c) return '';
      if (c.call_date && /^\d{4}-\d{2}-\d{2}/.test(c.call_date)) return c.call_date.slice(0, 10);
      if (c.date && /^\d{4}-\d{2}-\d{2}/.test(c.date)) return c.date.slice(0, 10);
      if (c.created_at && /^\d{4}-\d{2}-\d{2}/.test(c.created_at)) return c.created_at.slice(0, 10);
      const match = String(c.call_id || '').match(/\d{4}-\d{2}-\d{2}/);
      if (match) return match[0];
      return '';
    };
    const targetDate = getCallDateString(call);

    // 1. Filter allCalls to match this farmer AND strictly match the selected call's date
    let sameDayCalls = [];
    if (Array.isArray(allCalls) && allCalls.length > 0 && (fid || phone)) {
      sameDayCalls = allCalls.filter((c) => {
        const matchFarmer =
          (fid && String(c.farmer_id || '').trim() === fid) ||
          (phone && String(c.phone_number || c.phone || '').trim() === phone);
        if (!matchFarmer) return false;
        if (targetDate) {
          const cDate = getCallDateString(c);
          return cDate === targetDate;
        }
        return true;
      });
    }

    // Ensure the current call is included in the list
    if (!sameDayCalls.some((c) => c.call_id === call.call_id)) {
      sameDayCalls.push(call);
    }

    // 2. If there are multiple separate call log rows on this day, display them
    if (sameDayCalls.length > 1) {
      return sameDayCalls.sort((a, b) => {
        const da = a.created_at || a.time || a.call_timestamp || '';
        const db = b.created_at || b.time || b.call_timestamp || '';
        return db.localeCompare(da);
      });
    }

    // 3. If there is only 1 call log row on this day, check if it contains multiple attempts in attempts_log
    const attemptsLog = Array.isArray(call.attempts_log) ? call.attempts_log : [];
    if (attemptsLog.length > 1) {
      return attemptsLog.map((att, idx) => {
        const attNum = att.attempt_number || idx + 1;
        const isCurrent = idx === attemptsLog.length - 1;
        return {
          ...call,
          call_id: `${call.call_id} (Attempt ${attNum})`,
          attempt_number: attNum,
          status: att.status || (isCurrent ? call.status : 'Retrying'),
          disposition: att.disposition || att.error_message || (isCurrent ? call.disposition : `Attempt ${attNum}`),
          duration_seconds: att.duration_seconds != null ? att.duration_seconds : 0,
          created_at: att.created_at || att.time || call.created_at,
          direction: att.direction || call.direction,
          isCurrent,
        };
      }).reverse();
    }

    return sameDayCalls;
  }, [call, allCalls]);

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

  return (
    <>
      <div 
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 transition-opacity"
      />

      <aside className="fixed top-0 right-0 bottom-0 z-50 w-full max-w-2xl bg-white shadow-2xl flex flex-col border-l border-slate-200 animate-in slide-in-from-right duration-300">
        {/* Drawer Header with Incoming / Outgoing Arrow Badge */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <CallDirectionBadge direction={call.direction} />
              <span className="font-mono font-bold text-sm text-slate-900">
                {call.call_id}
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                {call.displayDateTime || call.call_timestamp || 'Active Call'}
              </span>
            </div>
            <p className="text-[11px] font-bold tracking-wider text-slate-500 uppercase mt-1">
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
                <span className="px-2.5 py-1 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
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

          {/* Farmer Attempt History (Only attempts for this farmer on the selected day) */}
          {farmerAttempts.length > 0 && (
            <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3 shadow-2xs">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
                    Farmer Attempt History
                  </span>
                  <h4 className="text-xs font-bold text-slate-800 mt-0.5">
                    {call.farmer_name || `Farmer ${call.farmer_id}`} • {call.created_at ? call.created_at.slice(0, 10) : (call.call_date || call.date || 'Today')} ({farmerAttempts.length} Attempt{farmerAttempts.length === 1 ? '' : 's'})
                  </h4>
                </div>
                <span className="text-[11px] text-slate-500 font-mono">
                  {farmerAttempts.length} Record{farmerAttempts.length > 1 ? 's' : ''} on {call.created_at ? call.created_at.slice(0, 10) : (call.call_date || call.date || 'this day')}
                </span>
              </div>

              <div className="space-y-2">
                {farmerAttempts.map((att) => (
                  <AttemptRowWithHover
                    key={att.call_id}
                    attempt={att}
                    isCurrent={att.call_id === call.call_id || att.isCurrent}
                    onSelect={() => onSelectCall && onSelectCall(att)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Callback Requested Highlight (Active for Today) */}
          {isCallback && isToday && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-amber-900 font-bold text-xs uppercase tracking-wider">
                  <Calendar className="w-4 h-4 text-amber-700" />
                  <span>Specific Reschedule / Callback Requested</span>
                </div>
                {isPendingCallback && onCallBack && (
                  <button
                    onClick={async () => {
                      setCallingBack(true);
                      setCallNote(null);
                      try {
                        await onCallBack(call);
                        setCallNote({ ok: true, text: 'Callback call placed. Result will update shortly.' });
                      } catch (err) {
                        setCallNote({ ok: false, text: err.message || 'Call failed' });
                      } finally {
                        setCallingBack(false);
                      }
                    }}
                    disabled={callingBack}
                    className="h-9 px-3.5 rounded-xl justify-center whitespace-nowrap inline-flex items-center gap-1.5 bg-trust-green text-white text-xs font-semibold hover:bg-emerald-700 shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <PhoneCall className={`w-3.5 h-3.5 ${callingBack ? 'animate-pulse' : ''}`} />
                    <span>{callingBack ? 'Calling...' : 'Call Back Now'}</span>
                  </button>
                )}
              </div>
              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-amber-800">Scheduled Callback Slot:</span>
                <span className="font-bold font-mono text-amber-900 bg-amber-100 px-2.5 py-0.5 rounded-lg border border-amber-300">
                  {call.scheduled_callback_time || 'Callback Pending'}
                </span>
              </div>
              <p className="text-[11px] text-amber-700 leading-relaxed pt-0.5">
                Callback status: <strong>{call.callback_status || 'pending'}</strong>
                {call.callback_requested_text ? ` (the farmer said: ${call.callback_requested_text})` : ''}. One call is placed at that time and it is not retried.
              </p>
              {callNote && (
                <div className={`p-2 rounded-lg text-xs font-semibold ${callNote.ok ? 'bg-emerald-100 text-trust-green border border-emerald-200' : 'bg-rose-100 text-rose-700 border border-rose-200'}`}>
                  {callNote.text}
                </div>
              )}
            </div>
          )}

          {/* Missed Callback on Past Day (Does not carry over to next day) */}
          {isPastMissedCb && (
            <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 space-y-1.5">
              <div className="flex items-center gap-2 text-rose-900 font-bold text-xs uppercase tracking-wider">
                <Clock className="w-4 h-4 text-rose-600" />
                <span>Callback Not Placed in Time</span>
              </div>
              <p className="text-xs text-rose-800 leading-relaxed">
                A callback was requested for {call.scheduled_callback_time || 'that day'}{call.callback_requested_text ? ` (${call.callback_requested_text})` : ''}, but could not be completed within the day. In accordance with telephony retry rules, callbacks do not continue into the next day.
              </p>
            </div>
          )}

          {retryNote && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 space-y-1">
              <span className="text-[10px] font-bold tracking-wider text-amber-800 uppercase">
                {retryNote.title}
              </span>
              <p className="text-xs text-amber-900 leading-relaxed">{retryNote.text}</p>
            </div>
          )}

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
              {call.note && call.note.trim() !== String(call.summary || '').trim() && (
                <p className="text-[11px] text-slate-500 break-words">{call.note}</p>
              )}
            </div>
          )}

          {Number(call.messages_sent || 0) > 0 && (
            <div className="p-3.5 rounded-2xl bg-sky-50/70 border border-sky-200/80 flex items-center justify-between text-xs shadow-2xs">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-sky-500" />
                <span className="font-semibold text-sky-950">
                  Advisory SMS Message Dispatched
                </span>
              </div>
              <span className="font-mono font-bold text-sky-700 bg-white px-2.5 py-0.5 rounded-lg border border-sky-200">
                {call.messages_sent} sent (₹{(call.messages_sent * 0.20).toFixed(2)})
              </span>
            </div>
          )}

          {/* Pictorial 4-Parameter Weather Card */}
          <WeatherVisualBadge call={call} />

          {/* Conversation */}
          <div className="p-4 rounded-2xl bg-white border border-slate-200/80 space-y-3.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">Conversation</span>
                {(call.language || call.primary_language) && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                    {call.language || call.primary_language}
                  </span>
                )}
                {transcriptItems.length > 0 && (
                  <button
                    onClick={toggleEnglish}
                    disabled={english.loading}
                    className="h-7 px-2.5 rounded-lg inline-flex items-center justify-center gap-1.5 whitespace-nowrap text-[10px] font-semibold border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <Languages className="w-3 h-3 text-trust-green" />
                    {english.loading ? 'Translating...' : english.show ? 'Hide English' : 'Show English'}
                  </button>
                )}
              </div>

              <div className="inline-flex items-center p-0.5 rounded-lg bg-slate-100 border border-slate-200/60 text-[11px] self-start sm:self-auto">
                <button
                  type="button"
                  onClick={() => setTranscriptMode('romanized')}
                  className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                    transcriptMode === 'romanized'
                      ? 'bg-white text-trust-navy shadow-xs font-bold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
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
                >
                  <Languages className="w-3 h-3 text-trust-green" />
                  Translate to English
                </button>
                <button
                  type="button"
                  onClick={() => setTranscriptMode('original')}
                  className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                    transcriptMode === 'original'
                      ? 'bg-white text-trust-navy shadow-xs font-bold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Original
                </button>
              </div>
            </div>

            {transcriptItems.length > 0 ? (
              <div className="space-y-3 pt-1">
                {transcriptItems.map((turn, idx) => {
                  const rawSpeaker = turn.speaker || turn.role || turn.author || (idx % 2 === 0 ? 'Agent' : 'Farmer');
                  const isAgent = /agent|bot|assistant/i.test(rawSpeaker);
                  const isSystem = /system|notice/i.test(rawSpeaker);
                  const text = String(turn.text || turn.content || turn.message || (typeof turn === 'string' ? turn : ''))
                    .replace(/\s*\n\s*/g, '\n').trim();
                  if (!text) return null;

                  if (isSystem) {
                    return (
                      <div key={idx} className="p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs">
                        <strong>Note:</strong> {formatTranscriptText(text, transcriptMode)}
                      </div>
                    );
                  }

                  const renderedText = formatTranscriptText(text, transcriptMode);

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
                        <div className="flex items-center justify-between gap-3 mb-1">
                          <span className="font-bold text-[10px] uppercase tracking-wider text-slate-400">
                            {isAgent ? 'Agent' : (call.farmer_name || 'Farmer')}
                          </span>
                          {transcriptMode !== 'original' && hasIndicScript(text) && (
                            <span className="text-[9px] font-medium px-1.5 py-0.2 rounded bg-white text-slate-500 border border-slate-200 shadow-2xs">
                              {transcriptMode === 'romanized' ? 'English script' : 'English translation'}
                            </span>
                          )}
                        </div>
                        <p
                          lang={transcriptMode === 'original' ? (LANG_CODES[call.language || call.primary_language] || undefined) : undefined}
                          className="whitespace-pre-line text-[14px] leading-7 break-words"
                          style={{ fontFamily: transcriptMode === 'original' ? INDIC_FONTS : undefined }}
                        >
                          {renderedText}
                        </p>
                        {english.show && english.turns && (english.turns[idx]?.english || '') !== '' && (
                          <p className="mt-1.5 pt-1.5 border-t border-slate-200/70 text-[12px] leading-relaxed text-slate-500 italic whitespace-pre-line break-words">
                            {english.turns[idx].english}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : rawTranscript ? (
              <div 
                className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-800 leading-7 whitespace-pre-line" 
                style={{ fontFamily: transcriptMode === 'original' ? INDIC_FONTS : undefined }}
              >
                {formatTranscriptText(rawTranscript, transcriptMode)}
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

export default CallDetailDrawer;
