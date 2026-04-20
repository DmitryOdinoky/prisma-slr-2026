#!/usr/bin/env python3
"""
Second-pass PDF fetcher. Input: pdfs_still_missing_links.csv
For each record with any_pdf_found=YES, try each candidate URL in order:
  unpaywall_pdf → ss_oa_pdf → openalex_pdf → arxiv_pdf
until one produces a valid PDF. Save into pdfs_fetched_v2/.

Fixed download: reads full body via r.content (no streamed-peek bug).
"""
import csv
import re
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT / "workspace"
OUTPUTS = WORKSPACE / "outputs"
WORK = WORKSPACE  # for relative_to()
IN_CSV = OUTPUTS / "pdfs_still_missing_links.csv"
OUT_DIR = WORKSPACE / "pdfs_oa_auto"
OUT_DIR.mkdir(exist_ok=True)
LOG_CSV = OUTPUTS / "pdfs_oa_auto_log.csv"

UA = "PRISMA-SLR/1.0 (mailto:dmitry.odinoky@gmail.com)"
H = {"User-Agent": UA, "Accept": "application/pdf,*/*;q=0.8"}


def safe_stem(dedup_id, title):
    t = re.sub(r"[^A-Za-z0-9]+", "_", title or "")[:80].strip("_")
    return f"{dedup_id}_{t}"


def download(url, dest):
    try:
        r = requests.get(url, headers=H, timeout=60, allow_redirects=True)
        if r.status_code != 200:
            return False, f"http-{r.status_code}"
        if not r.content[:4] == b"%PDF":
            return False, f"not-pdf ({r.headers.get('Content-Type','?')[:40]})"
        if len(r.content) < 8192:
            return False, f"too-small ({len(r.content)}B)"
        dest.write_bytes(r.content)
        return True, f"ok ({len(r.content)}B)"
    except Exception as e:
        return False, f"err:{e.__class__.__name__}"


def main():
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["any_pdf_found"] == "YES"]
    print(f"Records with OA link to attempt: {len(rows)}\n")

    log = []
    ok = 0
    for i, r in enumerate(rows, 1):
        urls = [(src, r.get(col, ""))
                for src, col in [("unpaywall", "unpaywall_pdf"),
                                  ("ss", "ss_oa_pdf"),
                                  ("openalex", "openalex_pdf"),
                                  ("arxiv", "arxiv_pdf")]
                if r.get(col, "")]
        dest = OUT_DIR / f"{safe_stem(r['dedup_id'], r['title'])}.pdf"
        chosen_src = ""
        result = ""
        tried = []
        for src, url in urls:
            success, msg = download(url, dest)
            tried.append(f"{src}:{msg}")
            if success:
                chosen_src = src
                result = msg
                break
        saved = dest.exists() and dest.stat().st_size > 8192
        if saved:
            ok += 1
        log.append({
            "dedup_id": r["dedup_id"],
            "abstract_screen": r["abstract_screen"],
            "source_database": r["source_database"],
            "title": r["title"],
            "doi": r["doi"],
            "chosen_source": chosen_src,
            "result": result if saved else "FAILED",
            "attempts": " | ".join(tried),
            "local_path": str(dest.relative_to(WORK)) if saved else "",
        })
        if i % 5 == 0:
            print(f"  {i}/{len(rows)}  ok={ok}")
        time.sleep(0.5)

    fields = ["dedup_id", "abstract_screen", "source_database", "title", "doi",
              "chosen_source", "result", "attempts", "local_path"]
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(log)

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    print(f"  Attempted : {len(rows)}")
    print(f"  Saved OK  : {ok}")
    print(f"  Failed    : {len(rows)-ok}")
    from collections import Counter
    print(f"\n  By chosen source:")
    for s, c in Counter(l["chosen_source"] for l in log if l["chosen_source"]).items():
        print(f"    {s}: {c}")
    print(f"\n  PDFs → {OUT_DIR}")
    print(f"  Log  → {LOG_CSV}")


if __name__ == "__main__":
    main()
