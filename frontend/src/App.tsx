import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { CustomerPortalShell } from './components/CustomerPortalShell';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';

const StoreDashboard = lazy(() =>
  import('./pages/StoreDashboard').then((m) => ({ default: m.StoreDashboard }))
);
const CustomerList = lazy(() =>
  import('./pages/CustomerList').then((m) => ({ default: m.CustomerList }))
);
const ProductList = lazy(() =>
  import('./pages/ProductList').then((m) => ({ default: m.ProductList }))
);
const InvoiceList = lazy(() =>
  import('./pages/InvoiceList').then((m) => ({ default: m.InvoiceList }))
);
const InvoiceForm = lazy(() =>
  import('./pages/InvoiceForm').then((m) => ({ default: m.InvoiceForm }))
);
const InvoiceDetail = lazy(() =>
  import('./pages/InvoiceDetail').then((m) => ({ default: m.InvoiceDetail }))
);
const CustomerBillsPage = lazy(() =>
  import('./pages/CustomerBillsPage').then((m) => ({ default: m.CustomerBillsPage }))
);
const CustomerDashboard = lazy(() =>
  import('./pages/CustomerDashboard').then((m) => ({ default: m.CustomerDashboard }))
);

export default function App() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-ink-soft">Loading workspace…</div>}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Store Owner Application (Full financial ledger & operations) */}
        <Route
          path="/app"
          element={
            <ProtectedRoute requiredRole="STORE_OWNER">
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<StoreDashboard />} />
          <Route path="customers" element={<CustomerList />} />
          <Route path="products" element={<ProductList />} />
          <Route path="invoices" element={<InvoiceList />} />
          <Route path="invoices/new" element={<InvoiceForm />} />
          <Route path="invoices/:id" element={<InvoiceDetail />} />
        </Route>

        {/* Separated Customer Portal (Strictly isolated from shop monetary data) */}
        <Route
          path="/portal"
          element={
            <ProtectedRoute requiredRole="CUSTOMER">
              <CustomerPortalShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="bills" replace />} />
          <Route path="bills" element={<CustomerBillsPage />} />
          <Route path="bills/:id" element={<InvoiceDetail />} />
          <Route path="spending" element={<CustomerDashboard />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}