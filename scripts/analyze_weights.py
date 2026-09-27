#!/usr/bin/env python3
"""
Weight research: how do LiveBench Agentic Coding and Coding correlate with
practical coding benchmarks (SWE-bench Verified, AA Coding Index, Aider)?
Run: python scripts/analyze_weights.py
Outputs: reports/weight-analysis.json + console table.
"""
import csv
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))

import build_simple
import livebench_official as lbo

ROOT = Path(__file__).parent.parent
OUT = ROOT / "reports"
OUT.mkdir(exist_ok=True)

RELEASE = "2026-06-25"


def load_livebench_rows():
    rows = lbo.fetch_table(RELEASE)
    categories = lbo.fetch_categories(RELEASE)
    out = []
    for row in rows:
        raw = row.get("model")
        if not raw:
            continue
        means = lbo.category_means(row, categories)
        out.append({
            "raw": raw,
            "core": lbo.core_name(raw),
            "agentic": means.get("Agentic Coding"),
            "coding": means.get("Coding"),
        })
    return out


def match_benchmark(rows, models, field):
    """Match models.json benchmark values onto LiveBench rows."""
    index = {}
    for m in models:
        val = (m.get("benchmarks") or {}).get(field)
        if val is None:
            continue
        name = m.get("name") or ""
        for key in (lbo.core_name(name), build_simple._norm(name),
                    build_simple._norm(build_simple._strip_provider(name))):
            if key and key not in index:
                index[key] = val
    hits = 0
    for r in rows:
        val = build_simple._lookup(r["raw"], index)
        r[field] = val
        if val is not None:
            hits += 1
    return hits


def corr_table(df, x, y):
    d = df[[x, y]].dropna()
    if len(d) < 5:
        return None
    pearson = stats.pearsonr(d[x], d[y])
    spearman = stats.spearmanr(d[x], d[y])
    return {
        "n": len(d), "x": x, "y": y,
        "pearson_r": round(pearson.statistic, 3), "pearson_p": float(f"{pearson.pvalue:.2g}"),
        "spearman_rho": round(spearman.statistic, 3), "spearman_p": float(f"{spearman.pvalue:.2g}"),
    }


def spread(series):
    s = series.dropna()
    return {"n": int(len(s)), "min": round(float(s.min()), 1), "max": round(float(s.max()), 1),
            "iqr": round(float(s.quantile(0.75) - s.quantile(0.25)), 1),
            "sd": round(float(s.std()), 1)}


def main():
    lb = load_livebench_rows()
    models = json.loads((ROOT / "data" / "models.json").read_text(encoding="utf-8"))["models"]

    matches = {}
    for field in ("swe_bench_verified", "aa_coding_index", "aider_polyglot",
                  "terminal_bench_2_1", "swe_bench_pro"):
        matches[field] = match_benchmark(lb, models, field)

    df = pd.DataFrame(lb)
    print(f"LiveBench rows: {len(df)} | matches: {matches}\n")

    results = {"n_livebench_rows": len(df), "matches": matches, "questions": {
        "agentic": 72, "coding": 117}, "correlations": [], "spread": {}}

    print("=== Rank correlations with practical benchmarks ===")
    print(f"{'target':22} {'n':>3}  {'agentic rho':>12} {'coding rho':>11}")
    for field in ("swe_bench_verified", "aa_coding_index", "aider_polyglot",
                  "terminal_bench_2_1", "swe_bench_pro"):
        a = corr_table(df, "agentic", field)
        c = corr_table(df, "coding", field)
        if a and c:
            results["correlations"].append({"target": field, "agentic": a, "coding": c})
            print(f"{field:22} {a['n']:>3}  {a['spearman_rho']:>12} {c['spearman_rho']:>11}")

    print("\n=== Score spread (all LiveBench rows) ===")
    for col in ("agentic", "coding"):
        s = spread(df[col])
        results["spread"][col] = s
        print(f"  {col:8} n={s['n']} min={s['min']} max={s['max']} IQR={s['iqr']} sd={s['sd']}")

    # combined vs practical benchmarks: equal, 50/50, 60/40, 70/30
    print("\n=== Combined score vs SWE-bench Verified / AA Coding Index ===")
    combos = {"50/50": 0.5, "60/40": 0.6, "70/30": 0.7, "80/20": 0.8}
    for label, w_ag in combos.items():
        df[f"combo_{label}"] = df["agentic"].fillna(df["coding"]) * w_ag + \
            df["coding"].fillna(df["agentic"]) * (1 - w_ag)
    row = {}
    for label in combos:
        r1 = corr_table(df, f"combo_{label}", "swe_bench_verified")
        r2 = corr_table(df, f"combo_{label}", "aa_coding_index")
        # average rank-correlation across both targets
        row[label] = round((r1["spearman_rho"] + r2["spearman_rho"]) / 2, 3)
        print(f"  {label}: SWE-v rho={r1['spearman_rho']} (n={r1['n']}) | AA index rho={r2['spearman_rho']} (n={r2['n']}) | avg {row[label]}")
    results["combo_avg_spearman"] = row

    # pairwise overlap check for matched-vision context
    n_both = df[["agentic", "coding"]].dropna().shape[0]
    print(f"\nRows with both categories: {n_both}")

    # sensitivity: correlation on models both benchmarks have in common
    sub = df.dropna(subset=["swe_bench_verified"])
    print(f"SWE-V subsample: n={len(sub)}")
    print(f"  agentic vs coding inter-correlation (Spearman): "
          f"{stats.spearmanr(sub['agentic'], sub['coding']).statistic:.3f}")
    results["inter_correlation_swe_subsample"] = round(
        float(stats.spearmanr(sub["agentic"], sub["coding"]).statistic), 3)

    (OUT / "weight-analysis.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT / 'weight-analysis.json'}")


if __name__ == "__main__":
    main()
