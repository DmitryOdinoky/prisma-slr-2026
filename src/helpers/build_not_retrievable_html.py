#!/usr/bin/env python3
"""
Build an interactive HTML page listing all papers we failed to retrieve
as full-text (91 records in the current run).

Sources joined:
  workspace/outputs/not_retrievable.csv             (authoritative 91-row set)
  workspace/outputs/pdfs_still_missing_links.csv    (OA-link candidates)
  workspace/outputs/abstract_screened.csv           (title, authors, abstract, venue)

Output:
  workspace/outputs/not_retrievable.html
"""
import csv
import html
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = REPO_ROOT / "workspace" / "outputs"

NOT_RETR = OUTPUTS / "not_retrievable.csv"
LINKS = OUTPUTS / "pdfs_still_missing_links.csv"
ABS = OUTPUTS / "abstract_screened.csv"
OUT = OUTPUTS / "not_retrievable.html"

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
    "10.1088": "IOP",
    "10.1051": "EDP Sciences",
    "10.1142": "World Scientific",
    "10.1093": "Oxford UP",
    "10.21595": "JVE International",
    "10.2478": "Sciendo / De Gruyter",
    "10.1515": "De Gruyter",
    "10.1145": "ACM",
    "10.37220": "Morskoj Vestnik",
    "10.59490": "TU Delft",
    "10.5750": "RINA / IMarEST",
    "10.5957": "SNAME",
    "10.23919": "IEEE / ACM Proceedings",
    "10.3303": "AIDIC",
    "10.33243": "NULP",
    "10.31490": "Other",
    "10.21014": "Other",
}


def publisher_of(doi):
    if not doi:
        return "No DOI"
    prefix = doi.split("/")[0]
    return PUBLISHERS.get(prefix, f"Other ({prefix})")


def load_csv(path, key):
    with open(path, newline="", encoding="utf-8") as f:
        return {r[key]: r for r in csv.DictReader(f)}


def main():
    # Load authoritative set
    with open(NOT_RETR, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    links_by_id = load_csv(LINKS, "dedup_id")
    abs_by_id = load_csv(ABS, "dedup_id")

    # Merge: enrich each not-retrievable record with OA links + abstract
    enriched = []
    for r in rows:
        rid = r["dedup_id"]
        ab = abs_by_id.get(rid, {})
        lk = links_by_id.get(rid, {})
        enriched.append({
            "dedup_id": rid,
            "title": r.get("title", "") or ab.get("title", ""),
            "authors": ab.get("authors", ""),
            "year": r.get("year", "") or ab.get("year", ""),
            "doi": r.get("doi", "") or ab.get("doi", ""),
            "source_database": r.get("source_database", "") or ab.get("source_database", ""),
            "venue": ab.get("venue", ""),
            "abstract_screen": r.get("abstract_screen", "") or ab.get("abstract_screen", ""),
            "abstract": ab.get("abstract", "")[:500],
            "url": ab.get("url", "") or lk.get("url", ""),
            "unpaywall_pdf": lk.get("unpaywall_pdf", ""),
            "ss_oa_pdf": lk.get("ss_oa_pdf", ""),
            "openalex_pdf": lk.get("openalex_pdf", ""),
            "arxiv_pdf": lk.get("arxiv_pdf", ""),
            "landing_urls": lk.get("landing_urls", ""),
            "oa_status": lk.get("oa_status", ""),
        })

    # Group by publisher
    groups = defaultdict(list)
    for e in enriched:
        groups[publisher_of(e["doi"])].append(e)

    # Sort groups by size desc
    sorted_groups = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    # Sort records within each group: INCLUDE first, then by year desc, title asc
    for _, items in sorted_groups:
        items.sort(key=lambda r: (r["abstract_screen"] != "INCLUDE",
                                   -int(str(r["year"]).strip() or 0) if str(r["year"]).strip().isdigit() else 0,
                                   r["title"].lower()))

    # Counts for summary
    n_total = len(enriched)
    n_include = sum(1 for e in enriched if e["abstract_screen"] == "INCLUDE")
    n_uncertain = sum(1 for e in enriched if e["abstract_screen"] == "UNCERTAIN")
    n_with_link = sum(1 for e in enriched
                      if any(e.get(k) for k in ("unpaywall_pdf", "ss_oa_pdf",
                                                 "openalex_pdf", "arxiv_pdf")))
    n_no_link = n_total - n_with_link

    # Build HTML
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>Not-retrievable papers — manual fetch list</title>",
        "<style>",
        "  body{font:13px/1.45 -apple-system,Segoe UI,Helvetica,sans-serif;"
        "       max-width:1180px;margin:1rem auto;padding:0 1rem;color:#222;background:#fafafa}",
        "  h1{font-size:20px;margin:0 0 4px}",
        "  .meta{color:#666;font-size:12px;margin-bottom:14px}",
        "  .toolbar{position:sticky;top:0;background:#fafafa;padding:8px 0;z-index:10;",
        "           border-bottom:1px solid #ddd;margin-bottom:10px}",
        "  .toolbar input[type=text]{width:320px;padding:6px 10px;font-size:13px;"
        "           border:1px solid #bbb;border-radius:4px}",
        "  .toolbar select{padding:6px 10px;font-size:13px;border:1px solid #bbb;"
        "           border-radius:4px;margin-left:6px}",
        "  .toolbar label{margin-left:12px;color:#555}",
        "  .summary{display:inline-block;margin-left:14px;color:#333;font-weight:500}",
        "  h2.pub{font-size:15px;margin:1.2rem 0 .3rem;padding:6px 10px;"
        "          background:#e0e7ff;border-left:3px solid #4f46e5;color:#1e1b4b;"
        "          border-radius:3px}",
        "  h2.pub .n{color:#4f46e5;font-weight:400;font-size:12px;margin-left:8px}",
        "  table{border-collapse:collapse;width:100%;margin-bottom:.8rem;background:#fff}",
        "  th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #eee;"
        "         vertical-align:top;font-size:12px}",
        "  th{background:#f3f4f6;font-size:10px;text-transform:uppercase;"
        "      letter-spacing:.6px;color:#555;position:sticky;top:52px}",
        "  .id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#777;"
        "       white-space:nowrap}",
        "  .year{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#888}",
        "  .title{font-weight:500;max-width:510px}",
        "  .meta2{color:#888;font-size:11px;margin-top:2px;font-style:italic}",
        "  .abs{color:#555;font-size:11px;margin-top:4px;max-width:510px;display:none}",
        "  tr.show-abs .abs{display:block}",
        "  .tag{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;"
        "        font-weight:500;margin-right:4px}",
        "  .tag-INCLUDE{background:#dcfce7;color:#14532d}",
        "  .tag-UNCERTAIN{background:#fef3c7;color:#78350f}",
        "  a.btn{display:inline-block;margin:1px 3px 1px 0;padding:3px 8px;"
        "         border-radius:3px;color:#fff;text-decoration:none;font-size:11px;"
        "         white-space:nowrap}",
        "  a.doi{background:#0f766e}         a.doi:hover{background:#0a5b54}",
        "  a.unpaywall{background:#2563eb}   a.unpaywall:hover{background:#1d4ed8}",
        "  a.ss{background:#7c3aed}          a.ss:hover{background:#5b21b6}",
        "  a.oa{background:#db2777}          a.oa:hover{background:#9d174d}",
        "  a.arxiv{background:#ea580c}       a.arxiv:hover{background:#9a3412}",
        "  a.landing{background:#64748b}     a.landing:hover{background:#475569}",
        "  tr:nth-child(even){background:#fbfbfb}",
        "  tr.done{text-decoration:line-through;color:#999;opacity:.5}",
        "  .info-icon{cursor:pointer;color:#4f46e5;margin-left:6px;user-select:none}",
        "  .hidden{display:none !important}",
        "</style>",
        "<script>",
        "function toggleDone(id){",
        "  const r=document.getElementById(id);",
        "  if(!r) return; r.classList.toggle('done');",
        "  localStorage.setItem('nr_'+id, r.classList.contains('done')?'1':'0');",
        "  updateCounts();",
        "}",
        "function toggleAbs(id){",
        "  const r=document.getElementById(id);",
        "  if(!r) return; r.classList.toggle('show-abs');",
        "}",
        "function applyFilter(){",
        "  const q=document.getElementById('q').value.toLowerCase();",
        "  const dec=document.getElementById('dec').value;",
        "  const hideDone=document.getElementById('hidedone').checked;",
        "  const onlyLinks=document.getElementById('onlylinks').checked;",
        "  document.querySelectorAll('tr.paper').forEach(r=>{",
        "    let ok=true;",
        "    const t=r.dataset.search||'';",
        "    if(q && !t.includes(q)) ok=false;",
        "    if(dec && r.dataset.dec!==dec) ok=false;",
        "    if(hideDone && r.classList.contains('done')) ok=false;",
        "    if(onlyLinks && r.dataset.links==='0') ok=false;",
        "    r.classList.toggle('hidden', !ok);",
        "  });",
        "  // Hide empty publisher sections",
        "  document.querySelectorAll('.pub-block').forEach(block=>{",
        "    const any=block.querySelector('tr.paper:not(.hidden)');",
        "    block.classList.toggle('hidden', !any);",
        "  });",
        "  updateCounts();",
        "}",
        "function updateCounts(){",
        "  const visible=document.querySelectorAll('tr.paper:not(.hidden)').length;",
        "  const done=document.querySelectorAll('tr.paper.done:not(.hidden)').length;",
        "  document.getElementById('countv').textContent=visible;",
        "  document.getElementById('countd').textContent=done;",
        "}",
        "window.addEventListener('DOMContentLoaded',()=>{",
        "  document.querySelectorAll('tr.paper').forEach(r=>{",
        "    if(localStorage.getItem('nr_'+r.id)==='1') r.classList.add('done');",
        "  });",
        "  applyFilter();",
        "});",
        "</script></head><body>",
        f"<h1>Not-retrievable papers — {n_total} records</h1>",
        f"<div class='meta'>PRISMA limitation: these {n_total} records passed abstract screening "
        f"(INCLUDE={n_include}, UNCERTAIN={n_uncertain}) but no PDF could be obtained via "
        "open-access channels or the author-curated set. Grouped by publisher (DOI prefix). "
        "Click a row's <b>✓</b> to mark it obtained (saved in browser). "
        "Click <b>ℹ︎</b> to toggle abstract preview. Use the filters above to narrow.</div>",
        "<div class='toolbar'>",
        "  <input type='text' id='q' placeholder='search title / author / DOI…' oninput='applyFilter()'>",
        "  <select id='dec' onchange='applyFilter()'>",
        "    <option value=''>all decisions</option>",
        "    <option value='INCLUDE'>INCLUDE only</option>",
        "    <option value='UNCERTAIN'>UNCERTAIN only</option>",
        "  </select>",
        "  <label><input type='checkbox' id='onlylinks' onchange='applyFilter()'> only with OA links</label>",
        "  <label><input type='checkbox' id='hidedone' onchange='applyFilter()'> hide done</label>",
        "  <span class='summary'>visible: <span id='countv'>0</span> · done: <span id='countd'>0</span></span>",
        "</div>",
    ]

    for pub, items in sorted_groups:
        n_inc = sum(1 for i in items if i["abstract_screen"] == "INCLUDE")
        n_unc = sum(1 for i in items if i["abstract_screen"] == "UNCERTAIN")
        parts.append(f"<div class='pub-block'>")
        parts.append(
            f"<h2 class='pub'>{html.escape(pub)}"
            f"<span class='n'>{len(items)} paper{'s' if len(items)!=1 else ''} "
            f"(INCLUDE {n_inc}, UNCERTAIN {n_unc})</span></h2>"
        )
        parts.append("<table><thead><tr>"
                     "<th style='width:3%'>✓</th>"
                     "<th style='width:7%'>ID</th>"
                     "<th style='width:4%'>Yr</th>"
                     "<th style='width:6%'>Dec.</th>"
                     "<th style='width:55%'>Title / authors / venue</th>"
                     "<th style='width:25%'>Links</th>"
                     "</tr></thead><tbody>")
        for r in items:
            rid = r["dedup_id"]
            title = html.escape(r["title"] or "")
            authors = html.escape(r["authors"] or "")
            venue = html.escape(r["venue"] or r["source_database"] or "")
            year = html.escape(str(r["year"] or ""))
            dec = r["abstract_screen"]
            abs_ = html.escape((r["abstract"] or "").strip())
            doi = r["doi"]
            doi_url = f"https://doi.org/{doi}" if doi else ""
            # OA buttons
            btns = []
            if doi_url:
                btns.append(f"<a class='btn doi' target='_blank' title='Publisher DOI landing page' "
                            f"href='{html.escape(doi_url)}'>DOI</a>")
            for label, col, cls in [("Unpaywall", "unpaywall_pdf", "unpaywall"),
                                     ("SemSchol", "ss_oa_pdf", "ss"),
                                     ("OpenAlex", "openalex_pdf", "oa"),
                                     ("arXiv", "arxiv_pdf", "arxiv")]:
                u = r.get(col, "").strip()
                if u:
                    btns.append(f"<a class='btn {cls}' target='_blank' "
                                f"href='{html.escape(u)}'>{label}</a>")
            # De-dupe landing urls against existing doi_url
            for u in (r.get("landing_urls", "") or "").split(" | "):
                u = u.strip()
                if u and u != doi_url:
                    btns.append(f"<a class='btn landing' target='_blank' "
                                f"href='{html.escape(u)}'>Land</a>")
            has_links = any(r.get(k) for k in ("unpaywall_pdf", "ss_oa_pdf",
                                                "openalex_pdf", "arxiv_pdf"))
            search_blob = f"{rid} {title} {authors} {venue} {doi} {year}".lower()
            info_icon = (
                f"<span class='info-icon' onclick=\"toggleAbs('{rid}')\" "
                f"title='Show/hide abstract'>&#8505;</span>"
            ) if abs_ else ""
            meta_line = authors
            if venue: meta_line += f" · {venue}"
            if doi: meta_line += f" · {doi}"
            abs_block = f"<div class='abs'>{abs_}</div>" if abs_ else ""
            btns_html = " ".join(btns) if btns else "<span style='color:#999'>—</span>"
            parts.append(
                f"<tr class='paper' id='{rid}' "
                f"data-dec='{dec}' data-links='{1 if has_links else 0}' "
                f"data-search='{html.escape(search_blob, quote=True)}'>"
                f"<td><input type='checkbox' onclick=\"toggleDone('{rid}')\" "
                f"title='Mark done'></td>"
                f"<td class='id'>{rid}</td>"
                f"<td class='year'>{year}</td>"
                f"<td><span class='tag tag-{dec}'>{dec}</span></td>"
                f"<td><div class='title'>{title} {info_icon}</div>"
                f"<div class='meta2'>{meta_line}</div>{abs_block}</td>"
                f"<td>{btns_html}</td></tr>"
            )
        parts.append("</tbody></table></div>")

    parts.append("</body></html>")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote: {OUT}")
    print(f"  Total: {n_total}  (INCLUDE {n_include} + UNCERTAIN {n_uncertain})")
    print(f"  With OA link candidates: {n_with_link}")
    print(f"  No link found (deepest paywall): {n_no_link}")
    print(f"  Publishers: {len(sorted_groups)}")


if __name__ == "__main__":
    main()
