import { useMemo, useState } from 'react';
import { Building2, Mail, Pencil, Phone, Plus, Search, Trash2, Truck, X } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import {
  type Supplier,
  useBusinesses,
  useCreateSupplier,
  useDeleteSupplier,
  useSuppliers,
  useUpdateSupplier,
} from '../hooks/useBusinessData';
import { formatDate } from '../lib/format';
import { isDemoMode } from '../mock/mockStore';

export function SupplierList() {
  const { data: businesses } = useBusinesses();
  const { data: suppliers, isPending, isError, refetch } = useSuppliers();
  const createSupplier = useCreateSupplier();
  const updateSupplier = useUpdateSupplier();
  const deleteSupplier = useDeleteSupplier();

  const [query, setQuery] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const openAddModal = () => {
    setEditingSupplier(null);
    setName('');
    setPhone('');
    setEmail('');
    setFormError(null);
    setShowModal(true);
  };

  const openEditModal = (supplier: Supplier) => {
    setEditingSupplier(supplier);
    setName(supplier.name);
    setPhone(supplier.phone ?? '');
    setEmail(supplier.email ?? '');
    setFormError(null);
    setShowModal(true);
  };

  const handleDelete = async (supplier: Supplier) => {
    if (!window.confirm(`Delete supplier "${supplier.name}"?`)) return;
    try {
      await deleteSupplier.mutateAsync(supplier.id);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Unable to delete supplier');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const bizId = businesses?.[0]?.id;
    if ((!bizId && !editingSupplier) || isDemoMode()) {
      setFormError('Connect to your live store account to save suppliers.');
      return;
    }
    if (!name.trim()) {
      setFormError('Supplier / distributor name is required.');
      return;
    }
    try {
      if (editingSupplier) {
        await updateSupplier.mutateAsync({
          id: editingSupplier.id,
          name: name.trim(),
          phone: phone.trim() || null,
          email: email.trim() || null,
        });
      } else if (bizId) {
        await createSupplier.mutateAsync({
          business_id: bizId,
          name: name.trim(),
          phone: phone.trim() || null,
          email: email.trim() || null,
        });
      }
      setShowModal(false);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Unable to save supplier');
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return suppliers ?? [];
    return (suppliers ?? []).filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.phone ?? '').toLowerCase().includes(q) ||
        (s.email ?? '').toLowerCase().includes(q),
    );
  }, [suppliers, query]);

  if (isPending) return <LoadingState label="Loading suppliers…" />;
  if (isError) return <ErrorState label="Couldn't load suppliers." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Suppliers &amp; Distributors</h1>
          <p className="text-xs text-ink-soft mt-0.5">
            Track wholesale vendors, mandis, and stock distributors supplying your store.
          </p>
        </div>
        <button
          type="button"
          onClick={openAddModal}
          className="inline-flex items-center gap-1.5 rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark shadow-xs"
        >
          <Plus className="h-4 w-4" /> Add Supplier
        </button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">
            <Truck className="h-4 w-4 text-navy" /> Total Suppliers
          </div>
          <p className="num mt-2 text-2xl font-bold text-ink">{suppliers?.length ?? 0}</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">
            <Phone className="h-4 w-4 text-positive" /> Phone Reachable
          </div>
          <p className="num mt-2 text-2xl font-bold text-ink">
            {(suppliers ?? []).filter((s) => Boolean(s.phone)).length}
          </p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">
            <Building2 className="h-4 w-4 text-navy" /> Active Store
          </div>
          <p className="mt-2 truncate text-sm font-bold text-ink">{businesses?.[0]?.name ?? 'Your Store'}</p>
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rule bg-canvas-raised p-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search supplier name, mobile, or email…"
            className="w-full rounded-md border border-rule bg-canvas pl-9 pr-3 py-1.5 text-sm outline-none focus:border-navy"
          />
        </div>
        <span className="text-xs text-ink-soft">
          Showing {filtered.length} of {suppliers?.length ?? 0}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
        {filtered.length ? (
          <table className="min-w-full text-sm">
            <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Supplier Name</th>
                <th scope="col" className="px-4 py-3 font-semibold">Mobile</th>
                <th scope="col" className="px-4 py-3 font-semibold">Email</th>
                <th scope="col" className="px-4 py-3 font-semibold">Added</th>
                {!isDemoMode() && <th scope="col" className="px-4 py-3 text-right font-semibold">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {filtered.map((sup) => (
                <tr key={sup.id} className="hover:bg-canvas">
                  <td className="px-4 py-3 font-semibold text-ink">{sup.name}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-soft">
                    {sup.phone ? (
                      <a href={`tel:${sup.phone}`} className="inline-flex items-center gap-1 text-navy hover:underline">
                        <Phone className="h-3.5 w-3.5" /> {sup.phone}
                      </a>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-soft">
                    {sup.email ? (
                      <span className="inline-flex items-center gap-1">
                        <Mail className="h-3.5 w-3.5 text-ink-faint" /> {sup.email}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-soft">
                    {formatDate(sup.created_at)}
                  </td>
                  {!isDemoMode() && (
                    <td className="whitespace-nowrap px-4 py-3 text-right space-x-2">
                      <button
                        type="button"
                        onClick={() => openEditModal(sup)}
                        className="inline-flex items-center text-ink-soft hover:text-ink"
                        title="Edit supplier"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(sup)}
                        className="inline-flex items-center text-ink-faint hover:text-due"
                        title="Delete supplier"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState label={query ? 'No suppliers match your search.' : 'No suppliers added yet.'} />
        )}
      </div>

      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-label="Supplier Form"
        >
          <form
            onSubmit={handleSubmit}
            className="w-full max-w-md rounded-xl border border-rule bg-canvas-raised p-6 shadow-xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-rule pb-3">
              <h2 className="text-base font-bold text-ink">
                {editingSupplier ? 'Edit Supplier' : 'Add Supplier'}
              </h2>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-lg p-1 text-ink-soft hover:bg-canvas-sunk"
                aria-label="Close supplier modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Supplier / Agency Name *</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Metro Cash & Carry Wholesale"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Mobile Number</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="9811002233"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="billing@distributor.in"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            {formError && <p className="rounded-md bg-due-tint p-2 text-xs text-due">{formError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="rounded-md border border-rule px-3 py-1.5 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createSupplier.isPending || updateSupplier.isPending}
                className="rounded-md bg-navy px-4 py-1.5 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
              >
                {createSupplier.isPending || updateSupplier.isPending
                  ? 'Saving…'
                  : editingSupplier
                    ? 'Save Changes'
                    : 'Save Supplier'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
