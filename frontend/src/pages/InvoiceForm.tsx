import { FormEvent, useMemo, useState } from 'react';

type LineItem = { product: string; quantity: number; unitPrice: number; discount: number };

const gstRate = 0.18;

export function InvoiceForm() {
  const [customerQuery, setCustomerQuery] = useState('');
  const [items, setItems] = useState<LineItem[]>([{ product: '', quantity: 1, unitPrice: 0, discount: 0 }]);
  const [paymentMethod, setPaymentMethod] = useState('UPI');
  const [showOtp, setShowOtp] = useState(false);
  const [otp, setOtp] = useState('');

  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, item) => sum + item.quantity * item.unitPrice - item.discount, 0);
    const tax = subtotal * gstRate;
    return { subtotal, tax, total: subtotal + tax };
  }, [items]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (totals.total > 500) {
      setShowOtp(true);
    }
  };

  return (
    <div className="space-y-6 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
      <div>
        <h1 className="font-[Space_Grotesk] text-3xl font-bold text-white">Create invoice</h1>
        <p className="mt-2 text-slate-400">Build an invoice with live totals and OTP verification for larger transactions.</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-6">
        <label className="block text-sm text-slate-300">
          Customer search or create
          <input value={customerQuery} onChange={(e) => setCustomerQuery(e.target.value)} className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 outline-none focus:border-sky-400" placeholder="Search customer or type a new name" />
        </label>

        <div className="space-y-4">
          {items.map((item, index) => (
            <div key={`${index}-${item.product}`} className="grid gap-3 rounded-3xl border border-white/10 bg-slate-950/35 p-4 md:grid-cols-[1.6fr_0.6fr_0.8fr_0.8fr]">
              <input value={item.product} onChange={(e) => setItems((current) => current.map((entry, position) => position === index ? { ...entry, product: e.target.value } : entry))} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none" placeholder="Product" />
              <input type="number" min="1" value={item.quantity} onChange={(e) => setItems((current) => current.map((entry, position) => position === index ? { ...entry, quantity: Number(e.target.value) } : entry))} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none" placeholder="Qty" />
              <input type="number" min="0" value={item.unitPrice} onChange={(e) => setItems((current) => current.map((entry, position) => position === index ? { ...entry, unitPrice: Number(e.target.value) } : entry))} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none" placeholder="Unit price" />
              <input type="number" min="0" value={item.discount} onChange={(e) => setItems((current) => current.map((entry, position) => position === index ? { ...entry, discount: Number(e.target.value) } : entry))} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none" placeholder="Discount" />
            </div>
          ))}
          <button type="button" onClick={() => setItems((current) => [...current, { product: '', quantity: 1, unitPrice: 0, discount: 0 }])} className="rounded-full border border-white/15 px-4 py-2 text-sm text-slate-200">
            Add line item
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm text-slate-300">
            Payment method
            <select value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 outline-none">
              {['CASH', 'UPI', 'CARD', 'CREDIT'].map((method) => <option key={method}>{method}</option>)}
            </select>
          </label>
          <div className="rounded-3xl border border-white/10 bg-slate-950/40 p-4">
            <p className="text-sm text-slate-400">Subtotal: ₹{totals.subtotal.toFixed(2)}</p>
            <p className="text-sm text-slate-400">GST (18%): ₹{totals.tax.toFixed(2)}</p>
            <p className="mt-2 text-2xl font-bold text-white">Total: ₹{totals.total.toFixed(2)}</p>
          </div>
        </div>

        <button type="submit" className="rounded-2xl bg-sky-400 px-5 py-3 font-semibold text-slate-950">Submit invoice</button>
      </form>

      {showOtp ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4">
          <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-slate-950 p-6 shadow-glow">
            <h2 className="text-2xl font-bold text-white">OTP verification required</h2>
            <p className="mt-2 text-sm text-slate-400">Transactions above ₹500 require a phone OTP before submission.</p>
            <input value={otp} onChange={(e) => setOtp(e.target.value)} className="mt-4 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 outline-none" placeholder="Enter OTP" />
            <div className="mt-4 flex justify-end gap-3">
              <button type="button" onClick={() => setShowOtp(false)} className="rounded-2xl border border-white/10 px-4 py-2">Cancel</button>
              <button type="button" className="rounded-2xl bg-violet-400 px-4 py-2 font-semibold text-slate-950">Verify & submit</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}