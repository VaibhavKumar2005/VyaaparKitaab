import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { CreditCard, QrCode, CheckCircle2, AlertCircle } from 'lucide-react';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useInvoice, useCreatePaymentOrder, useVerifyPayment, PaymentOrderData } from '../hooks/useInvoices';

export function InvoiceDetail() {
  const { id } = useParams();
  const { data, isPending, isError, refetch } = useInvoice(id);
  const createOrder = useCreatePaymentOrder();
  const verifyPayment = useVerifyPayment();

  const [activeOrder, setActiveOrder] = useState<PaymentOrderData | null>(null);
  const [paymentMsg, setPaymentMsg] = useState<string | null>(null);

  if (isPending) return <LoadingState label="Loading invoice..." />;
  if (isError || !data) return <ErrorState label="Unable to load this invoice." onRetry={() => void refetch()} />;

  const isPaid = data.status === 'PAID';

  const handleInitiatePayment = async () => {
    try {
      setPaymentMsg(null);
      const order = await createOrder.mutateAsync({ invoice_id: data.id });
      setActiveOrder(order);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to initiate payment';
      setPaymentMsg(message);
    }
  };

  const handleSimulatePaymentCompletion = async () => {
    if (!activeOrder) return;
    try {
      const res = await verifyPayment.mutateAsync({
        invoice_id: data.id,
        order_id: activeOrder.order_id,
        payment_id: `pay_${Date.now()}`,
        signature: 'sandbox_valid',
      });
      setPaymentMsg(res.message || 'Payment confirmed successfully!');
      setActiveOrder(null);
      refetch();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Payment verification failed';
      setPaymentMsg(message);
    }
  };

  return (
    <section className="space-y-6 rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">Invoice</p>
          <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">{data.invoice_number}</h1>
          <p className="mt-2 text-sm text-slate-300">
            Created on {new Date(data.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider ${
              isPaid
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
            }`}
          >
            {data.status}
          </span>
          {data.payment_method && (
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
              Method: {data.payment_method}
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-slate-400">Subtotal</p>
          <p className="text-lg font-semibold text-white">₹{data.subtotal.toFixed(2)}</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-slate-400">Tax</p>
          <p className="text-lg font-semibold text-white">₹{data.tax_amount.toFixed(2)}</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-slate-400">Total Amount</p>
          <p className="text-xl font-bold text-emerald-400">₹{data.total_amount.toFixed(2)}</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs text-slate-400">Paid Amount</p>
          <p className="text-xl font-bold text-white">₹{data.paid_amount.toFixed(2)}</p>
        </div>
      </div>

      {/* Payment Action Bar */}
      {!isPaid && (
        <div className="rounded-2xl border border-sky-500/20 bg-sky-500/10 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-semibold text-white flex items-center gap-2">
                <CreditCard className="h-5 w-5 text-sky-400" />
                Collect Payment Online
              </h3>
              <p className="text-xs text-slate-300 mt-1">
                Generate an instant UPI QR code or payment gateway order for this invoice.
              </p>
            </div>
            {!activeOrder ? (
              <button
                type="button"
                onClick={handleInitiatePayment}
                disabled={createOrder.isPending}
                className="flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-sky-400 transition-colors disabled:opacity-50"
              >
                <QrCode className="h-4 w-4" />
                {createOrder.isPending ? 'Generating Order...' : 'Pay via UPI / Card'}
              </button>
            ) : null}
          </div>

          {activeOrder && (
            <div className="mt-4 rounded-xl border border-white/10 bg-slate-900/80 p-4 space-y-3">
              <div className="flex items-center justify-between text-xs text-slate-300">
                <span>Order ID: <code className="text-sky-300">{activeOrder.order_id}</code></span>
                <span>Gateway: <strong className="uppercase">{activeOrder.gateway}</strong></span>
              </div>
              {activeOrder.upi_intent && (
                <div className="rounded-lg bg-black/40 p-3 text-xs text-slate-300 break-all font-mono">
                  UPI Intent URI: {activeOrder.upi_intent}
                </div>
              )}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setActiveOrder(null)}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSimulatePaymentCompletion}
                  disabled={verifyPayment.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {verifyPayment.isPending ? 'Verifying...' : 'Confirm Payment Received'}
                </button>
              </div>
            </div>
          )}

          {paymentMsg && (
            <div className="mt-3 flex items-center gap-2 text-xs text-sky-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{paymentMsg}</span>
            </div>
          )}
        </div>
      )}

      {/* Invoice Items Table */}
      <div className="overflow-x-auto rounded-2xl border border-white/10">
        <table className="min-w-full divide-y divide-white/10 text-left text-sm">
          <thead className="bg-white/5 text-slate-300">
            <tr>
              <th className="px-4 py-3">Product ID</th>
              <th className="px-4 py-3">Quantity</th>
              <th className="px-4 py-3">Unit Price</th>
              <th className="px-4 py-3">Discount</th>
              <th className="px-4 py-3">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10 text-slate-200">
            {data.items.map((item) => (
              <tr key={item.id}>
                <td className="px-4 py-3 font-mono text-xs text-slate-300">{item.product_id}</td>
                <td className="px-4 py-3">{item.quantity}</td>
                <td className="px-4 py-3">₹{item.unit_price.toFixed(2)}</td>
                <td className="px-4 py-3">₹{item.discount.toFixed(2)}</td>
                <td className="px-4 py-3 font-semibold text-white">₹{item.line_total.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}