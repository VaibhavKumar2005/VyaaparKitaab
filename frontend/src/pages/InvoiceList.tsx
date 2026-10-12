import { Link } from 'react-router-dom';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { useInvoices } from '../hooks/useInvoices';

export function InvoiceList() {
  const { data, isPending, isError, refetch } = useInvoices();

  if (isPending) return <LoadingState label="Loading invoices..." />;
  if (isError) return <ErrorState label="Unable to load invoices." onRetry={() => void refetch()} />;

  return (
    <section className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
      <div className="flex items-center justify-between gap-4"><div><h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Invoices</h1><p className="mt-2 text-sm text-slate-400">Track drafts, confirmed sales, and payments.</p></div><Link to="/app/invoices/new" className="rounded-2xl bg-sky-400 px-4 py-2 text-sm font-semibold text-slate-950">New invoice</Link></div>
      <div className="mt-6 overflow-x-auto rounded-2xl border border-white/10">
        {data?.length ? <table className="min-w-full divide-y divide-white/10 text-left text-sm"><thead className="bg-white/5 text-slate-300"><tr><th className="px-4 py-3">Invoice</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Total</th><th className="px-4 py-3">Created</th></tr></thead><tbody className="divide-y divide-white/10 text-slate-200">{data.map((invoice) => <tr key={invoice.id}><td className="px-4 py-3 font-medium"><Link className="text-sky-300 hover:text-sky-200" to={`/app/invoices/${invoice.id}`}>{invoice.invoice_number}</Link></td><td className="px-4 py-3">{invoice.status}</td><td className="px-4 py-3">₹{invoice.total_amount.toFixed(2)}</td><td className="px-4 py-3">{new Date(invoice.created_at).toLocaleDateString()}</td></tr>)}</tbody></table> : <EmptyState label="No invoices have been created yet." />}
      </div>
    </section>
  );
}