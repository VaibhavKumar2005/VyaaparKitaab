import { useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useCashflowTimeSeries } from '../hooks/useDashboard';
import { formatINR, formatINRPrecise } from '../lib/format';
import { isDemoMode } from '../mock/mockStore';

interface CashflowTimeSeriesPanelProps {
  view?: 'all' | 'customer' | 'store';
  title?: string;
}

const SOURCE_LABELS: Record<string, string> = {
  sms_upi: 'Bank SMS / UPI Alerts',
  razorpay: 'Razorpay Sync',
  statement: 'Bank / UPI Statements',
  store_invoice: 'Store Invoices',
  ocr_purchase: 'OCR Receipts',
};

export function CashflowTimeSeriesPanel({
  view = 'all',
  title = 'Unified Cashflow Time-Series & Multi-Model Forecast',
}: CashflowTimeSeriesPanelProps) {
  const [lookbackDays, setLookbackDays] = useState<30 | 60 | 90>(30);
  const [horizonDays, setHorizonDays] = useState<7 | 14 | 30>(14);
  const [granularity, setGranularity] = useState<'daily' | 'weekly'>('daily');

  const { data, isLoading, isError, refetch } = useCashflowTimeSeries({
    lookbackDays,
    horizonDays,
    granularity,
    view,
  });

  const combinedSeries = useMemo(() => {
    if (!data) return [];
    const hist = data.historical.map((p) => ({
      date: p.date.slice(5),
      inflow: p.inflow,
      outflow: p.outflow,
      rollingInflow: p.rolling_7d_inflow,
      rollingOutflow: p.rolling_7d_outflow,
      forecastInflow: null as number | null,
      forecastOutflow: null as number | null,
    }));
    const fc = data.forecast.map((f) => ({
      date: f.date.slice(5),
      inflow: null as number | null,
      outflow: null as number | null,
      rollingInflow: null as number | null,
      rollingOutflow: null as number | null,
      forecastInflow: f.projected_inflow,
      forecastOutflow: f.projected_outflow,
    }));
    return [...hist, ...fc];
  }, [data]);

  if (isDemoMode()) {
    return null;
  }

  if (isLoading) {
    return (
      <div className="rounded-xl border border-rule bg-canvas-raised p-5 text-xs text-ink-soft">
        Building chronological cashflow time-series across SMS, UPI, Razorpay, and ledger records…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-due/30 bg-due-tint p-4 text-xs text-due flex items-center justify-between">
        <span>Unable to compute cashflow time-series right now.</span>
        <button
          type="button"
          onClick={() => void refetch()}
          className="rounded bg-navy px-2.5 py-1 font-semibold text-white"
        >
          Retry
        </button>
      </div>
    );
  }

  const { summary, models, sources, seasonality, anomalies } = data;
  const inMetric = models.inflow_metrics[models.inflow_selected];
  const outMetric = models.outflow_metrics[models.outflow_selected];

  return (
    <section
      className="rounded-xl border border-rule bg-canvas-raised p-5 space-y-5"
      aria-label="Unified Cashflow Time-Series"
    >
      {/* Header + Controls */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-rule pb-3.5">
        <div>
          <h3 className="text-sm font-bold text-ink flex items-center gap-2">
            <Activity className="h-4 w-4 text-navy" />
            <span>{title}</span>
          </h3>
          <p className="text-xs text-ink-soft mt-0.5">
            Streamlined from Bank SMS, UPI alerts, Razorpay, statements &amp; bills • Best Inflow Model:{' '}
            <strong className="text-navy">{models.inflow_selected}</strong>
            {inMetric ? ` (RMSE ₹${inMetric.rmse})` : ''} • Best Outflow Model:{' '}
            <strong className="text-navy">{models.outflow_selected}</strong>
            {outMetric ? ` (RMSE ₹${outMetric.rmse})` : ''}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {([30, 60, 90] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setLookbackDays(d)}
              className={`rounded-md px-2 py-1 font-semibold transition-colors ${
                lookbackDays === d
                  ? 'bg-navy text-white'
                  : 'border border-rule bg-canvas text-ink-soft hover:text-ink'
              }`}
            >
              {d}d
            </button>
          ))}
          <span className="text-ink-faint px-1">|</span>
          {([7, 14, 30] as const).map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizonDays(h)}
              className={`rounded-md px-2 py-1 font-semibold transition-colors ${
                horizonDays === h
                  ? 'bg-emerald-700 text-white'
                  : 'border border-rule bg-canvas text-ink-soft hover:text-ink'
              }`}
            >
              +{h}d Fcst
            </button>
          ))}
          <span className="text-ink-faint px-1">|</span>
          {(['daily', 'weekly'] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGranularity(g)}
              className={`rounded-md px-2 py-1 font-semibold capitalize transition-colors ${
                granularity === g
                  ? 'bg-slate-800 text-white'
                  : 'border border-rule bg-canvas text-ink-soft hover:text-ink'
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3">
          <div className="flex items-center justify-between text-[11px] font-semibold text-emerald-900">
            <span>Period Inflow ({lookbackDays}d)</span>
            <span className="inline-flex items-center gap-0.5">
              {summary.inflow_growth_pct >= 0 ? (
                <TrendingUp className="h-3 w-3 text-emerald-700" />
              ) : (
                <TrendingDown className="h-3 w-3 text-rose-600" />
              )}
              {summary.inflow_growth_pct >= 0 ? '+' : ''}
              {summary.inflow_growth_pct}%
            </span>
          </div>
          <p className="num mt-1 text-lg font-bold text-ink">{formatINR(summary.total_inflow)}</p>
          <p className="text-[11px] text-ink-soft">Avg {formatINR(summary.avg_daily_inflow)} / day</p>
        </div>

        <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-3">
          <div className="flex items-center justify-between text-[11px] font-semibold text-rose-900">
            <span>Period Outflow ({lookbackDays}d)</span>
            <span>
              {summary.outflow_growth_pct >= 0 ? '+' : ''}
              {summary.outflow_growth_pct}%
            </span>
          </div>
          <p className="num mt-1 text-lg font-bold text-ink">{formatINR(summary.total_outflow)}</p>
          <p className="text-[11px] text-ink-soft">Avg {formatINR(summary.avg_daily_outflow)} / day</p>
        </div>

        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
          <div className="text-[11px] font-semibold text-blue-900">
            Forecasted Net (+{horizonDays}d)
          </div>
          <p
            className={`num mt-1 text-lg font-bold ${
              summary.projected_net_total >= 0 ? 'text-emerald-700' : 'text-rose-700'
            }`}
          >
            {summary.projected_net_total >= 0 ? '+' : ''}
            {formatINR(summary.projected_net_total)}
          </p>
          <p className="text-[11px] text-ink-soft">
            In {formatINR(summary.projected_inflow_total)} • Out {formatINR(summary.projected_outflow_total)}
          </p>
        </div>

        <div className="rounded-lg border border-rule bg-canvas-sunk p-3">
          <div className="text-[11px] font-semibold text-ink-soft">Streamlined Coverage</div>
          <p className="num mt-1 text-lg font-bold text-ink">{summary.total_transactions} txns</p>
          <p className="text-[11px] text-ink-soft">
            {summary.anomaly_count > 0
              ? `${summary.anomaly_count} anomaly day(s) flagged`
              : 'No abnormal daily spikes'}
          </p>
        </div>
      </div>

      {/* Main Historical + Forecast Chart */}
      <div className="h-72 w-full">
        {summary.total_transactions > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={combinedSeries} margin={{ top: 10, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#475e75' }} />
              <YAxis tick={{ fontSize: 10, fill: '#475e75' }} />
              <Tooltip
                formatter={(value: unknown, name: unknown) => [
                  formatINRPrecise(Number(value) || 0),
                  String(name),
                ]}
                contentStyle={{ backgroundColor: '#fff', borderRadius: 8, borderColor: '#e5e7eb', fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
              <Area
                type="monotone"
                dataKey="inflow"
                name="Inflow (Actual)"
                fill="#10b981"
                fillOpacity={0.2}
                stroke="#059669"
                strokeWidth={2}
              />
              <Area
                type="monotone"
                dataKey="outflow"
                name="Outflow (Actual)"
                fill="#f43f5e"
                fillOpacity={0.16}
                stroke="#e11d48"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="rollingInflow"
                name="7d Avg Inflow"
                stroke="#047857"
                strokeWidth={1.5}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="forecastInflow"
                name="Forecast Inflow"
                stroke="#059669"
                strokeDasharray="5 4"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="forecastOutflow"
                name="Forecast Outflow"
                stroke="#e11d48"
                strokeDasharray="5 4"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex flex-col items-center justify-center rounded-lg border border-dashed border-rule bg-canvas text-center p-6 text-xs text-ink-soft gap-1">
            <BarChart3 className="h-5 w-5 text-ink-faint" />
            <p className="font-semibold text-ink">No streamlined transactions in the last {lookbackDays} days yet.</p>
            <p>Paste Bank/UPI SMS messages, upload a statement, or sync Razorpay to populate this time-series forecast.</p>
          </div>
        )}
      </div>

      {/* Bottom Row: Weekday Seasonality + Streamlined Sources & Anomalies */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-rule bg-canvas p-3.5 space-y-2">
          <div className="text-xs font-bold text-ink">Day-of-Week Seasonality (Avg ₹)</div>
          <div className="h-36 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={seasonality} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#475e75' }} />
                <YAxis tick={{ fontSize: 10, fill: '#475e75' }} />
                <Tooltip
                  formatter={(val: unknown, name: unknown) => [formatINRPrecise(Number(val) || 0), String(name)]}
                  contentStyle={{ fontSize: 11, borderRadius: 8 }}
                />
                <Bar dataKey="avg_inflow" name="Avg Inflow" fill="#10b981" radius={[3, 3, 0, 0]} />
                <Bar dataKey="avg_outflow" name="Avg Outflow" fill="#f43f5e" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-lg border border-rule bg-canvas p-3.5 space-y-3">
          <div className="text-xs font-bold text-ink">Streamlined Sources &amp; Spike Alerts</div>
          {sources.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {sources.map((s) => (
                <span
                  key={s.source}
                  className="inline-flex items-center gap-1.5 rounded-md border border-rule bg-canvas-raised px-2.5 py-1 text-[11px] text-ink"
                >
                  <span className="font-semibold">{SOURCE_LABELS[s.source] ?? s.source}</span>
                  <span className="text-ink-soft">({s.count})</span>
                  <span className="num font-bold text-navy">{formatINR(s.volume)}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-ink-soft">No ingested sources yet.</p>
          )}

          {anomalies.length > 0 && (
            <div className="space-y-1.5 pt-1 border-t border-rule">
              {anomalies.slice(0, 3).map((a) => (
                <div
                  key={a.date}
                  className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-950"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5" />
                  <span>
                    <strong>{a.date}</strong>: {a.reason} (In {formatINR(a.inflow)} / Out {formatINR(a.outflow)})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
