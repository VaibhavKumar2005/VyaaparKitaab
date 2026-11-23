import { useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { paymentState } from '../components/StatusPill';
import { useInvoices } from '../hooks/useInvoices';
import { apiFetch } from '../lib/api';
import { isDemoMode } from '../mock/mockStore';
import { TransactionTable } from './StoreDashboard';

const filters = ['All', 'Unpaid', 'Part paid', 'Paid', 'Draft'] as const;

export function InvoiceList() {
  const { data, isPending, isError, refetch } = useInvoices();
  const [filter, setFilter] = useState<(typeof filters)[number]>('All');
  const [query, setQuery] = useState('');
  const [exporting, setExporting] = useState(false);

  const handleExportGstr1 = async () => {
    setExporting(true);
    try {
      let payload: unknown;
      if (isDemoMode()) {
        const sales = (data ?? []).filter((i) => i.type === 'SALE' && i.status !== 'DRAFT' && i.status !== 'CANCELLED');
        payload = {
          mode: 'demo',
          generated_at: new Date().toISOString(),
          summary: {
            total_invoices: sales.length,
            taxable_value: sales.reduce((s, i) => s + Math.max(i.subtotal - i.discount_amount, 0), 0),
            total_tax: sales.reduce((s, i) => s + i.tax_amount, 0),
            invoice_value: sales.reduce((s, i) => s + i.total_amount, 0),
          },
          invoices: sales,
        };
      } else {
        payload = await apiFetch<Record<string, unknown>>('/invoices/export/gstr1');
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `vyaparkitaab_gstr1_${new Date().toISOString().slice(0, 7)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? [])
      .filter((i) => filter === 'All' || paymentState(i) === filter)
      .filter((i) => !q || i.invoice_number.toLowerCase().includes(q))
      .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  }, [data, filter, query]);

  if (isPending) return <LoadingState label="Loading invoices…" />;
  if (isError) return <ErrorState label="Couldn't load invoices." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Invoices</h1>
        <button
          type="button"
          onClick={() => void handleExportGstr1()}
          disabled={exporting}
          className="inline-flex items-center gap-1.5 rounded-md border border-navy bg-canvas-raised px-3.5 py-2 text-xs font-semibold text-navy hover:bg-navy-tint disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          <span>{exporting ? 'Exporting GSTR-1…' : 'Export GSTR-1 JSON'}</span>
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
          {filters.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={`rounded-full border px-3 py-1 text-sm font-medium ${
                filter === f
                  ? 'border-navy bg-navy text-white'
                  : 'border-rule bg-canvas-raised text-ink-soft hover:text-ink'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <label className="sr-only" htmlFor="invoice-search">Search invoices</label>
        <input
          id="invoice-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by invoice number"
          className="w-full rounded-md border border-rule bg-canvas-raised px-3 py-2 text-sm outline-none focus:border-navy sm:w-64"
        />
      </div>

      <TransactionTable rows={rows} />
    </div>
  );
}