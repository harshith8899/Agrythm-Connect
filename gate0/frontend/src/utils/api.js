import { API_BASE, API_CONFIG } from './constants';

const getJson = async (url) => {
  const response = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' }, cache: 'no-store' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
};

const postJson = async (path, options = {}) => {
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', ...options });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new Error((body && body.error) || `HTTP ${response.status}`);
  return body;
};

/** Farmers saved in the backend database (phone numbers arrive already masked). */
export const loadFarmersData = async () => {
  try {
    const data = await getJson(API_CONFIG.farmersApiUrl);
    return { data: Array.isArray(data) ? data : [], source: 'sqlite_live' };
  } catch (err) {
    return { data: [], source: 'offline', error: err.message };
  }
};

/** One record per farmer per day: weather sent, status, attempts, transcript, summary, callback. */
export const loadCallLogsData = async () => {
  try {
    const data = await getJson(API_CONFIG.callLogsApiUrl);
    return { data: Array.isArray(data) ? data : [], source: 'sqlite_live' };
  } catch (err) {
    return { data: [], source: 'offline', error: err.message };
  }
};

/** Starts today's calls for every eligible farmer. Returns at once; results appear as calls finish. */
export const sendCallsNow = () =>
  postJson('/api/calls/send-now', { headers: { 'Content-Type': 'application/json' }, body: '{}' });

export const getDispatcherStatus = async () => {
  try {
    return await getJson(`${API_BASE}/api/orchestrator/status`);
  } catch {
    return { enabled: false, scheduledTime: '09:00 AM IST', systemStatus: 'Offline' };
  }
};

export const updateDispatcherStatus = (enabled) =>
  postJson('/api/orchestrator/auto-dispatch', {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });

const sendJson = async (method, path, payload) => {
  const response = await fetch(`${API_BASE}${path}`, {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new Error((body && body.error) || `HTTP ${response.status}`);
  return body;
};

/** Adds one farmer typed in by an admin. Consent is only Yes if call_consent is true. */
export const addFarmer = (fields) => sendJson('POST', '/api/farmers', fields);

/** Changes the fields sent for one farmer (name, phone, language, place, call_consent, active). */
export const updateFarmer = (farmerId, fields) => sendJson('PUT', `/api/farmers/${encodeURIComponent(farmerId)}`, fields);

/** Places a call now for one farmer: the day's first call, or the next retry. Returns at once; the result appears when the call ends. */
export const callFarmer = (farmerId) =>
  postJson(`/api/farmers/${encodeURIComponent(farmerId)}/call`, { headers: { 'Content-Type': 'application/json' }, body: '{}' });

/** Uploads a farmers CSV (Farmer ID, Farmer Name, Mobile Number, Village, District, State, Language, Consent). */
export const importFarmersCsv = async (file) =>
  postJson('/api/farmers/import', { headers: { 'Content-Type': 'text/csv' }, body: await file.text() });

/** Backend, database, weather API, Sarvam and the phone line: each ok, fail or off (not set up). */
export const getSystemChecks = (refresh = false) => getJson(`${API_BASE}/api/system/checks${refresh ? '?refresh=1' : ''}`);

/** Calls and billed minutes counted from Sarvam's own call records (Sarvam has no balance API). */
export const getUsage = (refresh = false) => getJson(`${API_BASE}/api/usage${refresh ? '?refresh=1' : ''}`);

/** Saves the per-minute rate of the Sarvam plan (rupees a minute); amounts are billed minutes times this rate. */
export const saveUsageRate = (sarvamRate) =>
  postJson('/api/usage', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sarvam_rate: sarvamRate }) });

/** Things the team must act on: farmers who asked to stop, failed calls, skipped runs. */
export const getAlerts = () => getJson(`${API_BASE}/api/alerts`);

export const getCallbacks = () => getJson(`${API_BASE}/api/callbacks`);

export const getWeatherParameters = (lat, lon) => getJson(`${API_BASE}/api/weather?lat=${lat}&lon=${lon}`);
