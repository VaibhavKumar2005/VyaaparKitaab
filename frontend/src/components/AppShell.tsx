import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Receipt, Users, Package, LogOut, Plus, RotateCcw, ShoppingBag } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { resetMockData } from '../mock/mockStore';
import { useQueryClient } from '@tanstack/react-query';

const links = [
  { to: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/app/invoices', label: 'Invoices', icon: Receipt },
  { to: '/app/customers', label: 'Customers', icon: Users },
  { to: '/app/products', label: 'Inventory', icon: Package },
  { to: '/portal/spending', label: 'Personal Spending', icon: ShoppingBag },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors',
    isActive ? 'bg-navy-tint text-navy' : 'text-ink-soft hover:bg-canvas-sunk hover:text-ink',
  ].join(' ');

export function AppShell() {
  const { user, logout, isDemo } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleResetData = () => {
    resetMockData();
    queryClient.invalidateQueries();
  };

  return (
    <div className="min-h-screen bg-canvas text-ink md:flex">
      <aside className="no-print hidden w-64 shrink-0 flex-col border-r border-rule bg-canvas-raised md:flex">
        <div className="px-5 py-5">
          <span className="font-display text-xl font-bold text-navy">VyaparKitaab</span>
          <p className="mt-0.5 text-xs text-ink-faint">Digital Bahi-Khata for MSMEs</p>
        </div>

        {isDemo && (
          <div className="mx-3 mb-3 rounded-md border border-navy/20 bg-navy-tint p-3 text-xs">
            <div className="flex items-center justify-between font-semibold text-navy">
              <span>⚡ Sample Store Data</span>
            </div>
            <p className="mt-1 text-[11px] text-ink-soft">
              Sharma Kirana & General Store (Kanpur Road, Lucknow)
            </p>
          </div>
        )}

        <nav className="flex-1 space-y-1 px-3" aria-label="Main">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={linkClass}>
              <Icon className="h-4 w-4" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-rule p-4">
          <p className="truncate text-xs font-semibold text-ink">{user?.email}</p>
          <div className="mt-2 flex items-center justify-between">
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-1.5 text-xs font-medium text-ink-soft hover:text-ink"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
            </button>
            {isDemo && (
              <button
                type="button"
                onClick={handleResetData}
                title="Reset test data to original state"
                className="flex items-center gap-1 text-[11px] text-navy hover:underline"
              >
                <RotateCcw className="h-3 w-3" /> Reset data
              </button>
            )}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-20 border-b border-rule bg-canvas-raised md:hidden">
          <div className="flex items-center justify-between px-4 py-3">
            <div>
              <span className="font-bold text-navy">VyaparKitaab</span>
              {isDemo && <span className="ml-2 text-[10px] font-semibold text-navy bg-navy-tint px-1.5 py-0.5 rounded">Sample Data</span>}
            </div>
            <button type="button" onClick={logout} aria-label="Sign out" className="p-2 text-ink-soft">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label="Main">
            {links.map(({ to, label }) => (
              <NavLink key={to} to={to} className={linkClass}>
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-8">
          <div className="no-print mb-6 flex flex-wrap items-center justify-between gap-3">
            {isDemo ? (
              <div className="flex items-center gap-2 rounded-md border border-rule bg-canvas-raised px-3 py-1.5 text-xs text-ink-soft">
                <span className="h-2 w-2 rounded-full bg-positive" />
                <span>Viewing <strong>Sharma Kirana Store</strong> test records</span>
                <button
                  type="button"
                  onClick={handleResetData}
                  className="ml-2 flex items-center gap-1 font-semibold text-navy hover:underline"
                >
                  <RotateCcw className="h-3 w-3" /> Reset
                </button>
              </div>
            ) : <div />}

            <button
              type="button"
              onClick={() => navigate('/app/invoices/new')}
              className="inline-flex items-center gap-1.5 rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white hover:bg-navy-dark"
            >
              <Plus className="h-4 w-4" aria-hidden /> New invoice
            </button>
          </div>
          <Outlet />
        </main>
      </div>
    </div>
  );
}