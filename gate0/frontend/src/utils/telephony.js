/**
 * Telephony on Sarvam's own number, counted the way Sarvam bills it (docs.sarvam.ai/voice-agents/pricing): Rs 0.20 per started
 * 30-second pulse of a connected call, before GST, the same on every plan. A 45-second call is 2 pulses. Calls that were not
 * picked up, were busy or failed cost nothing. (Agent minutes are separate: started 60-second minutes at the plan's rate.)
 */
export const TELEPHONY_PULSE_SECONDS = 30;
export const TELEPHONY_PULSE_RATE = 0.2;

/** Started 30-second pulses of a call that connected; 0 when there is no talk time. */
export const pulsesFor = (seconds) => {
  const s = Number(seconds);
  return Number.isFinite(s) && s > 0 ? Math.ceil(s / TELEPHONY_PULSE_SECONDS) : 0;
};

/** The telephony amount in rupees for a number of pulses. */
export const telephonyAmount = (pulses) => Math.round(Number(pulses || 0) * TELEPHONY_PULSE_RATE * 100) / 100;
