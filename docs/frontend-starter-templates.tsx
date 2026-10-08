/*
Starter templates for the frontend upgrade.

Copy each export into the matching file in frontend/src/ as you break the app into
real modules. The code is intentionally written to fit the current auth flow,
including in-memory access tokens and the /api/v1/auth/refresh endpoint.
*/

import React, { createContext, useContext, useMemo } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import axios, { AxiosError, AxiosInstance } from 'axios';

export const loginSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
});

export type LoginValues = z.infer<typeof loginSchema>;

export const dashboardSchema = z.object({
  totalRevenue: z.number(),
  openInvoices: z.number(),
  overdueInvoices: z.number(),
  activeCustomers: z.number(),
});

export type DashboardSummary = z.infer<typeof dashboardSchema>;

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

async function refreshAccessToken(): Promise<string | null> {
  try {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!response.ok) {
      return null;
    }

    const payload = (await response.json()) as { access_token?: string };
    if (!payload.access_token) {
      return null;
    }

    setAccessToken(payload.access_token);
    return payload.access_token;
  } catch {
    return null;
  }
}

export function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: '/api/v1',
    withCredentials: true,
    headers: { 'Content-Type': 'application/json' },
  });

  client.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token) {
      config.headers = config.headers ?? {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config;
      if (!originalRequest || error.response?.status !== 401 || (originalRequest as { _retry?: boolean })._retry) {
        return Promise.reject(error);
      }

      (originalRequest as { _retry?: boolean })._retry = true;
      const newToken = await refreshAccessToken();
      if (!newToken) {
        return Promise.reject(error);
      }

      originalRequest.headers = originalRequest.headers ?? {};
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return client(originalRequest);
    },
  );

  return client;
}

export const apiClient = createApiClient();

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2,
      gcTime: 1000 * 60 * 10,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

export function AppQueryProvider({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

export function useDashboardSummary() {
  return useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: async (): Promise<DashboardSummary> => {
      const response = await apiClient.get('/dashboard/summary');
      return dashboardSchema.parse(response.data);
    },
  });
}

type LoginFormProps = {
  onSubmit: (values: LoginValues) => Promise<void> | void;
};

export function LoginForm({ onSubmit }: LoginFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">Email</label>
        <input id="email" type="email" className="w-full rounded-lg border border-slate-300 px-3 py-2" {...register('email')} />
        {errors.email ? <p className="mt-1 text-sm text-red-600">{errors.email.message}</p> : null}
      </div>

      <div>
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">Password</label>
        <input id="password" type="password" className="w-full rounded-lg border border-slate-300 px-3 py-2" {...register('password')} />
        {errors.password ? <p className="mt-1 text-sm text-red-600">{errors.password.message}</p> : null}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
  );
}

type AuthContextValue = {
  token: string | null;
  setToken: (token: string | null) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const value = useMemo<AuthContextValue>(
    () => ({
      token: getAccessToken(),
      setToken: (token: string | null) => setAccessToken(token),
      logout: () => setAccessToken(null),
    }),
    [],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

export function DashboardSummaryCard() {
  const { data, isLoading, error } = useDashboardSummary();

  if (isLoading) {
    return <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6">Loading dashboard...</div>;
  }

  if (error || !data) {
    return <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700">Unable to load dashboard.</div>;
  }

  return (
    <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 md:grid-cols-4">
      <Stat label="Revenue" value={data.totalRevenue.toFixed(2)} />
      <Stat label="Open invoices" value={String(data.openInvoices)} />
      <Stat label="Overdue" value={String(data.overdueInvoices)} />
      <Stat label="Customers" value={String(data.activeCustomers)} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}
