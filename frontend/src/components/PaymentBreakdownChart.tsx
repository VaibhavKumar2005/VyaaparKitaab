import React, { useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { Smartphone, Zap, CheckCircle2, ShieldCheck, ArrowUpRight } from 'lucide-react';
import { usePaymentSummary } from '../hooks/usePayments';
import { formatINR, formatINRPrecise } from '../lib/format';
import { LoadingState } from './ui/LoadingState';

const APP_COLORS: Record<string, string> = {
  'Google Pay': '#0057d2', // SAP Blue / Google Blue
  PhonePe: '#7c3aed',     // Purple
  Paytm: '#0284c7',       // Cyan
  'Other UPI': '#d97706',  // Amber
  Card: '#059669',        // Green
  Cash: '#475e75',        // Slate
};

export function PaymentBreakdownChart() {
  const [period, setPeriod] = useState<string>('30d');
  const { data, isLoading } = usePaymentSummary(period);

  if (isLoading || !data) {
    return <LoadingState label="Loading payment and UPI collection analytics…" />;
  }

  const { by_app, daily_series, total_collected, total_transactions, recent_payments } = data;

  const gpayItem = by_app.find((a) => a.app === 'Google Pay');
  const phonepeItem = by_app.find((a) => a.app === 'PhonePe');
  const paytmItem = by_app.find((a) => a.app === 'Paytm');
  const otherItem = by_app.filter((a) => !['Google Pay', 'PhonePe', 'Paytm'].includes(a.app));
  const otherTotal = otherItem.reduce((sum, a) => sum + a.amount, 0);

  return (
    <div className="rounded-lg border border-rule bg-white p-5 space-y-6">
      {/* ─── Header & Period Selector ─── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-ink">UPI & Gateway Collections (डिजिटल भुगतान सारांश)</h2>
            <span className="rounded bg-navy-tint px-2 py-0.5 text-[10px] font-bold text-primary flex items-center gap-1">
              <Zap className="h-3 w-3" /> Real-time Ingestion
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-soft">
            Live transactions categorized by customer payment app (Google Pay, PhonePe, Paytm, etc.)
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-ink-nav">Period:</span>
          {(['7d', '30d', 'all'] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                period === p
                  ? 'bg-primary text-white'
                  : 'border border-rule bg-chrome text-ink-nav hover:text-ink'
              }`}
            >
              {p === '7d' ? '7 Days' : p === '30d' ? '30 Days' : 'All Time'}
            </button>
          ))}
        </div>
      </div>

      {/* ─── Key UPI Metrics Cards ─── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Google Pay */}
        <div className="rounded-md border border-blue-200 bg-blue-50/50 p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#0057d2]">Google Pay (GPay)</span>
            <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-[#0057d2]">
              {gpayItem ? `${gpayItem.percentage}%` : '0%'}
            </span>
          </div>
          <p className="num mt-2 text-xl font-bold text-ink">
            {formatINR(gpayItem?.amount ?? 0)}
          </p>
          <p className="mt-1 text-[11px] text-ink-soft">
            {gpayItem?.count ?? 0} verified payments
          </p>
        </div>

        {/* PhonePe */}
        <div className="rounded-md border border-purple-200 bg-purple-50/50 p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-purple-700">PhonePe</span>
            <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700">
              {phonepeItem ? `${phonepeItem.percentage}%` : '0%'}
            </span>
          </div>
          <p className="num mt-2 text-xl font-bold text-ink">
            {formatINR(phonepeItem?.amount ?? 0)}
          </p>
          <p className="mt-1 text-[11px] text-ink-soft">
            {phonepeItem?.count ?? 0} verified payments
          </p>
        </div>

        {/* Paytm */}
        <div className="rounded-md border border-sky-200 bg-sky-50/50 p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-sky-700">Paytm UPI</span>
            <span className="rounded-full bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-700">
              {paytmItem ? `${paytmItem.percentage}%` : '0%'}
            </span>
          </div>
          <p className="num mt-2 text-xl font-bold text-ink">
            {formatINR(paytmItem?.amount ?? 0)}
          </p>
          <p className="mt-1 text-[11px] text-ink-soft">
            {paytmItem?.count ?? 0} verified payments
          </p>
        </div>

        {/* Total Settled */}
        <div className="rounded-md border border-emerald-200 bg-emerald-50/50 p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-800">Total Settled</span>
            <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
              100%
            </span>
          </div>
          <p className="num mt-2 text-xl font-bold text-ink">
            {formatINR(total_collected)}
          </p>
          <p className="mt-1 text-[11px] text-ink-soft">
            {total_transactions} total transactions
          </p>
        </div>
      </div>

      {/* ─── Stacked Bar Chart: Daily Payments by Channel ─── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-ink-soft">
          <span className="font-semibold text-ink">Daily UPI Collection Distribution (₹ Amount)</span>
          <span className="text-[11px]">Hover over bars to inspect app shares</span>
        </div>

        <div className="h-64 w-full">
          {daily_series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily_series} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#475e75' }} />
                <YAxis tick={{ fontSize: 11, fill: '#475e75' }} />
                <Tooltip
                  formatter={(value: any, name: any) => [
                    formatINRPrecise(Number(value) || 0),
                    name === 'google_pay'
                      ? 'Google Pay'
                      : name === 'phonepe'
                      ? 'PhonePe'
                      : name === 'paytm'
                      ? 'Paytm'
                      : 'Other UPI',
                  ]}
                  contentStyle={{ backgroundColor: '#ffffff', borderRadius: 8, borderColor: '#e5e7eb', fontSize: 12 }}
                />
                <Legend
                  formatter={(value) =>
                    value === 'google_pay'
                      ? 'Google Pay'
                      : value === 'phonepe'
                      ? 'PhonePe'
                      : value === 'paytm'
                      ? 'Paytm'
                      : 'Other UPI'
                  }
                  wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                />
                <Bar dataKey="google_pay" stackId="a" fill={APP_COLORS['Google Pay']} name="google_pay" />
                <Bar dataKey="phonepe" stackId="a" fill={APP_COLORS.PhonePe} name="phonepe" />
                <Bar dataKey="paytm" stackId="a" fill={APP_COLORS.Paytm} name="paytm" />
                <Bar dataKey="other" stackId="a" fill={APP_COLORS['Other UPI']} name="other" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-ink-soft border border-dashed border-rule rounded-md">
              No payments recorded in this period yet. New payments will show here immediately.
            </div>
          )}
        </div>
      </div>

      {/* ─── Recent Gateway Ingestion Ledger ─── */}
      {recent_payments && recent_payments.length > 0 && (
        <div className="space-y-2 border-t border-rule pt-4">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-ink">Recent Ingested Payments (Single-Writer Ledger)</span>
            <span className="text-[11px] text-ink-soft">Guaranteed idempotency • Zero double counts</span>
          </div>

          <div className="overflow-x-auto rounded-md border border-rule">
            <table className="min-w-full text-xs">
              <thead className="bg-chrome text-ink-nav border-b border-rule text-left">
                <tr>
                  <th className="px-3 py-2 font-semibold">Gateway ID</th>
                  <th className="px-3 py-2 font-semibold">Payment App</th>
                  <th className="px-3 py-2 font-semibold">Customer VPA</th>
                  <th className="px-3 py-2 font-semibold">Invoice Ref</th>
                  <th className="px-3 py-2 text-right font-semibold">Amount</th>
                  <th className="px-3 py-2 text-right font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule bg-white">
                {recent_payments.slice(0, 5).map((tx) => (
                  <tr key={tx.id} className="hover:bg-chrome/50">
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-soft">{tx.payment_id}</td>
                    <td className="px-3 py-2 font-medium flex items-center gap-1.5">
                      <span
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: APP_COLORS[tx.app] || '#475e75' }}
                      />
                      <span>{tx.app}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-ink-soft">{tx.vpa || 'UPI / Gateway'}</td>
                    <td className="px-3 py-2 text-ink-soft">{tx.invoice_id}</td>
                    <td className="num px-3 py-2 text-right font-semibold text-ink">
                      {formatINRPrecise(tx.amount)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="inline-flex items-center gap-1 rounded bg-positive-tint px-2 py-0.5 text-[10px] font-bold text-positive">
                        <CheckCircle2 className="h-3 w-3" /> Captured
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

