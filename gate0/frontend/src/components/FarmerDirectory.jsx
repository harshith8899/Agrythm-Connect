import React, { useState, useRef, useEffect } from 'react';
import { Search, MapPin, Phone, PhoneCall, Upload, Users, Plus, Pencil, X, Phone as PhoneIcon, Loader2, ChevronDown, Check } from 'lucide-react';
import { isCallToday, didFarmerPickUpAndTalk, getCallTimestamp, maskPhoneNumber, normalizeLanguage, importFarmersCsv, addFarmer, updateFarmer, callFarmer, confirmDialog, INDIAN_STATES, getDistrictsForState, ALL_INDIAN_DISTRICTS, getStateForDistrict } from '../utils';

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
  // retryWhy: why "follow the retry rules" is not possible right now (a test call always is)
  if (!todayCall) return { label: 'Call', hint: 'No call yet today', first: true };
  const used = Number(todayCall.attempts_used || 0);
  const max = Number(todayCall.max_attempts || 3);
  if (RETRYABLE.includes(todayCall.status)) {
    return used < max
      ? { label: 'Call', hint: `Next attempt: ${used + 1} of ${max}`, next: used + 1, max }
      : { label: 'Call', hint: `All ${max} attempts used`, retryWhy: `All ${max} attempts are used today.` };
  }
  const reasons = { Completed: 'Already completed today.', Declined: 'The farmer said they do not need it today.', 'Callback Scheduled': 'A callback is booked.', Skipped: 'Skipped today.' };
  const why = reasons[todayCall.status] || 'Not available now.';
  return { label: 'Call', hint: why.replace(/\.$/, ''), retryWhy: why };
};

const LANGUAGES = ['Hindi', 'Kannada', 'Telugu', 'English'];
const BLANK = { farmer_name: '', phone_number: '', preferred_language: 'Kannada', village: '', district: '', state: 'Karnataka', pincode: '', call_consent: false, active: true };

const Field = ({ label, children }) => (
  <label className="block text-[11px] font-semibold text-slate-600">
    <span className="block mb-1">{label}</span>
    {children}
  </label>
);
const inputCls = 'w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:bg-white focus:border-trust-navy';

// A searchable dropdown combobox that filters options as the user types,
// supports keyboard navigation (Arrow Up/Down, Enter, Escape, Tab),
// and allows selecting from the list or entering custom values (when allowCustom=true).
const SearchableCombobox = ({
  value = '',
  onChange,
  options = [],
  placeholder = 'Select or type...',
  disabled = false,
  allowCustom = true,
  required = false,
  onSelect,
  describe,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState(value || '');
  const [prevValue, setPrevValue] = useState(value);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  if (value !== prevValue) {
    setPrevValue(value);
    setSearch(value || '');
  }

  const commitValue = () => {
    const trimmed = (search || '').trim();
    if (!trimmed) {
      if (value !== '') onChange('');
      setSearch('');
      return;
    }
    const match = options.find((o) => o.toLowerCase() === trimmed.toLowerCase());
    if (match) {
      if (value !== match) onChange(match);
      setSearch(match);
    } else {
      if (value !== trimmed) onChange(trimmed);
      setSearch(trimmed);
    }
  };

  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
        setHighlightIndex(-1);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('touchstart', handleOutsideClick);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('touchstart', handleOutsideClick);
    };
  }, []);

  const handleBlur = (e) => {
    if (containerRef.current && containerRef.current.contains(e.relatedTarget)) {
      return;
    }
    setIsOpen(false);
    setHighlightIndex(-1);
    commitValue();
  };

  const filtered = options.filter((opt) =>
    opt.toLowerCase().includes((search || '').toLowerCase().trim())
  );

  const displayList = filtered.slice(0, 60);

  const handleSelect = (option) => {
    setSearch(option);
    onChange(option);
    if (onSelect) onSelect(option);
    setIsOpen(false);
    setHighlightIndex(-1);
  };

  const handleInputChange = (e) => {
    const val = e.target.value;
    setSearch(val);
    setIsOpen(true);
    setHighlightIndex(0);
    onChange(val);
  };

  const handleKeyDown = (e) => {
    if (disabled) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setHighlightIndex(0);
      } else {
        setHighlightIndex((prev) => (prev < displayList.length - 1 ? prev + 1 : prev));
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((prev) => (prev > 0 ? prev - 1 : 0));
    } else if (e.key === 'Enter') {
      if (isOpen && highlightIndex >= 0 && displayList[highlightIndex]) {
        e.preventDefault();
        handleSelect(displayList[highlightIndex]);
      } else if (isOpen) {
        setIsOpen(false);
        commitValue();
      }
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      setIsOpen(false);
      setHighlightIndex(-1);
      if (e.key === 'Escape') {
        e.preventDefault();
      }
    }
  };

  return (
    <div ref={containerRef} className="relative w-full" onBlur={handleBlur}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={search}
          disabled={disabled}
          required={required}
          onChange={handleInputChange}
          onFocus={() => {
            if (!disabled) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Disabled' : placeholder}
          className={`${inputCls} pr-8 ${disabled ? 'bg-slate-100 text-slate-400 cursor-not-allowed' : ''}`}
          autoComplete="off"
        />
        <button
          type="button"
          tabIndex={-1}
          disabled={disabled}
          onClick={() => {
            if (!disabled) {
              setIsOpen((prev) => !prev);
              if (!isOpen && inputRef.current) inputRef.current.focus();
            }
          }}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer disabled:cursor-not-allowed disabled:text-slate-300 p-0.5"
          aria-label="Toggle options"
        >
          <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-150 ${isOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {isOpen && !disabled && (
        <ul className="absolute z-50 left-0 right-0 mt-1 max-h-48 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lg py-1 text-xs">
          {displayList.length > 0 ? (
            <>
              {displayList.map((opt, idx) => {
                const isSelected = opt.toLowerCase() === (value || '').toLowerCase();
                const isHighlighted = idx === highlightIndex;
                return (
                  <li
                    key={opt}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      handleSelect(opt);
                    }}
                    onMouseEnter={() => setHighlightIndex(idx)}
                    className={`px-3 py-1.5 flex items-center justify-between cursor-pointer transition-colors ${
                      isHighlighted ? 'bg-slate-100 text-slate-900' : 'text-slate-700'
                    } ${isSelected ? 'font-bold text-trust-navy bg-trust-navy/5' : ''}`}
                  >
                    <span className="truncate">{opt}</span>
                    {describe && describe(opt) && <span className="ml-2 shrink-0 text-[10px] text-slate-400">{describe(opt)}</span>}
                    {isSelected && <Check className="w-3.5 h-3.5 text-trust-green shrink-0 ml-2" />}
                  </li>
                );
              })}
              {filtered.length > displayList.length && (
                <li className="px-3 py-1 text-[10px] text-slate-400 bg-slate-50 text-center italic border-t border-slate-100">
                  Showing first {displayList.length} of {filtered.length} options. Type to narrow.
                </li>
              )}
            </>
          ) : (
            <li className="px-3 py-2 text-slate-400 italic text-[11px]">
              {allowCustom ? 'Press enter or tab to keep typed value' : 'No matching options found'}
            </li>
          )}
        </ul>
      )}
    </div>
  );
};

// Calling language that usually goes with a state (a suggestion only: it follows the state until someone picks a language).
const LANGUAGE_FOR_STATE = { Karnataka: 'Kannada', Telangana: 'Telugu', 'Andhra Pradesh': 'Telugu' };
const DEFAULT_STATE = 'Karnataka';
const sameText = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();

// Add a farmer by hand (farmer is null) or edit one. A blank phone keeps the saved number.
// Convenience: Karnataka is the default state (any other can be picked), the PIN code fills state, district and village,
// typing the first letters of a village lists matching places from the India Post directory (picking one fills the rest),
// and "Save and add another" keeps the state and district for the next farmer of the same area.
const FarmerFormModal = ({ farmer, farmers = [], onClose, onSaved }) => {
  const editing = Boolean(farmer);
  const [form, setForm] = useState(editing ? {
    farmer_name: farmer.farmer_name || '',
    phone_number: '',
    preferred_language: normalizeLanguage(farmer.preferred_language) || 'Hindi',
    village: farmer.village || '',
    district: farmer.district || '',
    state: farmer.state || DEFAULT_STATE,
    pincode: farmer.pincode || '',
    call_consent: farmer.call_consent === 'Yes',
    active: farmer.active !== 'No',
  } : BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [savedNote, setSavedNote] = useState('');
  const [pinLoading, setPinLoading] = useState(false);
  const [pinError, setPinError] = useState('');
  const [pinVillages, setPinVillages] = useState([]);
  const [places, setPlaces] = useState([]);              // matches for the village being typed, from the India Post directory
  const [placeBusy, setPlaceBusy] = useState(false);
  const languageChosen = useRef(editing);                // once a language is picked by hand it no longer follows the state
  const placeCache = useRef(new Map());
  const placeTimer = useRef(null);
  const placeRequest = useRef(0);
  const formRef = useRef(null);
  const nameRef = useRef(null);

  useEffect(() => () => clearTimeout(placeTimer.current), []);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  // Everything that changes the state goes through here, so the language suggestion and the district check stay in one place.
  const withState = (f, state) => {
    const keep = getDistrictsForState(state).some((d) => sameText(d, f.district));
    const language = !languageChosen.current && LANGUAGE_FOR_STATE[state] ? LANGUAGE_FOR_STATE[state]
      : (!languageChosen.current ? 'Hindi' : f.preferred_language);
    return { ...f, state, district: keep ? f.district : '', preferred_language: language };
  };

  const handleStateChange = (val) => setForm((f) => withState(f, val));

  const handleDistrictChange = (val) => {
    const detectedState = getStateForDistrict(val);
    setForm((f) => (detectedState && !sameText(detectedState, f.state) && !f.state
      ? { ...withState(f, detectedState), district: val } : { ...f, district: val }));
  };

  // India Post directory by place name (needs 3 letters; waits for a pause in typing; one answer is kept per search).
  const searchPlaces = (text) => {
    clearTimeout(placeTimer.current);
    const term = String(text || '').trim();
    if (term.length < 3) {
      placeRequest.current += 1;
      setPlaces([]);
      setPlaceBusy(false);
      return;
    }
    placeTimer.current = setTimeout(async () => {
      const id = ++placeRequest.current;
      const key = term.toLowerCase();
      try {
        let list = placeCache.current.get(key);
        if (!list) {
          setPlaceBusy(true);
          const res = await fetch(`https://api.postalpincode.in/postoffice/${encodeURIComponent(term)}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          list = data?.[0]?.Status === 'Success'
            ? (data[0].PostOffice || []).map((p) => ({ name: p.Name, district: p.District, state: p.State, pincode: p.Pincode }))
            : [];
          placeCache.current.set(key, list);
        }
        if (id === placeRequest.current) setPlaces(list);
      } catch {
        if (id === placeRequest.current) setPlaces([]);          // the directory is down: typing and saving still work
      } finally {
        if (id === placeRequest.current) setPlaceBusy(false);
      }
    }, 350);
  };

  // Places that fit what is already chosen (state, and district when there is one), best match first, one per name.
  const typed = form.village.trim().toLowerCase();
  const placeByName = new Map();
  places
    .filter((p) => (!form.state || sameText(p.state, form.state)) && (!form.district || sameText(p.district, form.district)))
    .sort((a, b) => Number(b.name.toLowerCase().startsWith(typed)) - Number(a.name.toLowerCase().startsWith(typed)) || a.name.localeCompare(b.name))
    .forEach((p) => { if (!placeByName.has(p.name.toLowerCase())) placeByName.set(p.name.toLowerCase(), p); });

  const handleVillageChange = (val) => {
    setForm((f) => ({ ...f, village: val }));
    searchPlaces(val);
  };

  // A village picked from the list fills what is still empty (district, state, PIN code) from the same row.
  const handleVillagePicked = (name) => {
    const fromFarmer = farmers.find((f) => sameText(f.village, name) && (!form.state || sameText(f.state, form.state)));
    const hit = placeByName.get(String(name).toLowerCase())
      || (fromFarmer && { district: fromFarmer.district, state: fromFarmer.state, pincode: fromFarmer.pincode });
    if (!hit) return;
    setForm((f) => {
      const next = hit.state && !f.state ? withState(f, hit.state) : { ...f };
      return { ...next, village: name, district: next.district || hit.district || '', pincode: next.pincode || hit.pincode || '' };
    });
  };

  // Autopopulate location from PIN code via India Post API
  const handlePincodeChange = async (e) => {
    const raw = e.target.value.replace(/\D/g, '').slice(0, 6);
    setForm((f) => ({ ...f, pincode: raw }));
    setPinError('');

    if (raw.length === 6) {
      setPinLoading(true);
      try {
        const res = await fetch(`https://api.postalpincode.in/pincode/${raw}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (Array.isArray(data) && data[0]?.Status === 'Success' && data[0]?.PostOffice?.length > 0) {
          const poList = data[0].PostOffice;
          const po = poList[0];
          const poNames = Array.from(new Set(poList.map((p) => p.Name).filter(Boolean)));
          setPinVillages(poNames);

          const matchedState = INDIAN_STATES.find((s) => sameText(s, po.State)) || po.State;
          const matchedDistrict = getDistrictsForState(matchedState).find((d) => sameText(d, po.District)) || po.District;

          setForm((prev) => ({
            ...withState(prev, matchedState || prev.state),
            district: matchedDistrict || prev.district,
            village: prev.village || (poNames.length === 1 ? poNames[0] : prev.village),
          }));
        } else {
          setPinError(data[0]?.Message || 'Invalid PIN code or no location found.');
        }
      } catch {
        setPinError('PIN code lookup service unreachable. Choose the state and district below.');
      } finally {
        setPinLoading(false);
      }
    }
  };

  // Karnataka first, then the other states; a state read from a PIN code that is not in the list is added too.
  const stateChoices = [DEFAULT_STATE, ...INDIAN_STATES.filter((s) => s !== DEFAULT_STATE)];
  if (form.state && !stateChoices.some((s) => sameText(s, form.state))) stateChoices.push(form.state);

  const districtOptions = form.state ? getDistrictsForState(form.state) : ALL_INDIAN_DISTRICTS;

  // Village choices: matches from the directory, the villages of the PIN code, and villages of existing farmers in the area
  const villageOptions = Array.from(new Set([
    ...Array.from(placeByName.values()).map((p) => p.name),
    ...pinVillages,
    ...farmers
      .filter((f) => f.village
        && (!form.state || sameText(f.state, form.state))
        && (!form.district || sameText(f.district, form.district)))
      .map((f) => String(f.village).trim()),
  ].filter(Boolean)));
  const describeVillage = (name) => {
    const p = placeByName.get(String(name).toLowerCase());
    return p ? [p.district, p.pincode].filter(Boolean).join(' · ') : '';
  };

  const save = async (again) => {
    if (formRef.current && !formRef.current.reportValidity()) return;
    setBusy(true);
    setError('');
    setSavedNote('');
    try {
      if (editing) await updateFarmer(farmer.farmer_id, form);
      else await addFarmer(form);
      onSaved();
      if (again && !editing) {
        setSavedNote(`Saved ${form.farmer_name}. Add the next farmer.`);
        setForm({ ...BLANK, state: form.state, district: form.district, preferred_language: form.preferred_language });
        setPinVillages([]);
        setPlaces([]);
        setBusy(false);
        if (nameRef.current) nameRef.current.focus();
      } else {
        onClose();
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    save(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40" role="dialog" aria-modal="true">
      <form ref={formRef} onSubmit={submit} className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-xl p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">{editing ? `Edit ${farmer.farmer_name}` : 'Add farmer'}</h3>
          <button type="button" onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 cursor-pointer" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        {savedNote && <p className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2">{savedNote}</p>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pb-4">
          <Field label="Farmer name">
            <input
              ref={nameRef}
              className={inputCls}
              value={form.farmer_name}
              onChange={set('farmer_name')}
              placeholder="e.g. Ramesh Kumar"
              autoFocus
              required
            />
          </Field>

          <Field label={editing ? `Mobile number (saved: ${farmer.phone_number}; blank keeps it)` : 'Mobile number'}>
            <input
              className={inputCls}
              value={form.phone_number}
              onChange={(e) => setForm((f) => ({ ...f, phone_number: e.target.value.replace(/[^\d+\s-]/g, '').slice(0, 16) }))}
              inputMode="tel"
              placeholder="10 digits (e.g. 9845012345)"
              required={!editing}
            />
          </Field>

          {/* The PIN code comes first: six digits fill the state, district and village below */}
          <div className="sm:col-span-2">
            <Field label="PIN code (fills state, district and village)">
              <div className="relative">
                <input
                  className={inputCls}
                  value={form.pincode}
                  onChange={handlePincodeChange}
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="e.g. 571401"
                />
                {pinLoading && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-trust-green" />
                  </div>
                )}
              </div>
            </Field>
            {pinError && <p className="text-[10px] font-semibold text-rose-600 mt-1">{pinError}</p>}
          </div>

          <Field label="State">
            <select className={inputCls} value={form.state} onChange={(e) => handleStateChange(e.target.value)} required>
              {stateChoices.map((s) => (
                <option key={s} value={s}>{s === DEFAULT_STATE ? `${s} (default)` : s}</option>
              ))}
            </select>
          </Field>

          <Field label="District">
            <SearchableCombobox
              value={form.district}
              onChange={handleDistrictChange}
              options={districtOptions}
              placeholder={`Type the first letters (${form.state || 'any state'})...`}
              required
            />
          </Field>

          <div className="sm:col-span-2">
            <Field label={placeBusy ? 'Village (searching places...)' : 'Village (type 3 letters to see places)'}>
              <SearchableCombobox
                value={form.village}
                onChange={handleVillageChange}
                onSelect={handleVillagePicked}
                describe={describeVillage}
                options={villageOptions}
                allowCustom={true}
                placeholder={form.district ? `Type the first letters of the village in ${form.district}...` : 'Type the first letters of the village...'}
              />
            </Field>
          </div>

          <div className="sm:col-span-2">
            <Field label="Calling language">
              <select
                className={inputCls}
                value={form.preferred_language}
                onChange={(e) => { languageChosen.current = true; setForm((f) => ({ ...f, preferred_language: e.target.value })); }}
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </Field>
          </div>
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
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200 cursor-pointer">Cancel</button>
          {!editing && (
            <button type="button" disabled={busy} onClick={() => save(true)} className="px-4 py-2 rounded-xl bg-white border border-slate-200 text-trust-navy text-xs font-semibold hover:bg-slate-50 disabled:opacity-50 cursor-pointer">
              Save and add another
            </button>
          )}
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
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [batchCalling, setBatchCalling] = useState(false);
  const [districtFilter, setDistrictFilter] = useState('all');
  const [stateFilter, setStateFilter] = useState('all');
  const [languageFilter, setLanguageFilter] = useState('all');

  const placeCall = async (farmer, action) => {
    const max = action.max || 3;
    const mode = await confirmDialog({
      title: `Call ${farmer.farmer_name} now?`,
      message: isLive ? 'This places a real call and uses Sarvam credits.' : 'Calls are simulated, so no real call is made.',
      confirmLabel: 'Call now',
      tone: isLive ? 'danger' : 'default',
      choices: [
        {
          value: 'retry',
          label: action.first ? 'Follow the retry rules: the first call of the day' : `Follow the retry rules: attempt ${action.next || '?'} of ${max}`,
          description: action.first
            ? 'Counts as today\'s first attempt. If it is not picked up, the usual retries follow (30 minutes, then 1 hour).'
            : 'Counts as the next attempt and replaces the waiting retry. Later retries follow the usual gaps.',
          disabledReason: action.retryWhy,
        },
        {
          value: 'test',
          label: 'Test call: ignore the retry rules',
          description: 'A one-off call that does not count as an attempt and does not change today\'s result, retries or callbacks. It shows as a Test row in Call Logs and can be repeated.',
        },
      ],
    });
    if (!mode) return;
    setCalling((c) => ({ ...c, [farmer.farmer_id]: true }));
    setCallNote((n) => ({ ...n, [farmer.farmer_id]: null }));
    try {
      await callFarmer(farmer.farmer_id, mode);
      setCallNote((n) => ({ ...n, [farmer.farmer_id]: { ok: true, text: mode === 'test' ? 'Test call started. It appears as a Test row in Call Logs.' : 'Call started. The result appears in Call Logs.' } }));
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
    const farmerCalls = callLogs.filter(c => !c.is_test && String(c.farmer_id).trim() === String(f.farmer_id).trim());
    const talkedToday = farmerCalls.some(c => isCallToday(getCallTimestamp(c)) && didFarmerPickUpAndTalk(c));
    const todayCall = farmerCalls.find(c => c.call_date === todayStr());
    return {
      ...f,
      action: callAction(f, todayCall),
      totalCalls: farmerCalls.length,
      talkedToday,
    };
  });

  const availableDistricts = Array.from(new Set(farmers.map((f) => f.district).filter(Boolean))).sort();
  const availableStates = Array.from(new Set(farmers.map((f) => f.state).filter(Boolean))).sort();
  const availableLanguages = Array.from(new Set(farmers.map((f) => normalizeLanguage(f.preferred_language || f.primary_language)).filter(Boolean))).sort();

  // Search every word typed against everything shown on the card (name, id, village, district, state, language, phone as
  // shown, status words), ignoring case, accents and punctuation. "mandya kannada" finds Kannada farmers in Mandya.
  const plain = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9\u0900-\u0dff]+/g, ' ');
  const searchText = (f) => {
    const phone = f.phone_number || f.phone || '';
    return plain([
      f.farmer_name, f.farmer_id, f.village, f.district, f.state, f.primary_language, f.preferred_language,
      normalizeLanguage(f.primary_language || f.preferred_language), phone, maskPhoneNumber(phone),
      f.active === 'No' ? 'inactive' : 'active', f.call_consent === 'No' ? 'no consent' : 'consent',
      f.talkedToday ? 'talked today' : '',
    ].join(' '));
  };
  const words = plain(search).split(' ').filter(Boolean);
  const filtered = farmerStats.filter((f) => {
    if (districtFilter !== 'all' && f.district !== districtFilter) return false;
    if (stateFilter !== 'all' && f.state !== stateFilter) return false;
    if (languageFilter !== 'all' && normalizeLanguage(f.primary_language || f.preferred_language) !== languageFilter) return false;
    if (words.length > 0) {
      const hay = searchText(f);
      const digits = hay.replace(/ /g, '');
      if (!words.every((w) => hay.includes(w) || (/^\d+$/.test(w) && digits.includes(w)))) return false;
    }
    return true;
  });

  const visibleFarmerIds = filtered.map((f) => f.farmer_id);
  const isAllVisibleSelected = visibleFarmerIds.length > 0 && visibleFarmerIds.every((id) => selectedIds.has(id));
  const isSomeVisibleSelected = visibleFarmerIds.some((id) => selectedIds.has(id));

  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (isAllVisibleSelected) {
        visibleFarmerIds.forEach((id) => next.delete(id));
      } else {
        visibleFarmerIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectFarmer = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectedFarmers = farmerStats.filter((f) => selectedIds.has(f.farmer_id));
  const selectedConsentedFarmers = selectedFarmers.filter((f) => f.call_consent !== 'No' && f.active !== 'No');

  const handleBatchCallSelected = async () => {
    if (selectedConsentedFarmers.length === 0) {
      setToggleError('None of the selected farmers have active call consent and active status.');
      return;
    }

    const mode = await confirmDialog({
      title: `Call ${selectedConsentedFarmers.length} consented farmer${selectedConsentedFarmers.length > 1 ? 's' : ''} now?`,
      message: isLive
        ? `This places real calls to ${selectedConsentedFarmers.length} farmer(s) and uses Sarvam credits.`
        : `Placing ${selectedConsentedFarmers.length} simulated call(s) (no actual phone calls made).`,
      confirmLabel: `Call ${selectedConsentedFarmers.length} farmer${selectedConsentedFarmers.length > 1 ? 's' : ''}`,
      tone: isLive ? 'danger' : 'default',
      choices: [
        {
          value: 'retry',
          label: 'Follow the retry rules (recommended)',
          description: "Counts as today's first attempt or next retry for each farmer.",
        },
        {
          value: 'test',
          label: 'Test calls (ignore retry rules)',
          description: "One-off test calls that do not count against the farmer's daily retry schedule.",
        },
      ],
    });

    if (!mode) return;

    setBatchCalling(true);
    setToggleError('');

    let successCount = 0;
    let failCount = 0;

    for (const farmer of selectedConsentedFarmers) {
      setCalling((c) => ({ ...c, [farmer.farmer_id]: true }));
      try {
        await callFarmer(farmer.farmer_id, mode);
        successCount++;
        setCallNote((n) => ({
          ...n,
          [farmer.farmer_id]: {
            ok: true,
            text: mode === 'test' ? 'Test call started.' : 'Call started.',
          },
        }));
      } catch (err) {
        failCount++;
        setCallNote((n) => ({
          ...n,
          [farmer.farmer_id]: {
            ok: false,
            text: err.message || 'Call failed',
          },
        }));
      } finally {
        setCalling((c) => ({ ...c, [farmer.farmer_id]: false }));
      }
    }

    setBatchCalling(false);
    setSelectedIds(new Set());
    if (failCount > 0) {
      setToggleError(`Started ${successCount} calls; ${failCount} failed.`);
    }
    [3000, 10000, 25000].forEach((ms) => setTimeout(() => onImported && onImported(), ms));
  };

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
        {editing && <FarmerFormModal farmer={editing === 'new' ? null : editing} farmers={farmers} onClose={() => setEditing(null)} onSaved={() => onImported && onImported()} />}
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
        <div className="relative w-full sm:min-w-[280px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, ID, phone, village, district, state, language..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy transition-all"
          />
        </div>
        </div>
      </div>

      {toggleError && <p className="text-xs font-semibold text-rose-700">{toggleError}</p>}
      {editing && <FarmerFormModal farmer={editing === 'new' ? null : editing} farmers={farmers} onClose={() => setEditing(null)} onSaved={() => onImported && onImported()} />}

      {/* Regional Filters & Select All Toolbar */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 cursor-pointer font-bold text-xs text-slate-800 select-none">
            <input
              type="checkbox"
              checked={isAllVisibleSelected}
              ref={(el) => {
                if (el) el.indeterminate = isSomeVisibleSelected && !isAllVisibleSelected;
              }}
              onChange={toggleSelectAllVisible}
              className="w-4 h-4 rounded-md border-slate-300 text-trust-navy focus:ring-trust-navy/20 cursor-pointer"
              aria-label="Select all visible farmers"
            />
            <span>
              Select All ({filtered.length} visible{filtered.length !== farmers.length ? ` of ${farmers.length}` : ''})
            </span>
          </label>
          {selectedIds.size > 0 && (
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="text-[11px] font-semibold text-slate-400 hover:text-slate-600 underline cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {availableStates.length > 0 && (
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="text-xs py-1.5 px-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-medium focus:outline-hidden focus:border-trust-navy cursor-pointer"
            >
              <option value="all">All States ({availableStates.length})</option>
              {availableStates.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          )}

          {availableDistricts.length > 0 && (
            <select
              value={districtFilter}
              onChange={(e) => setDistrictFilter(e.target.value)}
              className="text-xs py-1.5 px-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-medium focus:outline-hidden focus:border-trust-navy cursor-pointer"
            >
              <option value="all">All Districts ({availableDistricts.length})</option>
              {availableDistricts.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          )}

          {availableLanguages.length > 0 && (
            <select
              value={languageFilter}
              onChange={(e) => setLanguageFilter(e.target.value)}
              className="text-xs py-1.5 px-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 font-medium focus:outline-hidden focus:border-trust-navy cursor-pointer"
            >
              <option value="all">All Languages</option>
              {availableLanguages.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          )}

          {(stateFilter !== 'all' || districtFilter !== 'all' || languageFilter !== 'all') && (
            <button
              type="button"
              onClick={() => {
                setStateFilter('all');
                setDistrictFilter('all');
                setLanguageFilter('all');
              }}
              className="text-[11px] font-semibold text-slate-500 hover:text-rose-600 px-2 py-1 rounded-lg hover:bg-slate-100 cursor-pointer"
            >
              Reset Filters
            </button>
          )}
        </div>
      </div>

      {/* Batch Action Bar */}
      {selectedIds.size > 0 && (
        <div className="sticky top-16 z-20 bg-trust-navy text-white rounded-2xl shadow-lg border border-slate-800 p-4 flex flex-col sm:flex-row items-center justify-between gap-3 animate-in fade-in duration-150">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center px-2.5 py-1 rounded-full bg-emerald-500 text-white font-extrabold text-xs">
              {selectedIds.size}
            </span>
            <div className="text-xs">
              <span className="font-bold text-sm text-white">
                {selectedIds.size} farmer{selectedIds.size === 1 ? '' : 's'} selected
              </span>
              <span className="text-slate-300 ml-2">
                ({selectedConsentedFarmers.length} eligible for voice calls)
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-semibold transition-colors cursor-pointer"
            >
              Deselect All
            </button>
            <button
              type="button"
              onClick={handleBatchCallSelected}
              disabled={batchCalling || selectedConsentedFarmers.length === 0}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-green hover:bg-emerald-600 text-white text-xs font-bold transition-all shadow-xs disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {batchCalling ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Placing calls...</span>
                </>
              ) : (
                <>
                  <PhoneCall className="w-3.5 h-3.5" />
                  <span>Call Selected ({selectedConsentedFarmers.length})</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Farmers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((farmer, index) => {
          const isSelected = selectedIds.has(farmer.farmer_id);
          return (
          <div
            key={farmer.farmer_id || index}
            className={`bg-white rounded-2xl border p-5 transition-all space-y-4 shadow-2xs ${
              isSelected ? 'border-trust-navy ring-2 ring-trust-navy/20 bg-slate-50/50' : 'border-slate-200/80 hover:border-slate-300'
            } ${farmer.active === 'No' ? 'opacity-70' : ''}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelectFarmer(farmer.farmer_id)}
                  className="w-4 h-4 rounded-md border-slate-300 text-trust-navy focus:ring-trust-navy/20 cursor-pointer"
                  aria-label={`Select ${farmer.farmer_name}`}
                />
                <div className="w-10 h-10 rounded-xl bg-trust-navy text-white flex items-center justify-center font-bold text-base shadow-xs shrink-0">
                  {String(farmer.farmer_name || 'F').charAt(0)}
                </div>
                <div className="min-w-0">
                  <h3 className="font-bold text-sm text-slate-900 truncate">
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
                title={farmer.action.why || 'Place a call now'}
                className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors cursor-pointer disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
              >
                <PhoneIcon className="w-3.5 h-3.5" />
                <span>{calling[farmer.farmer_id] ? 'Calling...' : farmer.action.label}</span>
              </button>
              {(farmer.action.why || farmer.action.hint) && <p className="text-[11px] text-slate-500 text-center">{farmer.action.why || farmer.action.hint}</p>}
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
        );
      })}
      </div>
    </div>
  );
};
