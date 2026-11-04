import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for managing dashboard telemetry, orchestrator status, and metrics state
 */
export const useDashboardData = () => {
  const [loading, setLoading] = useState(false);
  const [orchestratorStatus, setOrchestratorStatus] = useState({
    enabled: true,
    scheduledTime: '09:00 AM IST',
    systemStatus: 'Operational',
  });
  const [metrics, setMetrics] = useState({
    activeSensors: 48,
    totalAreaCovered: '1,240 Ha',
    aiConfidenceScore: '98.5%',
    systemStatus: 'Operational',
  });

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/orchestrator/status');
      if (res.ok) {
        const data = await res.json();
        setOrchestratorStatus(data);
        setMetrics(prev => ({
          ...prev,
          systemStatus: data.systemStatus || 'Operational'
        }));
      }
    } catch {
      // Backend offline fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return {
    metrics,
    orchestratorStatus,
    loading,
    setLoading,
    setMetrics,
    refreshStatus: fetchStatus
  };
};
