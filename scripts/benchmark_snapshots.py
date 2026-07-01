"""
benchmark_snapshots.py — Inlined snapshots from whichllm project

Sources:
- LiveBench 2026-01-08 CSV + 2026-04 carryover (raw global average, 0-100)
- Artificial Analysis Intelligence Index verified 2026-05-14 (raw index, ~12-56)

Each entry maps a HuggingFace model ID to a raw score.  The matching
function normalizes both sides to find the best fit.

Usage:
    from benchmark_snapshots import match_livebench, match_aa_index
    matched = match_livebench(local_models)
"""

import re
import time

# ── LiveBench global-average snapshot ────────────────────────────────────
# Generated from the 2026-01-08 CSV (scripts/import_livebench_csv.py) plus
# 2026-04 carryover for older / smaller-class models.
LIVEBENCH_SNAPSHOT: dict[str, float] = {
    # --- 2026-01-08 CSV entries
    "MiniMaxAI/MiniMax-M2.5": 60.3,
    "MiniMaxAI/MiniMax-M2.7": 65.0,
    "Qwen/Qwen3-235B-A22B-Instruct-2507": 48.0,
    "Qwen/Qwen3-235B-A22B-Thinking-2507": 52.9,
    "Qwen/Qwen3-30B-A3B-Thinking-2507": 38.8,
    "Qwen/Qwen3-32B": 42.7,
    "Qwen/Qwen3-Next-80B-A3B-Instruct": 47.4,
    "Qwen/Qwen3-Next-80B-A3B-Thinking": 51.0,
    "Qwen/Qwen3.6-27B": 65.6,
    "XiaomiMiMo/MiMo-V2-Pro": 58.4,
    "deepseek-ai/DeepSeek-V3.2": 63.1,
    "deepseek-ai/DeepSeek-V3.2-Exp": 58.9,
    "deepseek-ai/DeepSeek-V4-Flash": 67.7,
    "deepseek-ai/DeepSeek-V4-Pro": 74.4,
    "google/gemma-4-31b-it": 62.4,
    "mistralai/Devstral-2512": 38.8,
    "moonshotai/Kimi-K2-Instruct": 45.9,
    "moonshotai/Kimi-K2-Thinking": 62.3,
    "moonshotai/Kimi-K2.5": 69.2,
    "moonshotai/Kimi-K2.6-Thinking": 72.4,
    "nvidia/Nemotron-3-Super-120B-A12B": 32.0,
    "openai/gpt-oss-120b": 46.4,
    "zai-org/GLM-4.6": 54.7,
    "zai-org/GLM-4.6V": 38.9,
    "zai-org/GLM-4.7": 57.3,
    "zai-org/GLM-5": 68.7,
    "zai-org/GLM-5.1": 70.6,
    # --- 2026-04 carryover (anchors for older / smaller-class models)
    "deepseek-ai/DeepSeek-R1-0528": 71.0,
    "deepseek-ai/DeepSeek-R1": 65.0,
    "deepseek-ai/DeepSeek-V3-0324": 57.0,
    "Qwen/Qwen3-235B-A22B": 65.0,
    "Qwen/Qwen3-Coder-30B-A3B-Instruct": 58.0,
    "Qwen/QwQ-32B": 57.0,
    "Qwen/Qwen3-4B-Thinking-2507": 50.0,
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": 56.0,
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": 50.0,
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B": 42.0,
    "meta-llama/Llama-3.3-70B-Instruct": 48.0,
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct": 54.0,
    "meta-llama/Llama-4-Scout-17B-16E-Instruct": 49.0,
    "google/gemma-3-27b-it": 50.0,
    "google/gemma-4-26b-a4b-it": 54.0,
    "microsoft/phi-4": 53.0,
    "mistralai/Mistral-Large-Instruct-2411": 58.0,
    "mistralai/Devstral-Small-2505": 50.0,
    "openai/gpt-oss-20b": 52.0,
    "zai-org/GLM-4.5": 58.0,
    "zai-org/GLM-4.5-Air": 52.0,
    "Qwen/Qwen3-8B": 50.0,
    "Qwen/Qwen3-14B": 56.0,
    "Qwen/Qwen3-4B-Instruct-2507": 45.0,
    "Qwen/Qwen3-4B": 42.0,
    "Qwen/Qwen3-30B-A3B": 58.0,
    "Qwen/Qwen2.5-7B-Instruct": 38.0,
    "Qwen/Qwen2.5-14B-Instruct": 42.0,
    "Qwen/Qwen2.5-32B-Instruct": 50.0,
    "meta-llama/Llama-3.1-8B-Instruct": 36.0,
    "google/gemma-2-9b-it": 38.0,
    "google/gemma-3-12b-it": 44.0,
    "microsoft/Phi-4-mini-instruct": 40.0,
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506": 50.0,
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503": 48.0,
}

# ── Artificial Analysis Intelligence Index snapshot ──────────────────────
# Verified 2026-05-14 from artificialanalysis.ai leaderboards/models.
# Raw index values (open-weights only), typically range 12-56.
AA_INDEX_SNAPSHOT: dict[str, float] = {
    "moonshotai/Kimi-K2-Thinking": 50.0,
    "moonshotai/Kimi-K2-Instruct": 47.0,
    "XiaomiMiMo/MiMo-V2.5-Pro": 54.0,
    "XiaomiMiMo/MiMo-V2.5": 49.0,
    "deepseek-ai/DeepSeek-V4-Pro": 52.0,
    "deepseek-ai/DeepSeek-V4-Flash": 47.0,
    "deepseek-ai/DeepSeek-V3.2": 45.0,
    "deepseek-ai/DeepSeek-V3.2-Exp": 44.0,
    "deepseek-ai/DeepSeek-V3.1": 42.0,
    "deepseek-ai/DeepSeek-V3-0324": 40.0,
    "deepseek-ai/DeepSeek-V3": 38.0,
    "deepseek-ai/DeepSeek-R1-0528": 48.0,
    "deepseek-ai/DeepSeek-R1": 43.0,
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": 32.0,
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": 26.0,
    "deepseek-ai/DeepSeek-R1-Distill-Llama-8B": 20.0,
    "Qwen/QwQ-32B": 36.0,
    "Qwen/Qwen3-4B-Thinking-2507": 22.0,
    "zai-org/GLM-5.1": 51.0,
    "zai-org/GLM-5.1-FP8": 51.0,
    "zai-org/GLM-5": 50.0,
    "zai-org/GLM-5-FP8": 50.0,
    "zai-org/GLM-4.7-Flash": 42.0,
    "zai-org/GLM-4.6": 40.0,
    "zai-org/GLM-4.5": 38.0,
    "zai-org/GLM-4.5-Air": 36.0,
    "Qwen/Qwen3.6-27B": 46.0,
    "Qwen/Qwen3.5-397B-A17B": 45.0,
    "Qwen/Qwen3-Next-80B-A3B-Instruct": 42.0,
    "Qwen/Qwen3-235B-A22B": 41.0,
    "Qwen/Qwen3-Coder-30B-A3B-Instruct": 38.0,
    "Qwen/Qwen3-32B": 37.0,
    "Qwen/Qwen3-14B": 33.0,
    "Qwen/Qwen3-8B": 30.0,
    "Qwen/Qwen3-4B-Instruct-2507": 28.0,
    "Qwen/Qwen3-4B": 26.0,
    "Qwen/Qwen3-1.7B": 20.0,
    "Qwen/Qwen3-0.6B": 16.0,
    "meta-llama/Llama-3.1-8B-Instruct": 22.0,
    "meta-llama/Meta-Llama-3-8B-Instruct": 20.0,
    "google/gemma-2-9b-it": 23.0,
    "microsoft/Phi-4-mini-instruct": 24.0,
    "mistralai/Mistral-7B-Instruct-v0.3": 20.0,
    "Qwen/Qwen2.5-7B-Instruct": 22.0,
    "Qwen/Qwen2.5-14B-Instruct": 26.0,
    "Qwen/Qwen2.5-32B-Instruct": 30.0,
    "Qwen/Qwen3-30B-A3B": 32.0,
    "openai/gpt-oss-120b": 41.0,
    "openai/gpt-oss-20b": 34.0,
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct": 38.0,
    "meta-llama/Llama-4-Scout-17B-16E-Instruct": 34.0,
    "meta-llama/Llama-3.3-70B-Instruct": 33.0,
    "google/gemma-4-31b-it": 38.0,
    "google/gemma-4-26b-a4b-it": 36.0,
    "google/gemma-3-27b-it": 33.0,
    "google/gemma-3-12b-it": 30.0,
    "microsoft/phi-4": 33.0,
    "mistralai/Mistral-Large-Instruct-2411": 35.0,
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506": 32.0,
    "mistralai/Mistral-Small-3.1-24B-Instruct-2503": 30.0,
    "mistralai/Devstral-Small-2505": 33.0,
    "MiniMaxAI/MiniMax-M2.5": 40.0,
    "stepfun-ai/Step-3.5-Flash": 38.0,
    "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16": 36.0,
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16": 33.0,
    "allenai/Olmo-3-7B-Instruct": 22.0,
    "allenai/Olmo-3-1025-7B": 22.0,
    "ibm-granite/granite-4.0-h-small": 30.0,
    "ibm-granite/granite-4.0-h-tiny": 22.0,
    "ibm-granite/granite-3.3-8b-instruct": 23.0,
    "ibm-granite/granite-3.3-2b-instruct": 17.0,
    "mistralai/Codestral-22B-v0.1": 28.0,
}


# ── Manual overrides ─────────────────────────────────────────────────────
# Maps a local model's normalized name (stripped of provider prefix) → HF ID
# from the snapshot.  Covers cases where slug-based matching fails because
# the names differ significantly (e.g. "Nemotron 3 Super" vs
# "NVIDIA-Nemotron-3-Super-120B-A12B-BF16").
MANUAL_LIVEBENCH: dict[str, str] = {
    "nemotron3super": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
    "katcoderprov2": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
}
MANUAL_AA_INDEX: dict[str, str] = {
    "nemotron3super": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16",
    "nemotron3nano30ba3b": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
    "katcoderprov2": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16",
    "lagunaxs2": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16",
    "lagunam1": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16",
}


# ── Name normalisation helpers ───────────────────────────────────────────

def _extract_slug(hf_id: str) -> str:
    """Extract the last component of a HuggingFace ID."""
    return hf_id.split("/")[-1] if "/" in hf_id else hf_id


def _norm(s: str) -> str:
    """Lowercase, strip whitespace, remove all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _strip_provider(model_name: str) -> str:
    """Remove leading 'Provider: ' prefix from OpenRouter-style names."""
    return re.sub(r"^[^:]+:\s*", "", model_name).strip()


# ── Snapshot index builder ───────────────────────────────────────────────

def _build_slug_index(snapshot: dict[str, float]) -> dict[str, float]:
    """Build a normalised-slug -> best-score index from a HF-ID-keyed snapshot.

    When multiple HF IDs map to the same slug (e.g. GLM-5 and GLM-5-FP8),
    the highest score wins.
    Also includes full HF ID as additional key for exact-match-by-HF-ID.
    """
    index: dict[str, float] = {}
    for hf_id, score in snapshot.items():
        slug = _norm(_extract_slug(hf_id))
        if score > index.get(slug, 0.0):
            index[slug] = score
        # Also index by normalized full HF ID (for matching via huggingface_id)
        index[_norm(hf_id)] = max(index.get(_norm(hf_id), 0.0), score)
    return index


# ── Public matching functions ────────────────────────────────────────────

def match_snapshot(models: list[dict], snapshot: dict[str, float],
                   benchmark_key: str, log_fn=None) -> int:
    """Match snapshot scores to models by normalised HF-slug / model-name.

    Matching strategy (tried in order):
    1. Manual override dict
    2. Exact match via model's huggingface_id (normalized)
    3. Exact match: snapshot slug in [model_name_norm, stripped_name_norm]
    4. Fuzzy substring: for names > 8 chars, check if either contains the other

    Returns the number of models that received a new (non-overwritten) score.
    """
    index = _build_slug_index(snapshot)
    manual = MANUAL_AA_INDEX if benchmark_key == "aa_coding_index" else MANUAL_LIVEBENCH
    if benchmark_key == "aa_coding_index":
        manual.update(MANUAL_LIVEBENCH)
    matched = 0

    for model in models:
        name = model.get("name", "")
        if not name:
            continue
        stripped = _strip_provider(name)
        candidates = [_norm(name), _norm(stripped)]
        b = model.setdefault("benchmarks", {})
        if b.get(benchmark_key) is not None:
            continue

        # 1. Manual override
        for manual_norm, manual_hf_id in manual.items():
            if manual_norm in candidates:
                score = index.get(_norm(_extract_slug(manual_hf_id)))
                if score is not None:
                    b[benchmark_key] = round(score, 1)
                    matched += 1
                    if log_fn:
                        log_fn(f"  {benchmark_key}: {name} = {score} (manual)")
                    break
        if b.get(benchmark_key) is not None:
            continue

        # 2. Exact match via huggingface_id
        hf_id = model.get("huggingface_id")
        if hf_id:
            hf_norm = _norm(hf_id)
            score = index.get(hf_norm)
            if score is not None:
                b[benchmark_key] = round(score, 1)
                matched += 1
                if log_fn:
                    log_fn(f"  {benchmark_key}: {name} = {score} (hf_id)")
                continue

        # 3. Exact match: slug in candidates
        found = False
        for slug, score in index.items():
            if slug in candidates:
                b[benchmark_key] = round(score, 1)
                matched += 1
                if log_fn:
                    log_fn(f"  {benchmark_key}: {name} = {score}")
                found = True
                break
        if found:
            continue

        # 4. Fuzzy substring: for names > 8 chars, check if one contains the other
        for slug, score in index.items():
            for c in candidates:
                if len(c) > 8 and len(slug) > 8:
                    if c in slug or slug in c:
                        b[benchmark_key] = round(score, 1)
                        matched += 1
                        if log_fn:
                            log_fn(f"  {benchmark_key}: {name} = {score} (fuzzy)")
                        found = True
                        break
            if found:
                break

    return matched


def match_livebench(models: list[dict], log_fn=None) -> int:
    """Match LiveBench scores to models.  Adds 'livebench' field."""
    return match_snapshot(models, LIVEBENCH_SNAPSHOT, "livebench", log_fn)


def match_aa_index(models: list[dict], log_fn=None) -> int:
    """Match AA Intelligence Index to models as a fallback for
    'aa_coding_index' when no value is already set."""
    return match_snapshot(models, AA_INDEX_SNAPSHOT, "aa_coding_index", log_fn)
