import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ShieldCheck, Store, Smartphone, CheckCircle2, Building2, Landmark, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { registerSchema, RegisterValues } from '../schemas/auth';
import { apiFetch } from '../lib/api';

const inputClass =
  'mt-1.5 w-full rounded-md border border-rule bg-canvas-raised px-3.5 py-2.5 text-sm outline-none focus:border-navy';

type KycVerificationResult = {
  status: string;
  provider?: string;
  checks?: Record<string, boolean | string>;
  gst_details: {
    gstin: string;
    pan: string;
    state_code: string;
    state_name: string;
    legal_name?: string | null;
    taxpayer_type: string;
    status: string;
  };
  bank_settlement: {
    bank_name: string;
    ifsc: string;
    masked_account: string;
    penny_drop_status?: string;
    status?: string;
  };
  message: string;
};

export function RegisterPage() {
  const { register: registerAccount, token } = useAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<'STORE_OWNER' | 'CUSTOMER'>('STORE_OWNER');
  const [businessName, setBusinessName] = useState('');
  const [businessAddress, setBusinessAddress] = useState('');
  const [gstin, setGstin] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [ifsc, setIfsc] = useState('');
  const [kycVerifying, setKycVerifying] = useState(false);
  const [kycResult, setKycResult] = useState<KycVerificationResult | null>(null);
  const [kycError, setKycError] = useState<string | null>(null);

  const {
    register: field,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', password: '', full_name: '', phone: '' },
  });

  const handleVerifyKyc = async () => {
    setKycError(null);
    setKycVerifying(true);
    try {
      if (!token) {
        throw new Error('Create and sign in to a merchant account before submitting KYC details.');
      }
      const res = await apiFetch<KycVerificationResult>('/auth/business/verify-kyc', {
        method: 'POST',
        body: JSON.stringify({
          gstin: gstin.trim().toUpperCase(),
          bank_account: bankAccount.trim(),
          ifsc: ifsc.trim().toUpperCase(),
        }),
      });
      setKycResult(res);
    } catch (err) {
      setKycResult(null);
      setKycError(err instanceof Error ? err.message : 'Unable to submit KYC details.');
    } finally {
      setKycVerifying(false);
    }
  };

  const onSubmit = async (values: RegisterValues) => {
    try {
      await registerAccount({
        ...values,
        role,
        business_name: role === 'STORE_OWNER' ? businessName : undefined,
        gstin: role === 'STORE_OWNER' ? gstin.trim().toUpperCase() : undefined,
        address: role === 'STORE_OWNER' ? businessAddress : undefined,
      });
      navigate(role === 'CUSTOMER' ? '/portal/bills' : '/app/dashboard');
    } catch (err) {
      setError('root', { message: err instanceof Error ? err.message : 'Unable to register' });
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-10">
      <div className="text-center">
        <Link to="/" className="font-display text-2xl font-bold text-navy">
          VyaparKitaab
        </Link>
        <h1 className="mt-4 font-display text-3xl font-bold">Create account & KYC</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Onboard your GST-compliant MSME store or create a customer passbook account.
        </p>
      </div>

      {/* Role Switcher */}
      <div className="mt-6 flex rounded-lg border border-rule bg-canvas-sunk p-1 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setRole('STORE_OWNER')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md py-2.5 transition-colors ${
            role === 'STORE_OWNER'
              ? 'bg-canvas-raised text-navy shadow-sm border border-rule'
              : 'text-ink-soft hover:text-ink'
          }`}
        >
          <Store className="h-4 w-4" />
          <span>Merchant Store Owner (GST KYC)</span>
        </button>
        <button
          type="button"
          onClick={() => setRole('CUSTOMER')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md py-2.5 transition-colors ${
            role === 'CUSTOMER'
              ? 'bg-canvas-raised text-navy shadow-sm border border-rule'
              : 'text-ink-soft hover:text-ink'
          }`}
        >
          <Smartphone className="h-4 w-4" />
          <span>Retail Customer (Passbook)</span>
        </button>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5" noValidate>
        {/* Step 1: Personal Credentials */}
        <div className="rounded-lg border border-rule bg-canvas-raised p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-rule pb-2.5">
            <span className="text-xs font-bold uppercase tracking-wider text-navy">
              1. Account Credentials
            </span>
            <span className="text-[11px] text-ink-faint">Role: {role}</span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="full_name" className="text-xs font-semibold">
                Full Name
              </label>
              <input
                {...field('full_name')}
                id="full_name"
                placeholder="Rajendra Sharma"
                autoComplete="name"
                className={inputClass}
              />
              {errors.full_name ? <p className="mt-1 text-xs text-due">{errors.full_name.message}</p> : null}
            </div>
            <div>
              <label htmlFor="phone" className="text-xs font-semibold">
                Mobile Number (+91)
              </label>
              <input
                {...field('phone')}
                id="phone"
                type="tel"
                placeholder="9876543210"
                autoComplete="tel"
                className={inputClass}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="email" className="text-xs font-semibold">
                Email Address
              </label>
              <input
                {...field('email')}
                id="email"
                type="email"
                placeholder="owner@sharmakirana.in"
                autoComplete="email"
                className={inputClass}
              />
              {errors.email ? <p className="mt-1 text-xs text-due">{errors.email.message}</p> : null}
            </div>
            <div>
              <label htmlFor="password" className="text-xs font-semibold">
                Password (min 8 chars)
              </label>
              <input
                {...field('password')}
                id="password"
                type="password"
                placeholder="••••••••"
                autoComplete="new-password"
                className={inputClass}
              />
              {errors.password ? <p className="mt-1 text-xs text-due">{errors.password.message}</p> : null}
            </div>
          </div>
        </div>

        {/* Step 2: Merchant KYC Application Scheme */}
        {role === 'STORE_OWNER' ? (
          <div className="rounded-lg border border-rule bg-canvas-raised p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-rule pb-2.5">
              <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-navy">
                <ShieldCheck className="h-4 w-4 text-positive" />
                2. Merchant KYC & Settlement Scheme
              </span>
              <span className="rounded bg-positive-tint px-2 py-0.5 text-[10px] font-bold text-positive">
                GSTN + Penny-Drop
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5 text-ink-soft" />
                  Shop / Trade Name
                </label>
                <input
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  placeholder="Sharma Kirana & General Store"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="text-xs font-semibold">15-Digit GSTIN</label>
                <input
                  value={gstin}
                  onChange={(e) => setGstin(e.target.value.toUpperCase())}
                  maxLength={15}
                  placeholder="09AAACS1429B1Z8"
                  className={`${inputClass} font-mono uppercase`}
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold">Registered Shop Address</label>
              <input
                value={businessAddress}
                onChange={(e) => setBusinessAddress(e.target.value)}
                placeholder="Plot 42, Civil Lines, Mathura, UP - 281001"
                className={inputClass}
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold flex items-center gap-1">
                  <Landmark className="h-3.5 w-3.5 text-ink-soft" />
                  Settlement Bank A/C No.
                </label>
                <input
                  value={bankAccount}
                  onChange={(e) => setBankAccount(e.target.value)}
                  placeholder="50100234987612"
                  className={`${inputClass} font-mono`}
                />
              </div>
              <div>
                <label className="text-xs font-semibold">Bank IFSC Code</label>
                <input
                  value={ifsc}
                  onChange={(e) => setIfsc(e.target.value.toUpperCase())}
                  maxLength={11}
                  placeholder="HDFC0001234"
                  className={`${inputClass} font-mono uppercase`}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <p className="text-[11px] text-ink-faint">
                Verifies State Code, embedded 10-char PAN & IMPS settlement account.
              </p>
              <button
                type="button"
                onClick={handleVerifyKyc}
                disabled={kycVerifying}
                className="rounded-md border border-navy bg-canvas px-3 py-1.5 text-xs font-semibold text-navy hover:bg-navy hover:text-white transition-colors"
              >
                {kycVerifying ? 'Verifying KYC…' : 'Verify KYC Now'}
              </button>
            </div>

            {kycError ? (
              <div className="flex items-start gap-2 rounded-md bg-due-tint p-2.5 text-xs text-due">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <span>{kycError}</span>
              </div>
            ) : null}

            {kycResult ? (
              <div className="rounded-md border border-positive/30 bg-positive-tint/50 p-3 text-xs space-y-1.5">
                <div className="flex items-center justify-between font-bold text-positive">
                  <span className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4" />
                    KYC checks completed: {kycResult.status}
                  </span>
                  <span className="font-mono text-[10px]">{kycResult.gst_details.status}</span>
                </div>
                <div className="grid grid-cols-2 gap-1 text-[11px] text-ink-soft pt-1">
                  <div>
                    <span className="font-semibold text-ink">PAN extracted from GSTIN:</span>{' '}
                    <span className="font-mono">{kycResult.gst_details.pan}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-ink">State Jurisdiction:</span>{' '}
                    <span>
                      {kycResult.gst_details.state_code} ({kycResult.gst_details.state_name})
                    </span>
                  </div>
                  <div>
                    <span className="font-semibold text-ink">Bank (from IFSC):</span>{' '}
                    <span>{kycResult.bank_settlement.bank_name}</span>
                  </div>
                  <div>
                    <span className="font-semibold text-ink">A/C Masked:</span>{' '}
                    <span className="font-mono">{kycResult.bank_settlement.masked_account}</span>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {errors.root ? (
          <p role="alert" className="rounded-md bg-due-tint p-3 text-sm text-due">
            {errors.root.message}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-navy px-4 py-2.5 font-semibold text-white hover:bg-navy-dark disabled:opacity-60"
        >
          {isSubmitting
            ? 'Creating account…'
            : role === 'STORE_OWNER'
              ? 'Complete KYC & Open Store Books'
              : 'Create Customer Account'}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-soft">
        Already registered?{' '}
        <Link to="/login" className="font-semibold text-navy hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
