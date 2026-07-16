#!/usr/bin/env python3
"""
Merge the separately-harvested Semantic Scholar 2026 records into the 2026
update search, then re-deduplicate and re-screen.

Semantic Scholar had to be harvested on its own (the API key was not active and
the public tier rate-limited the main run), so its records arrive after the other
four databases. This script folds them back in and re-runs deduplication and
title screening over the combined 2026 record set, so the update is deduplicated
as a whole rather than per-database.

Records already abstract-screened in the first pass are not re-screened; only
records new to this merge are forwarded.

Run:  python3 src/merge_ss.py --dir workspace/outputs/window_2026
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prisma_pipeline import deduplicate, screen_title, screen_title_pass2

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG_DEDUP = os.path.join(REPO_ROOT, "data", "records_deduplicated.csv")

from rapidfuzz import fuzz


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write(p, rows, fields=None):
    if not rows:
        print(f"  (nothing to write: {p})")
        return
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {p} ({len(rows)} rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    D = args.dir

    raw = load(os.path.join(D, "records_raw.csv"))
    ss_path = os.path.join(D, "ss_records.csv")
    if not os.path.exists(ss_path):
        print(f"ERROR: {ss_path} not found — run ss_reharvest.py first.")
        sys.exit(1)
    ss = load(ss_path)

    # Drop any Semantic Scholar rows from the main run: that harvest was
    # rate-limited and incomplete, and ss_records.csv supersedes it.
    raw_other = [r for r in raw if r["source_database"] != "Semantic Scholar"]
    dropped = len(raw) - len(raw_other)
    print(f"  main run: {len(raw)} raw ({dropped} incomplete SS rows dropped)")
    print(f"  SS re-harvest: {len(ss)} records")

    combined = raw_other + ss
    for i, r in enumerate(combined, 1):
        r["record_id"] = f"RAW-{i:04d}"
    write(os.path.join(D, "records_raw_merged.csv"), combined,
          ["record_id", "title", "authors", "year", "venue", "doi", "url",
           "abstract", "source_database", "string_id"])

    deduped, fuzzy = deduplicate(combined)
    print(f"\n  {len(combined)} raw → {len(deduped)} unique ({fuzzy} fuzzy)")
    write(os.path.join(D, "records_deduplicated_merged.csv"), deduped,
          ["dedup_id", "title", "authors", "year", "venue", "doi", "url",
           "abstract", "source_database", "string_id", "also_found_in"])

    # Title screen (same two-pass rule as the original review)
    screened = []
    for r in deduped:
        rc = dict(r)
        rc["title_screen"], rc["title_fail_reason"] = screen_title(r.get("title", ""))
        screened.append(rc)
    for r in screened:
        if r["title_screen"] != "MAYBE":
            continue
        res = screen_title_pass2(r.get("title", ""), r.get("abstract", ""))
        if res:
            r["title_screen"], r["title_fail_reason"] = res

    write(os.path.join(D, "title_screened_merged.csv"), screened,
          ["dedup_id", "title", "authors", "year", "venue", "doi", "url", "abstract",
           "source_database", "string_id", "also_found_in", "title_screen", "title_fail_reason"])

    # Diff against the original corpus
    orig = load(ORIG_DEDUP)
    orig_dois = {(r.get("doi") or "").strip().lower() for r in orig if (r.get("doi") or "").strip()}
    orig_titles = [" ".join((r.get("title") or "").lower().split()) for r in orig if r.get("title")]

    new = []
    for r in screened:
        doi = (r.get("doi") or "").strip().lower()
        if doi and doi in orig_dois:
            continue
        t = " ".join((r.get("title") or "").lower().split())
        if t and any(fuzz.ratio(t, ot) >= 90 for ot in orig_titles):
            continue
        new.append(r)

    write(os.path.join(D, "new_title_screened_merged.csv"), new)

    import collections
    fwd = [r for r in new if r["title_screen"] in ("PASS", "MAYBE")]
    print(f"\n{'='*58}")
    print(f"  MERGED 2026 UPDATE")
    print(f"{'='*58}")
    print(f"  Combined raw records   : {len(combined)}")
    print(f"  After deduplication    : {len(deduped)}")
    print(f"  New (not in original)  : {len(new)}")
    db = collections.Counter(r["source_database"] for r in new)
    for d, n in db.most_common():
        print(f"    {d:22s}: {n}")
    ts = collections.Counter(r["title_screen"] for r in new)
    print(f"  Title screen: PASS={ts.get('PASS',0)} MAYBE={ts.get('MAYBE',0)} FAIL={ts.get('FAIL',0)}")
    print(f"  → forward to abstract screening: {len(fwd)}")


if __name__ == "__main__":
    main()
