export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="rounded-lg border border-rule bg-canvas-raised p-6 text-sm text-ink-soft">
      {label}
    </div>
  );
}
