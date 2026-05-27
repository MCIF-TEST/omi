# Omi API

FastAPI backend for Omisphere. Hosts the `OmniDetect` detection engine.

## Install

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]            # base + test deps
# pip install -e .[dev,ml,db]    # full
```

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive docs: <http://localhost:8000/docs>

## Test

```bash
pytest
```

## Layout

```
app/
├── main.py            FastAPI app factory
├── config.py          Pydantic settings
├── schemas.py         Profile / Post / SignalResult / ScanResult
├── routes/
│   ├── health.py
│   └── analyze.py     /v1/analyze/account, /v1/analyze/comments
└── detection/
    ├── engine.py      Orchestrator
    ├── scoring.py     Log-odds aggregator + tier mapping
    ├── temporal.py    Cadence / sleep-gap / burst
    ├── semantic.py    TF-IDF (default) / embedding (optional) repetition
    ├── ai_writing.py  Burstiness / hedging / template repetition
    └── profile.py     Username entropy / age vs activity / bio quality
```

## Extending

To add a detector see the checklist in `docs/detection-methods.md`. Every detector returns a `SignalResult` and is independently testable.
