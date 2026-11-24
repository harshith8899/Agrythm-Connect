import React, { useMemo } from 'react';
import {
  Sun,
  CloudSun,
  CloudRain,
  Wind,
  Droplets,
  Thermometer,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { callDirections } from '../utils/callDirection';

function getWeatherVisualMeta(rain, wind, humidity) {
  if (rain >= 50) {
    return {
      Icon: CloudRain,
      label: 'Rain Alert',
      badgeClass: 'bg-sky-50 text-sky-700 border-sky-200',
      iconColor: 'text-sky-600',
    };
  }
  if (wind >= 25) {
    return {
      Icon: Wind,
      label: 'High Wind',
      badgeClass: 'bg-teal-50 text-teal-700 border-teal-200',
      iconColor: 'text-teal-600',
    };
  }
  if (rain >= 20 || humidity >= 75) {
    return {
      Icon: CloudSun,
      label: 'Partly Cloudy',
      badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      iconColor: 'text-indigo-600',
    };
  }
  return {
    Icon: Sun,
    label: 'Clear Sky',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
    iconColor: 'text-amber-500',
  };
}

export const WeatherVisualBadge = ({ call, compact = false }) => {
  const rain = Number(call?.weather_rainfall ?? 0);
  const wind = Number(call?.weather_windspeed ?? 0);
  const humidity = Number(call?.weather_humidity ?? 0);
  const rawTemp = String(call?.weather_temp ?? call?.temperature ?? '')
    .replace('°C', '')
    .trim();

  if (!rawTemp && call?.weather_rainfall == null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 italic">
        No weather data
      </span>
    );
  }

  const { Icon, label, badgeClass, iconColor } = getWeatherVisualMeta(rain, wind, humidity);

  const tempParts = rawTemp.split('-').map((t) => parseFloat(t));
  const hasRange = tempParts.length === 2 && !isNaN(tempParts[0]) && !isNaN(tempParts[1]);

  if (compact) {
    return (
      <div className="flex items-center gap-2.5 whitespace-nowrap min-w-0">
        <div
          title={label}
          className={`w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 shadow-2xs ${badgeClass}`}
        >
          <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
        </div>
        <div className="min-w-0 flex flex-col justify-center">
          <div className="flex items-center gap-2 whitespace-nowrap">
            <span className="font-bold text-slate-900 text-xs font-mono tabular-nums whitespace-nowrap min-w-[84px] inline-block">
              {rawTemp ? `${rawTemp}°C` : '—'}
            </span>
            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border whitespace-nowrap shrink-0 ${badgeClass}`}>
              {label}
            </span>
          </div>
          <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5 font-mono tabular-nums whitespace-nowrap">
            <span className={`inline-flex items-center gap-0.5 min-w-[36px] ${rain >= 50 ? 'text-sky-700 font-bold' : ''}`}>
              <CloudRain className="w-3 h-3 text-sky-500 shrink-0" />
              <span>{rain}%</span>
            </span>
            <span className={`inline-flex items-center gap-0.5 min-w-[58px] ${wind >= 25 ? 'text-amber-700 font-bold' : ''}`}>
              <Wind className="w-3 h-3 text-slate-400 shrink-0" />
              <span>{wind}km/h</span>
            </span>
            <span className="inline-flex items-center gap-0.5 min-w-[36px]">
              <Droplets className="w-3 h-3 text-blue-400 shrink-0" />
              <span>{humidity}%</span>
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-5 rounded-2xl bg-white border border-slate-200/80 space-y-4 shadow-2xs">
      {/* Header: Grounded Source & High-Level Agronomic Impact (No Duplicate Temperature) */}
      <div className="flex items-center justify-between gap-3 flex-wrap sm:flex-nowrap">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-10 h-10 rounded-xl border flex items-center justify-center shadow-2xs shrink-0 ${badgeClass}`}>
            <Icon className={`w-5 h-5 ${iconColor}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-900 truncate">{label}</span>
              <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                {call.weather_source || 'Open-Meteo'}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5 truncate">
              4-Parameter Meteorological Grounding
            </p>
          </div>
        </div>

        {/* Top-Right: High-level Weather Status Verdict (NO duplicate temperature) */}
        <div className="shrink-0">
          {rain >= 50 ? (
            <div className="px-3 py-1.5 rounded-xl bg-sky-50 border border-sky-200 text-sky-800 flex items-center gap-2 shadow-2xs">
              <CloudRain className="w-4 h-4 text-sky-600 shrink-0" />
              <div className="text-right">
                <div className="text-xs font-bold leading-tight">Rain Caution Active</div>
                <div className="text-[10px] text-sky-600 font-medium">Significant rainfall expected</div>
              </div>
            </div>
          ) : wind >= 25 ? (
            <div className="px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 flex items-center gap-2 shadow-2xs">
              <Wind className="w-4 h-4 text-amber-600 shrink-0" />
              <div className="text-right">
                <div className="text-xs font-bold leading-tight">Wind Advisory Active</div>
                <div className="text-[10px] text-amber-600 font-medium">Elevated wind conditions</div>
              </div>
            </div>
          ) : (
            <div className="px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-center gap-2 shadow-2xs">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <div className="text-right">
                <div className="text-xs font-bold leading-tight">Clear Weather Window</div>
                <div className="text-[10px] text-emerald-600 font-medium">Favorable weather conditions</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 4 Meteorological Parameter Cards (Richly Visualized with Range Gauges, Stage Bars & Fill Meters) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
        {/* 1. Temperature Card */}
        <div className="p-3 rounded-xl bg-slate-50/80 border border-slate-200/80 min-w-0 overflow-hidden flex flex-col justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-wider min-w-0">
              <Thermometer className="w-3.5 h-3.5 text-amber-500 shrink-0" />
              <span className="truncate">Temperature</span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1.5 min-w-0">
              <span className="font-mono font-bold text-sm sm:text-base text-slate-900 tabular-nums truncate">
                {rawTemp ? `${rawTemp}°C` : 'N/A'}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-100 text-amber-800 shrink-0">
                {hasRange ? (tempParts[1] >= 34 ? 'Hot' : (tempParts[1] >= 28 ? 'Warm' : 'Mild')) : 'Current'}
              </span>
            </div>
          </div>

          <div className="mt-2.5 space-y-1">
            <div className="relative h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
              {hasRange ? (
                <div
                  className="absolute top-0 bottom-0 rounded-full bg-gradient-to-r from-amber-400 to-orange-500"
                  style={{
                    left: `${Math.max(0, Math.min(100, ((tempParts[0] - 10) / 35) * 100))}%`,
                    width: `${Math.max(15, Math.min(100, ((tempParts[1] - tempParts[0]) / 35) * 100))}%`,
                  }}
                />
              ) : (
                <div
                  className="h-full rounded-full bg-amber-500"
                  style={{ width: `${Math.min(100, Math.max(20, (parseFloat(rawTemp) / 45) * 100))}%` }}
                />
              )}
            </div>
            <div className="flex justify-between text-[9px] font-mono text-slate-400">
              <span>{hasRange ? `${tempParts[0]}°` : '10°'}</span>
              <span>{hasRange ? `${tempParts[1]}°` : '45°'}</span>
            </div>
          </div>
        </div>

        {/* 2. Wind Speed Card */}
        <div className={`p-3 rounded-xl border min-w-0 overflow-hidden flex flex-col justify-between ${wind >= 25 ? 'bg-amber-50/70 border-amber-200' : 'bg-slate-50/80 border-slate-200/80'
          }`}>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-wider min-w-0">
              <Wind className="w-3.5 h-3.5 text-teal-600 shrink-0" />
              <span className="truncate">Wind Speed</span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1.5 min-w-0">
              <span className="font-mono font-bold text-sm sm:text-base text-slate-900 tabular-nums truncate">
                {call.weather_windspeed != null ? `${wind} km/h` : 'N/A'}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0 ${wind >= 25 ? 'bg-amber-100 text-amber-800' : 'bg-slate-200/70 text-slate-700'
                }`}>
                {wind >= 25 ? 'Gusty' : (wind >= 15 ? 'Moderate' : 'Calm')}
              </span>
            </div>
          </div>

          <div className="mt-2.5 space-y-1">
            <div className="grid grid-cols-3 gap-1">
              <div className={`h-1.5 rounded-full transition-all ${wind > 0 ? (wind >= 25 ? 'bg-amber-400' : 'bg-teal-500') : 'bg-slate-200'}`} />
              <div className={`h-1.5 rounded-full transition-all ${wind >= 15 ? (wind >= 25 ? 'bg-amber-500' : 'bg-teal-600') : 'bg-slate-200'}`} />
              <div className={`h-1.5 rounded-full transition-all ${wind >= 25 ? 'bg-rose-500' : 'bg-slate-200'}`} />
            </div>
            <div className="flex justify-between text-[9px] font-mono text-slate-400">
              <span>Calm</span>
              <span>Gusty</span>
            </div>
          </div>
        </div>

        {/* 3. Rain Chance Card */}
        <div className={`p-3 rounded-xl border min-w-0 overflow-hidden flex flex-col justify-between ${rain >= 50 ? 'bg-sky-50/80 border-sky-200' : 'bg-slate-50/80 border-slate-200/80'
          }`}>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-wider min-w-0">
              <CloudRain className="w-3.5 h-3.5 text-sky-600 shrink-0" />
              <span className="truncate">Rain Chance</span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1.5 min-w-0">
              <span className="font-mono font-bold text-sm sm:text-base text-slate-900 tabular-nums truncate">
                {call.weather_rainfall != null ? `${rain}%` : 'N/A'}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0 ${rain >= 50 ? 'bg-sky-100 text-sky-800' : 'bg-slate-200/70 text-slate-700'
                }`}>
                {rain >= 50 ? 'High Risk' : (rain >= 20 ? 'Moderate' : 'Low')}
              </span>
            </div>
          </div>

          <div className="mt-2.5 space-y-1">
            <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${rain >= 50 ? 'bg-sky-500' : (rain >= 20 ? 'bg-sky-400' : 'bg-slate-400')
                  }`}
                style={{ width: `${Math.min(100, Math.max(5, rain))}%` }}
              />
            </div>
            <div className="flex justify-between text-[9px] font-mono text-slate-400">
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>
        </div>

        {/* 4. Humidity Card */}
        <div className="p-3 rounded-xl bg-slate-50/80 border border-slate-200/80 min-w-0 overflow-hidden flex flex-col justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-wider min-w-0">
              <Droplets className="w-3.5 h-3.5 text-blue-500 shrink-0" />
              <span className="truncate">Humidity</span>
            </div>
            <div className="flex items-baseline justify-between gap-1 mt-1.5 min-w-0">
              <span className="font-mono font-bold text-sm sm:text-base text-slate-900 tabular-nums truncate">
                {call.weather_humidity != null ? `${humidity}%` : 'N/A'}
              </span>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold shrink-0 ${humidity >= 75 ? 'bg-blue-100 text-blue-800' : 'bg-slate-200/70 text-slate-700'
                }`}>
                {humidity >= 75 ? 'Elevated' : (humidity >= 50 ? 'Balanced' : 'Low')}
              </span>
            </div>
          </div>

          <div className="mt-2.5 space-y-1">
            <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${humidity >= 75 ? 'bg-blue-600' : 'bg-blue-400'
                  }`}
                style={{ width: `${Math.min(100, Math.max(5, humidity))}%` }}
              />
            </div>
            <div className="flex justify-between text-[9px] font-mono text-slate-400">
              <span>0%</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Pictorial Weather & Traffic Pulse Banner for the top of the Overview tab.
 */
export const DashboardWeatherPulse = ({ callLogs = [] }) => {
  const pulse = useMemo(() => {
    const withWeather = callLogs.filter((c) => c.weather_rainfall != null || c.weather_temp != null);
    const inboundCount = callLogs.filter((c) => callDirections(c).incoming).length;
    const outboundCount = callLogs.filter((c) => callDirections(c).outgoing).length;

    if (withWeather.length === 0) {
      return { hasWeather: false, inboundCount, outboundCount };
    }

    let rainAlerts = 0;
    let highWindAlerts = 0;
    let clearCount = 0;
    let sumRain = 0;
    let sumWind = 0;
    let sumHumidity = 0;

    withWeather.forEach((c) => {
      const r = Number(c.weather_rainfall ?? 0);
      const w = Number(c.weather_windspeed ?? 0);
      const h = Number(c.weather_humidity ?? 0);
      sumRain += r;
      sumWind += w;
      sumHumidity += h;
      if (r >= 50) rainAlerts += 1;
      else if (w >= 25) highWindAlerts += 1;
      else clearCount += 1;
    });

    const n = withWeather.length;
    return {
      hasWeather: true,
      total: n,
      rainAlerts,
      highWindAlerts,
      clearCount,
      avgRain: Math.round(sumRain / n),
      avgWind: Math.round(sumWind / n),
      avgHumidity: Math.round(sumHumidity / n),
      inboundCount,
      outboundCount,
    };
  }, [callLogs]);

  if (!pulse.hasWeather && callLogs.length === 0) return null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-stretch">
      {/* Pictorial Regional Weather Overview */}
      {pulse.hasWeather && (
        <div className="lg:col-span-8 bg-white border border-slate-200/80 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-2xs h-full">
          <div className="flex items-center gap-3">
            <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${pulse.rainAlerts > 0
                ? 'bg-sky-50 text-sky-600 border-sky-200'
                : 'bg-amber-50 text-amber-600 border-amber-200'
              }`}>
              {pulse.rainAlerts > 0 ? <CloudRain className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </div>
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Regional Weather Pulse
              </div>
              <div className="text-xs font-bold text-slate-900 mt-0.5 flex flex-wrap items-center gap-2">
                {pulse.rainAlerts > 0 && (
                  <span className="inline-flex items-center gap-1 text-sky-700">
                    <AlertTriangle className="w-3.5 h-3.5 text-sky-600" />
                    <span className="font-mono tabular-nums">{pulse.rainAlerts}</span> Rain Alert{pulse.rainAlerts > 1 ? 's' : ''}
                  </span>
                )}
                {pulse.highWindAlerts > 0 && (
                  <span className="inline-flex items-center gap-1 text-amber-700">
                    <Wind className="w-3.5 h-3.5 text-amber-600" />
                    <span className="font-mono tabular-nums">{pulse.highWindAlerts}</span> High Wind
                  </span>
                )}
                <span className="text-slate-600 font-medium">
                  <span className="font-mono tabular-nums">{pulse.clearCount}</span> Clear / Normal
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 text-xs font-mono tabular-nums">
            <div className="px-2.5 py-1.5 rounded-xl bg-slate-50 border border-slate-200/70 flex items-center gap-1.5">
              <CloudRain className="w-3.5 h-3.5 text-sky-600" />
              <span className="font-bold text-slate-800">{pulse.avgRain}%</span>
              <span className="text-[10px] text-slate-500 font-sans">Avg Rain</span>
            </div>
            <div className="px-2.5 py-1.5 rounded-xl bg-slate-50 border border-slate-200/70 flex items-center gap-1.5">
              <Wind className="w-3.5 h-3.5 text-teal-600" />
              <span className="font-bold text-slate-800">{pulse.avgWind} km/h</span>
            </div>
            <div className="hidden sm:flex px-2.5 py-1.5 rounded-xl bg-slate-50 border border-slate-200/70 items-center gap-1.5">
              <Droplets className="w-3.5 h-3.5 text-blue-500" />
              <span className="font-bold text-slate-800">{pulse.avgHumidity}%</span>
            </div>
          </div>
        </div>
      )}

      {/* Incoming vs. Outgoing Traffic Split */}
      <div className={`${pulse.hasWeather ? 'lg:col-span-4' : 'lg:col-span-12'} bg-white border border-slate-200/80 rounded-2xl p-4 flex items-center justify-between gap-3 shadow-2xs h-full`}>
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Call Direction Split
          </div>
          <div className="text-xs font-bold text-slate-900 mt-0.5">
            <span className="font-mono tabular-nums">{pulse.outboundCount}</span> Outgoing · <span className="font-mono tabular-nums">{pulse.inboundCount}</span> Incoming
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono tabular-nums font-bold">
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-slate-100 text-trust-navy border border-slate-200">
            ↗ {pulse.outboundCount}
          </span>
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200">
            ↙ {pulse.inboundCount}
          </span>
        </div>
      </div>
    </div>
  );
};

export default WeatherVisualBadge;
