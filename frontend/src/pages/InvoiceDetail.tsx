import { useParams } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useInvoice } from '../hooks/useInvoices';

export function InvoiceDetail() {
  const { id } = useParams();
  const { data, isPending, isError, refetch } = useInvoice(id);

  if (isPending) return <LoadingState label="Loading invoice..." />;
  if (isError || !data) return <ErrorState label="Unable to load this invoice." onRetry={() => void refetch()} />;

  return <section className="space-y-6 rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl"><div><p className="text-sm text-slate-400">Invoice</p><h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">{data.invoice_number}</h1><p className="mt-2 text-sm text-slate-300">{data.status} · {new Date(data.created_at).toLocaleDateString()}</p></div><div className="grid gap-4 md:grid-cols-3"><div><p className="text-sm text-slate-400">Subtotal</p><p className="text-xl font-semibold text-white">₹{data.subtotal.toFixed(2)}</p></div><div><p className="text-sm text-slate-400">Tax</p><p className="text-xl font-semibold text-white">₹{data.tax_amount.toFixed(2)}</p></div><div><p className="text-sm text-slate-400">Total</p><p className="text-xl font-semibold text-white">₹{data.total_amount.toFixed(2)}</p></div></div><div className="overflow-x-auto rounded-2xl border border-white/10"><table className="min-w-full divide-y divide-white/10 text-left text-sm"><thead className="bg-white/5 text-slate-300"><tr><th className="px-4 py-3">Product</th><th className="px-4 py-3">Quantity</th><th className="px-4 py-3">Line total</th></tr></thead><tbody className="divide-y divide-white/10 text-slate-200">{data.items.map((item) => <tr key={item.id}><td className="px-4 py-3">{item.product_id}</td><td className="px-4 py-3">{item.quantity}</td><td className="px-4 py-3">₹{item.line_total.toFixed(2)}</td></tr>)}</tbody></table></div></section>;
}