#!/usr/bin/env python3
"""
Enrich the still-missing records with candidate download links from
multiple OA sources: Unpaywall, Semantic Scholar, OpenAlex, arXiv.

Output: pdfs_still_missing_links.csv
  Columns add: unpaywall_pdf, ss_oa_pdf, openalex_pdf, arxiv_pdf,
               landing_urls (|-joined), any_pdf_found (bool)
"""
import csv
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUTS = REPO_ROOT / "workspace" / "outputs"
WORK = OUTPUTS
IN_CSV = OUTPUTS / "pdfs_missing.csv"
OUT_CSV = OUTPUTS / "pdfs_still_missing_links.csv"

EMAIL = "dmitry.odinoky@gmail.com"
UA = f"PRISMA-SLR/1.0 (mailto:{EMAIL})"
H = {"User-Agent": UA}


def unpaywall(doi):
    if not doi: return "", ""
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{doi}",
                         params={"email": EMAIL}, timeout=15, headers=H)
        if r.status_code != 200: return "", ""
        d = r.json()
        best = d.get("best_oa_location") or {}
        pdf = best.get("url_for_pdf") or ""
        landing = best.get("url") or ""
        if not pdf:
            for loc in d.get("oa_locations") or []:
                if loc.get("url_for_pdf"):
                    pdf = loc["url_for_pdf"]; landing = loc.get("url", landing); break
        return pdf, landing
    except Exception:
        return "", ""


def semantic_scholar(doi, title):
    try:
        if doi:
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        else:
            # search by title
            r = requests.get("https://api.semanticscholar.org/graph/v1/paper/search",
                             params={"query": title, "limit": 1,
                                     "fields": "title,openAccessPdf,externalIds"},
                             timeout=15, headers=H)
            if r.status_code != 200: return "", ""
            data = r.json().get("data") or []
            if not data: return "", ""
            oap = (data[0].get("openAccessPdf") or {}).get("url", "")
            return oap, ""
        r = requests.get(url, params={"fields": "openAccessPdf,externalIds,url"},
                         timeout=15, headers=H)
        if r.status_code != 200: return "", ""
        d = r.json()
        oap = (d.get("openAccessPdf") or {}).get("url", "")
        return oap, d.get("url", "")
    except Exception:
        return "", ""


def openalex(doi, title):
    try:
        if doi:
            r = requests.get(f"https://api.openalex.org/works/https://doi.org/{doi}",
                             timeout=15, headers=H)
        else:
            r = requests.get("https://api.openalex.org/works",
                             params={"search": title, "per-page": 1},
                             timeout=15, headers=H)
            if r.status_code != 200: return "", ""
            res = r.json().get("results") or []
            if not res: return "", ""
            w = res[0]
            loc = w.get("best_oa_location") or {}
            return loc.get("pdf_url") or "", w.get("id", "")
        if r.status_code != 200: return "", ""
        w = r.json()
        loc = w.get("best_oa_location") or {}
        pdf = loc.get("pdf_url") or ""
        if not pdf:
            for l in w.get("locations") or []:
                if l.get("pdf_url"): pdf = l["pdf_url"]; break
        return pdf, w.get("id", "")
    except Exception:
        return "", ""


def arxiv_search(title):
    try:
        # Keep only first 8 words for better matching
        q = " ".join(title.split()[:8])
        r = requests.get("http://export.arxiv.org/api/query",
                         params={"search_query": f'ti:"{q}"', "max_results": 1},
                         timeout=15, headers=H)
        if r.status_code != 200: return ""
        import re
        m = re.search(r'<link[^>]*title="pdf"[^>]*href="([^"]+)"', r.text)
        if m: return m.group(1)
        # Fallback: abs URL -> pdf
        m = re.search(r'<id>(http://arxiv.org/abs/[^<]+)</id>', r.text)
        if m:
            return m.group(1).replace("/abs/", "/pdf/") + ".pdf"
        return ""
    except Exception:
        return ""


def main():
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Missing records: {len(rows)}")

    out = []
    found_any = 0
    for i, r in enumerate(rows, 1):
        doi = (r.get("doi") or "").strip()
        title = r.get("title", "")

        up_pdf, up_land = unpaywall(doi)
        time.sleep(0.2)
        ss_pdf, ss_land = semantic_scholar(doi, title)
        time.sleep(0.3)
        oa_pdf, oa_land = openalex(doi, title)
        time.sleep(0.2)
        ax_pdf = arxiv_search(title) if title and len(title) > 20 else ""
        time.sleep(0.3)

        pdfs = [p for p in (up_pdf, ss_pdf, oa_pdf, ax_pdf) if p]
        landings = [l for l in (up_land, ss_land, oa_land) if l]

        row = {
            "dedup_id": r["dedup_id"],
            "abstract_screen": r["abstract_screen"],
            "source_database": r["source_database"],
            "year": r.get("year", ""),
            "title": title,
            "doi": doi,
            "url": r.get("url", ""),
            "unpaywall_pdf": up_pdf,
            "ss_oa_pdf": ss_pdf,
            "openalex_pdf": oa_pdf,
            "arxiv_pdf": ax_pdf,
            "landing_urls": " | ".join(dict.fromkeys(landings)),
            "any_pdf_found": "YES" if pdfs else "NO",
        }
        if pdfs: found_any += 1
        out.append(row)

        if i % 10 == 0:
            print(f"  {i}/{len(rows)}  with-link={found_any}")

    # Sort: INCLUDE first, then those with pdf links first
    out.sort(key=lambda r: (r["abstract_screen"] != "INCLUDE",
                            r["any_pdf_found"] != "YES",
                            r["source_database"]))

    fields = ["dedup_id", "abstract_screen", "source_database", "year",
              "title", "doi", "url",
              "unpaywall_pdf", "ss_oa_pdf", "openalex_pdf", "arxiv_pdf",
              "landing_urls", "any_pdf_found"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"\n{'='*60}\nSUMMARY\n{'='*60}")
    print(f"  Total missing         : {len(out)}")
    print(f"  With at least 1 OA PDF: {found_any}")
    print(f"  No OA link anywhere   : {len(out) - found_any}")
    inc = [r for r in out if r["abstract_screen"] == "INCLUDE"]
    inc_ok = [r for r in inc if r["any_pdf_found"] == "YES"]
    print(f"\n  INCLUDE missing       : {len(inc)}")
    print(f"    with link           : {len(inc_ok)}")
    print(f"    no link (paywalled) : {len(inc) - len(inc_ok)}")
    print(f"\nWrote: {OUT_CSV}")


if __name__ == "__main__":
    main()
