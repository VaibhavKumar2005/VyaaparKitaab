export function EmptyState({ label = 'Nothing here yet.' }: { label?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-rule bg-canvas-sunk px-6 py-10 text-center text-sm text-ink-soft">
      {label}
    </div>
  );
}
