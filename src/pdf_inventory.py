#!/usr/bin/env python3
"""
Match the 225 survivors (INCLUDE + UNCERTAIN from abstract_screened.csv)
against PDFs already on disk across pdfs_*/ folders.

Match strategy (per survivor):
  1) DOI match — look for DOI substring in any PDF's first-page text
  2) Fuzzy title match — filename OR first-page text vs. title (>= 82 ratio)

Outputs:
  pdf_inventory.csv     — one row per survivor with match status + pdf path
  pdfs_missing.csv      — subset: survivors with no PDF found
"""

import csv
import os
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

try:
    from pdfminer.high_level import extract_text
    from PyPDF2 import PdfReader
except ImportError:
    print("Install pdfminer.six: pip install pdfminer.six", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT / "workspace"
OUTPUTS = WORKSPACE / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)
WORK_DIR = WORKSPACE  # for pdf_path relative display
PDF_DIRS = [WORKSPACE / d for d in ("pdfs", "pdfs_final_69", "pdfs_manual",
                                     "pdfs_manual_old", "pdfs_new_13apr",
                                     "pdfs_15apr", "pdfs_17apr", "pdfs_oa_auto")]
IN_CSV = OUTPUTS / "abstract_screened.csv"
OUT_INV = OUTPUTS / "pdf_inventory.csv"
OUT_MISS = OUTPUTS / "pdfs_missing.csv"

SCAN_CHARS = 8000  # chars of PDF text to extract for matching
VALIDITY_CACHE = OUTPUTS / "pdf_validity_cache.json"


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def extract_first(pdf_path):
    try:
        txt = extract_text(str(pdf_path), maxpages=4) or ""
        return txt[:SCAN_CHARS]
    except Exception as e:
        return ""


# PDF validity thresholds — abstract-only PDFs are rejected from the corpus
MIN_PAGES = 4            # real papers are >= 4 pages
MIN_TEXT_CHARS = 6000    # full text >> abstract

def check_validity(pdf_path):
    """Return (is_valid, reason). Reject abstract-only / too-thin PDFs."""
    # Filename-based pre-check
    fn = pdf_path.name.lower()
    if "abstract" in fn and "abstracts" not in fn:
        return False, "filename:abstract-only"
    # Page count
    try:
        r = PdfReader(str(pdf_path), strict=False)
        n_pages = len(r.pages)
    except Exception:
        n_pages = 0
    if n_pages and n_pages < MIN_PAGES:
        return False, f"pages:{n_pages}<{MIN_PAGES}"
    # Text length (whole doc)
    try:
        full_text = extract_text(str(pdf_path)) or ""
    except Exception:
        full_text = ""
    if len(full_text) < MIN_TEXT_CHARS:
        return False, f"text:{len(full_text)}<{MIN_TEXT_CHARS}"
    return True, f"ok ({n_pages}p, {len(full_text)}chars)"


def main():
    # Load survivors
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["abstract_screen"] in ("INCLUDE", "UNCERTAIN")]
    print(f"Survivors: {len(rows)}")

    # Collect PDFs
    pdfs = []
    for d in PDF_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.pdf"):
            pdfs.append(p)
    print(f"PDFs on disk: {len(pdfs)}\n")

    # Pre-filter: validate each PDF; reject abstract-only / too-thin
    print("Validating PDFs (rejecting abstract-only / too-thin)…")
    # Load cache (keyed by rel-path + mtime)
    import json as _json
    cache = {}
    if VALIDITY_CACHE.exists():
        try:
            cache = _json.loads(VALIDITY_CACHE.read_text())
        except Exception:
            cache = {}
    invalid = []
    valid_pdfs = []
    cache_updated = False
    for p in pdfs:
        rel = str(p.relative_to(WORKSPACE))
        key = f"{rel}:{int(p.stat().st_mtime)}"
        if key in cache:
            ok, reason = cache[key]
        else:
            ok, reason = check_validity(p)
            cache[key] = [ok, reason]
            cache_updated = True
        if ok:
            valid_pdfs.append(p)
        else:
            invalid.append((p, reason))
    if cache_updated:
        VALIDITY_CACHE.write_text(_json.dumps(cache, indent=1))
    print(f"  valid  : {len(valid_pdfs)}")
    print(f"  invalid: {len(invalid)} (abstract-only or thin)")
    if invalid:
        OUT_INVALID = OUTPUTS / "pdfs_invalid.csv"
        with open(OUT_INVALID, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["pdf_path", "reject_reason"])
            for p, reason in invalid:
                w.writerow([str(p.relative_to(WORK_DIR)), reason])
        print(f"  → list: {OUT_INVALID}")
    pdfs = valid_pdfs

    # Extract text per PDF (cache in-memory)
    print("\nExtracting text from valid PDFs…")
    pdf_info = []  # list of (path, filename_norm, text_norm, dois_set, meta_title_norm)
    for i, p in enumerate(pdfs, 1):
        text = extract_first(p)
        tn = norm(text)
        fn = norm(p.stem)
        # All DOIs found anywhere in extracted text (not just first)
        dois = set(m.rstrip(".,").lower()
                   for m in re.findall(r"10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+", text))
        # PDF /Title metadata
        meta_title = ""
        try:
            r_pdf = PdfReader(str(p), strict=False)
            if r_pdf.metadata and r_pdf.metadata.title:
                meta_title = r_pdf.metadata.title.strip()
        except Exception:
            pass
        pdf_info.append((p, fn, tn, dois, norm(meta_title)))
        if i % 25 == 0:
            print(f"  {i}/{len(pdfs)}")
    print(f"  done. PDFs with DOI(s) detected: {sum(1 for _,_,_,d,_ in pdf_info if d)}")
    print(f"  done. PDFs with /Title metadata : {sum(1 for _,_,_,_,m in pdf_info if m)}")

    # Match each survivor
    print("\nMatching…")
    out = []
    for r in rows:
        doi = (r.get("doi") or "").lower().strip()
        title = r.get("title", "")
        tn = norm(title)
        best = None
        best_score = 0
        method = ""

        # 1) DOI match (against any DOI found in each PDF)
        if doi:
            for p, fn, txt, pdois, _ in pdf_info:
                if doi in pdois:
                    best = p; best_score = 100; method = "doi"; break
                if doi in txt:
                    best = p; best_score = 100; method = "doi-substr"; break

        # 2) Metadata /Title exact match (strong signal, low false positive)
        if not best and tn and len(tn) >= 25:
            for p, fn, txt, _, meta in pdf_info:
                if len(meta) < 20:
                    continue
                s = fuzz.token_set_ratio(tn, meta)
                if s >= 90 and s > best_score:
                    best_score = s; best = p; method = "title-meta"
            if best and best_score < 90:
                best = None; best_score = 0

        # 2b) Title-at-head match: many preprints have no /Title metadata
        #     but the title is in the first ~200 chars of page 1. Compare
        #     survivor title against the first N chars via partial_ratio.
        if not best and tn and len(tn) >= 25:
            head_len = min(len(tn) + 40, 250)
            best_head_score = 0; best_head = None
            for p, fn, txt, _, _ in pdf_info:
                if len(txt) < 40:
                    continue
                head = txt[:head_len]
                s = fuzz.partial_ratio(tn, head)
                if s > best_head_score:
                    best_head_score = s; best_head = p
            if best_head and best_head_score >= 88:
                best = best_head; best_score = best_head_score; method = "title-head"

        # 3) Fuzzy title match on filename / body text
        if not best and tn:
            for p, fn, txt, _, _ in pdf_info:
                s1 = fuzz.partial_ratio(tn, fn) if fn else 0
                s2 = fuzz.partial_ratio(tn, txt[:1500]) if txt else 0
                s = max(s1, s2)
                if s > best_score:
                    best_score = s
                    best = p
                    method = "title-filename" if s1 >= s2 else "title-text"
            # Fuzzy title requires higher threshold — token_set_ratio
            # inflates scores on generic domain vocabulary
            if best_score < 88:
                best = None
                method = ""

        out.append({
            "dedup_id": r["dedup_id"],
            "title": title,
            "doi": r.get("doi", ""),
            "year": r.get("year", ""),
            "source_database": r.get("source_database", ""),
            "abstract_screen": r["abstract_screen"],
            "match_status": "FOUND" if best else "MISSING",
            "match_score": best_score if best else 0,
            "match_method": method,
            "pdf_path": str(best.relative_to(WORK_DIR)) if best else "",
            "url": r.get("url", ""),
        })

    # Write inventory
    fields = ["dedup_id", "title", "doi", "year", "source_database",
              "abstract_screen", "match_status", "match_score",
              "match_method", "pdf_path", "url"]
    with open(OUT_INV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    missing = [r for r in out if r["match_status"] == "MISSING"]
    with open(OUT_MISS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(missing)

    # Summary
    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    from collections import Counter
    status = Counter(r["match_status"] for r in out)
    print(f"  FOUND  : {status['FOUND']}/{len(out)}")
    print(f"  MISSING: {status['MISSING']}/{len(out)}")

    by_dec = Counter((r["abstract_screen"], r["match_status"]) for r in out)
    print("\n  By decision:")
    for (d, s), n in sorted(by_dec.items()):
        print(f"    {d:10s} {s:8s} {n}")

    ieee_miss = [r for r in missing if "IEEE" in r["source_database"]]
    print(f"\n  IEEE missing: {len(ieee_miss)}")

    # PDFs not matched to any survivor (possibly stale/from prior corpus)
    matched_pdfs = {r["pdf_path"] for r in out if r["pdf_path"]}
    unmatched = [p for p, _, _, _, _ in pdf_info
                 if str(p.relative_to(WORK_DIR)) not in matched_pdfs]
    print(f"\n  PDFs NOT mapped to any survivor: {len(unmatched)}")
    print(f"    (these may be legacy/cluster papers or out-of-scope)")
    print(f"\nWrote: {OUT_INV}")
    print(f"Wrote: {OUT_MISS}")


if __name__ == "__main__":
    main()
