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
  LoginScreen
} from './components';
import { useVoiceAgentData } from './hooks';
import { getSessionToken, logoutAdmin } from './utils';

function Dashboard({ onLogout }) {
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

          {activeTab === 'system' && (
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
