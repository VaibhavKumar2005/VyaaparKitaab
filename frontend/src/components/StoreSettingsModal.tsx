import { FormEvent, useEffect, useState } from 'react';
import { Building2, CheckCircle2, QrCode, X } from 'lucide-react';
import { type Business, useUpdateBusiness } from '../hooks/useBusinessData';

export function StoreSettingsModal({
  open,
  business,
  onClose,
}: {
  open: boolean;
  business: Business | undefined;
  onClose: () => void;
}) {
  const updateBusiness = useUpdateBusiness();
  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [address, setAddress] = useState('');
  const [phone, setPhone] = useState('');
  const [upiVpa, setUpiVpa] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (open && business) {
      setName(business.name ?? '');
      setGstin(business.gstin ?? '');
      setAddress(business.address ?? '');
      setPhone(business.phone ?? '');
      setUpiVpa(business.upi_vpa ?? '');
      setError(null);
      setSaved(false);
    }
  }, [open, business]);

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!business) {
      setError('No business profile found for this account.');
      return;
    }
    if (!name.trim()) {
      setError('Store name cannot be empty.');
      return;
    }
    setError(null);
    setSaved(false);
    try {
      await updateBusiness.mutateAsync({
        id: business.id,
        name: name.trim(),
        gstin: gstin.trim().toUpperCase() || null,
        address: address.trim() || null,
        phone: phone.trim() || null,
        upi_vpa: upiVpa.trim() || null,
      });
      setSaved(true);
      setTimeout(() => onClose(), 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save store settings');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-label="Store Settings"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-lg rounded-xl border border-rule bg-canvas-raised p-6 shadow-2xl space-y-4"
      >
        <div className="flex items-center justify-between border-b border-rule pb-3">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-navy" />
            <div>
              <h2 className="text-base font-bold text-ink">Store Profile &amp; UPI QR Settings</h2>
              <p className="text-[11px] text-ink-soft">
                Printed on every GST tax invoice, Customer Passbook bill, and dynamic UPI QR code.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-ink-soft hover:bg-canvas-sunk"
            aria-label="Close settings"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {!business ? (
          <p className="rounded-md bg-due-tint p-3 text-xs text-due">
            No store profile is attached to this login yet. Register a Merchant Store Owner account to create one.
          </p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold text-ink">Shop / Trade Name *</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Nisha Electronics"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink">15-Digit GSTIN</label>
                <input
                  value={gstin}
                  maxLength={15}
                  onChange={(e) => setGstin(e.target.value.toUpperCase())}
                  placeholder="27AABCN1234E1Z5"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm font-mono uppercase outline-none focus:border-navy"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-ink">Registered Shop Address</label>
              <input
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Shop 12, Main Market, Pune"
                className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs font-semibold text-ink">Store Contact Phone</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="9876543210"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm outline-none focus:border-navy"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink flex items-center gap-1">
                  <QrCode className="h-3.5 w-3.5 text-navy" />
                  Merchant UPI ID (VPA)
                </label>
                <input
                  value={upiVpa}
                  onChange={(e) => setUpiVpa(e.target.value)}
                  placeholder="myshop@okaxis"
                  className="mt-1 w-full rounded-md border border-rule bg-canvas px-3 py-2 text-sm font-mono outline-none focus:border-navy"
                />
              </div>
            </div>

            {error && <p className="rounded-md bg-due-tint p-2.5 text-xs text-due">{error}</p>}
            {saved && (
              <p className="flex items-center gap-1.5 rounded-md bg-positive-tint p-2.5 text-xs font-semibold text-positive">
                <CheckCircle2 className="h-4 w-4" /> Store settings saved to PostgreSQL!
              </p>
            )}

            <div className="flex justify-end gap-2 border-t border-rule pt-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-rule px-3.5 py-2 text-xs font-semibold text-ink-soft hover:bg-canvas-sunk"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updateBusiness.isPending}
                className="rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark disabled:opacity-50"
              >
                {updateBusiness.isPending ? 'Saving…' : 'Save Store Profile'}
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}
