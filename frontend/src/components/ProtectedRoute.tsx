import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export function ProtectedRoute({
  children,
  requiredRole,
}: {
  children: React.ReactNode;
  requiredRole?: 'STORE_OWNER' | 'CUSTOMER';
}) {
  const { token, isDemo, user } = useAuth();
  const location = useLocation();

  if (!token && !isDemo) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  // Prevent customer from accessing store-owner monetary ledger screens
  if (requiredRole === 'STORE_OWNER' && user?.role === 'CUSTOMER') {
    return <Navigate to="/portal/bills" replace />;
  }

  return <>{children}</>;
}