import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  FileSpreadsheet,
  QrCode,
  Receipt,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Upload,
} from 'lucide-react';

const capabilities = [
  {
    icon: Receipt,
    title: 'GST Invoicing & GSTR-1 Export',
    body: 'Create 0%, 5%, 12%, 18%, or 28% GST invoices with live CGST/SGST splits, stock deduction, and 1-click GSTR-1 JSON export.',
  },
  {
    icon: QrCode,
    title: 'Dynamic NPCI UPI QR & Razorpay',
    body: 'Every invoice generates a scannable UPI QR wired to your store VPA plus optional Razorpay Checkout & webhook settlement.',
  },
  {
    icon: Upload,
    title: 'Real Bank, GPay & PhonePe Sync',
    body: 'Import SBI, HDFC, ICICI, Axis CSV/TSV/PDFs (including password-locked PDFs), Google Takeout HTML, or stream live alerts via UPI Bridge.',
  },
  {
    icon: CheckCircle2,
    title: '1-Click Udhaar Auto-Reconciliation',
    body: 'Incoming real UPI/bank credits are matched against open customer invoices so you can settle Udhaar ledgers without double-counting.',
  },
  {
    icon: Smartphone,
    title: 'Two-Sided Customer Passbook & OCR',
    body: 'Verified customers automatically receive store bills in /portal/bills and scan external receipts/PDFs with in-memory Tesseract OCR.',
  },
  {
    icon: Sparkles,
    title: 'Unified Ledger & Ask AI Assistant',
    body: 'Query spending, discounts saved, low-stock restock risks, and 7-day revenue forecasts across your real PostgreSQL ledger.',
  },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-rule bg-canvas-raised/80 backdrop-blur-xs">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="font-display text-xl font-bold text-navy">VyaparKitaab</span>
            <span className="hidden sm:inline-block rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-800">
              Live MSME &amp; UPI Ledger
            </span>
          </div>
          <nav className="flex items-center gap-3 text-sm font-medium">
            <Link to="/login" className="px-3 py-2 text-ink-soft hover:text-ink">
              Sign in
            </Link>
            <Link
              to="/register"
              className="rounded-md bg-navy px-4 py-2 font-semibold text-white hover:bg-navy-dark"
            >
              Create Live Account
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-12 sm:px-6 sm:pt-18">
          <div className="inline-flex items-center gap-2 rounded-full border border-rule bg-canvas-raised px-3 py-1 text-xs font-semibold text-navy">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            <span>Zero Bank Passwords • Fernet Encrypted PII • Multi-Tenant PostgreSQL</span>
          </div>
          <h1 className="mt-5 max-w-4xl font-display text-4xl font-bold leading-tight sm:text-6xl">
            One live financial notebook for Indian stores, UPI payments, and customer passbooks.
          </h1>
          <p className="mt-5 max-w-2xl text-base sm:text-lg text-ink-soft">
            Issue GST bills with scannable UPI QRs, import your real bank/GPay/PhonePe statements,
            reconcile incoming credits against open Udhaar automatically, and give every customer a verified digital passbook.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              to="/register"
              className="inline-flex items-center gap-2 rounded-md bg-navy px-5 py-3 text-sm font-semibold text-white hover:bg-navy-dark"
            >
              <Building2 className="h-4 w-4" />
              <span>Open Your Live Store Account</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-md border border-navy/30 bg-canvas-raised px-5 py-3 text-sm font-semibold text-navy hover:bg-navy-tint"
            >
              <Smartphone className="h-4 w-4" />
              <span>Customer Passbook / Merchant Sign In</span>
            </Link>
            <Link
              to="/app/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-3 text-xs font-semibold text-ink-soft hover:text-navy hover:underline"
            >
              <FileSpreadsheet className="h-3.5 w-3.5" />
              <span>Or preview sample store sandbox</span>
            </Link>
          </div>
        </section>

        <section className="border-y border-rule bg-canvas-raised">
          <div className="mx-auto grid max-w-6xl gap-px bg-rule sm:grid-cols-2 lg:grid-cols-3">
            {capabilities.map(({ icon: Icon, title, body }) => (
              <div key={title} className="bg-canvas-raised p-6 space-y-2">
                <div className="inline-flex rounded-lg bg-navy-tint p-2 text-navy">
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="font-display text-base font-bold text-ink">{title}</h2>
                <p className="text-sm text-ink-soft leading-relaxed">{body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-8 text-xs text-ink-faint sm:px-6">
        <span>© 2026 VyaparKitaab — Built for Indian MSMEs &amp; Everyday UPI Tracking</span>
        <span>FastAPI • PostgreSQL • React • RBI AA Ready</span>
      </footer>
    </div>
  );
}
