#!/usr/bin/env bash
# End-to-end PRISMA SLR pipeline runner.
# Run from src/: ./run_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "=== Stage 1: Search + dedup + title screening ==="
python3 prisma_pipeline.py --all

echo "=== Stage 2: Abstract screening ==="
python3 abstract_screen.py

echo "=== Stage 3: PDF inventory (first pass, with abstract-only rejection) ==="
python3 pdf_inventory.py

echo "=== Stage 4: Find OA links for missing ==="
cd helpers
python3 find_links.py

echo "=== Stage 5: Auto-fetch OA PDFs ==="
python3 fetch_oa_pdfs.py
cd ..

echo "=== Stage 6: PDF inventory (re-run to pick up fetched) ==="
python3 pdf_inventory.py

echo "=== Stage 7: Finalize corpus ==="
python3 finalize_corpus.py

echo "=== Stage 8: Extract paper content (heuristic) ==="
python3 extract_paper_content.py

echo "=== Stage 9: Click-list for the remaining manual fetch ==="
cd helpers
python3 find_links.py
cd ..
# Several open-access publishers block scripted downloads; generate the
# publisher-grouped click-list and fetch the remaining PDFs in a browser:
#   python3 helpers/build_manual_fetch_list.py --dir <output dir>

echo ""
echo "Pipeline complete."
echo "  Outputs: ../workspace/outputs/"
echo ""
echo "Next steps (manual):"
echo "  1. Review paper_extractions.json for completeness"
echo "  2. Retrieve remaining PDFs via the generated HTML lists (browser pass;"
echo "     several open-access publishers block scripted downloads)"
echo ""
echo "Update search (extend the year window, e.g. to include a new year):"
echo "  PRISMA_YEAR_MIN=2026 PRISMA_YEAR_MAX=2026 PRISMA_OUT_DIR=<dir> python3 prisma_pipeline.py --all"
echo "  python3 ss_reharvest.py --out <dir>      # Semantic Scholar, rate-limit tolerant"
echo "  python3 merge_ss.py --dir <dir>          # merge + re-dedup + re-screen"
echo "  python3 finalize_update.py               # combined corpus + PRISMA flow"
