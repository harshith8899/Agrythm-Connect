import React, { useState } from 'react';
import { Search, MapPin, Phone, PhoneCall, ExternalLink, Users } from 'lucide-react';
import { GOOGLE_SHEETS_CONFIG } from '../utils/constants';
import { isCallToday, didFarmerPickUpAndTalk, getCallTimestamp, maskPhoneNumber, normalizeLanguage } from '../utils';

export const FarmerDirectory = ({ farmers = [], callLogs = [], onSelectFarmer }) => {
  const [search, setSearch] = useState('');

  // Calculate call counts and today's engagement status purely per actual farmer in Sheet 1
  const farmerStats = farmers.map(f => {
    const farmerCalls = callLogs.filter(c => String(c.farmer_id).trim() === String(f.farmer_id).trim());
    const talkedToday = farmerCalls.some(c => isCallToday(getCallTimestamp(c)) && didFarmerPickUpAndTalk(c));
    return {
      ...f,
      totalCalls: farmerCalls.length,
      talkedToday,
    };
  });

  const filtered = farmerStats.filter(f => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const phone = f.phone_number || f.phone || '';
    return (
      String(f.farmer_name || '').toLowerCase().includes(q) ||
      String(phone).toLowerCase().includes(q) ||
      maskPhoneNumber(phone).toLowerCase().includes(q) ||
      String(f.district || '').toLowerCase().includes(q) ||
      String(f.village || '').toLowerCase().includes(q) ||
      String(f.farmer_id || '').toLowerCase().includes(q)
    );
  });

  if (farmers.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mx-auto">
          <Users className="w-7 h-7 text-trust-navy" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">
            No Farmer Profiles in Database Yet
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            The directory is connected live to your backend database (SQLite: <code>/api/farmers</code>). Add farmer records to the database or switch back to Google Sheet 1 anytime.
          </p>
        </div>
        <div className="pt-2 flex items-center justify-center gap-2">
          <a
            href={GOOGLE_SHEETS_CONFIG.farmersApiUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors"
          >
            <span>Open Farmers API</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header & Search */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Registered Directory
          </span>
          <h2 className="text-xl font-bold text-slate-900">
            Farmer Profiles ({farmers.length})
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Loaded directly from Backend Database (SQLite)
          </p>
        </div>

        <div className="relative min-w-[280px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search farmers by name, village, district..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy transition-all"
          />
        </div>
      </div>

      {/* Farmers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((farmer, index) => (
          <div
            key={farmer.farmer_id || index}
            className="bg-white rounded-2xl border border-slate-200/80 p-5 hover:border-slate-300 transition-all space-y-4 shadow-2xs"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-trust-navy text-white flex items-center justify-center font-bold text-base shadow-xs">
                  {String(farmer.farmer_name || 'F').charAt(0)}
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">
                    {farmer.farmer_name || 'Unnamed Farmer'}
                  </h3>
                  <span className="text-[10px] font-mono text-slate-400">
                    {farmer.farmer_id || 'ID N/A'}
                  </span>
                </div>
              </div>

              <div className="flex flex-col items-end gap-1">
                {farmer.talkedToday && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-trust-green border border-emerald-200">
                    Talked Today
                  </span>
                )}
                {farmer.primary_language && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                      normalizeLanguage(farmer.primary_language) === 'English'
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}
                  >
                    {normalizeLanguage(farmer.primary_language)}
                  </span>
                )}
              </div>
            </div>

            <div className="space-y-1.5 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <Phone className="w-3.5 h-3.5 text-slate-400" />
                <span className="font-mono text-slate-800">{maskPhoneNumber(farmer.phone_number || farmer.phone)}</span>
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                <span>{farmer.village || 'N/A'}, {farmer.district || 'N/A'}</span>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
              <div className="text-slate-500">
                Calls Recorded: <strong className="text-slate-800">{farmer.totalCalls}</strong>
              </div>

              <button
                onClick={() => onSelectFarmer(farmer.farmer_name)}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-50 hover:bg-trust-navy hover:text-white text-trust-navy text-xs font-semibold transition-colors cursor-pointer"
              >
                <PhoneCall className="w-3 h-3" />
                <span>View Call Logs</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
