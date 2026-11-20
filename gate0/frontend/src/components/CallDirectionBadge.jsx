import React from 'react';
import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';

export const CallDirectionBadge = ({ direction = 'outgoing', callId = '', compact = false }) => {
  const isInbound =
    ['inbound', 'incoming'].includes(String(direction).toLowerCase()) ||
    String(callId).startsWith('IN-');

  if (compact) {
    return isInbound ? (
      <span
        title="Incoming Call (Farmer rang back)"
        className="inline-flex items-center justify-center w-5 h-5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 shrink-0"
      >
        <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-600" />
      </span>
    ) : (
      <span
        title="Outgoing Call (System initiated)"
        className="inline-flex items-center justify-center w-5 h-5 rounded-md bg-slate-100 text-trust-navy border border-slate-200 shrink-0"
      >
        <ArrowUpRight className="w-3.5 h-3.5 text-trust-navy" />
      </span>
    );
  }

  return isInbound ? (
    <span
      title="Incoming Call (Farmer rang back)"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"
    >
      <ArrowDownLeft className="w-3 h-3 text-emerald-600 shrink-0" />
      <span>Incoming</span>
    </span>
  ) : (
    <span
      title="Outgoing Call (System initiated)"
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200"
    >
      <ArrowUpRight className="w-3 h-3 text-trust-navy shrink-0" />
      <span>Outgoing</span>
    </span>
  );
};

export default CallDirectionBadge;
