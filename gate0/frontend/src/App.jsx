import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
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
  MobileNav
} from './components';
import { useVoiceAgentData } from './hooks';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const {
    farmers,
    callLogs,
    filteredCallLogs,
    refreshing,
    triggeringDemo,
    lastSynced,
    syncStatus,
    isBackendOnline,
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
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Sticky Header with Triggers */}
        <Header
          onRefresh={() => fetchAllData(false)}
          refreshing={refreshing}
          syncStatus={syncStatus}
          isBackendOnline={isBackendOnline}
          activeTab={activeTab}
          onTriggerDemo={triggerDemo}
          triggeringDemo={triggeringDemo}
          autoDispatcher={autoDispatcher}
          onToggleAutoDispatcher={toggleAutoDispatcher}
        />

        {/* Tab Content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 md:py-8 pb-24 lg:pb-8 space-y-4 sm:space-y-6">
          {/* Global Backend Offline Alert Banner */}
          {!isBackendOnline && (
            <div className="bg-rose-50 border border-rose-200 p-4 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-rose-900 shadow-xs animate-in fade-in duration-200">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-rose-100 flex items-center justify-center text-rose-600 shrink-0">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs sm:text-sm font-bold text-rose-950">
                    Backend API Disconnected
                  </div>
                  <div className="text-xs text-rose-700 mt-0.5 leading-relaxed">
                    Cannot reach the API. If it runs on Render's free plan it may be waking up: wait a minute and press Retry.
                  </div>
                </div>
              </div>
              <button
                onClick={() => fetchAllData(false)}
                className="shrink-0 px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs transition-colors shadow-2xs cursor-pointer inline-flex items-center justify-center gap-1.5"
              >
                <span>Retry Connection</span>
              </button>
            </div>
          )}
          {activeTab === 'overview' && (
            <>
              {/* KPI Metrics */}
              <KpiMetrics metrics={summaryMetrics} />

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

export default App;
