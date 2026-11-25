import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Phone, Mail, UserCheck, Plus, BookOpen, X, Pencil, Trash2 } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { StatusPill, paymentState } from '../components/StatusPill';
import {
  type Customer,
  useBusinesses,
  useCreateCustomer,
  useCustomers,
  useDeleteCustomer,
  useUpdateCustomer,
} from '../hooks/useBusinessData';
import { isDemoMode } from '../mock/mockStore';
import { useInvoices } from '../hooks/useInvoices';
import { formatDate, formatINR, formatINRPrecise } from '../lib/format';

type BalanceFilter = 'all' | 'due' | 'settled';

export function CustomerList() {
  const { data: businesses } = useBusinesses();
  const { data: customers, isPending, isError, refetch } = useCustomers();
  const createCustomer = useCreateCustomer();
  const updateCustomer = useUpdateCustomer();
  const deleteCustomer = useDeleteCustomer();
  const { data: invoices } = useInvoices();
  const [query, setQuery] = useState('');
  const [balanceFilter, setBalanceFilter] = useState<BalanceFilter>('all');
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [addError, setAddError] = useState<string | null>(null);

  const openAddCustomerModal = () => {
    setEditingCustomer(null);
    setNewName('');
    setNewPhone('');
    setNewEmail('');
    setAddError(null);
    setShowAddModal(true);
  };

  const openEditCustomerModal = (customer: Customer) => {
    setEditingCustomer(customer);
    setNewName(customer.name);
    setNewPhone(customer.phone ?? '');
    setNewEmail(customer.email ?? '');
    setAddError(null);
    setShowAddModal(true);
  };

  const handleDeleteCustomer = async (customer: Customer) => {
    if (!window.confirm(`Delete customer "${customer.name}"?`)) return;
    try {
      await deleteCustomer.mutateAsync(customer.id);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Unable to delete customer');
    }
  };

  const handleAddCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddError(null);
    const bizId = businesses?.[0]?.id;
    if ((!bizId && !editingCustomer) || isDemoMode()) {
      setAddError('Connect to your live store account to save customers.');
      return;
    }
    if (!newName.trim()) {
      setAddError('Customer name is required.');
      return;
    }
    try {
      if (editingCustomer) {
        await updateCustomer.mutateAsync({
          id: editingCustomer.id,
          name: newName.trim(),
          phone: newPhone.trim() || undefined,
          email: newEmail.trim() || undefined,
        });
      } else if (bizId) {
        await createCustomer.mutateAsync({
          business_id: bizId,
          name: newName.trim(),
          phone: newPhone.trim() || null,
          email: newEmail.trim() || null,
        });
      }
      setEditingCustomer(null);
      setNewName('');
      setNewPhone('');
      setNewEmail('');
      setShowAddModal(false);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Unable to save customer');
    }
  };

  const ledgerByCustomer = useMemo(() => {
    const map = new Map<
      string,
      {
        totalBilled: number;
        totalPaid: number;
        balanceDue: number;
        count: number;
        entries: Array<{
          id: string;
          invoice_number: string;
          created_at: string;
          total_amount: number;
          paid_amount: number;
          runningBalance: number;
          state: string;
        }>;
      }
    >();

    const validSales = (invoices ?? [])
      .filter((i) => i.type === 'SALE' && i.status !== 'CANCELLED' && i.status !== 'DRAFT' && i.customer_id)
      .sort((a, b) => +new Date(a.created_at) - +new Date(b.created_at));

    for (const inv of validSales) {
      const cid = String(inv.customer_id);
      const curr = map.get(cid) ?? { totalBilled: 0, totalPaid: 0, balanceDue: 0, count: 0, entries: [] };
      curr.totalBilled = Number((curr.totalBilled + inv.total_amount).toFixed(2));
      curr.totalPaid = Number((curr.totalPaid + inv.paid_amount).toFixed(2));
      curr.balanceDue = Number(Math.max(curr.totalBilled - curr.totalPaid, 0).toFixed(2));
      curr.count += 1;
      curr.entries.push({
        id: inv.id,
        invoice_number: inv.invoice_number,
        created_at: inv.created_at,
        total_amount: inv.total_amount,
        paid_amount: inv.paid_amount,
        runningBalance: curr.balanceDue,
        state: paymentState(inv),
      });
      map.set(cid, curr);
    }
    return map;
  }, [invoices]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (customers ?? []).filter((c) => {
      const stats = ledgerByCustomer.get(c.id);
      const due = stats?.balanceDue ?? 0;
      if (balanceFilter === 'due' && due <= 0) return false;
      if (balanceFilter === 'settled' && due > 0) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        (c.phone && c.phone.includes(q)) ||
        (c.email && c.email.toLowerCase().includes(q))
      );
    });
  }, [customers, query, balanceFilter, ledgerByCustomer]);

  // Compute total receivables from open confirmed invoices
  const totalReceivables = useMemo(() => {
    if (!invoices) return 0;
    return invoices
      .filter((i) => i.type === 'SALE' && i.status !== 'CANCELLED' && i.status !== 'DRAFT')
      .reduce((sum, i) => sum + Math.max(i.total_amount - i.paid_amount, 0), 0);
  }, [invoices]);

  const selectedCustomer = (customers ?? []).find((c) => c.id === selectedCustomerId) ?? null;
  const selectedLedger = selectedCustomer ? ledgerByCustomer.get(selectedCustomer.id) : undefined;

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
        {!isDemoMode() && (
          <button
            type="button"
            onClick={openAddCustomerModal}
            className="inline-flex items-center gap-1.5 rounded-md bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-navy-dark"
          >
            <Plus className="h-4 w-4" /> Add Customer
          </button>
        )}
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
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Receivables</p>
          <p className="num mt-2 text-2xl font-bold text-due">{formatINR(totalReceivables)}</p>
          <p className="mt-1 text-xs text-ink-faint">Due across all open invoices</p>
        </div>
      </section>

      {/* Search Bar & Balance Filter Pills */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, phone or email…"
              className="w-full rounded-md border border-rule bg-canvas-raised pl-9 pr-3 py-2 text-sm outline-none focus:border-navy"
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-rule bg-canvas-sunk p-1 text-xs font-semibold">
            {(
              [
                ['all', 'All'],
                ['due', 'Has Udhaar'],
                ['settled', 'Settled'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setBalanceFilter(key)}
                className={`rounded-md px-2.5 py-1 transition-colors ${
                  balanceFilter === key
                    ? 'bg-navy text-white'
                    : 'text-ink-soft hover:text-ink'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
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
                <th scope="col" className="px-4 py-3 font-semibold">Contact</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Bills</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Total Billed</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Balance Due</th>
                <th scope="col" className="px-4 py-3 font-semibold">Status</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {filtered.map((customer) => {
                const stats = ledgerByCustomer.get(customer.id);
                const balanceDue = stats?.balanceDue ?? 0;
                return (
                <tr key={customer.id} className="hover:bg-canvas">
                  <td className="px-4 py-3">
                    <p className="font-medium text-ink">{customer.name}</p>
                    <p className="text-xs text-ink-faint">ID: {customer.id}</p>
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-ink-soft text-xs space-y-0.5">
                    {customer.phone && (
                      <div>
                        <a href={`tel:${customer.phone}`} className="inline-flex items-center gap-1 text-navy hover:underline">
                          <Phone className="h-3 w-3 text-ink-faint" />
                          <span>{customer.phone}</span>
                        </a>
                      </div>
                    )}
                    {customer.email && (
                      <div className="inline-flex items-center gap-1 text-ink-soft">
                        <Mail className="h-3 w-3 text-ink-faint" />
                        <span>{customer.email}</span>
                      </div>
                    )}
                    {!customer.phone && !customer.email && '—'}
                  </td>
                  <td className="num px-4 py-3 text-right text-ink-soft">
                    {stats?.count ?? 0}
                  </td>
                  <td className="num px-4 py-3 text-right font-medium text-ink">
                    {formatINR(stats?.totalBilled ?? 0)}
                  </td>
                  <td className={`num px-4 py-3 text-right font-bold ${balanceDue > 0 ? 'text-due' : 'text-positive'}`}>
                    {formatINR(balanceDue)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        balanceDue > 0
                          ? 'bg-due-tint text-due'
                          : 'bg-positive-tint text-positive'
                      }`}
                    >
                      <UserCheck className="h-3 w-3" /> {balanceDue > 0 ? 'Udhaar Due' : 'Settled'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap space-x-3">
                    <button
                      type="button"
                      onClick={() => setSelectedCustomerId(customer.id)}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                    >
                      <BookOpen className="h-3.5 w-3.5" /> Khata
                    </button>
                    <Link
                      to={`/app/invoices/new?customer_id=${customer.id}&customer_name=${encodeURIComponent(customer.name)}`}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-navy hover:underline"
                    >
                      <Plus className="h-3.5 w-3.5" /> Bill
                    </Link>
                    {!isDemoMode() && (
                      <>
                        <button
                          type="button"
                          onClick={() => openEditCustomerModal(customer)}
                          className="inline-flex items-center gap-1 text-xs font-medium text-ink-soft hover:text-ink"
                          title="Edit customer"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeleteCustomer(customer)}
                          className="inline-flex items-center gap-1 text-xs font-medium text-ink-faint hover:text-due"
                          title="Delete customer"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <EmptyState label={query ? 'No customers match your search.' : 'No customer records found.'} />
        )}
      </div>

      {/* Customer Running-Balance Udhaar Khata Modal */}
      {selectedCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <div className="w-full max-w-2xl rounded-2xl border border-rule bg-canvas-raised p-6 shadow-2xl space-y-4">
            <div className="flex items-start justify-between border-b border-rule pb-3">
              <div>
                <h2 className="text-lg font-bold text-ink">{selectedCustomer.name} — Khata Statement</h2>
                <p className="text-xs text-ink-soft mt-0.5">
                  {selectedCustomer.phone ?? 'No phone'}
                  {selectedCustomer.email ? ` · ${selectedCustomer.email}` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCustomerId(null)}
                className="rounded-lg p-1.5 text-ink-soft hover:bg-canvas-sunk hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="rounded-lg border border-rule bg-canvas p-3">
                <span className="text-ink-soft">Total Billed</span>
                <p className="num mt-1 text-base font-bold text-ink">{formatINRPrecise(selectedLedger?.totalBilled ?? 0)}</p>
              </div>
              <div className="rounded-lg border border-rule bg-canvas p-3">
                <span className="text-ink-soft">Total Paid</span>
                <p className="num mt-1 text-base font-bold text-positive">{formatINRPrecise(selectedLedger?.totalPaid ?? 0)}</p>
              </div>
              <div className="rounded-lg border border-rule bg-canvas p-3">
                <span className="text-ink-soft">Outstanding Udhaar</span>
                <p className={`num mt-1 text-base font-bold ${(selectedLedger?.balanceDue ?? 0) > 0 ? 'text-due' : 'text-positive'}`}>
                  {formatINRPrecise(selectedLedger?.balanceDue ?? 0)}
                </p>
              </div>
            </div>

            {!selectedLedger || selectedLedger.entries.length === 0 ? (
              <p className="py-6 text-center text-xs text-ink-soft border border-dashed border-rule rounded-lg">
                No confirmed bills yet for {selectedCustomer.name}.
              </p>
            ) : (
              <div className="overflow-x-auto max-h-72 rounded-lg border border-rule">
                <table className="min-w-full text-xs">
                  <thead className="bg-canvas-sunk text-left uppercase text-ink-soft">
                    <tr>
                      <th className="px-3 py-2 font-semibold">Date</th>
                      <th className="px-3 py-2 font-semibold">Invoice #</th>
                      <th className="px-3 py-2 text-right font-semibold">Billed</th>
                      <th className="px-3 py-2 text-right font-semibold">Paid</th>
                      <th className="px-3 py-2 text-right font-semibold">Running Balance</th>
                      <th className="px-3 py-2 font-semibold">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule bg-canvas">
                    {selectedLedger.entries.map((entry) => (
                      <tr key={entry.id}>
                        <td className="px-3 py-2 text-ink-soft whitespace-nowrap">{formatDate(entry.created_at)}</td>
                        <td className="px-3 py-2 font-mono font-semibold text-navy">
                          <Link to={`/app/invoices/${entry.id}`} className="hover:underline">
                            {entry.invoice_number}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-right num">{formatINRPrecise(entry.total_amount)}</td>
                        <td className="px-3 py-2 text-right num text-positive">{formatINRPrecise(entry.paid_amount)}</td>
                        <td className="px-3 py-2 text-right num font-bold text-ink">{formatINRPrecise(entry.runningBalance)}</td>
                        <td className="px-3 py-2"><StatusPill state={entry.state} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 border-t border-rule pt-3">
              <button
                type="button"
                onClick={() => setSelectedCustomerId(null)}
                className="rounded-lg border border-rule px-3.5 py-1.5 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
              >
                Close
              </button>
              <Link
                to={`/app/invoices/new?customer_id=${selectedCustomer.id}&customer_name=${encodeURIComponent(selectedCustomer.name)}`}
                className="inline-flex items-center gap-1 rounded-lg bg-navy px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-navy-dark"
              >
                <Plus className="h-3.5 w-3.5" /> Bill Customer
              </Link>
            </div>
          </div>
        </div>
      )}

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <form
            onSubmit={handleAddCustomer}
            className="w-full max-w-md rounded-xl border border-rule bg-canvas-raised p-6 shadow-xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-rule pb-3">
              <h2 className="text-base font-bold text-ink">
                {editingCustomer ? 'Edit Customer Account' : 'Add Customer Account'}
              </h2>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="rounded-lg p-1 text-ink-soft hover:bg-canvas-sunk"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Customer Name *</label>
              <input
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Ananya Verma"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Mobile Number (+91)</label>
              <input
                type="tel"
                value={newPhone}
                onChange={(e) => setNewPhone(e.target.value)}
                placeholder="Matching Customer Passbook links bills automatically"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Email Address</label>
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="customer@example.com"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            {addError && <p className="rounded bg-due-tint p-2 text-xs text-due">{addError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="rounded-md border border-rule px-3.5 py-2 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createCustomer.isPending || updateCustomer.isPending}
                className="rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
              >
                {createCustomer.isPending || updateCustomer.isPending
                  ? 'Saving…'
                  : editingCustomer
                    ? 'Update Customer'
                    : 'Save Customer'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}