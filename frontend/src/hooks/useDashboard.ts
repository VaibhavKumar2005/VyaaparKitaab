import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { getMockStoreDashboard, isDemoMode } from '../mock/mockStore';

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
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockStoreDashboard();
      }
      try {
        return await apiFetch<StoreDashboardData>('/dashboard/store');
      } catch {
        return getMockStoreDashboard();
      }
    },
  });
}

export function useCustomerDashboard(customerId: string) {
  return useQuery({
    queryKey: ['dashboard', 'customer', customerId],
    queryFn: async () => {
      if (isDemoMode()) {
        return {
          customer_id: customerId || 'cust-001',
          summary: {
            Grocery: { 'Atta & Flour': 840, 'Refined Oil': 580, 'Basmati Rice': 760 },
            Household: { 'Detergent Powder': 330, 'Bath Soap': 260 },
            Beverages: { 'Tea & Coffee': 520 },
          },
        };
      }
      try {
        return await apiFetch<CustomerSummary>(`/dashboard/customer/${customerId}`);
      } catch {
        return {
          customer_id: customerId,
          summary: {
            Grocery: { Essentials: 1200 },
          },
        };
      }
    },
    enabled: Boolean(customerId),
  });
}
