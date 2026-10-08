export function EmptyState({ label = 'Nothing here yet.' }: { label?: string }) {
  return <div className="rounded-2xl border border-dashed border-white/15 p-6 text-center text-sm text-slate-400">{label}</div>;
}
