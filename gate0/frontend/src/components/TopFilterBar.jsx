import React from 'react';
import {
  Search,
  Calendar as CalendarIcon,
  MapPin,
  Languages,
  Filter,
  RotateCcw,
  X as ClearIcon
} from 'lucide-react';

const getTodayStr = () => {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getYesterdayStr = () => {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const TopFilterBar = ({
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
  totalCount,
  filteredCount,
  resetFilters,
  availableDistricts = [],
  availableLanguages = [],
}) => {
  const isFiltered = searchQuery || dateFilter !== 'today' || districtFilter !== 'all' || languageFilter !== 'all' || statusFilter !== 'all';

  const handleDatePresetClick = (presetId) => {
    if (presetId === 'today') {
      const today = getTodayStr();
      setCustomDate(today);
      setDateFilter('today');
    } else if (presetId === 'yesterday') {
      const yesterday = getYesterdayStr();
      setCustomDate(yesterday);
      setDateFilter('yesterday');
    } else {
      // 'all'
      setCustomDate('');
      setDateFilter('all');
    }
  };

  const handleDateInputChange = (e) => {
    const val = e.target.value;
    setCustomDate(val);
    if (!val) {
      setDateFilter('all');
    } else if (val === getTodayStr()) {
      setDateFilter('today');
    } else if (val === getYesterdayStr()) {
      setDateFilter('yesterday');
    } else {
      setDateFilter('custom');
    }
  };

  const clearDateInput = () => {
    setCustomDate('');
    setDateFilter('all');
  };

  const datePresets = [
    { id: 'all', label: 'All Dates' },
    { id: 'today', label: 'Today' },
    { id: 'yesterday', label: 'Yesterday' },
  ];

  const statuses = ['All Status', 'Completed', 'Callback Scheduled', 'Callback Missed', 'Callback Done', 'Retrying', 'Not Confirmed', 'Declined', 'Unanswered', 'Failed', 'Skipped'];

  const box = 'flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-50 border border-slate-200/80 rounded-xl text-xs min-w-0';
  const select = 'bg-transparent text-xs font-medium text-slate-700 focus:outline-hidden cursor-pointer w-full min-w-0 sm:w-auto';

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 p-3 shadow-2xs">
      {/* Phones: a tidy two-column grid (date, quick dates, search full width; district and language side by side; status full
          width; reset and count on the last line). From sm up: one wrapping row. */}
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
        <div className={`${box} col-span-2`}>
          <CalendarIcon className="w-3.5 h-3.5 text-trust-green" />
          <input
            type="date"
            value={customDate || ''}
            onChange={handleDateInputChange}
            aria-label="Filter by date"
            className="bg-transparent border-none text-xs font-bold text-slate-900 focus:outline-hidden cursor-pointer flex-1 min-w-0"
          />
          {customDate && (
            <button type="button" onClick={clearDateInput} title="Reset date to all" className="text-slate-400 hover:text-slate-600 p-0.5 rounded cursor-pointer">
              <ClearIcon className="w-3 h-3" />
            </button>
          )}
        </div>

        <div className="col-span-2 grid grid-cols-3 gap-1 p-0.5 bg-slate-50 rounded-xl border border-slate-200/80 sm:flex sm:items-center">
          {datePresets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handleDatePresetClick(preset.id)}
              className={`px-2.5 py-1.5 sm:py-1 text-xs font-medium rounded-lg transition-colors whitespace-nowrap cursor-pointer ${
                dateFilter === preset.id
                  ? 'bg-trust-navy text-white shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-white'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="relative col-span-2 sm:flex-1 sm:min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search farmer, phone, village, call ID..."
            className="w-full pl-9 pr-7 py-2 bg-slate-50 border border-slate-200/80 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-trust-navy focus:ring-1 focus:ring-trust-navy transition-all"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600 cursor-pointer">
              ×
            </button>
          )}
        </div>

        <div className={`${box} col-span-1`}>
          <MapPin className="w-3.5 h-3.5 text-slate-400" />
          <select value={districtFilter} onChange={(e) => setDistrictFilter(e.target.value)} className={select}>
            <option value="all">All districts</option>
            {availableDistricts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        <div className={`${box} col-span-1`}>
          <Languages className="w-3.5 h-3.5 text-slate-400" />
          <select value={languageFilter} onChange={(e) => setLanguageFilter(e.target.value)} className={select}>
            <option value="all">All languages</option>
            {availableLanguages.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>

        <div className={`${box} col-span-2 sm:col-span-1`}>
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter === 'all' ? 'All Status' : statusFilter}
            onChange={(e) => setStatusFilter(e.target.value === 'All Status' ? 'all' : e.target.value)}
            className={select}
          >
            {statuses.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="col-span-2 flex items-center justify-between gap-2 sm:contents">
        {isFiltered && (
          <button
            onClick={resetFilters}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-xl font-medium transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset</span>
          </button>
        )}

        <span className="text-xs text-slate-500 whitespace-nowrap ml-auto sm:ml-0">
          <strong className="font-bold text-slate-900">{filteredCount}</strong> of {totalCount} calls
        </span>
        </div>
      </div>
    </div>
  );
};
