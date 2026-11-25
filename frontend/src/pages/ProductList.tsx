import { useMemo, useState } from 'react';
import { Search, AlertTriangle, PackageCheck, Plus, X, Pencil, Trash2 } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import {
  type Product,
  useBusinesses,
  useCreateProduct,
  useDeleteProduct,
  useProducts,
  useUpdateProduct,
} from '../hooks/useBusinessData';
import { isDemoMode } from '../mock/mockStore';
import { formatINR, formatINRPrecise } from '../lib/format';

export function ProductList() {
  const { data: businesses } = useBusinesses();
  const { data: products, isPending, isError, refetch } = useProducts();
  const createProduct = useCreateProduct();
  const updateProduct = useUpdateProduct();
  const deleteProduct = useDeleteProduct();
  const [query, setQuery] = useState('');
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [pName, setPName] = useState('');
  const [pSku, setPSku] = useState('');
  const [pUnit, setPUnit] = useState('Pcs');
  const [pPrice, setPPrice] = useState('');
  const [pCost, setPCost] = useState('');
  const [pStock, setPStock] = useState('10');
  const [pError, setPError] = useState<string | null>(null);

  const openAddProductModal = () => {
    setEditingProduct(null);
    setPName('');
    setPSku('');
    setPUnit('Pcs');
    setPPrice('');
    setPCost('');
    setPStock('10');
    setPError(null);
    setShowAddModal(true);
  };

  const openEditProductModal = (product: Product) => {
    setEditingProduct(product);
    setPName(product.name);
    setPSku(product.sku ?? '');
    setPUnit(product.unit ?? 'Pcs');
    setPPrice(String(product.selling_price));
    setPCost(product.cost_price != null ? String(product.cost_price) : '');
    setPStock(String(product.stock_qty));
    setPError(null);
    setShowAddModal(true);
  };

  const handleDeleteProduct = async (product: Product) => {
    if (!window.confirm(`Delete product "${product.name}"?`)) return;
    try {
      await deleteProduct.mutateAsync(product.id);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Unable to delete product');
    }
  };

  const handleAddProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setPError(null);
    const bizId = businesses?.[0]?.id;
    if ((!bizId && !editingProduct) || isDemoMode()) {
      setPError('Connect to your live store account to save inventory items.');
      return;
    }
    const selling = Number(pPrice);
    if (!pName.trim() || !Number.isFinite(selling) || selling <= 0) {
      setPError('Enter a valid product name and selling price.');
      return;
    }
    try {
      if (editingProduct) {
        await updateProduct.mutateAsync({
          id: editingProduct.id,
          name: pName.trim(),
          sku: pSku.trim() || undefined,
          unit: pUnit.trim() || 'Pcs',
          selling_price: selling,
          cost_price: pCost.trim() ? Number(pCost) : undefined,
          stock_qty: Number(pStock) || 0,
        });
      } else if (bizId) {
        await createProduct.mutateAsync({
          business_id: bizId,
          name: pName.trim(),
          sku: pSku.trim() || null,
          unit: pUnit.trim() || 'Pcs',
          selling_price: selling,
          cost_price: pCost.trim() ? Number(pCost) : null,
          stock_qty: Number(pStock) || 0,
        });
      }
      setEditingProduct(null);
      setPName('');
      setPSku('');
      setPPrice('');
      setPCost('');
      setPStock('10');
      setShowAddModal(false);
    } catch (err) {
      setPError(err instanceof Error ? err.message : 'Unable to save product');
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (products ?? []).filter((p) => {
      if (showLowStockOnly && p.stock_qty > 5) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) ||
        (p.sku && p.sku.toLowerCase().includes(q))
      );
    });
  }, [products, query, showLowStockOnly]);

  const stats = useMemo(() => {
    if (!products) return { total: 0, lowStock: 0, totalValuation: 0 };
    const lowStock = products.filter((p) => p.stock_qty <= 5).length;
    const totalValuation = products.reduce((sum, p) => sum + p.stock_qty * (p.cost_price ?? p.selling_price * 0.8), 0);
    return {
      total: products.length,
      lowStock,
      totalValuation,
    };
  }, [products]);

  if (isPending) return <LoadingState label="Loading product catalog and inventory…" />;
  if (isError) return <ErrorState label="Couldn't load inventory catalog." onRetry={() => void refetch()} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Inventory & Products</h1>
          <p className="mt-0.5 text-sm text-ink-soft">
            Catalog of store items, purchase rate, selling price, and stock levels.
          </p>
        </div>
        {!isDemoMode() && (
          <button
            type="button"
            onClick={openAddProductModal}
            className="inline-flex items-center gap-1.5 rounded-md bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-navy-dark"
          >
            <Plus className="h-4 w-4" /> Add Product
          </button>
        )}
      </div>

      {/* Summary Cards */}
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Inventory Summary">
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Catalog Items</p>
          <p className="num mt-2 text-2xl font-bold text-ink">{stats.total}</p>
          <p className="mt-1 text-xs text-ink-faint">FMCG & grocery products listed</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Low Stock Alert</p>
          <p className="num mt-2 text-2xl font-bold text-due">{stats.lowStock}</p>
          <p className="mt-1 text-xs text-ink-faint">5 units or fewer remaining</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Total Stock Value</p>
          <p className="num mt-2 text-2xl font-bold text-ink">{formatINR(stats.totalValuation)}</p>
          <p className="mt-1 text-xs text-ink-faint">Estimated at wholesale cost price</p>
        </div>
      </section>

      {/* Search & Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by product name or SKU…"
            className="w-full rounded-md border border-rule bg-canvas-raised pl-9 pr-3 py-2 text-sm outline-none focus:border-navy"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowLowStockOnly(!showLowStockOnly)}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
              showLowStockOnly
                ? 'border-due bg-due-tint text-due'
                : 'border-rule bg-canvas-raised text-ink-soft hover:text-ink'
            }`}
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>Low stock only ({stats.lowStock})</span>
          </button>
          <span className="text-xs text-ink-soft">
            Showing {filtered.length} of {products?.length ?? 0}
          </span>
        </div>
      </div>

      {/* Products Table */}
      <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
        {filtered.length ? (
          <table className="min-w-full text-sm">
            <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">Product Name</th>
                <th scope="col" className="px-4 py-3 font-semibold">SKU Code</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Cost Price</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Selling Price</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Available Stock</th>
                {!isDemoMode() && <th scope="col" className="px-4 py-3 text-right font-semibold">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {filtered.map((product) => {
                const isLow = product.stock_qty <= 5;
                return (
                  <tr key={product.id} className="hover:bg-canvas">
                    <td className="px-4 py-3 font-medium text-ink">{product.name}</td>
                    <td className="num whitespace-nowrap px-4 py-3 text-ink-soft">
                      {product.sku ?? '—'}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right text-ink-soft">
                      {product.cost_price ? formatINRPrecise(product.cost_price) : '—'}
                    </td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right font-semibold text-ink">
                      {formatINRPrecise(product.selling_price)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          isLow
                            ? 'bg-due-tint text-due border border-due/20'
                            : 'bg-canvas-sunk text-ink-soft border border-rule'
                        }`}
                      >
                        {isLow ? <AlertTriangle className="h-3 w-3" /> : <PackageCheck className="h-3 w-3 text-positive" />}
                        <span className="num font-bold">{product.stock_qty}</span> {product.unit ?? 'Pcs'}
                      </span>
                    </td>
                    {!isDemoMode() && (
                      <td className="whitespace-nowrap px-4 py-3 text-right space-x-2">
                        <button
                          type="button"
                          onClick={() => openEditProductModal(product)}
                          className="inline-flex items-center text-ink-soft hover:text-ink"
                          title="Edit product & stock"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDeleteProduct(product)}
                          className="inline-flex items-center text-ink-faint hover:text-due"
                          title="Delete product"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <EmptyState
            label={
              showLowStockOnly
                ? 'No low stock items right now!'
                : query
                ? 'No products match your search.'
                : 'No inventory items found.'
            }
          />
        )}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs">
          <form
            onSubmit={handleAddProduct}
            className="w-full max-w-md rounded-xl border border-rule bg-canvas-raised p-6 shadow-xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-rule pb-3">
              <h2 className="text-base font-bold text-ink">
                {editingProduct ? 'Edit Inventory Product' : 'Add Inventory Product'}
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
              <label className="text-xs font-semibold text-ink">Product Name *</label>
              <input
                required
                value={pName}
                onChange={(e) => setPName(e.target.value)}
                placeholder="e.g. Basmati Rice 5kg"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-ink">SKU Code</label>
                <input
                  value={pSku}
                  onChange={(e) => setPSku(e.target.value)}
                  placeholder="RICE-05"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm font-mono outline-none focus:border-navy"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink">Unit</label>
                <input
                  value={pUnit}
                  onChange={(e) => setPUnit(e.target.value)}
                  placeholder="Pcs / Kg / Bag"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-semibold text-ink">Selling Price (₹) *</label>
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={pPrice}
                  onChange={(e) => setPPrice(e.target.value)}
                  className="num mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink">Cost Price (₹)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={pCost}
                  onChange={(e) => setPCost(e.target.value)}
                  className="num mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink">Stock Qty</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={pStock}
                  onChange={(e) => setPStock(e.target.value)}
                  className="num mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
            </div>
            {pError && <p className="rounded bg-due-tint p-2 text-xs text-due">{pError}</p>}
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
                disabled={createProduct.isPending || updateProduct.isPending}
                className="rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
              >
                {createProduct.isPending || updateProduct.isPending
                  ? 'Saving…'
                  : editingProduct
                    ? 'Update Product'
                    : 'Save Product'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}