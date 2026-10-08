import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

export type Invoice = {
  id: string;
  invoice_number: string;
  total_amount: number;
  status: string;
  created_at: string;
};

export function useInvoices() {
  return useQuery({
    queryKey: ['invoices'],
    queryFn: () => apiFetch<Invoice[]>('/invoices'),
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
