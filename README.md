# PRISMA Systematic Literature Review: ML Methods for Vessel Performance Prediction

A PRISMA 2020-compliant systematic literature review of machine learning methods applied to vessel performance prediction and propulsion modeling.

**Paper:** *Machine Learning Methods for Vessel Performance Prediction and Propulsion Modeling: A Systematic Literature Review*  
**Author:** Dmitrijs Odinokijs (Riga Technical University / SIA ShipProjects)  
**Preprint submitted to:** Ocean Engineering  

## Overview

This repository contains the reproducible search pipeline and analysis code for a systematic review covering:

1. **ML baselines** for fuel consumption, speed, and power prediction (T1, 60 papers)
2. **Physics-hybrid architectures** — grey-box models, physics-informed neural networks (T2, 27 papers)
3. **Feature engineering** for maritime sensor time series (T3, 15 papers)
4. **Online adaptation** and real-time recalibration of deployed models (T4, 9 papers)
5. **Explainability** — SHAP, LIME for propulsion models (T6, 5 papers)

**Key finding:** Literature routinely reports R² = 0.95–0.99, but this is systematically inflated by random k-fold splitting on time-series data (data leakage). Under temporally rigorous holdout protocols, R² = 0.75–0.95. In production deployment without feature engineering, R² ≈ 0.30–0.40; with systematic feature engineering, R² ≈ 0.60–0.70.

## PRISMA Flow

```
869 raw records (4 databases + manual)
 → 575 after deduplication (DOI + fuzzy title matching)
   → 181 after title screening (3 passes)
     → 137 after abstract screening
       → 116 included studies (full-text assessed)
```

**Databases searched (April 14, 2026):** Semantic Scholar (279), OpenAlex (400), arXiv (9), Scopus (176), manual (5)

## Repository Structure

```
├── README.md                           # This file
├── src/
│   ├── prisma_pipeline.py              # Main search + screening pipeline
│   ├── build_q1_report.py              # LIAA Q1 report generator (Latvian)
│   └── manuscript_revision_instructions.md
└── .gitignore
```

**Not tracked (available on request):**
- `PRISMA_search_results_2026-04-14.xlsx` — full Excel with all sheets
- `PRISMA_AI_Search_Log_v2_verified.xlsx` — verified metrics version
- `*.csv` — raw records, deduplicated records, screening results
- `pdfs_*` — collected PDF papers
- `SLR_final_v2.tex` / `SLR_final_v2.pdf` — manuscript
- `Q1_Literaturas_Parskats_LIAA.docx` — LIAA Q1 deliverable

## Setup and Reproduction

### Prerequisites

```bash
# Python 3.10+
pip install scholarly rapidfuzz openpyxl requests pdfminer.six python-docx PyPDF2
```

### API Keys

The pipeline uses these free API keys (set as variables in `prisma_pipeline.py`):

| API | How to get | Required? |
|-----|-----------|-----------|
| Semantic Scholar | https://www.semanticscholar.org/product/api | Yes (free, apply for key) |
| Scopus / Elsevier | https://dev.elsevier.com/ | Yes (free, institutional) |
| IEEE Xplore | https://developer.ieee.org/ | Optional (was unavailable during this study) |
| OpenAlex | No key needed | — |
| arXiv | No key needed | — |

### Run the pipeline

```bash
cd src

# Full pipeline: search + deduplicate + screen
python prisma_pipeline.py --all

# This produces:
#   search_log.csv          — 20 database-string entries
#   records_raw.csv         — all raw records
#   records_deduplicated.csv — unique records
#   title_screened.csv      — screening decisions
#   PRISMA_search_results_YYYY-MM-DD.xlsx
```

### Reproduce screening

The pipeline includes three screening passes:
1. **Title Pass 1** — keyword-based PASS/FAIL/MAYBE
2. **Title Pass 2** — extended rules for MAYBE refinement (built into `prisma_pipeline.py`)
3. **Abstract screening** — run separately after Pass 2 (see `title_screened.csv`)

Full-text screening and metric extraction require manual PDF review.

### Generate LIAA Q1 report

```bash
python build_q1_report.py
# Produces: Q1_Literaturas_Parskats_LIAA.docx
```

## Search Strings

| String | Focus | Query |
|--------|-------|-------|
| A | Core propulsion | `("ship" OR "vessel") AND ("fuel consumption" OR "speed prediction" OR "power prediction" OR "propulsion model") AND ("machine learning" OR "data-driven") AND ("sensor data" OR "operational data" OR "in-service data" OR "onboard data" OR "noon report" OR "voyage data")` |
| B | Feature engineering | `("ship" OR "vessel") AND ("feature engineering" OR "feature selection" OR "variable selection" OR "input features") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "vessel performance") AND ("machine learning" OR "data-driven")` |
| C | Physics-hybrid | `("ship" OR "vessel") AND ("physics-informed" OR "physics-based" OR "semi-empirical" OR "resistance model" OR "grey-box" OR "physics-guided") AND ("machine learning" OR "data-driven") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "power prediction" OR "vessel performance" OR "ship performance")` |
| D | Real-time recalibration | `("ship" OR "vessel") AND ("model updating" OR "online learning" OR "adaptive model" OR "bias correction" OR "real-time calibration" OR "concept drift" OR "model drift" OR "sliding window") AND ("propulsion" OR "fuel consumption" OR "speed prediction" OR "vessel performance" OR "prediction model")` |

## Citation

If you use this pipeline or findings, please cite:

```bibtex
@article{odinokijs2026slr,
  title={Machine Learning Methods for Vessel Performance Prediction and 
         Propulsion Modeling: A Systematic Literature Review},
  author={Odinokijs, Dmitrijs},
  journal={Ocean Engineering (preprint)},
  year={2026}
}
```

## Acknowledgments

This work was conducted as part of a research project funded by LIAA (Investment and Development Agency of Latvia) at SIA ShipProjects, in conjunction with doctoral studies at Riga Technical University.

## License

MIT
