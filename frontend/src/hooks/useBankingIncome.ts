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
      return await apiFetch<IncomeStreamResponse>('/banking/income-stream');
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
      return await apiFetch<IncomeGraphResponse>('/banking/income-graph');
    },
  });
}

export function useInitiateBankingConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { fip_id: string; phone?: string; vua?: string; data_life_months?: number }) => {
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

const SAMPLE_PDF_LINES = [
  'STATE BANK OF INDIA / UNIFIED UPI CONSOLIDATED STATEMENT (REALISTIC SAMPLE)',
  'Account Holder: Sharma Kirana & General Store | Masked A/c: XXXX-XXXX-4821',
  'Statement Period: October - November 2026 | Currency: INR',
  '----------------------------------------------------------------------------------------',
  'Date | Narration | Type | Amount | Mode | App | VPA',
  '2026-11-01 | UPI/CR/631099281104/Rajesh Verma/Kirana Monthly Ration/OKAXIS | CREDIT | 3450.00 | UPI | Google Pay | rajesh.verma@okaxis',
  '2026-11-02 | UPI/DR/631188273615/Blinkit Groceries/Daily Store Supplies/AXL | DEBIT | 840.00 | UPI | PhonePe | blinkit.pay@axl',
  '2026-11-03 | UPI/CR/631277192837/Sunita Devi/Festival Grocery Bill/YBL | CREDIT | 2180.00 | UPI | PhonePe | sunita.devi@ybl',
  '2026-11-04 | UPI/DR/631366541209/Amazon India/Thermal Receipt Printer Paper/OKICICI | DEBIT | 699.00 | UPI | Google Pay | amazon@okicici',
  '2026-11-05 | NEFT/CR/SBIN2630918273/Metro Cash and Carry Rebate/Bonus Settlement | CREDIT | 14500.00 | NEFT | Bank NEFT | -',
  '2026-11-06 | UPI/DR/631544392018/Tata Power Electricity/Shop Meter Bill/PAYTM | DEBIT | 2420.00 | UPI | Paytm | tatapower@paytm',
  '2026-11-07 | UPI/CR/631633918274/Amit Kumar/Atta and Cooking Oil Settlement/OKHDFCBANK | CREDIT | 1890.00 | UPI | Google Pay | amit.k@okhdfcbank',
  '2026-11-08 | UPI/DR/631722839105/Swiggy Food Delivery/Staff Evening Snacks/YBL | DEBIT | 465.00 | UPI | PhonePe | swiggy@ybl',
  '2026-11-09 | UPI/CR/631811746592/Priya Nair/Household Provisions Bill/PAYTM | CREDIT | 2760.00 | UPI | Paytm | priya.nair@paytm',
  '2026-11-10 | UPI/DR/631900654321/IndianOil Fuel Station/Delivery Scooter Petrol/OKSBI | DEBIT | 550.00 | UPI | Google Pay | indianoil@oksbi',
  '2026-11-11 | UPI/DR/632011928374/Jio Fiber Broadband/Store WiFi & POS Recharge/OKAXIS | DEBIT | 999.00 | UPI | Google Pay | jiofiber@okaxis',
  '2026-11-12 | UPI/CR/632122837465/Vikram Singh/Bulk Dry Fruits & Spices Order/YBL | CREDIT | 5640.00 | UPI | PhonePe | vikram.singh@ybl',
];

export function buildSamplePdfStringClient(): string {
  const ops = ['BT', '/F1 9 Tf', '36 790 Td', '14 TL'];
  SAMPLE_PDF_LINES.forEach((line, idx) => {
    const escaped = line.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
    ops.push(idx === 0 ? `(${escaped}) Tj` : `T* (${escaped}) Tj`);
  });
  ops.push('ET');
  const streamStr = ops.join('\n');

  const objs = [
    '1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n',
    '2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n',
    '3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n',
    `4 0 obj\n<< /Length ${streamStr.length} >>\nstream\n${streamStr}\nendstream\nendobj\n`,
    '5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n',
  ];

  let pdf = '%PDF-1.4\n';
  const offsets: number[] = [];
  for (const obj of objs) {
    offsets.push(pdf.length);
    pdf += obj;
  }
  const xrefPos = pdf.length;
  pdf += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) {
    pdf += `${String(off).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`;
  return pdf;
}

export function createSampleStatementPdfFile(): File {
  const pdfStr = buildSamplePdfStringClient();
  return new File([pdfStr], 'realistic_upi_bank_statement.pdf', { type: 'application/pdf' });
}

export function downloadSampleStatementPdf(): void {
  const pdfStr = buildSamplePdfStringClient();
  const blob = new Blob([pdfStr], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'realistic_upi_bank_statement.pdf';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const mockImportedSpending: PersonalSpendingResponse = {
  has_imported_data: true,
  total_spent: 5973.0,
  total_received: 30420.0,
  net_cashflow: 24447.0,
  debits_count: 6,
  credits_count: 6,
  category_breakdown: [
    { category: 'Bills & Utilities', amount: 3419.0, count: 2, percentage: 57.2 },
    { category: 'Groceries & Kirana', amount: 840.0, count: 1, percentage: 14.1 },
    { category: 'Shopping & E-Commerce', amount: 699.0, count: 1, percentage: 11.7 },
    { category: 'Travel & Fuel', amount: 550.0, count: 1, percentage: 9.2 },
    { category: 'Food & Dining', amount: 465.0, count: 1, percentage: 7.8 },
  ],
  app_breakdown: [
    { app: 'Google Pay', amount: 2248.0, count: 3, percentage: 37.6 },
    { app: 'Paytm', amount: 2420.0, count: 1, percentage: 40.5 },
    { app: 'PhonePe', amount: 1305.0, count: 2, percentage: 21.8 },
  ],
  monthly_trend: [{ month: '2026-11', spent: 5973.0, received: 30420.0, count: 12 }],
  transactions: [
    {
      txn_id: 'TXN_20261112_VIKRAM',
      timestamp: '2026-11-12T10:00:00Z',
      date: '2026-11-12',
      amount: 5640.0,
      type: 'CREDIT',
      mode: 'UPI',
      app: 'PhonePe',
      vpa: 'vikram.singh@ybl',
      narration: 'UPI/CR/632122837465/Vikram Singh/Bulk Dry Fruits & Spices Order/YBL',
      category: 'Client UPI Receipt',
      counterparty: 'Vikram Singh',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
    {
      txn_id: 'TXN_20261111_JIO',
      timestamp: '2026-11-11T10:00:00Z',
      date: '2026-11-11',
      amount: 999.0,
      type: 'DEBIT',
      mode: 'UPI',
      app: 'Google Pay',
      vpa: 'jiofiber@okaxis',
      narration: 'UPI/DR/632011928374/Jio Fiber Broadband/Store WiFi & POS Recharge/OKAXIS',
      category: 'Bills & Utilities',
      counterparty: 'Jio Fiber Broadband',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
    {
      txn_id: 'TXN_20261106_TATAPOWER',
      timestamp: '2026-11-06T10:00:00Z',
      date: '2026-11-06',
      amount: 2420.0,
      type: 'DEBIT',
      mode: 'UPI',
      app: 'Paytm',
      vpa: 'tatapower@paytm',
      narration: 'UPI/DR/631544392018/Tata Power Electricity/Shop Meter Bill/PAYTM',
      category: 'Bills & Utilities',
      counterparty: 'Tata Power Electricity',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
    {
      txn_id: 'TXN_20261105_METRO',
      timestamp: '2026-11-05T10:00:00Z',
      date: '2026-11-05',
      amount: 14500.0,
      type: 'CREDIT',
      mode: 'NEFT',
      app: 'Bank NEFT',
      vpa: null,
      narration: 'NEFT/CR/SBIN2630918273/Metro Cash and Carry Rebate/Bonus Settlement',
      category: 'Business Sales Settlement',
      counterparty: 'Metro Cash and Carry Rebate',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
    {
      txn_id: 'TXN_20261102_BLINKIT',
      timestamp: '2026-11-02T10:00:00Z',
      date: '2026-11-02',
      amount: 840.0,
      type: 'DEBIT',
      mode: 'UPI',
      app: 'PhonePe',
      vpa: 'blinkit.pay@axl',
      narration: 'UPI/DR/631188273615/Blinkit Groceries/Daily Store Supplies/AXL',
      category: 'Groceries & Kirana',
      counterparty: 'Blinkit Groceries',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
    {
      txn_id: 'TXN_20261101_RAJESH',
      timestamp: '2026-11-01T10:00:00Z',
      date: '2026-11-01',
      amount: 3450.0,
      type: 'CREDIT',
      mode: 'UPI',
      app: 'Google Pay',
      vpa: 'rajesh.verma@okaxis',
      narration: 'UPI/CR/631099281104/Rajesh Verma/Kirana Monthly Ration/OKAXIS',
      category: 'Client UPI Receipt',
      counterparty: 'Rajesh Verma',
      masked_acc: 'XXXX-XXXX-4821',
      source: 'file:realistic_upi_bank_statement.pdf',
    },
  ],
};

let demoStatementImported = false;

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

export function usePersonalSpending() {
  return useQuery<PersonalSpendingResponse>({
    queryKey: ['personal_spending'],
    queryFn: async () => {
      if (isDemoMode()) {
        if (demoStatementImported) return mockImportedSpending;
        return {
          has_imported_data: false,
          total_spent: 0,
          total_received: 0,
          net_cashflow: 0,
          debits_count: 0,
          credits_count: 0,
          category_breakdown: [],
          app_breakdown: [],
          monthly_trend: [],
          transactions: [],
        };
      }
      return await apiFetch<PersonalSpendingResponse>('/banking/personal-spending');
    },
  });
}

export function useImportStatement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: File | { file: File; pdfPassword?: string }) => {
      const file = input instanceof File ? input : input.file;
      const pdfPassword = input instanceof File ? undefined : input.pdfPassword;
      const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
      const buffer = await file.arrayBuffer();
      const contentBase64 = arrayBufferToBase64(buffer);
      const contentText = isPdf ? '' : await file.text();

      if (isDemoMode()) {
        demoStatementImported = true;
        return {
          status: 'imported',
          filename: file.name,
          imported_count: 12,
          credits_count: 6,
          debits_count: 6,
        };
      }

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
          content: contentText,
          content_base64: contentBase64,
          pdf_password: pdfPassword || null,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
      queryClient.invalidateQueries({ queryKey: ['unified_transactions'] });
      queryClient.invalidateQueries({ queryKey: ['unified_assistant'] });
      queryClient.invalidateQueries({ queryKey: ['reconcile_suggestions'] });
    },
  });
}

export function useClearImportedTransactions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      demoStatementImported = false;
      if (isDemoMode()) {
        return { status: 'cleared' };
      }
      return await apiFetch<{ status: string }>('/banking/transactions', {
        method: 'DELETE',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
      queryClient.invalidateQueries({ queryKey: ['unified_transactions'] });
      queryClient.invalidateQueries({ queryKey: ['reconcile_suggestions'] });
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

export interface UpiBridgeTemplates {
  webhook_endpoint: string;
  full_webhook_url: string;
  header_name: string;
  supported_packages: string[];
  android_payload_template: string;
  gmail_apps_script: string;
  ios_shortcut_steps: string[];
  curl_test_command: string;
}

export interface UpiBridgeConfig {
  status: string;
  ingest_token: string;
  masked_token: string;
  rotated_at: string | null;
  ingest_count: number;
  last_ingest_at: string | null;
  last_app: string | null;
  templates: UpiBridgeTemplates;
}

export interface UpiBridgeIngestResult {
  status: 'ingested' | 'ignored';
  reason?: string;
  imported_count: number;
  transaction?: {
    txn_id: string;
    date: string;
    amount: number;
    type: string;
    mode: string;
    app: string;
    counterparty: string;
    category: string;
    masked_acc: string;
    narration: string;
  };
}

function buildFallbackBridgeConfig(tokenSuffix = 'demo8k9p2m4n'): UpiBridgeConfig {
  const token = `vk_upi_demo.${tokenSuffix}`;
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000';
  const endpoint = `${origin}/api/v1/banking/upi-bridge/ingest`;
  return {
    status: 'ACTIVE',
    ingest_token: token,
    masked_token: `${token.slice(0, 10)}...${token.slice(-6)}`,
    rotated_at: new Date().toISOString(),
    ingest_count: 0,
    last_ingest_at: null,
    last_app: null,
    templates: {
      webhook_endpoint: '/api/v1/banking/upi-bridge/ingest',
      full_webhook_url: endpoint,
      header_name: 'X-Ingest-Token',
      supported_packages: [
        'com.google.android.apps.nbu.paisa.user (Google Pay)',
        'net.one97.paytm (Paytm)',
        'com.phonepe.app (PhonePe)',
        'in.org.npci.upiapp (BHIM UPI)',
      ],
      android_payload_template: JSON.stringify(
        {
          source_channel: 'android_notification',
          app_package: '{notification_app_package}',
          title: '{notification_title}',
          message: '{notification_text}',
        },
        null,
        2,
      ),
      gmail_apps_script:
        `const VK_WEBHOOK_URL = "${endpoint}";\n` +
        `const VK_INGEST_TOKEN = "${token}";\n\n` +
        `function syncUpiAlertsToVyaparKitaab() {\n` +
        `  const label = GmailApp.getUserLabelByName("vk_synced") || GmailApp.createLabel("vk_synced");\n` +
        `  const threads = GmailApp.search('from:(googlepay-noreply@google.com OR alerts@paytm.com) newer_than:2d -label:vk_synced', 0, 20);\n` +
        `  for (const thread of threads) {\n` +
        `    for (const msg of thread.getMessages()) {\n` +
        `      UrlFetchApp.fetch(VK_WEBHOOK_URL, {\n` +
        `        method: "post",\n` +
        `        contentType: "application/json",\n` +
        `        headers: { "X-Ingest-Token": VK_INGEST_TOKEN },\n` +
        `        payload: JSON.stringify({ source_channel: "gmail_apps_script", title: msg.getSubject(), message: (msg.getPlainBody() || "").slice(0, 350) })\n` +
        `      });\n` +
        `    }\n` +
        `    thread.addLabel(label);\n` +
        `  }\n` +
        `}`,
      ios_shortcut_steps: [
        'Open Apple Shortcuts -> Automation -> "+" -> Message / Transaction.',
        'Trigger: When Message contains "UPI" or "debited" or "credited".',
        `Action: Get Contents of URL -> ${endpoint} (POST).`,
        'Headers: Content-Type = application/json, X-Ingest-Token = <your token>.',
        'JSON Body: { "source_channel": "ios_shortcut", "title": "UPI SMS", "message": [Shortcut Input] }.',
      ],
      curl_test_command: `curl -X POST "${endpoint}" -H "Content-Type: application/json" -H "X-Ingest-Token: ${token}" -d '{"app_package":"com.google.android.apps.nbu.paisa.user","title":"Paid ₹450.00 to Blue Tokai Coffee","message":"UPI Ref: 431789123456"}'`,
    },
  };
}

export function useUpiBridgeConfig(enabled = true) {
  return useQuery<UpiBridgeConfig>({
    queryKey: ['upi_bridge_config'],
    enabled,
    queryFn: async () => {
      if (isDemoMode()) {
        return buildFallbackBridgeConfig();
      }
      return await apiFetch<UpiBridgeConfig>('/banking/upi-bridge/config');
    },
  });
}

export function useRotateUpiBridgeToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (isDemoMode()) {
        return buildFallbackBridgeConfig(Math.random().toString(36).slice(2, 12));
      }
      return await apiFetch<UpiBridgeConfig>('/banking/upi-bridge/rotate-token', {
        method: 'POST',
      });
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['upi_bridge_config'], data);
    },
  });
}

export interface ReconcileSuggestion {
  txn_id: string;
  txn_amount: number;
  txn_date: string;
  txn_app: string;
  counterparty: string;
  narration: string;
  invoice_id: string;
  invoice_number: string;
  customer_name: string;
  due_amount: number;
  confidence: 'HIGH' | 'MEDIUM';
  match_reason: string;
}

export function useReconcileSuggestions() {
  return useQuery<{ suggestions: ReconcileSuggestion[]; count: number }>({
    queryKey: ['reconcile_suggestions'],
    queryFn: async () => {
      if (isDemoMode()) {
        return { suggestions: [], count: 0 };
      }
      return await apiFetch<{ suggestions: ReconcileSuggestion[]; count: number }>('/banking/reconcile/suggestions');
    },
  });
}

export function useApplyReconciliation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { txn_id: string; invoice_id: string }) =>
      apiFetch<{
        reconciled: boolean;
        invoice_id: string;
        invoice_number: string;
        invoice_status: string;
        paid_amount: number;
        message: string;
      }>('/banking/reconcile/match', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reconcile_suggestions'] });
      void queryClient.invalidateQueries({ queryKey: ['invoices'] });
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      void queryClient.invalidateQueries({ queryKey: ['unified_transactions'] });
    },
  });
}

function buildDemoBridgeIngestResult(input: {
  app_package: string;
  title: string;
  message: string;
}): UpiBridgeIngestResult {
  demoStatementImported = true;
  const isPaytm = input.app_package.includes('paytm');
  const isCredit = /received|credited/i.test(`${input.title} ${input.message}`);
  return {
    status: 'ingested',
    imported_count: 1,
    transaction: {
      txn_id: `BRIDGE_${Date.now().toString().slice(-8)}`,
      date: new Date().toISOString().slice(0, 10),
      amount: isCredit ? 1250 : 450,
      type: isCredit ? 'CREDIT' : 'DEBIT',
      mode: 'UPI',
      app: isPaytm ? 'Paytm' : 'Google Pay',
      counterparty: isPaytm ? 'Uber India' : isCredit ? 'Rahul Sharma' : 'Blue Tokai Coffee',
      category: isCredit ? 'Client UPI Receipt' : isPaytm ? 'Travel & Fuel' : 'Food & Dining',
      masked_acc: 'XXXX-XXXX-4821',
      narration: `${input.title} — ${input.message}`,
    },
  };
}

export function useTestUpiBridgeIngest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      ingestToken: string;
      app_package: string;
      title: string;
      message: string;
      source_channel?: string;
    }): Promise<UpiBridgeIngestResult> => {
      const apiBase = import.meta.env.VITE_API_URL
        ? String(import.meta.env.VITE_API_URL).replace(/\/$/, '')
        : '';
      let resp: Response;
      try {
        resp = await fetch(`${apiBase}/api/v1/banking/upi-bridge/ingest`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Ingest-Token': input.ingestToken,
          },
          body: JSON.stringify({
            source_channel: input.source_channel ?? 'android_notification',
            app_package: input.app_package,
            title: input.title,
            message: input.message,
          }),
        });
      } catch (err) {
        if (!isDemoMode() && !input.ingestToken.startsWith('vk_upi_demo.')) {
          throw err instanceof Error ? err : new Error('Network error contacting UPI bridge');
        }
        return buildDemoBridgeIngestResult(input);
      }

      if (!resp.ok) {
        if (isDemoMode() || input.ingestToken.startsWith('vk_upi_demo.')) {
          return buildDemoBridgeIngestResult(input);
        }
        throw new Error(await resp.text());
      }
      return (await resp.json()) as UpiBridgeIngestResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['upi_bridge_config'] });
      queryClient.invalidateQueries({ queryKey: ['personal_spending'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_stream'] });
      queryClient.invalidateQueries({ queryKey: ['banking_income_graph'] });
    },
  });
}


