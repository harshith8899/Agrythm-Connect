import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DB_DIR = path.resolve(__dirname);
if (!fs.existsSync(DB_DIR)) {
  fs.mkdirSync(DB_DIR, { recursive: true });
}

export const DB_PATH = path.join(DB_DIR, 'agrythm_connect.db');

let dbInstance = null;

export function getDb() {
  if (!dbInstance) {
    try {
      dbInstance = new DatabaseSync(DB_PATH);
      initSchema(dbInstance);
    } catch (err) {
      console.warn(`Could not open file database at ${DB_PATH} (${err.message}). Falling back to in-memory SQLite.`);
      dbInstance = new DatabaseSync(':memory:');
      initSchema(dbInstance);
    }
  }
  return dbInstance;
}

function initSchema(db) {
  // Main calls table matching specification
  db.exec(`
    CREATE TABLE IF NOT EXISTS calls (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      call_id TEXT UNIQUE NOT NULL,
      farmer_id TEXT NOT NULL,
      farmer_name TEXT,
      phone_number TEXT,
      location TEXT,
      weather_temp REAL,
      weather_windspeed REAL,
      weather_rainfall REAL,
      weather_humidity REAL,
      status TEXT CHECK(status IN ('Scheduled', 'Calling', 'Completed', 'Retrying', 'Failed', 'Escalated')),
      disposition TEXT,
      retry_count INTEGER DEFAULT 0,
      scheduled_callback_time TEXT DEFAULT NULL,
      duration_seconds INTEGER DEFAULT 0,
      transcript TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS call_attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      call_id TEXT NOT NULL,
      attempt_number INTEGER NOT NULL,
      status TEXT NOT NULL,
      duration_seconds INTEGER DEFAULT 0,
      error_message TEXT,
      transcript TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (call_id) REFERENCES calls(call_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS farmers (
      farmer_id TEXT PRIMARY KEY,
      farmer_name TEXT NOT NULL,
      phone_number TEXT,
      village TEXT,
      district TEXT,
      state TEXT,
      cluster TEXT,
      latitude REAL,
      longitude REAL,
      preferred_language TEXT DEFAULT 'Hindi',
      call_consent TEXT DEFAULT 'Yes',
      active TEXT DEFAULT 'Yes',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_calls_farmer_date ON calls(farmer_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
    CREATE INDEX IF NOT EXISTS idx_attempts_call_id ON call_attempts(call_id);
  `);

  // Remove any legacy demo farmer IDs (F001 to F010) if present
  try {
    db.prepare(`DELETE FROM farmers WHERE farmer_id LIKE 'F0%'`).run();
    db.prepare(`DELETE FROM calls WHERE farmer_id LIKE 'F0%'`).run();
  } catch {}
}

// -----------------------------------------------------------------------------
// Database Access Repository Functions
// -----------------------------------------------------------------------------

/**
 * Checks if a farmer already has a call marked 'Completed' today.
 * Prevents duplicate calls during automated dispatching.
 */
export function isFarmerCalledToday(farmer_id) {
  const db = getDb();
  const row = db.prepare(`
    SELECT call_id, status FROM calls
    WHERE farmer_id = ?
      AND date(created_at) = date('now')
      AND status = 'Completed'
    LIMIT 1
  `).get(farmer_id);
  return Boolean(row);
}

/**
 * Inserts a new call record
 */
export function insertCall(callData) {
  const db = getDb();
  const stmt = db.prepare(`
    INSERT INTO calls (
      call_id, farmer_id, farmer_name, phone_number, location,
      weather_temp, weather_windspeed, weather_rainfall, weather_humidity,
      status, disposition, retry_count, scheduled_callback_time,
      duration_seconds, transcript, created_at, updated_at
    ) VALUES (
      ?, ?, ?, ?, ?,
      ?, ?, ?, ?,
      ?, ?, ?, ?,
      ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    )
  `);

  stmt.run(
    callData.call_id,
    callData.farmer_id,
    callData.farmer_name || null,
    callData.phone_number || null,
    callData.location || null,
    callData.weather_temp != null ? Number(callData.weather_temp) : null,
    callData.weather_windspeed != null ? Number(callData.weather_windspeed) : null,
    callData.weather_rainfall != null ? Number(callData.weather_rainfall) : null,
    callData.weather_humidity != null ? Number(callData.weather_humidity) : null,
    callData.status || 'Scheduled',
    callData.disposition || 'Pending',
    callData.retry_count || 0,
    callData.scheduled_callback_time || null,
    callData.duration_seconds || 0,
    typeof callData.transcript === 'object' ? JSON.stringify(callData.transcript) : (callData.transcript || null)
  );

  return getCallById(callData.call_id);
}

/**
 * Updates an existing call record
 */
export function updateCall(call_id, updates) {
  const db = getDb();
  const fields = [];
  const params = [];

  const allowedFields = [
    'farmer_name', 'phone_number', 'location',
    'weather_temp', 'weather_windspeed', 'weather_rainfall', 'weather_humidity',
    'status', 'disposition', 'retry_count', 'scheduled_callback_time',
    'duration_seconds', 'transcript'
  ];

  for (const key of allowedFields) {
    if (updates[key] !== undefined) {
      fields.push(`${key} = ?`);
      if (key === 'transcript' && typeof updates[key] === 'object') {
        params.push(JSON.stringify(updates[key]));
      } else {
        params.push(updates[key]);
      }
    }
  }

  if (fields.length === 0) return getCallById(call_id);

  fields.push('updated_at = CURRENT_TIMESTAMP');
  params.push(call_id);

  const sql = `UPDATE calls SET ${fields.join(', ')} WHERE call_id = ?`;
  db.prepare(sql).run(...params);

  return getCallById(call_id);
}

/**
 * Records an individual attempt for auditability
 */
export function recordAttempt(attemptData) {
  const db = getDb();
  const stmt = db.prepare(`
    INSERT INTO call_attempts (
      call_id, attempt_number, status, duration_seconds, error_message, transcript, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
  `);

  stmt.run(
    attemptData.call_id,
    attemptData.attempt_number || 1,
    attemptData.status,
    attemptData.duration_seconds || 0,
    attemptData.error_message || null,
    typeof attemptData.transcript === 'object' ? JSON.stringify(attemptData.transcript) : (attemptData.transcript || null)
  );
}

/**
 * Retrieves all call records with nested attempt logs
 */
export function getAllCalls(options = {}) {
  const db = getDb();
  let sql = 'SELECT * FROM calls ORDER BY created_at DESC';
  if (options.limit) {
    sql += ` LIMIT ${Number(options.limit)}`;
  }

  const calls = db.prepare(sql).all();
  if (calls.length === 0) return [];

  // Fetch attempts for all calls
  const attemptsStmt = db.prepare('SELECT * FROM call_attempts WHERE call_id = ? ORDER BY attempt_number ASC');
  
  return calls.map(c => {
    const attempts = attemptsStmt.all(c.call_id);
    return {
      ...c,
      attempts_log: attempts
    };
  });
}

/**
 * Retrieves a single call record with attempt logs
 */
export function getCallById(call_id) {
  const db = getDb();
  const call = db.prepare('SELECT * FROM calls WHERE call_id = ?').get(call_id);
  if (!call) return null;

  const attempts = db.prepare('SELECT * FROM call_attempts WHERE call_id = ? ORDER BY attempt_number ASC').all(call_id);
  return {
    ...call,
    attempts_log: attempts
  };
}

/**
 * Retrieves all registered farmers
 */
export function getAllFarmers() {
  const db = getDb();
  return db.prepare('SELECT * FROM farmers ORDER BY farmer_id ASC').all();
}

/**
 * Upserts a farmer profile
 */
export function upsertFarmer(farmer) {
  const db = getDb();
  const stmt = db.prepare(`
    INSERT INTO farmers (
      farmer_id, farmer_name, phone_number, village, district, state,
      cluster, latitude, longitude, preferred_language, call_consent, active
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(farmer_id) DO UPDATE SET
      farmer_name = excluded.farmer_name,
      phone_number = excluded.phone_number,
      village = excluded.village,
      district = excluded.district,
      state = excluded.state,
      cluster = excluded.cluster,
      latitude = excluded.latitude,
      longitude = excluded.longitude,
      preferred_language = excluded.preferred_language,
      call_consent = excluded.call_consent,
      active = excluded.active
  `);

  stmt.run(
    String(farmer.farmer_id).trim(),
    farmer.farmer_name || farmer.name,
    String(farmer.phone_number || farmer.phone || ''),
    farmer.village || farmer.location || null,
    farmer.district || null,
    farmer.state || null,
    farmer.cluster || null,
    farmer.latitude != null ? Number(farmer.latitude) : null,
    farmer.longitude != null ? Number(farmer.longitude) : null,
    farmer.preferred_language || farmer.primary_language || 'Hindi',
    farmer.call_consent || 'Yes',
    farmer.active || 'Yes'
  );
}

/**
 * Clear calls table (useful for test resets)
 */
export function clearCalls() {
  const db = getDb();
  db.exec('DELETE FROM call_attempts; DELETE FROM calls;');
}

/**
 * Clear all tables including farmers
 */
export function clearAll() {
  const db = getDb();
  db.exec('DELETE FROM call_attempts; DELETE FROM calls; DELETE FROM farmers;');
}
