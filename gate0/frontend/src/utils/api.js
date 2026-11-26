import { API_BASE, API_CONFIG } from './constants';

const AUTH_TOKEN_KEY = 'gate0_session_token';
const AUTH_USER_KEY = 'gate0_admin_user';

export const getSessionToken = () => {
  try {
    return sessionStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
};

export const getAdminUser = () => {
  try {
    return sessionStorage.getItem(AUTH_USER_KEY) || 'Admin';
  } catch {
    return 'Admin';
  }
};

export const setSessionAuth = (token, username) => {
  try {
    if (token) sessionStorage.setItem(AUTH_TOKEN_KEY, token);
    if (username) sessionStorage.setItem(AUTH_USER_KEY, username);
    window.dispatchEvent(new Event('gate0-auth-change'));
  } catch {
    // Storage unavailable
  }
};

export const clearSessionAuth = () => {
  try {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_USER_KEY);
    window.dispatchEvent(new Event('gate0-auth-change'));
    window.dispatchEvent(new Event('gate0-unauthorized'));
  } catch {
    // Storage unavailable
  }
};

const authHeaders = (customHeaders = {}) => {
  const headers = new Headers(customHeaders);
  const token = getSessionToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
};

const checkAuthResponse = (response) => {
  if (response.status === 401) {
    clearSessionAuth();
    throw new Error('Unauthorized');
  }
};

/**
 * Asks the server whether it is awake (/api/health needs no sign-in). On the free hosting plan a sleeping server answers the first
 * request only after up to a minute, so this is also how the sign-in page wakes it early. Never throws: { ok, status, message }.
 */
export const pingServer = async (timeoutMs = 100000) => {
  // A sleeping free-plan server answers its first request after 20 to 60 seconds, so a request is never cut short before that.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}/api/health`, { cache: 'no-store', signal: controller.signal });
    let message = '';
    if (!response.ok) {
      try {
        message = String((await response.json()).error || '');
      } catch {
        message = '';
      }
    }
    return { ok: response.ok, status: response.status, message };
  } catch {
    return { ok: false, status: 0, message: '' };
  } finally {
    clearTimeout(timer);
  }
};

/**
 * Wakes the server from this browser's own connection. /api/wake?open=1 answers with a redirect to the server's own health
 * address, and the browser follows it, so the request reaches the host directly and not from the Cloudflare Worker (whose
 * requests do not always wake a sleeping server). The answer cannot be read (no-cors) and is not needed: pingServer tells us
 * when the server is up. Never throws.
 */
export const wakeDirect = () => {
  fetch(`${API_BASE}/api/wake?open=1`, { mode: 'no-cors', cache: 'no-store' }).catch(() => {});
};

/** An error that means "the server is not ready yet", not "wrong password": the caller may simply try again. */
const notReady = () => Object.assign(new Error('The server is still waking up. Trying again...'), { transient: true });

export const loginAdmin = async (username, password) => {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw notReady();                                    // no answer at all: asleep or restarting
  }
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (response.status >= 500 || response.status === 429) throw notReady();    // the host's "starting up" and proxy errors
  if (!response.ok) {
    throw new Error((body && body.error) || 'Invalid username or password');
  }
  if (body && body.token) {
    setSessionAuth(body.token, body.username || username);
  }
  return body;
};

export const logoutAdmin = () => {
  clearSessionAuth();
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

const getJson = async (url) => {
  const response = await fetch(url, {
    method: 'GET',
    headers: authHeaders({ Accept: 'application/json' }),
    cache: 'no-store',
  });
  checkAuthResponse(response);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
};

const postJson = async (path, options = {}) => {
  const headers = authHeaders(options.headers || {});
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    ...options,
    headers,
  });
  checkAuthResponse(response);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw new Error((body && body.error) || `HTTP ${response.status}`);
  return body;
};

const sendJson = async (method, path, payload) => {
  const headers = authHeaders({ 'Content-Type': 'application/json' });
  const options = {
    method,
    headers,
  };
  if (payload !== undefined) {
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(`${API_BASE}${path}`, options);
  checkAuthResponse(response);
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

/** Deletes one farmer from the database. */
export const deleteFarmer = (farmerId) => sendJson('DELETE', `/api/farmers/${encodeURIComponent(farmerId)}`);

/** Deletes multiple farmers by their IDs. */
export const batchDeleteFarmers = (farmerIds) =>
  postJson('/api/farmers/batch-delete', {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ farmer_ids: farmerIds }),
  });

/** Places a call now for one farmer. mode 'retry' follows the retry rules (first call or next attempt); 'test' is a one-off test row outside them. Returns at once. */
export const callFarmer = (farmerId, mode = 'retry') =>
  postJson(`/api/farmers/${encodeURIComponent(farmerId)}/call`, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) });

/** Schedules a callback for a farmer at a specific or relative time (e.g. 'in 2 hours', 'at 4 PM'). */
export const scheduleCallback = (farmerId, time = 'in 2 hours') =>
  postJson(`/api/farmers/${encodeURIComponent(farmerId)}/callback`, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ time }) });

/** Manually dispatches an advisory SMS message to a farmer. */
export const sendFarmerMessage = (farmerId, kind = 'weather') =>
  postJson(`/api/farmers/${encodeURIComponent(farmerId)}/message`, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind }) });

/** Uploads a farmers CSV (Farmer ID, Farmer Name, Mobile Number, Village, District, State, Language, Consent). */
export const importFarmersCsv = async (file) =>
  postJson('/api/farmers/import', { headers: { 'Content-Type': 'text/csv' }, body: await file.text() });

/** Backend, database, weather API, Sarvam and the phone line: each ok, fail or off (not set up). */
export const getSystemChecks = (refresh = false) => getJson(`${API_BASE}/api/system/checks${refresh ? '?refresh=1' : ''}`);

/** Calls and billed minutes counted from Sarvam's own call records (Sarvam has no balance API). */
export const getUsage = (refresh = false) => getJson(`${API_BASE}/api/usage${refresh ? '?refresh=1' : ''}`);

/** Saves the per-minute rate of the Sarvam plan (rupees a minute); amounts are billed minutes times this rate. */
/** Saves the 'Credits Left' figure from Sarvam's Billing page (rupees); the balance then falls with each call's cost. */
export const saveSarvamBalance = (amount) =>
  postJson('/api/usage', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sarvam_balance: amount }) });

export const saveUsageRate = (sarvamRate) =>
  postJson('/api/usage', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sarvam_rate: sarvamRate }) });

/** Things the team must act on: farmers who asked to stop, failed calls, skipped runs. */
export const getAlerts = () => getJson(`${API_BASE}/api/alerts`);
/** Removes one note for the team (by its id), or every note when no id is given. */
export const dismissAlerts = (id) =>
  postJson('/api/alerts/dismiss', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(id == null ? { all: true } : { id }) });
/** The emails sent (or not) after calls: one row per farmer, day and kind, with why when one was skipped or failed. */
/** Sends one sample email to the test address and says what happened: { status: sent | failed | skipped, note }. */
export const sendTestEmail = () => postJson('/api/mail/test', { headers: { 'Content-Type': 'application/json' }, body: '{}' });
/** The call's transcript with an English line under each turn: { available, turns: [{ speaker, text, english }], error }. */
export const getCallTranslation = (callId) => getJson(`${API_BASE}/api/calls/${encodeURIComponent(callId)}/translation`);
/** Removes one email log row (by its key), or all of them when no key is given. The email is still never sent twice. */
export const dismissMessages = (key) =>
  postJson('/api/messages/dismiss', { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(key == null ? { all: true } : { key }) });
/** The incoming line at a glance: { ready, sync: { at, seen, applied, error }, calls: [...] }. */
export const getIncoming = () => getJson(`${API_BASE}/api/incoming`);
export const getMessages = () => getJson(`${API_BASE}/api/messages`);

export const getCallbacks = () => getJson(`${API_BASE}/api/callbacks`);

export const getWeatherParameters = (lat, lon) => getJson(`${API_BASE}/api/weather?lat=${lat}&lon=${lon}`);
