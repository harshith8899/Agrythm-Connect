import express from 'express';
import { fetch4ParameterWeather } from '../services/weatherService.js';

export const weatherRouter = express.Router();

/**
 * GET /api/weather?lat={lat}&lon={lon}
 * Returns exactly the 4 real-time meteorological parameters:
 * 1. Temperature (°C)
 * 2. Wind Speed (km/h)
 * 3. Rainfall / Precipitation Probability (%)
 * 4. Relative Humidity (%)
 */
weatherRouter.get('/', async (req, res) => {
  try {
    const lat = req.query.lat ? Number(req.query.lat) : 12.524;
    const lon = req.query.lon ? Number(req.query.lon) : 76.8958;
    const location = req.query.location || 'Local Coordinates';

    const weather = await fetch4ParameterWeather(lat, lon, location);
    res.json(weather);
  } catch (err) {
    console.error('Weather fetch error:', err);
    res.status(500).json({ error: 'Failed to fetch weather parameters', details: err.message });
  }
});

