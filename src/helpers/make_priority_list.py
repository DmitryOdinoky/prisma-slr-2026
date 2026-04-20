#!/usr/bin/env python3
"""Build a compact HTML priority-fetch list for INCLUDE records with OA links."""
import csv
import html
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUTS = REPO_ROOT / "workspace" / "outputs"
IN_CSV = OUTPUTS / "pdfs_still_missing_links.csv"
OUT = OUTPUTS / "priority_fetch.html"


def main():
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["abstract_screen"] == "INCLUDE" and r["any_pdf_found"] == "YES"]
    rows.sort(key=lambda r: (r["source_database"], r["year"]))

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Priority Manual Fetch — INCLUDE records</title>",
        "<style>",
        "body{font:13px/1.4 -apple-system,Segoe UI,sans-serif;max-width:1100px;margin:1rem auto;padding:0 1rem;color:#222}",
        "h1{font-size:18px;margin:0 0 4px}",
        ".meta{color:#666;font-size:12px;margin-bottom:1rem}",
        "table{border-collapse:collapse;width:100%}",
        "th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}",
        "th{background:#f6f6f6;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#555}",
        ".id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#777;white-space:nowrap}",
        ".title{font-weight:500;max-width:440px}",
        ".meta2{color:#888;font-size:11px;margin-top:2px}",
        "a.btn{display:inline-block;margin:1px 3px 1px 0;padding:3px 8px;border-radius:3px;",
        "background:#2563eb;color:#fff;text-decoration:none;font-size:11px;white-space:nowrap}",
        "a.btn:hover{background:#1d4ed8}",
        "a.btn.alt{background:#64748b}",
        "a.btn.alt:hover{background:#475569}",
        "a.btn.doi{background:#0f766e}",
        "tr:nth-child(even){background:#fafafa}",
        ".done{text-decoration:line-through;color:#999;opacity:0.5}",
        "</style>",
        "<script>",
        "function toggle(id){const r=document.getElementById(id);r.classList.toggle('done');",
        "localStorage.setItem(id,r.classList.contains('done')?'1':'0');}",
        "window.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('tr[id]').forEach(r=>{",
        "if(localStorage.getItem(r.id)==='1')r.classList.add('done');});});",
        "</script></head><body>",
        f"<h1>Priority manual fetch — {len(rows)} INCLUDE records</h1>",
        "<div class='meta'>Click row to strike-through when done (saved in browser). Try <b>DOI</b> first, ",
        "then OA source buttons in order: Unpaywall → Semantic Scholar → OpenAlex → arXiv.</div>",
        "<table><thead><tr><th>ID</th><th>Title / Source / Year</th><th>Links</th></tr></thead><tbody>",
    ]

    for r in rows:
        rid = r["dedup_id"]
        t = html.escape(r["title"])
        db = html.escape(r["source_database"])
        yr = html.escape(r["year"])
        doi = html.escape(r["doi"])
        doi_url = f"https://doi.org/{doi}" if doi else ""

        btns = []
        if doi_url:
            btns.append(f"<a class='btn doi' target='_blank' href='{html.escape(doi_url)}'>DOI</a>")
        for label, col, style in [
            ("Unpaywall", "unpaywall_pdf", ""),
            ("SemScholar", "ss_oa_pdf", ""),
            ("OpenAlex", "openalex_pdf", ""),
            ("arXiv", "arxiv_pdf", ""),
        ]:
            u = r.get(col, "").strip()
            if u:
                btns.append(f"<a class='btn' target='_blank' href='{html.escape(u)}'>{label}</a>")
        for u in (r.get("landing_urls", "") or "").split(" | "):
            u = u.strip()
            if u and u != doi_url:
                btns.append(f"<a class='btn alt' target='_blank' href='{html.escape(u)}'>Landing</a>")

        parts.append(f"<tr id='{rid}' onclick='toggle(\"{rid}\")'>")
        parts.append(f"<td class='id'>{rid}</td>")
        parts.append(f"<td><div class='title'>{t}</div>"
                     f"<div class='meta2'>{db} · {yr} · {doi or '(no DOI)'}</div></td>")
        parts.append(f"<td>{' '.join(btns)}</td></tr>")

    parts.append("</tbody></table></body></html>")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote: {OUT}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
