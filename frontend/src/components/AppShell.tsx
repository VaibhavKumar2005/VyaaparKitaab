import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    'rounded-full px-4 py-2 text-sm transition',
    isActive ? 'bg-sky-400 text-slate-950 font-semibold' : 'text-slate-300 hover:bg-white/10',
  ].join(' ');

export function AppShell() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen px-4 py-5 text-slate-100 lg:px-8">
      <header className="mx-auto flex max-w-7xl items-center justify-between rounded-3xl border border-white/10 bg-slate-950/70 px-5 py-4 shadow-glow backdrop-blur-xl">
        <div>
          <p className="font-[Space_Grotesk] text-lg font-bold">VyaparKitaab</p>
          <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Cloud business notebook</p>
        </div>
        <nav className="flex flex-wrap items-center gap-2">
          <NavLink to="/app/dashboard" className={navClass}>Dashboard</NavLink>
          <NavLink to="/app/customers" className={navClass}>Customers</NavLink>
          <NavLink to="/app/products" className={navClass}>Products</NavLink>
          <NavLink to="/app/invoices" className={navClass}>Invoices</NavLink>
          <span className="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-400">
            {user?.role ?? 'STORE_OWNER'}
          </span>
          <button onClick={logout} className="rounded-full bg-white/10 px-4 py-2 text-sm hover:bg-white/15">
            Logout
          </button>
        </nav>
      </header>
      <main className="mx-auto mt-6 max-w-7xl">
        <Outlet />
      </main>
    </div>
  );
}