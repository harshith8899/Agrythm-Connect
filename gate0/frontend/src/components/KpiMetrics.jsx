import React from 'react';
import { 
  PhoneCall, 
  CheckCircle2,
  Clock, 
  RefreshCw,
  ShieldAlert
} from 'lucide-react';
import { OverviewCard } from './OverviewCard';

export const KpiMetrics = ({ metrics }) => {
  const totalCalls = metrics.totalCalls || 0;
  const completedCount = metrics.completedCount || metrics.deliveredCount || 0;
  const callbacksScheduled = metrics.callbacksScheduled ?? metrics.callbackCount ?? 0;
  const retryingCount = metrics.retryingCount || 0;
  const needsAttention = metrics.needsAttentionCount || 0;

  const completionPct = totalCalls > 0 ? `${Math.round((completedCount / totalCalls) * 100)}%` : '0%';

  return (
    <section className="grid grid-cols-2 lg:grid-cols-5 gap-2.5 sm:gap-3.5">
      {/* 1. Total Voice Calls */}
      <OverviewCard
        title="Total Voice Calls"
        value={totalCalls}
        subtitle="Total calls done today"
        icon={PhoneCall}
        badge={totalCalls > 0 ? "Daily Volume" : "Ready"}
      />

      {/* 2. Calls Completed */}
      <OverviewCard
        title="Calls Completed"
        value={completedCount}
        subtitle={`${completionPct} completed successfully`}
        icon={CheckCircle2}
        badge={completedCount > 0 ? `${completionPct} Completed` : "Pending"}
      />

      {/* 3. Callbacks Scheduled */}
      <OverviewCard
        title="Callbacks Scheduled"
        value={callbacksScheduled}
        subtitle={callbacksScheduled > 0 ? "Awaiting callback execution" : "All callbacks fulfilled"}
        icon={Clock}
        badge={callbacksScheduled > 0 ? `${callbacksScheduled} Pending` : "None Pending"}
      />

      {/* 4. Retrying (In Cycle) */}
      <OverviewCard
        title="Unanswered"
        value={retryingCount}
        subtitle="No answer or busy, awaiting a retry"
        icon={RefreshCw}
        badge={retryingCount > 0 ? `${retryingCount} Pending` : "Clear"}
      />

      {/* 5. Needs attention */}
      <OverviewCard
        title="Needs Attention"
        value={needsAttention}
        subtitle="Failed calls or weather not confirmed by the farmer"
        icon={ShieldAlert}
        badge={needsAttention > 0 ? `${needsAttention} To Check` : "All Clear"}
        className="col-span-2 lg:col-span-1"
      />
    </section>
  );
};
