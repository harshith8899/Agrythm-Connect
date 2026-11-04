import React from 'react';
import { 
  ShieldCheck, 
  Cpu, 
  CheckCircle2, 
  Languages, 
  ExternalLink 
} from 'lucide-react';
import { GOOGLE_SHEETS_CONFIG } from '../utils/constants';

export const TrustAiAnalyticsView = ({ callLogs = [] }) => {
  // Compute Language Distribution from real call logs
  const langCounts = {};
  let totalValidCalls = 0;

  callLogs.forEach(c => {
    const lang = c.primary_language || 'Unspecified';
    langCounts[lang] = (langCounts[lang] || 0) + 1;
    totalValidCalls++;
  });

  const languageDistribution = Object.entries(langCounts).map(([lang, count]) => {
    const pct = totalValidCalls > 0 ? Math.round((count / totalValidCalls) * 100) : 0;
    return { lang, count: `${count} call${count > 1 ? 's' : ''}`, pct };
  });

  // Calculate actual average AI confidence
  const confScores = callLogs
    .map(c => parseFloat(String(c.ai_confidence_score || '').replace('%', '')))
    .filter(s => !isNaN(s));

  const avgConfidence = confScores.length > 0
    ? `${(confScores.reduce((a, b) => a + b, 0) / confScores.length).toFixed(1)}%`
    : 'N/A';

  if (callLogs.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center space-y-4">
        <div className="w-14 h-14 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mx-auto">
          <ShieldCheck className="w-7 h-7 text-trust-navy" />
        </div>
        <div>
          <h3 className="text-base font-bold text-slate-900">
            No Call Records for AI Analytics Yet
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
            Trust AI confidence scores, language distributions, and automated safety checks will compute purely from the <code>ai_confidence_score</code> and <code>primary_language</code> recorded in Google Sheet 2.
          </p>
        </div>
        <div className="pt-2">
          <a
            href={`https://docs.google.com/spreadsheets/d/${GOOGLE_SHEETS_CONFIG.callLogsSheetId}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-trust-navy text-white text-xs font-semibold hover:bg-slate-800 transition-colors"
          >
            <span>Open Google Sheet 2</span>
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
            Trust AI Intelligence
          </span>
          <h2 className="text-xl font-bold text-slate-900">
            Advisory Verification & Model Health
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Computed from {callLogs.length} active records in Google Sheet 2
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-50 text-trust-green border border-emerald-200 text-xs font-bold">
            <ShieldCheck className="w-4 h-4" />
            Avg AI Confidence: {avgConfidence}
          </span>
        </div>
      </div>

      {/* Model Benchmark Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-2 shadow-2xs">
          <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Total Evaluated Calls
          </span>
          <div className="text-2xl font-bold text-slate-900">{callLogs.length}</div>
          <p className="text-[11px] text-slate-500 leading-tight">Synced directly from Sheet 2</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-2 shadow-2xs">
          <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Average Confidence Score
          </span>
          <div className="text-2xl font-bold text-slate-900">{avgConfidence}</div>
          <p className="text-[11px] text-slate-500 leading-tight">Derived from ai_confidence_score column</p>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 space-y-2 shadow-2xs">
          <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            Languages Detected
          </span>
          <div className="text-2xl font-bold text-slate-900">{languageDistribution.length}</div>
          <p className="text-[11px] text-slate-500 leading-tight">Distinct dialects in active records</p>
        </div>
      </div>

      {/* Language Distribution & Model Architecture */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Dialect Distribution */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 md:p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
              Multilingual Voice Distribution
            </span>
            <Languages className="w-4 h-4 text-slate-400" />
          </div>
          <h3 className="text-base font-bold text-slate-900">
            Language Breakdown ({languageDistribution.length})
          </h3>

          <div className="space-y-3 pt-2">
            {languageDistribution.map((item, i) => (
              <div key={i} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-800">{item.lang}</span>
                  <span className="text-slate-500">{item.count} ({item.pct}%)</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-trust-navy rounded-full transition-all duration-500"
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Safety & Grounding Guardrails */}
        <div className="bg-white rounded-2xl border border-slate-200/80 p-5 md:p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold tracking-wider text-slate-500 uppercase">
              Field-First Guardrails
            </span>
            <Cpu className="w-4 h-4 text-slate-400" />
          </div>
          <h3 className="text-base font-bold text-slate-900">
            Automated Agricultural Safety Checks
          </h3>

          <div className="space-y-3 pt-1">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/60 flex items-start gap-3">
              <CheckCircle2 className="w-4 h-4 text-trust-green shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-bold text-slate-900">Rain & Foliar Spray Prevention</div>
                <div className="text-[11px] text-slate-500 leading-relaxed mt-0.5">
                  Voice Agent blocks foliar pesticide recommendations if rainfall probability in the sheet exceeds 60%.
                </div>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/60 flex items-start gap-3">
              <CheckCircle2 className="w-4 h-4 text-trust-green shrink-0 mt-0.5" />
              <div>
                <div className="text-xs font-bold text-slate-900">Live Sheet Sync Verification</div>
                <div className="text-[11px] text-slate-500 leading-relaxed mt-0.5">
                  Metrics refresh automatically with each background poll or manual refresh.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
