import React from 'react';
import { 
  PhoneCall, 
  CheckCircle2,
  Clock, 
  RefreshCw,
  ShieldAlert
} from 'lucide-react';
import { OverviewCard } from './OverviewCard';

export const KpiMetrics = ({
  metrics,
  loading = false,
  statusFilter = 'all',
  setStatusFilter,
}) => {
  const called = metrics.totalCalls || 0;
  const uniqueFarmers = metrics.uniqueFarmersCount || called;
  const completed = metrics.completedCount || 0;
  const callbacks = metrics.callbacksScheduled || 0;
  const unanswered = metrics.retryingCount || 0;
  const needsAttention = metrics.needsAttentionCount || 0;
  const skipped = metrics.skippedCount || 0;
  const inProgress = metrics.inProgressCount || 0;
  const scope = metrics.scopeLabel || 'All dates';
  const completionPct = called > 0 ? `${Math.round((completed / called) * 100)}%` : '0%';

  const isAllActive = !statusFilter || statusFilter === 'all';
  const isCompletedActive = ['completed', 'callback done'].includes(String(statusFilter).toLowerCase());
  const isCallbackActive = ['callback scheduled', 'callback requested', 'callbacks pending'].includes(String(statusFilter).toLowerCase());
  const isUnansweredActive = ['unanswered', 'retrying', 'busy'].includes(String(statusFilter).toLowerCase());
  const isNeedsAttentionActive = ['needs attention', 'needs-attention', 'failed', 'not confirmed'].includes(String(statusFilter).toLowerCase());

  const handleCardClick = (targetStatus) => {
    if (!setStatusFilter) return;
    if (targetStatus === 'all') {
      setStatusFilter('all');
      return;
    }
    // Toggle off if already selected
    if (String(statusFilter).toLowerCase() === String(targetStatus).toLowerCase()) {
      setStatusFilter('all');
    } else {
      setStatusFilter(targetStatus);
    }
  };

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-1 text-[11px] text-slate-500">
        <div className="flex items-center gap-2">
          <span>Summary for <strong className="text-slate-800">{scope}</strong></span>
          {!isAllActive && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-trust-navy/10 text-trust-navy font-semibold text-[11px]">
              Filtered: {statusFilter}
              <button
                type="button"
                onClick={() => setStatusFilter && setStatusFilter('all')}
                className="ml-1 text-slate-500 hover:text-rose-600 font-bold cursor-pointer"
                title="Reset status filter"
              >
                ×
              </button>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {inProgress > 0 && <span className="font-semibold text-blue-700">{inProgress} in progress</span>}
          {skipped > 0 && <span>{skipped} skipped (not counted)</span>}
          <span className="text-slate-400 text-[10px] hidden sm:inline">Click any card to filter call logs</span>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2.5 sm:gap-3.5">
        <OverviewCard
          loading={loading}
          title={scope === 'All dates' ? "Total Calls" : "Farmers Called"}
          value={called}
          subtitle={
            uniqueFarmers && uniqueFarmers !== called
              ? `${uniqueFarmers} unique farmers (${called} calls)`
              : "Farmers with at least one call"
          }
          icon={PhoneCall}
          badge={called > 0 ? (isAllActive ? scope : 'All Calls') : 'None yet'}
          badgeColor={isAllActive ? 'bg-slate-100 text-slate-800 border-slate-300' : undefined}
          active={isAllActive}
          onClick={() => handleCardClick('all')}
        />
        <OverviewCard
          loading={loading}
          title="Completed"
          value={completed}
          subtitle={`${completionPct} of calls delivered weather`}
          icon={CheckCircle2}
          badge={isCompletedActive ? 'Active' : (called > 0 ? completionPct : 'Pending')}
          badgeColor={isCompletedActive ? 'bg-trust-navy text-white border-trust-navy' : 'bg-emerald-50 text-trust-green border-emerald-200'}
          active={isCompletedActive}
          onClick={() => handleCardClick('Completed')}
        />
        <OverviewCard
          loading={loading}
          title="Callbacks Pending"
          value={callbacks}
          subtitle="Farmers who asked to be called later"
          icon={Clock}
          badge={isCallbackActive ? 'Active' : (callbacks > 0 ? `${callbacks} Waiting` : 'None')}
          badgeColor={isCallbackActive ? 'bg-trust-navy text-white border-trust-navy' : 'bg-amber-50 text-amber-700 border-amber-200'}
          active={isCallbackActive}
          onClick={() => handleCardClick('Callback Scheduled')}
        />
        <OverviewCard
          loading={loading}
          title="Unanswered"
          value={unanswered}
          subtitle="Not picked up, busy, or scheduled for retry"
          icon={RefreshCw}
          badge={isUnansweredActive ? 'Active' : (unanswered > 0 ? `${unanswered} Retrying` : 'Clear')}
          badgeColor={isUnansweredActive ? 'bg-trust-navy text-white border-trust-navy' : 'bg-slate-100 text-slate-700 border-slate-200'}
          active={isUnansweredActive}
          onClick={() => handleCardClick('Unanswered')}
        />
        <OverviewCard
          loading={loading}
          title="Needs Attention"
          value={needsAttention}
          subtitle="Failed calls, or the farmer did not confirm"
          icon={ShieldAlert}
          badge={isNeedsAttentionActive ? 'Active' : (needsAttention > 0 ? `${needsAttention} To check` : 'All clear')}
          badgeColor={isNeedsAttentionActive ? 'bg-trust-navy text-white border-trust-navy' : (needsAttention > 0 ? 'bg-rose-50 text-rose-700 border-rose-200' : 'bg-emerald-50 text-trust-green border-emerald-200')}
          className="col-span-2 lg:col-span-1"
          active={isNeedsAttentionActive}
          onClick={() => handleCardClick('Needs Attention')}
        />
      </div>
    </section>
  );
};
