'use client';

import { useEffect, useState } from 'react';
import { Tag, Check, AlertCircle, Loader2, Trash2 } from 'lucide-react';
import {
  apiClient, ApiError,
  type AccountLabel, type AccountLabelsResponse,
  LABEL_KINDS, LABEL_CONFIDENCES, LABEL_TIERS,
} from '@/lib/api';

interface Props {
  platform: string;
  externalId: string;
}

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; existing: AccountLabel | null }
  | { kind: 'saving' }
  | { kind: 'saved'; existing: AccountLabel }
  | { kind: 'error'; message: string };

const LABEL_DISPLAY: Record<string, { label: string; hint: string }> = {
  bot:              { label: 'Bot',              hint: 'Pure automation — no human in the loop.' },
  human:            { label: 'Human',            hint: 'Real person, organic behavior.' },
  unclear:          { label: 'Unclear',          hint: 'Genuinely ambiguous; flagged for review.' },
  commercial_spam:  { label: 'Commercial spam',  hint: 'Affiliate / promotional / dropshipping.' },
  political_coord:  { label: 'Political coord',  hint: 'Astroturfing or coordinated political messaging.' },
  engagement_farm:  { label: 'Engagement farm',  hint: 'Like-for-like or follow-farming network.' },
  ai_content:       { label: 'AI content',       hint: 'LLM-generated comments / posts.' },
  suspended:        { label: 'Suspended',        hint: 'Platform took action (closed / banned).' },
};

/**
 * Ground-truth label widget. Admin-only — non-admins see nothing.
 *
 * The label says what the OPERATOR thinks this account actually is, and
 * what tier the engine SHOULD have returned. Feeds directly into the
 * calibration harness via /v1/labels/calibration/evaluate.
 */
export function LabelWidget({ platform, externalId }: Props) {
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [form, setForm] = useState({
    label: 'unclear' as typeof LABEL_KINDS[number],
    expected_tier: 'moderate' as typeof LABEL_TIERS[number],
    confidence: 'medium' as typeof LABEL_CONFIDENCES[number],
    rationale: '',
  });

  // On mount, see if this account already has a label from the current user.
  useEffect(() => {
    apiClient<AccountLabelsResponse>('/v1/labels?limit=500')
      .then((res) => {
        const existing = res.labels.find(
          (l) => l.platform === platform && l.external_id === externalId,
        );
        if (existing) {
          setForm({
            label: existing.label,
            expected_tier: existing.expected_tier,
            confidence: existing.confidence,
            rationale: existing.rationale || '',
          });
        }
        setState({ kind: 'ready', existing: existing ?? null });
      })
      .catch((err) => {
        // Forbidden = not admin; render nothing rather than an error.
        if (err instanceof ApiError && err.status === 403) {
          setState({ kind: 'error', message: '__not_admin__' });
          return;
        }
        setState({
          kind: 'error',
          message: err instanceof ApiError ? err.message : 'Failed to load labels',
        });
      });
  }, [platform, externalId]);

  async function save() {
    setState({ kind: 'saving' });
    try {
      const saved = await apiClient<AccountLabel>('/v1/labels', {
        method: 'POST',
        body: JSON.stringify({
          platform,
          external_id: externalId,
          label: form.label,
          expected_tier: form.expected_tier,
          confidence: form.confidence,
          rationale: form.rationale || null,
        }),
      });
      setState({ kind: 'saved', existing: saved });
      // After a moment, settle back to 'ready' so the form is reusable.
      setTimeout(() => setState({ kind: 'ready', existing: saved }), 1800);
    } catch (err) {
      setState({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Save failed',
      });
    }
  }

  async function remove() {
    if (state.kind !== 'ready' || !state.existing) return;
    const id = state.existing.id;
    setState({ kind: 'saving' });
    try {
      await apiClient(`/v1/labels/${id}`, { method: 'DELETE' });
      setForm({
        label: 'unclear',
        expected_tier: 'moderate',
        confidence: 'medium',
        rationale: '',
      });
      setState({ kind: 'ready', existing: null });
    } catch (err) {
      setState({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Delete failed',
      });
    }
  }

  // Hide entirely for non-admins.
  if (state.kind === 'error' && state.message === '__not_admin__') return null;

  if (state.kind === 'loading') return null;

  return (
    <div className="bg-bg-elev/40 border border-accent/30 rounded-md p-4">
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Tag size={13} className="text-accent" />
          <h3 className="font-mono text-2xs tracking-[0.18em] text-accent uppercase">
            Ground-truth label (admin)
          </h3>
        </div>
        {state.kind === 'ready' && state.existing && (
          <div className="flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-mute">
            <span className="px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-dim">
              source: {state.existing.source.replace('_', ' ')}
            </span>
            <button
              type="button"
              onClick={remove}
              className="inline-flex items-center gap-1 text-tier-high hover:text-tier-high/80"
              aria-label="Remove label"
            >
              <Trash2 size={11} />
              clear
            </button>
          </div>
        )}
      </div>

      <p className="text-xs text-fg-dim mb-4 leading-relaxed">
        Disagree with what the engine returned? Label this account so the
        calibration harness can score the engine against your judgment. Stored
        as ground truth — feeds the <code className="font-mono text-accent">/v1/labels/calibration/evaluate</code> endpoint.
      </p>

      {/* Label kind */}
      <div className="mb-3">
        <label className="block font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">
          What is this account?
        </label>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
          {LABEL_KINDS.map((k) => {
            const active = form.label === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => setForm((f) => ({ ...f, label: k }))}
                className={`text-left px-2.5 py-1.5 rounded-sm border font-mono text-2xs uppercase tracking-wider transition-colors ${
                  active
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot'
                }`}
                title={LABEL_DISPLAY[k]?.hint}
              >
                {LABEL_DISPLAY[k]?.label || k}
              </button>
            );
          })}
        </div>
      </div>

      {/* Expected tier + confidence */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="block font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">
            Engine should have returned
          </label>
          <select
            value={form.expected_tier}
            onChange={(e) => setForm((f) => ({ ...f, expected_tier: e.target.value as any }))}
            className="w-full bg-bg border border-border-1 rounded-sm px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
          >
            {LABEL_TIERS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">
            How sure are you?
          </label>
          <select
            value={form.confidence}
            onChange={(e) => setForm((f) => ({ ...f, confidence: e.target.value as any }))}
            className="w-full bg-bg border border-border-1 rounded-sm px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
          >
            {LABEL_CONFIDENCES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Rationale */}
      <div className="mb-3">
        <label className="block font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1.5">
          Rationale <span className="text-fg-faint normal-case tracking-normal">(optional but useful)</span>
        </label>
        <textarea
          value={form.rationale}
          onChange={(e) => setForm((f) => ({ ...f, rationale: e.target.value }))}
          placeholder="e.g. Posts every 15 min, 24/7, identical promo-code template. Reviewed 200 of their comments."
          rows={2}
          className="w-full bg-bg border border-border-1 rounded-sm px-2.5 py-2 text-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent resize-y"
        />
      </div>

      {/* Save bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={save}
          disabled={state.kind === 'saving' || state.kind === 'saved'}
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-sm bg-accent hover:bg-accent-2 text-bg-deep disabled:opacity-50 font-mono text-2xs uppercase tracking-wider font-semibold transition-colors"
        >
          {state.kind === 'saving' ? (
            <><Loader2 size={12} className="animate-spin" /> Saving…</>
          ) : state.kind === 'saved' ? (
            <><Check size={12} /> Saved</>
          ) : state.kind === 'ready' && state.existing ? (
            <>Update label</>
          ) : (
            <>Save label</>
          )}
        </button>
        {state.kind === 'ready' && state.existing && (
          <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
            Last updated {new Date(state.existing.created_at).toLocaleString()}
          </span>
        )}
        {state.kind === 'error' && state.message !== '__not_admin__' && (
          <span className="flex items-center gap-1 font-mono text-2xs text-tier-high">
            <AlertCircle size={11} /> {state.message}
          </span>
        )}
      </div>
    </div>
  );
}
