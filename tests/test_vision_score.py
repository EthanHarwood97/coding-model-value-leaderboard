#!/usr/bin/env python3
"""Fixture-based test for the MMMU-Pro scraper and top-level matcher."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from live_benchmarks import fetch_benchlm_mmmu_pro, match_live_scores_top_level

FIXTURE = Path(__file__).parent / "fixtures" / "benchlm_mmmu_pro.html"


def _load_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    import live_benchmarks
    live_benchmarks._fetch_text = lambda url: html
    return html


def test_scraper_parses_scores():
    _load_fixture()
    scores = fetch_benchlm_mmmu_pro()
    assert len(scores) >= 3, f"expected several scores, got {len(scores)}"
    assert any("GPT-5.4 Pro" in name for name in scores), "missing GPT-5.4 Pro"
    assert max(scores.values()) <= 100


def test_top_level_matcher_writes_field():
    _load_fixture()
    scores = fetch_benchlm_mmmu_pro()
    models = [
        {"name": "GPT-5.4 Pro", "benchmarks": {}},
        {"name": "Some Unlisted Model", "benchmarks": {}},
    ]
    matched = match_live_scores_top_level(models, scores, "vision_score")
    assert matched >= 1
    assert models[0].get("vision_score") is not None
    assert models[1].get("vision_score") is None


if __name__ == "__main__":
    test_scraper_parses_scores()
    test_top_level_matcher_writes_field()
    print("All vision-score tests passed.")
