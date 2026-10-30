import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CreditCard, Receipt, Upload, Trash2, Wallet, ArrowUpRight, ArrowDownLeft } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useMyBills } from '../hooks/useInvoices';
import {
  usePersonalSpending,
  useImportStatement,
  useClearImportedTransactions,
} from '../hooks/useBankingIncome';
import { StatusPill, paymentState } from '../components/StatusPill';
import { formatINR, formatINRPrecise, formatDate } from '../lib/format';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';

export function CustomerBillsPage() {
  // The server returns only SALE bills linked to this customer's phone/e-mail.
  const { data: allInvoices, isPending, isError, refetch } = useMyBills();
  const spendingQuery = usePersonalSpending();
  const importStatementMutation = useImportStatement();
  const clearTransactionsMutation = useClearImportedTransactions();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const handleUploadStatement = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    importStatementMutation.mutate(file, {
      onSuccess: (res) => {
        setImportMsg(
          `Imported ${res.imported_count} real statement rows (${res.debits_count} personal debits, ${res.credits_count} credits) from ${res.filename} into PostgreSQL.`
        );
      },
      onError: (err) => {
        setImportMsg(err instanceof Error ? err.message : 'Could not import statement');
      },
    });
    e.target.value = '';
  };

  const customerBills = useMemo(() => {
    return [...(allInvoices ?? [])]
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
                    <Link to={`/portal/bills/${bill.id}`} className="text-navy hover:underline">
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
                        to={`/portal/bills/${bill.id}`}
                        className="inline-flex items-center gap-1 rounded bg-navy px-2.5 py-1 text-xs font-semibold text-white hover:bg-navy-dark"
                      >
                        <CreditCard className="h-3.5 w-3.5" /> Pay UPI
                      </Link>
                    ) : (
                      <Link
                        to={`/portal/bills/${bill.id}`}
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

      {/* Personal Spending & UPI Statement Importer (Real Outside CSV / JSON Data) */}
      <section className="rounded-xl border border-rule bg-canvas-raised p-5 space-y-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-rule pb-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-navy p-2.5 text-white">
              <Wallet className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-ink">
                Personal Spending &amp; Bank / UPI Statement Analytics (मेरा व्यक्तिगत खर्च)
              </h2>
              <p className="text-xs text-ink-soft mt-0.5">
                Upload your real Google Pay, PhonePe, Paytm, or Bank (SBI / HDFC / ICICI / Axis) CSV or JSON statement to analyze your real personal spending in PostgreSQL.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.json"
              onChange={handleUploadStatement}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={importStatementMutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-navy-dark"
            >
              <Upload className="h-3.5 w-3.5" />
              {importStatementMutation.isPending ? 'Importing…' : 'Upload Real Statement (CSV / JSON)'}
            </button>
            {spendingQuery.data?.has_imported_data && (
              <button
                type="button"
                onClick={() => clearTransactionsMutation.mutate()}
                disabled={clearTransactionsMutation.isPending}
                className="inline-flex items-center gap-1 rounded-md border border-rule px-2.5 py-2 text-xs font-semibold text-due hover:bg-due-tint"
                title="Clear imported statement rows"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear
              </button>
            )}
          </div>
        </div>

        {importMsg && (
          <div className="rounded-md border border-navy/20 bg-navy-tint px-3.5 py-2.5 text-xs font-semibold text-navy">
            {importMsg}
          </div>
        )}

        {!spendingQuery.data?.has_imported_data ? (
          <div className="rounded-lg border border-dashed border-rule bg-canvas-sunk p-8 text-center space-y-2">
            <p className="text-sm font-semibold text-ink">
              No external bank or UPI statement uploaded yet
            </p>
            <p className="text-xs text-ink-soft max-w-lg mx-auto">
              Click <strong>Upload Real Statement (CSV / JSON)</strong> above and select your exported Google Pay, PhonePe, Paytm, or bank statement CSV (or test with <code className="font-mono text-navy">data/real_gpay_and_bank_statement.csv</code>).
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Spending KPI Cards */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-rule bg-canvas p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  Total Personal Spending (DEBIT)
                </p>
                <p className="num mt-1 text-2xl font-bold text-due">
                  -{formatINRPrecise(spendingQuery.data.total_spent)}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  Across {spendingQuery.data.debits_count} outgoing UPI / bank debits
                </p>
              </div>
              <div className="rounded-lg border border-rule bg-canvas p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  Total Inward Credits (CREDIT)
                </p>
                <p className="num mt-1 text-2xl font-bold text-positive">
                  +{formatINRPrecise(spendingQuery.data.total_received)}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  Across {spendingQuery.data.credits_count} incoming deposits
                </p>
              </div>
              <div className="rounded-lg border border-rule bg-canvas p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
                  UPI App Channels Used
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {spendingQuery.data.app_breakdown.map((a) => (
                    <span
                      key={a.app}
                      className="rounded border border-rule bg-canvas-raised px-2 py-0.5 text-xs font-semibold text-ink"
                    >
                      {a.app}: {formatINR(a.amount)} ({a.percentage}%)
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Category Breakdown Chart + Bars */}
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-lg border border-rule bg-canvas p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                  Personal Spending by Category
                </h3>
                <div className="h-52 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={spendingQuery.data.category_breakdown}
                      margin={{ top: 8, right: 8, left: -16, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#d9e0e6" />
                      <XAxis dataKey="category" tick={{ fontSize: 10, fill: '#556b82' }} />
                      <YAxis
                        tick={{ fontSize: 10, fill: '#556b82' }}
                        tickFormatter={(val: number) => `₹${val}`}
                      />
                      <Tooltip
                        formatter={(val: unknown) => [formatINRPrecise(Number(val) || 0), 'Spent']}
                      />
                      <Bar dataKey="amount" fill="#0057d2" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 pt-2 border-t border-rule">
                  {spendingQuery.data.category_breakdown.map((cat) => (
                    <div key={cat.category} className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="font-semibold text-ink">
                          {cat.category} ({cat.count})
                        </span>
                        <span className="num font-bold text-ink">
                          {formatINRPrecise(cat.amount)} ({cat.percentage}%)
                        </span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-canvas-sunk overflow-hidden">
                        <div
                          style={{ width: `${Math.min(100, cat.percentage)}%` }}
                          className="h-full bg-navy rounded-full"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Imported Statement Transactions Ledger */}
              <div className="rounded-lg border border-rule bg-canvas p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                  Imported Statement Ledger ({spendingQuery.data.transactions.length} rows)
                </h3>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {spendingQuery.data.transactions.map((tx) => (
                    <div
                      key={tx.txn_id}
                      className="rounded-md border border-rule bg-canvas-raised p-2.5 text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="inline-flex items-center gap-1 font-semibold text-ink">
                          {tx.type === 'DEBIT' ? (
                            <ArrowUpRight className="h-3.5 w-3.5 text-due" />
                          ) : (
                            <ArrowDownLeft className="h-3.5 w-3.5 text-positive" />
                          )}
                          {tx.counterparty}
                        </span>
                        <span
                          className={`num font-bold ${
                            tx.type === 'DEBIT' ? 'text-due' : 'text-positive'
                          }`}
                        >
                          {tx.type === 'DEBIT' ? '-' : '+'}
                          {formatINRPrecise(tx.amount)}
                        </span>
                      </div>
                      <p className="text-[11px] text-ink-soft truncate">{tx.narration}</p>
                      <div className="flex items-center justify-between text-[10px] text-ink-faint pt-0.5">
                        <span>
                          {tx.date} • <strong>{tx.app}</strong> • {tx.category}
                        </span>
                        <span className="font-mono">{tx.vpa || tx.txn_id}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

