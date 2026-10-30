import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { isDemoMode } from '../mock/mockStore';

export type PaymentSummaryItem = {
  app: string;
  amount: number;
  count: number;
  percentage: number;
};

export type DailyPaymentSeries = {
  date: string;
  total: number;
  google_pay: number;
  phonepe: number;
  paytm: number;
  other: number;
  count: number;
};

export type RecentPayment = {
  id: string;
  payment_id: string;
  amount: number;
  app: string;
  method: string;
  vpa?: string | null;
  invoice_id: string;
  status: string;
  created_at: string;
};

export type PaymentSummaryData = {
  period: string;
  total_collected: number;
  total_transactions: number;
  by_app: PaymentSummaryItem[];
  by_method: Array<{ method: string; amount: number; count: number; percentage: number }>;
  daily_series: DailyPaymentSeries[];
  recent_payments: RecentPayment[];
};

export const MOCK_PAYMENT_SUMMARY: PaymentSummaryData = {
  period: '30d',
  total_collected: 74000.0,
  total_transactions: 48,
  by_app: [
    { app: 'Google Pay', amount: 38480.0, count: 24, percentage: 52.0 },
    { app: 'PhonePe', amount: 21460.0, count: 14, percentage: 29.0 },
    { app: 'Paytm', amount: 9620.0, count: 7, percentage: 13.0 },
    { app: 'Other UPI', amount: 4440.0, count: 3, percentage: 6.0 },
  ],
  by_method: [
    { method: 'UPI', amount: 74000.0, count: 48, percentage: 100.0 },
  ],
  daily_series: [
    { date: '10-23', total: 6800, google_pay: 3500, phonepe: 2100, paytm: 800, other: 400, count: 4 },
    { date: '10-24', total: 8400, google_pay: 4200, phonepe: 2600, paytm: 1100, other: 500, count: 5 },
    { date: '10-25', total: 7200, google_pay: 3800, phonepe: 2000, paytm: 900, other: 500, count: 5 },
    { date: '10-26', total: 9500, google_pay: 5100, phonepe: 2800, paytm: 1200, other: 400, count: 6 },
    { date: '10-27', total: 11200, google_pay: 6000, phonepe: 3100, paytm: 1500, other: 600, count: 7 },
    { date: '10-28', total: 10400, google_pay: 5400, phonepe: 3000, paytm: 1400, other: 600, count: 7 },
    { date: '10-29', total: 9800, google_pay: 5100, phonepe: 2860, paytm: 1320, other: 520, count: 6 },
    { date: '10-30', total: 10700, google_pay: 5380, phonepe: 3000, paytm: 1400, other: 920, count: 8 },
  ],
  recent_payments: [
    {
      id: 'p-1',
      payment_id: 'pay_live_001_gpay',
      amount: 24850.0,
      app: 'Google Pay',
      method: 'UPI',
      vpa: 'customer@okhdfcbank',
      invoice_id: 'INV-2026-001',
      status: 'captured',
      created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    },
    {
      id: 'p-2',
      payment_id: 'pay_live_002_phonepe',
      amount: 18900.0,
      app: 'PhonePe',
      method: 'UPI',
      vpa: 'user@ybl',
      invoice_id: 'INV-2026-004',
      status: 'captured',
      created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    },
    {
      id: 'p-3',
      payment_id: 'pay_live_003_paytm',
      amount: 15300.0,
      app: 'Paytm',
      method: 'UPI',
      vpa: 'retail@paytm',
      invoice_id: 'INV-2026-010',
      status: 'captured',
      created_at: new Date(Date.now() - 1000 * 60 * 240).toISOString(),
    },
  ],
};

export function usePaymentSummary(period: string = '30d') {
  return useQuery({
    queryKey: ['payments', 'summary', period],
    queryFn: async (): Promise<PaymentSummaryData> => {
      if (isDemoMode()) {
        return MOCK_PAYMENT_SUMMARY;
      }
      try {
        const data = await apiFetch<PaymentSummaryData>(`/payments/summary?period=${period}`);
        // If live DB has no transactions recorded yet, show fallback template with empty flag
        if (!data || data.total_transactions === 0) {
          return {
            ...data,
            by_app: data.by_app?.length ? data.by_app : [],
            daily_series: data.daily_series?.length ? data.daily_series : [],
          };
        }
        return data;
      } catch {
        return MOCK_PAYMENT_SUMMARY;
      }
    },
    staleTime: 5000,
  });
}

