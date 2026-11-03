import { getAllFarmers, upsertFarmer, getDb } from '../database/db.js';

const GOOGLE_SHEET_FARMERS_CSV = 'https://docs.google.com/spreadsheets/d/1WwdKz4dyAL2tgMaMqStDvm95TQmaYKJtKCMPXYKWFcg/export?format=csv';

// Accurate coordinates for Karnataka districts and taluks in the Google Sheets
const LOCATION_COORDINATES = {
  'humnabad': { lat: 17.7667, lon: 77.2833 },
  'bhalki': { lat: 18.0441, lon: 77.2185 },
  'bidar': { lat: 17.9104, lon: 77.5199 },
  'aurad': { lat: 18.2500, lon: 77.4333 },
  'basavakalyan': { lat: 17.8736, lon: 76.9536 },
  'mandya': { lat: 12.5240, lon: 76.8958 },
  'maddur': { lat: 12.5833, lon: 77.0500 },
  'mysuru': { lat: 12.2958, lon: 76.6394 },
  'mysore': { lat: 12.2958, lon: 76.6394 },
  'hassan': { lat: 13.0068, lon: 76.0996 },
  'raichur': { lat: 16.2120, lon: 77.3439 }
};

/**
 * Loads farmers directly from the Google Sheets CSV (Sheet 1) and syncs to SQLite
 */
export async function syncAndLoadFarmers(options = {}) {
  const forceRefresh = options.forceRefresh ?? true;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    const res = await fetch(GOOGLE_SHEET_FARMERS_CSV, {
      signal: controller.signal,
      headers: { 'Accept': 'text/csv' },
      cache: 'no-store'
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const csvText = await res.text();
      const parsed = parseGoogleSheetFarmers(csvText);
      if (parsed.length > 0) {
        // Clean out legacy demo farmers
        const db = getDb();
        try {
          db.prepare(`DELETE FROM farmers WHERE farmer_id LIKE 'F0%'`).run();
        } catch {}

        for (const f of parsed) {
          upsertFarmer(f);
        }
        console.log(`[FarmerService] Successfully ingested ${parsed.length} real farmer profiles from Google Sheets.`);
        return getAllFarmers();
      }
    }
  } catch (err) {
    console.warn(`[FarmerService] Google Sheet CSV sync failed (${err.message}). Using local cache.`);
  }

  return getAllFarmers();
}

/**
 * Parses Google Sheets CSV rows into normalized farmer objects
 */
function parseGoogleSheetFarmers(csvText) {
  const lines = csvText.split(/\r?\n/).filter(line => line.trim().length > 0);
  if (lines.length < 2) return [];

  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/^["']|["']$/g, ''));
  const farmers = [];

  for (let i = 1; i < lines.length; i++) {
    const row = lines[i].split(',').map(c => c.trim().replace(/^["']|["']$/g, ''));
    if (row.length === 0 || !row[0]) continue;

    const getCol = (names) => {
      for (const name of names) {
        const idx = headers.indexOf(name);
        if (idx !== -1 && row[idx] !== undefined) return row[idx];
      }
      return '';
    };

    const farmerId = getCol(['farmer_id', 'farmer id', 'id']);
    const farmerName = getCol(['farmer_name', 'farmer name', 'name']);
    const phone = getCol(['phone_number', 'mobile number', 'phone', 'mobile']);
    const language = getCol(['primary_language', 'preferred calling language', 'language']) || 'Hindi';
    const district = getCol(['district']) || 'Bidar';
    const village = getCol(['village', 'cluster', 'location']) || 'Humnabad';

    // Lookup coordinates by village or district
    const locKey = (village || district || '').toLowerCase();
    const coords = LOCATION_COORDINATES[locKey] || LOCATION_COORDINATES[district.toLowerCase()] || { lat: 17.9104, lon: 77.5199 };

    if (farmerId && farmerName) {
      farmers.push({
        farmer_id: farmerId,
        farmer_name: farmerName,
        phone_number: phone,
        village: village,
        district: district,
        state: 'Karnataka',
        cluster: `${district} - ${village}`,
        latitude: coords.lat,
        longitude: coords.lon,
        preferred_language: language,
        call_consent: 'Yes',
        active: 'Yes'
      });
    }
  }

  return farmers;
}
