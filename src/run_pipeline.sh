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

echo "=== Stage 9: Helpers for remaining manual fetch ==="
cd helpers
python3 find_links.py
python3 paywalled_list.py
python3 make_priority_list.py
cd ..

echo ""
echo "Pipeline complete."
echo "  Outputs: ../workspace/outputs/"
echo ""
echo "Next steps (manual):"
echo "  1. Review paper_extractions.json for completeness"
echo "  2. Write thematic narratives (T1–T6 cluster analysis)"
echo "  3. Run report generators: cd reports && python3 build_q1_report.py"
echo "  4. Compile manuscript: python3 build_slr_manuscript.py"
