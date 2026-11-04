import express from 'express';
import { syncAndLoadFarmers } from '../services/farmerService.js';

export const farmersRouter = express.Router();

/**
 * GET /api/farmers
 * Fetches and syncs active farmer profiles directly from Google Sheets (Sheet 1)
 */
farmersRouter.get('/', async (req, res) => {
  try {
    const farmers = await syncAndLoadFarmers({ forceRefresh: true });
    res.json(farmers);
  } catch (err) {
    console.error('Error fetching farmers from Google Sheets:', err);
    res.status(500).json({ error: 'Failed to retrieve farmers from Google Sheets', details: err.message });
  }
});
