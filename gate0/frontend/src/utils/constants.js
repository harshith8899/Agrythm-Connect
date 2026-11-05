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

// Backend API. In development the address is empty and Vite proxies /api to the Python backend (see vite.config.js).
// For a hosted dashboard set VITE_API_URL (for example https://api.example.com) when building.
export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export const API_CONFIG = {
  farmersApiUrl: `${API_BASE}/api/farmers`,
  callLogsApiUrl: `${API_BASE}/api/calls`,
};
