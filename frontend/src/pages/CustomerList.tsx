import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Phone, Mail, UserCheck, Plus } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useCustomers } from '../hooks/useBusinessData';
import { useInvoices } from '../hooks/useInvoices';
import { formatINR } from '../lib/format';

export function CustomerList() {
  const { data: customers, isPending, isError, refetch } = useCustomers();
  const { data: invoices } = useInvoices();
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (customers ?? []).filter((c) => {
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        (c.phone && c.phone.includes(q)) ||
        (c.email && c.email.toLowerCase().includes(q))
      );
    });
  }, [customers, query]);

  // Compute total receivables from open confirmed invoices
  const totalReceivables = useMemo(() => {
    if (!invoices) return 0;
    return invoices
      .filter((i) => i.type === 'SALE' && i.status === 'CONFIRMED')
      .reduce((sum, i) => sum + Math.max(i.total_amount - i.paid_amount, 0), 0);
  }, [invoices]);

  if (isPending) return <LoadingState label="Loading customer accounts…" />;
  if (isError) return <ErrorState label="Couldn't load customer directory." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Customers & Accounts</h1>
          <p className="mt-0.5 text-sm text-ink-soft">
            Directory of buyers, contact details, and account ledger balances.
          </p>
        </div>
      </div>

      {/* Top summary cards */}
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Customer Summary">
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Customers</p>
          <p className="num mt-2 text-2xl font-bold text-ink">{customers?.length ?? 0}</p>
          <p className="mt-1 text-xs text-ink-faint">Registered shop accounts</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Active Khata</p>
          <p className="num mt-2 text-2xl font-bold text-positive">{customers?.length ?? 0}</p>
          <p className="mt-1 text-xs text-ink-faint">Regular retail & wholesale buyers</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Receivables (उधारी)</p>
          <p className="num mt-2 text-2xl font-bold text-due">{formatINR(totalReceivables)}</p>
          <p className="mt-1 text-xs text-ink-faint">Due across all open invoices</p>
        </div>
      </section>

      {/* Search Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, phone or email…"
            className="w-full rounded-md border border-rule bg-canvas-raised pl-9 pr-3 py-2 text-sm outline-none focus:border-navy"
          />
        </div>
        <span className="text-xs text-ink-soft">
          Showing {filtered.length} of {customers?.length ?? 0}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
        {filtered.length ? (
          <table className="min-w-full text-sm">
            <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Customer / Shop Name</th>
                <th scope="col" className="px-4 py-3 font-semibold">Phone (संपर्क)</th>
                <th scope="col" className="px-4 py-3 font-semibold">Email</th>
                <th scope="col" className="px-4 py-3 font-semibold">Status</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {filtered.map((customer) => (
                <tr key={customer.id} className="hover:bg-canvas">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{customer.name}</p>
                    <p className="text-xs text-ink-faint">ID: {customer.id}</p>
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-ink-soft">
                    {customer.phone ? (
                      <a href={`tel:${customer.phone}`} className="inline-flex items-center gap-1.5 text-navy hover:underline">
                        <Phone className="h-3.5 w-3.5 text-ink-faint" />
                        <span>{customer.phone}</span>
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3 text-ink-soft">
                    {customer.email ? (
                      <span className="inline-flex items-center gap-1.5">
                        <Mail className="h-3.5 w-3.5 text-ink-faint" />
                        <span>{customer.email}</span>
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1 rounded-full bg-positive-tint px-2.5 py-0.5 text-xs font-semibold text-positive">
                      <UserCheck className="h-3 w-3" /> Active
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/app/invoices/new?customer_id=${customer.id}&customer_name=${encodeURIComponent(customer.name)}`}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-navy hover:underline"
                    >
                      <Plus className="h-3.5 w-3.5" /> Bill
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState label={query ? 'No customers match your search.' : 'No customer records found.'} />
        )}
      </div>
    </div>
  );
}