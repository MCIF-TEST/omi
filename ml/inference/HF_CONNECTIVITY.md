# Hugging Face Connectivity Check (HUGGING_FACE_CONNECTIVITY_V1)

Minimal, **read-only** verification that Omi can talk to Hugging Face using the
existing `HF_TOKEN` GitHub secret and can read the model repository
`Andrewexiga/omi-behavioral-model-v1`.

This is the smallest verifiable slice of the integration plan's Render
boot-download step (`ml/HUGGING_FACE_INTEGRATION_PLAN.md` §F): prove the token +
registry are reachable **before** any download/serving wiring.

## Scope (what it deliberately does NOT do)
- ❌ does not train a model
- ❌ does not upload datasets (or anything)
- ❌ does not modify production code (`apps/api`, `apps/web`)
- ❌ does not modify scoring
- ✅ only authenticates (`whoami`) and reads repo metadata (`repo_info`)

A read-only token is sufficient — and is all the serving path is meant to use.

## Files
| File | Role |
|---|---|
| `.github/workflows/hf-connectivity.yml` | GitHub Action (manual trigger) |
| `ml/inference/hf_connectivity_check.py` | the read-only check (exit 0 = PASS) |

## A. How it works
The Action reads `HF_TOKEN` from GitHub Secrets, installs `huggingface_hub`, and
runs the script, which:
1. confirms `HF_TOKEN` is present (clean FAIL if missing — no token is ever printed),
2. authenticates via `HfApi().whoami()`,
3. verifies read access to the repo via `repo_info(...)`,
4. prints **PASS**/**FAIL** and writes a one-line CI step summary.

## B. Verification instructions
### Run in CI (primary)
1. Ensure the `HF_TOKEN` repository secret exists
   (**Settings → Secrets and variables → Actions**); read access is enough.
2. **Actions** tab → **hf-connectivity** → **Run workflow** (it is
   `workflow_dispatch`, i.e. manual only — it does not run on every push).
3. Open the run → job **HF · connectivity (read-only)** → step *Verify Hugging
   Face connectivity*. A ✅/❌ line also appears in the run **Summary**.

### Run locally (optional)
```bash
pip install "huggingface_hub>=0.23"
export HF_TOKEN=hf_...                      # read-only token
python ml/inference/hf_connectivity_check.py
echo "exit=$?"                              # 0 = PASS
```
Override the target if needed:
```bash
HF_REPO_ID=Andrewexiga/omi-behavioral-model-v1 HF_REPO_TYPE=model \
  python ml/inference/hf_connectivity_check.py
```

## C. Pass / fail output
**PASS** (exit 0):
```
Authenticated as: <account>
PASS: reached 'Andrewexiga/omi-behavioral-model-v1' (model, private, revision <sha12>)
```
CI Summary: `✅ HF connectivity PASS — authenticated as <account>, read Andrewexiga/omi-behavioral-model-v1 (private, rev <sha12>).`

**FAIL** (exit 1) — one clear reason, e.g.:
```
FAIL: HF_TOKEN is not set (configure it as a GitHub Actions secret).
FAIL: authentication failed (token rejected): ...
FAIL: repo 'Andrewexiga/omi-behavioral-model-v1' (model) not found or token lacks read access -- ...
FAIL: repo '...' is gated and the token lacks access.
```
The job (and the `hf-connectivity` check) is **red** on any FAIL, so a failed
connectivity check is visible without reading logs.
