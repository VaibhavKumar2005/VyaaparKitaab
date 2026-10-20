const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const inrPrecise = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** ₹24,850 — Indian digit grouping (lakh/crore aware). */
export const formatINR = (value: number) => inr.format(value);

/** ₹24,850.50 — for invoices and tables where paise matter. */
export const formatINRPrecise = (value: number) => inrPrecise.format(value);

export const formatDate = (value: string | Date) =>
  new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });

