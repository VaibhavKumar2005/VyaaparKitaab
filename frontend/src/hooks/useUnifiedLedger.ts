import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { isDemoMode } from '../mock/mockStore';

export interface CategoryTreeSubItem {
  subcategory: string;
  total_amount: number;
  count: number;
  percentage: number;
}

export interface CategoryTreeItem {
  category: string;
  total_amount: number;
  count: number;
  percentage: number;
  subcategories: CategoryTreeSubItem[];
}

export interface UnifiedTransactionItem {
  id: string;
  source_type: string;
  source_ref_id: string;
  invoice_id?: string | null;
  business_id?: string | null;
  customer_id?: string | null;
  direction: string;
  side: string;
  amount: number;
  paid_amount: number;
  discount_amount: number;
  tax_amount: number;
  currency: string;
  status: string;
  channel: string;
  app?: string | null;
  counterparty: string;
  narration: string;
  category: string;
  subcategory: string;
  classification_source: string;
  occurred_at: string;
}

export interface UnifiedTransactionFeedResponse {
  total_count: number;
  total_amount: number;
  total_discount_saved: number;
  total_debits: number;
  total_credits: number;
  nested_summary: Record<string, Record<string, number>>;
  category_tree: CategoryTreeItem[];
  items: UnifiedTransactionItem[];
}

export interface CustomerNotificationItem {
  id: string;
  event_type: string;
  invoice_id?: string | null;
  business_id?: string | null;
  store_name: string;
  title: string;
  message: string;
  amount: number;
  discount_amount: number;
  category: string;
  subcategory: string;
  payment_channel?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AssistantResponse {
  question: string;
  intent: string;
  answer: string;
  filters: {
    view?: string;
    period?: string;
    category?: string | null;
    subcategory?: string | null;
  };
  metrics: Record<string, number | string>;
  category_breakdown: CategoryTreeItem[];
  sample_transactions: UnifiedTransactionItem[];
}

const DEMO_UNIFIED_ITEMS: UnifiedTransactionItem[] = [
  {
    id: 'demo-uni-1',
    source_type: 'store_sale',
    source_ref_id: 'inv:demo-1',
    direction: 'CREDIT',
    side: 'BOTH',
    amount: 892.5,
    paid_amount: 892.5,
    discount_amount: 50.0,
    tax_amount: 42.5,
    currency: 'INR',
    status: 'PAID',
    channel: 'UPI',
    app: 'Google Pay',
    counterparty: 'Sharma Kirana & General Store',
    narration: 'INV-2026-101 - Aashirvaad Atta 5kg, Tata Salt 1kg',
    category: 'Food',
    subcategory: 'Grocery',
    classification_source: 'rule',
    occurred_at: new Date().toISOString(),
  },
  {
    id: 'demo-uni-2',
    source_type: 'statement_import',
    source_ref_id: 'bank:demo-2',
    direction: 'DEBIT',
    side: 'CUSTOMER',
    amount: 350.0,
    paid_amount: 350.0,
    discount_amount: 0.0,
    tax_amount: 0.0,
    currency: 'INR',
    status: 'RECORDED',
    channel: 'UPI',
    app: 'PhonePe',
    counterparty: 'Swiggy Food Delivery',
    narration: 'UPI/DR/431800112233/SWIGGY/HDFC',
    category: 'Food',
    subcategory: 'Delivery',
    classification_source: 'rule',
    occurred_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: 'demo-uni-3',
    source_type: 'personal_purchase',
    source_ref_id: 'purchase:demo-3',
    direction: 'DEBIT',
    side: 'CUSTOMER',
    amount: 1499.0,
    paid_amount: 1499.0,
    discount_amount: 0.0,
    tax_amount: 0.0,
    currency: 'INR',
    status: 'RECORDED',
    channel: 'UPI',
    app: 'Google Pay',
    counterparty: 'Amazon',
    narration: 'boAt Rockerz 450 Bluetooth Headphones',
    category: 'Shopping',
    subcategory: 'Electronics',
    classification_source: 'rule',
    occurred_at: new Date(Date.now() - 86400000 * 2).toISOString(),
  },
  {
    id: 'demo-uni-4',
    source_type: 'upi_bridge',
    source_ref_id: 'bank:demo-4',
    direction: 'DEBIT',
    side: 'CUSTOMER',
    amount: 220.0,
    paid_amount: 220.0,
    discount_amount: 0.0,
    tax_amount: 0.0,
    currency: 'INR',
    status: 'RECORDED',
    channel: 'UPI',
    app: 'Google Pay',
    counterparty: 'Uber India',
    narration: 'Uber Airport Commute Cab',
    category: 'Transport',
    subcategory: 'Cab',
    classification_source: 'explicit',
    occurred_at: new Date(Date.now() - 86400000 * 3).toISOString(),
  },
];

let demoNotificationsState: CustomerNotificationItem[] = [
  {
    id: 'demo-notif-1',
    event_type: 'purchase.recorded',
    store_name: 'Sharma Kirana & General Store',
    title: 'Receipt from Sharma Kirana & General Store',
    message: 'Purchase of ₹892.50 recorded (₹50.00 discount saved) under Food > Grocery.',
    amount: 892.5,
    discount_amount: 50.0,
    category: 'Food',
    subcategory: 'Grocery',
    payment_channel: 'UPI (Google Pay)',
    is_read: false,
    created_at: new Date().toISOString(),
  },
];

function buildDemoUnifiedFeed(params: {
  view?: 'all' | 'customer' | 'store';
  category?: string;
  subcategory?: string;
  sourceType?: string;
}): UnifiedTransactionFeedResponse {
  const filtered = DEMO_UNIFIED_ITEMS.filter((item) => {
    if (params.view === 'store' && item.source_type !== 'store_sale') return false;
    if (params.category && item.category !== params.category) return false;
    if (params.subcategory && item.subcategory !== params.subcategory) return false;
    if (params.sourceType && item.source_type !== params.sourceType) return false;
    return true;
  });
  const totalAmount = Number(filtered.reduce((acc, r) => acc + r.amount, 0).toFixed(2));
  const totalDiscount = Number(filtered.reduce((acc, r) => acc + r.discount_amount, 0).toFixed(2));
  const totalDebits = Number(filtered.filter((r) => r.direction === 'DEBIT').reduce((a, r) => a + r.amount, 0).toFixed(2));
  const totalCredits = Number(filtered.filter((r) => r.direction === 'CREDIT').reduce((a, r) => a + r.amount, 0).toFixed(2));

  const nested: Record<string, Record<string, number>> = {};
  const counts: Record<string, Record<string, number>> = {};
  for (const r of filtered) {
    nested[r.category] = nested[r.category] ?? {};
    counts[r.category] = counts[r.category] ?? {};
    nested[r.category][r.subcategory] = Number(((nested[r.category][r.subcategory] ?? 0) + r.amount).toFixed(2));
    counts[r.category][r.subcategory] = (counts[r.category][r.subcategory] ?? 0) + 1;
  }
  const denom = totalAmount > 0 ? totalAmount : 1;
  const categoryTree: CategoryTreeItem[] = Object.entries(nested)
    .map(([category, subs]) => {
      const catTotal = Number(Object.values(subs).reduce((a, b) => a + b, 0).toFixed(2));
      const catCount = Object.values(counts[category]).reduce((a, b) => a + b, 0);
      const catDenom = catTotal > 0 ? catTotal : 1;
      return {
        category,
        total_amount: catTotal,
        count: catCount,
        percentage: Number(((catTotal / denom) * 100).toFixed(1)),
        subcategories: Object.entries(subs).map(([subcategory, amt]) => ({
          subcategory,
          total_amount: amt,
          count: counts[category][subcategory],
          percentage: Number(((amt / catDenom) * 100).toFixed(1)),
        })),
      };
    })
    .sort((a, b) => b.total_amount - a.total_amount);

  return {
    total_count: filtered.length,
    total_amount: totalAmount,
    total_discount_saved: totalDiscount,
    total_debits: totalDebits,
    total_credits: totalCredits,
    nested_summary: nested,
    category_tree: categoryTree,
    items: filtered,
  };
}

function buildDemoAssistantResponse(question: string): AssistantResponse {
  const low = question.toLowerCase();
  if (low.includes('profit')) {
    return {
      question,
      intent: 'store_profit',
      answer: 'Demo Store net profit is ₹18,450.00 (Sales: ₹26,800.00, Supplier Purchases: ₹8,350.00, Discounts given: ₹320.00).',
      filters: { view: 'store', period: 'this month' },
      metrics: { net_profit: 18450 },
      category_breakdown: [],
      sample_transactions: [],
    };
  }
  if (low.includes('restock') || low.includes('stock')) {
    return {
      question,
      intent: 'restock_alert',
      answer: 'Demo Store should restock 2 product(s): Tata Salt Vacuum 1kg (3 left), Fortune Sunlite 1L (1 left).',
      filters: { view: 'store', period: 'current inventory' },
      metrics: { low_stock_count: 2 },
      category_breakdown: [],
      sample_transactions: [],
    };
  }
  if (low.includes('discount') || low.includes('saved')) {
    return {
      question,
      intent: 'discount_savings',
      answer: 'You saved ₹50.00 in total discounts across 4 sample transaction(s) (this month).',
      filters: { view: 'customer', period: 'this month' },
      metrics: { total_discount_saved: 50.0 },
      category_breakdown: [],
      sample_transactions: [],
    };
  }
  if (low.includes('food')) {
    return {
      question,
      intent: 'category_spend',
      answer: 'You spent ₹1,242.50 on Food (this month) across 2 transaction(s). Breakdown: Grocery: ₹892.50, Delivery: ₹350.00.',
      filters: { view: 'customer', period: 'this month', category: 'Food' },
      metrics: { total_amount: 1242.5 },
      category_breakdown: [],
      sample_transactions: [],
    };
  }
  return {
    question,
    intent: 'overall_summary',
    answer: 'Sample Demo summary: ₹2,961.50 tracked across 4 normalized transactions (₹50.00 saved in discounts).',
    filters: { view: 'all', period: 'all recorded dates' },
    metrics: { total_amount: 2961.5 },
    category_breakdown: [],
    sample_transactions: [],
  };
}

export function useUnifiedTransactions(params: {
  view?: 'all' | 'customer' | 'store';
  category?: string;
  subcategory?: string;
  sourceType?: string;
} = {}) {
  const view = params.view ?? 'all';
  return useQuery<UnifiedTransactionFeedResponse>({
    queryKey: ['unified_transactions', view, params.category ?? '', params.subcategory ?? '', params.sourceType ?? ''],
    queryFn: async () => {
      if (isDemoMode()) {
        return buildDemoUnifiedFeed(params);
      }
      const qs = new URLSearchParams({ view, limit: '200' });
      if (params.category) qs.set('category', params.category);
      if (params.subcategory) qs.set('subcategory', params.subcategory);
      if (params.sourceType) qs.set('source_type', params.sourceType);
      return await apiFetch<UnifiedTransactionFeedResponse>(`/transactions/unified?${qs.toString()}`);
    },
    refetchInterval: 15000,
  });
}

export function useCustomerNotifications() {
  return useQuery<CustomerNotificationItem[]>({
    queryKey: ['portal_notifications'],
    queryFn: async () => {
      if (isDemoMode()) {
        return demoNotificationsState;
      }
      return await apiFetch<CustomerNotificationItem[]>('/portal/notifications?limit=40');
    },
    refetchInterval: 15000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (notificationId?: string) => {
      if (isDemoMode()) {
        demoNotificationsState = demoNotificationsState.map((n) =>
          !notificationId || n.id === notificationId ? { ...n, is_read: true } : n
        );
        return { status: 'ok', updated: demoNotificationsState.length };
      }
      const path = notificationId
        ? `/portal/notifications/${notificationId}/read`
        : '/portal/notifications/read-all';
      return await apiFetch<{ status: string; updated: number }>(path, { method: 'POST' });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portal_notifications'] });
    },
  });
}

export function useFinancialAssistant() {
  return useMutation({
    mutationFn: async (question: string) => {
      if (isDemoMode()) {
        return buildDemoAssistantResponse(question);
      }
      return await apiFetch<AssistantResponse>('/ai/assistant', {
        method: 'POST',
        body: JSON.stringify({ question }),
      });
    },
  });
}

export function useUpdateUnifiedCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { transactionId: string; category: string; subcategory?: string }) => {
      if (isDemoMode()) {
        const idx = DEMO_UNIFIED_ITEMS.findIndex((i) => i.id === params.transactionId);
        if (idx >= 0) {
          DEMO_UNIFIED_ITEMS[idx] = {
            ...DEMO_UNIFIED_ITEMS[idx],
            category: params.category,
            subcategory: params.subcategory ?? DEMO_UNIFIED_ITEMS[idx].subcategory,
            classification_source: 'user_learned',
          };
          return DEMO_UNIFIED_ITEMS[idx];
        }
        throw new Error('Demo transaction not found');
      }
      return await apiFetch<UnifiedTransactionItem>(`/transactions/unified/${params.transactionId}/category`, {
        method: 'PATCH',
        body: JSON.stringify({ category: params.category, subcategory: params.subcategory }),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['unified_transactions'] });
    },
  });
}
