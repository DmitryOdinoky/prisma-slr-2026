#!/usr/bin/env python3
"""
Classify each corpus paper by validation protocol and pair it with its headline
R^2, so the review's central RQ1 claim — that reported accuracy is governed by
validation protocol more than by algorithm choice — is backed by corpus-wide
COUNTS and per-group medians, not just a table of typical ranges and a few
illustrative citations (co-author review comment, T. Parandjuks).

Protocol is inferred from the full text via keyword signatures, in priority
order (a paper matching several is assigned its most rigorous protocol, since a
temporal/blocked scheme is the binding constraint on the reported number):

  temporal_holdout  chronological / out-of-time / train-past-test-future split
  blocked_cv        time-series / blocked / voyage-block cross-validation
  random_kfold      k-fold or shuffled split with no temporal safeguard
  unclear           no protocol language detected

Headline R^2 per paper = the maximum reported R^2 (the number a reader remembers
and cross-study comparisons quote). Papers reporting no R^2 contribute to the
counts but not to the median.

This is a transparent heuristic over PDF text, not a hand audit; the per-paper
assignments are written out (protocol_classification.csv) so they can be spot-
checked and corrected.

Run:  python3 src/analyze_validation_protocol.py
"""
import csv
import json
import re
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEXTS = REPO / "workspace" / "outputs" / "paper_texts"
CORPUS = REPO / "workspace" / "outputs" / "update_2026_final" / "final_corpus_updated.csv"
EXTR = [REPO / "workspace" / "outputs" / "paper_extractions.json",
        REPO / "workspace" / "outputs" / "update_2026_final" / "extractions_2026_all.json",
        REPO / "workspace" / "outputs" / "update_2026_final" / "extractions_recovered.json"]
OUT = REPO / "workspace" / "outputs" / "update_2026_final"

# Signatures, checked most-rigorous first.
TEMPORAL = [
    "temporal holdout", "temporal split", "chronological split", "chronologically split",
    "out-of-time", "out of time", "train on the first", "trained on the first",
    "past data", "future period", "future unseen", "hold-out period", "held-out period",
    "last voyage", "final voyage", "later voyages", "train/validation/test split by time",
    "temporally disjoint", "walk-forward", "rolling-origin", "rolling origin",
]
BLOCKED = [
    "blocked cross-validation", "blocked cv", "time series split", "time-series split",
    "timeseriessplit", "voyage-block", "voyage block", "grouped cross-validation",
    "group k-fold", "groupkfold", "temporal cross-validation", "leave-one-voyage",
    "leave-one-ship", "leave one vessel",
]
RANDOM = [
    "k-fold", "kfold", "k fold", "cross-validation", "cross validation",
    "randomly split", "random split", "randomly divided", "shuffled", "shuffle",
    "80/20", "70/30", "holdout", "hold-out", "train-test split", "train/test split",
    "randomly selected",
]

# R^2 appears many ways in these papers: "R2 = 0.95", "R² of 0.95", "R2 score
# 0.95", "coefficient of determination ... 0.95". Match the label then the first
# nearby 0.xx value. Constrain to 0-1 downstream to reject stray decimals.
R2_PATTERNS = [
    re.compile(r"R\s*[\^]?\s*[²2]\s*[=:]\s*([01]?\.\d{2,5})", re.I),
    re.compile(r"R\s*[\^]?\s*[²2]\s+(?:score|value|of|was|is|reached|reaching)\s*(?:of\s*)?([01]?\.\d{2,5})", re.I),
    re.compile(r"\bR\s*-?\s*squared\b[^0-9]{0,25}([01]?\.\d{2,5})", re.I),
    re.compile(r"coefficient of determination[^0-9]{0,30}([01]?\.\d{2,5})", re.I),
]


def classify(text):
    t = text.lower()
    if any(k in t for k in TEMPORAL):
        return "temporal_holdout"
    if any(k in t for k in BLOCKED):
        return "blocked_cv"
    if any(k in t for k in RANDOM):
        return "random_kfold"
    return "unclear"


def headline_r2(text, extracted):
    vals = []
    # from structured extraction
    for m in extracted or []:
        if m.get("metric") == "R2":
            try:
                v = float(m["value"])
                if 0 <= v <= 1:
                    vals.append(v)
            except (ValueError, TypeError):
                pass
    # from text (catches papers the extractor missed)
    for rx in R2_PATTERNS:
        for mm in rx.finditer(text):
            v = float(mm.group(1))
            if 0 <= v <= 1:
                vals.append(v)
    return max(vals) if vals else None


def main():
    corpus = list(csv.DictReader(open(CORPUS, encoding="utf-8")))
    metrics = {}
    for f in EXTR:
        if f.exists():
            for p in json.load(open(f, encoding="utf-8"))["papers"]:
                metrics[p["dedup_id"]] = p.get("metrics", [])

    rows = []
    for r in corpus:
        did = r["dedup_id"]
        tf = TEXTS / f"{did}.txt"
        if not tf.exists():
            rows.append({"dedup_id": did, "year": r.get("year", ""),
                         "protocol": "no_text", "r2": ""})
            continue
        text = tf.read_text(encoding="utf-8", errors="ignore")
        proto = classify(text)
        r2 = headline_r2(text, metrics.get(did))
        rows.append({"dedup_id": did, "year": r.get("year", ""),
                     "protocol": proto, "r2": "" if r2 is None else round(r2, 4)})

    with open(OUT / "protocol_classification.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dedup_id", "year", "protocol", "r2"])
        w.writeheader()
        w.writerows(rows)

    # ── Aggregate ──
    order = ["random_kfold", "blocked_cv", "temporal_holdout", "unclear", "no_text"]
    label = {"random_kfold": "Random k-fold / shuffled",
             "blocked_cv": "Blocked / time-series CV",
             "temporal_holdout": "Temporal holdout",
             "unclear": "Protocol not stated",
             "no_text": "(full text unavailable)"}
    print(f"  Corpus classified: {len(rows)} papers\n")
    print(f"  {'Protocol':30s} {'N':>4s} {'w/ R²':>6s} {'median R²':>10s} {'IQR':>16s}")
    print("  " + "-" * 68)
    summary = {}
    for proto in order:
        grp = [x for x in rows if x["protocol"] == proto]
        r2s = sorted(float(x["r2"]) for x in grp if x["r2"] != "")
        n, nr = len(grp), len(r2s)
        if r2s:
            med = statistics.median(r2s)
            q1 = statistics.median(r2s[:len(r2s)//2]) if len(r2s) > 3 else min(r2s)
            q3 = statistics.median(r2s[(len(r2s)+1)//2:]) if len(r2s) > 3 else max(r2s)
            print(f"  {label[proto]:30s} {n:>4d} {nr:>6d} {med:>10.3f}   [{q1:.2f}, {q3:.2f}]")
            summary[proto] = {"n": n, "n_r2": nr, "median_r2": round(med, 3),
                              "q1": round(q1, 3), "q3": round(q3, 3)}
        else:
            print(f"  {label[proto]:30s} {n:>4d} {nr:>6d} {'—':>10s}")
            summary[proto] = {"n": n, "n_r2": nr, "median_r2": None}
    json.dump(summary, open(OUT / "protocol_summary.json", "w"), indent=1)
    print(f"\n  → protocol_classification.csv, protocol_summary.json")


if __name__ == "__main__":
    main()
