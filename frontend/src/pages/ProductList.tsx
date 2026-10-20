import { useMemo, useState } from 'react';
import { Search, AlertTriangle, PackageCheck } from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useProducts } from '../hooks/useBusinessData';
import { formatINR, formatINRPrecise } from '../lib/format';

export function ProductList() {
  const { data: products, isPending, isError, refetch } = useProducts();
  const [query, setQuery] = useState('');
  const [showLowStockOnly, setShowLowStockOnly] = useState(false);

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
                <th scope="col" className="px-4 py-3 text-right font-semibold">Cost (लागत)</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Selling Price (बिक्री)</th>
                <th scope="col" className="px-4 py-3 text-right font-semibold">Available Stock</th>
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
    </div>
  );
}