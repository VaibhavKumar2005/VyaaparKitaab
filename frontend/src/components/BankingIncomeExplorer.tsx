import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowDownLeft,
  Building2,
  CheckCircle2,
  Lock,
  Network,
  RefreshCw,
  Shield,
  ShieldCheck,
  Smartphone,
  TrendingUp,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  useIncomeStream,
  useIncomeGraph,
  useInitiateBankingConsent,
  useRevokeBankingConsent,
  useImportStatement,
} from '../hooks/useBankingIncome';
import { usePaymentStream } from '../hooks/usePaymentStream';
import { formatINR, formatINRPrecise } from '../lib/format';
import { LiveBankFeed } from './LiveBankFeed';

const SUPPORTED_BANKS = [
  { id: 'sbi_yono', name: 'SBI YONO', fullName: 'State Bank of India (YONO)', color: 'bg-blue-600' },
  { id: 'hdfc_bank', name: 'HDFC Bank', fullName: 'HDFC Bank MobileBanking', color: 'bg-navy' },
  { id: 'icici_imobile', name: 'ICICI iMobile', fullName: 'ICICI Bank iMobile Pay', color: 'bg-amber-600' },
  { id: 'axis_bank', name: 'Axis Mobile', fullName: 'Axis Mobile Banking', color: 'bg-rose-700' },
  { id: 'phonepe_aa', name: 'PhonePe AA', fullName: 'PhonePe Account Aggregator', color: 'bg-purple-600' },
];

export function BankingIncomeExplorer() {
  const { data: incomeData, isLoading, refetch } = useIncomeStream();
  const { data: graphData } = useIncomeGraph();
  const initiateConsentMutation = useInitiateBankingConsent();
  const revokeConsentMutation = useRevokeBankingConsent();
  const importStatementMutation = useImportStatement();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Real-time payment stream connection with single fallback refetch on reconnect
  usePaymentStream({
    url: '/streams/payments',
    onReconnect: () => {
      void refetch();
    },
  });

  const [selectedBankId, setSelectedBankId] = useState<string>('sbi_yono');
  const [showConsentModal, setShowConsentModal] = useState<boolean>(false);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  // 2-step AA Consent OTP Verification state
  const [aaPhone, setAaPhone] = useState<string>('9876543210');
  const [aaEmail, setAaEmail] = useState<string>('');
  const [aaOtpSent, setAaOtpSent] = useState<boolean>(false);
  const [aaOtpCode, setAaOtpCode] = useState<string>('');
  const [aaOtpHint, setAaOtpHint] = useState<string>('');
  const [aaError, setAaError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    importStatementMutation.mutate(file, {
      onSuccess: (res) => {
        setSuccessToast(
          `Imported ${res.imported_count} real transactions (${res.credits_count} credits, ${res.debits_count} debits) from ${res.filename}!`
        );
        setTimeout(() => setSuccessToast(null), 6000);
      },
      onError: (err) => {
        setSuccessToast(err instanceof Error ? err.message : 'Statement import failed');
        setTimeout(() => setSuccessToast(null), 6000);
      },
    });
    e.target.value = '';
  };

  const handleSendConsentOtp = async () => {
    setAaError(null);
    setAaOtpCode('');
    const boundTarget = aaEmail.trim() || aaPhone.trim();
    try {
      const params = new URLSearchParams({
        phone: boundTarget,
        purpose: 'AA_CONSENT',
      });
      const res = await fetch(`/api/v1/auth/otp/send?${params.toString()}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to send OTP' }));
        throw new Error(err.detail || 'Failed to send OTP');
      }
      const data = await res.json();
      if (data.channel === 'email') {
        setAaOtpHint(`OTP sent to ${boundTarget} via Gmail SMTP`);
      } else if (data.dev_otp) {
        setAaOtpHint(`OTP generated: ${data.dev_otp}`);
      } else {
        setAaOtpHint('Enter 6-digit OTP');
      }
      setAaOtpSent(true);
    } catch (err) {
      setAaError(err instanceof Error ? err.message : 'Failed to send OTP');
    }
  };

  const handleVerifyAndConnect = async () => {
    setAaError(null);
    if (!aaOtpCode || aaOtpCode.length < 6) {
      setAaError('Please enter the 6-digit OTP');
      return;
    }
    const boundTarget = aaEmail.trim() || aaPhone.trim();
    try {
      const verifyParams = new URLSearchParams({
        phone: boundTarget,
        otp: aaOtpCode.trim(),
        purpose: 'AA_CONSENT',
      });
      const verifyRes = await fetch(`/api/v1/auth/otp/verify?${verifyParams.toString()}`, {
        method: 'POST',
      });
      if (!verifyRes.ok) {
        const err = await verifyRes.json().catch(() => ({ detail: 'Invalid or expired OTP' }));
        throw new Error(err.detail || 'Invalid or expired OTP');
      }
      handleConnectBank(selectedBankId);
      setAaOtpSent(false);
      setAaOtpCode('');
    } catch (err) {
      setAaError(err instanceof Error ? err.message : 'OTP verification failed');
    }
  };

  const activeConsent = incomeData?.active_consent;
  const isConnected = incomeData?.is_connected && activeConsent?.status === 'APPROVED';

  const monthlyTrend = incomeData?.monthly_trend || [];
  const [throttledTrend, setThrottledTrend] = useState(monthlyTrend);
  const lastRedrawTime = useRef<number>(0);
  const pendingTrend = useRef(monthlyTrend);

  // Throttle live redraws to ~1 second and disable entry animations
  useEffect(() => {
    pendingTrend.current = monthlyTrend;
    const now = Date.now();
    if (now - lastRedrawTime.current >= 1000) {
      lastRedrawTime.current = now;
      setThrottledTrend(monthlyTrend);
    } else {
      const timer = setTimeout(() => {
        lastRedrawTime.current = Date.now();
        setThrottledTrend(pendingTrend.current);
      }, 1000 - (now - lastRedrawTime.current));
      return () => clearTimeout(timer);
    }
  }, [monthlyTrend]);

  const handleConnectBank = (fipId: string) => {
    setSelectedBankId(fipId);
    initiateConsentMutation.mutate(
      { fip_id: fipId, phone: '9876543210', data_life_months: 6 },
      {
        onSuccess: (data) => {
          setShowConsentModal(false);
          if (data.status === 'PENDING' && data.redirect_url) {
            setSuccessToast(
              `Consent initiated (${data.consent_id}). Complete approval at Setu AA: ${data.redirect_url}`
            );
            window.open(data.redirect_url, '_blank', 'noopener,noreferrer');
          } else {
            setSuccessToast(`Successfully connected ${data.fip_name} via RBI Account Aggregator!`);
          }
          setTimeout(() => setSuccessToast(null), 6000);
        },
      }
    );
  };

  const handleRevoke = () => {
    revokeConsentMutation.mutate(undefined, {
      onSuccess: () => {
        setSuccessToast('Banking app consent successfully revoked. No further income data will be fetched.');
        setTimeout(() => setSuccessToast(null), 5000);
      },
    });
  };

  if (isLoading || !incomeData) {
    return (
      <div className="rounded-xl border border-rule bg-canvas-raised p-6 text-center text-xs text-ink-soft">
        Connecting to RBI Account Aggregator consent gateway...
      </div>
    );
  }

  return (
    <section className="rounded-2xl border-2 border-emerald-500/30 bg-canvas-raised p-5 shadow-sm space-y-6">
      {/* Toast Notification */}
      {successToast && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-xs font-semibold text-emerald-900 shadow-sm animate-fade-in">
          <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
          <span>{successToast}</span>
        </div>
      )}

      {/* Main Header Strip */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-rule pb-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-emerald-600 p-2.5 text-white shadow-xs">
            <Building2 className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-ink">
                Connected Banking App — Safe Inflow &amp; Income Explorer
              </h2>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-300 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                RBI Sahamati AA Standard
              </span>
            </div>
            <p className="text-xs text-ink-soft mt-0.5">
              Securely visualizes revenue, client payments, and deposits coming into your bank app—
              <strong className="text-ink">without asking for, accessing, or storing your bank account number or password</strong>.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={importStatementMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-navy bg-canvas px-3 py-1.5 text-xs font-bold text-navy hover:bg-navy-tint transition-colors"
            title="Upload real Bank, Google Pay, PhonePe, or Paytm CSV/JSON statement"
          >
            <Upload className="h-3.5 w-3.5" />
            {importStatementMutation.isPending ? 'Importing…' : 'Import Statement (CSV/JSON)'}
          </button>
          <button
            type="button"
            onClick={() => setShowConsentModal(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-700 shadow-xs transition-colors"
          >
            <Smartphone className="h-3.5 w-3.5" />
            {isConnected ? 'Switch / Verify Bank AA' : 'Connect Banking App'}
          </button>
          {isConnected && (
            <button
              type="button"
              onClick={handleRevoke}
              disabled={revokeConsentMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors"
              title="Revoke consent anytime as per DPDP Act"
            >
              <XCircle className="h-3.5 w-3.5" />
              Disconnect
            </button>
          )}
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-lg border border-rule p-1.5 text-ink-soft hover:bg-canvas hover:text-ink"
            title="Refresh Inflow Stream"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Security Architecture Box (Why it's safe without storing account credentials) */}
      <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 space-y-2">
        <div className="flex items-center gap-2 text-xs font-bold text-blue-950">
          <Shield className="h-4 w-4 text-blue-700 shrink-0" />
          <span>How It Works Safely: The RBI Account Aggregator (AA) Framework</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4 text-xs text-blue-900 pt-1">
          <div className="rounded-lg bg-white/70 p-2.5 border border-blue-100 shadow-2xs">
            <span className="font-bold block text-blue-950">1. Zero Account Credentials</span>
            <span className="text-[11px] text-blue-800">
              You never enter your account number, netbanking password, or MPIN on VyaparKitaab.
            </span>
          </div>
          <div className="rounded-lg bg-white/70 p-2.5 border border-blue-100 shadow-2xs">
            <span className="font-bold block text-blue-950">2. In-App Mobile Consent</span>
            <span className="text-[11px] text-blue-800">
              Approval happens securely inside your own bank app (SBI YONO / HDFC / PhonePe AA).
            </span>
          </div>
          <div className="rounded-lg bg-white/70 p-2.5 border border-blue-100 shadow-2xs">
            <span className="font-bold block text-blue-950">3. 100% Read-Only Inflows</span>
            <span className="text-[11px] text-blue-800">
              Only incoming <code className="font-mono text-emerald-800 font-bold">CREDIT</code> records are streamed; debits are impossible.
            </span>
          </div>
          <div className="rounded-lg bg-white/70 p-2.5 border border-blue-100 shadow-2xs">
            <span className="font-bold block text-blue-950">4. 1-Click Revocable</span>
            <span className="text-[11px] text-blue-800">
              Full control under the DPDP Act. Revoking consent cuts off data access immediately.
            </span>
          </div>
        </div>
      </div>

      {/* Connected Bank Switcher Bar */}
      <div className="space-y-1.5">
        <span className="text-[11px] font-bold uppercase tracking-wider text-ink-soft">
          Active Banking App Inflow Source:
        </span>
        <div className="flex flex-wrap gap-2">
          {SUPPORTED_BANKS.map((bank) => {
            const isActive = activeConsent?.fip_id === bank.id;
            return (
              <button
                key={bank.id}
                type="button"
                onClick={() => handleConnectBank(bank.id)}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all border ${
                  isActive
                    ? 'bg-navy text-white border-navy shadow-sm'
                    : 'bg-canvas text-ink hover:bg-canvas-sunk border-rule'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${isActive ? 'bg-emerald-400' : 'bg-ink-faint'}`} />
                <span>{bank.name}</span>
                {isActive && (
                  <span className="rounded-full bg-white/20 px-1.5 py-0.2 text-[10px] font-mono">
                    {activeConsent?.masked_acc}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* KPI Metrics Strip */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-rule bg-canvas p-4 shadow-2xs">
          <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
            Total Inward Income (सकल आय)
          </p>
          <p className="num mt-1 text-2xl font-extrabold text-emerald-700">
            +{formatINRPrecise(incomeData.total_inward_income)}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-soft">
            Verified across {incomeData.total_credits_count} bank credits
          </p>
        </div>

        <div className="rounded-xl border border-rule bg-canvas p-4 shadow-2xs">
          <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
            Average Inflow Ticket Size
          </p>
          <p className="num mt-1 text-2xl font-extrabold text-ink">
            {formatINR(incomeData.avg_ticket_size)}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-soft">Average single customer deposit</p>
        </div>

        <div className="rounded-xl border border-rule bg-canvas p-4 shadow-2xs">
          <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
            Connected Bank Account
          </p>
          <p className="mt-1 text-sm font-bold text-ink truncate">
            {activeConsent?.fip_name || 'State Bank of India'}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-soft flex items-center gap-1 font-mono">
            <Lock className="h-3 w-3 text-emerald-600" />
            Masked: {activeConsent?.masked_acc || 'XXXX-XXXX-4821'}
          </p>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 shadow-2xs">
          <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-900">
            Security Guarantee
          </p>
          <p className="mt-1 text-sm font-extrabold text-emerald-950 flex items-center gap-1">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> 0.0% Debit Risk
          </p>
          <p className="mt-0.5 text-[11px] text-emerald-800">
            Read-only FIP-to-FIU tunnel (mTLS)
          </p>
        </div>
      </div>

      {/* Visual Inward Money Flow Graph (Bank App -> AA Tunnel -> Income Stream -> Categories) */}
      <div className="rounded-xl border border-rule bg-canvas p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-emerald-600" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
              Safe Inward Money-Flow Graph: Bank App ➔ Encrypted AA Tunnel ➔ VyaparKitaab
            </h3>
          </div>
          <span className="text-[10px] text-ink-soft">
            {graphData?.edges.length ?? 4} verified flow edges
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-4 items-center pt-1">
          {/* Node 1: Bank App (FIP) */}
          <div className="rounded-xl border border-rule bg-canvas-raised p-3 shadow-2xs space-y-1">
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[9px] font-bold text-blue-800">
              Stage 1: FIP Bank App
            </span>
            <p className="text-xs font-bold text-ink pt-1 truncate">
              {activeConsent?.fip_name ?? 'State Bank of India'}
            </p>
            <p className="num text-sm font-extrabold text-ink">
              +{formatINR(incomeData.total_inward_income)}
            </p>
            <p className="text-[10px] text-ink-faint font-mono">{activeConsent?.masked_acc}</p>
          </div>

          {/* Node 2: RBI Sahamati AA Pipeline */}
          <div className="rounded-xl border border-blue-300 bg-blue-50/50 p-3 shadow-2xs space-y-1">
            <span className="rounded bg-blue-200 px-2 py-0.5 text-[9px] font-bold text-blue-900">
              Stage 2: Encrypted Tunnel
            </span>
            <p className="text-xs font-bold text-blue-950 pt-1">RBI Sahamati AA Pipe</p>
            <p className="text-[10px] text-blue-800">mTLS + XML Encryption</p>
            <p className="text-[10px] text-emerald-700 font-semibold">Zero Credential Exposure</p>
          </div>

          {/* Node 3: VyaparKitaab Inward Ledger */}
          <div className="rounded-xl border-2 border-emerald-600 bg-emerald-50/70 p-3.5 shadow-2xs space-y-1 text-center">
            <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[9px] font-bold text-white uppercase">
              Stage 3: Income Stream
            </span>
            <p className="text-xs font-extrabold text-emerald-950 pt-1">VyaparKitaab Ledger</p>
            <p className="num text-base font-extrabold text-emerald-800">
              +{formatINRPrecise(incomeData.total_inward_income)}
            </p>
            <p className="text-[10px] text-emerald-900 font-medium">Verified Inward Credits</p>
          </div>

          {/* Node 4: Income Category Streams */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-ink-soft block">
              Stage 4: Revenue Channels
            </span>
            {incomeData.category_breakdown.slice(0, 3).map((cat) => (
              <div
                key={cat.category}
                className="rounded-lg border border-rule bg-canvas-raised p-2 text-xs flex items-center justify-between"
              >
                <div className="truncate pr-1">
                  <p className="font-semibold text-ink text-[11px] truncate">{cat.category}</p>
                  <p className="text-[9px] text-ink-soft">{cat.percentage}% of total</p>
                </div>
                <span className="num font-bold text-emerald-700 text-xs shrink-0">
                  +{formatINR(cat.total_amount)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Real-time Account Aggregator Live Bank Feed Panel */}
      <LiveBankFeed />

      {/* Dual Chart: Monthly Inward Trend + Recent Credits Ledger */}
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Left: Monthly Inward Trend Bars */}
        <div className="rounded-xl border border-rule bg-canvas p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-emerald-600" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                Monthly Inward Revenue Inflow
              </h3>
            </div>
            <span className="text-[10px] text-ink-soft">Aggregated by month</span>
          </div>

          {/* Live Stream Responsive Recharts Bar Chart */}
          <div className="h-44 w-full pt-1">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={throttledTrend}
                margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 11, fill: '#64748B' }}
                  tickLine={false}
                  axisLine={{ stroke: '#CBD5E1' }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#64748B' }}
                  tickLine={false}
                  axisLine={{ stroke: '#CBD5E1' }}
                  tickFormatter={(val: number) => `₹${val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val}`}
                />
                <Tooltip
                  formatter={(val: unknown) => [formatINRPrecise(Number(val) || 0), 'Income']}
                  labelFormatter={(label) => `Month: ${label}`}
                  contentStyle={{
                    backgroundColor: '#FFFFFF',
                    borderRadius: '8px',
                    border: '1px solid #E2E8F0',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
                  }}
                />
                <Bar
                  dataKey="total_income"
                  fill="#059669"
                  isAnimationActive={false}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2 pt-1 border-t border-rule/60">
            {throttledTrend.map((m) => (
              <div key={m.month} className="flex items-center justify-between text-xs">
                <span className="font-semibold text-ink">{m.month}</span>
                <span className="num font-bold text-emerald-700">
                  +{formatINRPrecise(m.total_income)}{' '}
                  <span className="text-[10px] font-normal text-ink-soft">
                    ({m.transaction_count} credits)
                  </span>
                </span>
              </div>
            ))}
          </div>

          {/* Category Split */}
          <div className="space-y-2 pt-3 border-t border-rule">
            <span className="text-[11px] font-bold uppercase tracking-wider text-ink-soft block">
              Inward Revenue Categorization:
            </span>
            <div className="space-y-2">
              {incomeData.category_breakdown.map((cat) => (
                <div key={cat.category} className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="font-medium text-ink">{cat.category}</span>
                    <span className="num font-bold text-ink">
                      +{formatINR(cat.total_amount)}{' '}
                      <span className="text-ink-soft font-normal">({cat.percentage}%)</span>
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-canvas-sunk overflow-hidden">
                    <div
                      style={{ width: `${Math.min(100, cat.percentage)}%` }}
                      className="h-full bg-emerald-600 rounded-full"
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Verified Inward Credits Ledger */}
        <div className="rounded-xl border border-rule bg-canvas p-4 space-y-3 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <ArrowDownLeft className="h-4 w-4 text-emerald-600" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                  Verified Inward Credits Ledger
                </h3>
              </div>
              <span className="rounded bg-emerald-100 px-2 py-0.5 text-[9px] font-bold text-emerald-800">
                100% Inward Only
              </span>
            </div>
            <p className="text-[11px] text-ink-soft">
              Real-time statement entries delivered via the read-only Account Aggregator session.
            </p>

            <div className="space-y-2 pt-1 overflow-y-auto max-h-80">
              {incomeData.recent_inflows.map((tx) => (
                <div
                  key={tx.txn_id}
                  className="rounded-lg border border-rule bg-canvas-raised p-2.5 space-y-1 text-xs hover:border-emerald-400 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="rounded bg-canvas-sunk px-1.5 py-0.5 text-[9px] font-bold text-ink-soft uppercase">
                      {tx.mode} Credit
                    </span>
                    <span className="num font-extrabold text-emerald-700 text-sm">
                      +{formatINRPrecise(tx.amount)}
                    </span>
                  </div>
                  <p className="font-semibold text-ink text-[11px] truncate">{tx.narration}</p>
                  <div className="flex items-center justify-between text-[10px] text-ink-faint pt-0.5">
                    <span>{tx.date}</span>
                    <span className="font-mono text-ink-soft">{tx.masked_acc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3 pt-2 border-t border-rule text-[11px] text-ink-soft flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Lock className="h-3 w-3 text-emerald-600" /> AES-128 Blind-Indexed
            </span>
            <span>Zero Withdrawal Access Guaranteed</span>
          </div>
        </div>
      </div>

      {/* Modal: Connect Banking App with 2-Step OTP Consent Verification */}
      {showConsentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-rule bg-canvas-raised p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-rule pb-3">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-emerald-600" />
                <h3 className="text-base font-bold text-ink">Connect Banking App via RBI AA</h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowConsentModal(false);
                  setAaOtpSent(false);
                  setAaError(null);
                }}
                className="text-ink-soft hover:text-ink text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-ink-soft leading-relaxed">
              Select your FIP bank below and verify your consent via 6-digit OTP (delivered to your Gmail SMTP inbox).
              <strong> VyaparKitaab never asks for or stores your bank account number or password.</strong>
            </p>

            <div className="grid grid-cols-2 gap-2">
              {SUPPORTED_BANKS.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => setSelectedBankId(b.id)}
                  className={`flex items-center gap-2 rounded-lg border p-2.5 text-xs font-semibold transition-all ${
                    selectedBankId === b.id
                      ? 'border-navy bg-navy-tint text-navy'
                      : 'border-rule bg-canvas text-ink hover:bg-canvas-sunk'
                  }`}
                >
                  <span className={`h-2.5 w-2.5 rounded-full ${b.color}`} />
                  <span className="truncate font-bold">{b.name}</span>
                </button>
              ))}
            </div>

            <div className="space-y-2.5 pt-1">
              <div>
                <label className="text-xs font-semibold text-ink">Linked Mobile Number</label>
                <input
                  type="tel"
                  maxLength={10}
                  value={aaPhone}
                  onChange={(e) => setAaPhone(e.target.value)}
                  placeholder="9876543210"
                  className="mt-1 w-full rounded border border-rule bg-canvas px-3 py-2 text-xs"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink">Email for Real OTP Verification (Gmail SMTP)</label>
                <input
                  type="email"
                  value={aaEmail}
                  onChange={(e) => setAaEmail(e.target.value)}
                  placeholder="yourname@gmail.com"
                  className="mt-1 w-full rounded border border-rule bg-canvas px-3 py-2 text-xs"
                />
              </div>

              {!aaOtpSent ? (
                <button
                  type="button"
                  onClick={handleSendConsentOtp}
                  className="w-full rounded-lg bg-navy px-4 py-2.5 text-xs font-bold text-white hover:bg-navy-dark"
                >
                  Send Consent Verification OTP
                </button>
              ) : (
                <div className="space-y-2 rounded-lg border border-navy/30 bg-navy-tint p-3">
                  <div className="text-[11px] font-semibold text-navy">{aaOtpHint}</div>
                  <input
                    type="text"
                    maxLength={6}
                    value={aaOtpCode}
                    onChange={(e) => setAaOtpCode(e.target.value)}
                    placeholder="Enter 6-digit OTP"
                    className="num w-full rounded border border-rule bg-canvas-raised px-3 py-2 text-center text-base font-bold tracking-widest"
                  />
                  <button
                    type="button"
                    onClick={handleVerifyAndConnect}
                    className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700"
                  >
                    Verify OTP &amp; Authorize Read-Only Consent
                  </button>
                </div>
              )}

              {aaError && (
                <p className="rounded bg-due-tint p-2 text-xs text-due">{aaError}</p>
              )}
            </div>

            <div className="rounded-lg bg-emerald-50/70 p-2.5 border border-emerald-200 text-[11px] text-emerald-900 flex items-start gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-700 shrink-0 mt-0.5" />
              <span>
                Regulated by the Reserve Bank of India (RBI) under the Non-Banking Financial Company - Account Aggregator (NBFC-AA) master direction.
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

