import express from 'express';
import cors from 'cors';
import { callsRouter } from './routes/callsRouter.js';
import { weatherRouter } from './routes/weatherRouter.js';
import { farmersRouter } from './routes/farmersRouter.js';
import { orchestratorRouter } from './routes/orchestratorRouter.js';
import { startCronScheduler } from './services/orchestrator.js';
import { getDb } from './database/db.js';

const app = express();
const PORT = process.env.PORT || 8000;

// Enable Cross-Origin Resource Sharing
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'Accept']
}));

app.use(express.json());

// Initialize SQLite Database schema
getDb();

// Register API Routes
app.use('/api/calls', callsRouter);
app.use('/api/weather', weatherRouter);
app.use('/api/farmers', farmersRouter);
app.use('/api/orchestrator', orchestratorRouter);

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'Agrythm Connect Orchestrator API',
    timestamp: new Date().toISOString()
  });
});

// Start background cron scheduler for 9:00 AM daily dispatch
startCronScheduler();

// Start Server
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Agrythm Connect] Orchestrator & Telemetry Server listening on http://localhost:${PORT}`);
  console.log(`- API Calls:         http://localhost:${PORT}/api/calls`);
  console.log(`- Trigger Demo:      POST http://localhost:${PORT}/api/calls/trigger-demo`);
  console.log(`- 4-Param Weather:   http://localhost:${PORT}/api/weather?lat=12.52&lon=76.89`);
  console.log(`- Telephony Webhook: POST http://localhost:${PORT}/api/calls/webhook`);
  console.log(`- Farmer Directory:  http://localhost:${PORT}/api/farmers`);
  console.log(`- Auto Dispatcher:   http://localhost:${PORT}/api/orchestrator/status`);
});

export default app;

