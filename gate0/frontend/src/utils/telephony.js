/**
 * Sarvam Telephony & Voice AI Pricing Model:
 * 1. Voice Agent Usage: ₹3.50 per started 60-second minute of connected calls.
 * 2. Advisory Messages: ₹0.20 per advisory SMS / WhatsApp message sent to farmers.
 * 3. Telephony Number Rental: ₹59.00 fixed monthly DID rental (no pulse carriage fees).
 */
export const TELEPHONY_MONTHLY_RENT = 59.0;
export const VOICE_AGENT_RATE_PER_MIN = 3.5;
export const SMS_MESSAGE_RATE = 0.20;

export const TELEPHONY_PULSE_SECONDS = 30;
export const TELEPHONY_PULSE_RATE = 0.2;

/** Started 30-second pulses of a call that connected; 0 when there is no talk time. */
export const pulsesFor = (seconds) => {
  const s = Number(seconds);
  return Number.isFinite(s) && s > 0 ? Math.ceil(s / TELEPHONY_PULSE_SECONDS) : 0;
};

/** The telephony amount in rupees for a number of pulses (legacy/compatibility). */
export const telephonyAmount = (pulses) => Math.round(Number(pulses || 0) * TELEPHONY_PULSE_RATE * 100) / 100;

