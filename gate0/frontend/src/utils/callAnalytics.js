/**
 * Utility functions for voice call analytics, date matching, and farmer engagement telemetry.
 */

/**
 * Check if a call timestamp matches today's date in local time.
 * Supports ISO, YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, MM/DD/YYYY, relative strings ('today', 'just now'), and unix epochs.
 * @param {string|number|Date} timestamp 
 * @returns {boolean}
 */
export const isCallToday = (timestamp) => {
  if (!timestamp && timestamp !== 0) return false;

  const tsStr = String(timestamp).trim();
  if (!tsStr) return false;

  const lower = tsStr.toLowerCase();
  if (lower.includes('today') || lower.includes('just now')) {
    return true;
  }

  const now = new Date();
  const yyyy = now.getFullYear();
  const m = now.getMonth() + 1;
  const d = now.getDate();
  const mm = String(m).padStart(2, '0');
  const dd = String(d).padStart(2, '0');

  // Direct string patterns for today
  if (
    tsStr.includes(`${yyyy}-${mm}-${dd}`) ||
    tsStr.includes(`${dd}/${mm}/${yyyy}`) ||
    tsStr.includes(`${dd}-${mm}-${yyyy}`) ||
    tsStr.includes(`${mm}/${dd}/${yyyy}`) ||
    tsStr.includes(`${d}/${m}/${yyyy}`) ||
    tsStr.includes(`${d}-${m}-${yyyy}`)
  ) {
    return true;
  }

  // Try parsing with Date constructor
  const parsed = new Date(tsStr);
  if (!isNaN(parsed.getTime())) {
    return (
      parsed.getFullYear() === yyyy &&
      parsed.getMonth() === now.getMonth() &&
      parsed.getDate() === d
    );
  }

  // Numeric epoch timestamp check (milliseconds or seconds)
  const num = Number(tsStr);
  if (!isNaN(num) && num > 1000000000) {
    const epochDate = new Date(num > 100000000000 ? num : num * 1000);
    if (!isNaN(epochDate.getTime())) {
      return (
        epochDate.getFullYear() === yyyy &&
        epochDate.getMonth() === now.getMonth() &&
        epochDate.getDate() === d
      );
    }
  }

  return false;
};

/**
 * Check if a call timestamp matches yesterday's date in local time.
 * @param {string|number|Date} timestamp 
 * @returns {boolean}
 */
export const isCallYesterday = (timestamp) => {
  if (!timestamp && timestamp !== 0) return false;

  const tsStr = String(timestamp).trim();
  if (!tsStr) return false;

  const lower = tsStr.toLowerCase();
  if (lower.includes('yesterday')) {
    return true;
  }

  const d = new Date();
  d.setDate(d.getDate() - 1);
  const yyyy = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const mm = String(m).padStart(2, '0');
  const dd = String(day).padStart(2, '0');

  if (
    tsStr.includes(`${yyyy}-${mm}-${dd}`) ||
    tsStr.includes(`${dd}/${mm}/${yyyy}`) ||
    tsStr.includes(`${dd}-${mm}-${yyyy}`) ||
    tsStr.includes(`${mm}/${dd}/${yyyy}`) ||
    tsStr.includes(`${day}/${m}/${yyyy}`) ||
    tsStr.includes(`${day}-${m}-${yyyy}`)
  ) {
    return true;
  }

  const parsed = new Date(tsStr);
  if (!isNaN(parsed.getTime())) {
    return (
      parsed.getFullYear() === yyyy &&
      parsed.getMonth() === d.getMonth() &&
      parsed.getDate() === day
    );
  }

  return false;
};

/**
 * Check if a date string in YYYY-MM-DD format matches yesterday's local date.
 * @param {string} dateStr 
 * @returns {boolean}
 */
export const isYesterdayDateStr = (dateStr) => {
  if (!dateStr) return false;
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return String(dateStr).trim() === `${yyyy}-${mm}-${dd}`;
};

/**
 * Check if a date string in YYYY-MM-DD format matches today's local date.
 * @param {string} dateStr 
 * @returns {boolean}
 */
export const isTodayDateStr = (dateStr) => {
  if (!dateStr) return false;
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return String(dateStr).trim() === `${yyyy}-${mm}-${dd}`;
};

/**
 * Format a YYYY-MM-DD date string into a readable label (e.g., '24 Oct 2026').
 * @param {string} dateStr 
 * @returns {string}
 */
export const formatDateForDisplay = (dateStr) => {
  if (!dateStr) return '';
  const parts = String(dateStr).split('-');
  if (parts.length === 3) {
    const [year, month, day] = parts;
    const d = new Date(parseInt(year, 10), parseInt(month, 10) - 1, parseInt(day, 10));
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    }
  }
  return String(dateStr);
};

/**
 * Check if a call timestamp matches a target date string formatted as YYYY-MM-DD.
 * @param {string|number|Date} timestamp 
 * @param {string} targetDateStr - Formatted as 'YYYY-MM-DD'
 * @returns {boolean}
 */
export const isCallOnDate = (timestamp, targetDateStr) => {
  if (!timestamp || !targetDateStr) return false;

  const tsStr = String(timestamp).trim();
  if (!tsStr) return false;

  const parts = targetDateStr.split('-');
  if (parts.length !== 3) return false;

  const [year, month, day] = parts;
  const dInt = parseInt(day, 10);
  const mInt = parseInt(month, 10);

  if (
    tsStr.includes(targetDateStr) ||
    tsStr.includes(`${day}/${month}/${year}`) ||
    tsStr.includes(`${day}-${month}-${year}`) ||
    tsStr.includes(`${month}/${day}/${year}`) ||
    tsStr.includes(`${dInt}/${mInt}/${year}`) ||
    tsStr.includes(`${dInt}-${mInt}-${year}`)
  ) {
    return true;
  }

  const parsed = new Date(tsStr);
  if (!isNaN(parsed.getTime())) {
    return (
      parsed.getFullYear() === parseInt(year, 10) &&
      parsed.getMonth() === mInt - 1 &&
      parsed.getDate() === dInt
    );
  }

  return false;
};

/**
 * Determines whether a farmer picked up the call and engaged/talked in the conversation.
 * Returns true if duration is > 0 or status confirms completed/delivered engagement,
 * and false if the call was missed, unanswered, busy, or failed.
 * @param {object} call - Call record object
 * @returns {boolean}
 */
export const didFarmerPickUpAndTalk = (call) => {
  if (!call) return false;

  const rawStatus = String(call.call_status || '').trim().toLowerCase();

  // Known statuses indicating the farmer was not reached / did not pick up
  const notReachedKeywords = [
    'no answer',
    'not answered',
    'missed',
    'failed',
    'busy',
    'unanswered',
    'declined',
    'rejected',
    'cancelled',
    'canceled',
    'not reached',
    'ringing',
  ];

  if (notReachedKeywords.some(keyword => rawStatus.includes(keyword))) {
    return false;
  }

  // Parse duration
  const durationSec = parseInt(call.duration_sec, 10);

  // If duration is explicitly 0 seconds, they did not talk
  if (!isNaN(durationSec) && durationSec === 0) {
    return false;
  }

  // If duration is positive (> 0 seconds), the farmer answered and talked
  if (!isNaN(durationSec) && durationSec > 0) {
    return true;
  }

  // If duration column is missing or unpopulated, check for successful delivery/engagement statuses
  const positiveStatuses = [
    'delivered',
    'completed',
    'requires escalation',
    'answered',
    'connected',
    'success',
  ];

  if (positiveStatuses.some(status => rawStatus.includes(status))) {
    return true;
  }

  // If transcript preview or advisory summary exists with conversation content
  if (
    (call.transcript_preview && String(call.transcript_preview).trim().length > 10) ||
    (call.advisory_summary && String(call.advisory_summary).trim().length > 10)
  ) {
    return true;
  }

  return false;
};

/**
 * Extracts pure date value from a call record.
 * Supports separate columns ('date', 'call_date', 'Date') or extracts from 'call_timestamp'.
 * @param {object} call 
 * @returns {string}
 */
export const getCallDate = (call) => {
  if (!call) return '';
  if (call.call_date) return String(call.call_date).trim();
  if (call.date) return String(call.date).trim();
  if (call.Date) return String(call.Date).trim();
  if (call.Call_Date) return String(call.Call_Date).trim();
  const ts = call.call_timestamp ?? call.timestamp ?? call.created_at ?? '';
  return String(ts).trim();
};

/**
 * Extracts pure time value from a call record.
 * Supports separate columns ('time', 'call_time', 'Time').
 * @param {object} call 
 * @returns {string}
 */
export const getCallTime = (call) => {
  if (!call) return '';
  if (call.call_time) return String(call.call_time).trim();
  if (call.time) return String(call.time).trim();
  if (call.Time) return String(call.Time).trim();
  if (call.Call_Time) return String(call.Call_Time).trim();
  return '';
};

/**
 * Formats date and time nicely for display in tables and inspection drawers.
 * @param {object} call 
 * @returns {string}
 */
export const getDisplayDateTime = (call) => {
  if (!call) return 'Just now';
  const d = call.call_date || call.date || call.Date || '';
  const t = call.call_time || call.time || call.Time || '';
  if (d && t) return `${d} • ${t}`;
  if (d) return String(d);
  if (t) return String(t);
  return call.call_timestamp || call.timestamp || 'Just now';
};

/**
 * Extracts timestamp or date value from a call record with column name fallbacks.
 * Looks for date, call_date, call_timestamp, timestamp, or created_at.
 * @param {object} call 
 * @returns {string|number}
 */
export const getCallTimestamp = (call) => {
  return getCallDate(call);
};

/**
 * Computes comprehensive 'Farmers Reached' metrics for today, yesterday, and custom selected dates.
 * Follows rule:
 * - For yesterday's date: mentions "yesterday"
 * - For other dates: mentions the date (e.g. '24 Oct 2026')
 * - For today's date: mentions "today"
 * @param {Array} callLogs - Enriched call records
 * @param {Array} farmers - Farmer records from Sheet 1
 * @param {object} options - Filter options { dateFilter, customDate }
 * @returns {object}
 */
export const getFarmersReachedMetrics = (callLogs = [], farmers = [], options = {}) => {
  const { dateFilter = 'all', customDate = '' } = options;

  let talkedAllDatesCallCount = 0;
  const uniqueFarmersAllDatesSet = new Set();

  let talkedTodayCallCount = 0;
  const uniqueFarmersTodaySet = new Set();

  let talkedYesterdayCallCount = 0;
  const uniqueFarmersYesterdaySet = new Set();

  let talkedCustomDateCallCount = 0;
  const uniqueFarmersCustomDateSet = new Set();

  callLogs.forEach(call => {
    if (!didFarmerPickUpAndTalk(call)) return;

    const id = call.farmer_id
      ? String(call.farmer_id).trim()
      : (call.phone_number
        ? String(call.phone_number).trim()
        : (call.farmer_name ? String(call.farmer_name).trim() : call.call_id));
    if (!id) return;

    talkedAllDatesCallCount++;
    uniqueFarmersAllDatesSet.add(id);

    const ts = getCallTimestamp(call);

    if (isCallToday(ts)) {
      talkedTodayCallCount++;
      uniqueFarmersTodaySet.add(id);
    }

    if (isCallYesterday(ts)) {
      talkedYesterdayCallCount++;
      uniqueFarmersYesterdaySet.add(id);
    }

    if (customDate && isCallOnDate(ts, customDate)) {
      talkedCustomDateCallCount++;
      uniqueFarmersCustomDateSet.add(id);
    }
  });

  const farmersReachedAllDates = uniqueFarmersAllDatesSet.size;
  const farmersReachedToday = uniqueFarmersTodaySet.size;
  const farmersReachedYesterday = uniqueFarmersYesterdaySet.size;
  const farmersReachedCustomDate = uniqueFarmersCustomDateSet.size;

  // Determine active context
  const isAllDates = dateFilter === 'all' && !customDate;
  const isYesterday = dateFilter === 'yesterday' || isYesterdayDateStr(customDate);
  const isToday = dateFilter === 'today' || (dateFilter !== 'all' && isTodayDateStr(customDate));
  const isCustomOtherDate = Boolean(customDate) && !isYesterday && !isToday && !isAllDates;

  let activeCount = 0;
  let subtitle = '';
  let badge = '';

  if (isAllDates) {
    activeCount = farmersReachedAllDates;
    subtitle = activeCount === 1
      ? '1 farmer picked up & talked across all dates'
      : `${activeCount} picked up & talked across all dates`;
    badge = 'All Dates';
  } else if (isYesterday) {
    activeCount = farmersReachedYesterday;
    subtitle = activeCount === 1
      ? '1 farmer picked up & talked yesterday'
      : `${activeCount} picked up & talked yesterday`;
    badge = 'Yesterday';
  } else if (isToday) {
    activeCount = farmersReachedToday;
    subtitle = activeCount === 1
      ? '1 farmer picked up & talked today'
      : `${activeCount} picked up & talked today`;
    badge = activeCount > 0 ? 'Talked Today' : 'Today';
  } else if (isCustomOtherDate) {
    activeCount = farmersReachedCustomDate;
    const formattedDate = formatDateForDisplay(customDate);
    subtitle = activeCount === 1
      ? `1 farmer picked up & talked on ${formattedDate}`
      : `${activeCount} picked up & talked on ${formattedDate}`;
    badge = formattedDate;
  } else {
    activeCount = farmersReachedAllDates;
    subtitle = `${activeCount} picked up & talked across all dates`;
    badge = 'All Dates';
  }

  return {
    farmersReached: activeCount,
    farmersReachedAllDates,
    farmersReachedToday,
    farmersReachedYesterday,
    farmersReachedCustomDate,
    talkedAllDatesCallCount,
    talkedTodayCallCount,
    talkedYesterdayCallCount,
    talkedCustomDateCallCount,
    subtitle,
    badge,
    totalFarmers: farmers.length,
    isAllDates,
    isYesterday,
    isToday,
    isCustomOtherDate,
  };
};
