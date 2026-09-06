import { useEffect, useState } from 'react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { StatCard } from '../components/StatCard';
import { useAuth } from '../contexts/AuthContext';
import { apiFetch } from '../lib/api';

type CustomerSummary = {
  customer_id: string;
  summary: Record<string, Record<string, number>>;
};

const colors = ['#38bdf8', '#8b5cf6', '#22c55e', '#f59e0b', '#f43f5e'];

export function CustomerDashboard() {
  const { token } = useAuth();
  const [summary, setSummary] = useState<CustomerSummary | null>(null);

  useEffect(() => {
    void apiFetch<CustomerSummary>('/dashboard/customer/demo', {}, token).then(setSummary).catch(() => setSummary(null));
  }, [token]);

  const chartData = Object.entries(summary?.summary ?? {}).map(([name, value]) => ({
    name,
    value: Object.values(value).reduce((total, current) => total + current, 0),
  }));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Spent this month" value="₹12,480" detail="Based on confirmed purchases" />
        <StatCard label="Top category" value="Food" detail="Most purchases fall here" />
        <StatCard label="Recent purchases" value="8" detail="Last 30 days" />
      </div>

      <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <article className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-glow backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-white">Spending by category</h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={chartData.length ? chartData : [{ name: 'Food', value: 1 }]} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={110} label>
                  {(chartData.length ? chartData : [{ name: 'Food', value: 1 }]).map((entry, index) => (
                    <Cell key={entry.name} fill={colors[index % colors.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#020617', border: '1px solid rgba(255,255,255,0.1)' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-glow backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-white">Subcategory breakdown</h2>
          <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
            <table className="min-w-full divide-y divide-white/10 text-sm">
              <thead className="bg-white/5 text-slate-300">
                <tr>
                  <th className="px-4 py-3 text-left">Category</th>
                  <th className="px-4 py-3 text-left">Subcategory</th>
                  <th className="px-4 py-3 text-left">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10 text-slate-200">
                {(summary ? Object.entries(summary.summary) : []).flatMap(([category, subcategories]) =>
                  Object.entries(subcategories).map(([subcategory, amount]) => (
                    <tr key={`${category}-${subcategory}`}>
                      <td className="px-4 py-3">{category}</td>
                      <td className="px-4 py-3">{subcategory}</td>
                      <td className="px-4 py-3">₹{amount.toFixed(2)}</td>
                    </tr>
                  )),
                )}
                {!chartData.length ? (
                  <tr>
                    <td className="px-4 py-4 text-slate-400" colSpan={3}>No spending data yet.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </div>
  );
}