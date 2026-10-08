import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

export type StoreDashboardData = {
  todayRevenue: number;
  totalCustomers: number;
  lowStockItems: number;
  pendingInvoices: number;
  topProducts: Array<{ name: string; sales: number }>;
  recentTransactions: Array<{ invoice_number: string; total_amount: number; status: string; created_at: string }>;
  revenueSeries: Array<{ day: string; revenue: number }>;
};

export type CustomerSummary = {
  customer_id: string;
  summary: Record<string, Record<string, number>>;
};

export function useStoreDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'store'],
    queryFn: () => apiFetch<StoreDashboardData>('/dashboard/store'),
  });
}

export function useCustomerDashboard(customerId: string) {
  return useQuery({
    queryKey: ['dashboard', 'customer', customerId],
    queryFn: () => apiFetch<CustomerSummary>(`/dashboard/customer/${customerId}`),
    enabled: Boolean(customerId),
  });
}
