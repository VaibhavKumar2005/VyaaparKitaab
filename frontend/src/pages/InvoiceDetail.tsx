import { useState } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import { ArrowLeft, Printer, QrCode, CheckCircle2, AlertCircle, CreditCard, Copy, Check, Banknote } from 'lucide-react';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { StatusPill, paymentState } from '../components/StatusPill';
import { useInvoice, useCreatePaymentOrder, useVerifyPayment, useUpdateInvoiceStatus, PaymentOrderData } from '../hooks/useInvoices';
import { useCustomers, useProducts } from '../hooks/useBusinessData';
import { formatDate, formatINRPrecise } from '../lib/format';

export function InvoiceDetail() {
  const { id } = useParams();
  const inPortal = useLocation().pathname.startsWith('/portal');
  const { data, isPending, isError, refetch } = useInvoice(id);
  const { data: customers } = useCustomers();
  const { data: products } = useProducts();
  const createOrder = useCreatePaymentOrder();
  const verifyPayment = useVerifyPayment();
  const updateStatus = useUpdateInvoiceStatus();

  const [activeOrder, setActiveOrder] = useState<PaymentOrderData | null>(null);
  const [paymentMsg, setPaymentMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showCashModal, setShowCashModal] = useState(false);
  const [cashTendered, setCashTendered] = useState<string>('');

  if (isPending) return <LoadingState label="Loading tax invoice details…" />;
  if (isError || !data) return <ErrorState label="Invoice not found or couldn't be loaded." onRetry={() => void refetch()} />;

  const isSale = data.type === 'SALE';
  const customer = customers?.find((c) => c.id === data.customer_id);
  const dueAmount = Math.max(data.total_amount - data.paid_amount, 0);
  const isFullyPaid = dueAmount <= 0;

  const cashGivenNum = parseFloat(cashTendered) || 0;
  const changeToReturn = Math.max(cashGivenNum - dueAmount, 0);

  const handleInitiatePayment = async () => {
    try {
      setPaymentMsg(null);
      setShowCashModal(false);
      const order = await createOrder.mutateAsync({ invoice_id: data.id, amount: dueAmount });
      setActiveOrder(order);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unable to initiate payment';
      setPaymentMsg(message);
    }
  };

  const handleSimulatePaymentCompletion = async () => {
    if (!activeOrder) return;
    try {
      const res = await verifyPayment.mutateAsync({
        invoice_id: data.id,
        order_id: activeOrder.order_id,
        payment_id: `pay_upi_${Date.now()}`,
        signature: 'sandbox_valid_sig',
        method: 'UPI',
        amount: dueAmount,
      });
      setPaymentMsg(res.message || 'Payment received and recorded successfully!');
      setActiveOrder(null);
      void refetch();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Payment verification failed';
      setPaymentMsg(message);
    }
  };

  const handleCashSettlement = async () => {
    try {
      setPaymentMsg(null);
      await updateStatus.mutateAsync({ id: data.id, status: 'PAID' });
      setPaymentMsg(
        changeToReturn > 0
          ? `₹ नकद भुगतान दर्ज (Cash received ${formatINRPrecise(cashGivenNum)}, return change ${formatINRPrecise(changeToReturn)})`
          : '₹ नकद भुगतान सफलतापूर्वक दर्ज किया गया (Cash payment recorded!)',
      );
      setShowCashModal(false);
      void refetch();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to record cash payment';
      setPaymentMsg(message);
    }
  };

  const handleCopyUPI = () => {
    if (activeOrder?.upi_intent) {
      void navigator.clipboard.writeText(activeOrder.upi_intent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top back navigation and actions */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <Link to={inPortal ? '/portal/bills' : '/app/invoices'} className="inline-flex items-center gap-1.5 text-sm font-medium text-navy hover:underline">
          <ArrowLeft className="h-4 w-4" /> {inPortal ? 'Back to My Bills' : 'Back to Invoices'}
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => window.print()}
            className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-canvas-raised px-3.5 py-1.5 text-xs font-semibold text-ink hover:bg-canvas-sunk"
          >
            <Printer className="h-3.5 w-3.5 text-ink-soft" /> Print Bill (A4)
          </button>
        </div>
      </div>

      {/* Main Invoice Card (Paper ledger appearance) */}
      <div className="rounded-lg border border-rule bg-canvas-raised p-6 sm:p-8 space-y-6">
        {/* Invoice Header */}
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-rule pb-6">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              GST Tax Invoice (कर बीजक)
            </span>
            <h1 className="num text-2xl sm:text-3xl font-bold text-ink mt-1">
              {data.invoice_number}
            </h1>
            <p className="mt-1 text-xs text-ink-soft">
              Date: <span className="font-semibold text-ink">{formatDate(data.created_at)}</span>
            </p>
          </div>
          <div className="text-right">
            <StatusPill state={paymentState(data)} />
            <p className="mt-2 text-xs font-medium text-ink-soft">
              Type: <strong className="text-ink">{isSale ? 'Credit (Sale Bill)' : 'Debit (Purchase Bill)'}</strong>
            </p>
          </div>
        </div>

        {/* Business & Customer Details (Bahi-Khata ledger heads) */}
        <div className="grid gap-6 sm:grid-cols-2 text-sm">
          <div className="rounded-md border border-rule bg-canvas-sunk p-4 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Billed By (विक्रेता)</p>
            <p className="font-bold text-ink">Sharma Kirana & General Store</p>
            <p className="text-xs text-ink-soft">GSTIN: <span className="font-mono text-ink">09AAACS1429B1Z8</span></p>
            <p className="text-xs text-ink-soft">Plot 42, Civil Lines, Kanpur Road, Lucknow, UP</p>
            <p className="text-xs text-ink-soft">Phone: +91 98765 43210</p>
          </div>

          <div className="rounded-md border border-rule bg-canvas-sunk p-4 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Billed To (क्रेता / ग्राहक)</p>
            <p className="font-bold text-ink">{customer?.name ?? (isSale ? 'Walk-in Retail Customer' : 'Registered Supplier')}</p>
            {customer?.phone && <p className="text-xs text-ink-soft">Phone: <span className="num font-semibold text-ink">{customer.phone}</span></p>}
            {customer?.email && <p className="text-xs text-ink-soft">Email: {customer.email}</p>}
            <p className="text-xs text-ink-soft">Payment Method: <span className="font-semibold text-ink">{data.payment_method ?? 'Not specified'}</span></p>
          </div>
        </div>

        {/* Line Items Table */}
        <div className="overflow-x-auto rounded-md border border-rule">
          <table className="min-w-full text-sm">
            <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Item Description</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Qty</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Rate</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Discount</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Line Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {data.items.map((item) => {
                const prod = products?.find((p) => p.id === item.product_id);
                return (
                  <tr key={item.id} className="hover:bg-canvas">
                    <td className="px-4 py-3">
                      <p className="font-medium text-ink">{prod?.name ?? item.product_id}</p>
                      {prod?.sku && <p className="text-xs text-ink-faint">SKU: {prod.sku}</p>}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right text-ink">
                      {item.quantity} {prod?.unit ?? 'Pcs'}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right text-ink-soft">
                      {formatINRPrecise(item.unit_price)}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right text-ink-soft">
                      {item.discount > 0 ? `− ${formatINRPrecise(item.discount)}` : '—'}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right font-semibold text-ink">
                      {formatINRPrecise(item.line_total)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Financial Calculation Breakdown */}
        <div className="flex flex-col sm:flex-row justify-between items-start gap-6 border-t border-rule pt-4">
          <div className="text-xs text-ink-soft max-w-sm space-y-1">
            <p className="font-semibold text-ink">Terms & Conditions:</p>
            <p>1. Goods once sold will not be taken back without original bill receipt.</p>
            <p>2. Payment due immediately on delivery unless credit terms agreed in bahi-khata.</p>
            <p>3. This is a computer-generated tax invoice verified under GST MSME provisions.</p>
          </div>

          <div className="w-full sm:w-72 space-y-2 text-sm">
            <div className="flex justify-between text-ink-soft">
              <span>Subtotal (मूल रकम):</span>
              <span className="num font-medium text-ink">{formatINRPrecise(data.subtotal)}</span>
            </div>
            <div className="flex justify-between text-ink-soft">
              <span>GST Tax (कर):</span>
              <span className="num font-medium text-ink">{formatINRPrecise(data.tax_amount)}</span>
            </div>
            <div className="flex justify-between border-t border-rule pt-2 text-base font-bold text-ink">
              <span>Total Invoice Amount:</span>
              <span className="num text-navy">{formatINRPrecise(data.total_amount)}</span>
            </div>
            <div className="flex justify-between text-ink-soft text-xs">
              <span>Paid Amount (जमा):</span>
              <span className="num font-semibold text-positive">
                + {formatINRPrecise(data.paid_amount)}
              </span>
            </div>
            <div className="flex justify-between border-t border-rule pt-2 font-bold text-sm">
              <span className={dueAmount > 0 ? 'text-due' : 'text-positive'}>
                {dueAmount > 0 ? 'Balance Due (बाकी उधारी):' : 'Settled Balance:'}
              </span>
              <span className={`num ${dueAmount > 0 ? 'text-due' : 'text-positive'}`}>
                {formatINRPrecise(dueAmount)}
              </span>
            </div>
          </div>
        </div>

        {/* Interactive UPI & Cash Collection Box (Only for unfulfilled/due amounts) */}
        {!isFullyPaid && (
          <div className="no-print mt-6 rounded-lg border border-navy/20 bg-navy-tint p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 className="font-bold text-navy flex items-center gap-2 text-sm">
                  <QrCode className="h-4 w-4" /> Collect Payment (भुगतान स्वीकार करें)
                </h3>
                <p className="text-xs text-ink-soft mt-0.5">
                  Collect the outstanding balance of{' '}
                  <strong className="text-navy">{formatINRPrecise(dueAmount)}</strong> via UPI QR or Cash Counter.
                </p>
              </div>

              {!activeOrder && !showCashModal && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setCashTendered(String(Math.ceil(dueAmount)));
                      setShowCashModal(true);
                    }}
                    className="inline-flex items-center justify-center gap-1.5 rounded-md border border-rule bg-canvas-raised px-3.5 py-2 text-xs font-semibold text-ink hover:bg-canvas-sunk"
                  >
                    <Banknote className="h-4 w-4 text-positive" />
                    Record Cash (नकद)
                  </button>
                  <button
                    type="button"
                    onClick={handleInitiatePayment}
                    disabled={createOrder.isPending}
                    className="inline-flex items-center justify-center gap-1.5 rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
                  >
                    <CreditCard className="h-4 w-4" />
                    {createOrder.isPending ? 'Generating QR…' : 'Generate UPI QR'}
                  </button>
                </div>
              )}
            </div>

            {showCashModal && (
              <div className="mt-3 rounded-md border border-rule bg-canvas-raised p-4 space-y-4">
                <div className="flex items-center justify-between border-b border-rule pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-ink">
                    Cash Counter Calculator (नकद हिसाब)
                  </span>
                  <span className="num text-xs font-semibold text-due">
                    Bill Due: {formatINRPrecise(dueAmount)}
                  </span>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 items-center">
                  <div>
                    <label className="block text-xs font-medium text-ink-soft">
                      Cash Received from Customer (प्राप्त नकद ₹)
                    </label>
                    <input
                      type="number"
                      min={dueAmount}
                      step="1"
                      value={cashTendered}
                      onChange={(e) => setCashTendered(e.target.value)}
                      className="num mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm font-semibold text-ink outline-none focus:border-navy"
                    />
                  </div>
                  <div className="rounded-md bg-canvas-sunk p-3 border border-rule">
                    <span className="block text-xs text-ink-soft">Change to Return (वापस करने योग्य छुट्टे)</span>
                    <span className="num mt-1 block text-lg font-bold text-positive">
                      {formatINRPrecise(changeToReturn)}
                    </span>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowCashModal(false)}
                    className="rounded-md border border-rule px-3 py-1.5 text-xs text-ink-soft hover:bg-canvas-sunk"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleCashSettlement}
                    disabled={updateStatus.isPending || cashGivenNum < dueAmount}
                    className="inline-flex items-center gap-1.5 rounded-md bg-positive px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-positive/90 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    {updateStatus.isPending ? 'Recording…' : 'Confirm Cash Settled'}
                  </button>
                </div>
              </div>
            )}

            {activeOrder && (
              <div className="mt-3 rounded-md border border-rule bg-canvas-raised p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div>
                    <span className="text-ink-soft">Order ID: </span>
                    <strong className="font-mono text-ink">{activeOrder.order_id}</strong>
                  </div>
                  <span className="rounded bg-positive-tint px-2 py-0.5 font-semibold text-positive">
                    UPI Active · {formatINRPrecise(activeOrder.amount)}
                  </span>
                </div>

                {activeOrder.upi_intent && (
                  <div className="flex items-center justify-between gap-2 rounded bg-canvas-sunk p-2.5 text-xs font-mono text-ink-soft break-all border border-rule">
                    <span className="truncate">{activeOrder.upi_intent}</span>
                    <button
                      type="button"
                      onClick={handleCopyUPI}
                      className="shrink-0 p-1 text-navy hover:text-navy-dark"
                      title="Copy UPI String"
                    >
                      {copied ? <Check className="h-4 w-4 text-positive" /> : <Copy className="h-4 w-4" />}
                    </button>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-end gap-2.5 pt-1">
                  <button
                    type="button"
                    onClick={() => setActiveOrder(null)}
                    className="rounded-md border border-rule px-3 py-1.5 text-xs text-ink-soft hover:bg-canvas-sunk"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSimulatePaymentCompletion}
                    disabled={verifyPayment.isPending}
                    className="inline-flex items-center gap-1.5 rounded-md bg-positive px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-positive/90 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    {verifyPayment.isPending ? 'Verifying payment…' : 'Simulate Instant Payment'}
                  </button>
                </div>
              </div>
            )}

            {paymentMsg && (
              <div className="flex items-center gap-2 text-xs font-semibold text-positive pt-1">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{paymentMsg}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}