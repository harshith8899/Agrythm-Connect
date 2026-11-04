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
  const escalationCount = metrics.escalationCount || 0;

  const completionPct = totalCalls > 0 ? `${Math.round((completedCount / totalCalls) * 100)}%` : '0%';

  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
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
        title="Retrying (In Cycle)"
        value={retryingCount}
        subtitle="Unanswered / Busy awaiting attempt 2 or 3"
        icon={RefreshCw}
        badge={retryingCount > 0 ? `${retryingCount} Pending` : "Clear"}
      />

      {/* 5. Agronomic Escalations */}
      <OverviewCard
        title="Agronomic Escalations"
        value={escalationCount}
        subtitle="Escalated to human extension agent"
        icon={ShieldAlert}
        badge={escalationCount > 0 ? `${escalationCount} Escalated` : "Guardrail Active"}
      />
    </section>
  );
};
