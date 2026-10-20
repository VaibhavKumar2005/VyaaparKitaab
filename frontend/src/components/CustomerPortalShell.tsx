import { NavLink, Outlet, Link } from 'react-router-dom';
import { Receipt, PieChart, LogOut, ShieldCheck } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const links = [
  { to: '/portal/bills', label: 'My Bills & Receipts (मेरे बिल)', icon: Receipt },
  { to: '/portal/spending', label: 'Spending Insights (खर्च विश्लेषण)', icon: PieChart },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center gap-2.5 rounded-md px-3.5 py-2 text-sm font-medium transition-colors',
    isActive ? 'bg-navy-tint text-navy font-semibold' : 'text-ink-soft hover:bg-canvas-sunk hover:text-ink',
  ].join(' ');

export function CustomerPortalShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Top Banking-Style Navigation Bar */}
      <header className="sticky top-0 z-20 border-b border-rule bg-canvas-raised">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Link to="/portal/bills" className="font-display text-lg font-bold text-navy">
              VyaparKitaab
            </Link>
            <span className="rounded-full bg-navy-tint px-2.5 py-0.5 text-xs font-semibold text-navy flex items-center gap-1">
              <ShieldCheck className="h-3.5 w-3.5" /> Customer Portal
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="hidden sm:block text-right">
              <p className="font-medium text-ink">{user?.email ?? 'customer@vyapaarkitaab.in'}</p>
              <p className="text-ink-faint">Verified Customer Account</p>
            </div>
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-1.5 rounded-md border border-rule px-2.5 py-1.5 text-xs font-medium text-ink-soft hover:bg-canvas-sunk hover:text-ink"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign out</span>
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="border-t border-rule bg-canvas-sunk">
          <div className="mx-auto flex max-w-5xl gap-2 px-4 sm:px-6">
            {links.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className={linkClass}>
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}

