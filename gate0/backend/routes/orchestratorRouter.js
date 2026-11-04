import express from 'express';
import { 
  getAutoDispatcherStatus, 
  setAutoDispatcherStatus,
  executeDailyDispatch
} from '../services/orchestrator.js';

export const orchestratorRouter = express.Router();

/**
 * GET /api/orchestrator/status
 * Returns orchestrator state and 9:00 AM auto dispatcher settings
 */
orchestratorRouter.get('/status', (req, res) => {
  res.json(getAutoDispatcherStatus());
});

/**
 * POST /api/orchestrator/auto-dispatch
 * Toggles or configures automated daily 9:00 AM dispatcher
 */
orchestratorRouter.post('/auto-dispatch', (req, res) => {
  const { enabled } = req.body;
  if (enabled === undefined) {
    return res.status(400).json({ error: 'Field "enabled" (boolean) is required' });
  }
  const updated = setAutoDispatcherStatus(enabled);
  res.json(updated);
});

/**
 * POST /api/orchestrator/run-now
 * Manually executes daily morning dispatch cycle
 */
orchestratorRouter.post('/run-now', async (req, res) => {
  try {
    const isDemoOverride = req.body.isDemoOverride || false;
    const result = await executeDailyDispatch({ isDemoOverride });
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: 'Daily dispatch execution failed', details: err.message });
  }
});

