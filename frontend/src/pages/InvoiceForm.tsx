import { FormEvent, useMemo, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, Receipt, Save } from 'lucide-react';
import { useCustomers, useProducts } from '../hooks/useBusinessData';
import { addMockInvoice } from '../mock/mockStore';
import { useQueryClient } from '@tanstack/react-query';
import { formatINRPrecise } from '../lib/format';

type LineItem = {
  productId: string;
  productName: string;
  quantity: number;
  unitPrice: number;
  discount: number;
};

const gstRate = 0.05; // 5% GST

export function InvoiceForm() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const { data: customers } = useCustomers();
  const { data: products } = useProducts();

  const preselectedCustId = searchParams.get('customer_id') ?? '';
  const [customerId, setCustomerId] = useState(preselectedCustId);
  const [customCustomerName, setCustomCustomerName] = useState(searchParams.get('customer_name') ?? '');
  const [invoiceType, setInvoiceType] = useState<'SALE' | 'PURCHASE'>('SALE');
  const [paymentMethod, setPaymentMethod] = useState<'UPI' | 'CASH' | 'CARD' | 'CREDIT'>('UPI');
  const [invoiceStatus, setInvoiceStatus] = useState<'CONFIRMED' | 'DRAFT'>('CONFIRMED');

  const [items, setItems] = useState<LineItem[]>([
    { productId: 'prod-001', productName: 'Fortune Sunlite Refined Sunflower Oil 1L', quantity: 10, unitPrice: 145, discount: 0 },
  ]);

  const totals = useMemo(() => {
    const subtotal = items.reduce(
      (sum, item) => sum + Math.max(item.quantity * item.unitPrice - item.discount, 0),
      0,
    );
    const tax = subtotal * gstRate;
    return { subtotal, tax, total: subtotal + tax };
  }, [items]);

  const handleProductSelect = (index: number, selectedProdId: string) => {
    const prod = products?.find((p) => p.id === selectedProdId);
    if (!prod) return;

    setItems((curr) =>
      curr.map((item, i) =>
        i === index
          ? {
              ...item,
              productId: prod.id,
              productName: prod.name,
              unitPrice: invoiceType === 'SALE' ? prod.selling_price : (prod.cost_price ?? prod.selling_price * 0.8),
            }
          : item,
      ),
    );
  };

  const handleAddItem = () => {
    const firstProd = products?.[0];
    setItems((curr) => [
      ...curr,
      {
        productId: firstProd?.id ?? `prod-${Date.now()}`,
        productName: firstProd?.name ?? 'Custom Item',
        quantity: 1,
        unitPrice: firstProd?.selling_price ?? 100,
        discount: 0,
      },
    ]);
  };

  const handleRemoveItem = (index: number) => {
    if (items.length > 1) {
      setItems((curr) => curr.filter((_, i) => i !== index));
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const invoiceNumber = `INV-2026-${Math.floor(100 + Math.random() * 900)}`;
    const isPaid = invoiceStatus === 'CONFIRMED' && paymentMethod !== 'CREDIT';

    const newInvoice = addMockInvoice({
      invoice_number: invoiceNumber,
      business_id: 'biz-001',
      customer_id: customerId || null,
      type: invoiceType,
      subtotal: Math.round(totals.subtotal * 100) / 100,
      tax_amount: Math.round(totals.tax * 100) / 100,
      discount_amount: items.reduce((s, i) => s + i.discount, 0),
      total_amount: Math.round(totals.total * 100) / 100,
      paid_amount: isPaid ? Math.round(totals.total * 100) / 100 : 0,
      status: invoiceStatus,
      payment_method: isPaid ? paymentMethod : null,
      items: items.map((it, idx) => ({
        id: `item-new-${idx}-${Date.now().toString(36)}`,
        product_id: it.productId,
        quantity: it.quantity,
        unit_price: it.unitPrice,
        discount: it.discount,
        line_total: Math.round((it.quantity * it.unitPrice - it.discount) * 100) / 100,
      })),
    });

    queryClient.invalidateQueries({ queryKey: ['invoices'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['products'] });

    navigate(`/app/invoices/${newInvoice.id}`);
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <div className="flex items-center justify-between">
        <Link to="/app/invoices" className="inline-flex items-center gap-1.5 text-sm font-medium text-navy hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to Invoices
        </Link>
      </div>

      <form onSubmit={handleSubmit} className="rounded-lg border border-rule bg-canvas-raised p-6 sm:p-8 space-y-6">
        {/* Title */}
        <div className="border-b border-rule pb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Billing Entry (नया बिल बनाएं)
            </span>
            <h1 className="text-2xl font-bold text-ink mt-0.5">New Tax Invoice</h1>
            <p className="text-xs text-ink-soft">
              Generate a digital invoice for sales or inventory stock purchase.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-md bg-navy-tint px-3 py-1.5 text-xs font-semibold text-navy">
            <Receipt className="h-4 w-4" />
            <span>5% MSME GST Ready</span>
          </div>
        </div>

        {/* Invoice Metadata */}
        <div className="grid gap-4 sm:grid-cols-3">
          {/* Invoice Type */}
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Invoice Type</label>
            <select
              value={invoiceType}
              onChange={(e) => setInvoiceType(e.target.value as 'SALE' | 'PURCHASE')}
              className="mt-1.5 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-navy"
            >
              <option value="SALE">Sale (बिक्री / Credit)</option>
              <option value="PURCHASE">Purchase (खरीद / Debit)</option>
            </select>
          </div>

          {/* Customer / Supplier */}
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Customer Account (ग्राहक)
            </label>
            <select
              value={customerId}
              onChange={(e) => {
                setCustomerId(e.target.value);
                const found = customers?.find((c) => c.id === e.target.value);
                if (found) setCustomCustomerName(found.name);
              }}
              className="mt-1.5 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-navy"
            >
              <option value="">-- Walk-in / Custom Customer --</option>
              {customers?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          {/* Payment Method */}
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Payment Method</label>
            <select
              value={paymentMethod}
              onChange={(e) => setPaymentMethod(e.target.value as 'UPI' | 'CASH' | 'CARD' | 'CREDIT')}
              className="mt-1.5 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-navy"
            >
              <option value="UPI">UPI (Google Pay / PhonePe / Paytm)</option>
              <option value="CASH">Cash (नकद)</option>
              <option value="CARD">Debit / Credit Card</option>
              <option value="CREDIT">Credit (उधारी / Khata)</option>
            </select>
          </div>
        </div>

        {/* If custom customer name */}
        {!customerId && (
          <div>
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Customer Name / Mobile (ग्राहक का नाम)
            </label>
            <input
              value={customCustomerName}
              onChange={(e) => setCustomCustomerName(e.target.value)}
              placeholder="e.g. Ramesh Kumar or 9820011223"
              className="mt-1.5 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-navy"
            />
          </div>
        )}

        {/* Line Items Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-soft">
              Line Items (सामान की सूची)
            </h3>
            <button
              type="button"
              onClick={handleAddItem}
              className="inline-flex items-center gap-1 text-xs font-semibold text-navy hover:underline"
            >
              <Plus className="h-3.5 w-3.5" /> Add another item
            </button>
          </div>

          <div className="space-y-3">
            {items.map((item, index) => {
              const lineTotal = Math.max(item.quantity * item.unitPrice - item.discount, 0);
              return (
                <div
                  key={index}
                  className="grid gap-3 rounded-md border border-rule bg-canvas-sunk p-3.5 sm:grid-cols-[2.5fr_1fr_1.2fr_1fr_1fr_auto] items-end"
                >
                  <div>
                    <label className="text-[11px] font-semibold text-ink-soft">Select Item</label>
                    <select
                      value={item.productId}
                      onChange={(e) => handleProductSelect(index, e.target.value)}
                      className="mt-1 w-full rounded border border-rule bg-canvas px-2.5 py-1.5 text-xs text-ink outline-none focus:border-navy"
                    >
                      {products?.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({formatINRPrecise(p.selling_price)})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-ink-soft">Qty</label>
                    <input
                      type="number"
                      min="1"
                      value={item.quantity}
                      onChange={(e) =>
                        setItems((curr) =>
                          curr.map((it, i) => (i === index ? { ...it, quantity: Number(e.target.value) || 1 } : it)),
                        )
                      }
                      className="num mt-1 w-full rounded border border-rule bg-canvas px-2.5 py-1.5 text-xs text-ink outline-none focus:border-navy"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-ink-soft">Rate (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={item.unitPrice}
                      onChange={(e) =>
                        setItems((curr) =>
                          curr.map((it, i) => (i === index ? { ...it, unitPrice: Number(e.target.value) || 0 } : it)),
                        )
                      }
                      className="num mt-1 w-full rounded border border-rule bg-canvas px-2.5 py-1.5 text-xs text-ink outline-none focus:border-navy"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-ink-soft">Discount (₹)</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={item.discount}
                      onChange={(e) =>
                        setItems((curr) =>
                          curr.map((it, i) => (i === index ? { ...it, discount: Number(e.target.value) || 0 } : it)),
                        )
                      }
                      className="num mt-1 w-full rounded border border-rule bg-canvas px-2.5 py-1.5 text-xs text-ink outline-none focus:border-navy"
                    />
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-ink-soft">Line Total</label>
                    <p className="num mt-2 text-xs font-semibold text-ink">{formatINRPrecise(lineTotal)}</p>
                  </div>

                  <div>
                    <button
                      type="button"
                      disabled={items.length <= 1}
                      onClick={() => handleRemoveItem(index)}
                      className="rounded p-1.5 text-ink-faint hover:text-due disabled:opacity-30"
                      title="Remove item"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Calculation summary and submission */}
        <div className="flex flex-col sm:flex-row justify-between items-start gap-6 border-t border-rule pt-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Initial Status</label>
            <div className="flex gap-4 text-xs font-medium text-ink">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="status"
                  value="CONFIRMED"
                  checked={invoiceStatus === 'CONFIRMED'}
                  onChange={() => setInvoiceStatus('CONFIRMED')}
                />
                <span>Confirm & Issue Bill</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="status"
                  value="DRAFT"
                  checked={invoiceStatus === 'DRAFT'}
                  onChange={() => setInvoiceStatus('DRAFT')}
                />
                <span>Save as Draft</span>
              </label>
            </div>
          </div>

          <div className="w-full sm:w-72 space-y-2 text-sm">
            <div className="flex justify-between text-ink-soft">
              <span>Subtotal:</span>
              <span className="num font-medium text-ink">{formatINRPrecise(totals.subtotal)}</span>
            </div>
            <div className="flex justify-between text-ink-soft">
              <span>GST (5%):</span>
              <span className="num font-medium text-ink">{formatINRPrecise(totals.tax)}</span>
            </div>
            <div className="flex justify-between border-t border-rule pt-2 text-base font-bold text-ink">
              <span>Total Amount:</span>
              <span className="num text-navy">{formatINRPrecise(totals.total)}</span>
            </div>

            <button
              type="submit"
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-md bg-navy px-4 py-2.5 font-semibold text-white hover:bg-navy-dark shadow-sm"
            >
              <Save className="h-4 w-4" />
              <span>{invoiceStatus === 'CONFIRMED' ? 'Create & Confirm Invoice' : 'Save Invoice Draft'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}