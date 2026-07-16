#!/usr/bin/env python3
"""
Match manually-downloaded PDFs to update records by CONTENT, not filename.

The manual PDFs are named by publisher convention (jmse-14-00122, 1-s2.0-...),
not the pipeline's <dedup_id>_<title> scheme, so they cannot be matched by name.
This reads each PDF's text, extracts its DOI (and title as a fallback), and maps
it to a record in the merged 2026 screening set. It reports three groups:

  * matched to a forwarded record  -> copied into pdfs_2026_manual/ as
    <dedup_id>_<title>.pdf so finalize_update.py picks it up;
  * matched to a record that was screened OUT (title/abstract FAIL) -> reported,
    not added — the reviewer excluded it for a reason;
  * unmatched -> the "arbitrary found" papers not in our search. Listed with the
    DOI/title read from the PDF so they can be assessed for manual inclusion.

Nothing is added to the corpus silently: exclusions and off-search papers are
surfaced for a human decision.

Run:  python3 src/match_manual_pdfs.py --src workspace/PDFs_Jul26_manual \
                                       --dir workspace/outputs/window_2026 [--apply]
"""
import argparse
import csv
import re
import shutil
from pathlib import Path

from pdfminer.high_level import extract_text

REPO = Path(__file__).resolve().parent.parent
WS = REPO / "workspace"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+")


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def safe_stem(dedup_id, title):
    t = re.sub(r"[^A-Za-z0-9]+", "_", title or "")[:80].strip("_")
    return f"{dedup_id}_{t}"


def pdf_head(path, chars=3500):
    try:
        return extract_text(str(path), maxpages=2) or ""
    except Exception as e:
        return ""


def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if Path(p).exists() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    SRC, D = Path(args.src), Path(args.dir)
    DEST = WS / "pdfs_2026_manual"

    # All merged records, with their screening verdict.
    scr = load(D / "abstract_screened_merged.csv")
    scr_by_id = {r["dedup_id"]: r for r in scr}
    # title screen carries the records that never reached abstract stage
    title = load(D / "title_screened_merged.csv")
    ded = load(D / "records_deduplicated_merged.csv")

    doi_map, title_map = {}, {}
    for r in ded:
        d = norm(r.get("doi"))
        if d:
            doi_map[d] = r["dedup_id"]
        t = norm(r.get("title"))
        if len(t) > 25:
            title_map[t] = r["dedup_id"]

    fwd_ids = {r["dedup_id"] for r in scr if r.get("abstract_screen") in ("INCLUDE", "UNCERTAIN")}

    matched_fwd, matched_excluded, unmatched = [], [], []
    for pdf in sorted(SRC.glob("*.pdf")):
        if pdf.stat().st_size < 8192:
            unmatched.append((pdf, "", "file too small / not a real PDF"))
            continue
        text = pdf_head(pdf)
        doi = ""
        m = DOI_RE.search(text)
        if m:
            doi = m.group(0).rstrip(".,)")
        did = doi_map.get(norm(doi)) if doi else None

        # title fallback: first non-trivial line
        guess_title = ""
        if not did:
            for line in text.splitlines():
                if len(line.strip()) > 30:
                    guess_title = line.strip()
                    break
            nt = norm(guess_title)
            # fuzzy-ish: exact normalized containment either way
            for t, rid in title_map.items():
                if nt and (nt[:60] in t or t[:60] in nt):
                    did = rid
                    break

        if did:
            rec = scr_by_id.get(did)
            if did in fwd_ids:
                matched_fwd.append((pdf, did, rec))
            else:
                verdict = (rec or {}).get("abstract_screen", "screened out at title stage")
                matched_excluded.append((pdf, did, verdict))
        else:
            unmatched.append((pdf, doi, guess_title[:70]))

    print(f"  {len(list(SRC.glob('*.pdf')))} manual PDFs\n")
    print(f"  ✓ matched to a FORWARDED record : {len(matched_fwd)}")
    print(f"  ⊘ matched to an EXCLUDED record : {len(matched_excluded)}")
    print(f"  ? not in our search set         : {len(unmatched)}\n")

    if matched_excluded:
        print("  ── matched but previously screened OUT (not added) ──")
        for pdf, did, verdict in matched_excluded:
            print(f"     {did} [{verdict}]  {pdf.name[:50]}")
        print()
    if unmatched:
        print("  ── not matched to any searched record (your 'arbitrary' finds) ──")
        for pdf, doi, t in unmatched:
            print(f"     {pdf.name[:46]}  doi={doi or '—'}  {('| '+t) if t else ''}")
        print()

    if args.apply:
        DEST.mkdir(parents=True, exist_ok=True)
        n = 0
        for pdf, did, rec in matched_fwd:
            dst = DEST / (safe_stem(did, rec.get("title", "")) + ".pdf")
            shutil.copy2(pdf, dst)
            n += 1
        print(f"  copied {n} matched PDFs → {DEST.relative_to(REPO)}")
        # persist the two review lists
        with open(D / "manual_matched_excluded.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["dedup_id", "verdict", "file"])
            for pdf, did, v in matched_excluded:
                w.writerow([did, v, pdf.name])
        with open(D / "manual_unmatched.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["file", "doi", "title_guess"])
            for pdf, doi, t in unmatched:
                w.writerow([pdf.name, doi, t])
        print(f"  wrote review lists: manual_matched_excluded.csv, manual_unmatched.csv")
    else:
        print("  (dry run — pass --apply to copy matched PDFs and write review lists)")


if __name__ == "__main__":
    main()
