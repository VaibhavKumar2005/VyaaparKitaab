import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { CreditCard, Receipt, CheckCircle2 } from 'lucide-react';
import { useInvoices } from '../hooks/useInvoices';
import { StatusPill, paymentState } from '../components/StatusPill';
import { formatINR, formatINRPrecise, formatDate } from '../lib/format';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';

export function CustomerBillsPage() {
  const { data: allInvoices, isPending, isError, refetch } = useInvoices();

  // Filter ONLY sale invoices for this customer (e.g. cust-001 or retail)
  // NEVER show purchase invoices or other customer records!
  const customerBills = useMemo(() => {
    return (allInvoices ?? [])
      .filter((i) => i.type === 'SALE' && (i.customer_id === 'cust-001' || i.customer_id === 'cust-003' || !i.customer_id))
      .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  }, [allInvoices]);

  const summary = useMemo(() => {
    const totalBilled = customerBills.reduce((sum, b) => sum + b.total_amount, 0);
    const totalPaid = customerBills.reduce((sum, b) => sum + b.paid_amount, 0);
    const balanceDue = Math.max(totalBilled - totalPaid, 0);
    return { totalBilled, totalPaid, balanceDue };
  }, [customerBills]);

  if (isPending) return <LoadingState label="Loading your store bills and receipts…" />;
  if (isError) return <ErrorState label="Couldn't load your bills." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold">My Bills & Receipts (मेरे बिल)</h1>
        <p className="mt-0.5 text-sm text-ink-soft">
          Personal invoice records from Sharma Kirana Store, payment receipts, and instant UPI clearing.
        </p>
      </div>

      {/* Financial Summary */}
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Customer Bill Summary">
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Billed</p>
          <p className="num mt-2 text-2xl font-bold text-ink">{formatINR(summary.totalBilled)}</p>
          <p className="mt-1 text-xs text-ink-faint">Across all your recorded bills</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Paid (जमा)</p>
          <p className="num mt-2 text-2xl font-bold text-positive">{formatINR(summary.totalPaid)}</p>
          <p className="mt-1 text-xs text-ink-faint">Settled via UPI / Cash</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Outstanding Balance (देय बाकी)</p>
          <p className="num mt-2 text-2xl font-bold text-due">{formatINR(summary.balanceDue)}</p>
          <p className="mt-1 text-xs text-ink-faint">Due for settlement</p>
        </div>
      </section>

      {/* Bills Table */}
      <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
        <table className="min-w-full text-sm">
          <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
            <tr>
              <th scope="col" className="px-4 py-3 font-semibold">Bill Date</th>
              <th scope="col" className="px-4 py-3 font-semibold">Bill #</th>
              <th scope="col" className="px-4 py-3 font-semibold">Status</th>
              <th scope="col" className="px-4 py-3 text-right font-semibold">Total Amount</th>
              <th scope="col" className="px-4 py-3 text-right font-semibold">Balance Due</th>
              <th scope="col" className="px-4 py-3 text-right font-semibold">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {customerBills.map((bill) => {
              const due = Math.max(bill.total_amount - bill.paid_amount, 0);
              return (
                <tr key={bill.id} className="hover:bg-canvas">
                  <td className="whitespace-nowrap px-4 py-3 text-ink-soft">{formatDate(bill.created_at)}</td>
                  <td className="px-4 py-3 font-medium">
                    <Link to={`/app/invoices/${bill.id}`} className="text-navy hover:underline">
                      {bill.invoice_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill state={paymentState(bill)} />
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-right font-semibold text-ink">
                    {formatINRPrecise(bill.total_amount)}
                  </td>
                  <td className={`num whitespace-nowrap px-4 py-3 text-right font-semibold ${due > 0 ? 'text-due' : 'text-positive'}`}>
                    {due > 0 ? formatINRPrecise(due) : 'Settled'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {due > 0 ? (
                      <Link
                        to={`/app/invoices/${bill.id}`}
                        className="inline-flex items-center gap-1 rounded bg-navy px-2.5 py-1 text-xs font-semibold text-white hover:bg-navy-dark"
                      >
                        <CreditCard className="h-3.5 w-3.5" /> Pay UPI
                      </Link>
                    ) : (
                      <Link
                        to={`/app/invoices/${bill.id}`}
                        className="inline-flex items-center gap-1 rounded border border-rule px-2.5 py-1 text-xs font-medium text-ink-soft hover:bg-canvas-sunk"
                      >
                        <Receipt className="h-3.5 w-3.5" /> View Receipt
                      </Link>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

