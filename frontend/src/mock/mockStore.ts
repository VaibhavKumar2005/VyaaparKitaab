import {
  mockBusiness,
  mockCustomers,
  mockInvoices,
  mockProducts,
  mockStoreDashboard,
} from './mockData';
import type { Business, Customer, Product } from '../hooks/useBusinessData';
import type { Invoice, PaymentOrderData } from '../hooks/useInvoices';
import type { StoreDashboardData } from '../hooks/useDashboard';

const DEMO_STORAGE_KEY = 'vyaaparkitaab_demo_mode';
const INVOICES_STORAGE_KEY = 'vyaaparkitaab_mock_invoices';
const PRODUCTS_STORAGE_KEY = 'vyaaparkitaab_mock_products';
const CUSTOMERS_STORAGE_KEY = 'vyaaparkitaab_mock_customers';

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return true;
  const stored = localStorage.getItem(DEMO_STORAGE_KEY);
  if (stored !== null) {
    return stored === 'true';
  }
  // Default to true if no auth token is present, allowing immediate testing
  return !localStorage.getItem('token');
}

export function setDemoMode(enabled: boolean): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(DEMO_STORAGE_KEY, enabled ? 'true' : 'false');
  window.dispatchEvent(new Event('vyaapar_demo_mode_changed'));
}

function loadFromStorage<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function saveToStorage<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore storage quota errors
  }
}

// In-memory / storage sync
let storedInvoices: Invoice[] = loadFromStorage<Invoice[]>(INVOICES_STORAGE_KEY, mockInvoices);
let storedProducts: Product[] = loadFromStorage<Product[]>(PRODUCTS_STORAGE_KEY, mockProducts);
let storedCustomers: Customer[] = loadFromStorage<Customer[]>(CUSTOMERS_STORAGE_KEY, mockCustomers);

export function getMockBusinesses(): Business[] {
  return [mockBusiness];
}

export function getMockCustomers(): Customer[] {
  return storedCustomers;
}

export function getMockProducts(): Product[] {
  return storedProducts;
}

export function getMockInvoices(): Invoice[] {
  return storedInvoices;
}

export function getMockInvoice(id: string | undefined): Invoice | undefined {
  if (!id) return undefined;
  return storedInvoices.find((i) => i.id === id || i.invoice_number === id);
}

export function updateMockInvoiceStatus(id: string, status: string): Invoice {
  storedInvoices = storedInvoices.map((inv) => {
    if (inv.id === id || inv.invoice_number === id) {
      const updated = { ...inv, status };
      if (status === 'PAID') {
        updated.paid_amount = updated.total_amount;
      }
      return updated;
    }
    return inv;
  });
  saveToStorage(INVOICES_STORAGE_KEY, storedInvoices);
  return getMockInvoice(id)!;
}

export function addMockInvoice(newInv: Omit<Invoice, 'id' | 'created_at'>): Invoice {
  const invoice: Invoice = {
    ...newInv,
    id: `inv-${Date.now().toString(36)}`,
    created_at: new Date().toISOString(),
  };
  storedInvoices = [invoice, ...storedInvoices];
  saveToStorage(INVOICES_STORAGE_KEY, storedInvoices);

  // Automatically deduct or replenish product stock for confirmed/paid bills
  if (invoice.status === 'CONFIRMED' || invoice.status === 'PAID') {
    const qtyByProd = new Map<string, number>();
    for (const item of invoice.items) {
      qtyByProd.set(item.product_id, (qtyByProd.get(item.product_id) ?? 0) + item.quantity);
    }
    storedProducts = storedProducts.map((prod) => {
      const delta = qtyByProd.get(prod.id);
      if (!delta) return prod;
      const updatedStock =
        invoice.type === 'SALE'
          ? Math.max(0, prod.stock_qty - delta)
          : prod.stock_qty + delta;
      return { ...prod, stock_qty: updatedStock };
    });
    saveToStorage(PRODUCTS_STORAGE_KEY, storedProducts);
  }

  return invoice;
}

export function simulateMockPayment(
  invoiceId: string,
  method: 'UPI' | 'CASH' = 'UPI',
  amountPaid?: number,
): { success: boolean; message: string; invoice_status: string } {
  let finalStatus = 'PAID';
  storedInvoices = storedInvoices.map((inv) => {
    if (inv.id === invoiceId || inv.invoice_number === invoiceId) {
      const newPaid =
        amountPaid !== undefined
          ? Math.min(inv.total_amount, inv.paid_amount + Math.max(0, amountPaid))
          : inv.total_amount;
      finalStatus = newPaid >= inv.total_amount ? 'PAID' : 'CONFIRMED';
      return {
        ...inv,
        status: finalStatus,
        paid_amount: newPaid,
        payment_method: method,
      };
    }
    return inv;
  });
  saveToStorage(INVOICES_STORAGE_KEY, storedInvoices);
  return {
    success: true,
    message:
      method === 'CASH'
        ? '₹ नकद भुगतान दर्ज किया गया (Cash payment recorded in ledger)'
        : '₹ पेमेंट सफलतापूर्वक जमा हुआ (UPI Payment verified and settled)',
    invoice_status: finalStatus,
  };
}

export function createMockPaymentOrder(invoiceId: string, customAmount?: number): PaymentOrderData {
  const inv = getMockInvoice(invoiceId);
  const amount = customAmount ?? (inv ? inv.total_amount - inv.paid_amount : 1000);
  return {
    order_id: `order_mock_${Date.now().toString(36)}`,
    amount,
    currency: 'INR',
    receipt: `rcpt_${Date.now().toString(36)}`,
    key_id: 'rzp_test_VyaparDemo2026',
    gateway: 'razorpay',
    upi_intent: `upi://pay?pa=sharmakirana@icici&pn=Sharma+Kirana+Store&am=${amount}&cu=INR&tn=Invoice+${inv?.invoice_number ?? 'Payment'}`,
  };
}

export function getMockStoreDashboard(): StoreDashboardData {
  const invoices = getMockInvoices();
  const sales = invoices.filter((i) => i.type === 'SALE');
  const paidSales = sales.reduce((sum, i) => sum + i.paid_amount, 0);
  const pendingInvoices = invoices.filter((i) => i.status === 'DRAFT').length;
  const lowStock = storedProducts.filter((p) => p.stock_qty <= 5).length;

  return {
    ...mockStoreDashboard,
    todayRevenue: paidSales,
    totalCustomers: storedCustomers.length,
    lowStockItems: lowStock,
    pendingInvoices,
    recentTransactions: invoices.slice(0, 8).map((inv) => ({
      invoice_number: inv.invoice_number,
      total_amount: inv.total_amount,
      status: inv.status,
      created_at: inv.created_at,
    })),
  };
}

export function resetMockData(): void {
  storedInvoices = mockInvoices;
  storedProducts = mockProducts;
  storedCustomers = mockCustomers;
  if (typeof window !== 'undefined') {
    localStorage.removeItem(INVOICES_STORAGE_KEY);
    localStorage.removeItem(PRODUCTS_STORAGE_KEY);
    localStorage.removeItem(CUSTOMERS_STORAGE_KEY);
  }
}

