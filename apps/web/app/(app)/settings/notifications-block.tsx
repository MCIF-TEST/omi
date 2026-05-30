'use client';

import { useEffect, useState } from 'react';
import { Mail, Webhook, Check, AlertCircle, Loader2 } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError, type NotificationPrefs } from '@/lib/api';

export function NotificationsBlock() {
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [webhookInput, setWebhookInput] = useState('');

  useEffect(() => {
    setPending(true);
    apiClient<NotificationPrefs>('/v1/auth/notifications')
      .then((p) => {
        setPrefs(p);
        setWebhookInput(p.webhook_url || '');
      })
      .catch((e) => setErr(e instanceof ApiError ? e.message : 'Failed to load preferences.'))
      .finally(() => setPending(false));
  }, []);

  async function update(partial: Partial<NotificationPrefs>) {
    setSaving(true);
    setErr(null);
    try {
      const body: Record<string, unknown> = {};
      if (partial.email_enabled !== undefined) body.email_enabled = partial.email_enabled;
      if (partial.webhook_enabled !== undefined) body.webhook_enabled = partial.webhook_enabled;
      if (partial.webhook_url !== undefined) body.webhook_url = partial.webhook_url;
      const updated = await apiClient<NotificationPrefs>('/v1/auth/notifications', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      setPrefs(updated);
      setWebhookInput(updated.webhook_url || '');
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt((t) => (t === Date.now() ? null : t)), 2200);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  }

  if (pending) {
    return (
      <Card>
        <CardLabel>Alert notifications</CardLabel>
        <div className="flex items-center gap-2 text-fg-dim text-sm">
          <Loader2 size={14} className="animate-spin" /> Loading preferences…
        </div>
      </Card>
    );
  }

  if (!prefs) {
    return (
      <Card>
        <CardLabel>Alert notifications</CardLabel>
        <p className="text-sm text-tier-high">{err || 'Could not load preferences.'}</p>
      </Card>
    );
  }

  return (
    <Card>
      <CardLabel>Alert notifications</CardLabel>
      <CardTitle>How OMISPHERE reaches you when watchlists fire</CardTitle>
      <p className="text-sm text-fg-dim mb-5 max-w-xl">
        Alerts trigger when a watched account or narrative crosses your tier threshold.
        Email goes to <span className="text-fg font-mono">{prefs.email}</span>.
        Webhook is fired as a JSON POST to any URL you provide — useful for Slack, Discord,
        or your own automation.
      </p>

      <div className="space-y-4">
        {/* Email toggle */}
        <Toggle
          icon={<Mail size={14} />}
          label="Email notifications"
          subtitle={`Delivered to ${prefs.email}`}
          enabled={prefs.email_enabled}
          disabled={saving}
          onChange={(enabled) => update({ email_enabled: enabled })}
        />

        {/* Webhook toggle + URL */}
        <div className="space-y-2">
          <Toggle
            icon={<Webhook size={14} />}
            label="Webhook notifications"
            subtitle="POST JSON payload to a URL you control"
            enabled={prefs.webhook_enabled}
            disabled={saving || !prefs.webhook_url}
            onChange={(enabled) => update({ webhook_enabled: enabled })}
          />
          <div className="pl-7 flex items-stretch gap-2">
            <input
              aria-label="Webhook URL"
              type="url"
              value={webhookInput}
              onChange={(e) => setWebhookInput(e.target.value)}
              placeholder="https://hooks.slack.com/services/…"
              disabled={saving}
              className="flex-1 px-3 py-2 bg-bg border border-border-2 rounded-sm text-sm text-fg font-mono placeholder:text-fg-mute focus:outline-none focus:border-accent"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => update({ webhook_url: webhookInput })}
              disabled={saving || webhookInput === (prefs.webhook_url || '')}
            >
              Save URL
            </Button>
          </div>
          <p className="pl-7 font-mono text-2xs text-fg-mute leading-relaxed">
            Payload format: <span className="text-fg">{`{ alert_id, kind, severity, message, payload, watchlist }`}</span>.
            Saving a URL turns webhook notifications on automatically.
          </p>
        </div>
      </div>

      {/* Status row */}
      <div className="mt-5 flex items-center gap-3 min-h-[1.5rem]">
        {savedAt && !err && (
          <span className="inline-flex items-center gap-1 font-mono text-2xs text-tier-low">
            <Check size={11} /> Saved
          </span>
        )}
        {saving && (
          <span className="inline-flex items-center gap-1 font-mono text-2xs text-fg-mute">
            <Loader2 size={11} className="animate-spin" /> Saving…
          </span>
        )}
        {err && (
          <span className="inline-flex items-center gap-1 font-mono text-2xs text-tier-high">
            <AlertCircle size={11} /> {err}
          </span>
        )}
      </div>
    </Card>
  );
}

function Toggle({
  icon,
  label,
  subtitle,
  enabled,
  disabled,
  onChange,
}: {
  icon: React.ReactNode;
  label: string;
  subtitle?: string;
  enabled: boolean;
  disabled?: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => !disabled && onChange(!enabled)}
        disabled={disabled}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors shrink-0 ${
          enabled ? 'bg-accent' : 'bg-border-2'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
        aria-label={`Toggle ${label}`}
        aria-pressed={enabled}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-bg-deep transition-transform ${
            enabled ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-fg text-sm font-medium">
          {icon}
          {label}
        </div>
        {subtitle && <div className="text-2xs text-fg-mute font-mono">{subtitle}</div>}
      </div>
    </div>
  );
}
