import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Receipt,
  Users,
  Package,
  LogOut,
  Plus,
  RotateCcw,
  ShoppingBag,
  Database,
  SlidersHorizontal,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { resetMockData } from '../mock/mockStore';
import { useQueryClient } from '@tanstack/react-query';

const tabs = [
  { to: '/app/dashboard', label: 'Financial Dashboard', icon: LayoutDashboard },
  { to: '/app/invoices', label: 'Invoices & Billing', icon: Receipt },
  { to: '/app/customers', label: 'Customers & Udhaar', icon: Users },
  { to: '/app/products', label: 'Inventory Stock', icon: Package },
  { to: '/portal/bills', label: 'Customer Passbook', icon: ShoppingBag },
];

export function AppShell() {
  const { user, logout, isDemo, enableDemo, disableDemo } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleResetData = () => {
    resetMockData();
    queryClient.invalidateQueries();
  };

  const handleToggleMode = () => {
    if (isDemo) {
      disableDemo();
    } else {
      enableDemo();
    }
    queryClient.invalidateQueries();
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col font-sans">
      {/* ─── Storey 1: SAP 60px Global Chrome Bar ─── */}
      <header className="no-print h-[60px] bg-chrome border-b border-rule px-4 sm:px-6 flex items-center justify-between shrink-0">
        {/* Brand identity */}
        <div className="flex items-center gap-3">
          <span className="font-display text-lg font-bold text-ink tracking-tight">VyaparKitaab</span>
          <span className="hidden sm:inline-block h-4 w-px bg-rule" />
          <span className="hidden sm:inline-block text-xs text-ink-nav">
            MSME Digital Bahi-Khata & Operating System
          </span>
        </div>

        {/* Real-time backend vs Demo switcher */}
        <div className="flex items-center gap-2">
          {!isDemo ? (
            <div className="flex items-center gap-2 rounded-md border border-rule bg-white px-3 py-1.5 text-xs">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-positive opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-positive" />
              </span>
              <span className="font-semibold text-ink">🟢 Live PostgreSQL Database</span>
              <button
                type="button"
                onClick={handleToggleMode}
                title="Switch to offline sample store"
                className="ml-2 text-[11px] text-primary font-medium hover:underline flex items-center gap-1"
              >
                <SlidersHorizontal className="h-3 w-3" /> Sample Demo
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-900">
              <Database className="h-3.5 w-3.5 text-amber-700" />
              <span>⚡ <strong>Sample Store Data</strong> (Offline Sandbox)</span>
              <button
                type="button"
                onClick={handleToggleMode}
                title="Connect to live PostgreSQL backend"
                className="ml-2 font-semibold text-primary hover:underline"
              >
                Connect Live DB
              </button>
              <button
                type="button"
                onClick={handleResetData}
                title="Reset sample data"
                className="ml-1 text-[11px] text-ink-soft hover:underline flex items-center gap-0.5"
              >
                <RotateCcw className="h-3 w-3" /> Reset
              </button>
            </div>
          )}
        </div>

        {/* User Account & Actions */}
        <div className="flex items-center gap-3">
          <div className="hidden md:block text-right text-xs">
            <p className="font-medium text-ink truncate max-w-[200px]">{user?.email ?? 'Merchant'}</p>
            <p className="text-[11px] text-ink-soft">
              {!isDemo ? 'Store Owner (Sharma Kirana)' : 'Demo Sandbox Session'}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-1.5 rounded-md border border-rule bg-white px-2.5 py-1.5 text-xs font-medium text-ink-nav hover:text-ink hover:bg-chrome transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </header>

      {/* ─── Storey 2: SAP Product Tab Rail ─── */}
      <nav
        className="no-print bg-white border-b border-rule px-4 sm:px-6 flex items-center justify-between shrink-0 overflow-x-auto"
        aria-label="Product Navigation"
      >
        <div className="flex gap-1 -mb-px">
          {tabs.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  'flex items-center gap-2 px-3.5 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
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

        <div className="py-2 pl-4 shrink-0">
          <button
            type="button"
            onClick={() => navigate('/app/invoices/new')}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-1.5 text-xs sm:text-sm font-semibold text-white hover:bg-primary-deep shadow-none transition-colors"
          >
            <Plus className="h-4 w-4" aria-hidden />
            <span>New Invoice</span>
          </button>
        </div>
      </nav>

      {/* ─── Storey 3: Content Pane (White Canvas Ground) ─── */}
      <main className="flex-1 bg-white">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </div>
      </main>

      {/* ─── Enterprise Quiet Footer ─── */}
      <footer className="no-print border-t border-rule bg-canvas-sunk py-3 px-6 text-xs text-ink-nav flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span>© 2026 VyaparKitaab MSME Enterprise</span>
          <span>•</span>
          <span>Dual Dashboard Architecture (Store B2B + Retail Customer Bahi-Khata)</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px]">
          <span>FastAPI</span>
          <span>•</span>
          <span>PostgreSQL 17</span>
          <span>•</span>
          <span>Real-time SSE Stream</span>
        </div>
      </footer>
    </div>
  );
}
