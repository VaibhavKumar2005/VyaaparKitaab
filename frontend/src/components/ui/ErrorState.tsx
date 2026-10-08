export function ErrorState({ label = 'Something went wrong.', onRetry }: { label?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-2xl border border-red-400/20 bg-red-400/10 p-6 text-sm text-red-200">
      <p>{label}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-3 rounded-lg border border-red-300/30 px-3 py-2 font-medium text-red-100 hover:bg-red-300/10">
          Try again
        </button>
      ) : null}
    </div>
  );
}
