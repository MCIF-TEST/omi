# OmiSphere — VISION

> Permanent project truths. Slow-changing. Update only when mission or product
> scope genuinely changes.

## What OmiSphere is

OmiSphere is a **social authenticity intelligence platform**. It analyzes
public social-media activity (an account, a video/tweet's commenters, a
message cluster, a campaign) and produces **evidence-backed, probabilistic**
assessments of authenticity and coordination — never verdicts-as-truth.

## Target users

- OSINT researchers
- Journalists
- Trust & safety analysts

## Mission

Detect and help analysts investigate:

- coordinated behavior
- synthetic amplification
- influence operations
- bot networks
- narrative manipulation

## Core principles

- **Evidence-first** — store and surface observations, evidence, and the
  reasons behind a number; never a persisted "this IS a bot/campaign" boolean.
- **Probabilistic** — scores are estimates with confidence, not accusations.
- **Explainable** — every score traces back to the detectors/evidence that
  produced it.
- **Analyst-controlled** — the human sets the verdict; the system informs it.
- **Transparency over certainty** — surface confidence, evidence-for,
  evidence-against, and "not enough data" honestly.

## What OmiSphere is NOT

- NOT a censorship platform
- NOT a truth machine
- NOT an accusation engine
- NOT an automated enforcement system

Engineering corollaries (how the principles show up in code):

- Records **evolve** — new evidence appends an observation and recomputes
  aggregates; no self-reinforcing loops that feed a conclusion back as truth.
- Coordination/legitimacy is the precision frontier: legitimate coordination
  (newsrooms, on-message officials) and benign automation must not be flagged.
  A single non-discriminative signal can never drive a maximal verdict
  (corroboration gate).
