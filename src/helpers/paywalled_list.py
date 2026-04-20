#!/usr/bin/env python3
"""Build grouped-by-publisher list of paywalled INCLUDE records."""
import csv
import html
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUTS = REPO_ROOT / "workspace" / "outputs"
IN_LINKS = OUTPUTS / "pdfs_still_missing_links.csv"
IN_ABS = OUTPUTS / "abstract_screened.csv"
OUT_HTML = OUTPUTS / "paywalled_includes.html"
OUT_CSV = OUTPUTS / "paywalled_includes.csv"

# DOI prefix → publisher
PUBLISHERS = {
    "10.1016": "Elsevier (ScienceDirect)",
    "10.1007": "Springer",
    "10.1109": "IEEE Xplore",
    "10.3390": "MDPI",
    "10.1115": "ASME",
    "10.1080": "Taylor & Francis",
    "10.1155": "Hindawi / Wiley",
    "10.1111": "Wiley",
    "10.1002": "Wiley",
    "10.1061": "ASCE",
    "10.1017": "Cambridge UP",
    "10.1177": "SAGE",
    "10.3233": "IOS Press",
    "10.4043": "OnePetro (OTC)",
    "10.2118": "OnePetro (SPE)",
    "10.1049": "IET",
    "10.1098": "Royal Society",
    "10.1038": "Nature / Springer Nature",
    "10.1126": "Science / AAAS",
    "10.1088": "IOP",
    "10.3141": "SAGE (TRR)",
    "10.37220": "Morskoj Vestnik",
    "10.31490": "Other",
    "10.21014": "Other",
    "10.21595": "JVE International",
    "10.1051": "EDP Sciences",
    "10.1142": "World Scientific",
    "10.1093": "Oxford UP",
    "10.14279": "TU Berlin",
    "10.31224": "engrXiv",
    "10.59490": "TU Delft",
    "10.18434": "NIST",
    "10.23919": "IEEE / ACM",
    "10.3303": "AIDIC",
    "10.2478": "Sciendo / De Gruyter",
    "10.1515": "De Gruyter",
}


def publisher_of(doi, venue):
    if doi:
        prefix = doi.split("/")[0]
        if prefix in PUBLISHERS:
            return PUBLISHERS[prefix]
        return f"Unknown ({prefix})"
    return "No DOI"


def main():
    # load venues from abstract_screened
    venues = {}
    with open(IN_ABS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            venues[r["dedup_id"]] = r.get("venue", "")

    with open(IN_LINKS, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["abstract_screen"] == "INCLUDE" and r["any_pdf_found"] == "NO"]

    groups = defaultdict(list)
    for r in rows:
        r["venue"] = venues.get(r["dedup_id"], "")
        groups[publisher_of(r["doi"], r["venue"])].append(r)

    # Sort groups by size desc, sort rows within by year desc
    sorted_groups = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for _, items in sorted_groups:
        items.sort(key=lambda r: (str(r.get("year") or ""), r["title"]), reverse=True)

    # CSV
    csv_fields = ["publisher", "dedup_id", "year", "doi", "title", "venue",
                  "source_database", "url"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for pub, items in sorted_groups:
            for r in items:
                w.writerow({"publisher": pub,
                            "dedup_id": r["dedup_id"], "year": r["year"],
                            "doi": r["doi"], "title": r["title"],
                            "venue": r["venue"],
                            "source_database": r["source_database"],
                            "url": r.get("url", "")})

    # HTML
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Paywalled INCLUDE records — grouped by publisher</title>",
        "<style>",
        "body{font:13px/1.4 -apple-system,Segoe UI,sans-serif;max-width:1100px;margin:1rem auto;padding:0 1rem;color:#222}",
        "h1{font-size:18px;margin:0 0 4px}",
        ".meta{color:#666;font-size:12px;margin-bottom:1rem}",
        "h2{font-size:15px;margin:1.2rem 0 .3rem;padding:4px 8px;background:#e0e7ff;border-left:3px solid #4f46e5;color:#1e1b4b}",
        "h2 .n{color:#4f46e5;font-weight:400;font-size:12px;margin-left:8px}",
        "table{border-collapse:collapse;width:100%;margin-bottom:.5rem}",
        "th,td{text-align:left;padding:5px 8px;border-bottom:1px solid #eee;vertical-align:top}",
        "th{background:#f6f6f6;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#555}",
        ".id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#777;white-space:nowrap}",
        ".year{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#888}",
        ".title{font-weight:500;max-width:540px}",
        ".venue{color:#888;font-size:11px;margin-top:2px;font-style:italic}",
        "a.btn{display:inline-block;padding:3px 8px;border-radius:3px;",
        "background:#0f766e;color:#fff;text-decoration:none;font-size:11px;white-space:nowrap}",
        "a.btn:hover{background:#0a5b54}",
        "tr:nth-child(even){background:#fafafa}",
        ".done{text-decoration:line-through;color:#999;opacity:0.5}",
        "</style>",
        "<script>",
        "function toggle(id){const r=document.getElementById(id);r.classList.toggle('done');",
        "localStorage.setItem('pw_'+id,r.classList.contains('done')?'1':'0');}",
        "window.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('tr[id]').forEach(r=>{",
        "if(localStorage.getItem('pw_'+r.id)==='1')r.classList.add('done');});});",
        "</script></head><body>",
        f"<h1>Paywalled INCLUDE — {len(rows)} records across {len(sorted_groups)} publishers</h1>",
        "<div class='meta'>Grouped by DOI publisher prefix. Click a row to mark done (saved locally). ",
        "Use institutional proxy (RTU library) or ResearchGate per-publisher batch.</div>",
    ]
    for pub, items in sorted_groups:
        parts.append(f"<h2>{html.escape(pub)}<span class='n'>{len(items)} paper{'s' if len(items)!=1 else ''}</span></h2>")
        parts.append("<table><thead><tr><th>ID</th><th>Yr</th><th>Title / Venue</th><th>DOI</th></tr></thead><tbody>")
        for r in items:
            rid = r["dedup_id"]
            t = html.escape(r["title"])
            v = html.escape(r["venue"] or "")
            yr = html.escape(str(r.get("year") or ""))
            doi = html.escape(r["doi"])
            doi_url = f"https://doi.org/{doi}" if doi else ""
            btn = f"<a class='btn' target='_blank' href='{html.escape(doi_url)}'>{doi}</a>" if doi_url else "—"
            parts.append(
                f"<tr id='{rid}' onclick='toggle(\"{rid}\")'>"
                f"<td class='id'>{rid}</td><td class='year'>{yr}</td>"
                f"<td><div class='title'>{t}</div>"
                f"{'<div class=venue>'+v+'</div>' if v else ''}</td>"
                f"<td>{btn}</td></tr>"
            )
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    OUT_HTML.write_text("\n".join(parts), encoding="utf-8")

    print(f"Wrote: {OUT_HTML}")
    print(f"Wrote: {OUT_CSV}\n")
    print("Distribution:")
    for pub, items in sorted_groups:
        print(f"  {pub:30s} {len(items)}")


if __name__ == "__main__":
    main()
