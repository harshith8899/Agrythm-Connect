import React from 'react';
import { PhoneIncoming, PhoneOutgoing } from 'lucide-react';
import { callDirections } from '../utils/callDirection';

const KINDS = {
  incoming: {
    label: 'Incoming',
    title: 'Incoming call: the farmer rang us',
    Icon: PhoneIncoming,
    box: 'bg-emerald-50 text-emerald-700 border-emerald-300',
  },
  outgoing: {
    label: 'Outgoing',
    title: 'Outgoing call: we rang the farmer',
    Icon: PhoneOutgoing,
    box: 'bg-blue-50 text-blue-700 border-blue-300',
  },
};

/**
 * The mark for the way a call went. Pass the whole call (a day holding both our call and the farmer ringing back shows both),
 * or just `direction` / `callId` for a single call such as one attempt.
 * compact: the icon alone; otherwise the icon with its word.
 */
export const CallDirectionBadge = ({ call, direction = 'outgoing', callId = '', compact = false }) => {
  const dirs = callDirections(call || { direction, call_id: callId });
  const kinds = [dirs.outgoing && 'outgoing', dirs.incoming && 'incoming'].filter(Boolean);
  if (kinds.length === 0) kinds.push('outgoing');

  return (
    <span className="inline-flex items-center gap-1 shrink-0">
      {kinds.map((k) => {
        const { label, title, Icon, box } = KINDS[k];
        return compact ? (
          <span key={k} title={title} aria-label={label}
            className={`inline-flex items-center justify-center w-6 h-6 rounded-md border ${box}`}>
            <Icon className="w-3.5 h-3.5" />
          </span>
        ) : (
          <span key={k} title={title}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${box}`}>
            <Icon className="w-3 h-3 shrink-0" />
            <span>{label}</span>
          </span>
        );
      })}
    </span>
  );
};

export default CallDirectionBadge;
