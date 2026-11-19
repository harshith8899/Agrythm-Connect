import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { 
  loadFarmersData, 
  loadCallLogsData, 
  sendCallsNow,
  getDispatcherStatus,
  updateDispatcherStatus,
  confirmDialog,
  isCallOnDate,
  getCallDate,
  getCallTime,
  normalizeLanguage,
  extractWeatherFromMessage,
  maskPhoneNumber
} from '../utils';

// Today's date in the browser's own calendar (YYYY-MM-DD), the default view of the overview
const localToday = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// enabled=false: no request is made (the dashboard is already on screen while the sign-in is still finishing in the background).
export const useVoiceAgentData = ({ enabled = true } = {}) => {
  const [farmers, setFarmers] = useState([]);
  const [callLogs, setCallLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggeringDemo, setTriggeringDemo] = useState(false);
  const [lastSynced, setLastSynced] = useState(null);
  const [syncStatus, setSyncStatus] = useState('syncing');
  const [isBackendOnline, setIsBackendOnline] = useState(true);
  const [hasConnected, setHasConnected] = useState(false);   // the backend has answered at least once
  const [offlineSince, setOfflineSince] = useState(null);     // when it stopped answering (ms)
  const [mountedAt] = useState(() => Date.now());          // when the page started waiting
  const [enabledAt, setEnabledAt] = useState(() => (enabled ? Date.now() : null));   // when the first request was allowed
  const inFlight = useRef(false);
  const [sarvamLive, setSarvamLive] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  // Auto Dispatcher (9:00 AM) state
  const [autoDispatcher, setAutoDispatcher] = useState({
    enabled: true,
    scheduledTime: '09:00 AM IST',
    systemStatus: 'Operational'
  });
  
  // Navigation
  const [activeTab, setActiveTab] = useState('overview');

  // Drawer
  const [selectedCall, setSelectedCall] = useState(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('today');   // a fresh day starts with an empty overview
  const [customDate, setCustomDate] = useState(localToday);
  const [districtFilter, setDistrictFilter] = useState('all');
  const [languageFilter, setLanguageFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const autoPollInterval = 15; // seconds between refreshes (3 s while a send is running)

  // Primary Fetch Function
  const fetchAllData = useCallback(async (isSilent = false) => {
    if (inFlight.current) return;      // a slow first answer (the server waking up) must not pile up more requests
    inFlight.current = true;
    if (!isSilent) {
      setRefreshing(true);
    }

    try {
      const [farmersRes, callLogsRes, dispRes] = await Promise.all([
        loadFarmersData(),
        loadCallLogsData(),
        getDispatcherStatus().catch(() => ({ enabled: true, scheduledTime: '09:00 AM IST' }))
      ]);

      setFarmers(farmersRes.data || []);
      setCallLogs(callLogsRes.data || []);
      setLastSynced(new Date());

      // Live Backend Health Detection:
      // If callLogsRes is offline, the backend API is unreachable.
      const isOnline = callLogsRes.source === 'sqlite_live' || farmersRes.source === 'sqlite_live';
      setIsBackendOnline(isOnline);
      setSyncStatus(isOnline ? 'connected' : 'disconnected');
      if (isOnline) {
        setHasConnected(true);
        setOfflineSince(null);
      } else {
        setOfflineSince((prev) => prev ?? mountedAt);
      }

      if (dispRes) {
        setAutoDispatcher(dispRes);
        // Sarvam is live only if backend is online AND credentials exist
        setSarvamLive(Boolean(isOnline && dispRes.sarvamLive));
      } else {
        setSarvamLive(false);
      }

      if (!isOnline) {
        setErrorMessage("Backend API is offline. Run 'npm run backend' to start it.");
      } else {
        setErrorMessage(null);
      }
    } catch (err) {
      console.error('Error refreshing voice agent data:', err);
      setIsBackendOnline(false);
      setOfflineSince((prev) => prev ?? mountedAt);
      setSarvamLive(false);
      setSyncStatus('disconnected');
      setErrorMessage(err.message || 'Failed to connect to backend server');
    } finally {
      inFlight.current = false;
      setLoading(false);
      setRefreshing(false);
    }
  }, [mountedAt]);

  // Initial load via microtask (once requests are allowed)
  useEffect(() => {
    if (!enabled) return undefined;
    setEnabledAt((prev) => prev ?? Date.now());
    let mounted = true;
    Promise.resolve().then(() => {
      if (mounted) {
        fetchAllData(true);
      }
    });
    return () => {
      mounted = false;
    };
  }, [fetchAllData, enabled]);

  // Periodic polling (faster while a send is running, so results appear as calls finish)
  // a call that is waiting or on the phone right now (the call log shows it as In Queue or In Call)
  const callLive = callLogs.some((c) => c.status === 'In Call' || c.status === 'In Queue');
  const sending = Boolean(autoDispatcher.running) || callLive;
  useEffect(() => {
    if (!enabled || !autoPollInterval || autoPollInterval <= 0) return undefined;

    // 2 s while a send runs, 5 s while the server is not answering (so the page fills in soon after it wakes), else 15 s
    const every = sending ? 2 : !isBackendOnline ? 5 : autoPollInterval;
    const timer = setInterval(() => {
      fetchAllData(true);
    }, every * 1000);

    return () => clearInterval(timer);
  }, [enabled, autoPollInterval, sending, isBackendOnline, fetchAllData]);

  // Combined Farmer Map for fast lookup
  const farmersMap = useMemo(() => {
    const map = new Map();
    farmers.forEach(f => {
      if (f.farmer_id) {
        map.set(String(f.farmer_id).trim(), f);
      }
    });
    return map;
  }, [farmers]);

  // Enriched Calls (Each call joined with farmer details, 4 weather parameters, and state flags)
  const enrichedCallLogs = useMemo(() => {
    return callLogs.map(call => {
      const farmer = call.farmer_id ? farmersMap.get(String(call.farmer_id).trim()) || {} : {};
      const callDate = call.call_date || getCallDate(call) || (call.created_at ? call.created_at.slice(0, 10) : 'Today');
      const callTime = call.time || getCallTime(call) || (call.created_at ? call.created_at.slice(11, 16) : '');
      
      const weatherFallback = extractWeatherFromMessage(call.message_text, call);
      
      // Determine 4 weather parameters (from SQLite columns or fallback extraction)
      const tempVal = call.weather_temp != null ? `${call.weather_temp}°C` : weatherFallback.temperature;
      const windVal = call.weather_windspeed != null ? `${call.weather_windspeed} km/h` : weatherFallback.wind;
      const rainVal = call.weather_rainfall != null ? `${call.weather_rainfall}%` : weatherFallback.rainfall_chance;
      const humidityVal = call.weather_humidity != null ? `${call.weather_humidity}%` : weatherFallback.humidity;

      // Status resolution: the backend sends the dashboard's own status words
      const rawStatus = call.status || call.call_status || 'Completed';
      const statusWords = {
        'completed': 'Completed', 'answered': 'Completed', 'callback scheduled': 'Callback Scheduled', 'callback requested': 'Callback Requested', 'callback missed': 'Callback Missed', 'callback done': 'Callback Done',
        'not confirmed': 'Not Confirmed', 'declined': 'Declined', 'unanswered': 'Unanswered', 'busy': 'Unanswered', 'no_answer': 'Unanswered',
        'retrying': 'Retrying', 'failed': 'Failed', 'skipped': 'Skipped', 'escalated': 'Escalated',
        'requires escalation': 'Escalated', 'calling': 'Calling', 'scheduled': 'Scheduled',
        'in call': 'In Call', 'in queue': 'In Queue',
      };
      const normalizedStatus = statusWords[String(rawStatus).toLowerCase()] || String(rawStatus);

      const retryCount = call.retry_count || 0;
      const attemptNumber = call.attempts_log?.length || (retryCount + 1);
      const attemptDisplay = call.is_test ? 'Test' : `Attempt ${attemptNumber}/3`;

      // Parse transcript
      let parsedTranscript = call.transcript;
      if (typeof call.transcript === 'string') {
        try {
          parsedTranscript = JSON.parse(call.transcript);
        } catch {
          parsedTranscript = call.transcript;
        }
      }

      const durationSec = call.duration_seconds != null ? call.duration_seconds : (call.duration_sec != null ? call.duration_sec : (call.duration_s != null ? call.duration_s : (call.duration || 0)));

      // Advisory summary
      const advisorySummary = call.advisory_summary || weatherFallback.advisory_summary;

      const isInbound =
        String(call.direction || '').toLowerCase() === 'inbound' ||
        Boolean(call.has_inbound_callback) ||
        (Array.isArray(call.attempts_log) && call.attempts_log.some((a) => a.direction === 'inbound'));

      return {
        ...call,
        call_id: call.call_id || `${call.farmer_id}-${callDate}`,
        date: callDate,
        time: callTime,
        call_timestamp: call.created_at || call.call_date || 'Just now',
        displayDateTime: call.created_at 
          ? `${call.created_at.slice(0, 10)} ${call.created_at.slice(11, 16)}`
          : (call.call_date ? `${call.call_date}` : 'Recent'),
        farmer_name: call.farmer_name || farmer.farmer_name || (call.farmer_id ? `Farmer ${call.farmer_id}` : 'Unassigned'),
        phone_number: call.phone_number || farmer.phone_number || farmer.phone || 'N/A',
        primary_language: normalizeLanguage(call.language || farmer.preferred_language || farmer.primary_language),
        district: farmer.district || (call.location ? call.location.split(',')[1]?.trim() : 'Mandya'),
        village: farmer.village || (call.location ? call.location.split(',')[0]?.trim() : 'N/A'),
        location: call.location || `${farmer.village || ''}, ${farmer.district || ''}`.trim(),
        
        // Direction: Inbound vs Outbound
        direction: isInbound ? 'inbound' : 'outbound',
        has_inbound_callback: Boolean(call.has_inbound_callback || isInbound),

        // 4 Meteorological parameters
        weather_temp: call.weather_temp,
        weather_windspeed: call.weather_windspeed,
        weather_rainfall: call.weather_rainfall,
        weather_humidity: call.weather_humidity,
        temperature: tempVal,
        wind: windVal,
        rainfall_chance: rainVal,
        humidity: humidityVal,
        weather_forecast: call.weather_forecast || (call.weather_rainfall == null ? 'No weather' : (call.weather_rainfall >= 50 ? 'Rain Alert' : 'Low rain chance')),
        advisory_summary: advisorySummary,

        // Status, Dispositions & Attempts
        status: normalizedStatus,
        call_status: normalizedStatus,
        disposition: call.disposition || (normalizedStatus === 'Completed' ? 'Weather Delivered' : normalizedStatus),
        retry_count: retryCount,
        attempt_number: attemptNumber,
        attempt_display: attemptDisplay,
        scheduled_callback_time: call.scheduled_callback_time || null,
        duration_sec: durationSec,
        duration_seconds: durationSec,
        transcript: parsedTranscript,
        attempts_log: call.attempts_log || []
      };
    });
  }, [callLogs, farmersMap]);

  // Dynamic filter options derived from real sheet data
  const availableDistricts = useMemo(() => {
    const set = new Set();
    farmers.forEach(f => { if (f.district) set.add(f.district); });
    enrichedCallLogs.forEach(c => { if (c.district) set.add(c.district); });
    return Array.from(set).sort();
  }, [farmers, enrichedCallLogs]);

  // Supported voice agent languages
  const availableLanguages = useMemo(() => {
    const langs = new Set(['English', 'Hindi', 'Kannada', 'Telugu']);
    farmers.forEach(f => {
      if (f.preferred_language) langs.add(f.preferred_language);
      if (f.primary_language) langs.add(f.primary_language);
    });
    return Array.from(langs);
  }, [farmers]);

  // Filtered Calls
  const filteredCallLogs = useMemo(() => {
    return enrichedCallLogs.filter(call => {
      // Search Query
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = String(call.farmer_name || '').toLowerCase().includes(query);
        const phoneStr = String(call.phone_number || '');
        const matchesPhone = phoneStr.toLowerCase().includes(query) ||
          maskPhoneNumber(phoneStr).toLowerCase().includes(query);
        const matchesCallId = String(call.call_id || '').toLowerCase().includes(query);
        const matchesVillage = String(call.village || '').toLowerCase().includes(query);
        const matchesDistrict = String(call.district || '').toLowerCase().includes(query);
        if (!matchesName && !matchesPhone && !matchesCallId && !matchesVillage && !matchesDistrict) {
          return false;
        }
      }

      // District Filter
      if (districtFilter !== 'all' && call.district !== districtFilter) {
        return false;
      }

      // Language Filter
      if (languageFilter !== 'all' && call.primary_language !== languageFilter) {
        return false;
      }

      // Status Filter
      if (statusFilter !== 'all') {
        const s = String(statusFilter).toLowerCase();
        if (s === 'callback requested' || s === 'callback scheduled' || s === 'callbacks pending') {
          const isCb =
            call.status === 'Callback Scheduled' ||
            call.status === 'Callback Requested' ||
            call.disposition === 'Callback Requested' ||
            call.callback_status === 'pending' ||
            Boolean(call.scheduled_callback_time && !['Completed', 'Callback Done', 'Failed', 'Callback Missed'].includes(call.status));
          if (!isCb) return false;
        } else if (s === 'needs attention' || s === 'needs-attention') {
          const isAttn =
            ['Failed', 'Not Confirmed', 'Callback Missed', 'Declined', 'Escalated'].includes(call.status) ||
            ['failed', 'error', 'declined'].includes(String(call.call_status || '').toLowerCase()) ||
            call.understood_weather === 'declined';
          if (!isAttn) return false;
        } else if (s === 'unanswered' || s === 'retrying') {
          const isUnans =
            ['Unanswered', 'Retrying', 'Busy', 'no_answer', 'busy'].includes(call.status) ||
            ['no_answer', 'busy'].includes(String(call.call_status || '').toLowerCase());
          if (!isUnans) return false;
        } else if (s === 'completed') {
          const isPendingCb =
            call.status === 'Callback Scheduled' ||
            call.status === 'Callback Requested' ||
            call.callback_status === 'pending';
          if (isPendingCb) return false;
          const isComp =
            ['Completed', 'Callback Done'].includes(call.status) ||
            call.disposition === 'Weather Delivered' ||
            call.disposition === 'Callback placed' ||
            (call.understood_weather === 'yes' && call.callback_status !== 'pending' && call.status !== 'Callback Scheduled');
          if (!isComp) return false;
        } else if (String(call.status).toLowerCase() !== s && String(call.call_status).toLowerCase() !== s) {
          return false;
        }
      }

      // Date Filter
      if (dateFilter !== 'all' && customDate) {
        const rawDate = getCallDate(call);
        if (!rawDate || !isCallOnDate(rawDate, customDate)) {
          return false;
        }
      }

      return true;
    });
  }, [enrichedCallLogs, searchQuery, districtFilter, languageFilter, statusFilter, dateFilter, customDate]);

  // Summary cards: unique farmer counts for the active scope (including test calls, excluding Skipped & live calls)
  const summaryMetrics = useMemo(() => {
    const inScope = (c) => {
      if (dateFilter !== 'all' && customDate) {
        const raw = getCallDate(c);
        if (!raw || !isCallOnDate(raw, customDate)) return false;
      }
      if (districtFilter !== 'all' && c.district !== districtFilter) return false;
      if (languageFilter !== 'all' && c.primary_language !== languageFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = String(c.farmer_name || '').toLowerCase().includes(query);
        const phoneStr = String(c.phone_number || '');
        const matchesPhone = phoneStr.toLowerCase().includes(query) ||
          maskPhoneNumber(phoneStr).toLowerCase().includes(query);
        const matchesCallId = String(c.call_id || '').toLowerCase().includes(query);
        const matchesVillage = String(c.village || '').toLowerCase().includes(query);
        const matchesDistrict = String(c.district || '').toLowerCase().includes(query);
        if (!matchesName && !matchesPhone && !matchesCallId && !matchesVillage && !matchesDistrict) {
          return false;
        }
      }
      return true;
    };

    // Rule 4: Include test calls alongside regular calls
    const scoped = enrichedCallLogs.filter((c) => inScope(c));
    const waiting = (c) => c.status === 'In Call' || c.status === 'In Queue' || c.status === 'Calling';
    const called = scoped.filter((c) => c.status !== 'Skipped' && !waiting(c));

    const isCallback = (c) =>
      c.status === 'Callback Scheduled' ||
      c.status === 'Callback Requested' ||
      c.callback_status === 'pending' ||
      Boolean(
        c.scheduled_callback_time &&
        !['Completed', 'Callback Done', 'Failed', 'Not Confirmed', 'Declined', 'Callback Missed'].includes(c.status)
      );

    const isCompleted = (c) =>
      !isCallback(c) && (
        ['Completed', 'Callback Done'].includes(c.status) ||
        c.disposition === 'Weather Delivered' ||
        c.disposition === 'Callback placed' ||
        (c.understood_weather === 'yes' && c.callback_status !== 'pending' && c.status !== 'Callback Scheduled')
      );

    const isUnanswered = (c) =>
      !isCompleted(c) && !isCallback(c) && (
        ['Retrying', 'Unanswered', 'Busy'].includes(c.status) ||
        ['no_answer', 'busy'].includes(String(c.call_status || '').toLowerCase())
      );

    const isNeedsAttention = (c) =>
      !isCompleted(c) && !isCallback(c) && !isUnanswered(c) && (
        ['Failed', 'Not Confirmed', 'Callback Missed', 'Declined', 'Escalated'].includes(c.status) ||
        ['failed', 'error', 'declined'].includes(String(c.call_status || '').toLowerCase()) ||
        c.understood_weather === 'declined'
      );

    // Rule 1A: Classify each unique farmer into a single highest-priority bucket
    const farmerBuckets = new Map();
    const priority = { completed: 4, callback: 3, unanswered: 2, attention: 1 };

    called.forEach((c) => {
      const fid = String(c.farmer_id || c.phone_number || c.phone || c.farmer_name || c.call_id || '').trim();
      if (!fid) return;

      let bucket = 'attention';
      if (isCompleted(c)) bucket = 'completed';
      else if (isCallback(c)) bucket = 'callback';
      else if (isUnanswered(c)) bucket = 'unanswered';
      else if (isNeedsAttention(c)) bucket = 'attention';

      const existing = farmerBuckets.get(fid);
      if (!existing || priority[bucket] > priority[existing]) {
        farmerBuckets.set(fid, bucket);
      }
    });

    let completedFarmersCount = 0;
    let callbacksScheduled = 0;
    let retryingCount = 0;
    let needsAttentionCount = 0;

    farmerBuckets.forEach((bucket) => {
      if (bucket === 'completed') completedFarmersCount += 1;
      else if (bucket === 'callback') callbacksScheduled += 1;
      else if (bucket === 'unanswered') retryingCount += 1;
      else needsAttentionCount += 1;
    });

    // Total calls by category
    const completedCallsCount = called.filter(isCompleted).length;
    const callbacksCallsCount = called.filter(isCallback).length;
    const unansweredCallsCount = called.filter(isUnanswered).length;
    const needsAttentionCallsCount = called.filter(isNeedsAttention).length;

    const scopeLabel =
      dateFilter === 'today'
        ? 'Today'
        : dateFilter === 'yesterday'
          ? 'Yesterday'
          : customDate
            ? customDate
            : 'All dates';

    return {
      scopeLabel,
      totalCalls: called.length,
      uniqueFarmersCount: farmerBuckets.size,
      completedCount: completedCallsCount,
      completedCallsCount,
      completedFarmersCount,
      callbacksScheduled,
      callbacksCallsCount,
      retryingCount,
      unansweredCallsCount,
      needsAttentionCount,
      needsAttentionCallsCount,
      declinedCount: called.filter((c) => c.status === 'Declined').length,
      skippedCount: scoped.filter((c) => c.status === 'Skipped').length,
      inProgressCount: scoped.filter(waiting).length,
    };
  }, [enrichedCallLogs, dateFilter, customDate, districtFilter, languageFilter, searchQuery]);

  // Send today's calls now to every eligible farmer
  const triggerDemo = async () => {
    if (!isBackendOnline) {
      const msg = "Cannot send calls: the backend API is offline. Start it with 'npm run backend'.";
      setErrorMessage(msg);
      return;
    }
    // Real calls cost credits and ring farmers' phones: ask first when calls are live
    if (autoDispatcher.live && !(await confirmDialog({
      title: "Send today's calls now?",
      message: 'This will place REAL calls to every eligible farmer today and uses Sarvam credits.',
      confirmLabel: 'Send now',
      tone: 'danger',
    }))) {
      return undefined;
    }
    setTriggeringDemo(true);
    try {
      const res = await sendCallsNow();
      await fetchAllData(true);
      return res;
    } catch (err) {
      console.error('Failed to trigger demo batch:', err);
      setIsBackendOnline(false);
      setSyncStatus('disconnected');
      setErrorMessage(err.message || 'Failed to trigger demo: Backend is offline');
      throw err;
    } finally {
      setTriggeringDemo(false);
    }
  };

  // Toggle Auto Dispatcher (9:00 AM)
  const toggleAutoDispatcher = async () => {
    try {
      const nextState = !autoDispatcher.enabled;
      if (nextState && autoDispatcher.live && !(await confirmDialog({
        title: 'Turn on the daily 9:00 AM calls?',
        message: 'Real calls will be placed to every eligible farmer every day at 9:00 AM IST.',
        confirmLabel: 'Turn on',
        tone: 'danger',
      }))) {
        return;
      }
      const res = await updateDispatcherStatus(nextState);
      setAutoDispatcher(prev => ({ ...prev, ...res }));
    } catch (err) {
      console.error('Failed to toggle auto dispatcher:', err);
      // Optimistic fallback toggle
      setAutoDispatcher(prev => ({ ...prev, enabled: !prev.enabled }));
    }
  };

  // Reset all filters
  const resetFilters = () => {
    setSearchQuery('');
    setDateFilter('today');
    setCustomDate(localToday());
    setDistrictFilter('all');
    setLanguageFilter('all');
    setStatusFilter('all');
  };

  return {
    farmers,
    callLogs: enrichedCallLogs,
    filteredCallLogs,
    loading,
    refreshing,
    triggeringDemo,
    lastSynced,
    syncStatus,
    isBackendOnline,
    hasConnected,
    waitingSince: !isBackendOnline ? offlineSince : (!hasConnected ? (enabledAt ?? mountedAt) : null),
    sarvamLive,
    errorMessage,
    summaryMetrics,
    autoDispatcher,
    toggleAutoDispatcher,
    triggerDemo,
    availableDistricts,
    availableLanguages,
    activeTab,
    setActiveTab,
    selectedCall,
    setSelectedCall,
    searchQuery,
    setSearchQuery,
    dateFilter,
    setDateFilter,
    customDate,
    setCustomDate,
    districtFilter,
    setDistrictFilter,
    languageFilter,
    setLanguageFilter,
    statusFilter,
    setStatusFilter,
    fetchAllData,
    resetFilters,
  };
};
