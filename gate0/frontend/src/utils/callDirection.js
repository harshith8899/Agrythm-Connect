// Which way a call went. A farmer's day can hold both: our own call and, later, the farmer ringing us.
const isIn = (d) => ['inbound', 'incoming'].includes(String(d || '').toLowerCase());

/** { outgoing, incoming }: true for each kind of call the row holds. A row is never neither. */
export function callDirections(call) {
  if (!call) return { outgoing: true, incoming: false };
  const attempts = Array.isArray(call.attempts_log) ? call.attempts_log : [];
  if (String(call.call_id || '').startsWith('IN-')) return { outgoing: false, incoming: true };
  if (attempts.length > 0) {
    const incoming = attempts.some((a) => a.incoming || isIn(a.direction));
    const outgoing = attempts.some((a) => !(a.incoming || isIn(a.direction)));
    if (incoming || outgoing) return { outgoing, incoming };
  }
  const incoming = isIn(call.direction) || Boolean(call.has_inbound_callback);
  return { outgoing: !incoming, incoming };
}
