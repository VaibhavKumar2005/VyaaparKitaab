import { useEffect, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import { apiFetch } from '../lib/api';
import { formatINR, formatINRPrecise } from '../lib/format';
import { isDemoMode } from '../mock/mockStore';

type CustomerSummary = {
  customer_id: string;
  summary: Record<string, Record<string, number>>;
};

const colors = ['#12305f', '#1d6b4a', '#c2410c', '#0284c7', '#7c3aed'];

const sampleDemoSummary: CustomerSummary = {
  customer_id: 'cust-me',
  summary: {
    'Grocery & Staples': {
      'Atta & Flours': 2450,
      'Refined Edible Oil': 1850,
      'Basmati Rice': 1520,
      'Pulses & Salt': 680,
    },
    'Household Essentials': {
      'Detergent & Washing': 825,
      'Bathing Soaps': 450,
    },
    'Beverages & Breakfast': {
      'Tea & Coffee': 1200,
      'Biscuits & Snacks': 650,
    },
  },
};

export function CustomerDashboard() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<CustomerSummary | null>(null);

  useEffect(() => {
    if (isDemoMode() || !token) {
      setSummary(sampleDemoSummary);
      return;
    }
    void apiFetch<CustomerSummary>('/dashboard/customer/me')
      .then(setSummary)
      .catch(() => setSummary(sampleDemoSummary));
  }, [token]);

  const activeSummary = summary ?? sampleDemoSummary;

  const chartData = Object.entries(activeSummary.summary ?? {}).map(([name, subcategories]) => ({
    name,
    value: Object.values(subcategories).reduce((total, current) => total + current, 0),
  }));

  const totalSpent = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Customer Purchase Summary</h1>
        <p className="mt-0.5 text-sm text-ink-soft">
          Personal ledger, purchase categories, and bill records for this account.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3" aria-label="Customer spending summary">
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Spent This Month</p>
          <p className="num mt-2 text-2xl font-bold text-ink">{formatINR(totalSpent)}</p>
          <p className="mt-1 text-xs text-ink-faint">Across confirmed store invoices</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Top Category</p>
          <p className="mt-2 text-2xl font-bold text-navy">{chartData[0]?.name ?? 'Grocery'}</p>
          <p className="mt-1 text-xs text-ink-faint">Primary store expense</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Recorded Purchases</p>
          <p className="num mt-2 text-2xl font-bold text-positive">8 Bills</p>
          <p className="mt-1 text-xs text-ink-faint">Settled & paid bills</p>
        </div>
      </div>

      <section className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        {/* Category Pie Chart */}
        <article className="rounded-lg border border-rule bg-canvas-raised p-5">
          <h2 className="text-base font-semibold text-ink">Spending by Category</h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData.length ? chartData : [{ name: 'Grocery', value: 1 }]}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={95}
                  label={({ name, percent }) => `${name} (${((percent || 0) * 100).toFixed(0)}%)`}
                >
                  {chartData.map((entry, index) => (
                    <Cell key={entry.name} fill={colors[index % colors.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(val: any) => [formatINR(Number(val) || 0), 'Amount']}
                  contentStyle={{ backgroundColor: '#ffffff', borderColor: '#dde3ec', borderRadius: '6px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>

        {/* Subcategory breakdown table */}
        <article className="rounded-lg border border-rule bg-canvas-raised p-5">
          <h2 className="text-base font-semibold text-ink">Item Category Breakdown</h2>
          <div className="mt-4 overflow-hidden rounded-md border border-rule">
            <table className="min-w-full divide-y divide-rule text-sm">
              <thead className="bg-canvas-sunk text-xs uppercase tracking-wider text-ink-soft">
                <tr>
                  <th scope="col" className="px-4 py-2.5 text-left font-semibold">Category</th>
                  <th scope="col" className="px-4 py-2.5 text-left font-semibold">Subcategory</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-semibold">Total Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {Object.entries(activeSummary.summary).flatMap(([category, subcategories]) =>
                  Object.entries(subcategories).map(([subcategory, amount]) => (
                    <tr key={`${category}-${subcategory}`} className="hover:bg-canvas">
                      <td className="px-4 py-2.5 text-ink font-medium">{category}</td>
                      <td className="px-4 py-2.5 text-ink-soft">{subcategory}</td>
                      <td className="num whitespace-nowrap px-4 py-2.5 text-right font-semibold text-ink">
                        {formatINRPrecise(amount)}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </div>
  );
}