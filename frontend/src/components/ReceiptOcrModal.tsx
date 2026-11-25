import { FormEvent, useRef, useState } from 'react';
import { CheckCircle2, FileText, ScanLine, Upload, X } from 'lucide-react';
import {
  ocrInvoiceApi,
  type OcrCapabilities,
  useCreatePersonalPurchase,
  useOcrCapabilities,
} from '../hooks/usePurchases';
import { formatINRPrecise } from '../lib/format';
import { TAXONOMY_CATEGORIES } from '../lib/taxonomy';

export const OCR_MODE_OPTIONS = [
  { id: 'auto', label: 'Auto (Eng + Hin)' },
  { id: 'hin', label: 'Hindi Printed' },
  { id: 'handwriting', label: 'Hindi Handwriting' },
] as const;

export type OcrMode = (typeof OCR_MODE_OPTIONS)[number]['id'];

export function getOcrCapabilityStatusText(caps?: OcrCapabilities): string | null {
  if (!caps) return null;
  if (caps.handwriting_vision_ready) return 'Hindi Handwriting AI Ready';
  if (caps.hindi_offline_ready) return 'Offline Hindi (hin+eng) Ready';
  return 'Local Tesseract (English) · Add tesseract-ocr-hin or GEMINI_API_KEY for Hindi';
}

export function ReceiptOcrModal({
  open,
  businessId,
  onClose,
}: {
  open: boolean;
  businessId?: string;
  onClose: () => void;
}) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const { data: caps } = useOcrCapabilities();
  const createPurchase = useCreatePersonalPurchase();

  const [ocrMode, setOcrMode] = useState<OcrMode>('auto');
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const [vendor, setVendor] = useState('');
  const [billNo, setBillNo] = useState('');
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('Shopping');
  const [paymentMethod, setPaymentMethod] = useState('Cash');
  const [itemsNote, setItemsNote] = useState('');
  const [rawText, setRawText] = useState('');

  if (!open) return null;

  const capText = getOcrCapabilityStatusText(caps);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setScanning(true);
    setScanError(null);
    setSavedMsg(null);
    try {
      const res = await ocrInvoiceApi(file, {
        lang: ocrMode === 'auto' ? 'auto' : 'hin+eng',
        handwriting: ocrMode === 'handwriting',
      });
      setVendor(res.marketplace || 'Store Supplier');
      setBillNo(res.order_id || `BILL-${Date.now().toString().slice(-6)}`);
      setAmount(res.amount != null ? String(res.amount) : '');
      setCategory(res.category || 'Shopping');
      setPaymentMethod(res.payment_method || 'Cash');
      setItemsNote(res.items_summary || '');
      setRawText(res.extracted_text || '');
    } catch (err) {
      setScanError(err instanceof Error ? err.message : 'Unable to scan bill image.');
    } finally {
      setScanning(false);
    }
  };

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setScanError(null);
    const numAmt = Number(amount);
    if (!vendor.trim() || !Number.isFinite(numAmt) || numAmt <= 0) {
      setScanError('Enter a valid vendor/store name and total amount.');
      return;
    }
    try {
      await createPurchase.mutateAsync({
        business_id: businessId,
        marketplace: vendor.trim(),
        order_id: billNo.trim() || `BILL-${Date.now().toString().slice(-6)}`,
        amount: numAmt,
        category,
        payment_method: paymentMethod,
        items_note: itemsNote.trim() || undefined,
      });
      setSavedMsg(`Saved ${vendor.trim()} (${formatINRPrecise(numAmt)}) to ledger.`);
      setTimeout(() => {
        setSavedMsg(null);
        onClose();
      }, 900);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : 'Unable to save scanned bill.');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-label="Scan Hindi or GST Bill"
    >
      <div className="w-full max-w-xl max-h-[92vh] overflow-y-auto rounded-xl border border-rule bg-canvas-raised p-5 sm:p-6 shadow-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-rule pb-3">
          <div className="flex items-center gap-2">
            <ScanLine className="h-5 w-5 text-navy" />
            <div>
              <h2 className="text-base font-bold text-ink">Scan Purchase / Hindi Bill (OCR)</h2>
              <p className="text-[11px] text-ink-soft">
                Upload a GST supplier invoice, printed Hindi receipt, or handwritten kirana parcha.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-ink-soft hover:bg-canvas-sunk"
            aria-label="Close OCR scanner"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="rounded-lg border border-rule bg-canvas p-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-ink">Bill Script / Mode</span>
            {capText && <span className="text-[10px] text-ink-soft">{capText}</span>}
          </div>
          <div className="grid grid-cols-3 gap-1.5 text-[11px]">
            {OCR_MODE_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setOcrMode(opt.id)}
                className={`rounded-md border px-2 py-1.5 font-semibold transition-colors ${
                  ocrMode === opt.id
                    ? 'border-navy bg-navy text-white'
                    : 'border-rule bg-canvas-raised text-ink-soft hover:text-ink'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/tiff,image/bmp,application/pdf,.pdf"
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border-2 border-dashed border-rule bg-canvas p-4">
          <div className="flex items-center gap-2.5 text-xs text-ink-soft">
            <FileText className="h-5 w-5 text-navy shrink-0" />
            <span>Processed in memory (image &amp; raw text are never saved).</span>
          </div>
          <button
            type="button"
            disabled={scanning}
            onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-md bg-navy px-3.5 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
          >
            <Upload className="h-3.5 w-3.5" />
            {scanning ? 'Extracting Text…' : 'Select Bill Image / PDF'}
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-3 border-t border-rule pt-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-xs font-semibold text-ink">Vendor / Store Name *</label>
              <input
                required
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                placeholder="e.g. Sharma Kirana / Metro Wholesale"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-1.5 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Bill / UTR No.</label>
              <input
                value={billNo}
                onChange={(e) => setBillNo(e.target.value)}
                placeholder="INV-2026-01"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-1.5 text-sm outline-none focus:border-navy"
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="text-xs font-semibold text-ink">Total Amount (₹) *</label>
              <input
                required
                type="number"
                step="0.01"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="num mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-1.5 text-sm outline-none focus:border-navy"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-2.5 py-1.5 text-sm outline-none focus:border-navy"
              >
                {TAXONOMY_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-ink">Payment Method</label>
              <input
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
                placeholder="UPI / Cash"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-1.5 text-sm outline-none focus:border-navy"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-ink">Extracted Items / Notes</label>
            <input
              value={itemsNote}
              onChange={(e) => setItemsNote(e.target.value)}
              placeholder="e.g. Atta 5kg, Sugar 2kg"
              className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-1.5 text-sm outline-none focus:border-navy"
            />
          </div>

          {rawText && (
            <details className="rounded-md border border-rule bg-canvas p-2.5 text-xs">
              <summary className="cursor-pointer font-semibold text-ink-soft">
                View raw OCR text ({rawText.length} chars)
              </summary>
              <pre className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] text-ink">
                {rawText}
              </pre>
            </details>
          )}

          {scanError && <p className="rounded-md bg-due-tint p-2.5 text-xs text-due">{scanError}</p>}
          {savedMsg && (
            <p className="flex items-center gap-1.5 rounded-md bg-emerald-50 p-2.5 text-xs font-semibold text-emerald-800">
              <CheckCircle2 className="h-4 w-4" /> {savedMsg}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-rule px-3.5 py-2 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createPurchase.isPending}
              className="rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
            >
              {createPurchase.isPending ? 'Saving…' : 'Save to Store Expenses'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
