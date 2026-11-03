import React, { useState } from 'react';
import { 
  Sidebar, 
  Header, 
  TopFilterBar, 
  KpiMetrics, 
  CallHistoryTable, 
  CallDetailDrawer, 
  FarmerDirectory, 
  WeatherAlertsView, 
  TrustAiAnalyticsView, 
  CloudSyncSettings 
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
    appsScriptUrl,
    saveAppsScriptUrl,
    autoPollInterval,
    setAutoPollInterval,
    fetchAllData,
    updateCallLog,
    resetFilters,
  } = useVoiceAgentData();

  // Check if any filter is active
  const isFiltered = Boolean(searchQuery || dateFilter !== 'all' || districtFilter !== 'all' || languageFilter !== 'all' || statusFilter !== 'all');

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
        syncStatus={syncStatus}
        weatherAlertsCount={summaryMetrics.severeWeatherAlerts}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Sticky Header with Triggers */}
        <Header
          onToggleSidebar={() => setSidebarOpen(true)}
          onRefresh={() => fetchAllData(false)}
          refreshing={refreshing}
          syncStatus={syncStatus}
          activeTab={activeTab}
          onTriggerDemo={triggerDemo}
          triggeringDemo={triggeringDemo}
          autoDispatcher={autoDispatcher}
          onToggleAutoDispatcher={toggleAutoDispatcher}
        />

        {/* Tab Content */}
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 md:py-8 space-y-6">
          {activeTab === 'overview' && (
            <>
              {/* Top Filter Bar with Calendar Display */}
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

              {/* KPI Metrics */}
              <KpiMetrics metrics={summaryMetrics} />

              {/* Call History Table */}
              <CallHistoryTable
                callLogs={filteredCallLogs}
                onSelectCall={(call) => setSelectedCall(call)}
                selectedCallId={selectedCall?.call_id}
                onResetFilters={resetFilters}
                isFiltered={isFiltered}
              />
            </>
          )}

          {activeTab === 'farmers' && (
            <FarmerDirectory
              farmers={farmers}
              callLogs={callLogs}
              onSelectFarmer={handleSelectFarmerFromDirectory}
            />
          )}

          {activeTab === 'weather' && (
            <WeatherAlertsView callLogs={callLogs} />
          )}

          {activeTab === 'trust_ai' && (
            <TrustAiAnalyticsView callLogs={callLogs} />
          )}

          {activeTab === 'sync' && (
            <CloudSyncSettings
              syncStatus={syncStatus}
              lastSynced={lastSynced}
              refreshing={refreshing}
              onRefresh={() => fetchAllData(false)}
              autoPollInterval={autoPollInterval}
              setAutoPollInterval={setAutoPollInterval}
              appsScriptUrl={appsScriptUrl}
              onSaveAppsScriptUrl={saveAppsScriptUrl}
              callLogs={callLogs}
            />
          )}
        </main>
      </div>

      {/* Slide-over Inspection Drawer for Call Details */}
      {selectedCall && (
        <CallDetailDrawer
          call={selectedCall}
          onClose={() => setSelectedCall(null)}
          onUpdateCall={updateCallLog}
        />
      )}
    </div>
  );
}

export default App;
