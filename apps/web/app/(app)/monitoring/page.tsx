import { MonitoringClient } from './monitoring-client';

export const metadata = { title: 'Monitoring — OMISPHERE' };
export const dynamic = 'force-dynamic';

export default function MonitoringPage() {
  return <MonitoringClient />;
}
