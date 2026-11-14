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
  CostAnalyticsView,
  RealTimeCostChart,
  ConfirmHost,
  MobileNav,
  ServerBanner,
  LoginScreen
} from './components';
import { useVoiceAgentData } from './hooks';
import { getSessionToken, logoutAdmin } from './utils';

function Dashboard({ onLogout }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showCostChart, setShowCostChart] = useState(false);

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
  } = useVoiceAgentData();

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
          onRefresh={() => fetchAllData(false)}
          refreshing={refreshing}
          syncStatus={syncStatus}
          isBackendOnline={isBackendOnline && hasConnected}
          activeTab={activeTab}
          onTriggerDemo={triggerDemo}
          triggeringDemo={triggeringDemo}
          autoDispatcher={autoDispatcher}
          onToggleAutoDispatcher={toggleAutoDispatcher}
          onLogout={onLogout}
        />

        {/* Tab Content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 md:py-8 pb-24 lg:pb-8 space-y-4 sm:space-y-6">
          {/* Waking up / offline banner */}
          <ServerBanner
            isOnline={isBackendOnline}
            loading={loading}
            hasConnected={hasConnected}
            waitingSince={waitingSince}
            onRetry={() => fetchAllData(false)}
          />
          {activeTab === 'overview' && (
            <>
              {/* KPI Metrics */}
              <KpiMetrics metrics={summaryMetrics} loading={!hasConnected} />

              {/* Real-Time Cost Analytics Chart Toggle & Panel */}
              <div className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <button
                    type="button"
                    onClick={() => setShowCostChart((prev) => !prev)}
                    className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-white border border-slate-200/80 text-slate-700 hover:text-slate-900 hover:border-slate-300 shadow-2xs transition-all cursor-pointer"
                  >
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                    </span>
                    <span>{showCostChart ? 'Hide Real-Time Cost Chart' : 'Show Real-Time Cost Analytics'}</span>
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-emerald-50 text-trust-green border border-emerald-200">
                      Live ₹
                    </span>
                  </button>
                </div>

                {showCostChart && (
                  <RealTimeCostChart
                    callLogs={callLogs}
                    rate={3.5}
                    isLive={Boolean(autoDispatcher?.live)}
                    onRefresh={() => fetchAllData(false)}
                  />
                )}
              </div>

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

          {activeTab === 'cost' && (
            <CostAnalyticsView isBackendOnline={isBackendOnline} callLogs={callLogs} />
          )}

          {activeTab === 'system' && (
            <SystemStatusView isBackendOnline={isBackendOnline} />
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

function App() {
  const [sessionToken, setSessionToken] = useState(() => getSessionToken());

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

  if (!sessionToken) {
    return <LoginScreen onLoginSuccess={() => setSessionToken(getSessionToken())} />;
  }

  return <Dashboard onLogout={logoutAdmin} />;
}

export default App;
