export function ErrorState({
  label = 'Something went wrong.',
  onRetry,
}: {
  label?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded-lg border border-due/30 bg-due-tint p-6 text-sm text-due">
      <p className="font-medium">{label}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-due/40 px-3 py-1.5 font-semibold hover:bg-white/60"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
