#!/usr/bin/env python3
"""
Build a click-through HTML list for update records whose PDFs could not be
fetched automatically.

Most of these are NOT paywalled. MDPI (gold open access) and several other
publishers sit behind Cloudflare bot protection that refuses any scripted client
regardless of user-agent; the same PDF downloads in one click from a browser.
This mirrors the manual retrieval pass used in the original review
(workspace/pdfs_manual). Scripted retrieval got 20 of 71; the rest need this.

Works from the *merged* screening output and what is actually on disk, so it
stays correct as PDFs are added — re-run it any time to see what is still left.

Run:  python3 src/helpers/build_manual_fetch_list.py --dir workspace/outputs/window_2026
"""
import argparse
import csv
import html
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent.parent
WS = REPO / "workspace"


def safe_stem(dedup_id, title):
    t = re.sub(r"[^A-Za-z0-9]+", "_", title or "")[:80].strip("_")
    return f"{dedup_id}_{t}"


def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if Path(p).exists() else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    D = Path(args.dir)

    scr = load(D / "abstract_screened_merged.csv")
    fwd = [r for r in scr if r.get("abstract_screen") in ("INCLUDE", "UNCERTAIN")]

    # Link candidates from both retrieval passes.
    links = {}
    for f in ("pdfs_links.csv", "pdfs_links_merged.csv"):
        for r in load(D / f):
            links[r["dedup_id"]] = r

    # What is already on disk (either auto-fetched or manually saved)?
    have = set()
    for d in (WS / "pdfs_2026", WS / "pdfs_2026_manual"):
        if d.exists():
            have |= {p.name.split("_")[0] for p in d.glob("*.pdf") if p.stat().st_size >= 8192}

    outstanding = [r for r in fwd if r["dedup_id"] not in have]

    groups = defaultdict(list)
    for r in outstanding:
        L = links.get(r["dedup_id"], {})
        cands = [L.get(k, "") for k in ("unpaywall_pdf", "ss_oa_pdf", "openalex_pdf", "arxiv_pdf")]
        cands = [c for c in cands if c]
        land = [u.strip() for u in (L.get("landing_urls") or "").split(";") if u.strip()]
        host = urlparse(cands[0]).netloc if cands else (
            urlparse(land[0]).netloc if land else "no open-access link found")
        groups[host].append((r, cands, land))

    parts = ["""<!doctype html><meta charset="utf-8">
<title>Manual PDF retrieval — 2026 update</title>
<style>
 body{font:15px/1.55 system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.5rem} h2{font-size:1.02rem;margin-top:2rem;padding:.45rem .7rem;background:#eef2f7;border-radius:5px}
 li{margin:.8rem 0} .t{font-weight:600}
 .fn{font-family:ui-monospace,monospace;font-size:12px;color:#036;background:#f4f7fa;padding:1px 5px;border-radius:3px}
 a{color:#0645ad} .note{background:#fff8e1;border-left:4px solid #fbc02d;padding:.8rem 1rem;margin:1rem 0}
 input{margin-right:.55rem;transform:scale(1.2)} .inc{color:#1b5e20;font-weight:600}
</style>
<h1>Manual PDF retrieval — 2026 update</h1>
<div class="note"><b>Most of these are not paywalled.</b> MDPI and similar publishers are open access
but refuse scripted downloads (Cloudflare bot protection) — they download normally from a browser.
Save each PDF under the <span class="fn">exact filename shown</span>, into
<span class="fn">workspace/pdfs_2026_manual/</span>, then re-run
<span class="fn">python3 src/finalize_update.py</span> — the corpus counts update automatically.
<br><br>Prioritise the <span class="inc">INCLUDE</span> records; UNCERTAIN ones need the full text to judge.</div>
"""]
    n_inc = sum(1 for r in outstanding if r.get("abstract_screen") == "INCLUDE")
    parts.append(f"<p><b>{len(outstanding)} PDFs outstanding</b> "
                 f"({n_inc} INCLUDE, {len(outstanding)-n_inc} UNCERTAIN), grouped by publisher.</p>")

    for host, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        parts.append(f"<h2>{html.escape(host)} — {len(items)} paper(s)</h2><ul>")
        for r, cands, land in items:
            title = html.escape((r.get("title") or "")[:190])
            doi = r.get("doi", "")
            fn = html.escape(safe_stem(r["dedup_id"], r.get("title", "")) + ".pdf")
            urls = [f'<a href="{html.escape(c)}" target="_blank">PDF</a>' for c in cands]
            if doi:
                urls.append(f'<a href="https://doi.org/{html.escape(doi)}" target="_blank">doi.org/{html.escape(doi)}</a>')
            for u in land[:1]:
                urls.append(f'<a href="{html.escape(u)}" target="_blank">landing page</a>')
            if not urls:
                q = html.escape((r.get("title") or ""))[:120].replace(" ", "+")
                urls.append(f'<a href="https://scholar.google.com/scholar?q={q}" target="_blank">Google Scholar</a>')
            cls = "inc" if r.get("abstract_screen") == "INCLUDE" else ""
            parts.append(
                f'<li><input type="checkbox"><span class="t">{title}</span> '
                f'<span class="{cls}">[{html.escape(r.get("abstract_screen",""))}]</span><br>'
                f'<span class="fn">{fn}</span><br>{" &nbsp;·&nbsp; ".join(urls)}</li>')
        parts.append("</ul>")

    out = D / "manual_fetch_2026.html"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"  forwarded to full text : {len(fwd)}")
    print(f"  already retrieved      : {len(fwd) - len(outstanding)}")
    print(f"  still needed (manual)  : {len(outstanding)}  ({n_inc} INCLUDE)")
    print()
    for host, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"    {len(items):3d}  {host}")
    print(f"\n  → {out}")


if __name__ == "__main__":
    main()
