// Trust AI Light System Design Tokens & Constants
export const TRUST_AI_THEME = {
  colors: {
    navy: '#0F2444',
    green: '#1E6F43',
    canvas: '#F8FAFC',
    card: '#FFFFFF',
    textPrimary: '#0F172A',
    textSecondary: '#64748B',
    border: 'rgba(226, 232, 240, 0.8)',
  },
  typography: {
    subHeader: 'text-[11px] font-bold tracking-wider text-slate-500 uppercase',
  },
  card: 'bg-white rounded-2xl border border-slate-200/80 p-5 transition-all duration-200',
};

// Telemetry & Google Sheets Configuration
export const GOOGLE_SHEETS_CONFIG = {
  // SQLite Local API Endpoints (Backend Database)
  farmersApiUrl: 'http://localhost:8000/api/farmers',
  callLogsApiUrl: 'http://localhost:8000/api/calls',

  // Google Sheets fallback / alternate source
  farmersSheetId: '1WwdKz4dyAL2tgMaMqStDvm95TQmaYKJtKCMPXYKWFcg',
  farmersCsvUrl: 'https://docs.google.com/spreadsheets/d/1WwdKz4dyAL2tgMaMqStDvm95TQmaYKJtKCMPXYKWFcg/export?format=csv',
  callLogsSheetId: '14SwDi8WGten2dzqXDT-w29gbDLBpyDwjHQ8P-DnNds0',
  callLogsCsvUrl: 'https://docs.google.com/spreadsheets/d/14SwDi8WGten2dzqXDT-w29gbDLBpyDwjHQ8P-DnNds0/export?format=csv',
};
