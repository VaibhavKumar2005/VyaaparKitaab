import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { isDemoMode } from '../mock/mockStore';

export interface PersonalPurchase {
  id: string;
  marketplace: string;
  category: string;
  amount: number;
  currency: string;
  purchased_at: string;
  order_id: string;
  items_note?: string | null;
  payment_method?: string | null;
  created_at: string;
  is_encrypted: boolean;
}

export interface DailySpendingItem {
  date: string;
  total_cost: number;
  order_count: number;
  marketplaces: string[];
}

export interface MarketplaceBreakdownItem {
  marketplace: string;
  total_cost: number;
  percentage: number;
  order_count: number;
}

export interface CategoryBreakdownItem {
  category: string;
  total_cost: number;
  percentage: number;
}

export interface PersonalSpendingAnalytics {
  today_cost: number;
  week_cost: number;
  month_cost: number;
  total_orders: number;
  daily_trend: DailySpendingItem[];
  marketplace_breakdown: MarketplaceBreakdownItem[];
  category_breakdown: CategoryBreakdownItem[];
  recent_purchases: PersonalPurchase[];
}

export interface CreatePurchasePayload {
  marketplace: string;
  category: string;
  amount: number;
  currency?: string;
  purchased_at?: string;
  order_id: string;
  items_note?: string;
  payment_method?: string;
}

export interface ParsedInvoiceResponse {
  marketplace: string;
  order_id: string | null;
  amount: number | null;
  purchased_at: string | null;
  items_summary: string | null;
  confidence: string;
}

export interface TransactionGraphNode {
  id: string;
  label: string;
  type: 'SOURCE' | 'GATEWAY' | 'MERCHANT';
  subtext: string;
  total_volume: number;
  order_count: number;
}

export interface TransactionGraphEdge {
  from_node: string;
  to_node: string;
  amount: number;
  order_count: number;
  status: string;
}

export interface TransactionGraphResponse {
  nodes: TransactionGraphNode[];
  edges: TransactionGraphEdge[];
  total_routed_volume: number;
  currency: string;
}

const mockGraph: TransactionGraphResponse = {
  total_routed_volume: 5198,
  currency: 'INR',
  nodes: [
    { id: 'user_bank', label: 'Primary Bank A/c (UPI)', type: 'SOURCE', subtext: 'Bank Debit Node', total_volume: 5198, order_count: 3 },
    { id: 'gpay', label: 'Google Pay UPI', type: 'GATEWAY', subtext: 'NPCI PSP Node', total_volume: 3998, order_count: 2 },
    { id: 'phonepe', label: 'PhonePe UPI', type: 'GATEWAY', subtext: 'NPCI PSP Node', total_volume: 1200, order_count: 1 },
    { id: 'mkt_amazon', label: 'Amazon India', type: 'MERCHANT', subtext: 'Appario Retail Pvt Ltd', total_volume: 3998, order_count: 2 },
    { id: 'mkt_flipkart', label: 'Flipkart', type: 'MERCHANT', subtext: 'RetailNet Pvt Ltd', total_volume: 1200, order_count: 1 },
  ],
  edges: [
    { from_node: 'user_bank', to_node: 'gpay', amount: 3998, order_count: 2, status: 'CONFIRMED' },
    { from_node: 'gpay', to_node: 'mkt_amazon', amount: 3998, order_count: 2, status: 'CONFIRMED' },
    { from_node: 'user_bank', to_node: 'phonepe', amount: 1200, order_count: 1, status: 'CONFIRMED' },
    { from_node: 'phonepe', to_node: 'mkt_flipkart', amount: 1200, order_count: 1, status: 'CONFIRMED' },
  ],
};

const mockAnalytics: PersonalSpendingAnalytics = {
  today_cost: 1499,
  week_cost: 4749,
  month_cost: 12850,
  total_orders: 8,
  daily_trend: [
    { date: '2026-10-17', total_cost: 1200, order_count: 1, marketplaces: ['Flipkart'] },
    { date: '2026-10-19', total_cost: 850, order_count: 1, marketplaces: ['Blinkit'] },
    { date: '2026-10-21', total_cost: 1200, order_count: 1, marketplaces: ['Amazon'] },
    { date: '2026-10-23', total_cost: 1499, order_count: 1, marketplaces: ['Amazon'] },
  ],
  marketplace_breakdown: [
    { marketplace: 'Amazon', total_cost: 7200, percentage: 56.0, order_count: 4 },
    { marketplace: 'Flipkart', total_cost: 3450, percentage: 26.8, order_count: 2 },
    { marketplace: 'Blinkit', total_cost: 2200, percentage: 17.2, order_count: 2 },
  ],
  category_breakdown: [
    { category: 'Electronics', total_cost: 5999, percentage: 46.7 },
    { category: 'Shopping & Apparel', total_cost: 3651, percentage: 28.4 },
    { category: 'Groceries & Instant', total_cost: 3200, percentage: 24.9 },
  ],
  recent_purchases: [
    {
      id: 'mock-p1',
      marketplace: 'Amazon',
      category: 'Electronics',
      amount: 1499,
      currency: 'INR',
      purchased_at: new Date().toISOString(),
      order_id: '404-7123456-7890123',
      items_note: 'boAt Rockerz 450 Bluetooth On Ear Headphones with Mic (Luscious Black)',
      payment_method: 'UPI (Google Pay)',
      created_at: new Date().toISOString(),
      is_encrypted: true,
    },
    {
      id: 'mock-p2',
      marketplace: 'Flipkart',
      category: 'Shopping & Apparel',
      amount: 2499,
      currency: 'INR',
      purchased_at: new Date(Date.now() - 86400000 * 2).toISOString(),
      order_id: 'OD30492817264819203',
      items_note: 'Men Slim Fit Solid Spread Collar Casual Shirt',
      payment_method: 'UPI (Google Pay)',
      created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
      is_encrypted: true,
    },
  ],
};

export function usePersonalSpendingAnalytics() {
  return useQuery<PersonalSpendingAnalytics>({
    queryKey: ['personal_spending_analytics'],
    queryFn: async () => {
      if (isDemoMode()) {
        return mockAnalytics;
      }
      try {
        return await apiFetch<PersonalSpendingAnalytics>('/purchases/analytics');
      } catch (err) {
        // Fallback gracefully if network drops
        return mockAnalytics;
      }
    },
    refetchInterval: 15000, // Refresh automatically every 15s to keep real-time costs up to date
  });
}

export function useCreatePersonalPurchase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreatePurchasePayload) => {
      return await apiFetch<PersonalPurchase>('/purchases', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending_analytics'] });
    },
  });
}

export function useDeletePersonalPurchase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (purchaseId: string) => {
      return await apiFetch<{ status: string; deleted_id: string }>(`/purchases/${purchaseId}`, {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending_analytics'] });
    },
  });
}

export async function parseInvoiceTextApi(text: string): Promise<ParsedInvoiceResponse> {
  return await apiFetch<ParsedInvoiceResponse>('/purchases/parse-invoice-text', {
    method: 'POST',
    body: JSON.stringify({ invoice_text: text }),
  });
}

export function useTransactionGraph() {
  return useQuery<TransactionGraphResponse>({
    queryKey: ['transaction_graph'],
    queryFn: async () => {
      if (isDemoMode()) {
        return mockGraph;
      }
      try {
        return await apiFetch<TransactionGraphResponse>('/purchases/transaction-graph');
      } catch {
        return mockGraph;
      }
    },
    refetchInterval: 15000,
  });
}

