/**
 * Payment state derived from amounts, not just the status enum, so a part-paid
 * invoice isn't shown as fully unpaid. The text label carries the meaning;
 * colour is only reinforcement.
 */
export function paymentState(inv: { status: string; total_amount: number; paid_amount: number }) {
  if (inv.status === 'CANCELLED') return 'Cancelled' as const;
  if (inv.status === 'DRAFT') return 'Draft' as const;
  if (inv.paid_amount >= inv.total_amount && inv.total_amount > 0) return 'Paid' as const;
  if (inv.paid_amount > 0) return 'Part paid' as const;
  return 'Unpaid' as const;
}

const styles: Record<string, string> = {
  Paid: 'bg-positive-tint text-positive',
  'Part paid': 'bg-navy-tint text-navy',
  Unpaid: 'bg-due-tint text-due',
  Draft: 'bg-canvas-sunk text-ink-soft',
  Cancelled: 'bg-canvas-sunk text-ink-faint',
};

export function StatusPill({ state }: { state: string }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles[state] ?? styles.Draft}`}>
      {state}
    </span>
  );
}

