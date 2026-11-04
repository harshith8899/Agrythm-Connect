import React from 'react';
import { 
  PhoneCall, 
  CheckCircle2,
  Users, 
  RefreshCw,
  ShieldAlert
} from 'lucide-react';
import { OverviewCard } from './OverviewCard';

export const KpiMetrics = ({ metrics }) => {
  const totalCalls = metrics.totalCalls || 0;
  const completedCount = metrics.completedCount || metrics.deliveredCount || 0;
  const farmersReached = metrics.farmersReached ?? 0;
  const retryingCount = metrics.retryingCount || 0;
  const escalationCount = metrics.escalationCount || 0;

  const completionPct = totalCalls > 0 ? `${Math.round((completedCount / totalCalls) * 100)}%` : '0%';

  return (
    <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
      {/* 1. Total Calls */}
      <OverviewCard
        title="Total Voice Calls"
        value={totalCalls}
        subtitle={`${completedCount} delivered / answered`}
        icon={PhoneCall}
        badge={totalCalls > 0 ? "Active Stream" : "Ready"}
      />

      {/* 2. Calls Completed */}
      <OverviewCard
        title="Calls Completed"
        value={completedCount}
        subtitle={`${completionPct} delivery rate`}
        icon={CheckCircle2}
        badge={completedCount > 0 ? `${completionPct} Success` : "Pending"}
      />

      {/* 3. Farmers Reached */}
      <OverviewCard
        title="Farmers Reached"
        value={farmersReached}
        subtitle={`${farmersReached} unique farmers talked`}
        icon={Users}
        badge={farmersReached > 0 ? "Engaged" : "Ready"}
      />

      {/* 4. Retrying */}
      <OverviewCard
        title="Retrying (In Cycle)"
        value={retryingCount}
        subtitle="Max 2-retry cycle enforced"
        icon={RefreshCw}
        badge={retryingCount > 0 ? `${retryingCount} Pending` : "Clear"}
      />

      {/* 5. Escalations */}
      <OverviewCard
        title="Agronomic Escalations"
        value={escalationCount}
        subtitle="Non-weather boundary guard"
        icon={ShieldAlert}
        badge={escalationCount > 0 ? "Escalated" : "Guardrail Active"}
      />
    </section>
  );
};
