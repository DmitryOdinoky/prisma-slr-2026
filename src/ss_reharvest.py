#!/usr/bin/env python3
"""
Harvest Semantic Scholar, tolerating a dead API key and a saturated public tier.

Semantic Scholar is not optional for this review: it was the sole source for 28
of the original 196 papers. But the supplied key returns 403 (approved, not yet
provisioned) and the keyless public tier is globally rate-limited, so a naive
run silently under-samples it.

This harvester therefore:
  * re-reads .env.local before every sub-query, so a newly-issued key is picked
    up mid-run without restarting — the moment it goes live, the harvest
    switches to the authenticated tier and finishes in seconds;
  * writes results incrementally, so a crash or kill never loses completed work;
  * resumes: sub-queries already present in the output file are skipped;
  * backs off exponentially, and reports exactly which sub-queries never landed,
    exiting non-zero so an incomplete harvest cannot pass silently.

Run:  PRISMA_YEAR_MIN=2026 PRISMA_YEAR_MAX=2026 \
      python3 -u src/ss_reharvest.py --out workspace/outputs/window_2026
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prisma_pipeline import SS_QUERIES, YEAR_MIN, YEAR_MAX

BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env.local"

KEYED_DELAY = 1.3      # their stated limit is 1 req/sec, cumulative
PUBLIC_DELAY = 20      # public tier: be a good citizen, it is shared
MAX_RETRIES = 8
MAX_BACKOFF = 180

# Semantic Scholar's limit is 1 request/second CUMULATIVE ACROSS ALL ENDPOINTS.
# Every request must go through this gate — including the key probe. Sleeping
# only after the fetch (as an earlier version did) still let the probe and the
# fetch fire back-to-back, breaching the limit on every sub-query.
_last_request = [0.0]


def throttle(delay):
    elapsed = time.monotonic() - _last_request[0]
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_request[0] = time.monotonic()

FIELDS = ["record_id", "title", "authors", "year", "venue", "doi", "url",
          "abstract", "source_database", "string_id"]


def current_key():
    """Re-read the key from .env.local each time, so a new key can be dropped in
    while this is running. Keys may be prefixed and hyphenated (e.g. s2k-...), so
    do not restrict the charset to alphanumerics — that would silently truncate
    the key at the hyphen and authenticate with a fragment."""
    if ENV_FILE.exists():
        m = re.search(r'SS_API_KEY=["\']?([A-Za-z0-9_\-]+)', ENV_FILE.read_text())
        if m:
            return m.group(1)
    return os.environ.get("SS_API_KEY", "")


def key_status(key):
    """Return 'live' | 'throttled' | 'dead' | 'none'.

    A 429 does NOT mean the key is bad — it means we are being rate-limited, and
    falling back to the keyless tier in that case would be strictly worse (the
    public pool is shared and even more congested). Only a 403 means the key is
    actually rejected.
    """
    if not key:
        return "none"
    try:
        throttle(KEYED_DELAY)
        r = requests.get(BASE, params={"query": "ship", "limit": 1, "fields": "title"},
                         headers={"x-api-key": key}, timeout=20)
        if r.status_code == 200:
            return "live"
        if r.status_code == 429:
            return "throttled"
        if r.status_code == 403:
            return "dead"
        return "throttled"
    except requests.RequestException:
        return "throttled"


def fetch(sq, headers):
    params = {"query": sq, "fields": "title,authors,year,venue,externalIds,abstract",
              "limit": 100, "publicationDateOrYear": f"{YEAR_MIN}:{YEAR_MAX}"}
    delay = KEYED_DELAY if headers else PUBLIC_DELAY
    for attempt in range(MAX_RETRIES):
        try:
            throttle(delay)
            r = requests.get(BASE, params=params, headers=headers, timeout=60)
            if r.status_code == 429:
                wait = min(MAX_BACKOFF, 15 * (2 ** attempt))
                print(f"      429 — backoff {wait}s ({attempt+1}/{MAX_RETRIES})", flush=True)
                time.sleep(wait)
                continue
            if r.status_code == 403:
                return "FORBIDDEN"
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = min(MAX_BACKOFF, 15 * (2 ** attempt))
            print(f"      {type(e).__name__} — retry in {wait}s ({attempt+1}/{MAX_RETRIES})", flush=True)
            time.sleep(wait)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_csv = out_dir / "ss_records.csv"
    state_f = out_dir / "ss_harvest_state.json"

    subs = [(sid, sq) for sid in ["A", "B", "C", "D"] for sq in SS_QUERIES[sid]]

    # Resume from whatever a previous run completed.
    done = set()
    rows = []
    if state_f.exists():
        done = set(json.loads(state_f.read_text()).get("done", []))
    if out_csv.exists():
        rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    seen = {(r["title"] or "").strip().lower() for r in rows}
    if done:
        print(f"  resuming: {len(done)}/{len(subs)} sub-queries already done, "
              f"{len(rows)} records held\n")

    # Probe the key ONCE. Probing before every sub-query costs an extra request
    # each time, and at a 1 req/sec cumulative limit that probe+fetch pair is
    # itself what triggers the throttling.
    key = current_key()
    st = key_status(key)
    keyed = st in ("live", "throttled")
    headers = {"x-api-key": key} if keyed else {}
    print(f"  key status: {st} → using {'authenticated' if keyed else 'public'} tier\n")

    for i, (sid, sq) in enumerate(subs, 1):
        if sq in done:
            print(f"  [{i}/{len(subs)}] {sid}: already done — skipping")
            continue

        print(f"  [{i}/{len(subs)}] {sid}: {sq[:50]}...", flush=True)

        data = fetch(sq, headers)
        if data == "FORBIDDEN":
            print("      403 — key rejected; falling back to public tier", flush=True)
            data = fetch(sq, {})
        if data is None:
            print("      FAILED — will need a re-run", flush=True)
            continue

        got = 0
        for p in data.get("data", []):
            tk = (p.get("title") or "").strip().lower()
            if not tk or tk in seen:
                continue
            seen.add(tk)
            ext = p.get("externalIds") or {}
            rows.append({
                "record_id": f"SS-{len(rows)+1:04d}",
                "title": p.get("title", ""),
                "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])),
                "year": p.get("year", "") or "",
                "venue": p.get("venue", "") or "",
                "doi": ext.get("DOI", "") or "",
                "url": f"https://www.semanticscholar.org/paper/{p.get('paperId','')}",
                "abstract": p.get("abstract", "") or "",
                "source_database": "Semantic Scholar",
                "string_id": sid,
            })
            got += 1

        done.add(sq)
        # Persist after every sub-query — never lose completed work.
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        state_f.write_text(json.dumps({"done": sorted(done)}, indent=1))
        print(f"      +{got} new (total {len(rows)}) — saved", flush=True)


    missing = [sq for _, sq in subs if sq not in done]
    print(f"\n{'='*58}")
    print(f"  Semantic Scholar: {len(rows)} records, "
          f"{len(subs)-len(missing)}/{len(subs)} sub-queries complete")
    print(f"  → {out_csv}")
    if missing:
        print(f"\n  INCOMPLETE — {len(missing)} sub-queries never landed:")
        for sq in missing:
            print(f"    - {sq[:62]}")
        print("\n  Recall is NOT comparable to the original review. Re-run this")
        print("  script (it resumes) once a working API key is in .env.local.")
        sys.exit(1)
    print("  Complete.")


if __name__ == "__main__":
    main()
