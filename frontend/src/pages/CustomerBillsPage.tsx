import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CreditCard,
  Receipt,
  Upload,
  Trash2,
  Wallet,
  ArrowUpRight,
  ArrowDownLeft,
  FileText,
  Download,
  Layers,
  Zap,
  Bell,
  PieChart,
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
import { useMyBills } from '../hooks/useInvoices';
import {
  useCustomerNotifications,
  useMarkNotificationRead,
} from '../hooks/useUnifiedLedger';
import { UnifiedCategoryPanel } from '../components/UnifiedCategoryPanel';
import {
  usePersonalSpending,
  useImportStatement,
  useClearImportedTransactions,
  createSampleStatementPdfFile,
  downloadSampleStatementPdf,
} from '../hooks/useBankingIncome';
import { StatusPill, paymentState } from '../components/StatusPill';
import { UpiAutoSyncModal } from '../components/UpiAutoSyncModal';
import { formatINR, formatINRPrecise, formatDate } from '../lib/format';
import { LoadingState } from '../components/ui/LoadingState';
import { ErrorState } from '../components/ui/ErrorState';

type CustomerPageTab = 'bills' | 'unified' | 'notifications' | 'statements' | 'all';

export function CustomerBillsPage() {
  // The server returns only SALE bills linked to this customer's phone/e-mail.
  const [activeTab, setActiveTab] = useState<CustomerPageTab>('bills');
  const { data: allInvoices, isPending, isError, refetch } = useMyBills();
  const spendingQuery = usePersonalSpending();
  const notificationsQuery = useCustomerNotifications();
  const markReadMutation = useMarkNotificationRead();
  const unreadCount = (notificationsQuery.data ?? []).filter((n) => !n.is_read).length;
  const importStatementMutation = useImportStatement();
  const clearTransactionsMutation = useClearImportedTransactions();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [lockedPdfFile, setLockedPdfFile] = useState<File | null>(null);
  const [pdfPassword, setPdfPassword] = useState<string>('');
  const [showBridgeModal, setShowBridgeModal] = useState<boolean>(false);

  const runStatementImport = (file: File, password?: string) => {
    importStatementMutation.mutate(
      password ? { file, pdfPassword: password } : file,
      {
        onSuccess: (res) => {
          setLockedPdfFile(null);
          setPdfPassword('');
          setImportMsg(
            `Imported ${res.imported_count} real statement rows (${res.debits_count} personal debits, ${res.credits_count} credits) from ${res.filename} into PostgreSQL.`
          );
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : 'Could not import statement';
          if (/password/i.test(msg)) {
            setLockedPdfFile(file);
          }
          setImportMsg(msg);
        },
      },
    );
  };

  const handleUploadStatement = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    runStatementImport(file);
    e.target.value = '';
  };

  const handleLoadSamplePdf = () => {
    const samplePdf = createSampleStatementPdfFile();
    runStatementImport(samplePdf);
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
          Verified store invoices linked to your mobile/email, digital payment receipts, and instant UPI clearing.
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

      {/* Segmented View Switcher: Prevents Vertical UI Stacking */}
      <nav
        className="no-print flex flex-wrap items-center justify-between gap-2 rounded-xl border border-rule bg-canvas-sunk p-1.5"
        aria-label="Customer Passbook Switcher"
      >
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveTab('bills')}
            className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all ${
              activeTab === 'bills'
                ? 'bg-navy text-white shadow-xs'
                : 'text-ink-soft hover:bg-canvas hover:text-ink'
            }`}
          >
            <Receipt className="h-3.5 w-3.5" />
            <span>Store Bills &amp; Receipts ({customerBills.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('unified')}
            className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all ${
              activeTab === 'unified'
                ? 'bg-navy text-white shadow-xs'
                : 'text-ink-soft hover:bg-canvas hover:text-ink'
            }`}
          >
            <PieChart className="h-3.5 w-3.5" />
            <span>Categories &amp; Ask AI</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('notifications')}
            className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all ${
              activeTab === 'notifications'
                ? 'bg-navy text-white shadow-xs'
                : 'text-ink-soft hover:bg-canvas hover:text-ink'
            }`}
          >
            <Bell className="h-3.5 w-3.5" />
            <span>Receipt Alerts</span>
            {unreadCount > 0 && (
              <span className="rounded-full bg-due px-1.5 py-0.5 text-[10px] font-bold text-white">
                {unreadCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('statements')}
            className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-bold transition-all ${
              activeTab === 'statements'
                ? 'bg-navy text-white shadow-xs'
                : 'text-ink-soft hover:bg-canvas hover:text-ink'
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            <span>Personal PDF / UPI Statement Analytics</span>
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                activeTab === 'statements'
                  ? 'bg-white/20 text-white'
                  : 'bg-emerald-100 text-emerald-800'
              }`}
            >
              PDF / CSV
            </span>
          </button>
        </div>

        <button
          type="button"
          onClick={() => setActiveTab('all')}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
            activeTab === 'all'
              ? 'bg-navy text-white shadow-xs'
              : 'border border-rule bg-canvas text-ink-soft hover:text-ink'
          }`}
        >
          <Layers className="h-3.5 w-3.5" />
          <span>Show Both</span>
        </button>
      </nav>

      {/* Bills Table */}
      {(activeTab === 'bills' || activeTab === 'all') && (
        <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
          <table className="min-w-full text-sm">
            <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Bill Date</th>
                <th scope="col" className="px-4 py-3 font-semibold">Store</th>
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
                    <td className="whitespace-nowrap px-4 py-3 text-xs font-medium text-ink">
                      {bill.store_name ?? 'Merchant Store'}
                    </td>
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
      )}

      {/* Unified Category -> Subcategory Tree & AI Assistant */}
      {(activeTab === 'unified' || activeTab === 'all') && (
        <UnifiedCategoryPanel view="customer" />
      )}

      {/* Store-to-Customer Purchase Notifications */}
      {(activeTab === 'notifications' || activeTab === 'all') && (
        <section className="rounded-xl border border-rule bg-canvas-raised p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-3">
            <div>
              <h2 className="text-base font-bold text-ink flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" />
                Purchase &amp; Receipt Notifications
              </h2>
              <p className="text-xs text-ink-soft mt-0.5">
                Automatic confirmations sent whenever a store records your bill or captures payment.
              </p>
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => markReadMutation.mutate(undefined)}
                disabled={markReadMutation.isPending}
                className="rounded-md border border-rule bg-canvas px-3 py-1.5 text-xs font-semibold text-ink hover:bg-canvas-sunk"
              >
                Mark all read
              </button>
            )}
          </div>

          {(notificationsQuery.data ?? []).length === 0 ? (
            <p className="text-xs text-ink-soft py-4">No store purchase notifications yet.</p>
          ) : (
            <div className="space-y-2.5">
              {(notificationsQuery.data ?? []).map((n) => (
                <div
                  key={n.id}
                  className={`rounded-lg border p-3.5 flex flex-wrap items-start justify-between gap-3 ${
                    n.is_read ? 'border-rule bg-canvas' : 'border-primary/40 bg-navy-tint/30'
                  }`}
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-ink">{n.title}</span>
                      <span className="rounded bg-canvas-sunk px-2 py-0.5 text-[10px] font-semibold text-ink-soft">
                        {n.category} &gt; {n.subcategory}
                      </span>
                      {n.discount_amount > 0 && (
                        <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                          Saved {formatINR(n.discount_amount)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-soft">{n.message}</p>
                    <p className="text-[11px] text-ink-faint">
                      {n.store_name} • {n.payment_channel ?? 'UPI'} • {formatDate(n.created_at)}
                    </p>
                  </div>
                  {!n.is_read && (
                    <button
                      type="button"
                      onClick={() => markReadMutation.mutate(n.id)}
                      className="rounded border border-rule bg-white px-2.5 py-1 text-[11px] font-semibold text-primary hover:bg-canvas-sunk"
                    >
                      Mark read
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Personal Spending & UPI Statement Importer (Real Outside PDF / CSV / JSON Data) */}
      {(activeTab === 'statements' || activeTab === 'all') && (
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
                  Upload your real Google Pay (CSV / JSON / Takeout HTML), PhonePe, Paytm, or Bank (SBI / HDFC / ICICI / Axis) <strong>PDF, CSV, HTML, or JSON</strong> statement, or use the zero-credential Auto-Sync Bridge.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.csv,.tsv,.txt,.json,.html,.htm,application/pdf,text/html"
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
                {importStatementMutation.isPending ? 'Importing…' : 'Upload Statement (PDF / CSV / GPay HTML)'}
              </button>
              <button
                type="button"
                onClick={() => setShowBridgeModal(true)}
                className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-950 hover:bg-amber-100"
                title="Sync GPay & Paytm alerts automatically without storing passwords or OAuth tokens"
              >
                <Zap className="h-3.5 w-3.5 text-amber-600" />
                Auto-Sync GPay / Paytm
              </button>
              <button
                type="button"
                onClick={handleLoadSamplePdf}
                disabled={importStatementMutation.isPending}
                className="inline-flex items-center gap-1.5 rounded-md border border-emerald-600/40 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-900 hover:bg-emerald-100"
                title="Load realistic 12-row Indian UPI & Bank PDF statement"
              >
                <FileText className="h-3.5 w-3.5 text-emerald-700" />
                Load Realistic PDF
              </button>
              <button
                type="button"
                onClick={downloadSampleStatementPdf}
                className="inline-flex items-center gap-1 rounded-md border border-rule bg-canvas px-2.5 py-2 text-xs font-semibold text-ink-soft hover:text-ink hover:bg-canvas-sunk"
                title="Download sample PDF statement file"
              >
                <Download className="h-3.5 w-3.5" />
                Sample PDF
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

        {lockedPdfFile && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (pdfPassword.trim()) {
                runStatementImport(lockedPdfFile, pdfPassword.trim());
              }
            }}
            className="rounded-lg border border-amber-300 bg-amber-50 p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
          >
            <div className="text-xs text-amber-950">
              <strong>Encrypted PDF ({lockedPdfFile.name}):</strong> Enter password to decrypt in-memory (never stored).
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <input
                type="password"
                value={pdfPassword}
                onChange={(e) => setPdfPassword(e.target.value)}
                placeholder="PDF Password"
                className="rounded border border-amber-300 bg-white px-2.5 py-1.5 text-xs outline-none focus:border-navy"
              />
              <button
                type="submit"
                disabled={!pdfPassword.trim() || importStatementMutation.isPending}
                className="rounded bg-navy px-3 py-1.5 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
              >
                {importStatementMutation.isPending ? 'Unlocking…' : 'Unlock & Import'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setLockedPdfFile(null);
                  setPdfPassword('');
                }}
                className="rounded border border-amber-300 px-2.5 py-1.5 text-xs text-amber-900 hover:bg-amber-100"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {!spendingQuery.data?.has_imported_data ? (
          <div className="rounded-lg border border-dashed border-rule bg-canvas-sunk p-8 text-center space-y-2">
            <p className="text-sm font-semibold text-ink">
              No external bank or UPI statement uploaded yet
            </p>
            <p className="text-xs text-ink-soft max-w-lg mx-auto">
              Click <strong>Upload Statement (PDF / CSV / JSON)</strong> or <strong>Load Realistic PDF</strong> above to parse a real Google Pay, PhonePe, Paytm, or bank statement (<code className="font-mono text-navy">data/realistic_upi_bank_statement.pdf</code> or <code className="font-mono text-navy">data/real_gpay_and_bank_statement.csv</code>).
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
      )}
      <UpiAutoSyncModal
        open={showBridgeModal}
        onClose={() => setShowBridgeModal(false)}
        onSynced={(summary) => setImportMsg(summary)}
      />
    </div>
  );
}

