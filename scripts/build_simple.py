#!/usr/bin/env python3
"""
build_simple.py — Build data/simple.json for the simplified leaderboard.

Merges three sources into one small file:
  1. LiveBench official table + categories  -> agentic_coding, coding
  2. BenchLM.ai MMMU-Pro                    -> vision_score
  3. Prices                                 -> models.json when matched,
                                               else LiveBench cost CSV

Scores:
  coder_score    = mean(agentic_coding, coding); every row has both
  frontend_score = mean of the available tracked scores, vision included
Agentic Coding below AGENTIC_FLOOR counts at AGENTIC_DISCOUNT inside both
scores; the raw number still ships as agentic_coding. Value is scaled by the
same discount again below the floor, so a task-failing model cannot win on
price alone.
Value = coder_score per $/1M output (consistent basis across all rows).

Usage:
    python scripts/build_simple.py                 # write data/simple.json
    python scripts/build_simple.py --check-only    # preview, no write
    python scripts/build_simple.py --release 2026-06-25
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from live_benchmarks import (
    _norm,
    _strip_provider,
    fetch_benchlm_aa_mmmu_pro,
    fetch_benchlm_mmmu_pro,
    fetch_llm_stats_mmmu_pro,
)
import livebench_official as lbo

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "models.json"
SIMPLE_FILE = ROOT / "data" / "simple.json"
SIMPLE_JS_FILE = ROOT / "data" / "simple.js"

FUZZY_MIN_RATIO = 0.85
FUZZY_MIN_LEN = 8

# Agentic Coding below this floor counts at a discount in Coder and
# Frontend: those runs fail often enough that the raw score overstates
# the model. The Agentic column always shows the raw LiveBench number.
AGENTIC_FLOOR = 42.0
AGENTIC_DISCOUNT = 0.6


def log(msg):
    print(f"[INFO] {msg}")


def _price_index(local_models):
    """core/normalised name -> (price, model name); first occurrence wins."""
    index = {}
    for m in local_models:
        price = (m.get("pricing") or {}).get("output_per_1m")
        if price is None:
            continue
        name = m.get("name") or ""
        for key in (_norm(name), _norm(_strip_provider(name)), lbo.core_name(name)):
            if key and key not in index:
                index[key] = (price, name)
    return index


def _collapse_max(scores):
    """Collapse reasoning-config variants of one model to its best score."""
    best = {}
    for name, score in scores.items():
        key = lbo.core_name(name)
        if not key:
            continue
        if key not in best or score > best[key][1]:
            best[key] = (name, score)
    return list(best.values())


def _vision_index(aa_scores, standard_scores, standard_extra=None):
    """core/normalised name -> (score, source).

    Priority: Artificial Analysis (independent run, configs collapsed to the
    best) > published BenchLM.ai > published llm-stats.com.
    """
    index = {}
    for name, score in _collapse_max(aa_scores or {}):
        for key in (_norm(name), lbo.core_name(name)):
            if key and key not in index:
                index[key] = (score, "aa")
    for source, scores in (("benchlm", standard_scores),
                           ("llm-stats", standard_extra or {})):
        for name, score in scores.items():
            for key in (_norm(name), lbo.core_name(name)):
                if key and key not in index:
                    index[key] = (score, source)
    return index


def _line_key(raw):
    """Family line a model belongs to: core name with version digits removed."""
    return re.sub(r"\d", "", lbo.core_name(raw))


def _version(base):
    """First version-like number in a display name (5.5, 6, 3.8)."""
    m = re.search(r"\d+(?:\.\d+)?", base)
    return float(m.group(0)) if m else None


def _vision_estimate(row, priors):
    """Lower bound from the newest scored model in the same family line.

    Only priors with a parseable version are used, and only when the target
    is a new or same version. Versionless pairs stay unmatched on purpose.
    """
    line = _line_key(row["raw"])
    version = _version(row["name"])
    if version is None:
        return None
    best = None
    for prior in priors:
        if prior["line"] != line:
            continue
        prior_version = prior["version"]
        if prior_version is None or prior_version > version:
            continue
        candidate = (prior_version, prior["vision_score"], prior["name"])
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    return {"value": best[1], "from": best[2]}


def _lookup(raw, index):
    """Match an eval config name against an index of known names."""
    keys = [lbo.core_name(raw), _norm(raw)]
    for key in keys:
        if key in index:
            return index[key]
    for key in keys:
        if len(key) < FUZZY_MIN_LEN:
            continue
        for idx_key, val in index.items():
            if len(idx_key) < FUZZY_MIN_LEN:
                continue
            shorter, longer = sorted((len(key), len(idx_key)))
            if shorter / longer > FUZZY_MIN_RATIO and (key in idx_key or idx_key in key):
                return val
    return None


def _effective_agentic(agentic):
    """Agentic score as it counts inside Coder and Frontend."""
    if agentic is None or agentic >= AGENTIC_FLOOR:
        return agentic
    return round(agentic * AGENTIC_DISCOUNT, 1)


def _value_factor(agentic):
    """Risk weight for Value: below the floor the ratio is scaled again."""
    if agentic is None or agentic >= AGENTIC_FLOOR:
        return 1.0
    return AGENTIC_DISCOUNT


def build_models(table_rows, categories, cost_rows, vision_scores, local_models,
                 vision_extra=None, vision_aa=None):
    """Pure merge step (fixture-testable). Returns rows sorted by frontend score."""
    price_index = _price_index(local_models)
    vision_index = _vision_index(vision_aa, vision_scores, vision_extra)
    cost_by_name = {r.get("model"): r for r in cost_rows if r.get("model")}

    out = []
    for row in table_rows:
        raw = row.get("model")
        if not raw:
            continue
        means = lbo.category_means(row, categories)
        agentic = means.get("Agentic Coding")
        coding = means.get("Coding")
        if agentic is None and coding is None:
            continue

        vision_match = _lookup(raw, vision_index)
        vision = vision_match[0] if vision_match else None
        vision_source = vision_match[1] if vision_match else None
        price_match = _lookup(raw, price_index)
        if price_match is not None:
            price, price_source = price_match[0], f"models.json ({price_match[1]})"
        else:
            cost_row = cost_by_name.get(raw, {})
            price = lbo._num(cost_row.get("output_price_per_million"))
            price_source = "livebench" if price is not None else None

        scores = [s for s in (agentic, coding, vision) if s is not None]
        effective_agentic = _effective_agentic(agentic)
        coder_score = None
        frontend_score = None
        if agentic is not None and coding is not None:
            frontend_parts = [effective_agentic, coding]
            if vision is not None:
                frontend_parts.append(vision)
            coder_score = round((effective_agentic + coding) / 2, 1)
            frontend_score = round(sum(frontend_parts) / len(frontend_parts), 1)
        value = None
        if coder_score is not None and price:
            value = round(coder_score / price * _value_factor(agentic), 2)

        base, variant = lbo.name_parts(raw)
        out.append({
            "name": base,
            "variant": variant or None,
            "raw": raw,
            "provider": lbo.infer_provider(raw),
            "agentic_coding": agentic,
            "agentic_effective": effective_agentic if effective_agentic != agentic else None,
            "coding": coding,
            "vision_score": vision,
            "vision_source": vision_source,
            "vision_est": None,
            "coverage": len(scores),
            "output_price_per_1m": price,
            "price_source": price_source,
            "coder_score": coder_score,
            "frontend_score": frontend_score,
            "value": value,
        })

    actuals = [m for m in out if m["vision_score"] is not None]
    priors = [{
        "name": m["name"],
        "vision_score": m["vision_score"],
        "line": _line_key(m["raw"]),
        "version": _version(m["name"]),
    } for m in actuals]
    merged_sources = {**(vision_extra or {}), **vision_scores, **(vision_aa or {})}
    for source_name, score in merged_sources.items():
        priors.append({
            "name": source_name,
            "vision_score": score,
            "line": _line_key(source_name),
            "version": _version(source_name),
        })

    for m in out:
        if m["vision_score"] is None:
            m["vision_est"] = _vision_estimate(m, priors)

    out.sort(key=lambda m: (m["frontend_score"] is None, -(m["frontend_score"] or 0)))
    for i, m in enumerate(out, 1):
        m["rank"] = i
    return out


def main():
    parser = argparse.ArgumentParser(description="Build data/simple.json")
    parser.add_argument("--release", help="LiveBench release date (YYYY-MM-DD)")
    parser.add_argument("--check-only", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    release = lbo.resolve_release(args.release, log_fn=log)
    log(f"LiveBench release: {release}")

    table = lbo.fetch_table(release)
    categories = lbo.fetch_categories(release)
    cost = lbo.fetch_cost(release)
    if not table or not categories:
        log("Failed to fetch LiveBench table/categories — aborting")
        return 1
    log(f"LiveBench rows: {len(table)} | cost rows: {len(cost)}")

    aa_vision = fetch_benchlm_aa_mmmu_pro()
    benchlm_vision = fetch_benchlm_mmmu_pro()
    llmstats_vision = fetch_llm_stats_mmmu_pro()
    log(f"Vision scores: AA {len(aa_vision)} | BenchLM {len(benchlm_vision)} "
        f"| llm-stats {len(llmstats_vision)}")

    local = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("models", [])
    models = build_models(table, categories, cost, benchlm_vision, local,
                          vision_extra=llmstats_vision, vision_aa=aa_vision)

    matched_vision = sum(1 for m in models if m["vision_score"] is not None)
    aa_used = sum(1 for m in models if m["vision_source"] == "aa")
    benchlm_used = sum(1 for m in models if m["vision_source"] == "benchlm")
    llmstats_used = sum(1 for m in models if m["vision_source"] == "llm-stats")
    estimated = sum(1 for m in models if m["vision_est"] is not None)
    local_prices = sum(1 for m in models if (m["price_source"] or "").startswith("models.json"))
    log(f"Built {len(models)} rows | vision actual {matched_vision} "
        f"(aa {aa_used}, benchlm {benchlm_used}, llm-stats {llmstats_used}) "
        f"| estimates {estimated} | models.json prices {local_prices}")

    for m in models[:5]:
        log("  #%d %s | coder %s frontend %s (ag %s, cod %s, vis %s) | $%s/1M | value %s" % (
            m["rank"], m["name"], m["coder_score"], m["frontend_score"],
            m["agentic_coding"], m["coding"], m["vision_score"],
            m["output_price_per_1m"], m["value"]))

    if args.check_only:
        log("Check-only: not writing data/simple.json")
        return 0

    payload = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "livebench_release": release,
        "sources": {
            "livebench": "https://livebench.ai — table/categories/cost CSVs",
            "vision": "MMMU-Pro by Artificial Analysis (via BenchLM.ai mirror); "
                      "published BenchLM.ai / llm-stats.com scores fill gaps",
            "vision_estimates": "lower bound from the newest scored model in the same line",
            "prices": "data/models.json where matched, else LiveBench cost CSV",
        },
        "scoring": {
            "coder": "mean(agentic_coding, coding)",
            "frontend": "mean(agentic_coding, coding, vision_score) with vision optional",
            "agentic_floor": AGENTIC_FLOOR,
            "agentic_discount": AGENTIC_DISCOUNT,
            "value": "coder per $/1M output price, scaled again by agentic_discount below the floor",
        },
        "models": models,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    SIMPLE_FILE.write_text(text, encoding="utf-8")
    log(f"Wrote {SIMPLE_FILE}")

    js_text = "window.__SCORECARD_DATA__ = " + text.replace("</", "<\\/") + ";\n"
    SIMPLE_JS_FILE.write_text(js_text, encoding="utf-8")
    log(f"Wrote {SIMPLE_JS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
