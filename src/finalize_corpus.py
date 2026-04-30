#!/usr/bin/env python3
"""
Produce the reproducible full-text corpus by marking paywalled-unretrievable
records as NOT_RETRIEVED in the PRISMA flow, and emit final_corpus.csv +
prisma_flow_counts.txt.

Policy: use only OA / openly retrievable PDFs + the custom manually-sourced
set already on disk. Paywalled records with no PDF on disk are excluded
with reason 'not-retrievable' (a standard PRISMA exclusion).
"""
import csv
from datetime import date
from pathlib import Path
from collections import Counter

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUTS = REPO_ROOT / "workspace" / "outputs"
WORK = OUTPUTS
ABS_CSV = OUTPUTS / "abstract_screened.csv"
INV_CSV = OUTPUTS / "pdf_inventory.csv"
OUT_CSV = OUTPUTS / "final_corpus.csv"
OUT_NOTRETR = OUTPUTS / "not_retrievable.csv"
OUT_FLOW = OUTPUTS / "prisma_flow_counts.txt"


def main():
    # abstract_screened: per-survivor decision (only forwarded PASS+MAYBE rows)
    with open(ABS_CSV, newline="", encoding="utf-8") as f:
        abs_rows = list(csv.DictReader(f))

    # pdf_inventory: per-survivor FOUND/MISSING + pdf_path
    with open(INV_CSV, newline="", encoding="utf-8") as f:
        inv = list(csv.DictReader(f))
    inv_by_id = {r["dedup_id"]: r for r in inv}

    # Full-pipeline counts
    with open(WORK / "records_raw.csv", newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))
    with open(WORK / "records_deduplicated.csv", newline="", encoding="utf-8") as f:
        dedup_rows = list(csv.DictReader(f))
    with open(WORK / "title_screened.csv", newline="", encoding="utf-8") as f:
        title_rows = list(csv.DictReader(f))

    db_counts = Counter(r["source_database"] for r in raw_rows)
    n_raw = len(raw_rows)
    n_dedup = len(dedup_rows)
    n_title_pass = sum(1 for r in title_rows if r["title_screen"] == "PASS")
    n_title_maybe = sum(1 for r in title_rows if r["title_screen"] == "MAYBE")
    n_title_fail = sum(1 for r in title_rows if r["title_screen"] == "FAIL")
    n_fwd = n_title_pass + n_title_maybe
    n_abs_inc = sum(1 for r in abs_rows if r["abstract_screen"] == "INCLUDE")
    n_abs_unc = sum(1 for r in abs_rows if r["abstract_screen"] == "UNCERTAIN")
    n_abs_exc = sum(1 for r in abs_rows if r["abstract_screen"] == "EXCLUDE")

    corpus = []
    notret = []
    for r in abs_rows:
        if r["abstract_screen"] not in ("INCLUDE", "UNCERTAIN"):
            continue
        inv_r = inv_by_id.get(r["dedup_id"], {})
        on_disk = inv_r.get("match_status") == "FOUND"
        pdf_path = inv_r.get("pdf_path", "")
        if on_disk and pdf_path:
            corpus.append({
                "dedup_id": r["dedup_id"],
                "title": r["title"],
                "authors": r["authors"],
                "year": r["year"],
                "venue": r["venue"],
                "doi": r["doi"],
                "source_database": r["source_database"],
                "abstract_screen": r["abstract_screen"],
                "pdf_path": pdf_path,
            })
        else:
            notret.append({
                "dedup_id": r["dedup_id"],
                "title": r["title"],
                "year": r["year"],
                "doi": r["doi"],
                "source_database": r["source_database"],
                "abstract_screen": r["abstract_screen"],
                "reason": "not-retrievable (paywalled or no PDF located)",
            })

    # Write
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(corpus[0].keys()))
        w.writeheader(); w.writerows(corpus)
    with open(OUT_NOTRETR, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(notret[0].keys()))
        w.writeheader(); w.writerows(notret)

    # PRISMA flow
    lines = [
        f"PRISMA Flow Counts — reproducible OA corpus ({date.today().isoformat()})",
        "=" * 56,
        "",
        "Identification:",
    ]
    for db, n in sorted(db_counts.items()):
        lines.append(f"  {db:20s} {n}")
    lines += [
        f"  {'TOTAL raw':20s} {n_raw}  (see records_raw.csv)",
        "",
        f"Screening:",
        f"  After dedup                : {n_dedup}",
        f"  After title screening      : {n_fwd}  (PASS={n_title_pass} + MAYBE={n_title_maybe}; FAIL={n_title_fail})",
        f"  After abstract screening   : {n_abs_inc + n_abs_unc}  (INCLUDE + UNCERTAIN)",
        f"    - INCLUDE                : {n_abs_inc}",
        f"    - UNCERTAIN              : {n_abs_unc}",
        f"    - EXCLUDE                : {n_abs_exc}",
        "",
        f"Full-text retrieval:",
        f"  PDFs retrievable           : {len(corpus)}  (→ final_corpus.csv)",
        f"  Not retrievable            : {len(notret)}  (→ not_retrievable.csv)",
        f"    by decision: INCLUDE={sum(1 for r in notret if r['abstract_screen']=='INCLUDE')}  "
        f"UNCERTAIN={sum(1 for r in notret if r['abstract_screen']=='UNCERTAIN')}",
        "",
        "Reproducibility note:",
        "  The corpus uses only openly retrievable PDFs (OA via Unpaywall/arXiv/",
        "  OpenAlex + publisher-provided OA) plus a curated ResearchGate/author-",
        "  provided set. Paywalled records with no openly retrievable PDF are",
        "  documented in not_retrievable.csv as a PRISMA limitation.",
    ]
    OUT_FLOW.write_text("\n".join(lines), encoding="utf-8")

    for line in lines:
        print(line)
    print(f"\nWrote:\n  {OUT_CSV}\n  {OUT_NOTRETR}\n  {OUT_FLOW}")


if __name__ == "__main__":
    main()
