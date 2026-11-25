import React, { useState } from 'react';
import { Check, ChevronDown, ChevronRight, Layers, Pencil, Search, Sparkles, Tag, X } from 'lucide-react';
import {
  useFinancialAssistant,
  useUnifiedTransactions,
  useUpdateUnifiedCategory,
} from '../hooks/useUnifiedLedger';
import { formatDate, formatINR } from '../lib/format';
import { CATEGORY_TAXONOMY, TAXONOMY_CATEGORIES } from '../lib/taxonomy';

interface UnifiedCategoryPanelProps {
  view: 'customer' | 'store' | 'all';
}

const SOURCE_BADGES: Record<string, string> = {
  store_sale: 'Store Sale',
  store_purchase: 'Supplier Bill',
  personal_purchase: 'Receipt / App',
  statement_import: 'Statement',
  account_aggregator: 'AA Feed',
};

const QUICK_QUESTIONS_CUSTOMER = [
  'How much did I spend on food this month?',
  'How much discount did I save?',
  'Show my grocery spending',
];

const QUICK_QUESTIONS_STORE = [
  'How much profit did I make this month?',
  'Which products should I restock?',
  'What is my 7-day forecast?',
];

export function UnifiedCategoryPanel({ view }: UnifiedCategoryPanelProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('');
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({});
  const [question, setQuestion] = useState<string>('');
  const [editingTxId, setEditingTxId] = useState<string | null>(null);
  const [editCat, setEditCat] = useState<string>('Shopping');
  const [editSubcat, setEditSubcat] = useState<string>('General Shopping');

  const fullLedger = useUnifiedTransactions({ view });
  const filteredLedger = useUnifiedTransactions({
    view,
    category: selectedCategory || undefined,
    subcategory: selectedSubcategory || undefined,
  });
  const assistant = useFinancialAssistant();
  const updateCategory = useUpdateUnifiedCategory();

  const toggleExpand = (cat: string) => {
    setExpandedCategories((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const handleAsk = (qText?: string) => {
    const clean = (qText ?? question).trim();
    if (clean.length < 2) return;
    if (qText) setQuestion(clean);
    assistant.mutate(clean);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAsk();
  };

  const tree = fullLedger.data?.category_tree ?? [];
  const items = filteredLedger.data?.items ?? [];
  const quickQuestions = view === 'store' ? QUICK_QUESTIONS_STORE : QUICK_QUESTIONS_CUSTOMER;

  return (
    <div className="space-y-5">
      {/* Ask AI Ledger Assistant */}
      <section className="rounded-xl border border-rule bg-canvas-raised p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-bold text-ink">
              Ask VyaparKitaab AI
            </h2>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {quickQuestions.map((qq) => (
              <button
                key={qq}
                type="button"
                onClick={() => handleAsk(qq)}
                className="rounded-full border border-rule bg-canvas px-2.5 py-1 text-[11px] font-medium text-ink-soft hover:text-ink hover:border-primary transition-colors"
              >
                {qq}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-faint" />
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask e.g. How much did I spend on food this month?"
              className="w-full rounded-lg border border-rule bg-canvas pl-9 pr-3 py-2 text-xs text-ink focus:border-primary focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={assistant.isPending}
            className="rounded-lg bg-navy px-4 py-2 text-xs font-semibold text-white hover:bg-navy/90 disabled:opacity-50"
          >
            {assistant.isPending ? 'Checking...' : 'Ask'}
          </button>
        </form>

        {assistant.isError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            Could not query the financial assistant:{' '}
            {assistant.error instanceof Error ? assistant.error.message : 'Please try again.'}
          </div>
        )}

        {assistant.data && (
          <div className="rounded-lg border border-primary/20 bg-navy-tint/50 p-3 text-xs space-y-1">
            <p className="font-semibold text-ink">{assistant.data.answer}</p>
            <p className="text-[11px] text-ink-soft">
              Scope: {assistant.data.filters.period ?? 'all dates'}
              {assistant.data.filters.category ? ` • ${assistant.data.filters.category}` : ''}
              {assistant.data.filters.subcategory ? ` > ${assistant.data.filters.subcategory}` : ''}
            </p>
          </div>
        )}
      </section>

      {/* Summary Bar */}
      <section className="grid gap-4 sm:grid-cols-4">
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Unified Transactions</p>
          <p className="num mt-1.5 text-xl font-bold text-ink">{fullLedger.data?.total_count ?? 0}</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Total Volume</p>
          <p className="num mt-1.5 text-xl font-bold text-ink">{formatINR(fullLedger.data?.total_amount ?? 0)}</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Discounts Saved</p>
          <p className="num mt-1.5 text-xl font-bold text-positive">{formatINR(fullLedger.data?.total_discount_saved ?? 0)}</p>
        </div>
        <div className="rounded-lg border border-rule bg-canvas-raised p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-soft">Top Category</p>
          <p className="mt-1.5 text-base font-bold text-navy truncate">{tree[0]?.category ?? 'None yet'}</p>
        </div>
      </section>

      {/* Hierarchical Category -> Subcategory Breakdown + Normalized Ledger */}
      <section className="grid gap-5 lg:grid-cols-12">
        <div className="lg:col-span-5 rounded-xl border border-rule bg-canvas-raised p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-ink flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" /> Category &amp; Subcategory Tree
            </h3>
            {(selectedCategory || selectedSubcategory) && (
              <button
                type="button"
                onClick={() => {
                  setSelectedCategory('');
                  setSelectedSubcategory('');
                }}
                className="text-[11px] font-semibold text-primary hover:underline"
              >
                Clear filter
              </button>
            )}
          </div>

          {fullLedger.isPending ? (
            <p className="text-xs text-ink-soft py-4">Loading unified categories...</p>
          ) : tree.length === 0 ? (
            <p className="text-xs text-ink-soft py-4">No categorized transactions recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {tree.map((catNode) => {
                const isExpanded = expandedCategories[catNode.category] ?? true;
                const isSelected = selectedCategory === catNode.category && !selectedSubcategory;
                return (
                  <div key={catNode.category} className="rounded-lg border border-rule bg-canvas p-2.5 space-y-1.5">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => toggleExpand(catNode.category)}
                        className="flex items-center gap-1.5 font-bold text-ink hover:text-primary"
                      >
                        {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        <span>{catNode.category}</span>
                        <span className="text-[10px] font-normal text-ink-faint">({catNode.count})</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCategory(isSelected ? '' : catNode.category);
                          setSelectedSubcategory('');
                        }}
                        className={`num font-bold ${isSelected ? 'text-primary underline' : 'text-ink'}`}
                      >
                        {formatINR(catNode.total_amount)} ({catNode.percentage}%)
                      </button>
                    </div>

                    {isExpanded && catNode.subcategories.length > 0 && (
                      <div className="pl-5 space-y-1 border-l border-rule ml-1.5">
                        {catNode.subcategories.map((sub) => {
                          const subActive =
                            selectedCategory === catNode.category && selectedSubcategory === sub.subcategory;
                          return (
                            <button
                              key={sub.subcategory}
                              type="button"
                              onClick={() => {
                                if (subActive) {
                                  setSelectedCategory('');
                                  setSelectedSubcategory('');
                                } else {
                                  setSelectedCategory(catNode.category);
                                  setSelectedSubcategory(sub.subcategory);
                                }
                              }}
                              className={`w-full flex items-center justify-between rounded px-2 py-1 text-[11px] transition-colors ${
                                subActive
                                  ? 'bg-navy-tint text-primary font-semibold'
                                  : 'text-ink-soft hover:bg-canvas-sunk hover:text-ink'
                              }`}
                            >
                              <span>{sub.subcategory} ({sub.count})</span>
                              <span className="num font-medium">
                                {formatINR(sub.total_amount)} • {sub.percentage}%
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="lg:col-span-7 rounded-xl border border-rule bg-canvas-raised overflow-hidden">
          <div className="px-4 py-3 border-b border-rule flex items-center justify-between">
            <h3 className="text-sm font-bold text-ink flex items-center gap-2">
              <Tag className="h-4 w-4 text-primary" />
              Normalized Ledger
              {selectedCategory ? ` (${selectedCategory}${selectedSubcategory ? ` > ${selectedSubcategory}` : ''})` : ''}
            </h3>
            <span className="text-[11px] text-ink-soft">{items.length} shown</span>
          </div>

          {items.length === 0 ? (
            <p className="p-6 text-xs text-ink-soft">No matching transactions for the selected filter.</p>
          ) : (
            <div className="overflow-x-auto max-h-[420px]">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-canvas-sunk text-left text-[11px] font-semibold uppercase text-ink-soft">
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Counterparty / Source</th>
                    <th className="px-3 py-2">Category</th>
                    <th className="px-3 py-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {items.slice(0, 40).map((tx) => {
                    const srcLabel = tx.source_type.startsWith('upi_bridge')
                      ? 'UPI Bridge'
                      : (SOURCE_BADGES[tx.source_type] ?? tx.source_type);
                    return (
                      <tr key={tx.id} className="hover:bg-canvas-sunk/40">
                        <td className="px-3 py-2 text-ink-soft whitespace-nowrap">
                          {formatDate(tx.occurred_at)}
                        </td>
                        <td className="px-3 py-2">
                          <div className="font-semibold text-ink">{tx.counterparty}</div>
                          <div className="text-[10px] text-ink-faint flex items-center gap-1.5">
                            <span>{srcLabel}</span>
                            <span>•</span>
                            <span>{tx.app || tx.channel}</span>
                            {tx.discount_amount > 0 && (
                              <span className="text-positive font-semibold">
                                • Saved {formatINR(tx.discount_amount)}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          {editingTxId === tx.id ? (
                            <div className="flex flex-wrap items-center gap-1">
                              <select
                                aria-label="Edit category"
                                value={editCat}
                                onChange={(e) => {
                                  const next = e.target.value;
                                  setEditCat(next);
                                  const subs = CATEGORY_TAXONOMY[next] ?? ['General'];
                                  setEditSubcat(subs[subs.length - 1]);
                                }}
                                className="rounded border border-rule bg-canvas px-1.5 py-0.5 text-[11px] text-ink"
                              >
                                {TAXONOMY_CATEGORIES.map((c) => (
                                  <option key={c} value={c}>{c}</option>
                                ))}
                              </select>
                              <select
                                aria-label="Edit subcategory"
                                value={editSubcat}
                                onChange={(e) => setEditSubcat(e.target.value)}
                                className="rounded border border-rule bg-canvas px-1.5 py-0.5 text-[11px] text-ink"
                              >
                                {(CATEGORY_TAXONOMY[editCat] ?? ['General']).map((sub) => (
                                  <option key={sub} value={sub}>{sub}</option>
                                ))}
                              </select>
                              <button
                                type="button"
                                disabled={updateCategory.isPending}
                                onClick={() => {
                                  updateCategory.mutate(
                                    { transactionId: tx.id, category: editCat, subcategory: editSubcat },
                                    { onSuccess: () => setEditingTxId(null) },
                                  );
                                }}
                                className="rounded bg-primary p-1 text-white hover:bg-primary-deep disabled:opacity-50"
                                title="Save category"
                              >
                                <Check className="h-3 w-3" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setEditingTxId(null)}
                                className="rounded border border-rule p-1 text-ink-soft hover:text-ink"
                                title="Cancel"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setEditingTxId(tx.id);
                                const safeCat = CATEGORY_TAXONOMY[tx.category] ? tx.category : 'Other';
                                setEditCat(safeCat);
                                const validSubs = CATEGORY_TAXONOMY[safeCat] ?? ['General'];
                                setEditSubcat(
                                  validSubs.includes(tx.subcategory) ? tx.subcategory : validSubs[validSubs.length - 1],
                                );
                              }}
                              className="group text-left hover:text-primary"
                              title="Click to recategorize and teach the AI classifier"
                            >
                              <span className="font-medium text-ink inline-flex items-center gap-1 group-hover:text-primary">
                                {tx.category}
                                <Pencil className="h-2.5 w-2.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                              </span>
                              <div className="text-[10px] text-ink-soft">
                                {tx.subcategory}
                                {tx.classification_source === 'user_learned' && (
                                  <span className="ml-1 rounded bg-emerald-50 px-1 text-[9px] font-semibold text-emerald-700">
                                    Learned
                                  </span>
                                )}
                              </div>
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right num font-bold text-ink whitespace-nowrap">
                          {formatINR(tx.amount)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
