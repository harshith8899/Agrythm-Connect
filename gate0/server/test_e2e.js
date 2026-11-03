/**
 * Comprehensive End-to-End Orchestrator & Real Google Sheet Data Test Suite
 */
import assert from 'node:assert';
import { getDb, getAllCalls, getAllFarmers, isFarmerCalledToday, clearCalls } from './database/db.js';
import { syncAndLoadFarmers } from './services/farmerService.js';
import { fetch4ParameterWeather } from './services/weatherService.js';
import { processFarmerUtterance } from './services/conversationalEngine.js';
import { executeDemoRun, executeDailyDispatch, simulateCallLifecycle } from './services/orchestrator.js';

async function runTests() {
  console.log('=== Starting Real Data & Orchestrator E2E Test Suite ===\n');

  // Test 1: Ingest Real Farmers from Live Google Sheet
  console.log('Test 1: Ingesting Real Farmers from Google Sheets...');
  const realFarmers = await syncAndLoadFarmers({ forceRefresh: true });
  assert(realFarmers.length >= 2, `Expected at least 2 real farmers, got ${realFarmers.length}`);

  const hemanth = realFarmers.find(f => String(f.farmer_id) === '1001');
  const harshith = realFarmers.find(f => String(f.farmer_id) === '1002');

  assert(hemanth != null, 'Farmer 1001 (Hemanth) must exist from Google Sheet');
  assert(harshith != null, 'Farmer 1002 (Harshith) must exist from Google Sheet');
  assert.strictEqual(hemanth.phone_number, '7483175260');
  assert.strictEqual(harshith.phone_number, '6363713736');
  console.log(`✓ Real farmers fetched from Google Sheet:`);
  console.log(`   - 1001: ${hemanth.farmer_name} | Phone: ${hemanth.phone_number} | Village: ${hemanth.village} | Lang: ${hemanth.preferred_language}`);
  console.log(`   - 1002: ${harshith.farmer_name} | Phone: ${harshith.phone_number} | Village: ${harshith.village} | Lang: ${harshith.preferred_language}`);

  // Test 2: Live 4-Parameter Weather Ingestion for Real Locations
  console.log('\nTest 2: Real-time 4-Parameter Weather for Humnabad & Bhalki...');
  const wHumnabad = await fetch4ParameterWeather(hemanth.latitude, hemanth.longitude, hemanth.village);
  const wBhalki = await fetch4ParameterWeather(harshith.latitude, harshith.longitude, harshith.village);

  assert(typeof wHumnabad.temperature === 'number');
  assert(typeof wHumnabad.wind_speed === 'number');
  assert(typeof wHumnabad.rainfall_probability === 'number');
  assert(typeof wHumnabad.relative_humidity === 'number');
  console.log(`✓ Humnabad Weather: ${wHumnabad.temperature}°C, ${wHumnabad.wind_speed} km/h wind, ${wHumnabad.rainfall_probability}% rain, ${wHumnabad.relative_humidity}% humidity`);
  console.log(`✓ Bhalki Weather:   ${wBhalki.temperature}°C, ${wBhalki.wind_speed} km/h wind, ${wBhalki.rainfall_probability}% rain, ${wBhalki.relative_humidity}% humidity`);

  // Test 3: Conversational Logic for Real Farmers
  console.log('\nTest 3: Multi-lingual Dialogue & Guardrail Handling...');

  // 3a: Hindi Weather Doubt (Hemanth)
  const doubtRes = processFarmerUtterance('क्या आज दोपहर बारिश होगी?', wHumnabad, { language: 'Hindi' });
  assert.strictEqual(doubtRes.intent, 'WEATHER_DOUBT_RESOLVED');
  assert.strictEqual(doubtRes.status, 'Completed');
  console.log('✓ Hindi weather doubt resolved');

  // 3b: Kannada Callback Reschedule (Harshith)
  const callbackRes = processFarmerUtterance('ಈಗ ಮಾರುಕಟ್ಟೆಯಲ್ಲಿದ್ದೇನೆ, ಸಂಜೆ 5 ಗಂಟೆಗೆ ಕರೆ ಮಾಡಿ.', wBhalki, { language: 'Kannada' });
  assert.strictEqual(callbackRes.intent, 'CALLBACK_REQUESTED');
  assert.strictEqual(callbackRes.disposition, 'Callback Requested');
  assert(callbackRes.scheduled_callback_time != null);
  console.log(`✓ Kannada callback requested handled: "${callbackRes.scheduled_callback_time}"`);

  // 3c: Boundary Guardrail Escalation
  const guardRes = processFarmerUtterance('ಕೀಟನಾಶಕ ಔಷಧಿ ಯಾವುದು ಸಿಂಪಡಿಸಬೇಕು?', wBhalki, { language: 'Kannada' });
  assert.strictEqual(guardRes.intent, 'NON_WEATHER_ESCALATION');
  assert.strictEqual(guardRes.status, 'Escalated');
  assert.strictEqual(guardRes.disposition, 'Non-Weather Inquiry');
  console.log('✓ Agronomic boundary guardrail triggered in Kannada');

  // Test 4: Dispatch Call Cycle for Real Farmers
  console.log('\nTest 4: Real Farmer Call Dispatch & SQLite Persistence...');
  clearCalls();
  const dispatchRes = await executeDemoRun();
  assert.strictEqual(dispatchRes.success, true);
  assert.strictEqual(dispatchRes.processedCount, 2);

  const calls = getAllCalls();
  assert.strictEqual(calls.length, 2);
  assert(calls.some(c => c.farmer_id === '1001' && c.farmer_name === 'Hemanth'));
  assert(calls.some(c => c.farmer_id === '1002' && c.farmer_name === 'Harshith'));

  console.log('✓ Real calls persisted in SQLite with live 4-parameter weather metrics');
  console.log('\n======================================================');
  console.log('REAL DATA TEST SUITE FULLY VERIFIED!');
  console.log('======================================================');
}

runTests().catch(err => {
  console.error('Test suite failed:', err);
  process.exit(1);
});
