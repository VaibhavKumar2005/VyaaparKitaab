import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import {
  getMockBusinesses,
  getMockCustomers,
  getMockProducts,
  isDemoMode,
} from '../mock/mockStore';

export type Business = {
  id: string;
  name: string;
  gstin?: string | null;
  address?: string | null;
  phone?: string | null;
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

export function useBusinesses() {
  return useQuery({
    queryKey: ['businesses'],
    queryFn: async () => {
      if (isDemoMode()) {
        return getMockBusinesses();
      }
      try {
        return await apiFetch<Business[]>('/businesses');
      } catch {
        return getMockBusinesses();
      }
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
      try {
        return await apiFetch<Customer[]>('/customers');
      } catch {
        return getMockCustomers();
      }
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
      try {
        return await apiFetch<Product[]>('/products');
      } catch {
        return getMockProducts();
      }
    },
  });
}
