import React, { useState, useEffect } from 'react';
import { 
  Sidebar, 
  Header, 
  TopFilterBar, 
  KpiMetrics, 
  CallHistoryTable, 
  CallDetailDrawer, 
  FarmerDirectory, 
  SystemStatusView,
  ConfirmHost,
  MobileNav,
  ServerBanner,
  LoginScreen,
  SignInStatus
} from './components';
import { useVoiceAgentData } from './hooks';
import { getSessionToken, logoutAdmin, loginAdmin, pingServer } from './utils';

// signingIn: the dashboard is on screen but the sign-in is still finishing in the background (the server may be asleep): nothing is
// requested and the buttons that need the server do nothing until it is done.
function Dashboard({ onLogout, signingIn = false, signIn = null }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const {
    farmers,
    callLogs,
    filteredCallLogs,
    refreshing,
    triggeringDemo,
    lastSynced: _lastSynced,
    syncStatus,
    loading,
    isBackendOnline,
    hasConnected,
    waitingSince,
    errorMessage: _errorMessage,
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
  } = useVoiceAgentData({ enabled: !signingIn });

  // Check if any filter is active
  const isFiltered = Boolean(searchQuery || dateFilter !== 'today' || districtFilter !== 'all' || languageFilter !== 'all' || statusFilter !== 'all');

  // Handle clicking "View Call Logs" from Farmer Directory
  const handleSelectFarmerFromDirectory = (farmerName) => {
    setSearchQuery(farmerName);
    setActiveTab('overview');
  };

  return (
    <div className="min-h-screen bg-trust-canvas text-slate-900 flex font-sans antialiased">
      {/* Left Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isOpen={sidebarOpen}
        setIsOpen={setSidebarOpen}
        onLogout={onLogout}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Sticky Header with Triggers */}
        <Header
          onRefresh={signingIn ? () => {} : () => fetchAllData(false)}
          refreshing={refreshing}
          syncStatus={syncStatus}
          isBackendOnline={isBackendOnline && hasConnected}
          activeTab={activeTab}
          onTriggerDemo={signingIn ? () => {} : triggerDemo}
          triggeringDemo={triggeringDemo}
          autoDispatcher={autoDispatcher}
          onToggleAutoDispatcher={signingIn ? () => {} : toggleAutoDispatcher}
          onLogout={onLogout}
        />

        {/* Tab Content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 md:py-8 pb-24 lg:pb-8 space-y-4 sm:space-y-6">
          {/* Waking up / offline banner */}
          {signingIn ? (
            <SignInStatus username={signIn?.username} info={signIn?.info} onCancel={onLogout} />
          ) : (
            <ServerBanner
              isOnline={isBackendOnline}
              loading={loading}
              hasConnected={hasConnected}
              waitingSince={waitingSince}
              onRetry={() => fetchAllData(false)}
            />
          )}
          {activeTab === 'overview' && (
            <>
              {/* KPI Metrics */}
              <KpiMetrics
                metrics={summaryMetrics}
                loading={!hasConnected}
                statusFilter={statusFilter}
                setStatusFilter={setStatusFilter}
              />

              {/* Filters, below the summary cards */}
              <TopFilterBar
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                dateFilter={dateFilter}
                setDateFilter={setDateFilter}
                customDate={customDate}
                setCustomDate={setCustomDate}
                districtFilter={districtFilter}
                setDistrictFilter={setDistrictFilter}
                languageFilter={languageFilter}
                setLanguageFilter={setLanguageFilter}
                statusFilter={statusFilter}
                setStatusFilter={setStatusFilter}
                totalCount={callLogs.length}
                filteredCount={filteredCallLogs.length}
                resetFilters={resetFilters}
                availableDistricts={availableDistricts}
                availableLanguages={availableLanguages}
              />

              {/* Call History Table */}
              <CallHistoryTable
                callLogs={filteredCallLogs}
                onSelectCall={(call) => setSelectedCall(call)}
                selectedCallId={selectedCall?.call_id}
                onResetFilters={resetFilters}
                isFiltered={isFiltered}
                isBackendOnline={isBackendOnline}
                loading={!hasConnected}
                refreshing={refreshing}
                onRefresh={() => fetchAllData(false)}
              />
            </>
          )}

          {activeTab === 'farmers' && (
            <FarmerDirectory
              farmers={farmers}
              callLogs={callLogs}
              onSelectFarmer={handleSelectFarmerFromDirectory}
              onImported={() => fetchAllData(false)}
              isLive={Boolean(autoDispatcher?.live)}
            />
          )}

          {(activeTab === 'system' || activeTab === 'cost') && (
            <SystemStatusView isBackendOnline={isBackendOnline} callLogs={callLogs} />
          )}
        </main>
      </div>

      <MobileNav activeTab={activeTab} setActiveTab={setActiveTab} />
      <ConfirmHost />

      {/* Slide-over Inspection Drawer for Call Details */}
      {selectedCall && (
        <CallDetailDrawer
          call={selectedCall}
          onClose={() => setSelectedCall(null)}
        />
      )}
    </div>
  );
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function App() {
  const [sessionToken, setSessionToken] = useState(() => getSessionToken());
  const [pending, setPending] = useState(null);          // { username, password } while the sign-in finishes in the background
  const [info, setInfo] = useState({ phase: 'waking', seconds: 0, last: null });
  const [loginError, setLoginError] = useState('');

  useEffect(() => {
    const handleAuth = () => {
      setSessionToken(getSessionToken());
    };
    window.addEventListener('gate0-auth-change', handleAuth);
    window.addEventListener('gate0-unauthorized', handleAuth);
    return () => {
      window.removeEventListener('gate0-auth-change', handleAuth);
      window.removeEventListener('gate0-unauthorized', handleAuth);
    };
  }, []);

  // The sign-in itself: wait for the server to answer (this wakes it), then check the details; a start-up error right after is tried
  // again, a wrong password is not. The person is already looking at the dashboard meanwhile.
  useEffect(() => {
    if (!pending) return undefined;
    let stopped = false;
    const startedAt = Date.now();
    const tick = setInterval(() => setInfo((prev) => ({ ...prev, seconds: Math.round((Date.now() - startedAt) / 1000) })), 1000);
    (async () => {
      for (;;) {
        const answer = await pingServer();
        if (stopped) return;
        if (answer.ok) break;
        const unconfigured = answer.status === 503 && /not configured/i.test(answer.message);
        setInfo((prev) => ({ ...prev, phase: unconfigured ? 'unconfigured' : 'waking', last: { status: answer.status, message: answer.message } }));
        await wait(unconfigured ? 10000 : 3000);
        if (stopped) return;
      }
      setInfo((prev) => ({ ...prev, phase: 'signing' }));
      for (let attempt = 0; ; attempt += 1) {
        try {
          await loginAdmin(pending.username, pending.password);       // stores the session: the dashboard then starts loading
          if (!stopped) setPending(null);
          return;
        } catch (err) {
          if (stopped) return;
          if (err.transient && attempt < 10) {
            setInfo((prev) => ({ ...prev, phase: 'waking' }));
            await wait(3000);
            continue;
          }
          setPending(null);
          setLoginError(err.transient ? 'The server did not answer. Check that the Render service shows Live, then try again.' : (err.message || 'Invalid username or password.'));
          return;
        }
      }
    })();
    return () => { stopped = true; clearInterval(tick); };
  }, [pending]);

  const signIn = (username, password) => {
    setLoginError('');
    setInfo({ phase: 'waking', seconds: 0, last: null });
    setPending({ username, password });
  };

  if (!sessionToken && !pending) {
    return <LoginScreen onSignIn={signIn} initialError={loginError} />;
  }

  const signingIn = !sessionToken;
  return (
    <Dashboard
      onLogout={signingIn ? () => setPending(null) : logoutAdmin}
      signingIn={signingIn}
      signIn={signingIn ? { username: pending?.username, info } : null}
    />
  );
}

export default App;
