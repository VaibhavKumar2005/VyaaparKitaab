import { useMemo, useState } from 'react';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { paymentState } from '../components/StatusPill';
import { useInvoices } from '../hooks/useInvoices';
import { TransactionTable } from './StoreDashboard';

const filters = ['All', 'Unpaid', 'Part paid', 'Paid', 'Draft'] as const;

export function InvoiceList() {
  const { data, isPending, isError, refetch } = useInvoices();
  const [filter, setFilter] = useState<(typeof filters)[number]>('All');
  const [query, setQuery] = useState('');

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
      <h1 className="text-2xl font-bold">Invoices</h1>

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