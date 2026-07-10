#!/usr/bin/env python3
"""Seed vision_score (MMMU-Pro) for known models into models.json.

Re-runnable: only sets the field when currently null. Run after the daily
auto-update; the scraper (fetch_benchlm_mmmu_pro) will overwrite from live data.
"""
import json
from pathlib import Path

from live_benchmarks import match_live_scores_top_level

DATA_FILE = Path(__file__).parent.parent / "data" / "models.json"

# MMMU-Pro scores (BenchLM.ai, 2026-07-04 snapshot). name -> score (0-100).
VISION_SEED = {
    "GPT-5.4 Pro": 94.0,
    "Claude Mythos 5": 92.7,
    "Claude Fable 5": 92.7,
    "Gemini 3.1 Pro": 83.9,
    "Google: Gemini 3.1 Pro Preview": 83.9,
    "Gemini 3.5 Flash": 83.6,
    "GPT-5.4": 81.2,
    "OpenAI: GPT-5.4": 81.2,
    "GPT-5.5": 81.2,
    "Gemini 3 Pro": 81.0,
    "GPT-5.2": 79.5,
    "OpenAI: GPT-5.2": 79.5,
    "Kimi K2.6": 79.4,
    "MoonshotAI: Kimi K2.6": 79.4,
    "Qwen3.7 Plus": 79.0,
    "Qwen: Qwen3.7 Plus": 79.0,
    "Qwen3.5 397B": 79.0,
    "Qwen: Qwen3.5 397B A17B": 79.0,
    "Qwen3.6 Plus": 78.8,
    "Qwen: Qwen3.6 Plus": 78.8,
    "Kimi K2.5": 78.5,
    "MoonshotAI: Kimi K2.5": 78.5,
    "MiniMax M3": 78.1,
    "Grok 4.3": 78.1,
    "MiMo-VII.5": 77.9,
    "Xiaomi: MiMo-VII.5-Pro": 77.9,
    "Claude Opus 4.6": 77.3,
    "Anthropic: Claude Opus 4.6": 77.3,
    "Gemma 4 31B": 76.9,
    "GPT-5.4 mini": 76.6,
    "OpenAI: GPT-5.4 Nano": 76.6,
}


def main():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    matched = match_live_scores_top_level(
        data["models"], VISION_SEED, "vision_score"
    )
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Seeded vision_score for {matched} models.")


if __name__ == "__main__":
    main()
