#!/usr/bin/env python3
"""
update.py — Auto-discover coding LLMs and refresh pricing + benchmarks

Data sources (all real, all public):
1. OpenRouter /api/v1/models         — current pricing, context, AA coding index
2. HuggingFace /api/models           — discover new model releases by name
3. HuggingFace model README          — extract SWE-bench scores from model cards
4. LiveBench / AA Index snapshots    — inlined data from whichllm project

Usage:
    python update.py                   # Full refresh
    python update.py --discover        # Only find new models, don't update existing
    python update.py --model deepseek  # Refresh one model
    python update.py --check-only      # Show changes without writing
    python update.py --dry-run         # Don't write to disk

Design principles:
- Resilient: failures on one source don't block others
- Conservative: only update fields with high confidence (regex match on official text)
- Auditable: prints every change it would make
- Discoverable: finds new models instead of waiting for manual updates

The script is conservative on purpose. If you're not sure about a field, leave it
alone. The leaderboard is more useful with accurate data than complete data.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Missing dependencies. Run: pip install requests")
    sys.exit(1)

# Snapshot-based benchmark sources from whichllm project
from benchmark_snapshots import match_livebench, match_aa_index

# Live scrapers for additional benchmark sources
from live_benchmarks import (
    fetch_benchlm_swe_bench,
    fetch_tbench_scores,
    fetch_whatllm_scores,
    match_live_scores,
    match_whatllm_multi,
)

# ---------- Config ----------
DATA_FILE = Path(__file__).parent.parent / "data" / "models.json"
USER_AGENT = "coding-model-value-leaderboard/1.0 (+https://github.com/EthanHarwood97/coding-model-value-leaderboard)"
REQUEST_TIMEOUT = 30

# Known coding-focused model name patterns (for discovery on HuggingFace)
CODING_MODEL_PATTERNS = [
    "deepseek-v4", "deepseek-coder", "deepseek-v3",
    "qwen3-coder", "qwen3.7", "qwen3.6", "qwen3.5",
    "kimi-k2", "kimi-k2.7", "kimi-k2.6",
    "glm-5", "glm-4.5", "glm-4.6", "glm-4.7",
    "minimax-m3", "minimax-m2",
    "mimo-v2", "mimo-v2.5",
    "codestral",
    "claude-opus-4", "claude-sonnet-4", "claude-haiku-4",
    "gpt-5", "gpt-5.5", "gpt-5.4", "gpt-5.3",
    "gemini-3.1", "gemini-3.5", "gemini-3-pro",
    "qwen-coder",
    "deepseek-r1",
]


# ---------- Logging ----------
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {level}: {msg}", flush=True)


def fetch_json(url: str, params: Optional[dict] = None) -> Optional[dict]:
    """Fetch JSON from URL with retries."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                log(f"Failed to fetch {url}: {e}", "WARN")
    return None


def fetch_text(url: str) -> Optional[str]:
    """Fetch text content from URL."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                log(f"Failed to fetch {url}: {e}", "WARN")
    return None


# ---------- Source 1: OpenRouter ----------
def fetch_openrouter_models() -> list:
    """Fetch all current models from OpenRouter (real-time, has pricing + benchmarks)."""
    log("Fetching OpenRouter /api/v1/models ...")
    data = fetch_json("https://openrouter.ai/api/v1/models")
    if not data or "data" not in data:
        return []
    return data["data"]


def openrouter_to_model(or_model: dict) -> Optional[dict]:
    """Convert OpenRouter model to our schema. Returns None if not coding-relevant."""
    model_id = or_model.get("id", "")
    name = or_model.get("name", "")
    name_lower = name.lower()
    id_lower = model_id.lower()

    # Skip non-coding (image, audio routers, very old models)
    skip_patterns = [
        "router", "auto", "dall-e", "whisper", "tts",
        "embedding", "moderation", "guard",
        "-image", "image-", "vl-", "-vl",
        "nano-banana",  # image gen
        "sonar",  # perplexity search
        "haiku-latest", "sonnet-latest", "opus-latest", "gpt-latest", "gemini-latest", "kimi-latest",
        "mistral-small", "mistral-medium", "phi-",
        # Skip dated snapshots of same model (we keep the canonical one)
        "2026-", "2025-", "-preview-", "-exp-",
    ]
    if any(p in id_lower for p in skip_patterns):
        return None

    # Skip R1 distills (we track the base R1)
    if "r1-distill" in id_lower:
        return None

    # Keep only coding-relevant models (positive signal: has code/coder in name OR is a frontier LLM)
    coding_signals = [
        "coder", "code", "deepseek", "qwen", "kimi", "glm",
        "minimax", "mimo", "claude-opus", "claude-sonnet",
        "gpt-5", "gpt-4", "gemini-3", "o3", "o4",
        "nemotron", "mistral-large", "command",
        "ring-", "ling-", "haiku-4", "hy3", "laguna",
        "kat-coder",
    ]
    if not any(s in id_lower for s in coding_signals):
        return None

    # Skip very old models (created before 2025)
    created = or_model.get("created", 0)
    if created < 1735689600:  # 2025-01-01
        return None

    # Pricing is per-token in OpenRouter, convert to per-1M
    pricing_raw = or_model.get("pricing", {})
    prompt_per_token = float(pricing_raw.get("prompt", 0) or 0)
    completion_per_token = float(pricing_raw.get("completion", 0) or 0)
    cache_read = float(pricing_raw.get("input_cache_read", 0) or 0) * 1_000_000

    if prompt_per_token <= 0 or completion_per_token <= 0:
        return None

    provider = model_id.split("/")[0].replace("-", " ").title() if "/" in model_id else "Unknown"

    # Benchmarks from artificial_analysis (when present)
    aa_benchmarks = or_model.get("benchmarks", {}).get("artificial_analysis", "")
    aa_coding_index = None
    if aa_benchmarks:
        m = re.search(r"coding_index=([\d.]+)", str(aa_benchmarks))
        if m:
            try:
                aa_coding_index = float(m.group(1))
            except ValueError:
                pass

    return {
        "name": name,
        "provider": provider,
        "license": "Proprietary",
        "open_weight": False,
        "openrouter_id": model_id,
        "huggingface_id": or_model.get("hugging_face_id"),
        "released": datetime.fromtimestamp(created).strftime("%Y-%m-%d") if created else None,
        "pricing": {
            "input_per_1m": round(prompt_per_token * 1_000_000, 4),
            "output_per_1m": round(completion_per_token * 1_000_000, 4),
            "cache_hit_per_1m": round(cache_read, 6) if cache_read > 0 else None,
            "currency": "USD",
        },
        "context_window": or_model.get("context_length"),
        "max_output": or_model.get("top_provider", {}).get("max_completion_tokens"),
        "benchmarks": {
            "swe_bench_verified": None,
            "swe_bench_pro": None,
            "terminal_bench_2_1": None,
            "livecodebench": None,
            "humaneval": None,
            "aa_coding_index": aa_coding_index,
            "scicode": None,
        },
        "reasoning_level": None,
        "tag": None,
        "best_for": None,
        "sources": {
            "pricing": "https://openrouter.ai/models/" + model_id,
            "benchmark": None,
        },
    }


# ---------- Source 2: Aider Polyglot Leaderboard ----------
def fetch_aider_leaderboard() -> dict:
    """Scrape Aider Polyglot coding leaderboard for % correct scores by model.
    
    The Aider leaderboard (aider.chat/docs/leaderboards/) tests 225 Exercism
    exercises across Python, Go, Rust, JavaScript, C++, and Java.
    Returns dict of normalized model name → pass_rate_2 (0-100).
    """
    log("Fetching Aider Polyglot leaderboard ...")
    html = fetch_text("https://aider.chat/docs/leaderboards/")
    if not html:
        log("Failed to fetch Aider page", "WARN")
        return {}

    # The page embeds model results in detail/summary elements.
    # Each model block has: model name, Percent correct value, pass rate 2 value.
    scores = {}

    # Try to find table-like data: model name followed by percentage
    # Pattern: model name line, then percent line like "88.0%"
    lines = html.split('\n')
    current_model = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect model name lines (typically inside detail/summary)
        # Model names contain hyphens, slashes, parens - not just HTML tags
        # The model name appears as text within <summary> or as plain text after "▶"
        model_match = re.match(r'^>\s*(.+?)\s*$', stripped)
        if model_match and not stripped.startswith('<') and not stripped.startswith('}'):
            name = model_match.group(1).strip()
            # Filter out non-model lines
            if any(c in name for c in ['%', '$', 'aider', 'http', '=', '{', '}']):
                continue
            if len(name) < 5 or len(name) > 100:
                continue
            # Skip common non-model text
            if name in ['Model', 'Percent correct', 'Cost', 'Command', 'Edit format',
                        'View', 'Select', 'Detail', 'Aider LLM Leaderboards',
                        'Code editing leaderboard', 'Refactoring leaderboard']:
                continue
            current_model = name

        # Look for pass rate percentage immediately after model name
        pct_match = re.match(r'^\s*(\d{2}\.\d+)%\s*$', stripped)
        if pct_match and current_model:
            score = float(pct_match.group(1))
            # First percent after model name is usually the pass_rate_2 (Percent correct)
            if current_model not in scores:
                scores[current_model] = score

    log(f"Found {len(scores)} model scores on Aider leaderboard")
    return scores


def normalize_model_name(name: str) -> str:
    """Normalize model name for matching across different sources."""
    n = name.lower()
    # Remove "Provider: " prefix from OpenRouter names
    n = re.sub(r'^[^:]+:\s*', '', n)
    # Remove version dates like "2026-04-20"
    n = re.sub(r'\d{4}[-/]\d{2}[-/]\d{2}', '', n)
    # Normalize whitespace
    n = re.sub(r'[^a-z0-9]', '', n)
    return n


def match_aider_to_local(local_models: list, aider_scores: dict) -> int:
    """Match Aider scores to local models by normalized name."""
    matched = 0
    for model in local_models:
        local_norm = normalize_model_name(model.get("name", ""))
        for aider_name, score in aider_scores.items():
            aider_norm = normalize_model_name(aider_name)
            # Exact match
            if local_norm == aider_norm:
                b = model.setdefault("benchmarks", {})
                if b.get("aider_polyglot") is None:
                    b["aider_polyglot"] = round(score, 1)
                    matched += 1
                    log(f"  AIDER match: {model['name']} = {score}%")
                break
            # Partial match (one contains the other)
            if len(local_norm) > 8 and len(aider_norm) > 8:
                if local_norm in aider_norm or aider_norm in local_norm:
                    b = model.setdefault("benchmarks", {})
                    if b.get("aider_polyglot") is None:
                        b["aider_polyglot"] = round(score, 1)
                        matched += 1
                        log(f"  AIDER fuzzy: {model['name']} ≈ {aider_name} = {score}%")
                    break
    return matched


# ---------- Source 3: HuggingFace (discovery) ----------
def discover_coding_models_on_hf() -> list:
    """Search HuggingFace for new coding models."""
    log("Discovering coding models on HuggingFace ...")
    found = []
    seen = set()
    for pattern in CODING_MODEL_PATTERNS:
        try:
            data = fetch_json(
                "https://huggingface.co/api/models",
                params={"search": pattern, "limit": 10, "full": False}
            )
            if not data:
                continue
            for m in data:
                model_id = m.get("id", "")
                if not model_id or model_id in seen:
                    continue
                seen.add(model_id)
                # Skip gated or private repos (will 401 on README)
                if m.get("private") or m.get("gated"):
                    continue
                # Must be reasonably popular OR from known org
                downloads = m.get("downloads", 0)
                if downloads < 1000:  # raised threshold to filter noise
                    continue
                # Only flag as "interesting" if it has coding-related tags
                tags = m.get("tags", [])
                coding_tags = ["code", "coding", "text-generation", "text-generation-inference"]
                if not any(t in tags for t in coding_tags):
                    continue
                found.append({
                    "id": model_id,
                    "downloads": downloads,
                    "created": m.get("createdAt"),
                    "tags": tags,
                })
        except Exception as e:
            log(f"HF search '{pattern}' failed: {e}", "WARN")
            continue
    log(f"Found {len(found)} candidate coding models on HuggingFace")
    return found


# ---------- Source 3: HuggingFace README (benchmarks) ----------
def extract_swe_bench_from_readme(model_id: str) -> dict:
    """Extract SWE-bench scores from a HuggingFace model card."""
    readme = fetch_text(f"https://huggingface.co/{model_id}/raw/main/README.md")
    if not readme:
        return {}

    extracted = {}
    # SWE-bench Verified: "SWE-bench Verified: 80.6%" or "swe-bench-verified: 80.6"
    for label in [
        ("swe_bench_verified", r"SWE-?bench[\s-]*Verified[^|\n]*?([\d.]+)\s*%"),
        ("swe_bench_pro", r"SWE-?bench[\s-]*Pro[^|\n]*?([\d.]+)\s*%"),
        ("terminal_bench_2_1", r"Terminal-?Bench[\s-]*2\.1[^|\n]*?([\d.]+)\s*%"),
        ("livecodebench", r"LiveCodeBench[^|\n]*?([\d.]+)\s*%"),
        ("humaneval", r"HumanEval[^|\n]*?([\d.]+)\s*%"),
    ]:
        key, pattern = label
        m = re.search(pattern, readme, re.IGNORECASE)
        if m:
            try:
                extracted[key] = float(m.group(1))
            except ValueError:
                pass
    return extracted


# ---------- Matching & merging ----------
def normalize(name: str) -> str:
    """Normalize model name for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_existing(models_data: dict, name: str, or_id: Optional[str] = None) -> Optional[dict]:
    """Find an existing model entry by exact name or OpenRouter ID match."""
    # Try matching with and without "Provider: " prefix
    name_normalized = normalize(name)
    name_base = normalize(re.sub(r"^[^:]+:\s*", "", name).strip())

    for m in models_data.get("models", []):
        # Exact normalized name match
        if normalize(m["name"]) == name_normalized:
            return m
        # Exact OpenRouter ID match
        if or_id and m.get("openrouter_id") == or_id:
            return m
        # Strip "Provider:" prefix from existing name; match against candidate's full OR base
        existing_base = normalize(re.sub(r"^[^:]+:\s*", "", m["name"]).strip())
        if existing_base == name_normalized or existing_base == name_base:
            return m
    return None


def deep_merge(target: dict, updates: dict) -> dict:
    """Merge updates into target. Only overwrites non-null values."""
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            deep_merge(target[k], v)
        elif v is not None:
            target[k] = v
    return target


# ---------- Main flows ----------
def refresh_from_openrouter(models_data: dict, check_only: bool = False) -> dict:
    """Update pricing + add new models from OpenRouter."""
    or_models = fetch_openrouter_models()
    if not or_models:
        return {"added": 0, "updated": 0, "skipped": 0}

    added = updated = skipped = 0
    new_models = []

    for or_m in or_models:
        candidate = openrouter_to_model(or_m)
        if not candidate:
            skipped += 1
            continue

        existing = find_existing(models_data, candidate["name"], candidate.get("openrouter_id"))

        if existing:
            # Update pricing + benchmarks from OpenRouter
            changes = {}
            # Pricing
            new_pricing = candidate["pricing"]
            if existing.get("pricing") != new_pricing:
                changes["pricing"] = new_pricing
            # Context
            if candidate.get("context_window") and existing.get("context_window") != candidate["context_window"]:
                changes["context_window"] = candidate["context_window"]
            # AA coding index
            if candidate["benchmarks"].get("aa_coding_index"):
                b = existing.setdefault("benchmarks", {})
                if b.get("aa_coding_index") != candidate["benchmarks"]["aa_coding_index"]:
                    changes.setdefault("benchmarks", {})["aa_coding_index"] = candidate["benchmarks"]["aa_coding_index"]

            if changes:
                if not check_only:
                    deep_merge(existing, changes)
                log(f"  UPDATE {candidate['name']}: {list(changes.keys())}")
                updated += 1
        else:
            # New model — only add if pricing is reasonable (< $50/1M output)
            if candidate["pricing"]["output_per_1m"] < 50:
                new_models.append(candidate)
                log(f"  NEW: {candidate['name']} (${candidate['pricing']['output_per_1m']}/1M out)")

    if new_models:
        if not check_only:
            models_data.setdefault("models", []).extend(new_models)
        added = len(new_models)

    log(f"OpenRouter: added={added}, updated={updated}, skipped={skipped}")
    return {"added": added, "updated": updated, "skipped": skipped}


def discover_new_models(models_data: dict, check_only: bool = False) -> int:
    """Find new coding models on HuggingFace and try to add them."""
    candidates = discover_coding_models_on_hf()
    added = 0

    for c in candidates:
        # Skip if already in our list
        existing = find_existing(models_data, c["id"].split("/")[-1])
        if existing:
            continue

        # Try to get SWE-bench from model card
        benchmarks = extract_swe_bench_from_readme(c["id"])
        if not benchmarks:
            continue  # Skip if no coding benchmarks found

        provider = c["id"].split("/")[0] if "/" in c["id"] else "Unknown"
        name = c["id"].split("/")[-1]
        name_lower = name.lower()

        # Mark as proprietary by default when discovered from HF (can't assume open-weight)
        is_open = "deepseek" in name_lower or "minimax" in name_lower or "qwen" in name_lower or "glm" in name_lower
        new_entry = {
            "name": name,
            "provider": provider,
            "license": "Open-weight" if is_open else "Proprietary",
            "open_weight": is_open,
            "openrouter_id": None,
            "huggingface_id": c["id"],
            "released": c["created"][:10] if c.get("created") else None,
            "pricing": {
                "input_per_1m": None,
                "output_per_1m": None,
                "cache_hit_per_1m": None,
                "currency": "USD",
            },
            "context_window": None,
            "max_output": None,
            "benchmarks": {
                "swe_bench_verified": benchmarks.get("swe_bench_verified"),
                "swe_bench_pro": benchmarks.get("swe_bench_pro"),
                "terminal_bench_2_1": benchmarks.get("terminal_bench_2_1"),
                "livecodebench": benchmarks.get("livecodebench"),
                "humaneval": benchmarks.get("humaneval"),
                "aa_coding_index": None,
                "scicode": None,
            },
            "reasoning_level": None,
            "tag": "New Release",
            "best_for": "Newly discovered — needs review",
            "sources": {
                "pricing": None,
                "benchmark": f"https://huggingface.co/{c['id']}",
            },
        }

        if not check_only:
            models_data.setdefault("models", []).append(new_entry)
        log(f"  DISCOVERED: {name} (SWE-Pro: {benchmarks.get('swe_bench_pro')})")
        added += 1

        # Rate limit HF requests
        time.sleep(1)

    log(f"Discovered {added} new models from HuggingFace")
    return added


def enrich_benchmarks_from_hf(models_data: dict, check_only: bool = False) -> int:
    """Check OR-discovered models lacking benchmarks against HF model cards.

    Many models added from OpenRouter have a huggingface_id but no benchmark
    data. This pass fetches their READMEs and extracts SWE-bench scores.
    """
    enriched = 0
    # Only enrich models that lack all coding benchmarks
    benchmark_keys = ["swe_bench_verified", "swe_bench_pro", "terminal_bench_2_1",
                      "livecodebench", "humaneval", "aider_polyglot", "aa_coding_index",
                      "livebench", "scicode"]

    for m in models_data.get("models", []):
        b = m.setdefault("benchmarks", {})
        # Skip if any benchmark already set
        if any(b.get(k) is not None for k in benchmark_keys):
            continue

        hf_id = m.get("huggingface_id")
        if not hf_id:
            continue

        log(f"  HF enrich: {m['name']} ({hf_id})")
        extracted = extract_swe_bench_from_readme(hf_id)
        if extracted:
            for key, val in extracted.items():
                if b.get(key) is None:
                    b[key] = val
                    if not check_only:
                        m["sources"] = m.get("sources", {})
                        m["sources"]["benchmark"] = f"https://huggingface.co/{hf_id}"
            enriched += 1
            found = [f"{k}={v}" for k, v in extracted.items()]
            log(f"    Found: {', '.join(found)}")
        else:
            log(f"    No benchmarks found in README")
        time.sleep(1)  # Rate limit

    log(f"HF enrich: updated {enriched} models with benchmark data")
    return enriched


def main():
    parser = argparse.ArgumentParser(description="Update model leaderboard data")
    parser.add_argument("--model", help="Update only this model (name substring match)")
    parser.add_argument("--discover", action="store_true", help="Only discover new models, don't refresh existing")
    parser.add_argument("--check-only", action="store_true", help="Show changes without writing")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to disk")
    args = parser.parse_args()

    if not DATA_FILE.exists():
        log(f"Data file not found: {DATA_FILE}", "ERROR")
        sys.exit(1)

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    log(f"Loaded {len(data.get('models', []))} existing models")

    # Run refresh from OpenRouter
    if not args.model or "deepseek" in args.model.lower() or len(args.model) < 3:
        # Single-model refresh only for very specific queries
        result = refresh_from_openrouter(data, check_only=args.check_only)
            # Aider Polyglot refresh
        log("Fetching Aider Polyglot scores...")
        aider_scores = fetch_aider_leaderboard()
        if aider_scores:
            matched = match_aider_to_local(data.get("models", []), aider_scores)
            log(f"Aider: matched {matched} models")

        # Snapshot-based benchmark sources (LiveBench + AA Index)
        lb_matched = match_livebench(data.get("models", []), log_fn=log)
        aa_matched = match_aa_index(data.get("models", []), log_fn=log)
        log(f"LiveBench snapshot: matched {lb_matched} models")
        log(f"AA Index snapshot: matched {aa_matched} models")

        # Live scrapers for additional benchmark sources
        # BenchLM.ai — SWE-bench Verified (55+ models)
        benchlm_scores = fetch_benchlm_swe_bench()
        if benchlm_scores:
            blm_matched = match_live_scores(
                data.get("models", []), benchlm_scores, "swe_bench_verified", log_fn=log
            )
            log(f"BenchLM SWE-bench Verified: matched {blm_matched} models")

        # tbench.ai — Terminal-Bench 2.1 (agentic CLI)
        tbench_scores = fetch_tbench_scores()
        if tbench_scores:
            tb_matched = match_live_scores(
                data.get("models", []), tbench_scores, "terminal_bench_2_1", log_fn=log
            )
            log(f"Terminal-Bench 2.1: matched {tb_matched} models")

        # whatllm.org — Multi-benchmark (LiveCodeBench, Terminal-Bench, SciCode)
        whatllm_scores = fetch_whatllm_scores()
        if whatllm_scores:
            wl_matched = match_whatllm_multi(
                data.get("models", []), whatllm_scores, log_fn=log
            )
            log(f"WhatLLM multi-benchmark: matched {wl_matched} fields")

        if not args.discover:
            # Enrich OR-discovered models with benchmarks from HF model cards
            enrich_benchmarks_from_hf(data, check_only=args.check_only)

            log("Discovery pass (HuggingFace)...")
            discover_new_models(data, check_only=args.check_only)
    else:
        log(f"Refreshing single model: {args.model}")
        # For single-model, find it in our data and try to refresh from OpenRouter
        for m in data.get("models", []):
            if args.model.lower() in m["name"].lower():
                log(f"Found: {m['name']}")

    # Update timestamp
    if not args.check_only and not args.dry_run:
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        # Recompute derived scores
        for m in data.get("models", []):
            try:
                # cost_per_pro_point
                out = m.get("pricing", {}).get("output_per_1m")
                b = m.get("benchmarks", {}) or {}
                pro = b.get("swe_bench_pro")
                if out and pro:
                    m["cost_per_pro_point"] = round(out / pro, 3)
                else:
                    m.pop("cost_per_pro_point", None)

                # Base score from common benchmarks (normalized). Hard benchmarks (Pro, Aider)
                # are treated as bonus signals — they can only help, never hurt.
                base_weights = {"swe_bench_verified": 0.50, "terminal_bench_2_1": 0.25,
                                "livebench": 0.15, "scicode": 0.10}
                bonus_keys = {"swe_bench_pro": 5.0, "aider_polyglot": 3.0}
                norm_ranges = {
                    "swe_bench_verified": (25, 90),
                    "terminal_bench_2_1": (45, 85),
                    "livebench": (30, 75),
                    "scicode": (40, 65),
                }
                # Compute base score
                base_score = 0.0
                base_w = 0.0
                base_count = 0
                has_primary = False
                for key, weight in base_weights.items():
                    val = b.get(key)
                    if val is not None:
                        lo, hi = norm_ranges[key]
                        norm = max(0, min(100, (float(val) - lo) / (hi - lo) * 100))
                        base_score += norm * weight
                        base_w += weight
                        base_count += 1
                        if key in ("swe_bench_verified", "terminal_bench_2_1"):
                            has_primary = True
                if base_w == 0 or not has_primary:
                    m.pop("coding_quality_score", None)
                else:
                    # Add bonuses from hard benchmarks (only if above threshold)
                    bonuses = 0.0
                    bonus_count = 0
                    pro_thresholds = {"swe_bench_pro": 45.0, "aider_polyglot": 65.0}
                    for key, max_bonus in bonus_keys.items():
                        val = b.get(key)
                        if val is not None:
                            bonus_count += 1
                            threshold = pro_thresholds[key]
                            if float(val) >= threshold:
                                bonuses += max_bonus
                    total_bm = base_count + bonus_count
                    final = base_score / base_w + bonuses
                    if total_bm == 1:
                        final *= 0.88
                    elif total_bm == 2:
                        final *= 0.95
                    final = min(final, 100.0)
                    m["coding_quality_score"] = round(final, 1)

                # cost_per_quality
                qs = m.get("coding_quality_score")
                if out and qs and qs > 0:
                    m["cost_per_quality"] = round(out / qs, 3)
                else:
                    m.pop("cost_per_quality", None)
            except Exception:
                pass

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log(f"Wrote {len(data.get('models', []))} models to {DATA_FILE}")
    else:
        log(f"No changes to write (check_only={args.check_only}, dry_run={args.dry_run})")


if __name__ == "__main__":
    main()