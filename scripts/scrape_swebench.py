#!/usr/bin/env python3
"""Scrape SWE-bench leaderboard and update benchmarks.
Run standalone: python scripts/scrape_swebench.py
Called by update.py daily."""
import json, re, sys, time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    import urllib.request as urllib2
    _requests_available = False
else:
    _requests_available = True

DATA_FILE = Path(__file__).parent.parent / "data" / "models.json"
USER_AGENT = "coding-model-value-leaderboard/1.0"


def log(msg, level="INFO"):
    print(f"[{datetime.now():%H:%M:%S}] {level}: {msg}", flush=True)


def norm(s):
    s = s.lower()
    s = re.sub(r'https?://[^/\s]+/', '', s)
    s = re.sub(r'^[a-z]+[-.]?[a-z]*/', '', s)
    s = re.sub(r'\([^)]*\)', ' ', s)
    s = re.sub(r'\d{4}[-/]\d{2}[-/]\d{2}', ' ', s)
    s = s.replace('-', ' ').replace('_', ' ').replace('.', ' ').replace('/', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def overlap(a, b):
    ta = set(norm(a).split())
    tb = set(norm(b).split())
    if not ta or not tb:
        return 0
    return len(ta & tb) / len(ta | tb)


def run():
    log("Scraping SWE-bench leaderboard...")
    try:
        if _requests_available:
            r = requests.get("https://www.swebench.com/", headers={"User-Agent": USER_AGENT}, timeout=15)
            html = r.text
        else:
            req = urllib2.Request("https://www.swebench.com/", headers={"User-Agent": USER_AGENT})
            html = urllib2.urlopen(req, timeout=15).read().decode("utf-8")
    except Exception as e:
        log(f"Failed: {e}", "WARN")
        return 0

    m = re.search(r'<script type="application/json" id="leaderboard-data">(.*?)</script>', html, re.DOTALL)
    if not m:
        log("Leaderboard data not found", "WARN")
        return 0

    raw = re.sub(r': NaN', ': 0', m.group(1).strip())
    data = json.loads(raw)

    swe_scores = {}
    for section in data:
        for entry in section.get("results", []):
            tags = entry.get("tags", [])
            model_tags = [t for t in tags if t.startswith("Model:")]
            if model_tags:
                mn = model_tags[0].replace("Model: ", "")
                r = entry.get("resolved", 0) or 0
                if mn not in swe_scores or r > swe_scores[mn]:
                    swe_scores[mn] = r

    log(f"Found {len(swe_scores)} models on SWE-bench")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        models_data = json.load(f)

    local_index = {}
    for model in models_data.get("models", []):
        key = norm(re.sub(r'^[^:]+:\s*', '', model["name"]).strip())
        local_index[key] = model

    matched = 0
    for swe_name, swe_score in swe_scores.items():
        swe_norm = norm(swe_name)
        if swe_norm in local_index:
            b = local_index[swe_norm].setdefault("benchmarks", {})
            if b.get("swe_bench_verified") is None:
                b["swe_bench_verified"] = round(swe_score, 1)
                matched += 1
            continue

        best = None
        best_sim = 0
        for key, model in local_index.items():
            s = overlap(swe_name, key)
            if s > best_sim:
                best_sim = s
                best = model
        if best and best_sim >= 0.25:
            b = best.setdefault("benchmarks", {})
            if b.get("swe_bench_verified") is None:
                b["swe_bench_verified"] = round(swe_score, 1)
                matched += 1

    log(f"Matched {matched} models")

    models_data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    for m in models_data.get("models", []):
        try:
            out = m.get("pricing", {}).get("output_per_1m")
            ver = m.get("benchmarks", {}).get("swe_bench_verified")
            if out and ver:
                m["cost_per_pro_point"] = round(out / ver, 3)
        except Exception:
            pass

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(models_data, f, indent=2, ensure_ascii=False)

    with_bench = sum(1 for m in models_data["models"] if m.get("benchmarks", {}).get("swe_bench_verified"))
    log(f"Models with benchmarks: {with_bench}/{len(models_data['models'])}")
    return matched


if __name__ == "__main__":
    sys.exit(run())
