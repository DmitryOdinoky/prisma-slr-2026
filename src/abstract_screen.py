#!/usr/bin/env python3
"""
Abstract screening stage of the PRISMA pipeline.

Input : title_screened.csv  (forwards records where title_screen in {PASS, MAYBE})
Steps : 1) Backfill missing abstracts via Crossref (by DOI)
        2) Apply abstract-level PASS/FAIL/UNCERTAIN rules (eligibility criteria E1..E5)
Output: abstract_screened.csv
"""

import csv
import os
import sys
import time
from collections import Counter

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUTS = os.path.join(REPO_ROOT, "workspace", "outputs")
IN_CSV = os.path.join(OUTPUTS, "title_screened.csv")
OUT_CSV = os.path.join(OUTPUTS, "abstract_screened.csv")

# ── Abstract screening rule sets ─────────────────────────────────────────────

MARITIME = ["ship", "vessel", "maritime", "marine", "bulk carrier", "container ship",
            "tanker", "tugboat", "cruise", "ferry", "naval", "hull"]

PERF_TOPIC = ["fuel consumption", "fuel oil", "specific fuel", "speed prediction",
              "power prediction", "shaft power", "brake power", "propulsion",
              "vessel performance", "ship performance", "energy efficiency",
              "main engine", "engine performance", "speed loss", "speed-power",
              "propeller performance", "hull fouling", "biofouling",
              "carbon intensity", "eedi", "cii", "resistance model",
              "in-service performance", "operational efficiency"]

ML_METHOD = ["machine learning", "neural network", "deep learning", "random forest",
             "xgboost", "gradient boosting", "lightgbm", "catboost", "svm",
             "support vector", "regression", "data-driven", "physics-informed",
             "grey-box", "gray-box", "digital twin", "ensemble learning",
             "online learning", "transfer learning", "reinforcement learning",
             "lstm", "gru", "transformer", "autoencoder", "gaussian process",
             "decision tree", "feature engineering", "feature selection"]

# Abstract-level off-topic signals (strong FAIL)
OFFTOPIC_E5 = ["lithium-ion", "state of charge", "battery degradation",
               "electric vehicle ", " ev charging", "wind turbine", "wind farm",
               "solar panel", "photovoltaic", "pv system", "microgrid",
               "power grid ", "smart grid", "medical", "patient", "clinical",
               "retinal", "cancer", "covid", "traffic signal", "urban traffic",
               "building energy", "building hvac", "automotive engine",
               "railway", "aircraft", "airplane", "drone ", "uav "]

# Abstract-level out-of-scope maritime topics (E1)
OFFTOPIC_E1 = ["collision avoidance", "trajectory prediction", "ship detection",
               "vessel detection", "object detection", "path planning",
               "route optimization", "weather routing", "voyage optimization",
               "dynamic positioning", "motion prediction", "roll prediction",
               "pitch prediction", "sea state estimation", "wave prediction",
               "berthing", "mooring", "cavitation noise", "underwater noise",
               "port scheduling", "ballast water", "structural integrity",
               "hull inspection", "corrosion detection", "crack detection",
               "ais-based trajectory", "anomaly detection in ais"]


def screen_abstract(title, abstract):
    """Return (decision, reason). Decision in {INCLUDE, EXCLUDE, UNCERTAIN}."""
    a = (abstract or "").lower().strip()
    t = (title or "").lower().strip()

    if not a or len(a) < 120:
        # No abstract → fall back to title signal
        if any(k in t for k in PERF_TOPIC) and any(k in t for k in MARITIME):
            return "UNCERTAIN", "no-abstract; title relevant"
        return "UNCERTAIN", "no-abstract"

    # Hard FAIL: off-topic signals
    for term in OFFTOPIC_E5:
        if term in a:
            return "EXCLUDE", f"E5:{term.strip()}"
    for term in OFFTOPIC_E1:
        if term in a:
            return "EXCLUDE", f"E1:{term}"

    has_maritime = any(k in a for k in MARITIME)
    has_perf = any(k in a for k in PERF_TOPIC)
    has_ml = any(k in a for k in ML_METHOD)

    if not has_maritime:
        return "EXCLUDE", "E1:non-maritime"
    if not has_perf:
        return "EXCLUDE", "E1:non-performance-topic"
    if not has_ml:
        # Allow physics/semi-empirical-only if clearly perf modeling
        if any(k in a for k in ["semi-empirical", "physics-based model", "holtrop",
                                 "resistance estimation", "admiralty formula"]):
            return "INCLUDE", "physics-only perf model"
        return "EXCLUDE", "E3:no-ML-method"

    return "INCLUDE", ""


# ── Crossref backfill ────────────────────────────────────────────────────────

CROSSREF = "https://api.crossref.org/works/"


def fetch_abstract(doi):
    if not doi:
        return ""
    try:
        r = requests.get(CROSSREF + doi, timeout=15,
                         headers={"User-Agent": "PRISMA-SLR/1.0 (mailto:dmitry.odinoky@gmail.com)"})
        if r.status_code != 200:
            return ""
        msg = r.json().get("message", {})
        abs_ = msg.get("abstract", "") or ""
        # Strip JATS tags
        import re
        abs_ = re.sub(r"<[^>]+>", " ", abs_)
        abs_ = re.sub(r"\s+", " ", abs_).strip()
        return abs_
    except Exception:
        return ""


def main():
    with open(IN_CSV, newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    forwarded = [r for r in all_rows if r["title_screen"] in ("PASS", "MAYBE")]
    print(f"Loaded {len(all_rows)} screened; {len(forwarded)} forwarded (PASS+MAYBE)")

    need = [r for r in forwarded if not (r.get("abstract") or "").strip() and r.get("doi")]
    print(f"\n=== Backfilling abstracts via Crossref: {len(need)} records ===")
    filled = 0
    for i, r in enumerate(need, 1):
        abs_ = fetch_abstract(r["doi"])
        if abs_ and len(abs_) > 80:
            r["abstract"] = abs_
            filled += 1
        if i % 20 == 0:
            print(f"  {i}/{len(need)} done ({filled} filled)")
        time.sleep(0.3)
    print(f"  Total backfilled: {filled}/{len(need)}")

    print("\n=== Abstract screening ===")
    out_rows = []
    dec_counter = Counter()
    reason_counter = Counter()
    for r in forwarded:
        decision, reason = screen_abstract(r.get("title", ""), r.get("abstract", ""))
        dec_counter[decision] += 1
        if reason:
            reason_counter[reason.split(":")[0]] += 1
        out_rows.append({
            **{k: r.get(k, "") for k in
               ["dedup_id", "title", "authors", "year", "venue", "doi", "url",
                "abstract", "source_database", "string_id", "also_found_in",
                "title_screen", "title_fail_reason"]},
            "abstract_length": len((r.get("abstract") or "").strip()),
            "abstract_screen": decision,
            "abstract_fail_reason": reason,
        })

    fieldnames = ["dedup_id", "title", "authors", "year", "venue", "doi", "url",
                  "abstract", "source_database", "string_id", "also_found_in",
                  "title_screen", "title_fail_reason",
                  "abstract_length", "abstract_screen", "abstract_fail_reason"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  Wrote: {OUT_CSV}")

    print("\n=== Summary ===")
    for k in ["INCLUDE", "EXCLUDE", "UNCERTAIN"]:
        print(f"  {k:10s}: {dec_counter.get(k, 0)}")
    print(f"\n  Exclusion reason families: {dict(reason_counter)}")
    print(f"\n  → Forward to full-text: {dec_counter['INCLUDE'] + dec_counter['UNCERTAIN']}")
    print(f"    (INCLUDE = high-confidence; UNCERTAIN = manual/PDF needed)")

    # IEEE contribution
    ieee = [r for r in out_rows if r["source_database"] == "IEEE Xplore"]
    ieee_inc = [r for r in ieee if r["abstract_screen"] == "INCLUDE"]
    ieee_unc = [r for r in ieee if r["abstract_screen"] == "UNCERTAIN"]
    print(f"\n  IEEE Xplore: {len(ieee)} forwarded → {len(ieee_inc)} INCLUDE + {len(ieee_unc)} UNCERTAIN")


if __name__ == "__main__":
    main()
