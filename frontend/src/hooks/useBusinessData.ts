import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';

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
    queryFn: () => apiFetch<Business[]>('/businesses'),
  });
}

export function useCustomers() {
  return useQuery({
    queryKey: ['customers'],
    queryFn: () => apiFetch<Customer[]>('/customers'),
  });
}

export function useProducts() {
  return useQuery({
    queryKey: ['products'],
    queryFn: () => apiFetch<Product[]>('/products'),
  });
}
