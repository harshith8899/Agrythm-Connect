import React from 'react';
import { 
  CloudRain, 
  ExternalLink 
} from 'lucide-react';
import { GOOGLE_SHEETS_CONFIG } from '../utils/constants';

export const WeatherAlertsView = ({ callLogs = [] }) => {
  // Aggregate real district reports from sheet call logs
  const districtMap = new Map();

  callLogs.forEach(call => {
    const district = call.district || 'General';
    if (!districtMap.has(district)) {
      districtMap.set(district, {
        district,
        calls: [],
        latestForecast: call.weather_forecast || 'Weather report logged',
        advisory: call.advisory_summary || 'No advisory text',
        rainfallChance: call.rainfall_chance || 'N/A',
        temp: call.temperature || 'N/A',
        wind: call.wind || 'N/A',
      });
    }
    const item = districtMap.get(district);
    item.calls.push(call);
    if (call.weather_forecast && call.weather_forecast !== 'General Weather') item.latestForecast = call.weather_forecast;
    if (call.advisory_summary && !call.advisory_summary.startsWith('No spoken message')) item.advisory = call.advisory_summary;
    if (call.rainfall_chance && call.rainfall_chance !== 'N/A') item.rainfallChance = call.rainfall_chance;
    if (call.temperature && call.temperature !== 'N/A') item.temp = call.temperature;
    if (call.wind && call.wind !== 'N/A') item.wind = call.wind;
  });

  const alerts = Array.from(districtMap.values());

  if (alerts.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mx-auto">
          <CloudRain className="w-7 h-7 text-trust-navy" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">
            No Weather Advisories Recorded Yet
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            District weather alerts are compiled from the grounded meteorological parameters and spoken advisory summaries delivered by your voice agent. As calls are logged, district cards will appear here.
          </p>
        </div>
        <div className="pt-2">
          <a
            href={GOOGLE_SHEETS_CONFIG.callLogsApiUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors"
          >
            <span>View Live Call Telemetry</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
            Meteorological Intelligence
          </span>
          <h2 className="text-xl font-bold text-slate-900">
            District Weather Advisories ({alerts.length})
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Compiled from active Gate Zero voice agent call records and meteorological grounding
          </p>
        </div>
      </div>

      {/* District Alert Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {alerts.map((alert, i) => (
          <div
            key={i}
            className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-4 hover:border-slate-300 transition-all shadow-2xs"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">
                {alert.district} District
              </h3>
              <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                {alert.calls.length} Call{alert.calls.length > 1 ? 's' : ''} Logged
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-slate-800">{alert.latestForecast}</div>
                {(alert.temp !== 'N/A' || alert.wind !== 'N/A') && (
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    Temp: {alert.temp} • Wind: {alert.wind}
                  </div>
                )}
              </div>
              <div className="text-right">
                <span className="text-xs font-extrabold text-blue-600 block">
                  {alert.rainfallChance}
                </span>
                <span className="text-[10px] text-slate-400">Rain Prob</span>
              </div>
            </div>

            <div className="text-xs text-slate-700 leading-relaxed bg-blue-50/40 p-3 rounded-xl border border-blue-100/60">
              <strong className="text-trust-navy block mb-0.5">Latest Voice Advisory:</strong>
              {alert.advisory}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
