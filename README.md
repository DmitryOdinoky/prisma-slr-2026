# PRISMA SLR: ML Methods for Vessel Performance Prediction

PRISMA 2020 systematic literature review of machine learning methods for vessel performance prediction and propulsion modelling.

**Author:** Dmitrijs Odinokijs (RTU / SIA ShipProjects)

## PRISMA flow (April 2026)

```
913 raw records (5 databases)
 → 593 after deduplication
   → 358 after title screening
     → 193 after abstract screening (incl. 32 manual exclusions)
       → 174 full-text PDFs retrievable (final corpus)
           19 not retrievable (paywalled — documented)
```

## Repository structure

```
src/                            Core reproducible pipeline
  prisma_pipeline.py            Search 5 databases + dedup + title screen
  abstract_screen.py            Abstract-level screening with Crossref backfill
  pdf_inventory.py              Match records to PDFs, reject abstract-only (<4 pages)
  extract_paper_content.py      Heuristic metadata extraction from PDFs
  finalize_corpus.py            PRISMA flow counts + final_corpus.csv
  citation_utils.py             Shared bibliography/citation helpers
  run_pipeline.sh               End-to-end driver script

src/helpers/                    PDF retrieval aids (not needed for reproduction)
  fetch_oa_pdfs.py              Auto-fetch via Unpaywall / Semantic Scholar / OpenAlex
  find_links.py                 Find OA link candidates for missing PDFs
  paywalled_list.py             Generate publisher-grouped HTML for manual fetch
  make_priority_list.py         Priority HTML list
  build_not_retrievable_html.py Interactive HTML for tracking manual downloads

src/reports/                    Report generators (LIAA deliverables)
  build_q1_report.py            Latvian Q1 literature review (.docx)
  build_q1_deliverables.py      Full LIAA Q1 delivery package
  build_slr_manuscript.py       LaTeX SLR paper + compile to PDF

data/                           Supplementary data (tracked, for reproducibility)
  search_log.csv                20 queries across 5 databases
  records_raw.csv               913 raw records
  records_deduplicated.csv      593 unique records after DOI + fuzzy dedup
  title_screened.csv            593 records with PASS/FAIL/MAYBE
  abstract_screened.csv         593 records with INCLUDE/UNCERTAIN/EXCLUDE
  final_corpus.csv              174 included studies with metadata + PDF paths
  not_retrievable.csv           19 paywalled records (PRISMA limitation)
  prisma_flow_counts.txt        Record counts at each screening stage
  PRISMA_search_results.xlsx    Full Excel (5 sheets: logs, dedup, screened, corpus, not-retr)

src/baselineTrainerValidator/   Baseline model (gitignored — proprietary data)
workspace/                      PDFs, outputs, deliverables (gitignored)
templates/                      Report templates (gitignored)
```

## Setup

```bash
pip install requests rapidfuzz openpyxl pdfminer.six PyPDF2 python-docx xgboost joblib
# For LaTeX compilation:
sudo apt install texlive-xetex texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra
```

### API keys

Keys must be set as environment variables — never hardcoded.

```bash
export SS_API_KEY="your-semantic-scholar-key"      # https://www.semanticscholar.org/product/api
export SCOPUS_API_KEY="your-scopus-key"            # https://dev.elsevier.com/
export IEEE_API_KEY="your-ieee-xplore-key"         # https://developer.ieee.org/
```

OpenAlex and arXiv do not require keys.

## Reproduction guide

### What is fully reproducible

Running `src/run_pipeline.sh` with the same API keys and date will produce:
- **Identical search results** (same queries → same database responses, ±minor indexing changes)
- **Identical deduplication** (deterministic DOI + fuzzy title matching, threshold 90%)
- **Identical title screening** (keyword rules hardcoded in `prisma_pipeline.py`)
- **Identical abstract screening** (keyword rules in `abstract_screen.py`)
- **Identical PDF validity check** (page count ≥4, text length ≥6000 chars)
- **Identical content extraction** (regex-based, deterministic)

### What is NOT reproducible (and why)

Three steps in this SLR involved subjective human judgement:

1. **Manual exclusions (32 papers).** After automated screening, 32 papers were manually excluded as out-of-scope based on the reviewer's reading of their titles and abstracts. These papers passed the keyword-based screening but were judged irrelevant upon closer inspection (e.g., papers about ship detection from satellite imagery, non-propulsion maritime topics). The excluded IDs are applied in `run_pipeline.sh` as a hardcoded list; a different reviewer might exclude a partially different set.

2. **PDF collection.** Full-text retrieval combined three sources: (i) a personal collection of relevant papers accumulated over two years of active research; (ii) open-access PDFs obtained programmatically via Unpaywall, OpenAlex, Semantic Scholar, and arXiv; and (iii) paywalled papers accessed through Riga Technical University's institutional library subscriptions. A researcher with different institutional access may obtain a partially different set. The 19 papers that were not available through RTU's subscriptions are documented in `not_retrievable.csv`.

3. **Thematic narrative synthesis.** The cluster-level narratives (T1–T6 discussions) in the manuscript and Q1 report were written by the primary reviewer after reading the full-text corpus. A different reviewer reading the same papers may emphasise different aspects or draw partially different conclusions. The structured data (`paper_extractions.json`, `feature_frequency.csv`) is deterministic; the interpretive narrative is inherently reviewer-dependent.

### Step-by-step reproduction

```bash
cd src

# 1. Automated pipeline (deterministic)
export SS_API_KEY="..." SCOPUS_API_KEY="..." IEEE_API_KEY="..."
python3 prisma_pipeline.py --all
python3 abstract_screen.py

# 2. Apply manual exclusions (reviewer judgement — list provided)
python3 -c "
import csv
exclude = {'REC-560','REC-562','REC-508','REC-454','REC-127','REC-590',
           'REC-580','REC-531','REC-411','REC-589','REC-150','REC-573',
           'REC-586','REC-593','REC-131','REC-567','REC-205','REC-403',
           'REC-588','REC-587','REC-529','REC-577','REC-582','REC-518',
           'REC-570','REC-514','REC-087','REC-532','REC-563','REC-583',
           'REC-062','REC-517'}
# ... (see run_pipeline.sh for full script)
"

# 3. PDF matching (depends on which PDFs you have on disk)
python3 pdf_inventory.py

# 4. OA fetching (optional — fetches what's freely available)
cd helpers
python3 find_links.py
python3 fetch_oa_pdfs.py
cd ..
python3 pdf_inventory.py    # re-run to pick up fetched

# 5. Finalize + extract
python3 finalize_corpus.py
python3 extract_paper_content.py

# 6. Reports (optional — LIAA-specific)
cd reports
python3 build_q1_report.py
python3 build_slr_manuscript.py
```

### Reproducing with a different PDF set

If you have institutional access to paywalled journals:
1. Download additional PDFs into `workspace/pdfs_custom/`
2. Add the folder name to `PDF_DIRS` in `src/pdf_inventory.py`
3. Re-run from step 3 onward

The 19 records in `not_retrievable.csv` are the most likely candidates to improve corpus coverage.

## Search strings

| ID | Focus | Core query |
|----|-------|-----------|
| A | Propulsion modelling | `("ship" OR "vessel") AND ("fuel consumption" OR "speed prediction" OR ...) AND ("machine learning" OR "data-driven") AND ("sensor data" OR "operational data" OR ...)` |
| B | Feature engineering | `("ship" OR "vessel") AND ("feature engineering" OR "feature selection" OR ...) AND ("propulsion" OR ...) AND ("machine learning" OR ...)` |
| C | Physics-hybrid | `("ship" OR "vessel") AND ("physics-informed" OR "grey-box" OR ...) AND ("machine learning" OR ...) AND ("propulsion" OR ...)` |
| D | Online adaptation | `("ship" OR "vessel") AND ("model updating" OR "online learning" OR "concept drift" OR ...) AND ("propulsion" OR ...)` |

Full strings in `src/prisma_pipeline.py`.

## Citation

```bibtex
@unpublished{odinokijs2026slr,
    title={Machine Learning Methods for Vessel Performance Prediction and
           Propulsion Modeling: A Systematic Literature Review},
    author={Odinokijs, Dmitrijs},
    note={Manuscript in preparation},
    year={2026}
  }
```

## Acknowledgments

Conducted at SIA ShipProjects in conjunction with doctoral studies at Riga Technical University.

## License

MIT
