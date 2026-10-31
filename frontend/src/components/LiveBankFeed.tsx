import React, { useState } from 'react';
import {
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Play,
  Radio,
  ShieldCheck,
  Square,
  Zap,
} from 'lucide-react';
import {
  useBankDemoStreamStatus,
  useEmitBankCredit,
  useIncomeStream,
  useStartBankDemoStream,
  useStopBankDemoStream,
} from '../hooks/useBankingIncome';
import { formatINRPrecise } from '../lib/format';

export function LiveBankFeed() {
  const { data: incomeData } = useIncomeStream();
  const { data: streamStatus } = useBankDemoStreamStatus();
  const startStreamMutation = useStartBankDemoStream();
  const stopStreamMutation = useStopBankDemoStream();
  const emitCreditMutation = useEmitBankCredit();

  const [flashId, setFlashId] = useState<string | null>(null);

  const isRunning = Boolean(streamStatus?.is_running);
  const emittedCount = streamStatus?.emitted_count || 0;

  const handleToggleStream = () => {
    if (isRunning) {
      stopStreamMutation.mutate();
    } else {
      startStreamMutation.mutate(10);
    }
  };

  const handleEmitInstant = () => {
    emitCreditMutation.mutate(undefined, {
      onSuccess: (res: any) => {
        if (res?.txn_id) {
          setFlashId(res.txn_id);
          setTimeout(() => setFlashId(null), 3500);
        }
      },
    });
  };

  const recentItems = incomeData?.recent_inflows || [];

  const getAppBadge = (app: string) => {
    const low = app.toLowerCase();
    if (low.includes('google')) {
      return { label: 'Google Pay', bg: 'bg-blue-50 text-blue-700 border-blue-200' };
    }
    if (low.includes('phonepe')) {
      return { label: 'PhonePe', bg: 'bg-purple-50 text-purple-700 border-purple-200' };
    }
    if (low.includes('paytm')) {
      return { label: 'Paytm', bg: 'bg-sky-50 text-sky-700 border-sky-200' };
    }
    if (low.includes('bhim')) {
      return { label: 'BHIM UPI', bg: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
    }
    return { label: app || 'UPI', bg: 'bg-slate-50 text-slate-700 border-slate-200' };
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
      {/* Header Bar */}
      <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3 bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-600">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
                Live Account Aggregator Feed
              </h3>
              {isRunning ? (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                  Streaming Live (10s)
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  Ready
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Simulates live RBI Account Aggregator inward credit events pushed over SSE into PostgreSQL
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleEmitInstant}
            disabled={emitCreditMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-500 hover:bg-amber-600 text-white shadow-xs transition-colors cursor-pointer disabled:opacity-50"
            title="Immediately emits 1 verified UPI credit without waiting"
          >
            <Zap className="w-3.5 h-3.5 fill-current" />
            {emitCreditMutation.isPending ? 'Emitting...' : 'Emit Test Credit'}
          </button>

          <button
            type="button"
            onClick={handleToggleStream}
            disabled={startStreamMutation.isPending || stopStreamMutation.isPending}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer shadow-xs ${
              isRunning
                ? 'bg-rose-600 hover:bg-rose-700 text-white'
                : 'bg-emerald-600 hover:bg-emerald-700 text-white'
            }`}
          >
            {isRunning ? (
              <>
                <Square className="w-3.5 h-3.5 fill-current" />
                Stop Stream
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                Start Auto Stream
              </>
            )}
          </button>
        </div>
      </div>

      {/* Info Strip */}
      <div className="px-5 py-2.5 bg-slate-50 border-b border-slate-100 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-600">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">Stream Status:</span>
            <span className="font-semibold text-slate-800">
              {isRunning ? 'Active Producer' : 'Idle (Waiting)'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">Emitted in Session:</span>
            <span className="font-semibold text-slate-800">{emittedCount} transactions</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-slate-400">Cadence:</span>
            <span className="font-semibold text-slate-800">10 seconds</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-emerald-700 font-medium">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Idempotent DB Ingestion (UniqueConstraint)</span>
        </div>
      </div>

      {/* Feed List */}
      <div className="divide-y divide-slate-100 max-h-72 overflow-y-auto">
        {recentItems.length === 0 ? (
          <div className="px-5 py-8 text-center text-slate-400 text-xs">
            No bank transactions in live feed yet. Click <strong>"Emit Test Credit"</strong> or{' '}
            <strong>"Start Auto Stream"</strong> to demonstrate live inflow!
          </div>
        ) : (
          recentItems.map((tx) => {
            const badge = getAppBadge(tx.payer_identifier || tx.category || 'UPI');
            const isFlashed = flashId === tx.txn_id;

            return (
              <div
                key={tx.txn_id}
                className={`px-5 py-3 flex items-center justify-between gap-3 text-xs transition-colors ${
                  isFlashed ? 'bg-emerald-50/70 border-l-4 border-emerald-500' : 'hover:bg-slate-50/60'
                }`}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center shrink-0 mt-0.5">
                    <ArrowUpRight className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-slate-900 truncate">
                        {tx.narration}
                      </span>
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${badge.bg}`}
                      >
                        {badge.label}
                      </span>
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                        Verified Credit
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-slate-400 mt-1 text-[11px]">
                      <span className="font-mono text-slate-500">{tx.txn_id}</span>
                      <span>•</span>
                      <span>Account: {tx.masked_acc || 'XXXX-XXXX-4821'}</span>
                      <span>•</span>
                      <span className="inline-flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {tx.date || 'Today'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <div className="text-sm font-semibold text-emerald-600">
                    + {formatINRPrecise(tx.amount)}
                  </div>
                  <div className="text-[10px] text-slate-400 capitalize">
                    {tx.category || 'Inward Credit'}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

