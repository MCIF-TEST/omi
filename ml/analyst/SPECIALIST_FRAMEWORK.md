# OMI Specialist Intelligence Framework. Handbook

> GENERATED from `app.reasoning.prompts.framework` (framework v1, `sf:dfbf36f3f281213f2093d1f84ec9ea9b`, constitution v10). Do not hand-edit; regenerate via `python -m app.reasoning.prompts.export`.

Every AI specialist inherits this framework. Authored content lives in ONE place (the specialist's `SpecialistSpec`, its thirteen prompt sections); the framework derives identity, reasoning workflow, governance, technical, quality, validation, and documentation dimensions from it. GitHub is the single source of truth; Hugging Face receives the synchronized catalog through the existing publish workflow.

## Creating a new specialist (the template)

1. Author a `SpecialistSpec` in `app/reasoning/prompts/specialists.py` (13 sections).
2. Add it to `SPECIALISTS`; the library registers it in the ONE Prompt Registry as `lib-v1` (inert, nothing activates).
3. `framework.lift(spec)` now yields its complete profile automatically; override any derived dimension by keyword if the defaults do not fit.
4. Add its knowledge reading list (entries in `app/reasoning/knowledge/entries.py` naming the new key in `specialists`).
5. Write the unit tests its validation profile names; run the full suite.
6. Regenerate exports (`python -m app.reasoning.prompts.export`); commit; the existing GitHub Actions publish workflow synchronizes Hugging Face.

A worked example lives in `framework.example_investigation_planner()` (inert). Counterexample: a prompt-driven Governor. Validation is code, never generation.

## Directory conventions

- Authored specs: `app/reasoning/prompts/specialists.py` (+ constitution blocks in `constitution.py`)
- Framework: `app/reasoning/prompts/framework.py` (this module)
- Knowledge: `app/reasoning/knowledge/entries.py`
- Exports (HF-synchronized): `ml/analyst/hf_repo/prompts/` via `export.py`
- Tests: `apps/api/tests/test_specialist_framework.py` + per-specialist suites

## Profiles

### OMI BEHAVIOR ANALYST (`behavior_analyst`). Tier 1 · model

- **Mission:** Interpret a subject's behavioral signals into cited, probabilistic findings. What the behavior is consistent with, weighed both ways, without ever asserting a verdict.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:f7bf73b76955441b88b208fd438e4df4`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('behavior_analyst') (13 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'behavior_analyst'
- **Handbook:** OMI BEHAVIOR ANALYST. Tier 1 finding specialist. Interpret a subject's behavioral signals into cited, probabilistic findings. What the behavior is consistent with, weighed both ways, without ever asserting a verdict. Deep library: ml/analyst/BEHAVIORAL_ANALYST.md (methodology, knowledge base, playbook, failure + evaluation libraries).
- **Counterexample:** a finding that reads 'mechanical cadence therefore bot'. Regularity is never guilt; the benign twin (scheduler) was not tested

### OMI CALIBRATION ANALYST (`calibration_analyst`). Tier 2 · model

- **Mission:** Audit the council's confidence. Ensure stated confidence matches evidence strength and quantity. Flagging both over-confidence and under-confidence.
- **Authority:** challenge, calibrate, and advise; may lower or bound a read, never raise the number
- **Output:** One JSON object: {"critiques":[{"target":"<claim/overall>","challenge":"<over- or under-confidence and why>","recommended_band":"insufficient|low|moderate|high"
- **Prompt:** lib-v1 `ph:5b1b351c2546c47573752d305c13a9ee`
- **Schema:** council critique artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('calibration_analyst') (4 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'calibration_analyst'
- **Handbook:** OMI CALIBRATION ANALYST. Tier 2 critique specialist. Audit the council's confidence. Ensure stated confidence matches evidence strength and quantity. Flagging both over-confidence and under-confidence.
- **Counterexample:** a critique with direction='raises'. Critiques may lower or bound, never raise

### OMI CAMPAIGN ANALYST (`campaign_analyst`). Tier 2 · model

- **Mission:** Assess a materialized campaign (a persisted cluster of accounts acting together) and test the legitimate-coordination hypothesis before any hostile conclusion.
- **Authority:** challenge, calibrate, and advise; may lower or bound a read, never raise the number
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:ffddca98e7170ee98a5f168b9ee46273`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('campaign_analyst') (4 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'campaign_analyst'
- **Handbook:** OMI CAMPAIGN ANALYST. Tier 2 finding specialist. Assess a materialized campaign (a persisted cluster of accounts acting together) and test the legitimate-coordination hypothesis before any hostile conclusion.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI COORDINATION ANALYST (`coordination_analyst`). Tier 1 · model

- **Mission:** Determine whether accounts are acting together, and whether that coordination is inauthentic, the platform's core question, strictly through the corroboration gate.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:5b93c61f08929c6c77fa7f9ee50d0e16`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('coordination_analyst') (8 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'coordination_analyst'
- **Handbook:** OMI COORDINATION ANALYST. Tier 1 finding specialist. Determine whether accounts are acting together, and whether that coordination is inauthentic, the platform's core question, strictly through the corroboration gate.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI COUNTER-EVIDENCE ANALYST (`counter_evidence_analyst`). Tier 2 · model

- **Mission:** Be the council's devil's advocate. Actively build the strongest benign case for the subject and challenge every incriminating finding that the evidence does not uniquely support.
- **Authority:** challenge, calibrate, and advise; may lower or bound a read, never raise the number
- **Output:** One JSON object: {"critiques":[{"target":"<finding/claim challenged>","challenge":"<why the evidence does not uniquely support it, or the benign alternative>","
- **Prompt:** lib-v1 `ph:296976e8ce2cb80b459518093551476f`
- **Schema:** council critique artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('counter_evidence_analyst') (8 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'counter_evidence_analyst'
- **Handbook:** OMI COUNTER-EVIDENCE ANALYST. Tier 2 critique specialist. Be the council's devil's advocate. Actively build the strongest benign case for the subject and challenge every incriminating finding that the evidence does not uniquely support.
- **Counterexample:** a critique with direction='raises'. Critiques may lower or bound, never raise

### OMI FLOOR (`floor`). Tier 3 · deterministic-code

- **Mission:** Guarantee a valid, governed assessment exists no matter what fails above, the deterministic always-on judge of last resort.
- **Authority:** adjudicate (Judge) / validate (Governor) / guarantee (Floor); the only tier that rules
- **Output:** a deterministic, schema-valid analyst assessment (Ruling)
- **Prompt:** none (code-backed)
- **Schema:** schema/analyst_response_schema.json · **Token budget:** 1
- **Retrieval:** none. Pure function of ruling + bundle
- **Escalation:** none, the Floor is the terminal guarantee
- **Validation:** tests must cover: every violation class fires; 'floor' cannot be bypassed
- **Handbook:** OMI FLOOR. Tier 3, CODE-BACKED. Guarantee a valid, governed assessment exists no matter what fails above, the deterministic always-on judge of last resort. Never prompt- or model-driven.
- **Counterexample:** a prompt-driven governor. Unconstitutional; validation must be code

### OMI GOVERNOR (`governor`). Tier 3 · deterministic-code

- **Mission:** Validate every council ruling against the constitution. Mandatory, deterministic, unskippable.
- **Authority:** adjudicate (Judge) / validate (Governor) / guarantee (Floor); the only tier that rules
- **Output:** ValidationTrace (vt:). Permit/reject + violation codes
- **Prompt:** none (code-backed)
- **Schema:** schema/analyst_response_schema.json · **Token budget:** 1
- **Retrieval:** none. Pure function of ruling + bundle
- **Escalation:** REJECT hands the case to the deterministic Floor
- **Validation:** tests must cover: every violation class fires; 'governor' cannot be bypassed
- **Handbook:** OMI GOVERNOR. Tier 3, CODE-BACKED. Validate every council ruling against the constitution. Mandatory, deterministic, unskippable. Never prompt- or model-driven.
- **Counterexample:** a prompt-driven governor. Unconstitutional; validation must be code

### OMI JUDGE (`judge`). Tier 3 · model

- **Mission:** Adjudicate. Synthesize every specialist finding and critique into ONE cited, probabilistic, schema-valid ruling a human analyst can act on, cite, or overturn. echoing the engine number and honoring the corroboration gate.
- **Authority:** adjudicate (Judge) / validate (Governor) / guarantee (Floor); the only tier that rules
- **Output:** One schema-valid Omi Analyst assessment object (subject, verdict, suspicion_tier, suspicion_probability [echoed], confidence_band, confidence_rationale, headlin
- **Prompt:** lib-v1 `ph:c37c92a59fb02329619f3af139f6d837`
- **Schema:** schema/analyst_response_schema.json · **Token budget:** 2048
- **Retrieval:** KnowledgeIndex.for_specialist('judge') (7 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'judge'
- **Handbook:** OMI JUDGE. Tier 3 ruling specialist. Adjudicate. Synthesize every specialist finding and critique into ONE cited, probabilistic, schema-valid ruling a human analyst can act on, cite, or overturn. echoing the engine number and honoring the corroboration gate.
- **Counterexample:** a ruling with suspicion_probability != the engine number. Governor REJECT

### OMI LANGUAGE ANALYST (`language_analyst`). Tier 1 · model

- **Mission:** Interpret linguistic and stylometric evidence. Shared phrasing, templated text, copypasta, style matches. While respecting that style similarity is weak on its own.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:28b045098b0fb9015a95f60cdb096077`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('language_analyst') (5 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'language_analyst'
- **Handbook:** OMI LANGUAGE ANALYST. Tier 1 finding specialist. Interpret linguistic and stylometric evidence. Shared phrasing, templated text, copypasta, style matches. While respecting that style similarity is weak on its own.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI MEMORY ANALYST (`memory_analyst`). Tier 1 · model

- **Mission:** Retrieve and present relevant institutional memory as labeled background context. orienting the council without ever becoming proof.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"priors":[{"type":"<archetype/prior>","label":"<short>","influence":"supports|contradicts|neutral","stability":0.0,"note":"institutional memor
- **Prompt:** lib-v1 `ph:eadb52a4ec4720d1510f3342b27ce4b4`
- **Schema:** council memory artifact contract · **Token budget:** 512
- **Retrieval:** KnowledgeIndex.for_specialist('memory_analyst') (2 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'memory_analyst'
- **Handbook:** OMI MEMORY ANALYST. Tier 1 memory specialist. Retrieve and present relevant institutional memory as labeled background context. orienting the council without ever becoming proof.
- **Counterexample:** a prior carrying evidence_refs. Memory-boundary violation; dropped

### OMI METADATA ANALYST (`metadata_analyst`). Tier 1 · model

- **Mission:** Interpret account-metadata signals. Creation timing, age cohorts, handle patterns, profile completeness, verification, as weak, corroborating context.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:b0bbac9315262484b9ddcf8cae727ee7`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('metadata_analyst') (4 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'metadata_analyst'
- **Handbook:** OMI METADATA ANALYST. Tier 1 finding specialist. Interpret account-metadata signals. Creation timing, age cohorts, handle patterns, profile completeness, verification, as weak, corroborating context.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI NARRATIVE ANALYST (`narrative_analyst`). Tier 1 · model

- **Mission:** Assess whether a message/narrative is spreading organically or being coordinated and amplified. Reasoning over the narrative (message) grain, not the account grain.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:aa78ce973cdd04f4deaeb9bacddea36a`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('narrative_analyst') (4 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'narrative_analyst'
- **Handbook:** OMI NARRATIVE ANALYST. Tier 1 finding specialist. Assess whether a message/narrative is spreading organically or being coordinated and amplified. Reasoning over the narrative (message) grain, not the account grain.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI NETWORK ANALYST (`network_analyst`). Tier 1 · model

- **Mission:** Analyze the interaction graph between accounts. Co-engagement, co-tagging, reply pods, fingerprint clusters, to reveal structure that single-account views miss.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:d9c04f2b53e598bf9c5d93feb8327703`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('network_analyst') (6 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'network_analyst'
- **Handbook:** OMI NETWORK ANALYST. Tier 1 finding specialist. Analyze the interaction graph between accounts. Co-engagement, co-tagging, reply pods, fingerprint clusters, to reveal structure that single-account views miss.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

### OMI RISK ANALYST (`risk_analyst`). Tier 2 · model

- **Mission:** Assess the decision risk around the read, the cost of a false positive vs a false negative, and the harm surface, WITHOUT inflating suspicion to justify caution.
- **Authority:** challenge, calibrate, and advise; may lower or bound a read, never raise the number
- **Output:** One JSON object: {"critiques":[{"target":"<the read/decision>","challenge":"<risk consideration>","direction":"neutral|lowers","evidence_refs":["ev:..."]}],"unc
- **Prompt:** lib-v1 `ph:42fb31d586008a287484ca29c6add6ab`
- **Schema:** council critique artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('risk_analyst') (4 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'risk_analyst'
- **Handbook:** OMI RISK ANALYST. Tier 2 critique specialist. Assess the decision risk around the read, the cost of a false positive vs a false negative, and the harm surface, WITHOUT inflating suspicion to justify caution.
- **Counterexample:** a critique with direction='raises'. Critiques may lower or bound, never raise

### OMI TEMPORAL ANALYST (`temporal_analyst`). Tier 1 · model

- **Mission:** Interpret timing evidence. Posting cadence, burst synchrony, scheduling regularity, and separate botnet-like synchronization from benign automation and organic bursts.
- **Authority:** interpret evidence into cited artifacts; no verdicts, no score movement
- **Output:** One JSON object: {"findings":[{"signal":"<name>","claim":"<probabilistic sentence>","direction":"raises|lowers|neutral","evidence_refs":["ev:..."]}],"uncertaint
- **Prompt:** lib-v1 `ph:cccf7d262ba8a21d23456516ad9892c5`
- **Schema:** council finding artifact contract · **Token budget:** 1024
- **Retrieval:** KnowledgeIndex.for_specialist('temporal_analyst') (5 entries) + memory retrieve() PriorContext; both constant-time, off the hot path
- **Escalation:** surface ambiguity to the Judge as explicit uncertainty, never force a call; a Governor REJECT escalates to the deterministic Floor
- **Validation:** tests must cover: contract shape, citation resolution, supplemental gating, and graceful fallback for 'temporal_analyst'
- **Handbook:** OMI TEMPORAL ANALYST. Tier 1 finding specialist. Interpret timing evidence. Posting cadence, burst synchrony, scheduling regularity, and separate botnet-like synchronization from benign automation and organic bursts.
- **Counterexample:** a finding citing "ev:fabricated123". Unresolvable ref; whole output invalid → floor

