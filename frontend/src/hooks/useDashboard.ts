import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { getMockStoreDashboard, isDemoMode } from '../mock/mockStore';

export type StoreDashboardData = {
  todayRevenue: number;
  totalCustomers: number;
  lowStockItems: number;
  pendingInvoices: number;
  totalDiscountsGiven?: number;
  paymentBreakdown?: Array<{ method: string; amount: number; count: number }>;
  categoryBreakdown?: Array<{ category: string; amount: number; count: number }>;
  topProducts: Array<{ name: string; sales: number }>;
  recentTransactions: Array<{
    invoice_number: string;
    total_amount: number;
    discount_amount?: number;
    payment_method?: string | null;
    status: string;
    created_at: string;
  }>;
  revenueSeries: Array<{ day?: string; date?: string; revenue: number; count?: number }>;
};

export type CustomerSummary = {
  customer_id: string;
  summary: Record<string, Record<string, number>>;
};

export type AiSkuForecast = {
  product_id: string;
  name: string;
  sku: string;
  unit: string;
  current_stock: number;
  daily_velocity: number;
  forecast_7d_units: number;
  forecast_30d_units: number;
  days_to_stockout: number;
  recommended_reorder_qty: number;
  urgency: 'CRITICAL' | 'WARNING' | 'HEALTHY';
  selected_model: string;
};

export type AiForecastData = {
  generated_at: string;
  lookback_days: number;
  horizon_days: number;
  revenue_model: {
    selected_model: string;
    validation_metrics: Record<string, { mae: number; rmse: number }>;
    projected_7d_revenue: number;
    outstanding_receivables: number;
    historical_daily: Array<{ date: string; revenue: number }>;
    forecast_daily: Array<{ date: string; projected_revenue: number }>;
  };
  inventory_forecasts: AiSkuForecast[];
  critical_restock_count: number;
  insights: string[];
};

const FALLBACK_AI_FORECAST: AiForecastData = {
  generated_at: new Date().toISOString(),
  lookback_days: 30,
  horizon_days: 7,
  revenue_model: {
    selected_model: 'Holt-Linear',
    validation_metrics: {
      'SMA-7': { mae: 412.5, rmse: 518.2 },
      'Holt-Linear': { mae: 284.1, rmse: 349.6 },
    },
    projected_7d_revenue: 38450,
    outstanding_receivables: 4200,
    historical_daily: [],
    forecast_daily: [
      { date: 'Day +1', projected_revenue: 5200 },
      { date: 'Day +2', projected_revenue: 5350 },
      { date: 'Day +3', projected_revenue: 5480 },
      { date: 'Day +4', projected_revenue: 5520 },
      { date: 'Day +5', projected_revenue: 5600 },
      { date: 'Day +6', projected_revenue: 5620 },
      { date: 'Day +7', projected_revenue: 5680 },
    ],
  },
  inventory_forecasts: [
    {
      product_id: 'demo-1',
      name: 'Aashirvaad Shudh Chakki Atta (10 kg)',
      sku: 'ATT-010',
      unit: 'Bag',
      current_stock: 4,
      daily_velocity: 1.8,
      forecast_7d_units: 12.6,
      forecast_30d_units: 54,
      days_to_stockout: 2.2,
      recommended_reorder_qty: 50,
      urgency: 'CRITICAL',
      selected_model: 'Holt-Linear',
    },
    {
      product_id: 'demo-2',
      name: 'Fortune Sunlite Refined Sunflower Oil (1 L)',
      sku: 'OIL-001',
      unit: 'Pouch',
      current_stock: 14,
      daily_velocity: 2.4,
      forecast_7d_units: 16.8,
      forecast_30d_units: 72,
      days_to_stockout: 5.8,
      recommended_reorder_qty: 58,
      urgency: 'WARNING',
      selected_model: 'Holt-Linear',
    },
  ],
  critical_restock_count: 1,
  insights: [
    'Restock Alert: 1 item(s) (Aashirvaad Shudh Chakki Atta) risk stockout within 72 hours based on current sales velocity.',
    'Revenue Projection (Holt-Linear): Expected sales of ₹38,450.00 over the next 7 days.',
  ],
};

export function useStoreDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'store'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockStoreDashboard();
      }
      return await apiFetch<StoreDashboardData>('/dashboard/store');
    },
  });
}

export type CashflowHistoricalPoint = {
  date: string;
  inflow: number;
  outflow: number;
  net_cashflow: number;
  cumulative_net: number;
  rolling_7d_inflow: number;
  rolling_7d_outflow: number;
  txn_count: number;
  is_anomaly: boolean;
  anomaly_reason: string | null;
};

export type CashflowForecastPoint = {
  date: string;
  projected_inflow: number;
  inflow_lower: number;
  inflow_upper: number;
  projected_outflow: number;
  outflow_lower: number;
  outflow_upper: number;
  projected_net: number;
};

export type CashflowTimeSeriesData = {
  generated_at: string;
  lookback_days: number;
  horizon_days: number;
  granularity: 'daily' | 'weekly';
  view: 'all' | 'customer' | 'store';
  summary: {
    total_inflow: number;
    total_outflow: number;
    net_cashflow: number;
    avg_daily_inflow: number;
    avg_daily_outflow: number;
    projected_inflow_total: number;
    projected_outflow_total: number;
    projected_net_total: number;
    inflow_growth_pct: number;
    outflow_growth_pct: number;
    total_transactions: number;
    anomaly_count: number;
  };
  models: {
    inflow_selected: string;
    outflow_selected: string;
    inflow_metrics: Record<string, { mae: number; rmse: number }>;
    outflow_metrics: Record<string, { mae: number; rmse: number }>;
  };
  sources: Array<{ source: string; volume: number; count: number }>;
  historical: CashflowHistoricalPoint[];
  forecast: CashflowForecastPoint[];
  seasonality: Array<{ day: string; avg_inflow: number; avg_outflow: number; avg_net: number }>;
  anomalies: Array<{ date: string; inflow: number; outflow: number; reason: string }>;
};

export function useAiForecast() {
  return useQuery({
    queryKey: ['dashboard', 'ai-forecast'],
    queryFn: async () => {
      if (isDemoMode()) {
        return FALLBACK_AI_FORECAST;
      }
      return await apiFetch<AiForecastData>('/ai/forecast');
    },
  });
}

export function useCashflowTimeSeries(options?: {
  lookbackDays?: number;
  horizonDays?: number;
  granularity?: 'daily' | 'weekly';
  view?: 'all' | 'customer' | 'store';
}) {
  const lookback = options?.lookbackDays ?? 30;
  const horizon = options?.horizonDays ?? 14;
  const granularity = options?.granularity ?? 'daily';
  const view = options?.view ?? 'all';

  return useQuery<CashflowTimeSeriesData>({
    queryKey: ['cashflow_timeseries', lookback, horizon, granularity, view],
    queryFn: async () => {
      const params = new URLSearchParams({
        lookback_days: String(lookback),
        horizon_days: String(horizon),
        granularity,
        view,
      });
      return await apiFetch<CashflowTimeSeriesData>(`/ai/cashflow-timeseries?${params.toString()}`);
    },
    enabled: !isDemoMode(),
    staleTime: 10000,
  });
}
