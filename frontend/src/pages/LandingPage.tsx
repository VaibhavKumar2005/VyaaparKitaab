import { Link } from 'react-router-dom';

const features = [
  {
    title: 'Invoices',
    body: 'Create GST invoices with line items and totals, and keep every bill searchable.',
  },
  {
    title: 'Customers',
    body: 'One record per customer, with their invoices alongside.',
  },
  {
    title: 'Inventory',
    body: 'Stock levels and prices in one list, with low-stock items flagged.',
  },
  {
    title: 'Payments',
    body: 'Collect by UPI and have the invoice marked paid once the payment is verified.',
  },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="font-display text-xl font-bold text-navy">VyaparKitaab</span>
        <nav className="flex items-center gap-3 text-sm font-medium">
          <Link to="/login" className="px-3 py-2 text-ink-soft hover:text-ink">
            Sign in
          </Link>
          <Link
            to="/register"
            className="rounded-md bg-navy px-4 py-2 font-semibold text-white hover:bg-navy-dark"
          >
            Create account
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-12 sm:px-6 sm:pt-20">
          <p className="text-xs font-semibold uppercase tracking-widest text-ink-faint">
            A digital bahi-khata for small businesses
          </p>
          <h1 className="mt-4 max-w-3xl font-display text-4xl font-bold leading-tight sm:text-6xl">
            Keep your shop's accounts in one clear place.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-ink-soft">
            Invoices, customers, stock and payments — written down once, easy to find later.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/register"
              className="rounded-md bg-navy px-5 py-3 font-semibold text-white hover:bg-navy-dark"
            >
              Get started
            </Link>
            <Link
              to="/app/dashboard"
              className="rounded-md border border-navy/30 bg-navy-tint px-5 py-3 font-semibold text-navy hover:bg-navy/15"
            >
              ⚡ Explore Demo Store
            </Link>
            <Link
              to="/login"
              className="rounded-md border border-rule bg-canvas-raised px-5 py-3 font-semibold hover:bg-canvas-sunk"
            >
              Sign in
            </Link>
          </div>
        </section>

        <section className="border-y border-rule bg-canvas-raised">
          <div className="mx-auto grid max-w-6xl gap-px bg-rule sm:grid-cols-2 lg:grid-cols-4">
            {features.map((f) => (
              <div key={f.title} className="bg-canvas-raised p-6">
                <h2 className="font-display text-lg font-bold">{f.title}</h2>
                <p className="mt-2 text-sm text-ink-soft">{f.body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-4 py-8 text-sm text-ink-faint sm:px-6">
        © 2026 VyaparKitaab
      </footer>
    </div>
  );
}