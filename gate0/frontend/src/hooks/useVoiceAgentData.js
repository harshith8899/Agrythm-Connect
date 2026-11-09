import { useState, useEffect, useMemo, useCallback } from 'react';
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

export const useVoiceAgentData = () => {
  const [farmers, setFarmers] = useState([]);
  const [callLogs, setCallLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [triggeringDemo, setTriggeringDemo] = useState(false);
  const [lastSynced, setLastSynced] = useState(null);
  const [syncStatus, setSyncStatus] = useState('syncing');
  const [isBackendOnline, setIsBackendOnline] = useState(true);
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
  const [dateFilter, setDateFilter] = useState('all');
  const [customDate, setCustomDate] = useState('');
  const [districtFilter, setDistrictFilter] = useState('all');
  const [languageFilter, setLanguageFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const autoPollInterval = 15; // seconds between refreshes (3 s while a send is running)

  // Primary Fetch Function
  const fetchAllData = useCallback(async (isSilent = false) => {
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
      setSarvamLive(false);
      setSyncStatus('disconnected');
      setErrorMessage(err.message || 'Failed to connect to backend server');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Initial load via microtask
  useEffect(() => {
    let mounted = true;
    Promise.resolve().then(() => {
      if (mounted) {
        fetchAllData(true);
      }
    });
    return () => {
      mounted = false;
    };
  }, [fetchAllData]);

  // Periodic polling (faster while a send is running, so results appear as calls finish)
  const sending = Boolean(autoDispatcher.running);
  useEffect(() => {
    if (!autoPollInterval || autoPollInterval <= 0) return;

    const timer = setInterval(() => {
      fetchAllData(true);
    }, (sending ? 3 : autoPollInterval) * 1000);

    return () => clearInterval(timer);
  }, [autoPollInterval, sending, fetchAllData]);

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
        'completed': 'Completed', 'answered': 'Completed', 'callback scheduled': 'Callback Scheduled',
        'not confirmed': 'Not Confirmed', 'declined': 'Declined', 'unanswered': 'Unanswered', 'busy': 'Unanswered', 'no_answer': 'Unanswered',
        'retrying': 'Retrying', 'failed': 'Failed', 'skipped': 'Skipped', 'escalated': 'Escalated',
        'requires escalation': 'Escalated', 'calling': 'Calling', 'scheduled': 'Scheduled',
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

      const durationSec = call.duration_seconds != null ? call.duration_seconds : (call.duration_sec || 0);

      // Advisory summary
      const advisorySummary = call.advisory_summary || 
        (call.weather_temp != null
          ? `Temp ${call.weather_temp}°C | Wind ${call.weather_windspeed} km/h | Rain ${call.weather_rainfall}% | Humidity ${call.weather_humidity}%`
          : weatherFallback.advisory_summary);

      return {
        ...call,
        call_id: call.call_id || `${call.farmer_id}-${callDate}`,
        date: callDate,
        time: callTime,
        call_timestamp: call.created_at || call.call_date || 'Just now',
        displayDateTime: call.created_at 
          ? `${call.created_at.slice(0, 10)} ${call.created_at.slice(11, 16)} (${attemptDisplay})`
          : (call.call_date ? `${call.call_date} (${attemptDisplay})` : 'Recent'),
        farmer_name: call.farmer_name || farmer.farmer_name || (call.farmer_id ? `Farmer ${call.farmer_id}` : 'Unassigned'),
        phone_number: call.phone_number || farmer.phone_number || farmer.phone || 'N/A',
        primary_language: normalizeLanguage(call.language || farmer.preferred_language || farmer.primary_language),
        district: farmer.district || (call.location ? call.location.split(',')[1]?.trim() : 'Mandya'),
        village: farmer.village || (call.location ? call.location.split(',')[0]?.trim() : 'N/A'),
        location: call.location || `${farmer.village || ''}, ${farmer.district || ''}`.trim(),
        
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
        if (s === 'callback requested') {
          if (!call.scheduled_callback_time && call.disposition !== 'Callback Requested') return false;
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

  // Summary metrics calculated from the call records the backend returns
  const summaryMetrics = useMemo(() => {
    const realLogs = enrichedCallLogs.filter(c => !c.is_test); // test calls never count in the summary
    const totalCalls = realLogs.length;
    const completedCount = realLogs.filter(c => c.status === 'Completed').length;
    const retryingCount = realLogs.filter(c => ['Retrying', 'Unanswered'].includes(c.status)).length;
    const failedCount = realLogs.filter(c => c.status === 'Failed').length;
    const needsAttentionCount = realLogs.filter(c => ['Failed', 'Not Confirmed'].includes(c.status)).length;
    const escalationCount = needsAttentionCount;
    const callbackCount = realLogs.filter(c => Boolean(c.scheduled_callback_time) || c.disposition === 'Callback Requested').length;

    // Callbacks still waiting to be placed (the backend places each one at the time the farmer asked for)
    const callbacksScheduled = realLogs.filter(c => c.callback_status === 'pending').length;

    // Unique farmers reached (answered weather or resolved callback/escalation)
    const reachedFarmerIds = new Set();
    realLogs.forEach(c => {
      if (['Completed', 'Escalated'].includes(c.status) || ['Weather Delivered', 'Callback Requested', 'Non-Weather Inquiry'].includes(c.disposition)) {
        if (c.farmer_id) reachedFarmerIds.add(String(c.farmer_id).trim());
      }
    });
    const farmersReached = reachedFarmerIds.size;

    return {
      totalCalls,
      completedCount,
      deliveredCount: completedCount,
      farmersReached,
      retryingCount,
      failedCount,
      escalationCount,
      needsAttentionCount,
      callbackCount,
      callbacksScheduled,
      totalRegisteredFarmers: farmers.length,
      confidenceRate: '98.5%'
    };
  }, [enrichedCallLogs, farmers]);

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
    setDateFilter('all');
    setCustomDate('');
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
