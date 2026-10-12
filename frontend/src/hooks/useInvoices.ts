import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

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
    queryFn: () => apiFetch<Invoice[]>('/invoices'),
  });
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: ['invoices', id],
    queryFn: () => apiFetch<Invoice>(`/invoices/${id}`),
    enabled: Boolean(id),
  });
}

export function useUpdateInvoiceStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch<Invoice>(`/invoices/${id}/status?status=${encodeURIComponent(status)}`, { method: 'PATCH' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['invoices'] }),
  });
}
