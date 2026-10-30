import { Link } from 'react-router-dom';
import { AlertTriangle, Sparkles, TrendingUp, Wallet } from 'lucide-react';
import { BankingIncomeExplorer } from '../components/BankingIncomeExplorer';
import { PaymentBreakdownChart } from '../components/PaymentBreakdownChart';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingState } from '../components/ui/LoadingState';
import { StatusPill, paymentState } from '../components/StatusPill';
import { useAiForecast, useStoreDashboard } from '../hooks/useDashboard';
import { useInvoices } from '../hooks/useInvoices';
import { useProducts } from '../hooks/useBusinessData';
import { formatDate, formatINR, formatINRPrecise } from '../lib/format';

export function StoreDashboard() {
  const dash = useStoreDashboard();
  const inv = useInvoices();
  const prod = useProducts();
  const ai = useAiForecast();

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
  const sales = invoices.filter((i) => i.type === 'SALE' && i.status !== 'CANCELLED' && i.status !== 'DRAFT');
  // Money still owed on confirmed sales. Drafts and cancelled invoices aren't owed yet.
  const open = sales.filter((i) => i.total_amount > i.paid_amount);
  const outstanding = open.reduce((s, i) => s + Math.max(i.total_amount - i.paid_amount, 0), 0);
  const received = sales.reduce((s, i) => s + i.paid_amount, 0);
  const totalSalesVolume = Math.max(received + outstanding, 1);

  // Payment channel breakdown (UPI vs Cash vs Card vs Pending Credit/Udhar)
  const upiCollected = sales
    .filter((i) => i.payment_method === 'UPI')
    .reduce((s, i) => s + i.paid_amount, 0);
  const cashCollected = sales
    .filter((i) => i.payment_method === 'CASH')
    .reduce((s, i) => s + i.paid_amount, 0);
  const cardCollected = sales
    .filter((i) => i.payment_method === 'CARD')
    .reduce((s, i) => s + i.paid_amount, 0);

  const upiPct = Math.round((upiCollected / totalSalesVolume) * 100);
  const cashPct = Math.round((cashCollected / totalSalesVolume) * 100);
  const cardPct = Math.round((cardCollected / totalSalesVolume) * 100);
  const udharPct = Math.max(0, 100 - upiPct - cashPct - cardPct);

  const lowStockList = (prod.data ?? []).filter((p) => p.stock_qty <= 5).slice(0, 5);
  const topProducts = dash.data.topProducts ?? [];

  const recent = [...invoices]
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
    .slice(0, 8);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Store Financial Dashboard (व्यापार सारांश)</h1>
          <p className="text-xs text-ink-soft mt-0.5">
            Real-time cash flow, payment collection channels, and inventory stock health.
          </p>
        </div>
        <Link
          to="/app/invoices/new"
          className="rounded-md bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy-dark"
        >
          + Create New Bill
        </Link>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Summary">
        <Summary label="Payments received (जमा)" value={formatINR(received)} note="Settled across all sales" />
        <Summary
          label="Outstanding Udhar (बाकी)"
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
          label="Low stock alerts"
          value={String(dash.data.lowStockItems)}
          note="5 units or fewer"
          emphasis={dash.data.lowStockItems > 0}
        />
      </section>

      {/* Real Ingested Gateway & Google Pay / UPI Collections */}
      <PaymentBreakdownChart />

      {/* Connected Banking App: Inflow Income Explorer (RBI AA) */}
      <BankingIncomeExplorer />

      {/* Roznamcha: Payment Mode Collection Split & Inventory Health */}
      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-lg border border-rule bg-canvas-raised p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-ink flex items-center gap-2">
              <Wallet className="h-4 w-4 text-navy" />
              Collection Mode Split (भुगतान माध्यम विवरण)
            </h2>
            <span className="num text-xs font-medium text-ink-soft">
              Total Billed Sales: <strong className="text-ink">{formatINR(received + outstanding)}</strong>
            </span>
          </div>

          {/* Segmented Progress Bar (Zero external chart library overhead) */}
          <div className="h-3 w-full overflow-hidden rounded-full bg-canvas-sunk flex border border-rule">
            {upiPct > 0 && (
              <div style={{ width: `${upiPct}%` }} className="bg-navy transition-all" title={`UPI: ${upiPct}%`} />
            )}
            {cashPct > 0 && (
              <div style={{ width: `${cashPct}%` }} className="bg-positive transition-all" title={`Cash: ${cashPct}%`} />
            )}
            {cardPct > 0 && (
              <div style={{ width: `${cardPct}%` }} className="bg-ink-soft transition-all" title={`Card: ${cardPct}%`} />
            )}
            {udharPct > 0 && (
              <div style={{ width: `${udharPct}%` }} className="bg-due transition-all" title={`Pending Udhar: ${udharPct}%`} />
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1 text-xs">
            <div className="rounded-md border border-rule bg-canvas-sunk p-3">
              <div className="flex items-center gap-1.5 text-ink-soft">
                <span className="h-2 w-2 rounded-full bg-navy" />
                <span>UPI QR / Online</span>
              </div>
              <p className="num mt-1 text-base font-bold text-ink">{formatINR(upiCollected)}</p>
              <p className="text-[11px] text-ink-faint">{upiPct}% of volume</p>
            </div>

            <div className="rounded-md border border-rule bg-canvas-sunk p-3">
              <div className="flex items-center gap-1.5 text-ink-soft">
                <span className="h-2 w-2 rounded-full bg-positive" />
                <span>Cash (नकद गल्ला)</span>
              </div>
              <p className="num mt-1 text-base font-bold text-ink">{formatINR(cashCollected)}</p>
              <p className="text-[11px] text-ink-faint">{cashPct}% of volume</p>
            </div>

            <div className="rounded-md border border-rule bg-canvas-sunk p-3">
              <div className="flex items-center gap-1.5 text-ink-soft">
                <span className="h-2 w-2 rounded-full bg-ink-soft" />
                <span>Card / Bank</span>
              </div>
              <p className="num mt-1 text-base font-bold text-ink">{formatINR(cardCollected)}</p>
              <p className="text-[11px] text-ink-faint">{cardPct}% of volume</p>
            </div>

            <div className="rounded-md border border-rule bg-canvas-sunk p-3">
              <div className="flex items-center gap-1.5 text-ink-soft">
                <span className="h-2 w-2 rounded-full bg-due" />
                <span>Unpaid Udhar</span>
              </div>
              <p className="num mt-1 text-base font-bold text-due">{formatINR(outstanding)}</p>
              <p className="text-[11px] text-ink-faint">{udharPct}% pending</p>
            </div>
          </div>

          {topProducts.length > 0 && (
            <div className="border-t border-rule pt-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2 flex items-center gap-1.5">
                <TrendingUp className="h-3.5 w-3.5 text-positive" /> Top Selling Items (सर्वाधिक बिक्री)
              </p>
              <div className="grid gap-2 sm:grid-cols-2 text-xs">
                {topProducts.slice(0, 4).map((tp) => (
                  <div key={tp.name} className="flex items-center justify-between rounded bg-canvas px-3 py-1.5 border border-rule">
                    <span className="truncate font-medium text-ink pr-2">{tp.name}</span>
                    <span className="num font-semibold text-navy shrink-0">{formatINR(tp.sales)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Low Stock Reorder Watchlist */}
        <div className="rounded-lg border border-rule bg-canvas-raised p-5 flex flex-col justify-between space-y-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-ink flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4 text-due" />
                Reorder Watchlist (कम स्टॉक)
              </h2>
              <Link to="/app/products" className="text-xs font-medium text-navy hover:underline">
                Inventory
              </Link>
            </div>
            {lowStockList.length === 0 ? (
              <p className="text-xs text-ink-soft py-6 text-center">All products are well-stocked.</p>
            ) : (
              <ul className="divide-y divide-rule text-xs">
                {lowStockList.map((item) => (
                  <li key={item.id} className="py-2.5 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink">{item.name}</p>
                      <p className="text-[11px] text-ink-faint">SKU: {item.sku ?? '—'}</p>
                    </div>
                    <span className="num shrink-0 rounded bg-due-tint px-2 py-0.5 font-bold text-due">
                      {item.stock_qty} {item.unit ?? 'left'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Link
            to="/app/invoices/new"
            className="block w-full rounded-md border border-rule bg-canvas-sunk py-2 text-center text-xs font-semibold text-ink hover:bg-canvas"
          >
            Record Supplier Purchase Bill
          </Link>
        </div>
      </section>

      {/* AI/ML Demand & Cash-Flow Forecasting Section */}
      {ai.data && (
        <section className="rounded-lg border border-rule bg-canvas-raised p-5 space-y-4" aria-label="AI Demand Forecast">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-ink flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-navy" />
                AI Demand & Cash-Flow Forecast (AI मांग एवं नकदी पूर्वानुमान)
              </h2>
              <p className="text-xs text-ink-soft mt-0.5">
                Chronological 80/20 validation • Active Model:{' '}
                <strong className="text-navy">{ai.data.revenue_model.selected_model}</strong>
                {ai.data.revenue_model.validation_metrics[ai.data.revenue_model.selected_model] && (
                  <span>
                    {' '}
                    (RMSE:{' '}
                    {ai.data.revenue_model.validation_metrics[ai.data.revenue_model.selected_model].rmse}, MAE:{' '}
                    {ai.data.revenue_model.validation_metrics[ai.data.revenue_model.selected_model].mae})
                  </span>
                )}
              </p>
            </div>
            <div className="rounded-md bg-canvas-sunk px-3 py-1.5 border border-rule text-xs">
              <span className="text-ink-soft">Projected Next 7d Revenue: </span>
              <strong className="num text-navy font-bold">
                {formatINR(ai.data.revenue_model.projected_7d_revenue)}
              </strong>
            </div>
          </div>

          {ai.data.insights.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {ai.data.insights.slice(0, 2).map((insight, idx) => (
                <div
                  key={idx}
                  className="rounded-md border border-rule bg-canvas-sunk px-3 py-2 text-xs text-ink flex items-start gap-2"
                >
                  <TrendingUp className="h-3.5 w-3.5 text-navy shrink-0 mt-0.5" />
                  <span>{insight}</span>
                </div>
              ))}
            </div>
          )}

          {ai.data.inventory_forecasts.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="border-b border-rule bg-canvas-sunk text-left uppercase tracking-wider text-ink-soft">
                  <tr>
                    <th className="px-3 py-2 font-semibold">SKU / Item</th>
                    <th className="px-3 py-2 text-right font-semibold">Stock</th>
                    <th className="px-3 py-2 text-right font-semibold">7d Forecast</th>
                    <th className="px-3 py-2 text-right font-semibold">Est. Stockout</th>
                    <th className="px-3 py-2 text-right font-semibold">Suggested Reorder</th>
                    <th className="px-3 py-2 text-right font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {ai.data.inventory_forecasts.slice(0, 5).map((item) => (
                    <tr key={item.product_id} className="hover:bg-canvas">
                      <td className="px-3 py-2 font-medium text-ink">
                        {item.name} <span className="text-ink-faint">({item.sku})</span>
                      </td>
                      <td className="num px-3 py-2 text-right text-ink-soft">
                        {item.current_stock} {item.unit}
                      </td>
                      <td className="num px-3 py-2 text-right font-medium text-ink">
                        {item.forecast_7d_units} {item.unit}
                      </td>
                      <td className="num px-3 py-2 text-right text-ink-soft">
                        {item.days_to_stockout >= 900 ? '30+ days' : `${item.days_to_stockout} days`}
                      </td>
                      <td className="num px-3 py-2 text-right font-semibold text-navy">
                        +{item.recommended_reorder_qty} {item.unit}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                            item.urgency === 'CRITICAL'
                              ? 'bg-due-tint text-due'
                              : item.urgency === 'WARNING'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-positive-tint text-positive'
                          }`}
                        >
                          {item.urgency}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

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