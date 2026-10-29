import React, { useState } from 'react';
import {
  Lock,
  ShieldCheck,
  Plus,
  Trash2,
  Sparkles,
  ShoppingBag,
  CreditCard,
  X,
  TrendingUp,
  Receipt,
  CheckCircle2,
  ArrowRight,
  Network,
  Building2,
  Smartphone,
  Shield,
} from 'lucide-react';
import {
  usePersonalSpendingAnalytics,
  useCreatePersonalPurchase,
  useDeletePersonalPurchase,
  useTransactionGraph,
  usePaymentsToOthersSummary,
  useStoreDrilldown,
  parseInvoiceTextApi,
  type CreatePurchasePayload,
} from '../hooks/usePurchases';
import { formatINR, formatINRPrecise, formatDate } from '../lib/format';
import { BankingIncomeExplorer } from '../components/BankingIncomeExplorer';

const MARKETPLACES = [
  'Amazon',
  'Flipkart',
  'Blinkit',
  'Myntra',
  'Zepto',
  'Instamart',
  'Direct UPI to Person / Contact',
  'Local Shop / Merchant',
  'Other',
];
const CATEGORIES = [
  'Electronics',
  'Shopping',
  'Groceries',
  'Fashion & Apparel',
  'Home & Kitchen',
  'Health & Personal Care',
  'Books',
  'Food & Dining',
];
const PAYMENT_METHODS = [
  'UPI (Google Pay)',
  'UPI (PhonePe)',
  'UPI (Paytm)',
  'Credit Card',
  'Debit Card',
  'Cash on Delivery',
];

export function CustomerDashboard() {
  const { data: analytics, isLoading, refetch } = usePersonalSpendingAnalytics();
  const { data: graphData } = useTransactionGraph();
  const { data: paymentsSummary } = usePaymentsToOthersSummary();
  const [selectedStore, setSelectedStore] = useState<string | null>(null);
  const [hoveredTxIdx, setHoveredTxIdx] = useState<number | null>(null);
  const { data: storeDrilldown } = useStoreDrilldown(selectedStore);
  const createPurchaseMutation = useCreatePersonalPurchase();
  const deletePurchaseMutation = useDeletePersonalPurchase();

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'form' | 'paste'>('form');

  // Form Fields
  const [marketplace, setMarketplace] = useState('Amazon');
  const [category, setCategory] = useState('Shopping');
  const [amount, setAmount] = useState<string>('');
  const [orderId, setOrderId] = useState<string>('');
  const [itemsNote, setItemsNote] = useState<string>('');
  const [paymentMethod, setPaymentMethod] = useState('UPI (Google Pay)');
  const [purchasedDate, setPurchasedDate] = useState<string>(
    () => new Date().toISOString().split('T')[0]
  );

  // Paste / Auto-Extract State
  const [rawInvoiceText, setRawInvoiceText] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractSuccessMsg, setExtractSuccessMsg] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const resetForm = () => {
    setMarketplace('Amazon');
    setCategory('Shopping');
    setAmount('');
    setOrderId('');
    setItemsNote('');
    setPaymentMethod('UPI (Google Pay)');
    setPurchasedDate(new Date().toISOString().split('T')[0]);
    setRawInvoiceText('');
    setExtractSuccessMsg(null);
    setFormError(null);
  };

  const handleOpenModal = () => {
    resetForm();
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    resetForm();
  };

  const handleAutoExtract = async () => {
    if (!rawInvoiceText.trim()) {
      setFormError('Please paste order confirmation text, receipt, or SMS first.');
      return;
    }
    setIsExtracting(true);
    setFormError(null);
    setExtractSuccessMsg(null);
    try {
      const parsed = await parseInvoiceTextApi(rawInvoiceText);
      if (parsed.marketplace) setMarketplace(parsed.marketplace);
      if (parsed.order_id) setOrderId(parsed.order_id);
      if (parsed.amount) setAmount(parsed.amount.toString());
      if (parsed.items_summary) setItemsNote(parsed.items_summary);
      if (parsed.purchased_at) {
        setPurchasedDate(new Date(parsed.purchased_at).toISOString().split('T')[0]);
      }
      setExtractSuccessMsg(
        `Extracted details from ${parsed.marketplace}: Order #${parsed.order_id ?? 'N/A'}, Amount ₹${parsed.amount ?? 0}`
      );
      // Auto-switch to review form
      setActiveTab('form');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to extract invoice text';
      setFormError(`Extraction failed: ${msg}. You can enter details manually.`);
    } finally {
      setIsExtracting(false);
    }
  };

  const handleSubmitPurchase = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setFormError('Please enter a valid purchase amount greater than ₹0.');
      return;
    }
    if (!orderId.trim()) {
      setFormError('Please enter the Marketplace Order ID.');
      return;
    }

    const payload: CreatePurchasePayload = {
      marketplace: marketplace.trim(),
      category: category.trim() || 'Shopping',
      amount: parsedAmount,
      currency: 'INR',
      purchased_at: new Date(purchasedDate).toISOString(),
      order_id: orderId.trim(),
      items_note: itemsNote.trim() || undefined,
      payment_method: paymentMethod.trim() || 'UPI (Google Pay)',
    };

    try {
      await createPurchaseMutation.mutateAsync(payload);
      handleCloseModal();
      void refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not save purchase';
      setFormError(msg);
    }
  };

  const handleDelete = async (purchaseId: string) => {
    if (!window.confirm('Delete this purchase record from your private ledger?')) return;
    try {
      await deletePurchaseMutation.mutateAsync(purchaseId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete';
      alert(`Delete error: ${msg}`);
    }
  };

  const todayCost = analytics?.today_cost ?? 0;
  const weekCost = analytics?.week_cost ?? 0;
  const monthCost = analytics?.month_cost ?? 0;
  const totalOrders = analytics?.total_orders ?? 0;
  const dailyTrend = analytics?.daily_trend ?? [];
  const marketplaceBreakdown = analytics?.marketplace_breakdown ?? [];
  const categoryBreakdown = analytics?.category_breakdown ?? [];
  const recentPurchases = analytics?.recent_purchases ?? [];

  const maxDailyCost = Math.max(1, ...dailyTrend.map((d) => d.total_cost));

  return (
    <div className="space-y-6">
      {/* Top Header & Confidentiality Shield */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-ink">Personal Spending & Cost Tracker</h1>
            <span className="flex items-center gap-1 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> AES-128 Fernet Encrypted
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-soft">
            Private, leak-proof ledger tracking your Amazon & marketplace purchases and daily costs incurred.
          </p>
        </div>

        <button
          type="button"
          onClick={handleOpenModal}
          className="inline-flex items-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          <span>Record Purchase (खरीद दर्ज करें)</span>
        </button>
      </div>

      {/* Security Banner */}
      <div className="rounded-lg border border-navy/20 bg-navy-tint/60 p-3.5 text-xs text-navy flex items-start gap-3">
        <Lock className="h-4 w-4 shrink-0 text-navy mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold">Closed & Isolated Personal Vault</p>
          <p className="text-ink-soft mt-0.5 text-[11px]">
            Your purchase amounts, order numbers, and item details are encrypted at rest with AES-128 and strictly isolated to your user account. Duplicate protection uses deterministic HMAC blind indexes without revealing plaintext identifiers.
          </p>
        </div>
      </div>

      {/* Real-Time Cost KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Cost Incurred Today */}
        <div className="rounded-xl border-2 border-emerald-500/30 bg-canvas-raised p-5 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Cost Incurred Today
            </span>
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" /> Live Real-Time
            </span>
          </div>
          <p className="num mt-2 text-3xl font-extrabold text-ink">
            {formatINR(todayCost)}
          </p>
          <p className="mt-1 text-xs text-ink-soft">
            {todayCost > 0 ? 'Marketplace orders placed today' : 'No purchases recorded today yet'}
          </p>
        </div>

        {/* 7-Day Cost */}
        <div className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
            This Week's Cost
          </span>
          <p className="num mt-2 text-2xl font-bold text-ink">
            {formatINR(weekCost)}
          </p>
          <p className="mt-1 text-xs text-ink-faint">Past 7 days spending</p>
        </div>

        {/* 30-Day Cost */}
        <div className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
            This Month's Cost
          </span>
          <p className="num mt-2 text-2xl font-bold text-ink">
            {formatINR(monthCost)}
          </p>
          <p className="mt-1 text-xs text-ink-faint">Past 30 days cumulative</p>
        </div>

        {/* Total Orders */}
        <div className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
            Total Purchases
          </span>
          <p className="num mt-2 text-2xl font-bold text-navy">
            {totalOrders} Orders
          </p>
          <p className="mt-1 text-xs text-ink-faint">Encrypted & catalogued</p>
        </div>
      </div>

      {/* Connected Banking App: Inflow Income Explorer (RBI AA) */}
      <BankingIncomeExplorer />

      {/* Daily Cost Timeline Bar Chart */}
      <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-navy" />
            <h2 className="text-base font-semibold text-ink">Daily Cost Incurred (Last 14 Days)</h2>
          </div>
          <span className="text-xs text-ink-soft">Aggregated by purchase date</span>
        </div>

        {dailyTrend.length === 0 ? (
          <div className="py-8 text-center text-xs text-ink-faint border border-dashed border-rule rounded-lg">
            No daily spending trends recorded yet. Use "+ Record Purchase" to track your first Amazon order.
          </div>
        ) : (
          <div className="space-y-3 pt-2">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 md:grid-cols-7">
              {dailyTrend.map((item) => {
                const heightPct = Math.max(12, Math.round((item.total_cost / maxDailyCost) * 100));
                const isToday =
                  item.date === new Date().toISOString().split('T')[0];

                return (
                  <div
                    key={item.date}
                    className={`flex flex-col items-center justify-end rounded-lg p-3 text-center border transition-all ${
                      isToday
                        ? 'border-emerald-400 bg-emerald-50/50'
                        : 'border-rule bg-canvas'
                    }`}
                  >
                    <div className="w-full flex flex-col items-center justify-end h-24 mb-2">
                      <span className="text-[10px] font-bold text-ink mb-1">
                        {formatINR(item.total_cost)}
                      </span>
                      <div
                        style={{ height: `${heightPct}%` }}
                        className={`w-full max-w-[32px] rounded-t transition-all ${
                          isToday ? 'bg-emerald-600' : 'bg-navy'
                        }`}
                      />
                    </div>
                    <span className="text-[11px] font-semibold text-ink">
                      {item.date.slice(5)}
                    </span>
                    <span className="text-[10px] text-ink-soft">
                      {item.order_count} {item.order_count === 1 ? 'order' : 'orders'}
                    </span>
                    <div className="mt-1 flex flex-wrap justify-center gap-0.5">
                      {item.marketplaces.map((m) => (
                        <span
                          key={m}
                          className="rounded bg-canvas-sunk px-1 py-0.2 text-[9px] font-medium text-ink-soft"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* Summary of Payments Made to Others (ML Payee Intelligence) */}
      {paymentsSummary && (
        <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-navy" />
              <div>
                <h2 className="text-base font-semibold text-ink">
                  Summary of Payments Made to Others (अन्य को किए गए भुगतान का सारांश)
                </h2>
                <p className="text-xs text-ink-soft">
                  Powered by Python <code className="font-mono text-navy">pandas</code> +{' '}
                  <code className="font-mono text-navy">scikit-learn</code> (
                  {paymentsSummary.ml_models_used.regression_model ?? 'RidgeRegression'} &amp; KMeans Payee Clustering)
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-md bg-canvas-sunk px-3 py-1 border border-rule">
                Total Paid to Others:{' '}
                <strong className="num font-bold text-ink">
                  {formatINR(paymentsSummary.total_paid_to_others)}
                </strong>
              </span>
              <span className="rounded-md bg-navy-tint px-3 py-1 border border-navy/20 text-navy">
                ML 7d Projected Outflow:{' '}
                <strong className="num font-bold">{formatINR(paymentsSummary.predicted_7d_outflow)}</strong>
              </span>
            </div>
          </div>

          {/* Executive Narrative Summary */}
          <div className="rounded-lg border border-navy/20 bg-canvas-sunk p-3.5 text-xs text-ink leading-relaxed">
            <strong className="text-navy">AI Executive Summary: </strong>
            {paymentsSummary.ai_summary_text}
          </div>

          {/* Payee-Wise Summary Table */}
          {paymentsSummary.payee_summary.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-rule">
              <table className="min-w-full text-xs">
                <thead className="border-b border-rule bg-canvas-sunk text-left uppercase tracking-wider text-ink-soft">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Recipient / Payee (भुगतान प्राप्तकर्ता)</th>
                    <th className="px-3 py-2.5 font-semibold">Type</th>
                    <th className="px-3 py-2.5 font-semibold">Primary Channel</th>
                    <th className="px-3 py-2.5 font-semibold">ML Cluster Tier (KMeans)</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Payments</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Avg Ticket</th>
                    <th className="px-3 py-2.5 text-right font-semibold">Total Paid &amp; Share</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule bg-canvas">
                  {paymentsSummary.payee_summary.map((payee) => {
                    const isFocusedStore =
                      storeDrilldown?.selected_store.toLowerCase() === payee.payee_name.toLowerCase();
                    return (
                      <tr
                        key={payee.payee_name}
                        onClick={() => {
                          setSelectedStore(payee.payee_name);
                          setHoveredTxIdx(null);
                        }}
                        className={`cursor-pointer transition-colors ${
                          isFocusedStore ? 'bg-navy-tint/60' : 'hover:bg-canvas-raised'
                        }`}
                        title={`Click to view graphical transactions from ${payee.payee_name}`}
                      >
                        <td className="px-3 py-2.5 font-bold text-ink flex items-center gap-1.5">
                          <span>{payee.payee_name}</span>
                          <span className="rounded bg-navy/10 px-1.5 py-0.5 text-[9px] font-semibold text-navy">
                            View Graph ➔
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-ink-soft">{payee.payee_type}</td>
                        <td className="px-3 py-2.5 text-ink-soft">{payee.primary_channel}</td>
                        <td className="px-3 py-2.5">
                          <span className="inline-block rounded-full bg-navy-tint px-2.5 py-0.5 text-[10px] font-semibold text-navy">
                            {payee.ml_cluster_label}
                          </span>
                        </td>
                        <td className="num px-3 py-2.5 text-right font-medium text-ink">
                          {payee.payment_count}
                        </td>
                        <td className="num px-3 py-2.5 text-right text-ink-soft">
                          {formatINR(payee.avg_payment)}
                        </td>
                        <td className="num px-3 py-2.5 text-right font-bold text-ink">
                          {formatINRPrecise(payee.total_paid)}{' '}
                          <span className="text-[10px] font-normal text-ink-soft">
                            ({payee.share_percentage}%)
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Payment App / Channel Split Pills */}
          {paymentsSummary.payment_app_summary.length > 0 && (
            <div className="grid gap-2.5 sm:grid-cols-3 pt-1">
              {paymentsSummary.payment_app_summary.map((ch) => (
                <div
                  key={ch.channel}
                  className="rounded-lg border border-rule bg-canvas px-3.5 py-2.5 flex items-center justify-between text-xs"
                >
                  <div>
                    <p className="font-semibold text-ink">{ch.channel}</p>
                    <p className="text-[10px] text-ink-faint">{ch.transaction_count} payment(s)</p>
                  </div>
                  <div className="text-right">
                    <p className="num font-bold text-navy">{formatINR(ch.total_paid)}</p>
                    <p className="text-[10px] text-ink-soft">{ch.percentage}% of total</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Store-Specific Graphical Transaction Explorer (Store Drill-Down) */}
      {storeDrilldown && storeDrilldown.available_stores.length > 0 && (
        <section className="rounded-xl border-2 border-navy/25 bg-canvas-raised p-5 shadow-sm space-y-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2.5">
              <div className="rounded-lg bg-navy p-2 text-white">
                <ShoppingBag className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-ink">
                  Store-Specific Graphical Transaction Explorer (किसी विशेष स्टोर के लेन-देन का ग्राफ़)
                </h2>
                <p className="text-xs text-ink-soft">
                  Select any store or merchant below to inspect every transaction, cumulative cost curve, UPI routing, and item breakdown graphically.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-bold text-emerald-900">
              <Lock className="h-3.5 w-3.5 text-emerald-700" />
              Viewing Store: {storeDrilldown.selected_store}
            </span>
          </div>

          {/* Interactive Store Selector Bar */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">
              Choose Store / Merchant to Inspect Graphically:
            </span>
            <div className="flex flex-wrap gap-2">
              {storeDrilldown.available_stores.map((st) => {
                const isActive =
                  st.store_name.toLowerCase() === storeDrilldown.selected_store.toLowerCase();
                return (
                  <button
                    key={st.store_name}
                    type="button"
                    onClick={() => {
                      setSelectedStore(st.store_name);
                      setHoveredTxIdx(null);
                    }}
                    className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition-all flex items-center gap-2 border ${
                      isActive
                        ? 'bg-navy text-white border-navy shadow-sm'
                        : 'bg-canvas text-ink hover:bg-canvas-sunk border-rule'
                    }`}
                  >
                    <span>{st.store_name}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] num ${
                        isActive ? 'bg-white/20 text-white' : 'bg-canvas-sunk text-ink-soft'
                      }`}
                    >
                      {formatINR(st.total_spent)} · {st.transaction_count} tx
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Selected Store KPI Strip */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-rule bg-canvas p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                Total Spent at {storeDrilldown.selected_store}
              </p>
              <p className="num mt-1 text-xl font-extrabold text-navy">
                {formatINRPrecise(storeDrilldown.total_spent)}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-soft">
                {storeDrilldown.share_of_wallet_pct}% of your total payments
              </p>
            </div>

            <div className="rounded-lg border border-rule bg-canvas p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                Transactions &amp; Avg Ticket
              </p>
              <p className="num mt-1 text-xl font-extrabold text-ink">
                {storeDrilldown.transaction_count} Orders
              </p>
              <p className="mt-0.5 text-[11px] text-ink-soft">
                Avg Cost: <strong className="num">{formatINR(storeDrilldown.avg_order_value)}</strong> / order
              </p>
            </div>

            <div className="rounded-lg border border-rule bg-canvas p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                Order Cost Range (Min – Max)
              </p>
              <p className="num mt-1 text-xl font-extrabold text-ink">
                {formatINR(storeDrilldown.min_order_value)} – {formatINR(storeDrilldown.max_order_value)}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-soft">
                Store Type: {storeDrilldown.store_type}
              </p>
            </div>

            <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-900">
                ML Predicted Next Spend
              </p>
              <p className="num mt-1 text-xl font-extrabold text-emerald-900">
                {formatINR(storeDrilldown.predicted_next_order)}
              </p>
              <p className="mt-0.5 text-[11px] text-emerald-800">
                pandas EWMA trajectory for {storeDrilldown.selected_store}
              </p>
            </div>
          </div>

          {/* Dual-Layer SVG Chart: Order Cost Bars + Cumulative Spend Curve for Selected Store */}
          {(() => {
            const pts = storeDrilldown.transactions_timeline;
            if (pts.length === 0) return null;
            const maxCum = Math.max(...pts.map((p) => p.cumulative_amount), 1);
            const svgW = 720;
            const svgH = 220;
            const padL = 54;
            const padR = 28;
            const padT = 24;
            const padB = 42;
            const plotW = svgW - padL - padR;
            const plotH = svgH - padT - padB;
            const stepX = pts.length > 1 ? plotW / pts.length : plotW;

            const coords = pts.map((pt, idx) => {
              const cx = padL + stepX * idx + stepX / 2;
              const barH = Math.max(8, (pt.amount / maxCum) * plotH);
              const barY = padT + plotH - barH;
              const cumY = padT + plotH - (pt.cumulative_amount / maxCum) * plotH;
              return { cx, barH, barY, cumY, pt, idx };
            });

            const linePath = coords
              .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.cx.toFixed(1)} ${c.cumY.toFixed(1)}`)
              .join(' ');
            const areaPath =
              coords.length > 0
                ? `${linePath} L ${coords[coords.length - 1].cx.toFixed(1)} ${(padT + plotH).toFixed(1)} L ${coords[0].cx.toFixed(1)} ${(padT + plotH).toFixed(1)} Z`
                : '';

            const activeIdx =
              hoveredTxIdx !== null && hoveredTxIdx < pts.length ? hoveredTxIdx : pts.length - 1;
            const activeTx = pts[activeIdx];

            return (
              <div className="grid gap-4 lg:grid-cols-3 items-stretch">
                {/* Left 2 Columns: SVG Dual-Layer Graph */}
                <div className="lg:col-span-2 rounded-xl border border-rule bg-canvas p-4 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                        {storeDrilldown.selected_store} — Order Cost Bars &amp; Cumulative Spend Curve
                      </h3>
                      <p className="text-[11px] text-ink-soft">
                        Hover or click any bar/node to inspect that specific order from {storeDrilldown.selected_store}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 text-[11px]">
                      <span className="flex items-center gap-1 text-ink">
                        <span className="h-2.5 w-2.5 rounded-xs bg-navy inline-block" /> Individual Order Cost
                      </span>
                      <span className="flex items-center gap-1 text-emerald-700 font-semibold">
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-600 inline-block" /> Running Cumulative Spend
                      </span>
                    </div>
                  </div>

                  <svg
                    viewBox={`0 0 ${svgW} ${svgH}`}
                    className="w-full h-56 overflow-visible select-none"
                    role="img"
                    aria-label={`Transactions graph for ${storeDrilldown.selected_store}`}
                  >
                    <defs>
                      <linearGradient id="storeCumGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#059669" stopOpacity="0.24" />
                        <stop offset="100%" stopColor="#059669" stopOpacity="0.02" />
                      </linearGradient>
                    </defs>

                    {/* Horizontal Reference Grid Lines */}
                    {[0, 0.5, 1].map((frac) => {
                      const y = padT + plotH * (1 - frac);
                      const val = Math.round(maxCum * frac);
                      return (
                        <g key={frac}>
                          <line
                            x1={padL}
                            y1={y}
                            x2={svgW - padR}
                            y2={y}
                            stroke="#E5E0D5"
                            strokeDasharray="3 3"
                          />
                          <text
                            x={padL - 6}
                            y={y + 4}
                            textAnchor="end"
                            className="fill-ink-faint text-[10px] font-mono"
                          >
                            ₹{val.toLocaleString('en-IN')}
                          </text>
                        </g>
                      );
                    })}

                    {/* Shaded Cumulative Area */}
                    {areaPath && <path d={areaPath} fill="url(#storeCumGrad)" />}

                    {/* Individual Order Cost Bars */}
                    {coords.map((c) => {
                      const isSelected = c.idx === activeIdx;
                      const barW = Math.min(44, Math.max(18, stepX * 0.42));
                      return (
                        <g
                          key={c.pt.id}
                          className="cursor-pointer"
                          onMouseEnter={() => setHoveredTxIdx(c.idx)}
                          onClick={() => setHoveredTxIdx(c.idx)}
                        >
                          <rect
                            x={c.cx - barW / 2}
                            y={c.barY}
                            width={barW}
                            height={c.barH}
                            rx={4}
                            fill={isSelected ? '#059669' : '#1E3A8A'}
                            opacity={isSelected ? 0.95 : 0.78}
                          />
                          <text
                            x={c.cx}
                            y={c.barY - 5}
                            textAnchor="middle"
                            className="fill-ink text-[10px] font-bold font-mono"
                          >
                            ₹{c.pt.amount.toLocaleString('en-IN')}
                          </text>
                          <text
                            x={c.cx}
                            y={padT + plotH + 15}
                            textAnchor="middle"
                            className="fill-ink-soft text-[10px] font-semibold"
                          >
                            {c.pt.date.slice(5)}
                          </text>
                          <text
                            x={c.cx}
                            y={padT + plotH + 28}
                            textAnchor="middle"
                            className="fill-ink-faint text-[9px] font-mono"
                          >
                            #{c.pt.order_id.slice(0, 7)}
                          </text>
                        </g>
                      );
                    })}

                    {/* Cumulative Spend Line & Nodes */}
                    {linePath && (
                      <path
                        d={linePath}
                        fill="none"
                        stroke="#059669"
                        strokeWidth={2.5}
                        strokeLinecap="round"
                      />
                    )}
                    {coords.map((c) => {
                      const isSelected = c.idx === activeIdx;
                      return (
                        <circle
                          key={`dot-${c.pt.id}`}
                          cx={c.cx}
                          cy={c.cumY}
                          r={isSelected ? 6 : 4}
                          fill={isSelected ? '#047857' : '#10B981'}
                          stroke="#FFFFFF"
                          strokeWidth={2}
                          className="cursor-pointer"
                          onMouseEnter={() => setHoveredTxIdx(c.idx)}
                          onClick={() => setHoveredTxIdx(c.idx)}
                        />
                      );
                    })}
                  </svg>
                </div>

                {/* Right Column: Interactive Selected Order Inspector Card */}
                {activeTx && (
                  <div className="rounded-xl border border-rule bg-canvas p-4 flex flex-col justify-between space-y-3">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="rounded bg-navy-tint px-2 py-0.5 text-[10px] font-bold text-navy">
                          Order #{activeIdx + 1} of {pts.length} at {storeDrilldown.selected_store}
                        </span>
                        <span className="text-[11px] font-semibold text-ink-soft">
                          {activeTx.date}
                        </span>
                      </div>

                      <div>
                        <p className="text-[10px] uppercase tracking-wider text-ink-faint">
                          Order Cost Incurred
                        </p>
                        <p className="num text-2xl font-extrabold text-ink">
                          {formatINRPrecise(activeTx.amount)}
                        </p>
                      </div>

                      <div className="rounded-lg bg-canvas-sunk p-2.5 border border-rule space-y-1 text-xs">
                        <p className="font-semibold text-ink flex items-center gap-1">
                          <Lock className="h-3 w-3 text-emerald-600 shrink-0" />
                          <span>{activeTx.items_note}</span>
                        </p>
                        <p className="text-[11px] font-mono text-ink-soft">
                          Order ID: {activeTx.order_id}
                        </p>
                      </div>
                    </div>

                    <div className="space-y-1.5 pt-2 border-t border-rule text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-ink-soft">Paid Via:</span>
                        <span className="font-semibold text-ink">{activeTx.payment_method}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-ink-soft">Category:</span>
                        <span className="font-semibold text-ink">{activeTx.category}</span>
                      </div>
                      <div className="flex items-center justify-between pt-1 border-t border-dashed border-rule">
                        <span className="font-semibold text-emerald-800">
                          Cumulative at {storeDrilldown.selected_store}:
                        </span>
                        <span className="num font-extrabold text-emerald-700">
                          {formatINRPrecise(activeTx.cumulative_amount)}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* Store-to-Orders Directed Money Flow Subgraph + Payment & Category Split */}
          <div className="grid gap-4 lg:grid-cols-3">
            {/* Store Flow Graph: Bank -> UPI Method -> Selected Store -> Individual Orders */}
            <div className="lg:col-span-2 rounded-xl border border-rule bg-canvas p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink flex items-center gap-1.5">
                  <Network className="h-4 w-4 text-navy" />
                  <span>
                    Store Money-Flow Graph: Bank A/c ➔ UPI App ➔ {storeDrilldown.selected_store} ➔ Orders
                  </span>
                </h3>
                <span className="text-[10px] text-ink-soft">
                  {storeDrilldown.store_flow_edges.length} verified flow edges
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-3 items-center pt-1">
                {/* Node 1: UPI Gateways used for this store */}
                <div className="space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                    1. UPI App(s) Used
                  </p>
                  {storeDrilldown.store_flow_nodes
                    .filter((n) => n.type === 'GATEWAY')
                    .map((gw) => (
                      <div
                        key={gw.id}
                        className="rounded-lg border border-rule bg-canvas-raised p-2.5 text-xs shadow-2xs"
                      >
                        <div className="flex items-center justify-between font-bold text-ink">
                          <span>{gw.label}</span>
                          <ArrowRight className="h-3.5 w-3.5 text-navy" />
                        </div>
                        <p className="num text-navy font-extrabold mt-0.5">
                          {formatINR(gw.total_volume)}
                        </p>
                        <p className="text-[10px] text-ink-faint">{gw.subtext}</p>
                      </div>
                    ))}
                </div>

                {/* Node 2: Selected Store Hub */}
                <div className="rounded-xl border-2 border-navy bg-navy-tint/40 p-3.5 text-center space-y-1">
                  <span className="rounded-full bg-navy px-2.5 py-0.5 text-[9px] font-bold uppercase text-white">
                    2. Selected Store Hub
                  </span>
                  <h4 className="text-sm font-extrabold text-ink pt-1">
                    {storeDrilldown.selected_store}
                  </h4>
                  <p className="num text-lg font-extrabold text-navy">
                    {formatINRPrecise(storeDrilldown.total_spent)}
                  </p>
                  <p className="text-[10px] text-ink-soft">
                    {storeDrilldown.transaction_count} settled transactions
                  </p>
                </div>

                {/* Node 3: Individual Order Nodes at this Store */}
                <div className="space-y-1.5">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                    3. Store Order Nodes
                  </p>
                  {storeDrilldown.store_flow_nodes
                    .filter((n) => n.type === 'ORDER')
                    .map((ordNode, oIdx) => (
                      <div
                        key={ordNode.id}
                        onClick={() => setHoveredTxIdx(oIdx)}
                        className="cursor-pointer rounded-lg border border-rule bg-canvas-raised px-2.5 py-1.5 text-xs hover:border-emerald-500 transition-colors flex items-center justify-between"
                      >
                        <div className="truncate pr-2">
                          <p className="font-mono text-[11px] font-bold text-ink truncate">
                            {ordNode.label}
                          </p>
                          <p className="text-[10px] text-ink-faint truncate">{ordNode.subtext}</p>
                        </div>
                        <span className="num font-bold text-emerald-700 shrink-0">
                          {formatINR(ordNode.total_volume)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            </div>

            {/* Store Payment & Category Breakdown */}
            <div className="rounded-xl border border-rule bg-canvas p-4 space-y-4">
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                  Payment Apps Used at {storeDrilldown.selected_store}
                </h3>
                {storeDrilldown.payment_method_split.map((m) => (
                  <div key={m.method} className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="font-semibold text-ink">
                        {m.method} <span className="text-ink-faint">({m.count})</span>
                      </span>
                      <span className="num font-bold text-navy">
                        {formatINR(m.amount)} ({m.percentage}%)
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-canvas-sunk overflow-hidden">
                      <div
                        style={{ width: `${Math.min(100, m.percentage)}%` }}
                        className="h-full bg-navy rounded-full"
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="space-y-2 pt-2 border-t border-rule">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                  Categories Bought at {storeDrilldown.selected_store}
                </h3>
                {storeDrilldown.category_split.map((c) => (
                  <div key={c.category} className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="font-semibold text-ink">
                        {c.category} <span className="text-ink-faint">({c.count})</span>
                      </span>
                      <span className="num font-bold text-emerald-700">
                        {formatINR(c.amount)} ({c.percentage}%)
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-canvas-sunk overflow-hidden">
                      <div
                        style={{ width: `${Math.min(100, c.percentage)}%` }}
                        className="h-full bg-emerald-600 rounded-full"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Real-Time Payment Routing Network & Transaction Flow Graph */}
      <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5 text-navy" />
            <div>
              <h2 className="text-base font-semibold text-ink">
                Real-Time Payment Network & Transaction Flow Graph
              </h2>
              <p className="text-xs text-ink-soft">
                Live cryptographic money flow network between Your Bank, UPI Apps (Google Pay, PhonePe), and Merchants.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 rounded-full border border-blue-300 bg-blue-50 px-2.5 py-0.5 text-[11px] font-semibold text-blue-800">
              <Shield className="h-3 w-3 text-blue-600" /> CA-Verified mTLS Ingress
            </span>
          </div>
        </div>

        {/* Visual 3-Stage Network Flow Pipeline */}
        <div className="grid gap-4 md:grid-cols-3 items-stretch pt-2">
          {/* Stage 1: Source (Your Bank) */}
          <div className="rounded-xl border border-rule bg-canvas p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                  Stage 1: Payer Node
                </span>
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              <div className="flex items-center gap-2.5">
                <div className="rounded-lg bg-navy-tint p-2 text-navy">
                  <Building2 className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-ink">Primary Bank A/c</h3>
                  <p className="text-[11px] text-ink-soft">UPI Auto-Debit Source</p>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-rule">
              <p className="text-[10px] text-ink-faint">Total Debited Volume</p>
              <p className="num text-xl font-extrabold text-ink">
                {formatINR(graphData?.total_routed_volume ?? todayCost)}
              </p>
              <p className="text-[10px] text-ink-soft mt-0.5">
                {(graphData?.edges.length ?? 0) > 0 ? `${graphData?.edges.length} active routes` : 'Direct UPI Routing'}
              </p>
            </div>
          </div>

          {/* Stage 2: Gateways & PSP Nodes (Google Pay, PhonePe) */}
          <div className="rounded-xl border border-rule bg-canvas p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                  Stage 2: Payment PSP Gateways
                </span>
                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[9px] font-bold text-blue-800">
                  NPCI UPI
                </span>
              </div>

              {/* Gateway Cards */}
              <div className="space-y-2">
                {graphData?.nodes
                  .filter((n) => n.type === 'GATEWAY')
                  .map((gw) => (
                    <div
                      key={gw.id}
                      className="rounded-lg border border-rule bg-canvas-raised p-2.5 flex items-center justify-between shadow-xs"
                    >
                      <div className="flex items-center gap-2">
                        <Smartphone className="h-4 w-4 text-navy" />
                        <div>
                          <p className="text-xs font-bold text-ink">{gw.label}</p>
                          <p className="text-[10px] text-ink-faint">{gw.order_count} transactions</p>
                        </div>
                      </div>
                      <span className="num text-xs font-bold text-navy">
                        {formatINR(gw.total_volume)}
                      </span>
                    </div>
                  ))}
                {(!graphData || graphData.nodes.filter((n) => n.type === 'GATEWAY').length === 0) && (
                  <div className="rounded-lg border border-rule bg-canvas-raised p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Smartphone className="h-4 w-4 text-navy" />
                      <div>
                        <p className="text-xs font-bold text-ink">Google Pay UPI</p>
                        <p className="text-[10px] text-ink-faint">Primary Payment App</p>
                      </div>
                    </div>
                    <span className="num text-xs font-bold text-navy">{formatINR(todayCost)}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-3 pt-2 text-[10px] text-ink-soft flex items-center gap-1">
              <Shield className="h-3 w-3 text-blue-600" />
              <span>TLS 1.3 + HMAC-SHA256 Payload Signature</span>
            </div>
          </div>

          {/* Stage 3: Destination Merchants (Amazon, Flipkart) */}
          <div className="rounded-xl border border-rule bg-canvas p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider text-ink-soft">
                  Stage 3: Verified Merchants
                </span>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-800">
                  Settled
                </span>
              </div>

              {/* Merchant Cards */}
              <div className="space-y-2">
                {graphData?.nodes
                  .filter((n) => n.type === 'MERCHANT')
                  .map((m) => (
                    <div
                      key={m.id}
                      className="rounded-lg border border-rule bg-canvas-raised p-2.5 flex items-center justify-between shadow-xs"
                    >
                      <div className="flex items-center gap-2">
                        <ShoppingBag className="h-4 w-4 text-emerald-700" />
                        <div>
                          <p className="text-xs font-bold text-ink">{m.label}</p>
                          <p className="text-[10px] text-ink-faint">{m.order_count} orders confirmed</p>
                        </div>
                      </div>
                      <span className="num text-xs font-bold text-emerald-700">
                        {formatINR(m.total_volume)}
                      </span>
                    </div>
                  ))}
                {(!graphData || graphData.nodes.filter((n) => n.type === 'MERCHANT').length === 0) && (
                  <div className="rounded-lg border border-rule bg-canvas-raised p-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ShoppingBag className="h-4 w-4 text-emerald-700" />
                      <div>
                        <p className="text-xs font-bold text-ink">Amazon India</p>
                        <p className="text-[10px] text-ink-faint">Merchant Destination</p>
                      </div>
                    </div>
                    <span className="num text-xs font-bold text-emerald-700">{formatINR(todayCost)}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-3 pt-2 text-[10px] text-ink-soft flex items-center gap-1">
              <Lock className="h-3 w-3 text-emerald-600" />
              <span>AES-128 Blind-Indexed at Rest</span>
            </div>
          </div>
        </div>

        {/* CA Certificate & Security Information Callout */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-3 text-xs text-blue-900 flex items-start gap-2.5">
          <Shield className="h-4 w-4 text-blue-700 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-blue-950">
              Why CA Certificates & mTLS are Mandatory for Real-Time Payment Graphs
            </p>
            <p className="text-[11px] text-blue-800 leading-relaxed">
              When payment providers (Google Pay, PhonePe, Razorpay) deliver live webhooks or bank Account Aggregators sync transaction data, they strictly require:
              <strong> 1) Publicly-trusted X.509 CA certificates</strong> (e.g., Let's Encrypt / DigiCert) — self-signed certs are automatically rejected.
              <strong> 2) Mutual TLS (mTLS)</strong> with client certificates to verify server identity.
              <strong> 3) HMAC-SHA256 signature verification</strong> to prevent spoofed callbacks or data tampering.
            </p>
          </div>
        </div>
      </section>

      {/* Breakdowns: Marketplace Distribution + Categories */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Marketplace Breakdown */}
        <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <ShoppingBag className="h-4 w-4 text-navy" />
            <h2 className="text-base font-semibold text-ink">Marketplace Breakdown</h2>
          </div>

          {marketplaceBreakdown.length === 0 ? (
            <p className="text-xs text-ink-faint">No marketplace purchases recorded yet.</p>
          ) : (
            <div className="space-y-3 pt-1">
              {marketplaceBreakdown.map((m) => (
                <div key={m.marketplace} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-navy" />
                      {m.marketplace}
                      <span className="text-ink-faint font-normal">({m.order_count} orders)</span>
                    </span>
                    <span className="num font-bold text-ink">
                      {formatINR(m.total_cost)}{' '}
                      <span className="text-ink-soft font-normal">({m.percentage}%)</span>
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-canvas-sunk border border-rule">
                    <div
                      style={{ width: `${Math.min(100, m.percentage)}%` }}
                      className="h-full bg-navy transition-all"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Category Breakdown */}
        <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <CreditCard className="h-4 w-4 text-navy" />
            <h2 className="text-base font-semibold text-ink">Expense Categories</h2>
          </div>

          {categoryBreakdown.length === 0 ? (
            <p className="text-xs text-ink-faint">No category breakdown available.</p>
          ) : (
            <div className="space-y-3 pt-1">
              {categoryBreakdown.map((cat) => (
                <div key={cat.category} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-600" />
                      {cat.category}
                    </span>
                    <span className="num font-bold text-ink">
                      {formatINR(cat.total_cost)}{' '}
                      <span className="text-ink-soft font-normal">({cat.percentage}%)</span>
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-canvas-sunk border border-rule">
                    <div
                      style={{ width: `${Math.min(100, cat.percentage)}%` }}
                      className="h-full bg-emerald-600 transition-all"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Encrypted Purchases Ledger Table */}
      <section className="rounded-xl border border-rule bg-canvas-raised p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Receipt className="h-4 w-4 text-navy" />
            <h2 className="text-base font-semibold text-ink">Encrypted Personal Purchases Ledger</h2>
          </div>
          <span className="text-xs text-ink-faint">Decrypted securely in-session</span>
        </div>

        {recentPurchases.length === 0 ? (
          <div className="py-12 text-center rounded-lg border border-dashed border-rule">
            <ShoppingBag className="mx-auto h-8 w-8 text-ink-faint" />
            <p className="mt-2 text-sm font-semibold text-ink">No purchases recorded yet</p>
            <p className="text-xs text-ink-soft mt-1">
              Record your Amazon or online orders to start tracking daily costs.
            </p>
            <button
              type="button"
              onClick={handleOpenModal}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-navy/90"
            >
              <Plus className="h-3.5 w-3.5" /> Record Today's Purchase
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-rule">
            <table className="min-w-full divide-y divide-rule text-sm">
              <thead className="bg-canvas-sunk text-xs font-semibold uppercase tracking-wider text-ink-soft">
                <tr>
                  <th scope="col" className="px-4 py-3 text-left">Date</th>
                  <th scope="col" className="px-4 py-3 text-left">Marketplace</th>
                  <th scope="col" className="px-4 py-3 text-left">Item Details</th>
                  <th scope="col" className="px-4 py-3 text-left">Order ID</th>
                  <th scope="col" className="px-4 py-3 text-left">Payment</th>
                  <th scope="col" className="px-4 py-3 text-right">Cost Incurred</th>
                  <th scope="col" className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule bg-canvas-raised">
                {recentPurchases.map((purchase) => (
                  <tr key={purchase.id} className="hover:bg-canvas transition-colors">
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-soft">
                      {formatDate(purchase.purchased_at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span className="inline-flex items-center gap-1 rounded-md bg-canvas-sunk px-2 py-0.5 text-xs font-bold text-ink border border-rule">
                        {purchase.marketplace}
                      </span>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate text-xs text-ink">
                      <div className="flex items-center gap-1">
                        <span title="Decrypted from AES-128 ciphertext">
                          <Lock className="h-3 w-3 shrink-0 text-emerald-600" />
                        </span>
                        <span className="truncate">{purchase.items_note || 'General Purchase'}</span>
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs font-mono text-ink-soft">
                      {purchase.order_id}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-soft">
                      {purchase.payment_method || 'UPI (Google Pay)'}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right text-xs font-bold text-ink">
                      {formatINRPrecise(purchase.amount)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-center">
                      <button
                        type="button"
                        onClick={() => handleDelete(purchase.id)}
                        className="rounded p-1 text-ink-faint hover:bg-red-50 hover:text-red-600 transition-colors"
                        title="Delete purchase"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Modal: Record Purchase with Auto-Extract & Manual Form */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-rule bg-canvas-raised p-6 shadow-2xl space-y-4">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-rule pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-emerald-600" />
                <h3 className="text-lg font-bold text-ink">Record Marketplace Purchase</h3>
              </div>
              <button
                type="button"
                onClick={handleCloseModal}
                className="rounded-lg p-1.5 text-ink-soft hover:bg-canvas-sunk hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Mode Switch Tabs */}
            <div className="flex rounded-lg border border-rule bg-canvas-sunk p-1 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setActiveTab('form')}
                className={`flex-1 rounded-md py-1.5 text-center transition-all ${
                  activeTab === 'form' ? 'bg-canvas-raised text-navy shadow-sm' : 'text-ink-soft hover:text-ink'
                }`}
              >
                Manual Details Form
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('paste')}
                className={`flex-1 rounded-md py-1.5 text-center transition-all flex items-center justify-center gap-1.5 ${
                  activeTab === 'paste' ? 'bg-canvas-raised text-navy shadow-sm' : 'text-ink-soft hover:text-ink'
                }`}
              >
                <Sparkles className="h-3.5 w-3.5 text-navy" />
                Paste Amazon Receipt / Text
              </button>
            </div>

            {/* Error & Success Messages */}
            {formError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-700">
                {formError}
              </div>
            )}
            {extractSuccessMsg && (
              <div className="flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-800">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>{extractSuccessMsg}</span>
              </div>
            )}

            {/* Tab 2: Paste Receipt Text */}
            {activeTab === 'paste' && (
              <div className="space-y-3">
                <p className="text-xs text-ink-soft">
                  Paste raw text copied from your Amazon / Flipkart confirmation email, web order details, or Google Pay UPI SMS:
                </p>
                <textarea
                  rows={6}
                  value={rawInvoiceText}
                  onChange={(e) => setRawInvoiceText(e.target.value)}
                  placeholder="e.g. Order #404-7123456-7890123&#10;Order Total: ₹1,499.00&#10;Items: boAt Rockerz 450 Bluetooth On Ear Headphones..."
                  className="w-full rounded-lg border border-rule bg-canvas p-3 font-mono text-xs text-ink focus:border-navy focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleAutoExtract}
                  disabled={isExtracting}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy/90 disabled:opacity-50"
                >
                  <Sparkles className="h-4 w-4" />
                  {isExtracting ? 'Extracting In-Memory...' : '⚡ Auto-Extract Details & Review'}
                </button>
                <p className="text-[11px] text-ink-faint text-center">
                  🔒 Zero-persistence: Parsed strictly in memory; no raw text saved to disk.
                </p>
              </div>
            )}

            {/* Tab 1: Form Inputs */}
            {activeTab === 'form' && (
              <form onSubmit={handleSubmitPurchase} className="space-y-3 text-xs">
                {/* Marketplace chips */}
                <div>
                  <label className="font-semibold text-ink block mb-1">Marketplace</label>
                  <div className="flex flex-wrap gap-1.5">
                    {MARKETPLACES.map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMarketplace(m)}
                        className={`rounded-md px-2.5 py-1 font-medium transition-all ${
                          marketplace === m
                            ? 'bg-navy text-white'
                            : 'bg-canvas-sunk text-ink-soft hover:bg-canvas border border-rule'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Amount & Date */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-semibold text-ink block mb-1">Cost Incurred (₹)</label>
                    <div className="relative">
                      <span className="absolute left-3 top-2 text-ink-soft font-bold">₹</span>
                      <input
                        type="number"
                        step="0.01"
                        required
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        placeholder="1499.00"
                        className="w-full rounded-lg border border-rule bg-canvas pl-7 pr-3 py-1.5 font-bold text-ink focus:border-navy focus:outline-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="font-semibold text-ink block mb-1">Purchase Date</label>
                    <input
                      type="date"
                      required
                      value={purchasedDate}
                      onChange={(e) => setPurchasedDate(e.target.value)}
                      className="w-full rounded-lg border border-rule bg-canvas px-3 py-1.5 text-ink focus:border-navy focus:outline-none"
                    />
                  </div>
                </div>

                {/* Order ID */}
                <div>
                  <label className="font-semibold text-ink block mb-1 flex items-center justify-between">
                    <span>Marketplace Order ID</span>
                    <span className="text-[10px] text-emerald-700 font-normal flex items-center gap-1">
                      <Lock className="h-3 w-3" /> AES-128 Encrypted at Rest
                    </span>
                  </label>
                  <input
                    type="text"
                    required
                    value={orderId}
                    onChange={(e) => setOrderId(e.target.value)}
                    placeholder="e.g. 404-7123456-7890123"
                    className="w-full rounded-lg border border-rule bg-canvas px-3 py-1.5 font-mono text-ink focus:border-navy focus:outline-none"
                  />
                </div>

                {/* Category & Payment Method */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-semibold text-ink block mb-1">Category</label>
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                      className="w-full rounded-lg border border-rule bg-canvas px-2.5 py-1.5 text-ink focus:border-navy focus:outline-none"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="font-semibold text-ink block mb-1">Payment Method</label>
                    <select
                      value={paymentMethod}
                      onChange={(e) => setPaymentMethod(e.target.value)}
                      className="w-full rounded-lg border border-rule bg-canvas px-2.5 py-1.5 text-ink focus:border-navy focus:outline-none"
                    >
                      {PAYMENT_METHODS.map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Items Description */}
                <div>
                  <label className="font-semibold text-ink block mb-1 flex items-center justify-between">
                    <span>Items Note / Purchased Goods</span>
                    <span className="text-[10px] text-emerald-700 font-normal flex items-center gap-1">
                      <Lock className="h-3 w-3" /> Encrypted
                    </span>
                  </label>
                  <input
                    type="text"
                    value={itemsNote}
                    onChange={(e) => setItemsNote(e.target.value)}
                    placeholder="e.g. boAt Rockerz 450 Bluetooth On Ear Headphones (Luscious Black)"
                    className="w-full rounded-lg border border-rule bg-canvas px-3 py-1.5 text-ink focus:border-navy focus:outline-none"
                  />
                </div>

                {/* Live Pre-Transaction Cost & Store Impact Preview */}
                {Number(amount) > 0 && (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between font-bold text-emerald-950">
                      <span className="flex items-center gap-1">
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-700" />
                        Live Transaction Cost &amp; Safety Preview ({marketplace})
                      </span>
                      <span className="num">{formatINRPrecise(Number(amount))}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-emerald-900">
                      <div>
                        Today&apos;s Spend Impact:{' '}
                        <strong className="num">
                          {formatINR(todayCost)} ➔ {formatINR(todayCost + Number(amount))}
                        </strong>
                      </div>
                      <div>
                        UPI MDR / Gateway Fee: <strong className="num">₹0.00 (Zero-Fee NPCI)</strong>
                      </div>
                    </div>
                  </div>
                )}

                {/* Submit Buttons */}
                <div className="flex items-center justify-end gap-2 pt-3 border-t border-rule">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="rounded-lg border border-rule px-4 py-2 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={createPurchaseMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy/90 disabled:opacity-50"
                  >
                    <Lock className="h-3.5 w-3.5" />
                    <span>
                      {createPurchaseMutation.isPending ? 'Encrypting & Saving...' : 'Save & Encrypt Purchase'}
                    </span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
