import { useEffect, useState } from 'react';
import { Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { StatCard } from '../components/StatCard';
import { apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';

type StoreDashboardData = {
  todayRevenue: number;
  totalCustomers: number;
  lowStockItems: number;
  pendingInvoices: number;
  topProducts: Array<{ name: string; sales: number }>;
  recentTransactions: Array<{ invoice_number: string; total_amount: number; status: string; created_at: string }>;
  revenueSeries: Array<{ day: string; revenue: number }>;
};

export function StoreDashboard() {
  const { token } = useAuth();
  const [data, setData] = useState<StoreDashboardData | null>(null);

  useEffect(() => {
    void apiFetch<StoreDashboardData>('/dashboard/store', {}, token).then(setData).catch(() => setData(null));
  }, [token]);

  const chartData = data?.revenueSeries.length
    ? data.revenueSeries
    : Array.from({ length: 30 }, (_, index) => ({ day: `D${index + 1}`, revenue: 1000 + index * 80 }));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Today's Revenue" value={`₹${data?.todayRevenue ?? 0}`} detail="Live sales tracked from invoices" />
        <StatCard label="Total Customers" value={`${data?.totalCustomers ?? 0}`} detail="Stored contacts and walk-ins" />
        <StatCard label="Low Stock Items" value={`${data?.lowStockItems ?? 0}`} detail="Products below the safe threshold" />
        <StatCard label="Pending Invoices" value={`${data?.pendingInvoices ?? 0}`} detail="Drafts awaiting confirmation" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_0.9fr]">
        <section className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-glow backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-white">Revenue trend</h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis dataKey="day" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip contentStyle={{ background: '#020617', border: '1px solid rgba(255,255,255,0.1)' }} />
                <Line type="monotone" dataKey="revenue" stroke="#38bdf8" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-glow backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-white">Top products</h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data?.topProducts ?? []} dataKey="sales" nameKey="name" cx="50%" cy="50%" outerRadius={100} fill="#8b5cf6" />
                <Tooltip contentStyle={{ background: '#020617', border: '1px solid rgba(255,255,255,0.1)' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="rounded-3xl border border-white/10 bg-white/5 p-5 shadow-glow backdrop-blur-xl">
        <h2 className="text-lg font-semibold text-white">Recent transactions</h2>
        <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
          <table className="min-w-full divide-y divide-white/10 text-sm">
            <thead className="bg-white/5 text-slate-300">
              <tr>
                <th className="px-4 py-3 text-left">Invoice</th>
                <th className="px-4 py-3 text-left">Amount</th>
                <th className="px-4 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10 text-slate-200">
              {(data?.recentTransactions ?? []).map((transaction) => (
                <tr key={transaction.invoice_number}>
                  <td className="px-4 py-3">{transaction.invoice_number}</td>
                  <td className="px-4 py-3">₹{transaction.total_amount}</td>
                  <td className="px-4 py-3">{transaction.status}</td>
                </tr>
              ))}
              {!data?.recentTransactions?.length ? (
                <tr>
                  <td className="px-4 py-4 text-slate-400" colSpan={3}>No transactions yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}