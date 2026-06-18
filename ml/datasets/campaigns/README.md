# `ml/datasets/campaigns/`

**Materialized coordinated-cluster datasets** — from the `Campaign` /
`CampaignMember` / `CampaignObservation` store: the persisted, evolving
account-coordination clusters (the network grain).

## What goes here
- Per-campaign and per-member rows: members, observation history,
  `coordination_score` / `max_coordination_score`, detector methods that fired,
  corroboration status, and provenance.
- Includes **disclosed state-actor archives** (e.g. platform IO disclosures)
  whose account identities are **anonymized at source** — preserve that
  anonymization and record provenance.
- Used to train/evaluate **campaign detection / attribution / clustering** R&D.

## Source
`apps/api` → campaign store + seeded featured campaigns (`apps/api/app/content/`),
via offline export.

## Constraints
Network grain only. Corroboration discipline: a single non-discriminative
method must not imply a campaign. Evidence-first. Validate against
`ml/schemas/`. Governance + quarantine apply.
