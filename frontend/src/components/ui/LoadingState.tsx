export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <div role="status" className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-slate-300">
      <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-sky-400" />
      {label}
    </div>
  );
}
