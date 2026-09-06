import { useAuth } from '../contexts/AuthContext';
import { CustomerDashboard } from './CustomerDashboard';
import { StoreDashboard } from './StoreDashboard';

export function DashboardRouter() {
  const { user } = useAuth();
  return user?.role === 'CUSTOMER' ? <CustomerDashboard /> : <StoreDashboard />;
}