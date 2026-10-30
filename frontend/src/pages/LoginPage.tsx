import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Store, Smartphone, ShieldCheck, CheckCircle2, ArrowRight, Mail } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { loginSchema, LoginValues } from '../schemas/auth';

const inputClass =
  'mt-1.5 w-full rounded-md border border-rule bg-canvas-raised px-3.5 py-2.5 text-sm outline-none focus:border-navy';

export function LoginPage() {
  const { login, customerOtpLogin, enableDemo, enableCustomerDemo } = useAuth();
  const navigate = useNavigate();

  // Tab state: 'BUSINESS' or 'CUSTOMER'
  const [activeTab, setActiveTab] = useState<'BUSINESS' | 'CUSTOMER'>('BUSINESS');

  // Customer OTP state
  const [customerPhone, setCustomerPhone] = useState('9876543210');
  const [customerEmail, setCustomerEmail] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpValue, setOtpValue] = useState('');
  const [otpHint, setOtpHint] = useState<string>('');
  const [otpError, setOtpError] = useState<string | null>(null);
  const [isSendingOtp, setIsSendingOtp] = useState(false);
  const [smtpConfigured, setSmtpConfigured] = useState(false);

  useEffect(() => {
    fetch('/api/v1/auth/otp/status')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setSmtpConfigured(Boolean(d.smtp_configured));
        }
      })
      .catch(() => {});
  }, []);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: 'demo@vyapaarkitaab.in', password: 'Password123!' },
  });

  const onBusinessSubmit = async (values: LoginValues) => {
    try {
      await login(values.email, values.password);
      navigate('/app/dashboard');
    } catch (err) {
      setError('root', { message: err instanceof Error ? err.message : 'Unable to sign in' });
    }
  };

  const handleSendOtp = async () => {
    const boundTarget = customerEmail.trim() || customerPhone.trim();
    if (!boundTarget || (!boundTarget.includes('@') && boundTarget.length < 10)) {
      setOtpError('Please enter a valid 10-digit Indian mobile number or email address');
      return;
    }
    setOtpError(null);
    setIsSendingOtp(true);
    setOtpValue(''); // Never auto-fill; user enters the 6-digit code manually
    try {
      const params = new URLSearchParams({
        phone: boundTarget,
        purpose: 'LOGIN',
      });
      const res = await fetch(`/api/v1/auth/otp/send?${params.toString()}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to dispatch OTP' }));
        throw new Error(err.detail || 'Failed to dispatch OTP');
      }
      const data = (await res.json()) as {
        dev_otp?: string;
        channel?: string;
        provider?: string;
        message?: string;
      };
      if (data.channel === 'email') {
        setOtpHint(`Sent via Gmail SMTP to ${boundTarget}`);
      } else if (data.channel === 'sms') {
        setOtpHint(`SMS OTP sent to +91 ${boundTarget}`);
      } else if (data.dev_otp) {
        setOtpHint(`Generated DB Code (set SMTP_USER & SMTP_PASSWORD in .env for email delivery): ${data.dev_otp}`);
      } else {
        setOtpHint('Enter 6-digit verification code');
      }
      setOtpSent(true);
    } catch (err) {
      setOtpError(err instanceof Error ? err.message : 'Unable to send OTP');
    } finally {
      setIsSendingOtp(false);
    }
  };

  const handleVerifyCustomerOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpValue || otpValue.length < 6) {
      setOtpError('Please enter 6-digit OTP');
      return;
    }
    setOtpError(null);
    const boundTarget = customerEmail.trim() || customerPhone.trim();
    try {
      await customerOtpLogin(boundTarget, otpValue);
      navigate('/portal/bills');
    } catch (err) {
      setOtpError(err instanceof Error ? err.message : 'Invalid or expired OTP');
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-10">
      <div className="text-center">
        <Link to="/" className="font-display text-2xl font-bold text-navy">
          VyaparKitaab
        </Link>
        <h1 className="mt-4 font-display text-2xl sm:text-3xl font-bold">Sign in to your account</h1>
        <p className="mt-1 text-sm text-ink-soft">
          Separate, secure login for business merchants and retail customers.
        </p>
      </div>

      {/* Role Switcher Tabs */}
      <div className="mt-6 flex rounded-lg border border-rule bg-canvas-sunk p-1 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab('BUSINESS')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md py-2.5 transition-colors ${
            activeTab === 'BUSINESS'
              ? 'bg-canvas-raised text-navy shadow-sm border border-rule'
              : 'text-ink-soft hover:text-ink'
          }`}
        >
          <Store className="h-4 w-4" />
          <span>Business (दुकानदार / Merchant)</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('CUSTOMER')}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md py-2.5 transition-colors ${
            activeTab === 'CUSTOMER'
              ? 'bg-canvas-raised text-navy shadow-sm border border-rule'
              : 'text-ink-soft hover:text-ink'
          }`}
        >
          <Smartphone className="h-4 w-4" />
          <span>Customer (ग्राहक पासबुक)</span>
        </button>
      </div>

      {/* 1. BUSINESS LOGIN TAB (Store Owner with KYC credentials) */}
      {activeTab === 'BUSINESS' ? (
        <div className="mt-5 space-y-4">
          <div className="rounded-lg border border-rule bg-canvas-raised p-4 text-xs space-y-2">
            <div className="flex items-center justify-between font-semibold text-navy">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4 text-positive" />
                Verified Merchant KYC
              </span>
              <span className="rounded bg-positive-tint px-2 py-0.5 text-[10px] text-positive font-bold">
                GST Ready
              </span>
            </div>
            <p className="text-ink-soft">
              Merchant portal manages complete bahi-khata, customer balances, inventory wholesale costs, and tax bills.
            </p>
            <button
              type="button"
              onClick={async () => {
                try {
                  await login('demo@vyapaarkitaab.in', 'Password123!');
                  navigate('/app/dashboard');
                } catch {
                  enableDemo();
                  navigate('/app/dashboard');
                }
              }}
              className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-md bg-navy px-3 py-2 text-xs font-semibold text-white hover:bg-navy-dark transition-colors"
            >
              <span>⚡ 1-Click Live Login (Sharma Kirana Store - Real Database)</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-ink-soft">Need offline sandbox testing?</span>
              <button
                type="button"
                onClick={() => {
                  enableDemo();
                  navigate('/app/dashboard');
                }}
                className="text-[11px] text-navy font-semibold hover:underline"
              >
                Launch Mock Demo Mode
              </button>
            </div>
          </div>

          <form onSubmit={handleSubmit(onBusinessSubmit)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="email" className="text-sm font-medium">Business Email or Phone</label>
              <input {...register('email')} id="email" type="email" autoComplete="email" placeholder="owner@shop.com" className={inputClass} />
              {errors.email ? <p className="mt-1 text-xs text-due">{errors.email.message}</p> : null}
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium">Password</label>
              <input {...register('password')} id="password" type="password" autoComplete="current-password" placeholder="••••••••" className={inputClass} />
              {errors.password ? <p className="mt-1 text-xs text-due">{errors.password.message}</p> : null}
            </div>
            {errors.root ? (
              <p role="alert" className="rounded-md bg-due-tint p-3 text-sm text-due">{errors.root.message}</p>
            ) : null}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-md border border-rule bg-canvas-raised px-4 py-2.5 font-semibold text-ink hover:bg-canvas-sunk disabled:opacity-60 text-sm"
            >
              {isSubmitting ? 'Signing in…' : 'Sign in as Merchant'}
            </button>
          </form>
        </div>
      ) : (
        /* 2. CUSTOMER LOGIN TAB (Universal Indian Phone + OTP Login) */
        <div className="mt-5 space-y-4">
          <div className="rounded-lg border border-rule bg-canvas-raised p-4 text-xs space-y-2">
            <div className="flex items-center justify-between font-semibold text-navy">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-positive" />
                Zero-Friction Phone OTP
              </span>
              <span className="rounded bg-navy-tint px-2 py-0.5 text-[10px] text-navy font-bold">
                Customer Passbook
              </span>
            </div>
            <p className="text-ink-soft">
              No complex KYC required for customers. Enter your mobile number to view your bills, payment receipts, and clear dues via UPI.
            </p>
            <button
              type="button"
              onClick={() => {
                enableCustomerDemo();
                navigate('/portal/bills');
              }}
              className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-md bg-positive px-3 py-2 text-xs font-semibold text-white hover:bg-positive/90 transition-colors"
            >
              <span>⚡ 1-Click Customer Access (Ramesh Kumar)</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <form onSubmit={handleVerifyCustomerOtp} className="space-y-4">
            <div>
              <label htmlFor="phone" className="text-sm font-medium">Customer Mobile Number (मोबाइल नंबर)</label>
              <div className="mt-1.5 flex gap-2">
                <span className="inline-flex items-center rounded-md border border-rule bg-canvas-sunk px-3 text-sm text-ink-soft">
                  +91
                </span>
                <input
                  id="phone"
                  type="tel"
                  maxLength={10}
                  value={customerPhone}
                  onChange={(e) => {
                    setCustomerPhone(e.target.value);
                    setOtpSent(false);
                  }}
                  placeholder="9876543210"
                  className="w-full rounded-md border border-rule bg-canvas-raised px-3.5 py-2.5 text-sm outline-none focus:border-navy"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="customerEmail" className="text-sm font-medium flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-navy" />
                  <span>Or Email for Real OTP Delivery (Gmail SMTP)</span>
                </label>
                <span className="text-[11px] font-semibold text-ink-soft">
                  {smtpConfigured ? 'SMTP Active' : 'Configure in .env'}
                </span>
              </div>
              <input
                id="customerEmail"
                type="email"
                value={customerEmail}
                onChange={(e) => {
                  setCustomerEmail(e.target.value);
                  setOtpSent(false);
                }}
                placeholder="yourname@gmail.com (optional — binds OTP to this email)"
                className={inputClass}
              />
            </div>

            {!otpSent ? (
              <button
                type="button"
                disabled={isSendingOtp}
                onClick={handleSendOtp}
                className="w-full rounded-md bg-navy px-4 py-2.5 font-semibold text-white hover:bg-navy-dark disabled:opacity-60 text-sm flex items-center justify-center gap-1.5"
              >
                <span>{isSendingOtp ? 'Dispatching OTP…' : 'Send 6-Digit OTP (ओटीपी भेजें)'}</span>
              </button>
            ) : (
              <div className="space-y-3 rounded-md border border-navy/20 bg-navy-tint p-3.5">
                <div className="flex flex-col gap-1 text-xs">
                  <span className="font-semibold text-ink">
                    Enter 6-digit OTP to verify +91 {customerPhone}:
                  </span>
                  {otpHint && (
                    <span className="text-[11px] font-mono font-bold text-navy">{otpHint}</span>
                  )}
                </div>
                <input
                  type="text"
                  maxLength={6}
                  value={otpValue}
                  onChange={(e) => setOtpValue(e.target.value)}
                  placeholder="Enter 6-digit OTP"
                  className="num w-full rounded border border-rule bg-canvas-raised px-3 py-2 text-center text-lg font-bold tracking-widest outline-none focus:border-navy"
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    className="flex-1 rounded-md bg-navy px-4 py-2.5 font-semibold text-white hover:bg-navy-dark text-sm"
                  >
                    Verify OTP & View My Bills
                  </button>
                  <button
                    type="button"
                    onClick={handleSendOtp}
                    className="rounded-md border border-rule bg-canvas-raised px-3 py-2.5 text-xs font-semibold text-ink hover:bg-canvas-sunk"
                  >
                    Resend
                  </button>
                </div>
              </div>
            )}

            {otpError && (
              <p className="rounded-md bg-due-tint p-2 text-xs text-due">{otpError}</p>
            )}
          </form>
        </div>
      )}

      <p className="mt-6 text-center text-xs text-ink-soft">
        New merchant? <Link to="/register" className="font-semibold text-navy hover:underline">Register your business & complete GST KYC</Link>
      </p>
    </div>
  );
}