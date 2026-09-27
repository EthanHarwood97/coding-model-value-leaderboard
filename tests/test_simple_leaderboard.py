#!/usr/bin/env python3
"""Fixture-based tests for the LiveBench official feed and simple build."""
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import livebench_official as lbo
import build_simple

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _rows(name):
    return list(csv.DictReader(io.StringIO(_read(name))))


def _patch_fetch(mapping):
    original = lbo._fetch_text
    lbo._fetch_text = lambda url: mapping.get(url)
    return original


def test_discover_latest_release():
    original = _patch_fetch({
        lbo.SITE_URL: _read("livebench_site_sample.html"),
        "https://livebench.ai/static/js/main.abc123.js": _read("livebench_bundle_sample.js"),
    })
    try:
        assert lbo.discover_latest_release() == "2026-06-25"
    finally:
        lbo._fetch_text = original


def test_resolve_release_fallback():
    original = _patch_fetch({})
    try:
        assert lbo.resolve_release() == lbo.PINNED_RELEASE
        assert lbo.resolve_release("2026-05-01") == "2026-05-01"
    finally:
        lbo._fetch_text = original


def test_category_means():
    categories = json.loads(_read("livebench_categories_sample.json"))
    row = _rows("livebench_table_sample.csv")[0]
    means = lbo.category_means(row, categories)
    assert means["Coding"] == 79.0, means
    assert means["Agentic Coding"] == 50.0, means


def test_core_name_matching_variants():
    assert lbo.core_name("claude-opus-4-6-thinking-auto-high-effort") == "claudeopus46"
    assert lbo.core_name("claude-opus-4-5-20251101-thinking-64k-high-effort") == "claudeopus45"
    assert lbo.core_name("gpt-5.2-2025-12-11-high") == "gpt52"
    assert lbo.core_name("Claude Opus 4.6") == "claudeopus46"
    assert lbo.core_name("deepseek-v4-flash-0731") != lbo.core_name("deepseek-v4-flash")


def test_name_parts():
    assert lbo.name_parts("claude-opus-4-6-thinking-auto-high-effort") == (
        "Claude Opus 4.6", "Thinking Auto High Effort")
    assert lbo.name_parts("gpt-5.4-mini-xhigh") == ("GPT-5.4 Mini", "xHigh")
    assert lbo.name_parts("glm-5.2") == ("GLM-5.2", "")
    assert lbo.name_parts("deepseek-v4-flash-0731") == ("DeepSeek V4 Flash", "0731")
    assert lbo.prettify_name("claude-opus-5-5-max-effort") == "Claude Opus 5.5 · Max Effort"


def test_infer_provider():
    assert lbo.infer_provider("claude-opus-5-5-max-effort") == "Anthropic"
    assert lbo.infer_provider("qwen3.8-max") == "Alibaba"
    assert lbo.infer_provider("nemotron-3-ultra-550b-a55b") == "NVIDIA"


def test_build_models_merge():
    table = _rows("livebench_table_sample.csv")
    categories = json.loads(_read("livebench_categories_sample.json"))
    cost = _rows("livebench_cost_sample.csv")
    vision = {"Claude Opus 4.6": 77.3, "GPT-5.6 Sol": 83.0, "Kimi K2.6": 79.4}
    local = [
        {"name": "DeepSeek V4 Flash", "pricing": {"output_per_1m": 0.18}},
        {"name": "Anthropic: Claude Opus 4.6", "pricing": {"output_per_1m": 5.0}},
    ]

    models = build_simple.build_models(table, categories, cost, vision, local)
    by_raw = {m["raw"]: m for m in models}

    claude = by_raw["claude-opus-4-6-thinking-auto-high-effort"]
    assert claude["vision_score"] == 77.3
    assert claude["vision_source"] == "benchlm"
    assert claude["coder_score"] == 64.5, claude
    assert claude["frontend_score"] == 68.8, claude
    assert claude["output_price_per_1m"] == 5.0
    assert claude["price_source"].startswith("models.json")
    assert claude["coverage"] == 3

    flash = by_raw["deepseek-v4-flash"]
    assert flash["vision_score"] is None
    assert flash["agentic_coding"] == 37.6
    assert flash["agentic_effective"] == 22.6
    assert flash["coder_score"] == 45.8, flash
    assert flash["frontend_score"] == 45.8, flash
    assert flash["output_price_per_1m"] == 0.18
    assert flash["value"] == 152.67, flash

    variant = by_raw["deepseek-v4-flash-0731"]
    assert variant["price_source"] == "livebench", variant
    assert variant["output_price_per_1m"] == 0.3
    assert variant["value"] == 96.4, variant

    unmatched = by_raw["some-unmatched-model"]
    assert unmatched["price_source"] == "livebench"
    assert unmatched["output_price_per_1m"] == 2.0
    assert unmatched["value"] == 13.35, unmatched

    raws = [m["raw"] for m in models]
    assert raws == sorted(raws, key=lambda r: -by_raw[r]["frontend_score"])
    assert models[0]["raw"] == "claude-opus-5-max-effort"


def test_vision_estimates():
    table = _rows("livebench_table_sample.csv")
    categories = json.loads(_read("livebench_categories_sample.json"))
    vision = {"Claude Opus 4.6": 77.3, "GPT-5.6 Sol": 83.0, "Kimi K2.6": 79.4}

    models = build_simple.build_models(table, categories, [], vision, [])
    by_raw = {m["raw"]: m for m in models}

    opus5 = by_raw["claude-opus-5-max-effort"]
    assert opus5["vision_score"] is None
    assert opus5["vision_est"] == {"value": 77.3, "from": "Claude Opus 4.6"}, opus5
    assert opus5["coder_score"] == 78.8, opus5
    assert opus5["frontend_score"] == 78.8, opus5

    gpt6 = by_raw["gpt-6-sol-max"]
    assert gpt6["vision_est"] == {"value": 83.0, "from": "GPT-5.6 Sol"}, gpt6

    kimi_code = by_raw["kimi-k2.7-code"]
    assert kimi_code["vision_est"] is None, kimi_code

    claude = by_raw["claude-opus-4-6-thinking-auto-high-effort"]
    assert claude["vision_est"] is None


def test_line_key_and_version():
    assert build_simple._line_key("claude-opus-5-max-effort") == "claudeopus"
    assert build_simple._line_key("gpt-6-sol-max") == "gptsol"
    assert build_simple._line_key("kimi-k2.7-code") == "kimikcode"
    assert build_simple._version("Claude Opus 5.5") == 5.5
    assert build_simple._version("GPT-6 Sol") == 6.0
    assert build_simple._version("Smaug Mini") is None


def test_aa_mmmu_pro_parser():
    import live_benchmarks

    original = live_benchmarks._fetch_text
    live_benchmarks._fetch_text = lambda url: (
        _read("benchlm_aa_mmmu_pro_sample.md") if "aammmupro" in url.lower() else None)
    try:
        scores = live_benchmarks.fetch_benchlm_aa_mmmu_pro()
    finally:
        live_benchmarks._fetch_text = original

    assert len(scores) == 5, scores
    assert scores["Claude Opus 5.5"] == 87.7
    assert scores["GPT-6 Astra"] == 86.9
    assert scores["Claude Opus 4.6 (Adaptive)"] == 75.4


def test_vision_index_priority():
    index = build_simple._vision_index(
        aa_scores={"Model X (Adaptive)": 70.0, "Model X": 65.0},
        standard_scores={"Model X": 75.0, "Model Y": 60.0},
        standard_extra={"Model X": 77.0, "Model Y": 61.0, "Model Z": 50.0},
    )
    assert index["modelx"] == (70.0, "aa")
    assert index["modely"] == (60.0, "benchlm")
    assert index["modelz"] == (50.0, "llm-stats")


def test_build_models_vision_sources():
    table = _rows("livebench_table_sample.csv")
    categories = json.loads(_read("livebench_categories_sample.json"))
    standard = {"Claude Opus 4.6": 77.3}
    extra = {"Claude Opus 4.6": 76.0}
    aa = {
        "Claude Opus 4.6 (Adaptive)": 75.4,
        "Claude Opus 4.6": 72.5,
        "GPT-5.6 Sol": 83.4,
    }

    models = build_simple.build_models(table, categories, [], standard, [],
                                       vision_extra=extra, vision_aa=aa)
    by_raw = {m["raw"]: m for m in models}

    claude = by_raw["claude-opus-4-6-thinking-auto-high-effort"]
    assert claude["vision_score"] == 75.4, claude
    assert claude["vision_source"] == "aa"
    assert claude["vision_est"] is None

    gpt6 = by_raw["gpt-6-sol-max"]
    assert gpt6["vision_est"] == {"value": 83.4, "from": "GPT-5.6 Sol"}, gpt6


def test_agentic_floor_penalty():
    assert build_simple._effective_agentic(42.0) == 42.0
    assert build_simple._effective_agentic(41.9) == round(41.9 * 0.6, 1)
    assert build_simple._effective_agentic(None) is None

    table = _rows("livebench_table_sample.csv")
    categories = json.loads(_read("livebench_categories_sample.json"))
    models = build_simple.build_models(table, categories, [], {}, [])
    by_raw = {m["raw"]: m for m in models}

    flash = by_raw["deepseek-v4-flash"]
    assert flash["agentic_coding"] == 37.6
    assert flash["agentic_effective"] == 22.6
    assert flash["coder_score"] == 45.8
    assert flash["value"] is None

    claude = by_raw["claude-opus-4-6-thinking-auto-high-effort"]
    assert claude["agentic_effective"] is None
    assert claude["coder_score"] == 64.5

    gpt6 = by_raw["gpt-6-sol-max"]
    assert gpt6["agentic_effective"] is None
    assert gpt6["coder_score"] == 56.8


def test_top_level_matcher_prefix_guard():
    import live_benchmarks

    models = [
        {"name": "OpenAI: GPT-5.4", "vision_score": None},
        {"name": "OpenAI: GPT-5.4 Nano", "vision_score": None},
    ]
    scores = {"OpenAI: GPT-5.4 Nano": 76.6, "OpenAI: GPT-5.4": 81.2}

    matched = live_benchmarks.match_live_scores_top_level(models, scores, "vision_score")
    by_name = {m["name"]: m["vision_score"] for m in models}

    assert matched == 2
    assert by_name["OpenAI: GPT-5.4"] == 81.2, by_name
    assert by_name["OpenAI: GPT-5.4 Nano"] == 76.6, by_name


if __name__ == "__main__":
    test_discover_latest_release()
    test_resolve_release_fallback()
    test_category_means()
    test_core_name_matching_variants()
    test_name_parts()
    test_infer_provider()
    test_build_models_merge()
    test_vision_estimates()
    test_line_key_and_version()
    test_aa_mmmu_pro_parser()
    test_vision_index_priority()
    test_build_models_vision_sources()
    test_agentic_floor_penalty()
    test_top_level_matcher_prefix_guard()
    print("All simple-leaderboard tests passed.")
