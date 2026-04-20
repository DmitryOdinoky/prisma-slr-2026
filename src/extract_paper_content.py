#!/usr/bin/env python3
"""
Extract structured content from each corpus PDF.

Heuristic extraction: per-paper metadata + mined fields.
Thematic narrative synthesis is performed manually by the reviewer.

Per-paper fields extracted:
  meta     : title (from /Title or first line), authors, year, doi, journal, pages
  text     : full text (cached; used by synthesis step)
  methods  : list of ML method keywords detected
  metrics  : list of metric values (R², RMSE, MAE, MAPE) with numeric parse
  data     : dataset hints (AIS, noon report, sensor, ship type, voyage duration)
  cluster  : T1 / T2 / T3 / T4 / T6 / other (keyword rules)

Output: workspace/outputs/paper_extractions.json
        workspace/outputs/paper_texts/{dedup_id}.txt  (plain text cache)
"""
import csv
import json
import re
import sys
from pathlib import Path
from collections import Counter

from pdfminer.high_level import extract_text
from PyPDF2 import PdfReader

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORKSPACE = REPO_ROOT / "workspace"
OUTPUTS = WORKSPACE / "outputs"
TEXTS_DIR = OUTPUTS / "paper_texts"
TEXTS_DIR.mkdir(parents=True, exist_ok=True)

IN_CORPUS = OUTPUTS / "final_corpus.csv"
OUT_JSON = OUTPUTS / "paper_extractions.json"

# ── Keyword taxonomies ───────────────────────────────────────────────────────

ML_METHODS = {
    "linear regression": ["linear regression", "ordinary least squares", "ols "],
    "random forest": ["random forest", "random forests"],
    "xgboost": ["xgboost", "extreme gradient boosting", "xg-boost"],
    "lightgbm": ["lightgbm", "light gbm", "light-gbm"],
    "catboost": ["catboost", "cat-boost"],
    "gradient boosting": ["gradient boosting", "gbm ", "gbrt"],
    "svm": ["support vector", "svm ", "svr "],
    "knn": ["k-nearest", "knn ", "k nearest"],
    "decision tree": ["decision tree"],
    "mlp/ann": ["multilayer perceptron", "feedforward neural", "ann ", "fully connected",
                "artificial neural network"],
    "cnn": [" cnn ", "convolutional neural"],
    "lstm": ["lstm", "long short-term memory"],
    "gru": ["gru ", "gated recurrent"],
    "transformer": ["transformer", "self-attention", "attention mechanism"],
    "autoencoder": ["autoencoder"],
    "gaussian process": ["gaussian process", " gp regress"],
    "bayesian network": ["bayesian network"],
    "physics-informed NN": ["physics-informed neural", "pinn ", "physics informed neural"],
    "grey-box": ["grey-box", "grey box", "gray-box", "gray box"],
    "digital twin": ["digital twin"],
    "ensemble": ["ensemble learning", "ensemble model", "stacking", "bagging"],
    "reinforcement learning": ["reinforcement learning", " rl agent"],
    "online learning": ["online learning", "incremental learning"],
    "transfer learning": ["transfer learning"],
    "feature selection": ["feature selection", "feature importance"],
    "shap/xai": ["shap ", "shapley", "lime explanation", " xai", "explainable ai",
                 "explainable artificial"],
}

SHIP_TYPES = ["bulk carrier", "container ship", "tanker", "tugboat", "cruise", "ferry",
              "ro-ro", "lng carrier", "naval", "fishing vessel", "yacht", "cargo ship",
              "passenger ship", "research vessel", "icebreaker"]

DATA_SOURCES = {
    "ais": ["ais data", "automatic identification system"],
    "noon report": ["noon report", "noon-report"],
    "sensor/iot": ["sensor data", "iot ", "in-service sensor", "onboard sensor",
                   "high-frequency sensor", "telemetr"],
    "voyage data recorder": ["voyage data recorder", "vdr "],
    "cfd simulation": ["cfd simulat", "computational fluid dynamics"],
    "model basin": ["towing tank", "model basin", "sea trial"],
    "noon + weather": ["metocean", "weather forecast", "wave height", "wind data"],
}

TARGETS = {
    "fuel consumption": ["fuel consumption", "foc ", "sfoc", "specific fuel"],
    "shaft power": ["shaft power", "brake power", "propulsion power"],
    "speed": ["ship speed prediction", "vessel speed", "speed-through-water"],
    "speed loss": ["speed loss", "speed degradation"],
    "emissions": [" co2", "co₂", "ghg emission", "emission intensity"],
    "efficiency": ["energy efficiency", "eedi", "cii ", "eexi"],
}

# Cluster rules (priority top-to-bottom)
CLUSTER_RULES = [
    ("T2", ["physics-informed", "physics informed", "grey-box", "gray-box",
            "semi-empirical", "holtrop", "physics-based model", "physics-guided"]),
    ("T3", ["feature engineering", "feature selection", "feature importance",
            "dimension reduction", "pca ", "data preprocessing", "feature construct"]),
    ("T4", ["online learning", "incremental learning", "adaptive model",
            "bias correction", "concept drift", "model drift",
            "real-time calibration", "sliding window"]),
    ("T6", ["shap ", "shapley", "lime ", "xai ", "explainable ai",
            "interpretable ml", "interpretability"]),
    ("T1", ["machine learning", "neural network", "regression", "random forest",
            "xgboost", "deep learning", "ensemble", "prediction model"]),
]


def extract_meta(pdf_path):
    try:
        r = PdfReader(str(pdf_path), strict=False)
        n_pages = len(r.pages)
        meta_title = (r.metadata.title or "") if r.metadata else ""
    except Exception:
        n_pages = 0; meta_title = ""
    return n_pages, meta_title.strip()


def find_doi(text):
    m = re.search(r"10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+", text)
    return m.group(0).rstrip(".,") if m else ""


def find_year(text):
    for m in re.finditer(r"\b(19[9]\d|20[0-2]\d)\b", text[:3000]):
        yr = int(m.group(0))
        if 1990 <= yr <= 2026:
            return yr
    return None


def mine_methods(text_lower):
    found = set()
    for label, keywords in ML_METHODS.items():
        for kw in keywords:
            if kw in text_lower:
                found.add(label); break
    return sorted(found)


def mine_metrics(text):
    """Extract numeric metrics: R², RMSE, MAE, MAPE."""
    out = []
    # R² values: look for 'R^2', 'R2', 'R²' followed by = or is and a number
    for pat, name in [
        (r"R\s*\^?\s*2\s*[=:]\s*(0\.\d+|[01]\.0+)", "R2"),
        (r"R²\s*[=:]\s*(0\.\d+|[01]\.0+)", "R2"),
        (r"coefficient of determination[^.]{0,80}?(0\.\d+|[01]\.0+)", "R2"),
        (r"\bRMSE\b[^.]{0,40}?[=:]\s*(\d+\.?\d*)", "RMSE"),
        (r"\bMAE\b[^.]{0,40}?[=:]\s*(\d+\.?\d*)", "MAE"),
        (r"\bMAPE\b[^.]{0,40}?[=:]\s*(\d+\.?\d*)", "MAPE"),
    ]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = float(m.group(1))
                out.append({"metric": name, "value": val})
            except Exception:
                pass
    return out[:25]  # cap


def mine_data(text_lower):
    out = {"ship_types": [], "sources": []}
    for st in SHIP_TYPES:
        if st in text_lower:
            out["ship_types"].append(st)
    for src, kws in DATA_SOURCES.items():
        if any(k in text_lower for k in kws):
            out["sources"].append(src)
    return out


def mine_targets(text_lower):
    out = []
    for tgt, kws in TARGETS.items():
        if any(k in text_lower for k in kws):
            out.append(tgt)
    return out


def classify_cluster(text_lower):
    for label, kws in CLUSTER_RULES:
        if any(k in text_lower for k in kws):
            return label
    return "other"


def extract_abstract(text):
    """Find abstract block. Loose heuristic."""
    m = re.search(r"\bAbstract\b\s*[:.\-—]?\s*(.{200,2500}?)(?:\b(?:Keywords|Introduction|1\.\s*Introduction)\b)",
                  text, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:2500]
    # fallback: first 1500 chars after removing headers
    head = text[:3000]
    return re.sub(r"\s+", " ", head).strip()[:2000]


def process_paper(row):
    pdf_path = WORKSPACE / row["pdf_path"]
    if not pdf_path.exists():
        return None
    try:
        text = extract_text(str(pdf_path)) or ""
    except Exception:
        text = ""
    n_pages, meta_title = extract_meta(pdf_path)
    text_l = text.lower()
    dedup_id = row["dedup_id"]
    # Cache text
    (TEXTS_DIR / f"{dedup_id}.txt").write_text(text, encoding="utf-8")

    return {
        "dedup_id": dedup_id,
        "title": row.get("title", ""),
        "authors": row.get("authors", ""),
        "year": row.get("year", "") or find_year(text),
        "doi": row.get("doi", ""),
        "venue": row.get("venue", ""),
        "source_database": row.get("source_database", ""),
        "abstract_screen": row.get("abstract_screen", ""),
        "pdf_path": row["pdf_path"],
        "n_pages": n_pages,
        "text_length": len(text),
        "abstract": extract_abstract(text),
        "cluster": classify_cluster(text_l),
        "methods": mine_methods(text_l),
        "targets": mine_targets(text_l),
        "data": mine_data(text_l),
        "metrics": mine_metrics(text),
    }


def main():
    with open(IN_CORPUS, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Corpus: {len(rows)} papers")

    results = []
    failed = []
    for i, r in enumerate(rows, 1):
        try:
            ext = process_paper(r)
            if ext:
                results.append(ext)
            else:
                failed.append(r["dedup_id"])
        except Exception as e:
            failed.append((r["dedup_id"], str(e)))
        if i % 10 == 0:
            print(f"  {i}/{len(rows)}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"n": len(results), "papers": results}, f, ensure_ascii=False, indent=1)

    # Summary
    print(f"\nExtracted: {len(results)}  Failed: {len(failed)}")
    cluster_dist = Counter(p["cluster"] for p in results)
    print(f"Clusters: {dict(cluster_dist)}")
    target_dist = Counter(t for p in results for t in p["targets"])
    print(f"Targets : {dict(target_dist)}")
    method_dist = Counter(m for p in results for m in p["methods"])
    print(f"Top methods: {dict(method_dist.most_common(12))}")
    print(f"\nWrote: {OUT_JSON}")
    print(f"Texts: {TEXTS_DIR}/")
    if failed:
        print(f"Failed list: {failed[:5]}…")


if __name__ == "__main__":
    main()
