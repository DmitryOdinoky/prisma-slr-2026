#!/usr/bin/env python3
"""
Finalise the 2026 PRISMA update: merge the new records into the original corpus
and emit the updated corpus + a two-column PRISMA flow (original vs update).

A PRISMA update reports counts for the original review and the update search
separately, then combined — so a reader can see exactly what the update added.
That is what this produces, rather than silently overwriting the old numbers.

Inputs
  data/final_corpus.csv                              original 196 studies
  data/not_retrievable.csv                           original 21 paywalled
  workspace/outputs/window_2026/                     the 2026 update search
      new_abstract_screened.csv                      screened new records
      pdfs_links.csv, pdfs_fetch_log.csv, pdfs_refetch_log.csv
  workspace/pdfs_2026/, workspace/pdfs_2026_manual/  retrieved PDFs

Outputs (into workspace/outputs/update_2026_final/)
  final_corpus_updated.csv        original + new, with pdf_path
  not_retrievable_updated.csv     original + new paywalled
  prisma_flow_update.txt          two-column PRISMA flow
"""

import argparse
import csv
import collections
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
WS = REPO / "workspace"
OUT = WS / "outputs" / "update_2026_final"


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(p, rows, fields=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print(f"  (no rows) {p}")
        return
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {p.relative_to(REPO)} ({len(rows)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-dir", default=str(WS / "outputs" / "window_2026"))
    args = ap.parse_args()
    D = Path(args.update_dir)

    orig = load(DATA / "final_corpus.csv")
    orig_nr = load(DATA / "not_retrievable.csv")
    # Prefer the merged screening (includes the Semantic Scholar harvest, which
    # had to be run separately); fall back to the pre-merge file if absent.
    merged = D / "abstract_screened_merged.csv"
    scr = load(merged if merged.exists() else D / "new_abstract_screened.csv")

    fwd = [r for r in scr if r.get("abstract_screen") in ("INCLUDE", "UNCERTAIN")]

    # Which of the forwarded records did we actually get a PDF for?
    pdf_dirs = [WS / "pdfs_2026", WS / "pdfs_2026_manual"]
    have = {}
    for d in pdf_dirs:
        if not d.exists():
            continue
        for p in d.glob("*.pdf"):
            if p.stat().st_size < 8192:          # reject stubs / error pages
                continue
            have.setdefault(p.name.split("_")[0], p)

    # The 2026 dedup restarts REC-numbering from REC-001, which collides with the
    # original corpus's REC-xxx ids. dedup_id is the join key for extractions,
    # narratives, and citations, so a collision silently conflates two papers.
    # Namespace every new record with a "U" (update) prefix; the original 196
    # keep their ids so the existing manuscript's references stay valid.
    def newid(did):
        return f"U{did}"

    corpus_new, notretr_new = [], []
    for r in fwd:
        did = r["dedup_id"]
        p = have.get(did)
        if p:
            corpus_new.append({
                "dedup_id": newid(did), "title": r["title"], "authors": r.get("authors", ""),
                "year": r.get("year", ""), "venue": r.get("venue", ""),
                "doi": r.get("doi", ""), "source_database": r.get("source_database", ""),
                "abstract_screen": r.get("abstract_screen", ""),
                "pdf_path": str(p.relative_to(WS)),
            })
        else:
            notretr_new.append({
                "dedup_id": newid(did), "title": r["title"], "authors": r.get("authors", ""),
                "year": r.get("year", ""), "venue": r.get("venue", ""),
                "doi": r.get("doi", ""), "source_database": r.get("source_database", ""),
                "abstract_screen": r.get("abstract_screen", ""),
                "reason": "no open-access PDF retrievable",
            })

    # Abstract-stage manual reconsideration (July 2026): records the automated
    # screen excluded but a reviewer re-admitted (audit trail in
    # data/abstract_reconsider_2026-07.csv). Their PDFs live in pdfs_readmit/.
    readmit_csv = D / "readmit_missing.csv"
    n_readmit = 0
    if readmit_csv.exists():
        re_dirs = [WS / "pdfs_readmit", WS / "pdfs_readmit_manual"]
        re_have = {}
        for d in re_dirs:
            if d.exists():
                for p in d.glob("*.pdf"):
                    if p.stat().st_size >= 8192:
                        re_have.setdefault(p.name.split("_")[0], p)
        for r in load(readmit_csv):
            did = r["dedup_id"]
            n_readmit += 1
            base = {"dedup_id": did, "title": r["title"], "authors": r.get("authors", ""),
                    "year": r.get("year", ""), "venue": r.get("venue", ""),
                    "doi": r.get("doi", ""), "source_database": r.get("source_database", ""),
                    "abstract_screen": "RECONSIDER"}
            p = re_have.get(did)
            if p:
                corpus_new.append({**base, "pdf_path": str(p.relative_to(WS))})
            else:
                notretr_new.append({**base, "reason": "no open-access PDF retrievable"})

    corpus_all = orig + corpus_new
    write(OUT / "final_corpus_updated.csv", corpus_all,
          ["dedup_id", "title", "authors", "year", "venue", "doi",
           "source_database", "abstract_screen", "pdf_path"])
    write(OUT / "not_retrievable_updated.csv", orig_nr + notretr_new)
    write(OUT / "corpus_2026_only.csv", corpus_new,
          ["dedup_id", "title", "authors", "year", "venue", "doi",
           "source_database", "abstract_screen", "pdf_path"])

    # ── PRISMA flow: original | update | combined ─────────────────────────────
    def pick(merged_name, plain_name):
        p = D / merged_name
        return load(p if p.exists() else D / plain_name)

    raw_u = pick("records_raw_merged.csv", "records_raw.csv")
    ded_u = pick("records_deduplicated_merged.csv", "records_deduplicated.csv")
    new_t = pick("new_title_screened_merged.csv", "new_title_screened.csv")
    t_fwd = [r for r in new_t if r["title_screen"] in ("PASS", "MAYBE")]

    db_u = collections.Counter(r["source_database"] for r in raw_u)
    inc = sum(1 for r in scr if r.get("abstract_screen") == "INCLUDE")
    unc = sum(1 for r in scr if r.get("abstract_screen") == "UNCERTAIN")

    # The two columns are DIFFERENT WINDOWS — original spans 11 years, the update
    # spans ~6 months. Label them explicitly: an unlabelled "Update" column reads
    # as though the databases returned fewer papers, which is the opposite of what
    # happened (like-for-like over 2015-2026, Scopus +58, IEEE +12, arXiv +8).
    L = []
    L.append("PRISMA 2020 flow — original review and 2026 update search")
    L.append("=" * 72)
    L.append(f"{'Stage':<44}{'Original':>13}{'Update':>13}")
    L.append(f"{'':<44}{'2015-2025':>13}{'2026 only':>13}")
    L.append("-" * 72)
    L.append(f"{'Records identified (databases)':<44}{913:>13}{len(raw_u):>13}")
    for db in ["Semantic Scholar", "OpenAlex", "arXiv", "Scopus", "IEEE Xplore"]:
        o = {"Semantic Scholar": 279, "OpenAlex": 400, "arXiv": 9,
             "Scopus": 176, "IEEE Xplore": 49}[db]
        L.append(f"{'  ' + db:<44}{o:>13}{db_u.get(db, 0):>13}")
    L.append(f"{'After deduplication':<44}{593:>13}{len(ded_u):>13}")
    L.append(f"{'  new to update (not in original)':<44}{'—':>13}{len(new_t):>13}")
    L.append(f"{'After title screening':<44}{400:>13}{len(t_fwd):>13}")
    L.append(f"{'After abstract screening':<44}{217:>13}{inc + unc:>13}")
    L.append(f"{'  INCLUDE':<44}{136:>13}{inc:>13}")
    L.append(f"{'  UNCERTAIN':<44}{81:>13}{unc:>13}")
    L.append(f"{'Full text retrieved (final corpus)':<44}{196:>13}{len(corpus_new):>13}")
    L.append(f"{'Not retrievable':<44}{21:>13}{len(notretr_new):>13}")
    L.append("-" * 72)
    L.append(f"{'COMBINED CORPUS':<44}{'':>13}{len(corpus_all):>13}")
    L.append("")
    yrs = collections.Counter(r["year"] for r in corpus_all if r.get("year"))
    L.append("Year distribution of combined corpus:")
    for y in sorted(yrs, key=str):
        L.append(f"  {y}: {yrs[y]}")

    txt = "\n".join(L)
    (OUT / "prisma_flow_update.txt").write_text(txt, encoding="utf-8")
    print()
    print(txt)
    print()
    print(f"  → {(OUT / 'prisma_flow_update.txt').relative_to(REPO)}")

    still = len(fwd) - len(corpus_new)
    if still:
        print(f"\n  NOTE: {still} forwarded records still have no PDF. Retrieve them via")
        print(f"        {(D / 'manual_fetch_2026.html').relative_to(REPO)} into workspace/pdfs_2026_manual/,")
        print(f"        then re-run this script — counts will update.")


if __name__ == "__main__":
    main()
