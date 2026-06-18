# `ml/datasets/analyst_verdicts/`

**Human ground-truth labels — the gold set.** This is what makes supervised
training and honest calibration possible, and it operationalizes the platform's
*analyst-controlled* principle: the human's conclusion is the training signal.

## What goes here
- Analyst verdicts from `Investigation.verdict`
  (`confirmed_bot_ring` / `likely_inauthentic` / `mixed` / `likely_authentic`
  / `inconclusive`) plus analyst notes, joined to the case/account they label.
- Account-level labels (and their confidence: high/medium) where they exist.
- Provenance + timestamp for every label (who/what decided, and when), so
  label quality is auditable and drift is detectable.

## How it's used
- **Training labels** for behavioral / case models (joined into `accounts/`,
  `investigations/`, etc.).
- **Calibration + evaluation** targets in `ml/evaluation/` (e.g. tier accuracy,
  Brier vs. human ground truth, FPR on analyst-confirmed-authentic controls).
- **Analyst training**: curated worked examples and known false-positive traps
  for onboarding/calibrating human reviewers.

## Source
`apps/api` → `Investigation.verdict` + account labels, via offline export.

## Constraints
Labels are evolving evidence, not immutable truth — keep provenance, allow
relabeling via new versions, never overwrite. Validate against `ml/schemas/`.
Governance applies; low-quality/disputed labels go to quarantine, not training.
