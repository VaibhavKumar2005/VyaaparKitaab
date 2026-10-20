import { Link } from 'react-router-dom';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { StatusPill, paymentState } from '../components/StatusPill';
import { useStoreDashboard } from '../hooks/useDashboard';
import { useInvoices } from '../hooks/useInvoices';
import { formatDate, formatINR, formatINRPrecise } from '../lib/format';

export function StoreDashboard() {
  const dash = useStoreDashboard();
  const inv = useInvoices();

  if (dash.isPending || inv.isPending) return <LoadingState label="Loading dashboard…" />;
  if (dash.isError || inv.isError || !dash.data || !inv.data) {
    return (
      <ErrorState
        label="Couldn't load the dashboard."
        onRetry={() => {
          void dash.refetch();
          void inv.refetch();
        }}
      />
    );
  }

  const invoices = inv.data;
  // Money still owed on confirmed sales. Drafts and cancelled invoices aren't owed yet.
  const open = invoices.filter((i) => i.type === 'SALE' && i.status === 'CONFIRMED');
  const outstanding = open.reduce((s, i) => s + Math.max(i.total_amount - i.paid_amount, 0), 0);
  const received = invoices
    .filter((i) => i.type === 'SALE')
    .reduce((s, i) => s + i.paid_amount, 0);
  const recent = [...invoices]
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
    .slice(0, 8);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Summary">
        <Summary label="Payments received" value={formatINR(received)} note="All sale invoices" />
        <Summary
          label="Outstanding"
          value={formatINR(outstanding)}
          note={`${open.length} open invoice${open.length === 1 ? '' : 's'}`}
          emphasis={outstanding > 0}
        />
        <Summary
          label="Draft invoices"
          value={String(dash.data.pendingInvoices)}
          note="Not yet confirmed"
        />
        <Summary
          label="Low stock"
          value={String(dash.data.lowStockItems)}
          note="5 units or fewer"
          emphasis={dash.data.lowStockItems > 0}
        />
      </section>

      <section aria-labelledby="recent">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 id="recent" className="text-lg font-semibold">Recent activity</h2>
          <Link to="/app/invoices" className="text-sm font-medium text-navy hover:underline">
            View all
          </Link>
        </div>
        <TransactionTable rows={recent} />
      </section>
    </div>
  );
}

export function TransactionTable({
  rows,
}: {
  rows: Array<{
    id: string;
    invoice_number: string;
    type: string;
    status: string;
    total_amount: number;
    paid_amount: number;
    created_at: string;
  }>;
}) {
  if (!rows.length) {
    return (
      <div className="rounded-lg border border-dashed border-rule bg-canvas-sunk px-6 py-10 text-center text-sm text-ink-soft">
        No invoices yet.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-rule bg-canvas-raised">
      <table className="min-w-full text-sm">
        <thead className="border-b border-rule bg-canvas-sunk text-left text-xs uppercase tracking-wider text-ink-soft">
          <tr>
            <th scope="col" className="px-4 py-3 font-semibold">Date</th>
            <th scope="col" className="px-4 py-3 font-semibold">Reference</th>
            <th scope="col" className="px-4 py-3 font-semibold">Type</th>
            <th scope="col" className="px-4 py-3 font-semibold">Status</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {rows.map((r) => {
            const credit = r.type === 'SALE';
            return (
              <tr key={r.id} className="hover:bg-canvas">
                <td className="whitespace-nowrap px-4 py-3 text-ink-soft">{formatDate(r.created_at)}</td>
                <td className="px-4 py-3 font-medium">
                  <Link to={`/app/invoices/${r.id}`} className="text-navy hover:underline">
                    {r.invoice_number}
                  </Link>
                </td>
                {/* Text label as well as sign, so credit/debit never relies on colour alone */}
                <td className="px-4 py-3 text-ink-soft">{credit ? 'Credit (sale)' : 'Debit (purchase)'}</td>
                <td className="px-4 py-3"><StatusPill state={paymentState(r)} /></td>
                <td className={`num whitespace-nowrap px-4 py-3 text-right font-semibold ${credit ? 'text-positive' : 'text-ink'}`}>
                  {credit ? '+' : '−'} {formatINRPrecise(r.total_amount)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Summary({
  label,
  value,
  note,
  emphasis,
}: {
  label: string;
  value: string;
  note: string;
  emphasis?: boolean;
}) {
  return (
    <div className="rounded-lg border border-rule bg-canvas-raised p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">{label}</p>
      <p className={`num mt-2 text-2xl font-bold ${emphasis ? 'text-due' : 'text-ink'}`}>{value}</p>
      <p className="mt-1 text-xs text-ink-faint">{note}</p>
    </div>
  );
}