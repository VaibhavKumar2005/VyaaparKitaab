import { useEffect, useState } from 'react';
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  FileCode2,
  KeyRound,
  Mail,
  MessageSquareText,
  RefreshCw,
  Send,
  ShieldCheck,
  Smartphone,
  X,
} from 'lucide-react';
import {
  type SmsBatchImportResult,
  useImportSmsMessages,
  useRotateUpiBridgeToken,
  useTestUpiBridgeIngest,
  useUpiBridgeConfig,
} from '../hooks/useBankingIncome';

export interface UpiAutoSyncModalProps {
  open: boolean;
  onClose: () => void;
  onSynced?: (summary: string) => void;
}

type BridgeTab = 'sms_paste' | 'android' | 'gmail' | 'ios' | 'takeout';

const SAMPLE_BANK_SMS_BATCH = [
  'AD-HDFCBK: Sent Rs.485.50 From HDFC Bank A/C *4821 To SWIGGY On 22/11/26 Ref 432610011223. Avl Bal: Rs 45,200.00',
  'VM-SBIUPI: Dear UPI user A/C X3421 debited by 640.0 on date 23Nov26 trf to INDIANOIL Refno 432710022334',
  'JX-ICICIB: ICICI Bank Acct XX1029 debited for Rs 1299.00 on 24-Nov-26; BLINKIT credited. UPI:432810033445. Avl Bal: INR 18,900.00',
  'AX-AXISBK: INR 3450.00 credited to A/c no. XX9912 on 25-Nov-26. Info- UPI/CR/432910044556/RAHUL SHARMA',
  'AD-HDFCBK: 849201 is your OTP for Rs 5,000 txn. Do not share OTP with anyone.',
].join('\n\n');

export function UpiAutoSyncModal({ open, onClose, onSynced }: UpiAutoSyncModalProps) {
  const { data: config, isLoading } = useUpiBridgeConfig(open);
  const rotateMutation = useRotateUpiBridgeToken();
  const testIngestMutation = useTestUpiBridgeIngest();
  const smsImportMutation = useImportSmsMessages();

  const [activeTab, setActiveTab] = useState<BridgeTab>('sms_paste');
  const [smsDraft, setSmsDraft] = useState('');
  const [smsPreview, setSmsPreview] = useState<SmsBatchImportResult | null>(null);
  const [revealToken, setRevealToken] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const token = config?.ingest_token ?? '';
  const templates = config?.templates;

  const copyText = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } catch {
      setFeedback('Copy failed—please copy manually from the box.');
    }
  };

  const handleRotate = () => {
    rotateMutation.mutate(undefined, {
      onSuccess: () => {
        setFeedback('Scoped ingest token rotated. Previous device/script tokens are now revoked.');
      },
    });
  };

  const handleTestWebhook = (preset: 'gpay' | 'paytm') => {
    if (!token) return;
    const payload =
      preset === 'gpay'
        ? {
            ingestToken: token,
            app_package: 'com.google.android.apps.nbu.paisa.user',
            title: 'Paid ₹450.00 to Blue Tokai Coffee',
            message: 'Paid using HDFC Bank A/C XX4821. UPI Ref: 431789123456',
            source_channel: 'android_notification',
          }
        : {
            ingestToken: token,
            app_package: 'net.one97.paytm',
            title: 'Money Received! ₹1,250.00 credited',
            message: 'Received from Rahul Sharma (rahul@paytm) via Paytm UPI Ref 431711223344',
            source_channel: 'android_notification',
          };

    testIngestMutation.mutate(payload, {
      onSuccess: (res) => {
        const msg = res.transaction
          ? `Synced ${res.transaction.app} ${res.transaction.type}: ₹${res.transaction.amount} (${res.transaction.counterparty})`
          : `Webhook response: ${res.reason ?? res.status}`;
        setFeedback(msg);
        onSynced?.(msg);
      },
      onError: (err) => {
        setFeedback(err instanceof Error ? err.message : 'Test webhook failed');
      },
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 p-4 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-label="Zero-Credential GPay and Paytm Auto-Sync Bridge"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl rounded-2xl border border-rule bg-canvas-raised p-5 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between border-b border-rule pb-3">
          <div className="flex items-center gap-2.5">
            <div className="rounded-xl bg-emerald-600 p-2 text-white">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-ink">
                Auto-Sync Google Pay &amp; Paytm (Zero Credentials)
              </h3>
              <p className="text-[11px] text-ink-soft">
                Push transaction notifications directly from your phone or Gmail—never share bank passwords, UPI PINs, or Google OAuth tokens.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-ink-soft hover:bg-canvas-sunk hover:text-ink"
            aria-label="Close modal"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Scoped Token + Privacy Controls */}
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3.5 space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-950">
              <KeyRound className="h-4 w-4 text-emerald-700" />
              <span>Scoped X-Ingest-Token (Write-Only • Instant Revoke)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setRevealToken((v) => !v)}
                className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-white px-2 py-1 text-[11px] font-semibold text-emerald-900 hover:bg-emerald-50"
              >
                {revealToken ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                {revealToken ? 'Hide' : 'Reveal'}
              </button>
              <button
                type="button"
                disabled={!token}
                onClick={() => void copyText('token', token)}
                className="inline-flex items-center gap-1 rounded border border-emerald-300 bg-white px-2 py-1 text-[11px] font-semibold text-emerald-900 hover:bg-emerald-50"
              >
                {copiedKey === 'token' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copiedKey === 'token' ? 'Copied' : 'Copy Token'}
              </button>
              <button
                type="button"
                onClick={handleRotate}
                disabled={rotateMutation.isPending}
                className="inline-flex items-center gap-1 rounded bg-emerald-700 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-emerald-800"
              >
                <RefreshCw className={`h-3 w-3 ${rotateMutation.isPending ? 'animate-spin' : ''}`} />
                Rotate Token
              </button>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-lg bg-white/90 border border-emerald-200 px-3 py-2 text-xs font-mono text-ink">
            <span className="truncate">
              {isLoading ? 'Loading scoped bridge token…' : revealToken ? token : config?.masked_token}
            </span>
            <span className="text-[10px] font-sans font-semibold text-emerald-800 shrink-0">
              OTPs &amp; 13+ digit card/A/c numbers auto-scrubbed
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-emerald-900">
            <span>
              Synced alerts: <strong>{config?.ingest_count ?? 0}</strong>
              {config?.last_app ? ` • Last: ${config.last_app}` : ''}
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                disabled={!token || testIngestMutation.isPending}
                onClick={() => handleTestWebhook('gpay')}
                className="inline-flex items-center gap-1 rounded bg-navy px-2.5 py-1 text-[11px] font-bold text-white hover:bg-navy-dark"
              >
                <Send className="h-3 w-3" />
                Test GPay Debit
              </button>
              <button
                type="button"
                disabled={!token || testIngestMutation.isPending}
                onClick={() => handleTestWebhook('paytm')}
                className="inline-flex items-center gap-1 rounded border border-navy bg-white px-2.5 py-1 text-[11px] font-bold text-navy hover:bg-navy-tint"
              >
                <Send className="h-3 w-3" />
                Test Paytm Credit
              </button>
            </div>
          </div>
        </div>

        {feedback && (
          <div className="rounded-lg border border-navy/25 bg-navy-tint px-3 py-2 text-xs font-semibold text-navy">
            {feedback}
          </div>
        )}

        {/* Horizontal Platform Tabs (Keeps Modal Compact & Un-Stacked) */}
        <div className="flex flex-wrap gap-1 rounded-xl border border-rule bg-canvas-sunk p-1">
          {(
            [
              { id: 'sms_paste', label: 'Paste Bank SMS', icon: MessageSquareText },
              { id: 'android', label: 'Android Auto-Forward', icon: Smartphone },
              { id: 'gmail', label: 'Gmail Apps Script', icon: Mail },
              { id: 'ios', label: 'iOS Shortcuts', icon: Smartphone },
              { id: 'takeout', label: 'Google Takeout', icon: FileCode2 },
            ] as const
          ).map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold transition-all ${
                  activeTab === tab.id
                    ? 'bg-navy text-white shadow-xs'
                    : 'text-ink-soft hover:bg-canvas hover:text-ink'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tab Body */}
        {activeTab === 'sms_paste' && (
          <div className="space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-ink-soft">
                Paste real <strong className="text-ink">HDFC, SBI, ICICI, Axis, Kotak, GPay, PhonePe, or Paytm</strong> transaction SMS messages (one per line or blank-line separated). OTPs, PINs, account/card numbers, PAN, URLs, and bank balances are automatically stripped before saving.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSmsDraft(SAMPLE_BANK_SMS_BATCH);
                  setSmsPreview(null);
                }}
                className="rounded border border-navy/30 bg-navy-tint px-2.5 py-1 text-[11px] font-semibold text-navy hover:bg-navy hover:text-white transition-colors"
              >
                Load Sample SMS Batch
              </button>
            </div>

            <textarea
              rows={5}
              value={smsDraft}
              onChange={(e) => {
                setSmsDraft(e.target.value);
                setSmsPreview(null);
              }}
              placeholder="Paste bank / UPI transaction SMS messages here (e.g. AD-HDFCBK: Sent Rs.450.00 From HDFC Bank A/C *1234 To SWIGGY On 26/11/26 Ref 432910293847)…"
              className="w-full rounded-lg border border-rule bg-canvas p-3 font-mono text-[11px] text-ink outline-none focus:border-navy"
            />

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!smsDraft.trim() || smsImportMutation.isPending}
                onClick={() => {
                  smsImportMutation.mutate(
                    { raw_text: smsDraft, dry_run: true },
                    {
                      onSuccess: (res) => {
                        setSmsPreview(res);
                        setFeedback(
                          `Preview ready: ${res.imported_count} valid txns (${res.credits_count} credit, ${res.debits_count} debit), ${res.ignored_count} OTP/spam/failed blocked.`,
                        );
                      },
                      onError: (err) => setFeedback(err instanceof Error ? err.message : 'Preview failed'),
                    },
                  );
                }}
                className="rounded-lg border border-navy bg-canvas px-3 py-1.5 font-bold text-navy hover:bg-navy-tint disabled:opacity-50"
              >
                {smsImportMutation.isPending ? 'Scanning…' : 'Preview & Scrub (Dry Run)'}
              </button>

              <button
                type="button"
                disabled={!smsDraft.trim() || smsImportMutation.isPending}
                onClick={() => {
                  smsImportMutation.mutate(
                    { raw_text: smsDraft, dry_run: false },
                    {
                      onSuccess: (res) => {
                        setSmsPreview(res);
                        const summary = `Streamlined ${res.imported_count} SMS transactions (${res.credits_count} credits, ${res.debits_count} debits) into Ledger & Time Series (${res.ignored_count} OTP/spam blocked).`;
                        setFeedback(summary);
                        onSynced?.(summary);
                      },
                      onError: (err) => setFeedback(err instanceof Error ? err.message : 'SMS import failed'),
                    },
                  );
                }}
                className="rounded-lg bg-emerald-600 px-3.5 py-1.5 font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {smsImportMutation.isPending ? 'Importing…' : 'Streamline into Ledger & Time Series'}
              </button>
            </div>

            {smsPreview && smsPreview.transactions.length > 0 && (
              <div className="rounded-lg border border-rule bg-canvas overflow-x-auto max-h-48">
                <table className="min-w-full text-[11px]">
                  <thead className="bg-canvas-sunk border-b border-rule text-left text-ink-soft">
                    <tr>
                      <th className="px-2.5 py-1.5">Date</th>
                      <th className="px-2.5 py-1.5">Bank / App</th>
                      <th className="px-2.5 py-1.5">Party &amp; Scrubbed Text</th>
                      <th className="px-2.5 py-1.5">Category</th>
                      <th className="px-2.5 py-1.5 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-rule">
                    {smsPreview.transactions.map((t) => (
                      <tr key={t.txn_id}>
                        <td className="px-2.5 py-1.5 font-mono text-ink-soft whitespace-nowrap">{t.date}</td>
                        <td className="px-2.5 py-1.5 font-semibold text-ink whitespace-nowrap">{t.app}</td>
                        <td className="px-2.5 py-1.5 text-ink">
                          <div className="font-semibold">{t.counterparty}</div>
                          <div className="text-[10px] text-ink-soft truncate max-w-xs">{t.narration}</div>
                        </td>
                        <td className="px-2.5 py-1.5 text-ink-soft whitespace-nowrap">
                          {t.category} › {t.subcategory}
                        </td>
                        <td
                          className={`num px-2.5 py-1.5 text-right font-bold whitespace-nowrap ${
                            t.type === 'CREDIT' ? 'text-emerald-700' : 'text-rose-700'
                          }`}
                        >
                          {t.type === 'CREDIT' ? '+' : '-'}₹{t.amount.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'android' && templates && (
          <div className="space-y-3 text-xs text-ink-soft">
            <p className="leading-relaxed">
              Use an open-source Android notification forwarder (like{' '}
              <strong className="text-ink">Notification2Webhook</strong> or <strong className="text-ink">MacroDroid</strong>) to forward{' '}
              <em>only</em> payment notifications from these package names:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {templates.supported_packages.map((pkg) => (
                <span key={pkg} className="rounded-md border border-rule bg-canvas px-2 py-1 font-mono text-[11px] text-ink">
                  {pkg}
                </span>
              ))}
            </div>
            <div className="rounded-lg border border-rule bg-canvas p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-ink">POST {templates.full_webhook_url}</span>
                <button
                  type="button"
                  onClick={() => void copyText('android_json', templates.android_payload_template)}
                  className="inline-flex items-center gap-1 rounded border border-rule bg-canvas-raised px-2 py-0.5 text-[11px] font-semibold text-ink hover:bg-canvas-sunk"
                >
                  {copiedKey === 'android_json' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                  Copy JSON
                </button>
              </div>
              <pre className="overflow-x-auto rounded bg-slate-950 p-2.5 text-[11px] text-emerald-300">
                {templates.android_payload_template}
              </pre>
            </div>
          </div>
        )}

        {activeTab === 'gmail' && templates && (
          <div className="space-y-3 text-xs text-ink-soft">
            <p className="leading-relaxed">
              Paste this script in <strong className="text-ink">script.google.com</strong> (inside your own Google account) on a 5-minute time trigger.
              It reads <strong className="text-ink">googlepay-noreply@google.com</strong> &amp; <strong className="text-ink">alerts@paytm.com</strong> directly in your Google Workspace and scrubs long numbers before calling VyaparKitaab—so no Gmail OAuth token ever touches our backend.
            </p>
            <div className="rounded-lg border border-rule bg-canvas p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-ink">syncUpiAlertsToVyaparKitaab.gs</span>
                <button
                  type="button"
                  onClick={() => void copyText('apps_script', templates.gmail_apps_script)}
                  className="inline-flex items-center gap-1 rounded border border-rule bg-canvas-raised px-2 py-0.5 text-[11px] font-semibold text-ink hover:bg-canvas-sunk"
                >
                  {copiedKey === 'apps_script' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                  Copy Apps Script
                </button>
              </div>
              <pre className="max-h-52 overflow-auto rounded bg-slate-950 p-2.5 text-[11px] text-sky-200">
                {templates.gmail_apps_script}
              </pre>
            </div>
          </div>
        )}

        {activeTab === 'ios' && templates && (
          <div className="space-y-2.5 text-xs text-ink-soft">
            <p className="leading-relaxed">
              iOS isolates app notifications, so bank SMS + Apple Shortcuts is the official zero-credential path on iPhone:
            </p>
            <ol className="list-decimal list-inside space-y-1.5 rounded-lg border border-rule bg-canvas p-3 text-ink">
              {templates.ios_shortcut_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
        )}

        {activeTab === 'takeout' && (
          <div className="space-y-2.5 text-xs text-ink-soft rounded-lg border border-rule bg-canvas p-3.5">
            <p className="font-bold text-ink">Google Takeout GPay History (100% Official Export)</p>
            <ol className="list-decimal list-inside space-y-1.5">
              <li>Visit <strong>takeout.google.com</strong>, deselect all, and select only <strong>Google Pay</strong>.</li>
              <li>Unzip the archive and locate <code className="font-mono text-navy">Google Pay/My Activity/My Activity.html</code> (or JSON/CSV).</li>
              <li>Click <strong>Upload Statement</strong> in VyaparKitaab and upload that <code className="font-mono text-navy">.html</code> file directly—no credentials required.</li>
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
