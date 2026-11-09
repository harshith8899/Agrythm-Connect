import React, { useState } from 'react';
import { Search, MapPin, Phone, PhoneCall, Upload, Users, Plus, Pencil, X, Phone as PhoneIcon } from 'lucide-react';
import { isCallToday, didFarmerPickUpAndTalk, getCallTimestamp, maskPhoneNumber, normalizeLanguage, importFarmersCsv, addFarmer, updateFarmer, callFarmer } from '../utils';

// Upload a farmers CSV; the backend saves it (same Farmer ID updates the farmer) and the list reloads.
const ImportCsvButton = ({ onImported }) => {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  const handlePick = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    setBusy(true);
    setMessage(null);
    try {
      const res = await importFarmersCsv(file);
      const noLocation = res.no_location && res.no_location.length > 0
        ? ` No location found for: ${res.no_location.join(', ')} (they will be skipped).` : '';
      setMessage({ ok: true, text: `Saved ${res.imported} farmers.${noLocation}` });
      if (onImported) onImported();
    } catch (err) {
      setMessage({ ok: false, text: err.message });
    } finally {
      setBusy(false);
      e.target.value = '';
    }
  };

  return (
    <div className="flex flex-col items-start gap-1.5">
      <label className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer ${busy ? 'opacity-60 pointer-events-none' : ''}`}>
        <Upload className="w-3.5 h-3.5" />
        <span>{busy ? 'Importing...' : 'Import farmers (CSV)'}</span>
        <input type="file" accept=".csv,text/csv" className="hidden" onChange={handlePick} />
      </label>
      {message && (
        <span className={`text-[11px] font-semibold ${message.ok ? 'text-emerald-700' : 'text-rose-700'}`}>{message.text}</span>
      )}
    </div>
  );
};

const todayStr = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// What the Call button does for a farmer, from today's call record: the day's first call, the next retry, or nothing (with the reason).
const RETRYABLE = ['Retrying', 'Unanswered', 'Not Confirmed', 'Failed'];
const callAction = (farmer, todayCall) => {
  if (farmer.active === 'No') return { disabled: true, label: 'Call', why: 'Inactive farmer' };
  if (farmer.call_consent === 'No') return { disabled: true, label: 'Call', why: 'No call consent' };
  if (!todayCall) return { label: 'Call now', first: true };
  const used = Number(todayCall.attempts_used || 0);
  const max = Number(todayCall.max_attempts || 3);
  if (RETRYABLE.includes(todayCall.status)) {
    return used < max
      ? { label: `Retry now (${used + 1} of ${max})` }
      : { disabled: true, label: 'Call', why: `All ${max} attempts used today` };
  }
  const reasons = { Completed: 'Already completed today', Declined: 'Said they do not need it today', 'Callback Scheduled': 'A callback is booked', Skipped: 'Skipped today' };
  return { disabled: true, label: 'Call', why: reasons[todayCall.status] || 'Not available now' };
};

const LANGUAGES = ['Hindi', 'Kannada', 'Telugu', 'English'];
const BLANK = { farmer_name: '', phone_number: '', preferred_language: 'Hindi', village: '', district: '', state: '', call_consent: false, active: true };

const Field = ({ label, children }) => (
  <label className="block text-[11px] font-semibold text-slate-600">
    <span className="block mb-1">{label}</span>
    {children}
  </label>
);
const inputCls = 'w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:bg-white focus:border-trust-navy';

// Add a farmer by hand (farmer is null) or edit one. A blank phone keeps the saved number.
const FarmerFormModal = ({ farmer, onClose, onSaved }) => {
  const editing = Boolean(farmer);
  const [form, setForm] = useState(editing ? {
    farmer_name: farmer.farmer_name || '', phone_number: '', preferred_language: normalizeLanguage(farmer.preferred_language) || 'Hindi',
    village: farmer.village || '', district: farmer.district || '', state: farmer.state || '',
    call_consent: farmer.call_consent === 'Yes', active: farmer.active !== 'No',
  } : BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (editing) await updateFarmer(farmer.farmer_id, form);
      else await addFarmer(form);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-xl p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">{editing ? `Edit ${farmer.farmer_name}` : 'Add farmer'}</h3>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 cursor-pointer" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Farmer name"><input className={inputCls} value={form.farmer_name} onChange={set('farmer_name')} required /></Field>
          <Field label={editing ? `Mobile number (saved: ${farmer.phone_number}; blank keeps it)` : 'Mobile number'}>
            <input className={inputCls} value={form.phone_number} onChange={set('phone_number')} inputMode="tel" placeholder="10 digits" required={!editing} />
          </Field>
          <Field label="Village"><input className={inputCls} value={form.village} onChange={set('village')} /></Field>
          <Field label="District"><input className={inputCls} value={form.district} onChange={set('district')} /></Field>
          <Field label="State"><input className={inputCls} value={form.state} onChange={set('state')} /></Field>
          <Field label="Calling language">
            <select className={inputCls} value={form.preferred_language} onChange={set('preferred_language')}>
              {LANGUAGES.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Field>
        </div>
        <div className="space-y-2 text-xs text-slate-700">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={form.call_consent} onChange={set('call_consent')} />
            <span>The farmer has agreed to receive these calls</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={form.active} onChange={set('active')} />
            <span>Active (called every day)</span>
          </label>
        </div>
        {error && <p className="text-xs font-semibold text-rose-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200 cursor-pointer">Cancel</button>
          <button type="submit" disabled={busy} className="px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 cursor-pointer">
            {busy ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  );
};

const AddFarmerButton = ({ onClick }) => (
  <button onClick={onClick} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white border border-slate-200 text-trust-navy text-xs font-semibold hover:bg-slate-50 transition-colors cursor-pointer">
    <Plus className="w-3.5 h-3.5" />
    <span>Add farmer</span>
  </button>
);

export const FarmerDirectory = ({ farmers = [], callLogs = [], onSelectFarmer, onImported, isLive = false }) => {
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null); // null: closed, 'new': add form, or the farmer being edited
  const [toggleError, setToggleError] = useState('');
  const [callNote, setCallNote] = useState({}); // farmer id -> { ok, text } shown on the card
  const [calling, setCalling] = useState({});

  const placeCall = async (farmer, action) => {
    const what = action.first ? 'a call' : 'the next attempt';
    const text = isLive
      ? `Place ${what} to ${farmer.farmer_name} now? This is a real call and uses Sarvam credits.`
      : `Place ${what} to ${farmer.farmer_name} now? Calls are simulated, so no real call is made.`;
    if (!window.confirm(text)) return;
    setCalling((c) => ({ ...c, [farmer.farmer_id]: true }));
    setCallNote((n) => ({ ...n, [farmer.farmer_id]: null }));
    try {
      await callFarmer(farmer.farmer_id);
      setCallNote((n) => ({ ...n, [farmer.farmer_id]: { ok: true, text: 'Call started. The result appears in Call Logs.' } }));
      [3000, 10000, 25000].forEach((ms) => setTimeout(() => onImported && onImported(), ms));
    } catch (err) {
      setCallNote((n) => ({ ...n, [farmer.farmer_id]: { ok: false, text: err.message } }));
    } finally {
      setTimeout(() => setCalling((c) => ({ ...c, [farmer.farmer_id]: false })), 4000);
    }
  };

  const toggleActive = async (farmer) => {
    setToggleError('');
    try {
      await updateFarmer(farmer.farmer_id, { active: farmer.active === 'No' });
      if (onImported) onImported();
    } catch (err) {
      setToggleError(err.message);
    }
  };

  // Calculate call counts and today's engagement status purely per actual farmer in Sheet 1
  const farmerStats = farmers.map(f => {
    const farmerCalls = callLogs.filter(c => String(c.farmer_id).trim() === String(f.farmer_id).trim());
    const talkedToday = farmerCalls.some(c => isCallToday(getCallTimestamp(c)) && didFarmerPickUpAndTalk(c));
    const todayCall = farmerCalls.find(c => c.call_date === todayStr());
    return {
      ...f,
      action: callAction(f, todayCall),
      totalCalls: farmerCalls.length,
      talkedToday,
    };
  });

  const filtered = farmerStats.filter(f => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const phone = f.phone_number || f.phone || '';
    return (
      String(f.farmer_name || '').toLowerCase().includes(q) ||
      String(phone).toLowerCase().includes(q) ||
      maskPhoneNumber(phone).toLowerCase().includes(q) ||
      String(f.district || '').toLowerCase().includes(q) ||
      String(f.village || '').toLowerCase().includes(q) ||
      String(f.farmer_id || '').toLowerCase().includes(q)
    );
  });

  if (farmers.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mx-auto">
          <Users className="w-7 h-7 text-trust-navy" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">
            No Farmer Profiles in Database Yet
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            Import a CSV with Farmer ID, Farmer Name, Mobile Number, Village, District, State, Preferred Calling Language and Call Consent. Phone numbers are stored on the server and shown masked.
          </p>
        </div>
        <div className="pt-2 flex items-center justify-center gap-3">
          <ImportCsvButton onImported={onImported} />
          <AddFarmerButton onClick={() => setEditing('new')} />
        </div>
        {editing && <FarmerFormModal farmer={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => onImported && onImported()} />}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header & Search */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Registered Directory
          </span>
          <h2 className="text-xl font-bold text-slate-900">
            Farmer Profiles ({farmers.length})
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Loaded from the backend database
          </p>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <ImportCsvButton onImported={onImported} />
          <AddFarmerButton onClick={() => setEditing('new')} />
        <div className="relative min-w-[280px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search farmers by name, village, district..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy transition-all"
          />
        </div>
        </div>
      </div>

      {toggleError && <p className="text-xs font-semibold text-rose-700">{toggleError}</p>}
      {editing && <FarmerFormModal farmer={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => onImported && onImported()} />}

      {/* Farmers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((farmer, index) => (
          <div
            key={farmer.farmer_id || index}
            className={`bg-white rounded-2xl border border-slate-200/80 p-5 hover:border-slate-300 transition-all space-y-4 shadow-2xs ${farmer.active === 'No' ? 'opacity-70' : ''}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-trust-navy text-white flex items-center justify-center font-bold text-base shadow-xs">
                  {String(farmer.farmer_name || 'F').charAt(0)}
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">
                    {farmer.farmer_name || 'Unnamed Farmer'}
                  </h3>
                  <span className="text-[10px] font-mono text-slate-400">
                    {farmer.farmer_id || 'ID N/A'}
                  </span>
                </div>
              </div>

              <div className="flex flex-col items-end gap-1">
                {farmer.active === 'No' && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                    Inactive
                  </span>
                )}
                {farmer.call_consent === 'No' && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                    No consent
                  </span>
                )}
                {farmer.talkedToday && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-trust-green border border-emerald-200">
                    Talked Today
                  </span>
                )}
                {(farmer.primary_language || farmer.preferred_language) && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      normalizeLanguage(farmer.primary_language || farmer.preferred_language) === 'English'
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}
                  >
                    {normalizeLanguage(farmer.primary_language || farmer.preferred_language)}
                  </span>
                )}
              </div>
            </div>

            <div className="space-y-1.5 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                <span className="font-mono text-slate-800">{maskPhoneNumber(farmer.phone_number || farmer.phone)}</span>
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                <span>{farmer.village || 'N/A'}, {farmer.district || 'N/A'}</span>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs">
              <label className="inline-flex items-center gap-2 cursor-pointer text-slate-600 font-semibold">
                <input type="checkbox" checked={farmer.active !== 'No'} onChange={() => toggleActive(farmer)} />
                <span>{farmer.active === 'No' ? 'Inactive' : 'Active'}</span>
              </label>
              <button
                onClick={() => setEditing(farmer)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
              >
                <Pencil className="w-3 h-3" />
                <span>Edit</span>
              </button>
            </div>

            <div className="space-y-1">
              <button
                onClick={() => placeCall(farmer, farmer.action)}
                disabled={farmer.action.disabled || calling[farmer.farmer_id]}
                title={farmer.action.why || (farmer.action.first ? 'Place a call now' : 'Place the next attempt now')}
                className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
              >
                <PhoneIcon className="w-3.5 h-3.5" />
                <span>{calling[farmer.farmer_id] ? 'Calling...' : farmer.action.label}</span>
              </button>
              {farmer.action.why && <p className="text-[11px] text-slate-500 text-center">{farmer.action.why}</p>}
              {callNote[farmer.farmer_id] && (
                <p className={`text-[11px] font-semibold text-center ${callNote[farmer.farmer_id].ok ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {callNote[farmer.farmer_id].text}
                </p>
              )}
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
              <div className="text-slate-500">
                Calls Recorded: <strong className="text-slate-800">{farmer.totalCalls}</strong>
              </div>

              <button
                onClick={() => onSelectFarmer(farmer.farmer_name)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-trust-navy hover:text-white text-trust-navy text-xs font-semibold transition-colors cursor-pointer"
              >
                <PhoneCall className="w-3 h-3" />
                <span>View Call Logs</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
