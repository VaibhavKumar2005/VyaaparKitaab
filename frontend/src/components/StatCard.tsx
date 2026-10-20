export function StatCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-2 font-[Space_Grotesk] text-2xl font-bold text-slate-900">{value}</p>
      {detail ? <p className="mt-1.5 text-xs text-slate-500">{detail}</p> : null}
    </article>
  );
}