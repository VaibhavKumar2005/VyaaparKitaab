import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useProducts } from '../hooks/useBusinessData';

export function ProductList() {
  const { data, isPending, isError, refetch } = useProducts();

  if (isPending) return <LoadingState label="Loading products..." />;
  if (isError) return <ErrorState label="Unable to load products." onRetry={() => void refetch()} />;

  return (
    <section className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between gap-4"><div><h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Products</h1><p className="mt-2 text-sm text-slate-400">Inventory and selling prices for your business.</p></div><span className="rounded-full border border-white/10 px-3 py-1 text-sm text-slate-300">{data?.length ?? 0} total</span></div>
      <div className="mt-6 overflow-x-auto rounded-2xl border border-white/10">
        {data?.length ? <table className="min-w-full divide-y divide-white/10 text-left text-sm"><thead className="bg-white/5 text-slate-300"><tr><th className="px-4 py-3">Product</th><th className="px-4 py-3">SKU</th><th className="px-4 py-3">Price</th><th className="px-4 py-3">Stock</th></tr></thead><tbody className="divide-y divide-white/10 text-slate-200">{data.map((product) => <tr key={product.id}><td className="px-4 py-3 font-medium">{product.name}</td><td className="px-4 py-3">{product.sku ?? '-'}</td><td className="px-4 py-3">₹{product.selling_price.toFixed(2)}</td><td className="px-4 py-3">{product.stock_qty} {product.unit ?? ''}</td></tr>)}</tbody></table> : <EmptyState label="No products have been added yet." />}
      </div>
    </section>
  );
}