"""Dataset ingestion + training-corpus CLI.

The operator-facing front door to :mod:`app.ml.datasets`. Drop files into the
repo's ``datasets/`` folder and run these commands; everything is incremental
(a content-hash ledger means re-runs only touch new or changed files).

    cd apps/api

    # What's in the folder and what would be ingested?
    python -m scripts.datasets status

    # Score every account dataset through the engine + collect text datasets.
    # (Accounts need a DB; text works without one.)
    python -m scripts.datasets ingest                 # only new/changed files
    python -m scripts.datasets ingest --all           # re-ingest everything
    python -m scripts.datasets ingest --text-out FILE # also dump text JSONL

    # Measure the rule AI-writing detector against the labeled text corpus.
    python -m scripts.datasets benchmark-text

    # Build the brand-new combined corpus (imported datasets + captured
    # labels) the model trains on, written under datasets/_generated/.
    python -m scripts.datasets export
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.datasets.ingest import ingest_directory, plan_directory  # noqa: E402
from app.ml.datasets.paths import default_datasets_dir, generated_dir  # noqa: E402


def _cmd_status(args) -> int:
    root = args.root
    plan = plan_directory(root)
    print(f"datasets root: {plan.root}\n")
    print(f"{'':2} {'file':62} {'kind':9} {'adapter':24} new")
    print("-" * 110)
    for f in plan.files:
        mark = "OK" if f.supported else "--"
        print(f"{mark:2} {f.rel_path[:62]:62} {f.kind:9} {str(f.adapter)[:24]:24} {'yes' if f.is_new else 'no'}")
        if f.reason:
            print(f"     ↳ {f.reason}")
    print()
    print(f"ingestable: {len(plan.ingestable)}   new/changed: {len(plan.new_files)}")
    if args.json:
        print(json.dumps([f.__dict__ for f in plan.files], indent=2))
    return 0


def _cmd_ingest(args) -> int:
    root = args.root
    session = None
    has_accounts = any(f.kind == "accounts" for f in plan_directory(root).ingestable)
    if has_accounts and not args.text_only:
        try:
            from app.storage.db import get_session
            session_cm = get_session()
            session = session_cm.__enter__()
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: no DB session ({e}); account datasets will be skipped.",
                  file=sys.stderr)
            session = None

    try:
        report = ingest_directory(
            root,
            session=session,
            only_new=not args.all,
            limit_per_file=args.limit,
            collect_text=bool(args.text_out),
        )
    finally:
        if session is not None:
            session_cm.__exit__(None, None, None)

    if args.text_out and report.text_records:
        from app.ml.datasets.text_corpus import export_text_jsonl
        n = export_text_jsonl(report.text_records, Path(args.text_out))
        print(f"wrote {n} text rows → {args.text_out}")

    print(json.dumps({
        "files_processed": report.files_processed,
        "files_skipped_unchanged": report.files_skipped_unchanged,
        "accounts_ingested": report.accounts_ingested,
        "accounts_bots": report.accounts_bots,
        "accounts_humans": report.accounts_humans,
        "text_samples": report.text_samples,
        "text_ai": report.text_ai,
        "text_human": report.text_human,
        "per_file": report.per_file,
    }, indent=2))
    return 0


def _cmd_benchmark_text(args) -> int:
    from app.evaluation import evaluate_ai_writing_default
    rep = evaluate_ai_writing_default(root=args.root, limit_per_file=args.limit)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    if rep.get("n_total", 0) == 0:
        print(rep.get("message", "No text datasets found."))
        return 1
    cov, ov = rep["covered"], rep["overall"]
    print("=" * 64)
    print(" AI-WRITING DETECTOR vs LABELED TEXT CORPUS")
    print("=" * 64)
    print(f"  samples:   {rep['n_total']}  (ai={rep['n_ai']}, human={rep['n_human']})")
    print(f"  coverage:  {rep['coverage']:.1%}  ({rep['n_covered']} samples scored; "
          f"the rest are below the long-form word floor)")
    print(f"  mean conf: {rep['mean_confidence']:.3f}")
    print()
    print(f"  OVERALL (abstain → predict human):")
    print(f"    accuracy {ov['accuracy']:.3f}  (majority baseline {ov['majority_class_rate']:.3f})")
    print(f"    AI precision {ov['ai_precision']:.3f}  recall {ov['ai_recall']:.3f}  f1 {ov['ai_f1']:.3f}")
    print(f"    Brier {ov['brier']:.3f}  ROC-AUC {ov['roc_auc']}")
    print()
    print(f"  WHERE IT FIRES (n={cov['n']}):")
    if cov.get("n"):
        print(f"    accuracy {cov['accuracy']:.3f}  AI precision {cov['ai_precision']:.3f}  "
              f"recall {cov['ai_recall']:.3f}")
    print()
    print("  Takeaway: the rule detector is high-precision but low-coverage on")
    print("  short social text. Export the corpus and train the text head to")
    print("  close the recall gap (python -m scripts.datasets ingest --text-out ...).")
    return 0


def _cmd_export(args) -> int:
    out_dir = generated_dir(args.root)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")

    # 1) Combined account corpus from the live DB (imported + captured labels).
    wrote_accounts = False
    try:
        from app.ml.export import export_jsonl, export_summary
        from app.storage.db import get_session
        with get_session() as session:
            summary = export_summary(session, min_confidence=args.min_confidence)
            corpus = export_jsonl(session, min_confidence=args.min_confidence)
        acc_path = out_dir / f"omi_corpus_accounts_{stamp}.jsonl"
        acc_path.write_text(corpus, encoding="utf-8")
        wrote_accounts = True
        print(f"wrote account corpus → {acc_path}")
        print(json.dumps(summary, indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"account corpus skipped (no DB?): {e}", file=sys.stderr)

    # 2) Text corpus straight from the files (no DB needed).
    from app.ml.datasets.text_corpus import export_text_jsonl, load_text_records
    texts = load_text_records(args.root, limit_per_file=args.limit)
    if texts:
        txt_path = out_dir / f"omi_corpus_text_{stamp}.jsonl"
        n = export_text_jsonl(texts, txt_path)
        print(f"wrote text corpus → {txt_path} ({n} rows)")

    return 0 if (wrote_accounts or texts) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="OMISPHERE dataset ingestion + corpus tools.")
    ap.add_argument("--root", type=Path, default=default_datasets_dir(),
                    help="datasets folder (default: repo datasets/).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="List files and what would be ingested.")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("ingest", help="Ingest account datasets (DB) + collect text.")
    p.add_argument("--all", action="store_true", help="Re-ingest unchanged files too.")
    p.add_argument("--text-only", action="store_true", help="Skip the DB; text datasets only.")
    p.add_argument("--text-out", type=Path, help="Also write collected text rows to this JSONL.")
    p.add_argument("--limit", type=int, default=None, help="Max rows per file (debug).")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("benchmark-text", help="Score the AI-writing detector on the text corpus.")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=_cmd_benchmark_text)

    p = sub.add_parser("export", help="Write the combined training corpus to datasets/_generated/.")
    p.add_argument("--min-confidence", choices=("high", "medium"), default="medium")
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=_cmd_export)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
