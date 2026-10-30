import { NavLink, Outlet, Link } from 'react-router-dom';
import { Receipt, PieChart, LogOut, ShieldCheck, ArrowLeft } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const links = [
  { to: '/portal/bills', label: 'My Store Bills & Receipts (मेरे बिल)', icon: Receipt },
  { to: '/portal/spending', label: 'Personal Spending & Cost Tracker (खर्च व वर्गीकरण)', icon: PieChart },
];

export function CustomerPortalShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-sans">
      {/* ─── Storey 1: SAP 60px Global Chrome Bar ─── */}
      <header className="no-print h-[60px] bg-chrome border-b border-rule px-4 sm:px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Link to="/" className="font-display text-lg font-bold text-ink tracking-tight">
            VyaparKitaab
          </Link>
          <span className="hidden sm:inline-block h-4 w-px bg-rule" />
          <span className="rounded bg-navy-tint px-2 py-0.5 text-xs font-semibold text-primary flex items-center gap-1">
            <ShieldCheck className="h-3.5 w-3.5" /> Customer Passbook
          </span>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/app/dashboard"
            className="hidden sm:flex items-center gap-1.5 text-xs text-primary font-medium hover:underline mr-2"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Store Merchant App
          </Link>

          <div className="text-right text-xs hidden md:block">
            <p className="font-medium text-ink">{user?.email ?? 'Customer'}</p>
            <p className="text-[11px] text-ink-soft">Verified Customer Account</p>
          </div>

          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-1.5 rounded-md border border-rule bg-white px-2.5 py-1.5 text-xs font-medium text-ink-nav hover:text-ink hover:bg-chrome transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      {/* ─── Storey 2: SAP Product Tab Rail ─── */}
      <nav
        className="no-print bg-white border-b border-rule px-4 sm:px-6 flex items-center justify-between shrink-0 overflow-x-auto"
        aria-label="Customer Navigation"
      >
        <div className="flex gap-1 -mb-px">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                  isActive
                    ? 'border-primary text-primary font-semibold'
                    : 'border-transparent text-ink-nav hover:text-ink hover:border-rule',
                ].join(' ')
              }
            >
              <Icon className="h-4 w-4" aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      {/* ─── Storey 3: Content Pane (White Canvas Ground) ─── */}
      <main className="flex-1 bg-white">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </div>
      </main>

      {/* ─── Footer ─── */}
      <footer className="no-print border-t border-rule bg-canvas-sunk py-3 px-6 text-xs text-ink-nav flex flex-wrap items-center justify-between gap-2">
        <span>© 2026 VyaparKitaab Customer Portal</span>
        <span>Verified Digital Receipts & UPI Payments</span>
      </footer>
    </div>
  );
}
