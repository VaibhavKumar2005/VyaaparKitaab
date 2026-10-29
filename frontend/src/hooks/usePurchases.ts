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
  type: 'SOURCE' | 'GATEWAY' | 'MERCHANT' | 'ORDER';
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

export interface PayeeSummaryItem {
  payee_name: string;
  payee_type: string;
  total_paid: number;
  share_percentage: number;
  payment_count: number;
  avg_payment: number;
  last_paid_at: string;
  primary_channel: string;
  recency_days: number;
  ml_cluster_label: string;
  pca_x: number;
  pca_y: number;
}

export interface PaymentChannelSummaryItem {
  channel: string;
  total_paid: number;
  percentage: number;
  transaction_count: number;
}

export interface PaymentAnomalyItem {
  payee_name: string;
  amount: number;
  paid_at: string;
  channel: string;
  note: string;
}

export interface OutgoingPaymentsSummaryResponse {
  total_paid_to_others: number;
  total_transactions: number;
  unique_payees_count: number;
  top_payee_name: string;
  top_payee_amount: number;
  predicted_7d_outflow: number;
  predicted_30d_outflow: number;
  ai_summary_text: string;
  ml_models_used: {
    regression_model?: string;
    clustering_model?: string;
    clustering_silhouette_score?: number;
    anomaly_detector?: string;
  };
  payee_summary: PayeeSummaryItem[];
  payment_app_summary: PaymentChannelSummaryItem[];
  anomalies: PaymentAnomalyItem[];
}

export interface StoreOptionItem {
  store_name: string;
  store_type: string;
  total_spent: number;
  transaction_count: number;
  last_tx_at: string;
}

export interface StoreTransactionPoint {
  id: string;
  date: string;
  paid_at: string;
  amount: number;
  cumulative_amount: number;
  order_id: string;
  items_note: string;
  payment_method: string;
  category: string;
}

export interface StoreMethodSplitItem {
  method: string;
  amount: number;
  percentage: number;
  count: number;
}

export interface StoreCategorySplitItem {
  category: string;
  amount: number;
  percentage: number;
  count: number;
}

export interface StoreDrilldownResponse {
  selected_store: string;
  store_type: string;
  total_spent: number;
  share_of_wallet_pct: number;
  transaction_count: number;
  avg_order_value: number;
  max_order_value: number;
  min_order_value: number;
  predicted_next_order: number;
  available_stores: StoreOptionItem[];
  transactions_timeline: StoreTransactionPoint[];
  payment_method_split: StoreMethodSplitItem[];
  category_split: StoreCategorySplitItem[];
  store_flow_nodes: TransactionGraphNode[];
  store_flow_edges: TransactionGraphEdge[];
}

const mockStoreTransactionsCatalog: Record<
  string,
  {
    store_type: string;
    txs: Array<{
      id: string;
      date: string;
      amount: number;
      order_id: string;
      items_note: string;
      payment_method: string;
      category: string;
    }>;
  }
> = {
  Amazon: {
    store_type: 'Marketplace / App',
    txs: [
      {
        id: 'amz-1',
        date: '2026-10-08',
        amount: 1299,
        order_id: '404-1122334-5566771',
        items_note: 'Logitech M331 Silent Plus Wireless Mouse',
        payment_method: 'UPI (Google Pay)',
        category: 'Electronics',
      },
      {
        id: 'amz-2',
        date: '2026-10-14',
        amount: 2199,
        order_id: '404-3981726-1928374',
        items_note: 'Samsung EVO Plus 256GB microSDXC UHS-I Card',
        payment_method: 'UPI (Google Pay)',
        category: 'Electronics',
      },
      {
        id: 'amz-3',
        date: '2026-10-21',
        amount: 2203,
        order_id: '404-6655443-9988112',
        items_note: 'Milton Thermosteel Flask 1L + Kitchen Containers Set',
        payment_method: 'UPI (PhonePe)',
        category: 'Home & Kitchen',
      },
      {
        id: 'amz-4',
        date: '2026-10-27',
        amount: 1499,
        order_id: '404-7123456-7890123',
        items_note: 'boAt Rockerz 450 Bluetooth On Ear Headphones',
        payment_method: 'UPI (Google Pay)',
        category: 'Electronics',
      },
    ],
  },
  Flipkart: {
    store_type: 'Marketplace / App',
    txs: [
      {
        id: 'flp-1',
        date: '2026-10-12',
        amount: 951,
        order_id: 'OD4291827364519201',
        items_note: 'Casio Vintage Digital Watch Strap & Screen Guard',
        payment_method: 'UPI (PhonePe)',
        category: 'Accessories',
      },
      {
        id: 'flp-2',
        date: '2026-10-24',
        amount: 2499,
        order_id: 'OD30492817264819203',
        items_note: 'Men Slim Fit Solid Spread Collar Casual Shirt (Pack of 2)',
        payment_method: 'UPI (PhonePe)',
        category: 'Shopping & Apparel',
      },
    ],
  },
  Blinkit: {
    store_type: 'Marketplace / App',
    txs: [
      {
        id: 'blk-1',
        date: '2026-10-16',
        amount: 850,
        order_id: 'BLK-88912031',
        items_note: 'Aashirvaad Select Atta 5kg + Amul Butter 500g + Milk',
        payment_method: 'UPI (Google Pay)',
        category: 'Groceries & Instant',
      },
      {
        id: 'blk-2',
        date: '2026-10-25',
        amount: 1350,
        order_id: 'BLK-99201445',
        items_note: 'Fortune Sunlite Oil 2L + Tata Sampann Toor Dal 2kg + Dry Fruits',
        payment_method: 'UPI (Google Pay)',
        category: 'Groceries & Instant',
      },
    ],
  },
  'Sharma Kirana & General Store': {
    store_type: 'Retail Store',
    txs: [
      {
        id: 'skr-1',
        date: '2026-10-10',
        amount: 640,
        order_id: 'INV-SK-104',
        items_note: 'Basmati Rice 5kg + Loose Spices',
        payment_method: 'UPI (Paytm)',
        category: 'Groceries & Retail',
      },
      {
        id: 'skr-2',
        date: '2026-10-22',
        amount: 1120,
        order_id: 'INV-SK-119',
        items_note: 'Monthly Ration Pack (Sugar, Tea, Pulses, Detergents)',
        payment_method: 'UPI (Google Pay)',
        category: 'Groceries & Retail',
      },
    ],
  },
};

function buildMockStoreDrilldown(requestedStore?: string | null): StoreDrilldownResponse {
  const storeNames = Object.keys(mockStoreTransactionsCatalog);
  const available_stores: StoreOptionItem[] = storeNames
    .map((sName) => {
      const entry = mockStoreTransactionsCatalog[sName];
      const total = entry.txs.reduce((acc, t) => acc + t.amount, 0);
      const lastDate = entry.txs[entry.txs.length - 1]?.date || '2026-10-27';
      return {
        store_name: sName,
        store_type: entry.store_type,
        total_spent: total,
        transaction_count: entry.txs.length,
        last_tx_at: `${lastDate}T12:00:00Z`,
      };
    })
    .sort((a, b) => b.total_spent - a.total_spent);

  const grandTotal = available_stores.reduce((acc, s) => acc + s.total_spent, 0);
  const targetStore =
    (requestedStore &&
      storeNames.find((s) => s.toLowerCase() === requestedStore.toLowerCase() || s.toLowerCase().includes(requestedStore.toLowerCase()))) ||
    available_stores[0].store_name;

  const storeData = mockStoreTransactionsCatalog[targetStore];
  let running = 0;
  const transactions_timeline: StoreTransactionPoint[] = storeData.txs.map((tx) => {
    running += tx.amount;
    return {
      ...tx,
      paid_at: `${tx.date}T12:00:00Z`,
      cumulative_amount: running,
    };
  });

  const total_spent = running;
  const transaction_count = storeData.txs.length;
  const avg_order_value = Math.round(total_spent / Math.max(transaction_count, 1));
  const amounts = storeData.txs.map((t) => t.amount);
  const max_order_value = Math.max(...amounts);
  const min_order_value = Math.min(...amounts);
  const predicted_next_order = Math.round(amounts[amounts.length - 1] * 0.6 + avg_order_value * 0.4);

  const methodMap: Record<string, { amount: number; count: number }> = {};
  const catMap: Record<string, { amount: number; count: number }> = {};
  for (const tx of storeData.txs) {
    if (!methodMap[tx.payment_method]) methodMap[tx.payment_method] = { amount: 0, count: 0 };
    methodMap[tx.payment_method].amount += tx.amount;
    methodMap[tx.payment_method].count += 1;

    if (!catMap[tx.category]) catMap[tx.category] = { amount: 0, count: 0 };
    catMap[tx.category].amount += tx.amount;
    catMap[tx.category].count += 1;
  }

  const payment_method_split: StoreMethodSplitItem[] = Object.entries(methodMap)
    .map(([method, info]) => ({
      method,
      amount: info.amount,
      percentage: Number(((info.amount / Math.max(total_spent, 1)) * 100).toFixed(1)),
      count: info.count,
    }))
    .sort((a, b) => b.amount - a.amount);

  const category_split: StoreCategorySplitItem[] = Object.entries(catMap)
    .map(([category, info]) => ({
      category,
      amount: info.amount,
      percentage: Number(((info.amount / Math.max(total_spent, 1)) * 100).toFixed(1)),
      count: info.count,
    }))
    .sort((a, b) => b.amount - a.amount);

  const store_flow_nodes: TransactionGraphNode[] = [
    {
      id: 'bank_source',
      label: 'Your Bank Account',
      type: 'SOURCE',
      subtext: `Total Debited for ${targetStore}`,
      total_volume: total_spent,
      order_count: transaction_count,
    },
    {
      id: 'store_hub',
      label: targetStore,
      type: 'MERCHANT',
      subtext: storeData.store_type,
      total_volume: total_spent,
      order_count: transaction_count,
    },
  ];
  const store_flow_edges: TransactionGraphEdge[] = [];

  payment_method_split.forEach((m, idx) => {
    const gwId = `gw_${idx}`;
    store_flow_nodes.push({
      id: gwId,
      label: m.method,
      type: 'GATEWAY',
      subtext: `${m.percentage}% of store spend`,
      total_volume: m.amount,
      order_count: m.count,
    });
    store_flow_edges.push({
      from_node: 'bank_source',
      to_node: gwId,
      amount: m.amount,
      order_count: m.count,
      status: 'CONFIRMED',
    });
    store_flow_edges.push({
      from_node: gwId,
      to_node: 'store_hub',
      amount: m.amount,
      order_count: m.count,
      status: 'CONFIRMED',
    });
  });

  transactions_timeline.forEach((tx, idx) => {
    const ordId = `ord_${idx}`;
    store_flow_nodes.push({
      id: ordId,
      label: `#${tx.order_id.slice(0, 14)}`,
      type: 'ORDER',
      subtext: `${tx.date} · ${tx.items_note.slice(0, 26)}`,
      total_volume: tx.amount,
      order_count: 1,
    });
    store_flow_edges.push({
      from_node: 'store_hub',
      to_node: ordId,
      amount: tx.amount,
      order_count: 1,
      status: 'CONFIRMED',
    });
  });

  return {
    selected_store: targetStore,
    store_type: storeData.store_type,
    total_spent,
    share_of_wallet_pct: Number(((total_spent / Math.max(grandTotal, 1)) * 100).toFixed(1)),
    transaction_count,
    avg_order_value,
    max_order_value,
    min_order_value,
    predicted_next_order,
    available_stores,
    transactions_timeline,
    payment_method_split,
    category_split,
    store_flow_nodes,
    store_flow_edges,
  };
}

const mockPaymentsToOthers: OutgoingPaymentsSummaryResponse = {
  total_paid_to_others: 12850,
  total_transactions: 8,
  unique_payees_count: 3,
  top_payee_name: 'Amazon',
  top_payee_amount: 7200,
  predicted_7d_outflow: 3150,
  predicted_30d_outflow: 13500,
  ai_summary_text:
    'You have made 8 payment(s) totalling ₹12,850.00 across 3 recipient(s). Your largest payee is Amazon (₹7,200.00, 56.0% of all outflows), primarily paid via UPI (Google Pay). Based on RidgeRegression time-series regression, your projected outflow over the next 7 days is ₹3,150.00.',
  ml_models_used: {
    regression_model: 'RidgeRegression',
    clustering_model: 'KMeans + StandardScaler + PCA',
    clustering_silhouette_score: 0.642,
    anomaly_detector: 'IsolationForest (contamination=0.15)',
  },
  payee_summary: [
    {
      payee_name: 'Amazon',
      payee_type: 'Marketplace / App',
      total_paid: 7200,
      share_percentage: 56.0,
      payment_count: 4,
      avg_payment: 1800,
      last_paid_at: new Date().toISOString(),
      primary_channel: 'UPI (Google Pay)',
      recency_days: 0.2,
      ml_cluster_label: 'High-Value Regular Payee',
      pca_x: 1.42,
      pca_y: 0.18,
    },
    {
      payee_name: 'Flipkart',
      payee_type: 'Marketplace / App',
      total_paid: 3450,
      share_percentage: 26.8,
      payment_count: 2,
      avg_payment: 1725,
      last_paid_at: new Date(Date.now() - 86400000 * 2).toISOString(),
      primary_channel: 'UPI (PhonePe)',
      recency_days: 2.0,
      ml_cluster_label: 'Frequent Everyday Payee',
      pca_x: -0.45,
      pca_y: 0.61,
    },
    {
      payee_name: 'Blinkit',
      payee_type: 'Marketplace / App',
      total_paid: 2200,
      share_percentage: 17.2,
      payment_count: 2,
      avg_payment: 1100,
      last_paid_at: new Date(Date.now() - 86400000 * 4).toISOString(),
      primary_channel: 'UPI (Google Pay)',
      recency_days: 4.0,
      ml_cluster_label: 'Occasional / One-Time Payee',
      pca_x: -0.97,
      pca_y: -0.79,
    },
  ],
  payment_app_summary: [
    { channel: 'UPI (Google Pay)', total_paid: 9400, percentage: 73.2, transaction_count: 6 },
    { channel: 'UPI (PhonePe)', total_paid: 3450, percentage: 26.8, transaction_count: 2 },
  ],
  anomalies: [],
};

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
      queryClient.invalidateQueries({ queryKey: ['transaction_graph'] });
      queryClient.invalidateQueries({ queryKey: ['payments_to_others_summary'] });
      queryClient.invalidateQueries({ queryKey: ['store_drilldown'] });
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
      queryClient.invalidateQueries({ queryKey: ['transaction_graph'] });
      queryClient.invalidateQueries({ queryKey: ['payments_to_others_summary'] });
      queryClient.invalidateQueries({ queryKey: ['store_drilldown'] });
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

export function usePaymentsToOthersSummary() {
  return useQuery<OutgoingPaymentsSummaryResponse>({
    queryKey: ['payments_to_others_summary'],
    queryFn: async () => {
      if (isDemoMode()) {
        return mockPaymentsToOthers;
      }
      try {
        return await apiFetch<OutgoingPaymentsSummaryResponse>('/purchases/payments-to-others');
      } catch {
        return mockPaymentsToOthers;
      }
    },
    refetchInterval: 15000,
  });
}

export function useStoreDrilldown(selectedStore: string | null) {
  return useQuery<StoreDrilldownResponse>({
    queryKey: ['store_drilldown', selectedStore || 'default'],
    queryFn: async () => {
      if (isDemoMode()) {
        return buildMockStoreDrilldown(selectedStore);
      }
      try {
        const queryParam = selectedStore ? `?store=${encodeURIComponent(selectedStore)}` : '';
        const res = await apiFetch<StoreDrilldownResponse>(`/purchases/store-drilldown${queryParam}`);
        if (res.available_stores.length === 0) {
          return buildMockStoreDrilldown(selectedStore);
        }
        return res;
      } catch {
        return buildMockStoreDrilldown(selectedStore);
      }
    },
    refetchInterval: 15000,
  });
}

