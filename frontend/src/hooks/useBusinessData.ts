import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import {
  getMockBusinesses,
  getMockCustomers,
  getMockProducts,
  getMockSuppliers,
  isDemoMode,
} from '../mock/mockStore';

export type Business = {
  id: string;
  name: string;
  gstin?: string | null;
  address?: string | null;
  phone?: string | null;
  upi_vpa?: string | null;
  created_at: string;
};

export type Customer = {
  id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  business_id: string;
  created_at: string;
};

export type Product = {
  id: string;
  name: string;
  sku?: string | null;
  unit?: string | null;
  selling_price: number;
  cost_price?: number | null;
  stock_qty: number;
  business_id: string;
  created_at: string;
};

export type Supplier = {
  id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  business_id: string;
  created_at: string;
};

export function useBusinesses() {
  return useQuery({
    queryKey: ['businesses'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockBusinesses();
      }
      return await apiFetch<Business[]>('/businesses');
    },
  });
}

export function useCustomers() {
  return useQuery({
    queryKey: ['customers'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockCustomers();
      }
      return await apiFetch<Customer[]>('/customers');
    },
  });
}

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockProducts();
      }
      return await apiFetch<Product[]>('/products');
    },
  });
}

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; phone?: string | null; email?: string | null; business_id: string }) =>
      apiFetch<Customer>('/customers', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['customers'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function useCreateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      name: string;
      sku?: string | null;
      unit?: string | null;
      selling_price: number;
      cost_price?: number | null;
      stock_qty: number;
      business_id: string;
    }) =>
      apiFetch<Product>('/products', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function useUpdateBusiness() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      ...payload
    }: {
      id: string;
      name?: string;
      gstin?: string | null;
      address?: string | null;
      phone?: string | null;
      upi_vpa?: string | null;
    }) =>
      apiFetch<Business>(`/businesses/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['businesses'] });
      void queryClient.invalidateQueries({ queryKey: ['invoices'] });
    },
  });
}

export function useUpdateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: string; name?: string; phone?: string; email?: string }) =>
      apiFetch<Customer>(`/customers/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

export function useDeleteCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      apiFetch<{ deleted: boolean; id: string }>(`/customers/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
  });
}

export function useUpdateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      ...payload
    }: {
      id: string;
      name?: string;
      sku?: string;
      unit?: string;
      selling_price?: number;
      cost_price?: number;
      stock_qty?: number;
    }) =>
      apiFetch<Product>(`/products/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function useDeleteProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      apiFetch<{ deleted: boolean; id: string }>(`/products/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['products'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function useSuppliers() {
  return useQuery({
    queryKey: ['suppliers'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockSuppliers();
      }
      return await apiFetch<Supplier[]>('/suppliers');
    },
  });
}

export function useCreateSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; phone?: string | null; email?: string | null; business_id: string }) =>
      apiFetch<Supplier>('/suppliers', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });
}

export function useUpdateSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: string; name?: string; phone?: string | null; email?: string | null }) =>
      apiFetch<Supplier>(`/suppliers/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });
}

export function useDeleteSupplier() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      apiFetch<{ deleted: boolean; id: string }>(`/suppliers/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });
}
