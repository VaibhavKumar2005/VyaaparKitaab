import { useState } from 'react';
import { NavLink, Outlet, Link, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Receipt,
  Users,
  Package,
  Truck,
  LogOut,
  Plus,
  RotateCcw,
  ShoppingBag,
  Database,
  Settings,
  SlidersHorizontal,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useBusinesses } from '../hooks/useBusinessData';
import { resetMockData } from '../mock/mockStore';
import { useQueryClient } from '@tanstack/react-query';
import { StoreSettingsModal } from './StoreSettingsModal';

const tabs = [
  { to: '/app/dashboard', label: 'Financial Dashboard', icon: LayoutDashboard },
  { to: '/app/invoices', label: 'Invoices & Billing', icon: Receipt },
  { to: '/app/customers', label: 'Customers & Udhaar', icon: Users },
  { to: '/app/products', label: 'Inventory Stock', icon: Package },
  { to: '/app/suppliers', label: 'Suppliers', icon: Truck },
];

export function AppShell() {
  const { user, logout, isDemo, enableDemo, disableDemo } = useAuth();
  const { data: businesses } = useBusinesses();
  const primaryBusiness = businesses?.[0];
  const primaryStoreName = primaryBusiness?.name ?? 'Store Owner';
  const [showSettings, setShowSettings] = useState(false);
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
      <header className="no-print h-[60px] bg-chrome border-b border-rule px-3 sm:px-6 flex items-center justify-between gap-2 shrink-0">
        {/* Brand identity */}
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-display text-base sm:text-lg font-bold text-ink tracking-tight truncate">VyaparKitaab</span>
          <span className="hidden lg:inline-block h-4 w-px bg-rule" />
          <span className="hidden lg:inline-block text-xs text-ink-nav">
            MSME Digital Bahi-Khata & Operating System
          </span>
        </div>

        {/* Real-time backend vs Demo switcher */}
        <div className="flex items-center gap-1.5 shrink-0">
          {!isDemo ? (
            <div className="flex items-center gap-1.5 sm:gap-2 rounded-md border border-rule bg-white px-2 sm:px-3 py-1.5 text-xs">
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-positive opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-positive" />
              </span>
              <span className="font-semibold text-ink">
                <span className="sm:hidden">Live</span>
                <span className="hidden sm:inline">Live Sync</span>
              </span>
              <button
                type="button"
                onClick={handleToggleMode}
                title="Switch to offline sample store"
                className="ml-1 sm:ml-2 text-[11px] text-primary font-medium hover:underline flex items-center gap-1"
              >
                <SlidersHorizontal className="h-3 w-3" />
                <span className="hidden sm:inline">Demo</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 sm:gap-2 rounded-md border border-amber-300 bg-amber-50 px-2 sm:px-3 py-1.5 text-xs text-amber-900">
              <Database className="h-3.5 w-3.5 text-amber-700 shrink-0" />
              <span className="font-semibold">
                <span className="sm:hidden">Demo</span>
                <span className="hidden sm:inline">Sample Store Data</span>
              </span>
              <button
                type="button"
                onClick={handleToggleMode}
                title="Connect to live PostgreSQL backend"
                className="ml-1 sm:ml-2 font-semibold text-primary hover:underline"
              >
                Go Live
              </button>
              <button
                type="button"
                onClick={handleResetData}
                title="Reset sample data"
                className="hidden sm:flex ml-1 text-[11px] text-ink-soft hover:underline items-center gap-0.5"
              >
                <RotateCcw className="h-3 w-3" /> Reset
              </button>
            </div>
          )}
        </div>

        {/* User Account & Actions */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
          {!isDemo && (
            <button
              type="button"
              onClick={() => setShowSettings(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-white px-2 sm:px-2.5 py-1.5 text-xs font-medium text-ink-nav hover:text-ink hover:bg-canvas transition-colors"
              title="Edit Store Name, GSTIN, Address & UPI ID"
            >
              <Settings className="h-3.5 w-3.5" />
              <span className="hidden xl:inline">Store Settings</span>
            </button>
          )}
          <Link
            to="/portal/bills"
            className="hidden sm:inline-flex items-center gap-1.5 rounded-md border border-rule bg-white px-2 sm:px-2.5 py-1.5 text-xs font-medium text-primary hover:bg-canvas transition-colors"
            title="Switch to Customer Passbook view"
          >
            <ShoppingBag className="h-3.5 w-3.5" />
            <span className="hidden xl:inline">Customer Passbook</span>
          </Link>
          <div className="hidden md:block text-right text-xs">
            <p className="font-medium text-ink truncate max-w-[160px]">{user?.email ?? 'Merchant'}</p>
            <p className="text-[11px] text-ink-soft truncate max-w-[160px]">
              {!isDemo ? primaryStoreName : 'Demo Sandbox Session'}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="flex items-center gap-1.5 rounded-md border border-rule bg-white px-2 sm:px-2.5 py-1.5 text-xs font-medium text-ink-nav hover:text-ink hover:bg-chrome transition-colors"
            title="Sign out"
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

      <StoreSettingsModal
        open={showSettings}
        business={primaryBusiness}
        onClose={() => setShowSettings(false)}
      />
    </div>
  );
}
