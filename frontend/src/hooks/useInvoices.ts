import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import {
  createMockPaymentOrder,
  getMockInvoice,
  getMockInvoices,
  isDemoMode,
  simulateMockPayment,
  updateMockInvoiceStatus,
} from '../mock/mockStore';

export type Invoice = {
  id: string;
  invoice_number: string;
  business_id: string;
  customer_id?: string | null;
  type: string;
  subtotal: number;
  tax_amount: number;
  discount_amount: number;
  total_amount: number;
  paid_amount: number;
  status: string;
  payment_method?: string | null;
  created_at: string;
  items: Array<{
    id: string;
    product_id: string;
    quantity: number;
    unit_price: number;
    discount: number;
    line_total: number;
  }>;
};

export function useInvoices() {
  return useQuery({
    queryKey: ['invoices'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockInvoices();
      }
      try {
        return await apiFetch<Invoice[]>('/invoices');
      } catch {
        return getMockInvoices();
      }
    },
  });
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: ['invoices', id],
    queryFn: async () => {
      if (isDemoMode()) {
        const inv = getMockInvoice(id);
        if (!inv) throw new Error('Invoice not found');
        return inv;
      }
      try {
        return await apiFetch<Invoice>(`/invoices/${id}`);
      } catch {
        const inv = getMockInvoice(id);
        if (inv) return inv;
        throw new Error('Invoice not found');
      }
    },
    enabled: Boolean(id),
  });
}

export function useUpdateInvoiceStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      if (isDemoMode()) {
        return updateMockInvoiceStatus(id, status);
      }
      return await apiFetch<Invoice>(`/invoices/${id}/status?status=${encodeURIComponent(status)}`, { method: 'PATCH' });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export type PaymentOrderData = {
  order_id: string;
  amount: number;
  currency: string;
  receipt: string;
  key_id: string;
  gateway: string;
  upi_intent?: string | null;
};

export function useCreatePaymentOrder() {
  return useMutation({
    mutationFn: async ({ invoice_id, amount }: { invoice_id: string; amount?: number }) => {
      if (isDemoMode()) {
        return createMockPaymentOrder(invoice_id, amount);
      }
      return await apiFetch<PaymentOrderData>('/payments/create-order', {
        method: 'POST',
        body: JSON.stringify({ invoice_id, amount }),
      });
    },
  });
}

export function useVerifyPayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: {
      invoice_id: string;
      order_id: string;
      payment_id: string;
      signature: string;
      method?: 'UPI' | 'CASH';
      amount?: number;
    }) => {
      if (isDemoMode()) {
        return simulateMockPayment(data.invoice_id, data.method ?? 'UPI', data.amount);
      }
      return await apiFetch<{ success: boolean; message: string; invoice_status: string }>('/payments/verify', {
        method: 'POST',
        body: JSON.stringify({
          invoice_id: data.invoice_id,
          order_id: data.order_id,
          payment_id: data.payment_id,
          signature: data.signature,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });
}
