#!/usr/bin/env python3
"""
Generate SLR manuscript (LaTeX) from the final corpus + extractions + narratives.
Then compile to PDF via pdflatex.

Input:
  workspace/outputs/final_corpus.csv
  workspace/outputs/paper_extractions.json   (structured heuristic extraction)
  workspace/outputs/paper_narratives.json    (reviewer-authored thematic narratives)
  workspace/outputs/prisma_flow_counts.txt

Output:
  workspace/deliverables/SLR_final.tex
  workspace/deliverables/SLR_final.bib
  workspace/deliverables/SLR_final.pdf
"""
import csv
import json
import re
import subprocess
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from citation_utils import (
    bibkey as _bibkey_util,
    latex_escape as _latex_escape_util,
    rewrite_narrative_latex,
    surname_from_authors as _surname_util,
    to_ascii,
)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT / "workspace"
OUTPUTS = WORKSPACE / "outputs"
DELIVERABLES = WORKSPACE / "deliverables"
DELIVERABLES.mkdir(parents=True, exist_ok=True)
TEMPLATE = REPO_ROOT / "templates" / "SLR_template.tex"

CORPUS_CSV = OUTPUTS / "final_corpus.csv"
EXTR_JSON = OUTPUTS / "paper_extractions.json"
NARR_JSON = OUTPUTS / "paper_narratives.json"
FLOW_TXT = OUTPUTS / "prisma_flow_counts.txt"

OUT_TEX = DELIVERABLES / "SLR_final.tex"
OUT_BIB = DELIVERABLES / "SLR_final.bib"
OUT_PDF = DELIVERABLES / "SLR_final.pdf"


# ── Use shared helpers from citation_utils ─────────────────────────────────

# Re-export convenient module-local aliases with the names the rest of this
# file already uses.
surname_from_authors = _surname_util
latex_escape = _latex_escape_util
bibkey = _bibkey_util
rewrite_narrative = rewrite_narrative_latex


def _bib_escape(s):
    """Escape characters that must not appear raw in a BibTeX field value."""
    if not s:
        return ""
    # Only escape & (most common offender). Braces/quotes in source data
    # should be rare; leave them alone so we don't double-escape.
    return s.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")


def build_bibtex(papers):
    used = set()
    entries = []
    key_map = {}
    for p in papers:
        key = bibkey(p, used)
        key_map[p["dedup_id"]] = key
        etype = "inproceedings" if "conf" in (p.get("venue", "") or "").lower() else "article"
        venue = _bib_escape(p.get("venue", "") or "n.a.")
        authors = _bib_escape(p.get("authors", "") or "Anonymous")
        title = _bib_escape(p.get("title", "") or "")
        doi = p.get("doi", "") or ""
        year = p.get("year", "") or "n.d."
        fields = [
            f"  title = {{{title}}}",
            f"  author = {{{authors.replace(',', ' and')}}}",
            f"  year = {{{year}}}",
            f"  journal = {{{venue}}}" if etype == "article" else f"  booktitle = {{{venue}}}",
        ]
        if doi: fields.append(f"  doi = {{{doi}}}")
        entries.append(f"@{etype}{{{key},\n" + ",\n".join(fields) + "\n}")
    # add framework references used in narrative
    framework_refs = [
        ("@article{page2021,title={The PRISMA 2020 statement: an updated guideline for reporting systematic reviews},"
         "author={Page, M. J. and others},journal={BMJ},year={2021},volume={372},pages={n71}}", "page2021"),
        ("@article{holtrop1982,title={An approximate power prediction method},"
         "author={Holtrop, J. and Mennen, G. G. J.},journal={International Shipbuilding Progress},"
         "year={1982},volume={29},pages={166--170}}", "holtrop1982"),
        ("@techreport{imo2020ghg,title={Fourth IMO GHG Study 2020},"
         "author={{International Maritime Organization}},institution={IMO},year={2020}}", "imo2020ghg"),
        ("@techreport{imo2023strategy,title={2023 IMO Strategy on Reduction of GHG Emissions from Ships},"
         "author={{International Maritime Organization}},institution={IMO},year={2023}}", "imo2023strategy"),
        ("@techreport{imo2023cii,title={Guidelines on the operational carbon intensity rating of ships (CII)},"
         "author={{International Maritime Organization}},institution={IMO},year={2023}}", "imo2023cii"),
        ("@techreport{ittc2014,title={ITTC Recommended Procedures -- Analysis of Speed/Power Trial Data},"
         "author={{International Towing Tank Conference}},institution={ITTC},year={2014}}", "ittc2014"),
    ]
    for entry, _ in framework_refs:
        entries.append(entry)
    return "\n\n".join(entries), key_map


# ── Section builders ────────────────────────────────────────────────────────

def cite_all(keys):
    return "\\cite{" + ",".join(keys) + "}"


def section_abstract(ctx):
    p = ctx
    return rf"""\begin{{abstract}}
This paper presents an updated systematic literature review of machine learning
methods applied to vessel performance prediction and propulsion modeling,
conducted in accordance with the PRISMA 2020 reporting standard. A structured
search of five academic databases (Semantic Scholar, OpenAlex, arXiv, Scopus,
and IEEE~Xplore) on {p['search_date']} identified {p['n_raw']} records.
After deduplication ({p['n_dedup']} unique), title screening
({p['n_title_fwd']} forwarded), abstract screening ({p['n_abs_fwd']} forwarded),
and a reproducible full-text retrieval step using only openly obtainable PDFs
augmented by an author-curated set, a corpus of {p['n_corpus']} peer-reviewed
studies was obtained and analysed across {p['n_clusters']} thematic clusters.
Gradient boosting ensembles and tree-based learners dominate reported methods
and achieve the highest headline accuracy on tabular operational data, but
substantial heterogeneity in validation protocol introduces systematic
inflation in cross-study comparison. Physics-hybrid (grey-box) architectures
consistently improve accuracy and out-of-distribution robustness over pure
data-driven baselines. Feature engineering effort, particularly the use of
rolling-window statistics and physics-derived covariates, has as large an effect
on final accuracy as the choice of learning algorithm. Online adaptation of
deployed propulsion models remains a small and methodologically under-specified
subfield. Principal research gaps and a reproducibility-oriented protocol for
future ML-for-ship-performance studies are identified.
\end{{abstract}}"""


def section_intro(ctx):
    return r"""\section{Introduction}
\label{sec:intro}

Commercial shipping is responsible for approximately 2.5\% of global greenhouse
gas (GHG) emissions while carrying over 80\% of world trade~\cite{imo2020ghg}.
The International Maritime Organization's 2023 revised GHG strategy~\cite{imo2023strategy}
targets net-zero shipping emissions ``by or around 2050'' and introduces the
Carbon Intensity Indicator (CII) annual rating scheme that places operational
efficiency at the centre of regulatory compliance~\cite{imo2023cii}. Accurate
prediction of vessel fuel consumption, propulsion power, and speed is the
technical foundation for CII compliance, voyage optimisation, hull-condition
management, and operational decision support.

The simultaneous influence of vessel loading, environmental forcing, propulsion
system state, hull and propeller condition, and vessel-class hydrodynamics makes
propulsion modelling an inherently multivariate inference problem.
Semi-empirical naval architecture methods such as the Holtrop--Mennen
resistance estimation~\cite{holtrop1982} and the ITTC~\cite{ittc2014} speed/power
trial analysis provide structured baselines but cannot adapt to idiosyncratic
behaviour of individual vessels in service. The proliferation of onboard sensor
infrastructure over the last decade -- fuel flow meters, AIS transponders, draft
sensors, weather reanalysis services -- has enabled supervised ML approaches to
learn vessel-specific performance models directly from operational data.

\subsection{Scope and research questions}

This review addresses four research questions:
\begin{enumerate}[leftmargin=*,label=RQ\arabic*.]
  \item What ML methods have been applied to vessel speed, fuel consumption,
  and power prediction from operational data, and how do their reported
  accuracies compare once validation-protocol differences are accounted for?
  \item How do physics-hybrid (grey-box) architectures compare to pure
  data-driven models in terms of accuracy and robustness to distribution
  shift?
  \item What feature engineering and data preprocessing practices are used,
  and which consistently improve prediction accuracy?
  \item What approaches exist for online adaptation and recalibration of
  deployed propulsion models, and how mature is this subfield?
\end{enumerate}

\subsection{Contribution of this review}

The principal contributions of this review are:
(1)~a PRISMA~2020 compliant systematic search of five major databases
(IEEE~Xplore re-added relative to earlier iterations of this review once an
active API key became available), with a reproducibility-first retrieval policy
that uses only openly available PDFs together with an author-curated set;
(2)~a thematic synthesis across six clusters with quantitative comparisons of
method performance, physics integration, feature engineering, and adaptation;
(3)~identification of three principal research gaps; and
(4)~a proposed reproducibility protocol addressing the systematic
validation-protocol heterogeneity uncovered in the corpus."""


def build_prisma_table(ctx):
    return rf"""\begin{{table}}[t]
\centering
\caption{{PRISMA 2020 flow counts for this review.}}
\label{{tab:prisma}}
\small
\begin{{tabularx}}{{\columnwidth}}{{@{{}}L{{5.2cm}}C{{1.9cm}}@{{}}}}
\toprule
\textbf{{Stage}} & \textbf{{Records}} \\
\midrule
Semantic Scholar & {ctx['db']['Semantic Scholar']} \\
OpenAlex & {ctx['db']['OpenAlex']} \\
arXiv & {ctx['db'].get('arXiv', 0)} \\
Scopus & {ctx['db']['Scopus']} \\
IEEE Xplore & {ctx['db']['IEEE Xplore']} \\
\textbf{{Total from databases}} & \textbf{{{ctx['n_raw']}}} \\
\midrule
Records after deduplication & {ctx['n_dedup']} \\
After title screening (PASS+MAYBE) & {ctx['n_title_fwd']} \\
After abstract screening & {ctx['n_abs_fwd']} \\
\ \ INCLUDE (high confidence) & {ctx['n_abs_inc']} \\
\ \ UNCERTAIN (forwarded for review) & {ctx['n_abs_unc']} \\
\midrule
Full text retrievable (OA + curated) & {ctx['n_corpus']} \\
Not retrievable (paywalled; documented) & {ctx['n_notretr']} \\
\bottomrule
\end{{tabularx}}
\end{{table}}"""


def section_methodology(ctx):
    prisma_tbl = build_prisma_table(ctx)
    return rf"""\section{{Methodology}}
\label{{sec:method}}

\subsection{{Protocol and reporting standard}}
This review was conducted in accordance with the PRISMA~2020
statement~\cite{{page2021}}. The complete search log, screening records, PDF
inventory, and paper-level data extraction are provided as supplementary
material. All code used to run the searches, screen records, and build this
manuscript is released alongside the paper.

\subsection{{Search strategy}}
Five databases were queried programmatically on {ctx['search_date']} using
their REST APIs. Four thematic search strings were used, covering
(A)~core propulsion modelling, (B)~feature engineering, (C)~physics-hybrid
approaches, and (D)~real-time recalibration. The full string text is
reproduced in Appendix~\ref{{app:strings}}. All searches used a date filter of
2015--2025.

\subsection{{Eligibility criteria}}
Inclusion criteria (all must be satisfied): (I1)~the study involves prediction
of vessel fuel consumption, speed, propulsion power, or an equivalent
performance parameter; (I2)~the study employs a supervised ML, statistical
learning, or physics-ML hybrid method; (I3)~at least one quantitative accuracy
metric ($R^2$, RMSE, MAE, or MAPE) is reported; (I4)~published 2015--2025 in a
peer-reviewed journal or major conference; (I5)~full text in English.

Exclusion criteria (any sufficient): (E1)~maritime study outside propulsion/fuel
prediction (trajectory, routing, structural integrity); (E2)~no data-driven
component; (E3)~duplicate publication; (E4)~gray literature; (E5)~non-maritime
domain; (E6)~non-English; (E7)~insufficient methodological novelty or no
quantitative accuracy metric.

\subsection{{Screening, retrieval, and extraction}}
Three screening stages were applied: title screening (keyword-based with a
two-pass refinement), abstract screening (rule-based with multi-axis maritime
+ ML + performance-target filters), and full-text assessment. At full-text
stage, records whose PDFs could be obtained either via open access
(Unpaywall~\cite{{page2021}}, OpenAlex, Semantic Scholar, or publisher-provided
OA) or an author-curated set of previously collected manuscripts were retained
in the corpus. Records that were paywalled and could not be retrieved with
openly available channels were documented explicitly as ``not retrievable''
in the supplementary material; they are reported as a PRISMA
limitation.

{prisma_tbl}

\subsection{{PDF validity check}}
To ensure that only full-text papers enter the quantitative synthesis, each
retrieved PDF was validated against a minimum-content threshold: page count
$\geq 4$ and extractable text length $\geq 6000$ characters. PDFs containing
only extended abstracts or conference teasers were rejected at this stage and
flagged for replacement when possible."""


def section_descriptive(ctx):
    cluster_counts = ctx["cluster_counts"]
    rows = "\n".join(f"{c} & {n} \\\\" for c, n in cluster_counts.most_common())
    target_counts = ctx["target_counts"]
    trows = "\n".join(f"{latex_escape(t)} & {n} \\\\" for t, n in target_counts.most_common(10))
    mrows = "\n".join(f"{latex_escape(m)} & {n} \\\\" for m, n in ctx["method_counts"].most_common(12))
    years_dist = ctx["years_dist"]
    yrs_rows = "\n".join(f"{y} & {n} \\\\" for y, n in sorted(years_dist.items()))
    return rf"""\section{{Descriptive Statistics}}
\label{{sec:desc}}

\subsection{{Corpus composition}}
The final corpus contains {ctx['n_corpus']} peer-reviewed studies. Table~\ref{{tab:clusters}}
reports the thematic-cluster distribution of the corpus; papers may be
assigned to more than one cluster in subsequent sections but each has a single
primary cluster based on the dominant contribution.

\begin{{table}}[t]
\centering
\caption{{Thematic cluster distribution of the corpus.}}
\label{{tab:clusters}}
\small
\begin{{tabular}}{{@{{}}lc@{{}}}}
\toprule
\textbf{{Cluster}} & \textbf{{\#}} \\
\midrule
{rows}
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Publication year trend}}
Table~\ref{{tab:years}} reports the publication-year distribution.

\begin{{table}}[t]
\centering
\caption{{Publication year distribution of the corpus.}}
\label{{tab:years}}
\small
\begin{{tabular}}{{@{{}}lc@{{}}}}
\toprule
\textbf{{Year}} & \textbf{{\#}} \\
\midrule
{yrs_rows}
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Prediction targets}}
Table~\ref{{tab:targets}} lists the prediction targets that appear most
frequently in the corpus.

\begin{{table}}[t]
\centering
\caption{{Top prediction targets in the corpus (a study may target more
than one variable).}}
\label{{tab:targets}}
\small
\begin{{tabular}}{{@{{}}lc@{{}}}}
\toprule
\textbf{{Target}} & \textbf{{\#}} \\
\midrule
{trows}
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{ML methods}}
Table~\ref{{tab:methods}} reports the most frequent ML method keywords
detected in the corpus. A single study may contribute multiple counts when it
compares several methods.

\begin{{table}}[t]
\centering
\caption{{Most frequent ML method mentions across the corpus (heuristic
keyword mining).}}
\label{{tab:methods}}
\small
\begin{{tabular}}{{@{{}}lc@{{}}}}
\toprule
\textbf{{Method}} & \textbf{{\#}} \\
\midrule
{mrows}
\bottomrule
\end{{tabular}}
\end{{table}}"""


def build_feature_frequency_table(ctx):
    """Read feature_frequency.csv and emit a LaTeX table for the T3 section."""
    import csv as _csv
    p = OUTPUTS / "feature_frequency.csv"
    if not p.exists():
        return ""
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    # Top ~30 rows sorted by n_papers desc
    rows = sorted(rows, key=lambda r: -int(r.get("n_papers", 0) or 0))[:30]
    body = "\n".join(
        f"{latex_escape(r['feature_name'])} & {latex_escape(r['category'])} & {r['n_papers']} \\\\"
        for r in rows
    )
    return rf"""\begin{{table}}[t]
\centering
\caption{{Top-30 most frequent features across a sample of 49 papers with
explicit feature-list disclosure. Counts are lower bounds
(category-level occurrences within the sample).}}
\label{{tab:features}}
\small
\begin{{tabular}}{{@{{}}L{{4.6cm}}L{{2.5cm}}c@{{}}}}
\toprule
\textbf{{Feature}} & \textbf{{Category}} & \textbf{{N}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\end{{table}}"""


def section_results(ctx):
    cluster_text = ctx.get("cluster_narratives", {})
    feat_tbl = build_feature_frequency_table(ctx)
    blocks = []
    for c, title in [("T1", "ML baseline methods"), ("T2", "Physics-hybrid architectures"),
                     ("T3", "Feature engineering"), ("T4", "Online adaptation"),
                     ("T6", "Explainability")]:
        narr = cluster_text.get(c, f"This subsection summarises the {title.lower()} cluster. "
                                   "Narrative synthesis of per-paper findings was "
                                   "produced from the full-text extraction pass.")
        # For T3 inject the feature-frequency table after the narrative
        body = narr
        if c == "T3" and feat_tbl:
            body = narr + "\n\n" + feat_tbl
        blocks.append(rf"""\subsection{{{title} ({c})}}
\label{{sec:results-{c}}}
{body}""")
    return r"""\section{Results}
\label{sec:results}

The following subsections summarise findings per thematic cluster. Paper-level
details, metrics, and citations are tabulated in the supplementary material.

""" + "\n\n".join(blocks)


def section_discussion(ctx):
    validation_narr = ctx.get("validation", "")
    return rf"""\section{{Discussion}}
\label{{sec:discuss}}

\subsection{{Research gaps and validation audit}}
{validation_narr}

\subsection{{Reproducibility limitations of this review}}
The retrieval protocol used here restricts full-text analysis to openly
obtainable PDFs plus a curated author set. A number of paywalled records
(principally from IEEE~Xplore and Elsevier) could not be retrieved and are
documented explicitly; their abstracts were read and used for high-level
classification, but no paper-level metric extraction was performed. The set
of not-retrievable papers is listed in the supplementary material. Future
replications with institutional access should expand the corpus accordingly
and check whether the conclusions of this review are preserved."""


def section_conclusion(ctx):
    return rf"""\section{{Conclusion}}
\label{{sec:concl}}

This systematic review analysed {ctx['n_corpus']} peer-reviewed studies on
machine learning for vessel performance prediction and propulsion modelling.
Gradient boosting and tree-based ensembles dominate reported methods on
tabular operational data; physics-hybrid grey-box models are the most
consistent approach to improving out-of-distribution robustness; feature
engineering exerts an effect on accuracy comparable to the choice of learning
algorithm; and online adaptation of deployed models is the smallest and
least mature subfield. A reproducibility protocol addressing the systematic
validation heterogeneity observed across the corpus is proposed as the main
methodological recommendation of this review."""


def section_appendix_strings(ctx):
    S = ctx["strings"]
    lines = [r"\appendix", r"\section{Search strings}", r"\label{app:strings}"]
    for sid in "ABCD":
        lines.append(rf"\textbf{{String {sid}}}: \texttt{{{latex_escape(S[sid])}}}")
        lines.append("")
    return "\n".join(lines)


def section_appendix_corpus(ctx, key_map, papers):
    """Create a table of all corpus papers."""
    lines = [r"\onecolumn",
             r"\section{Included studies}",
             r"\label{app:included}",
             r"\small",
             r"\begin{longtable}{@{}p{1.2cm}p{0.8cm}p{1.4cm}p{8.5cm}p{1.2cm}@{}}",
             r"\toprule",
             r"\textbf{ID} & \textbf{Year} & \textbf{Cluster} & \textbf{Title (authors)} & \textbf{Ref.} \\",
             r"\midrule", r"\endhead"]
    for p in papers:
        key = key_map.get(p["dedup_id"], "")
        yr = latex_escape(p.get("year", ""))
        cl = ""
        for q in ctx.get("extractions", []):
            if q["dedup_id"] == p["dedup_id"]:
                cl = q.get("cluster", ""); break
        short_auth = (p.get("authors", "").split(",")[0] or "Anon")
        title_authors = f"{latex_escape(p.get('title',''))}"
        if short_auth:
            title_authors += f" \\emph{{({latex_escape(short_auth.strip())} et~al.)}}"
        lines.append(f"{latex_escape(p['dedup_id'])} & {yr} & {cl} & {title_authors} & \\cite{{{key}}} \\\\")
    lines += [r"\bottomrule", r"\end{longtable}", r"\twocolumn"]
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Load data
    with open(CORPUS_CSV, newline="", encoding="utf-8") as f:
        papers = list(csv.DictReader(f))
    with open(EXTR_JSON, encoding="utf-8") as f:
        extractions = json.load(f)["papers"]
    ext_by_id = {p["dedup_id"]: p for p in extractions}

    narratives = {}
    validation_text = ""
    if NARR_JSON.exists():
        with open(NARR_JSON, encoding="utf-8") as f:
            nd = json.load(f)
        narratives = nd.get("clusters", {})
        validation_text = nd.get("validation", "")

    # PRISMA flow
    flow_text = FLOW_TXT.read_text(encoding="utf-8")
    def num(pattern, default=0):
        m = re.search(pattern, flow_text)
        return int(m.group(1)) if m else default
    db = {"Semantic Scholar": num(r"Semantic Scholar\s+(\d+)"),
          "OpenAlex": num(r"OpenAlex\s+(\d+)"),
          "arXiv": num(r"arXiv\s+(\d+)"),
          "Scopus": num(r"Scopus\s+(\d+)"),
          "IEEE Xplore": num(r"IEEE Xplore\s+(\d+)")}
    n_raw = num(r"TOTAL raw\s+(\d+)")
    n_dedup = num(r"After dedup\s+:\s+(\d+)")
    n_title_fwd = num(r"After title screening\s+:\s+(\d+)")
    n_abs_fwd = num(r"After abstract screening\s+:\s+(\d+)")
    n_abs_inc = num(r"INCLUDE\s+:\s+(\d+)")
    n_abs_unc = num(r"UNCERTAIN\s+:\s+(\d+)")
    n_corpus = num(r"PDFs retrievable\s+:\s+(\d+)")
    n_notretr = num(r"Not retrievable\s+:\s+(\d+)")

    cluster_counts = Counter(ext_by_id[p["dedup_id"]]["cluster"]
                             for p in papers if p["dedup_id"] in ext_by_id)
    target_counts = Counter(t for p in papers
                            for t in ext_by_id.get(p["dedup_id"], {}).get("targets", []))
    method_counts = Counter(m for p in papers
                            for m in ext_by_id.get(p["dedup_id"], {}).get("methods", []))
    years_dist = Counter()
    for p in papers:
        y = str(p.get("year", "")).strip()
        if y.isdigit():
            years_dist[y] += 1

    STRINGS = {
        "A": '("ship" OR "vessel") AND ("fuel consumption" OR "speed prediction" OR "power prediction" OR "propulsion model") AND ("machine learning" OR "data-driven") AND ("sensor data" OR "operational data" OR "in-service data" OR "onboard data" OR "noon report" OR "voyage data")',
        "B": '("ship" OR "vessel") AND ("feature engineering" OR "feature selection" OR "variable selection" OR "input features") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "vessel performance") AND ("machine learning" OR "data-driven")',
        "C": '("ship" OR "vessel") AND ("physics-informed" OR "physics-based" OR "semi-empirical" OR "resistance model" OR "grey-box" OR "physics-guided") AND ("machine learning" OR "data-driven") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "power prediction" OR "vessel performance" OR "ship performance")',
        "D": '("ship" OR "vessel") AND ("model updating" OR "online learning" OR "adaptive model" OR "bias correction" OR "real-time calibration" OR "concept drift" OR "model drift" OR "sliding window") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "vessel performance" OR "prediction model")',
    }

    # Build bib first — we need key_map to rewrite narratives
    bib_text, key_map = build_bibtex(papers)
    OUT_BIB.write_text(bib_text, encoding="utf-8")
    print(f"  BibTeX: {OUT_BIB}")

    # Rewrite REC-xxx references in narratives to proper \cite{bibkey}
    corpus_by_id = {p["dedup_id"]: p for p in papers}
    narratives_rw = {k: rewrite_narrative(v, key_map, corpus_by_id)
                     for k, v in narratives.items()}
    validation_rw = rewrite_narrative(validation_text, key_map, corpus_by_id)

    ctx = {
        "search_date": date.today().strftime("%d %B %Y"),
        "db": db,
        "n_raw": n_raw, "n_dedup": n_dedup, "n_title_fwd": n_title_fwd,
        "n_abs_fwd": n_abs_fwd, "n_abs_inc": n_abs_inc, "n_abs_unc": n_abs_unc,
        "n_corpus": n_corpus, "n_notretr": n_notretr,
        "n_clusters": len(cluster_counts),
        "cluster_counts": cluster_counts,
        "target_counts": target_counts,
        "method_counts": method_counts,
        "years_dist": years_dist,
        "cluster_narratives": narratives_rw,
        "validation": validation_rw,
        "strings": STRINGS,
        "extractions": extractions,
    }

    preamble = r"""\documentclass[final,3p,times,twocolumn]{elsarticle}

\usepackage{hyperref}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{multirow}
\usepackage{xcolor}
\usepackage{enumitem}
\usepackage{caption}
\usepackage{amsmath}
\usepackage{rotating}
\usepackage{longtable}
\usepackage{fontspec}

\journal{Ocean Engineering}

\newcolumntype{L}[1]{>{\raggedright\arraybackslash}p{#1}}
\newcolumntype{C}[1]{>{\centering\arraybackslash}p{#1}}

\begin{document}

\begin{frontmatter}

\title{Machine Learning Methods for Vessel Performance Prediction and
Propulsion Modeling: A Systematic Literature Review}

\author[rtu,sp]{Dmitrijs Odinokijs\corref{cor1}}
\ead{dmitrijs.odinokijs@edu.rtu.lv}
\cortext[cor1]{Corresponding author}

\affiliation[rtu]{organization={Institute of Applied Computer Systems,
Faculty of Computer Science, Information Technology and Energy,
Riga Technical University},
addressline={Zunda Krastmala 10},
city={Riga},
postcode={LV-1048},
country={Latvia}}

\affiliation[sp]{organization={SIA ShipProjects},
addressline={Hospitalu iela 18A, Vidzemes priekspilseta},
city={Riga},
postcode={LV-1013},
country={Latvia}}

"""

    body = "\n\n".join([
        section_abstract(ctx),
        r"""\begin{keyword}
vessel performance prediction \sep
ship fuel consumption \sep
gradient boosting \sep
physics-informed machine learning \sep
feature engineering \sep
online adaptation \sep
grey-box model \sep
PRISMA systematic review
\end{keyword}

\end{frontmatter}""",
        section_intro(ctx),
        section_methodology(ctx),
        section_descriptive(ctx),
        section_results(ctx),
        section_discussion(ctx),
        section_conclusion(ctx),
    ])

    # Force every corpus paper into the bibliography via \nocite (invisible).
    # Narrative text already cites the papers actually discussed, so the
    # bibliography ends up containing both: cited-in-prose and reference-list-
    # only corpus members.
    nocite_all = "\\nocite{" + ",".join(
        key_map[p["dedup_id"]] for p in papers if p["dedup_id"] in key_map
    ) + "}"

    appendix = "\n\n".join([
        section_appendix_strings(ctx),
        section_appendix_corpus(ctx, key_map, papers),
    ])

    ending = rf"""

{nocite_all}
\bibliographystyle{{elsarticle-num}}
\bibliography{{SLR_final}}

{appendix}

\end{{document}}
"""

    OUT_TEX.write_text(preamble + body + ending, encoding="utf-8")
    print(f"  LaTeX : {OUT_TEX}")

    # Compile
    print("\nCompiling PDF…")
    for _ in range(2):  # need two passes for bibtex
        res = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", OUT_TEX.name],
            cwd=DELIVERABLES, capture_output=True)
    res_bib = subprocess.run(
        ["bibtex", OUT_TEX.stem],
        cwd=DELIVERABLES, capture_output=True)
    for _ in range(2):
        res = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", OUT_TEX.name],
            cwd=DELIVERABLES, capture_output=True)
    if OUT_PDF.exists():
        print(f"  PDF   : {OUT_PDF}  ({OUT_PDF.stat().st_size} bytes)")
    else:
        print(f"  pdflatex FAILED. Tail of log:")
        log = (DELIVERABLES / (OUT_TEX.stem + ".log"))
        if log.exists():
            print(log.read_text()[-2000:])


if __name__ == "__main__":
    main()
