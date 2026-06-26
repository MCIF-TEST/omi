# OMI_ENGINEERING_SPRINT_006 — First Live Reasoning Module (report)

> **Engineering sprint.** Proved that Omi's constitutional architecture can host a **real AI
> reasoning model** without changing the surrounding system. Exactly **one** specialist — the
> Behavior Analyst — becomes AI-backed; everything else stays deterministic. The AI specialist
> is a **drop-in for its existing Reasoning Contract**: it consumes only contract-permitted
> evidence + PriorContext, cites bundle evidence (and **cannot fabricate** — a bad citation
> triggers fallback, never a bad artifact), exposes uncertainty, never moves the engine number,
> and **falls back to the deterministic analyst on every failure**. The Governor stays
> mandatory; the Floor stays the fallback. Once a live endpoint exists, activation is **pure
> configuration**.

## A. GitHub commits

One commit on `claude/stoic-edison-2ueecx`. One new standalone package
(`app/reasoning/model_providers/`), one new orchestrator module
(`orchestrator/ai_modules.py`), one new test file, and two-line additive edits
(`orchestrator/__init__.py` exports, one new optional setting). **Zero** changes to the
engine, scoring, OmiScore, the Binder, the Evidence Bundle, the Governor, the Blackboard, the
Contracts, the Orchestrator control plane, or the existing `app/reasoning/providers.py`
(Phase-7 commentary LLM layer). Sprint 002–005 paths run untouched (the default council is
still fully deterministic; the AI specialist is opt-in / config-gated).

## B. Remote reasoning implementation (`app/reasoning/model_providers/`)

A **model-agnostic** seam between the deterministic architecture and any external model. The
council, contracts, blackboard, and Governor depend only on the protocol + typed errors here —
never on HTTP/HF/Qwen specifics. A future provider is a new class, activated by configuration.

- **`base.py`** — `ReasoningProvider` (a `@runtime_checkable` Protocol: `.name` + `.complete`),
  `ReasoningRequest` (with **revision pinning**, `max_tokens`, `temperature`, `stream`,
  `response_format`), `ReasoningResponse` (text + parsed `structured` + `diagnostics`), and the
  typed failures `ProviderUnavailable` / `ProviderTimeout` / `ProviderProtocolError`.
- **`remote.py`** — `RemoteReasoningProvider`, an HF text-generation client (stdlib `urllib`,
  no new dependency): **model revision pinning**, **timeout**, **capped-backoff retries** on
  transient network errors only, **diagnostics** (latency / attempts / streamed / model /
  revision), **structured-output** parsing (strips a Qwen `<think>` trace, extracts the JSON
  object), and **streaming compatibility** via `assemble_stream` (reassembles SSE token
  chunks — a pure, tested helper). On any failure it raises a typed error rather than ever
  fabricating an answer.
- **`mock.py`** — `MockReasoningProvider`, a scriptable in-process stand-in (canned
  structured/text output, or a chosen error) so every branch is testable offline.
- **`config.py`** — `build_remote_provider(settings)` (returns a configured provider or `None`
  when no endpoint is set) and `provider_status(settings)` (a no-secrets readiness snapshot).

## C. First AI-backed specialist (`orchestrator/ai_modules.py`)

- **`RemoteAnalyst`** — a council module that carries the **same contract** as the
  deterministic analyst it shadows (true drop-in), delegates reasoning to a `ReasoningProvider`,
  and **enforces the constitution in code**: every cited `evidence_ref` must resolve against
  the bundle (fabrication → fallback), empty/parse-failed output → fallback, and **any**
  provider exception → fallback. It records `last_diagnostics` (`ai` | `fallback` + telemetry).
- **`ai_behavior_analyst(provider, store=…, now=…)`** — the **one** AI specialist this sprint.
  It builds its request from contract-permitted **behavioral** evidence (non-supplemental
  contributions only — supplemental signals carry zero suspicion weight, so they are never
  offered) plus optional **PriorContext** (institutional memory, clearly labeled *background,
  never proof, never cite*). It parses the model's JSON into `Finding`s, **clamps direction**,
  and **drops any finding that tries to raise on supplemental evidence**. Its deterministic
  fallback is the Sprint-004 `BehaviorAnalyst`.
- The model can therefore only ever produce **contract-valid, bundle-anchored** findings — or
  defer to the deterministic floor. It never recomputes a score and the Judge still **echoes
  the engine number**, so an AI specialist cannot move suspicion up or down by itself.

## D. Test results

`cd apps/api && python -m pytest tests/ -q` → **846 passed** (was 827; **+19**), 0
regressions. `tests/test_ai_specialist.py` covers every required area:
- **contract compatibility** — the AI analyst's contract `==` the deterministic one; it
  satisfies the `AnalystModule` Protocol; both providers satisfy `ReasoningProvider`;
- **provider failures / timeout / retries / malformed** — `ProviderUnavailable`,
  `ProviderTimeout`, and non-JSON output each **fall back** with the right diagnostic reason;
  the remote client **retries then raises `ProviderTimeout`** (asserted attempt count) and
  raises `ProviderUnavailable` with no token;
- **never fabricate** — a fabricated `ev:` citation falls back and returns the *deterministic*
  findings; a supplemental-raise is dropped;
- **Governor validation + council execution** — a 1-AI-specialist council **passes the
  Governor**, the number stays **0.72**, and the AI finding flows into `evidence_for`;
- **deterministic replay** — same payload + deterministic provider → identical assessment and
  `ValidationTrace` id;
- **streaming + structured output** — `assemble_stream` concatenation, `extract_json`
  think-trace stripping;
- **runtime readiness** — `build_council` is deterministic when disabled and AI-backed when
  configured; `build_remote_provider` pins the revision; `provider_status` reports readiness.

## E. Runtime readiness

Activation is **configuration, not architecture** — via the existing `OMI_ANALYST_*` settings:

| Setting (env: `OMI_…`) | Role |
|---|---|
| `OMI_ANALYST_ENABLED` | master flag (off by default) |
| `OMI_ANALYST_ENDPOINT_URL` | HF inference endpoint (presence flips council to AI-backed) |
| `OMI_ANALYST_HF_REVISION` | model revision pin (reproducibility) |
| `OMI_ANALYST_TIMEOUT_SECONDS` | per-call timeout |
| `OMI_ANALYST_MAX_RETRIES` | **new** — transient-retry budget (default 2) |
| `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` | credential (presence is a boolean in diagnostics) |

`build_council(settings, store=…)` assembles the council from config: endpoint set + flag on →
the Behavior Analyst is the Qwen-backed `RemoteAnalyst`; otherwise the deterministic
`BehaviorAnalyst`. The Orchestrator, Governor, and Floor are **identical** either way.
`provider_status()` reports `ai_specialist_ready` only when flag + endpoint + token are all
present. Wiring `build_council` into the live `/analyst` HTTP route is the one remaining step
(Sprint 007), kept out of this sprint to avoid bridging the council Ruling shape to the
existing 4-assessment route under a single change.

## F. Remaining external blockers

- **The live HF inference endpoint + `HF_TOKEN`** (the standing blocker since Sprint 003).
  Until they exist, `RemoteReasoningProvider.complete` raises `ProviderUnavailable` and the AI
  specialist **falls back to deterministic** on every call — the council runs exactly as today.
  The entire integration is implemented and tested behind `MockReasoningProvider`; the moment
  the endpoint is provisioned and `OMI_ANALYST_ENABLED=true`, the live Qwen path activates with
  **no code change**. Operator actions: stand up the endpoint, set `OMI_ANALYST_ENDPOINT_URL`,
  `OMI_ANALYST_HF_REVISION`, and `HF_TOKEN`, flip `OMI_ANALYST_ENABLED=true`.

## G. Recommendation for Sprint 007

1. **Make the council production-reachable, flagged + off by default.** Wire `build_council`
   into the live `/analyst` path behind the Budget Controller / settings flag, persist the
   `ValidationTrace` + a blackboard digest to a durable audit store, and shadow-compare the
   AI-backed council against the proven deterministic Floor (the Governor + Floor already
   guarantee safety). This closes the loop between the live route and the council architecture.
2. **Capture live-vs-deterministic diagnostics.** Surface `RemoteAnalyst.last_diagnostics`
   (mode, latency, attempts, fallback reason) through the analyst status endpoint so operators
   can see, per investigation, whether the AI specialist ran or fell back and why — the
   evaluation substrate for promoting a second specialist (Counter-Evidence) to AI-backed.

---

*Long-term architecture over short-term sophistication. One specialist became AI-backed; the
constitution held: evidence over inference, no fabricated citations, the engine number echoed
not recomputed, the Governor mandatory and the Floor the fallback, execution deterministic
under a deterministic provider. No engine / scoring / OmiScore change; the model couples only
through the provider protocol + the existing contract. Gates green at commit time (846 backend
tests). GitHub remains the source of truth; Hugging Face remains the source of AI assets.*
