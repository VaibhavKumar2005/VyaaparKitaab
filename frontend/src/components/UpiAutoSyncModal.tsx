import { useEffect, useState } from 'react';
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  FileCode2,
  KeyRound,
  Mail,
  RefreshCw,
  Send,
  ShieldCheck,
  Smartphone,
  X,
} from 'lucide-react';
import {
  useRotateUpiBridgeToken,
  useTestUpiBridgeIngest,
  useUpiBridgeConfig,
} from '../hooks/useBankingIncome';

export interface UpiAutoSyncModalProps {
  open: boolean;
  onClose: () => void;
  onSynced?: (summary: string) => void;
}

type BridgeTab = 'android' | 'gmail' | 'ios' | 'takeout';

export function UpiAutoSyncModal({ open, onClose, onSynced }: UpiAutoSyncModalProps) {
  const { data: config, isLoading } = useUpiBridgeConfig(open);
  const rotateMutation = useRotateUpiBridgeToken();
  const testIngestMutation = useTestUpiBridgeIngest();

  const [activeTab, setActiveTab] = useState<BridgeTab>('android');
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
              { id: 'android', label: 'Android (GPay / Paytm / SMS)', icon: Smartphone },
              { id: 'gmail', label: 'Gmail Apps Script', icon: Mail },
              { id: 'ios', label: 'iOS Shortcuts', icon: Smartphone },
              { id: 'takeout', label: 'Google Takeout HTML', icon: FileCode2 },
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
