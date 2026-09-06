import { Link } from 'react-router-dom';
import { ThreeScene } from '../components/ThreeScene';

export function LandingPage() {
  return (
    <div className="mx-auto min-h-screen max-w-7xl px-4 py-6 lg:px-8">
      <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-slate-950/70 p-6 shadow-glow backdrop-blur-xl lg:p-10">
        <div className="grid gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
          <div className="space-y-6">
            <span className="inline-flex rounded-full border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-sky-300">
              MSME business notebook
            </span>
            <h1 className="max-w-2xl font-[Space_Grotesk] text-5xl font-bold leading-[0.95] text-white lg:text-7xl">
              One workspace for invoices, inventory, customers, and cash flow.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-slate-300">
              VyaparKitaab is the operational notebook for Indian small businesses: role-aware dashboards, transaction checks, and a cloud-first stack that can grow into analytics and AI.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/login" className="rounded-full bg-sky-400 px-5 py-3 font-semibold text-slate-950">
                Sign in
              </Link>
              <Link to="/register" className="rounded-full border border-white/15 bg-white/5 px-5 py-3 font-semibold text-white">
                Create account
              </Link>
            </div>
          </div>
          <div className="space-y-4">
            <ThreeScene />
            <div className="grid grid-cols-2 gap-4 text-sm text-slate-300">
              <article className="rounded-3xl border border-white/10 bg-white/5 p-4">
                <p className="text-sky-300">Store dashboard</p>
                <p className="mt-2">Revenue, low-stock alerts, and invoices in one view.</p>
              </article>
              <article className="rounded-3xl border border-white/10 bg-white/5 p-4">
                <p className="text-violet-300">Customer view</p>
                <p className="mt-2">Spending breakdowns and recent purchases.</p>
              </article>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}