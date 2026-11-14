import React from 'react';
import { 
  PhoneCall, 
  CheckCircle2,
  Clock, 
  RefreshCw,
  ShieldAlert
} from 'lucide-react';
import { OverviewCard } from './OverviewCard';

export const KpiMetrics = ({ metrics, loading = false }) => {
  const called = metrics.totalCalls || 0;
  const completed = metrics.completedCount || 0;
  const callbacks = metrics.callbacksScheduled || 0;
  const unanswered = metrics.retryingCount || 0;
  const needsAttention = metrics.needsAttentionCount || 0;
  const skipped = metrics.skippedCount || 0;
  const inProgress = metrics.inProgressCount || 0;
  const scope = metrics.scopeLabel || 'All dates';
  const completionPct = called > 0 ? `${Math.round((completed / called) * 100)}%` : '0%';

  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-1 text-[11px] text-slate-500">
        <span>Summary for <strong className="text-slate-800">{scope}</strong>, counted per farmer</span>
        {inProgress > 0 && <span className="font-semibold text-blue-700">{inProgress} in progress, counted when they end</span>}
        {skipped > 0 && <span>{skipped} skipped (no consent, inactive or no weather), not counted</span>}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2.5 sm:gap-3.5">
        <OverviewCard
          loading={loading}
          title="Farmers Called"
          value={called}
          subtitle="Farmers with at least one call"
          icon={PhoneCall}
          badge={called > 0 ? scope : 'None yet'}
        />
        <OverviewCard
          loading={loading}
          title="Completed"
          value={completed}
          subtitle={`${completionPct} of farmers called understood the weather`}
          icon={CheckCircle2}
          badge={called > 0 ? completionPct : 'Pending'}
        />
        <OverviewCard
          loading={loading}
          title="Callbacks Pending"
          value={callbacks}
          subtitle="Farmers who asked to be called later"
          icon={Clock}
          badge={callbacks > 0 ? 'Waiting' : 'None'}
        />
        <OverviewCard
          loading={loading}
          title="Unanswered"
          value={unanswered}
          subtitle="Not picked up, waiting for a retry or out of attempts"
          icon={RefreshCw}
          badge={unanswered > 0 ? 'Retrying' : 'Clear'}
        />
        <OverviewCard
          loading={loading}
          title="Needs Attention"
          value={needsAttention}
          subtitle="Failed calls, or the farmer did not confirm"
          icon={ShieldAlert}
          badge={needsAttention > 0 ? 'To check' : 'All clear'}
          className="col-span-2 lg:col-span-1"
        />
      </div>
    </section>
  );
};
