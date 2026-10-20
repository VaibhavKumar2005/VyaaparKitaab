import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { CustomerPortalShell } from './components/CustomerPortalShell';
import { ProtectedRoute } from './components/ProtectedRoute';
import { CustomerBillsPage } from './pages/CustomerBillsPage';
import { CustomerDashboard } from './pages/CustomerDashboard';
import { CustomerList } from './pages/CustomerList';
import { DashboardRouter } from './pages/DashboardRouter';
import { InvoiceDetail } from './pages/InvoiceDetail';
import { InvoiceForm } from './pages/InvoiceForm';
import { InvoiceList } from './pages/InvoiceList';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { ProductList } from './pages/ProductList';
import { RegisterPage } from './pages/RegisterPage';

export default function App() {
  return (
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
        <Route path="dashboard" element={<DashboardRouter />} />
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
  );
}