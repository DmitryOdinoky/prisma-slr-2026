# PRISMA SLR: ML Methods for Vessel Performance Prediction

PRISMA 2020 systematic literature review of machine learning methods for vessel performance prediction and propulsion modelling.

**Authors:** Dmitrijs Odinokijs (RTU / SIA ShipProjects), Tomass Parandjuks (University of Latvia / SIA ShipProjects)

## PRISMA flow

Searches were executed on 17 April 2026 and complemented on 14 July 2026 to
capture publications from 2026. All queries used the same four Boolean search
strings across five databases, date-filtered to 2015–2026.

```
1428 raw records (Semantic Scholar 324, OpenAlex 800, arXiv 17,
                  Scopus 232, IEEE Xplore 55)
 → 941 after deduplication
   → 640 after title screening
     → 302 after abstract screening (288 automated + 14 re-admitted
                                     by manual reviewer reconsideration)
       → 267 full-text PDFs retrieved (final corpus)
          35 not retrievable (documented)
```

Per-search-arm stage counts are in `data/prisma_flow_update.txt`; the original
17 April searches alone yielded 913 → 593 → 400 → 217 → 196 (+21 not
retrievable).

Abstract-stage decisions of the automated keyword screen were also subject
to manual reviewer reconsideration: 14 excluded records were re-admitted on
full reading of their abstracts. The complete audit trail (automated verdict,
decision, and rationale for every reviewed record) is in
`data/abstract_reconsider_2026-07.csv`.

The original title-stage PASS count includes 42 records that were re-admitted
through manual reviewer judgement after the automated keyword screen
flagged them as FAIL (titles too short or generic for the keyword rules
to act on, but on inspection clearly in scope). These are recorded with
the value `reconsider` in the `Title Screened` sheet of the Excel
workbook and merged with the automated `PASS` set in `title_screened.csv`.

## Repository structure

```
src/                            Core reproducible pipeline
  prisma_pipeline.py            Search 5 databases + dedup + title screen
  abstract_screen.py            Abstract-level screening with Crossref backfill
  pdf_inventory.py              Match records to PDFs, reject abstract-only (<4 pages)
  extract_paper_content.py      Heuristic metadata extraction from PDFs
  finalize_corpus.py            PRISMA flow counts + final_corpus.csv
  run_pipeline.sh               End-to-end driver script

  ss_reharvest.py               Semantic Scholar harvest tolerant of rate limits
                                (throttled, resumable, picks up a new key mid-run)
  merge_ss.py                   Merge separately-harvested SS records, re-dedup + re-screen
  match_manual_pdfs.py          Match manually-downloaded PDFs to records by content (DOI/title)
  finalize_update.py            Merge new records into the corpus + combined PRISMA flow
  analyze_validation_protocol.py  Classify papers by validation protocol + headline R^2
                                (evidence behind the manuscript's Table 2)

src/helpers/                    PDF retrieval aids
  find_links.py                 Find OA link candidates (Unpaywall / S2 / OpenAlex / arXiv)
  fetch_oa_pdfs.py              Auto-fetch open-access PDFs
  build_manual_fetch_list.py    Publisher-grouped click-list for the manual browser pass

data/                           Supplementary data (tracked, for reproducibility)
  search_log.csv                20 queries across 5 databases
  records_raw.csv               913 raw records
  records_deduplicated.csv      593 unique records after DOI + fuzzy dedup
  title_screened.csv            593 records with PASS/FAIL/MAYBE
  abstract_screened.csv         400 records (title PASS+MAYBE) with INCLUDE/UNCERTAIN/EXCLUDE
  final_corpus.csv              196 included studies with metadata + PDF paths
  not_retrievable.csv           21 paywalled records (PRISMA limitation)
  prisma_flow_counts.txt        Record counts at each screening stage
  PRISMA_search_results.xlsx    Full Excel (5 sheets: logs, dedup, screened, corpus, not-retr)
  update_2026/                  Complementary searches of 14 July 2026
    search_log.csv              Update search log (incl. Semantic Scholar harvest)
    records_raw_merged.csv      515 raw records
    records_deduplicated_merged.csv  355 unique (348 new to the corpus)
    title_screened_merged.csv   Title-screen verdicts (355 records)
    abstract_screened_merged.csv Abstract-screen verdicts
    PRISMA_search_results_update.xlsx  Full Excel workbook (update searches)
  final_corpus_updated.csv      Combined 267-study corpus (final)
  not_retrievable_updated.csv   Combined 35 not-retrievable records
  prisma_flow_update.txt        Per-search-arm stage counts
  protocol_classification.csv   Per-paper validation-protocol assignment + headline R^2
  protocol_summary.json         Aggregates behind the manuscript's Table 2
  abstract_reconsider_2026-07.csv  Abstract-stage manual reconsideration audit trail

src/baselineTrainerValidator/   Baseline model (gitignored — proprietary data)
workspace/                      PDFs, outputs, deliverables (gitignored)
templates/                      Report templates (gitignored)
```

## Setup

```bash
pip install requests rapidfuzz openpyxl pdfminer.six PyPDF2
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

1. **Manual title-screen reconsideration (42 papers).** After the automated keyword title screen produced PASS=173, MAYBE=185, FAIL=235, the reviewer re-examined the 235 FAIL records and re-admitted 42 of them as in-scope (titles that the keyword rules could not classify reliably — typically very short titles or those that name a model architecture rather than the application domain). These 42 records appear with `title_screen=PASS` in `data/title_screened.csv` and are tagged `reconsider` in the Excel workbook so the original automated decision is preserved. Net effect: 173 + 42 + 185 MAYBE = 400 records forwarded to abstract screening. A different reviewer might re-admit a partially different set.

2. **PDF collection.** Full-text retrieval combined three sources: (i) a personal collection of relevant papers accumulated over two years of active research; (ii) open-access PDFs obtained programmatically via Unpaywall, OpenAlex, Semantic Scholar, and arXiv; and (iii) paywalled papers accessed through Riga Technical University's institutional library subscriptions. A researcher with different institutional access may obtain a partially different set. The papers that were not available through any of these channels are documented in `not_retrievable.csv` (21, original searches) and `not_retrievable_updated.csv` (35, combined 2015–2026 corpus).

3. **Thematic narrative synthesis.** The cluster-level narratives (T1–T6 discussions) in the manuscript were written by the primary reviewer after reading the full-text corpus. A different reviewer reading the same papers may emphasise different aspects or draw partially different conclusions. The structured data (`paper_extractions.json`, `feature_frequency.csv`) is deterministic; the interpretive narrative is inherently reviewer-dependent.

### Step-by-step reproduction

```bash
cd src

# 1. Automated pipeline (deterministic)
export SS_API_KEY="..." SCOPUS_API_KEY="..." IEEE_API_KEY="..."
python3 prisma_pipeline.py --all
#   → records_raw.csv (913), records_deduplicated.csv (593),
#     title_screened.csv (PASS=173, MAYBE=185, FAIL=235)

# 2. Manual title-screen reconsideration (reviewer judgement)
#    Re-admit 42 records from FAIL → PASS using the reference set in
#    data/title_screened.csv (column title_screen). The IDs that were
#    re-admitted by this review are exactly the rows whose title_screen
#    is PASS in data/title_screened.csv but whose automated rules would
#    have produced FAIL — see the Excel workbook (Title Screened sheet,
#    value 'reconsider') for the audit trail.

python3 abstract_screen.py
#   → abstract_screened.csv (400 forwarded; INCLUDE=136, UNCERTAIN=81, EXCLUDE=183)

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
#   → final_corpus.csv (196), not_retrievable.csv (21), prisma_flow_counts.txt
python3 extract_paper_content.py
```

### Update search (extending the year window)

```bash
export PRISMA_YEAR_MIN=2026 PRISMA_YEAR_MAX=2026
export PRISMA_OUT_DIR=$PWD/../workspace/outputs/window_2026
export PRISMA_DATABASES="openalex,scopus,ieee,arxiv"   # SS handled separately
python3 prisma_pipeline.py --all
python3 ss_reharvest.py --out ../workspace/outputs/window_2026
python3 merge_ss.py --dir ../workspace/outputs/window_2026
python3 finalize_update.py
python3 analyze_validation_protocol.py
```

Note: several gold open-access publishers (notably MDPI) refuse scripted
downloads via bot protection regardless of client headers; the affected PDFs
download normally in a browser. `helpers/build_manual_fetch_list.py`
generates a publisher-grouped click-list with target filenames so the manual
pass feeds straight back into the pipeline.

### Reproducing with a different PDF set

If you have institutional access to paywalled journals:
1. Download additional PDFs into `workspace/pdfs_custom/`
2. Add the folder name to `PDF_DIRS` in `src/pdf_inventory.py`
3. Re-run from step 3 onward

The 21 records in `not_retrievable.csv` are the most likely candidates to improve corpus coverage.

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
    author={Odinokijs, Dmitrijs and Parandjuks, Tomass},
    note={Manuscript in preparation},
    year={2026}
  }
```

## Acknowledgments

Conducted at SIA ShipProjects in conjunction with doctoral studies at Riga Technical University.

## License

MIT
