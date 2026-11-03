import express from 'express';
import { 
  getAllCalls, 
  getCallById, 
  updateCall, 
  recordAttempt 
} from '../database/db.js';
import { 
  executeDemoRun, 
  dispatchCallForFarmer 
} from '../services/orchestrator.js';
import { processFarmerUtterance } from '../services/conversationalEngine.js';

export const callsRouter = express.Router();

/**
 * GET /api/calls
 * Retrieves all call records with nested attempt logs from SQLite
 */
callsRouter.get('/', (req, res) => {
  try {
    const limit = req.query.limit ? Number(req.query.limit) : null;
    const calls = getAllCalls({ limit });
    res.json(calls);
  } catch (err) {
    console.error('Error fetching calls:', err);
    res.status(500).json({ error: 'Failed to retrieve call records', details: err.message });
  }
});

/**
 * POST /api/calls/trigger-demo
 * Executes immediate manual batch run across test numbers,
 * enforcing real-time retry intervals and state machines
 */
callsRouter.post('/trigger-demo', async (req, res) => {
  try {
    const result = await executeDemoRun();
    res.json(result);
  } catch (err) {
    console.error('Error triggering demo batch:', err);
    res.status(500).json({ error: 'Failed to execute demo run', details: err.message });
  }
});

/**
 * GET /api/calls/:id
 * Retrieves single call record
 */
callsRouter.get('/:id', (req, res) => {
  try {
    const call = getCallById(req.params.id);
    if (!call) {
      return res.status(404).json({ error: 'Call not found' });
    }
    res.json(call);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /api/calls/webhook
 * Simulates or handles telephony events, transcripts, callbacks, and retries.
 * 
 * Supported events:
 * - 'answered': farmer answers call
 * - 'utterance': farmer speaks, intent classifier processes response
 * - 'no-answer' / 'busy' / 'failed': telephony failures initiating 2-retry cycle
 * - 'completed': call session closed
 */
callsRouter.post('/webhook', async (req, res) => {
  try {
    const { 
      call_id, 
      event, 
      utterance, 
      language = 'Hindi',
      duration_seconds = 0,
      weather 
    } = req.body;

    if (!call_id) {
      return res.status(400).json({ error: 'call_id is required' });
    }

    const existingCall = getCallById(call_id);
    if (!existingCall) {
      return res.status(404).json({ error: 'Call record not found' });
    }

    const currentWeather = weather || {
      temperature: existingCall.weather_temp || 28.0,
      wind_speed: existingCall.weather_windspeed || 10.0,
      rainfall_probability: existingCall.weather_rainfall || 20,
      relative_humidity: existingCall.weather_humidity || 60
    };

    switch (event) {
      case 'utterance': {
        // Run conversational classifier
        const conv = processFarmerUtterance(utterance, currentWeather, { language });
        
        let existingTranscript = [];
        try {
          existingTranscript = typeof existingCall.transcript === 'string'
            ? JSON.parse(existingCall.transcript)
            : (existingCall.transcript || []);
        } catch {
          existingTranscript = [{ speaker: 'Transcript', text: String(existingCall.transcript || '') }];
        }

        const updatedTranscript = [
          ...existingTranscript,
          { speaker: 'Farmer', text: utterance },
          { speaker: 'Agent', text: conv.speech_response }
        ];

        const updated = updateCall(call_id, {
          status: conv.status,
          disposition: conv.disposition,
          scheduled_callback_time: conv.scheduled_callback_time,
          duration_seconds: Math.max(existingCall.duration_seconds || 0, Number(duration_seconds)),
          transcript: updatedTranscript
        });

        return res.json({
          status: 'ok',
          action: conv.intent,
          response: conv.speech_response,
          call: updated
        });
      }

      case 'no-answer':
      case 'busy':
      case 'failed': {
        const currentRetry = existingCall.retry_count || 0;
        const newRetry = currentRetry + 1;
        const attemptNumber = (existingCall.attempts_log?.length || 0) + 1;

        recordAttempt({
          call_id,
          attempt_number: attemptNumber,
          status: event === 'busy' ? 'Busy' : (event === 'no-answer' ? 'No Answer' : 'Failed'),
          duration_seconds: Number(duration_seconds) || 10,
          error_message: `Telephony event: ${event}`,
          transcript: `Attempt ${attemptNumber}: ${event}`
        });

        let nextStatus = 'Retrying';
        let disposition = event === 'busy' ? 'Busy' : 'No Answer';

        // 2-retry cycle: if retries exceed 2 (i.e. attempt 3 fails), mark Failed
        if (newRetry > 2) {
          nextStatus = 'Failed';
          disposition = 'Fallback Sent';
        }

        const updated = updateCall(call_id, {
          status: nextStatus,
          disposition,
          retry_count: Math.min(newRetry, 2),
          duration_seconds: (existingCall.duration_seconds || 0) + (Number(duration_seconds) || 10)
        });

        return res.json({
          status: 'ok',
          retry_count: updated.retry_count,
          call_status: updated.status,
          call: updated
        });
      }

      case 'completed': {
        const updated = updateCall(call_id, {
          status: 'Completed',
          disposition: existingCall.disposition || 'Weather Delivered',
          duration_seconds: Math.max(existingCall.duration_seconds || 0, Number(duration_seconds))
        });
        return res.json({ status: 'ok', call: updated });
      }

      default:
        return res.json({ status: 'ignored', message: `Unhandled event: ${event}` });
    }
  } catch (err) {
    console.error('Webhook processing error:', err);
    res.status(500).json({ error: 'Webhook processing failed', details: err.message });
  }
});

