import { useParams } from 'react-router-dom';

export function InvoiceDetail() {
  const params = useParams();
  return <div className="rounded-3xl border border-white/10 bg-white/5 p-6 text-slate-300">Invoice detail for {params.id}</div>;
}