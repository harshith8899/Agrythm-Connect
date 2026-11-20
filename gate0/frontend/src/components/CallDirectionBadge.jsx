import React from 'react';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';

export const CallDirectionBadge = ({ direction = 'outgoing', compact = false }) => {
  const isInbound = ['inbound', 'incoming'].includes(String(direction).toLowerCase());

  if (compact) {
    // an arrow and a word, so a row says whether we called the farmer or the farmer rang us
    return isInbound ? (
      <span
        title="Incoming call: the farmer rang us"
        className="inline-flex items-center gap-0.5 h-5 px-1.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold shrink-0"
      >
        <ArrowDownLeft className="w-3 h-3 text-emerald-600" />In
      </span>
    ) : (
      <span
        title="Outgoing call: we rang the farmer"
        className="inline-flex items-center gap-0.5 h-5 px-1.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 text-[10px] font-bold shrink-0"
      >
        <ArrowUpRight className="w-3 h-3 text-slate-600" />Out
      </span>
    );
  }

  return isInbound ? (
    <span
      title="Incoming call: the farmer rang us"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"
    >
      <ArrowDownLeft className="w-3 h-3 text-emerald-600 shrink-0" />
      <span>Incoming</span>
    </span>
  ) : (
    <span
      title="Outgoing call: we rang the farmer"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200"
    >
      <ArrowUpRight className="w-3 h-3 text-trust-navy shrink-0" />
      <span>Outgoing</span>
    </span>
  );
};

export default CallDirectionBadge;
