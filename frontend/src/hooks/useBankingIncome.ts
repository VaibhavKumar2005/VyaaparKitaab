import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { isDemoMode } from '../mock/mockStore';

export interface BankingConsentResponse {
  consent_id: string;
  fip_id: string;
  fip_name: string;
  status: string;
  redirect_url: string;
  purpose_text: string;
  masked_acc: string;
  fi_types: string[];
  created_at: string;
  expires_at: string;
  security_guarantees: Record<string, string>;
}

export interface IncomeTransactionItem {
  txn_id: string;
  timestamp: string;
  date: string;
  amount: number;
  mode: string;
  type: string;
  narration: string;
  category: string;
  payer_identifier: string;
  masked_acc: string;
}

export interface MonthlyIncomePoint {
  month: string;
  total_income: number;
  transaction_count: number;
}

export interface IncomeCategoryBreakdown {
  category: string;
  total_amount: number;
  percentage: number;
  count: number;
}

export interface IncomeStreamResponse {
  is_connected: boolean;
  active_consent: BankingConsentResponse | null;
  total_inward_income: number;
  total_credits_count: number;
  avg_ticket_size: number;
  monthly_trend: MonthlyIncomePoint[];
  category_breakdown: IncomeCategoryBreakdown[];
  recent_inflows: IncomeTransactionItem[];
  security_metadata: Record<string, string>;
}

export interface IncomeGraphNode {
  id: string;
  label: string;
  type: string;
  subtext: string;
  volume: number;
  count: number;
}

export interface IncomeGraphEdge {
  from_node: string;
  to_node: string;
  amount: number;
  label: string;
  status: string;
}

export interface IncomeGraphResponse {
  nodes: IncomeGraphNode[];
  edges: IncomeGraphEdge[];
  total_inward_volume: number;
  fip_name: string;
  currency: string;
}

const mockIncomeStream: IncomeStreamResponse = {
  is_connected: true,
  active_consent: {
    consent_id: 'consent_mock_sbi9021',
    fip_id: 'sbi_yono',
    fip_name: 'State Bank of India (SBI YONO)',
    status: 'APPROVED',
    redirect_url: 'https://aa.setu.co/consent?id=consent_mock_sbi9021',
    purpose_text: 'Income Inflow & Spending Pattern Visualization (Sahamati Code 102)',
    masked_acc: 'XXXX-XXXX-4821',
    fi_types: ['DEPOSIT'],
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000 * 180).toISOString(),
    security_guarantees: {
      zero_account_storage: 'No raw account number or netbanking password stored',
      read_only: 'Strictly read-only; zero debit or withdrawal permission',
      revocable: 'User can revoke consent at any moment',
      encryption: 'End-to-End TLS 1.3 + FIP/FIU XML Key Pair Encryption',
    },
  },
  total_inward_income: 191070.0,
  total_credits_count: 8,
  avg_ticket_size: 23883.75,
  monthly_trend: [
    { month: '2026-09', total_income: 67920.0, transaction_count: 3 },
    { month: '2026-10', total_income: 123150.0, transaction_count: 5 },
  ],
  category_breakdown: [
    {
      category: 'Direct Deposit / Retainer',
      total_amount: 110000.0,
      percentage: 57.6,
      count: 2,
    },
    {
      category: 'Business Sales Settlement',
      total_amount: 68150.0,
      percentage: 35.7,
      count: 3,
    },
    {
      category: 'Client UPI Receipt',
      total_amount: 21400.0,
      percentage: 11.2,
      count: 2,
    },
    {
      category: 'Bank Interest & Dividends',
      total_amount: 1420.0,
      percentage: 0.7,
      count: 1,
    },
  ],
  recent_inflows: [
    {
      txn_id: 'CR_UPI_9881029314',
      timestamp: new Date().toISOString(),
      date: new Date().toISOString().split('T')[0],
      amount: 28450.0,
      mode: 'UPI',
      type: 'CREDIT',
      narration: 'UPI/CR/9881029314/Sharma Kirana/Daily Sales Settlement/HDFC001',
      category: 'Business Sales Settlement',
      payer_identifier: 'UPI Merchant VPA',
      masked_acc: 'XXXX-XXXX-4821',
    },
    {
      txn_id: 'CR_UPI_8820193847',
      timestamp: new Date(Date.now() - 86400000 * 2).toISOString(),
      date: new Date(Date.now() - 86400000 * 2).toISOString().split('T')[0],
      amount: 12500.0,
      mode: 'UPI',
      type: 'CREDIT',
      narration: 'UPI/CR/8820193847/Vikas Sharma/Invoice Bill Clearance/OKAXIS',
      category: 'Client UPI Receipt',
      payer_identifier: 'vikas.sharma@okaxis',
      masked_acc: 'XXXX-XXXX-4821',
    },
    {
      txn_id: 'CR_NEFT_551029384',
      timestamp: new Date(Date.now() - 86400000 * 6).toISOString(),
      date: new Date(Date.now() - 86400000 * 6).toISOString().split('T')[0],
      amount: 65000.0,
      mode: 'NEFT',
      type: 'CREDIT',
      narration: 'NEFT-CMS-RETAILNET PVT LTD-MONTHLY CONSULTING & INVENTORY FEE',
      category: 'Direct Deposit / Retainer',
      payer_identifier: 'RetailNet Pvt Ltd (NEFT)',
      masked_acc: 'XXXX-XXXX-4821',
    },
  ],
  security_metadata: {
    zero_account_exposure: 'Verified (No account number or login password stored)',
    data_channel: 'RBI Account Aggregator (FIP -> Sahamati AA -> FIU)',
    debit_risk: '0.0% (Cryptographically impossible to debit account)',
    active_fip: 'State Bank of India (SBI YONO)',
    masked_account: 'XXXX-XXXX-4821',
  },
};

const mockIncomeGraph: IncomeGraphResponse = {
  total_inward_volume: 191070.0,
  fip_name: 'State Bank of India (SBI YONO)',
  currency: 'INR',
  nodes: [
    {
      id: 'source_bank',
      label: 'State Bank of India (SBI YONO)',
      type: 'SOURCE_BANK',
      subtext: 'A/c XXXX-XXXX-4821 (FIP Bank App)',
      volume: 191070.0,
      count: 8,
    },
    {
      id: 'aa_tunnel',
      label: 'RBI Sahamati AA Pipeline',
      type: 'AA_TUNNEL',
      subtext: 'Encrypted Read-Only Tunnel',
      volume: 191070.0,
      count: 8,
    },
    {
      id: 'income_hub',
      label: 'VyaparKitaab Income Stream',
      type: 'INCOME_HUB',
      subtext: 'Total Verified Inflow',
      volume: 191070.0,
      count: 8,
    },
    {
      id: 'cat_0',
      label: 'Direct Deposit / Retainer',
      type: 'INFLOW_CATEGORY',
      subtext: '57.6% of total income',
      volume: 110000.0,
      count: 2,
    },
    {
      id: 'cat_1',
      label: 'Business Sales Settlement',
      type: 'INFLOW_CATEGORY',
      subtext: '35.7% of total income',
      volume: 68150.0,
      count: 3,
    },
    {
      id: 'cat_2',
      label: 'Client UPI Receipt',
      type: 'INFLOW_CATEGORY',
      subtext: '11.2% of total income',
      volume: 21400.0,
      count: 2,
    },
  ],
  edges: [
    { from_node: 'source_bank', to_node: 'aa_tunnel', amount: 191070.0, label: 'FIP Consent Sync', status: 'VERIFIED_CREDIT' },
    { from_node: 'aa_tunnel', to_node: 'income_hub', amount: 191070.0, label: 'Decrypted Inflows', status: 'VERIFIED_CREDIT' },
    { from_node: 'income_hub', to_node: 'cat_0', amount: 110000.0, label: '57.6%', status: 'VERIFIED_CREDIT' },
    { from_node: 'income_hub', to_node: 'cat_1', amount: 68150.0, label: '35.7%', status: 'VERIFIED_CREDIT' },
    { from_node: 'income_hub', to_node: 'cat_2', amount: 21400.0, label: '11.2%', status: 'VERIFIED_CREDIT' },
  ],
};

export function useIncomeStream() {
  return useQuery<IncomeStreamResponse>({
    queryKey: ['banking_income_stream'],
    queryFn: async () => {
      if (isDemoMode()) {
        return mockIncomeStream;
      }
      try {
        return await apiFetch<IncomeStreamResponse>('/banking/income-stream');
      } catch {
        return mockIncomeStream;
      }
    },
  });
}

export function useIncomeGraph() {
  return useQuery<IncomeGraphResponse>({
    queryKey: ['banking_income_graph'],
    queryFn: async () => {
      if (isDemoMode()) {
        return mockIncomeGraph;
      }
      try {
        return await apiFetch<IncomeGraphResponse>('/banking/income-graph');
      } catch {
        return mockIncomeGraph;
      }
    },
  });
}

export function useInitiateBankingConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { fip_id: string; phone?: string; data_life_months?: number }) => {
      return await apiFetch<BankingConsentResponse>('/banking/consent/initiate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}

export function useAuthorizeBankingConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { consent_id: string; approve: boolean; fip_id?: string }) => {
      return await apiFetch<BankingConsentResponse>('/banking/consent/authorize', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}

export function useRevokeBankingConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      return await apiFetch<{ status: string; message: string }>('/banking/consent/revoke', {
        method: 'POST',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}

export interface PersonalSpendingItem {
  txn_id: string;
  timestamp: string;
  date: string;
  amount: number;
  type: 'DEBIT' | 'CREDIT';
  mode: string;
  app: string;
  vpa?: string | null;
  narration: string;
  category: string;
  counterparty: string;
  masked_acc: string;
  source: string;
}

export interface PersonalSpendingResponse {
  has_imported_data: boolean;
  total_spent: number;
  total_received: number;
  net_cashflow: number;
  debits_count: number;
  credits_count: number;
  category_breakdown: Array<{ category: string; amount: number; count: number; percentage: number }>;
  app_breakdown: Array<{ app: string; amount: number; count: number; percentage: number }>;
  monthly_trend: Array<{ month: string; spent: number; received: number; count: number }>;
  transactions: PersonalSpendingItem[];
}

export function usePersonalSpending() {
  return useQuery<PersonalSpendingResponse>({
    queryKey: ['personal_spending'],
    queryFn: async () => {
      return await apiFetch<PersonalSpendingResponse>('/banking/personal-spending');
    },
  });
}

export function useImportStatement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const content = await file.text();
      return await apiFetch<{
        status: string;
        filename: string;
        imported_count: number;
        credits_count: number;
        debits_count: number;
      }>('/banking/import-statement', {
        method: 'POST',
        body: JSON.stringify({
          filename: file.name,
          content,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}

export function useClearImportedTransactions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      return await apiFetch<{ status: string }>('/banking/transactions', {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}

export interface BankDemoStreamStatus {
  is_running: boolean;
  interval_seconds: number;
  emitted_count: number;
  last_emitted_at: string | null;
}

export function useBankDemoStreamStatus() {
  return useQuery<BankDemoStreamStatus>({
    queryKey: ['bank_demo_stream_status'],
    queryFn: async () => {
      try {
        return await apiFetch<BankDemoStreamStatus>('/banking/demo-stream/status');
      } catch {
        return { is_running: false, interval_seconds: 10, emitted_count: 0, last_emitted_at: null };
      }
    },
    refetchInterval: (query) => (query.state.data?.is_running ? 3000 : false),
  });
}

export function useStartBankDemoStream() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (intervalSeconds: number = 10) => {
      return await apiFetch<BankDemoStreamStatus>(`/banking/demo-stream/start?interval_seconds=${intervalSeconds}`, {
        method: 'POST',
      });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['bank_demo_stream_status'], data);
    },
  });
}

export function useStopBankDemoStream() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      return await apiFetch<BankDemoStreamStatus>('/banking/demo-stream/stop', {
        method: 'POST',
      });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['bank_demo_stream_status'], data);
    },
  });
}

export function useEmitBankCredit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      return await apiFetch<Record<string, unknown>>('/banking/demo-stream/emit', {
        method: 'POST',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bank_demo_stream_status'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
    },
  });
}


