# `ml/schemas/`

**Versioned data contracts** — the stable interfaces between every layer:
stores → `datasets/` → `features/` → `models/` (I/O) → `evaluation/`.

## What goes here
- A schema per dataset grain (investigations, narratives, campaigns, accounts,
  analyst_verdicts), per feature set, and per model input/output.
- Each schema is **versioned**; a breaking change is a new version, so a
  dataset/feature/model always names the exact schema it conforms to.

## Why a separate layer
It lets each stage evolve independently while staying compatible: a new feature
set can't silently break training, and a model's I/O is explicit for promotion.
Schemas **mirror** the production Pydantic shapes
(`apps/api/app/schemas.py`, `app/intelligence/schemas.py`) so offline and live
representations agree — but they are **standalone copies**, not imports, keeping
`/ml` decoupled from `apps/api`.

## Constraints
Validation is mandatory: datasets validate on publish, features on emit, model
I/O at train + eval time. No schema here imports or is imported by production.
