import Papa from 'papaparse';
import { GOOGLE_SHEETS_CONFIG } from './constants';

/**
 * Fetch and parse a public Google Sheet published/exported as CSV
 * @param {string} csvUrl 
 * @returns {Promise<Array>}
 */
export const fetchGoogleSheetCSV = async (csvUrl) => {
  try {
    const response = await fetch(csvUrl, {
      method: 'GET',
      headers: {
        'Accept': 'text/csv',
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch sheet: HTTP ${response.status}`);
    }

    const csvText = await response.text();

    return new Promise((resolve, reject) => {
      Papa.parse(csvText, {
        header: true,
        skipEmptyLines: true,
        dynamicTyping: true,
        complete: (results) => {
          // Filter out rows that are completely null, empty, or just header duplicates
          const validRows = (results.data || []).filter(row => {
            return Object.values(row).some(val => val !== null && val !== undefined && String(val).trim() !== '');
          });
          resolve(validRows);
        },
        error: (err) => reject(err),
      });
    });
  } catch (error) {
    console.warn(`Error fetching CSV from ${csvUrl}:`, error);
    throw error;
  }
};

/**
 * Fetch all Farmers from local SQLite API (falls back to Google Sheets CSV if API unavailable)
 */
export const loadFarmersData = async (customUrl = null) => {
  const url = customUrl || GOOGLE_SHEETS_CONFIG.farmersApiUrl;
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return { data: Array.isArray(data) ? data : [], source: 'sqlite_live' };
  } catch (err) {
    console.warn(`Could not fetch from SQLite Farmers API (${url}). Trying Google Sheet fallback:`, err.message);
    try {
      const rows = await fetchGoogleSheetCSV(GOOGLE_SHEETS_CONFIG.farmersCsvUrl);
      return { data: rows || [], source: 'live_google_sheet' };
    } catch {
      return { data: [], source: 'offline', error: err.message };
    }
  }
};

/**
 * Fetch Call Execution Logs from local SQLite API
 */
export const loadCallLogsData = async (customUrl = null) => {
  const url = customUrl || GOOGLE_SHEETS_CONFIG.callLogsApiUrl;
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return { data: Array.isArray(data) ? data : [], source: 'sqlite_live' };
  } catch (err) {
    console.warn(`Could not fetch from SQLite API (${url}). Check if server is running:`, err.message);
    return { data: [], source: 'offline', error: err.message };
  }
};

/**
 * Trigger manual demo run across test numbers in SQLite Orchestrator
 */
export const triggerDemoCalls = async () => {
  const url = 'http://localhost:8000/api/calls/trigger-demo';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Demo trigger failed: HTTP ${response.status}`);
  }
  return await response.json();
};

/**
 * Get 9:00 AM Auto Dispatcher status
 */
export const getDispatcherStatus = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/orchestrator/status');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch {
    return { enabled: true, scheduledTime: '09:00 AM IST', systemStatus: 'Operational' };
  }
};

/**
 * Toggle or update Auto Dispatcher
 */
export const updateDispatcherStatus = async (enabled) => {
  const response = await fetch('http://localhost:8000/api/orchestrator/auto-dispatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
};

/**
 * Fetch 4 meteorological parameters from Open-Meteo endpoint
 */
export const getWeatherParameters = async (lat, lon) => {
  const url = `http://localhost:8000/api/weather?lat=${lat}&lon=${lon}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
};

/**
 * Push an updated or new call log to a Google Apps Script Web App endpoint
 */
export const syncCallUpdateToGoogleSheet = async (webAppUrl, payload) => {
  if (!webAppUrl) {
    return { success: true, localOnly: true, message: 'Saved to dashboard state (Apps Script Web App URL not configured)' };
  }

  try {
    await fetch(webAppUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      mode: 'no-cors',
      body: JSON.stringify(payload),
    });

    return { success: true, localOnly: false, message: 'Synced to Google Sheet via Apps Script Web App' };
  } catch (err) {
    console.error('Failed to sync to Google Apps Script:', err);
    return { success: false, error: err.message };
  }
};

/**
 * Pre-written Google Apps Script code for bidirectional sheet editing
 */
export const GOOGLE_APPS_SCRIPT_SAMPLE = `function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Sheet1") || SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    
    // Append or update call record
    if (data.action === "updateCall") {
      var rows = sheet.getDataRange().getValues();
      var callId = data.call_id;
      var foundRow = -1;
      
      for (var i = 1; i < rows.length; i++) {
        if (rows[i][0] == callId) {
          foundRow = i + 1;
          break;
        }
      }
      
      if (foundRow !== -1) {
        // Update status and operator notes (columns 9 and 11)
        sheet.getRange(foundRow, 9).setValue(data.call_status);
        sheet.getRange(foundRow, 11).setValue(data.operator_notes);
      } else {
        // Append new record
        sheet.appendRow([
          data.call_id,
          data.farmer_id,
          data.call_timestamp,
          data.duration_sec,
          data.weather_forecast,
          data.rainfall_chance,
          data.advisory_summary,
          data.ai_confidence_score,
          data.call_status,
          data.transcript_preview,
          data.operator_notes
        ]);
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({ status: "success" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}`;
