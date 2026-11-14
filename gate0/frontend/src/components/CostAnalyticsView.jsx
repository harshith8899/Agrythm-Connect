// Cost Analytics and System Status are unified under SystemStatusView.
// Re-exporting SystemStatusView ensures full backwards compatibility with any legacy imports.
export { SystemStatusView as CostAnalyticsView } from './SystemStatusView';
