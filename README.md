# 💸 Coding Model Value Leaderboard

A community-maintained leaderboard that ranks LLMs for **coding agents** by **quality-per-dollar** — no remortgage required.

## Why This Exists

Most leaderboards either:
- Rank by raw benchmark score (favoring expensive frontier models), or
- Rank by chat-quality benchmarks (irrelevant for coding agents)

This leaderboard follows the **research consensus** on which LLM leaderboards are most trustworthy — blending **multiple high-signal sources** rather than relying on any single benchmark. See [the research](https://github.com/EthanHarwood97/coding-model-value-leaderboard/issues/1) for how we selected our sources.

**Trust tier approach** (based on independent analysis):
1. **Tier 1 (most trusted):** Arena AI (human preference ELO) + Artificial Analysis (benchmark composite)
2. **Tier 2 (coding-specific):** Aider Polyglot (multi-language code editing), SWE-bench (agentic coding), LiveBench (contamination-free)
3. **Tier 3 (avoid):** Vendor cherry-picked charts, single-benchmark boards (MMLU alone is saturated), Reddit polls

## Features

- **30+ models** tracked with multi-benchmark coverage
- **Coding Quality Score** (0–100): weighted blend of SWE-bench Pro (40%), Aider Polyglot (35%), LiveCodeBench (25%)
- **$/Quality Point**: output price ÷ Coding Quality Score (lower = better value) — the most holistic value metric
- **Aider Polyglot** scores: gold standard for coding-specific LLM evaluation (225 real Exercism exercises across 6 languages)
- **AA Coding Index**: Artificial Analysis composite intelligence score
- **SWE-bench Pro / Verified**: real GitHub issue resolution benchmarks
- **Terminal-Bench 2.1**: agentic CLI performance
- **Filters**: max price, min benchmark score, min context window, license type
- **Sortable** columns by any metric
- **Scatter plot**: price vs Coding Quality Score, bubble size = context window
- **Daily auto-updates** via GitHub Actions
- **Dark / light mode**
- **Mobile-friendly**

## Quick Links

- 🌐 **Live site**: https://EthanHarwood97.github.io/coding-model-value-leaderboard/
- 📊 **Data file**: [`data/models.json`](data/models.json)
- 🔄 **Auto-updates**: `.github/workflows/update.yml`

## How Rankings Work

### Coding Quality Score (Composite)

The **Coding Quality Score** blends six coding-specific benchmarks into a single 0–100 score:

| Weight | Benchmark | Coverage | What It Measures |
|--------|-----------|----------|-----------------|
| **30%** | **SWE-bench Pro** | 8% | Harder GitHub issues, multi-file fixes, no hinting |
| **25%** | **Aider Polyglot** | 8% | 225 Exercism exercises across Python, Go, Rust, JS, C++, Java |
| **20%** | **SWE-bench Verified** | 51% | Human-validated GitHub issue resolution |
| **10%** | **LiveBench** | 27% | Contamination-free global average across math, reasoning, coding |
| **10%** | **Terminal-Bench 2.1** | 9% | Agentic CLI performance |
| **5%** | **SciCode** | 5% | Scientific coding across 16 disciplines |

Each benchmark is normalized to 0–100 using calibration anchors. Models with any single benchmark get a score; more benchmarks = higher confidence.

### Other Metrics

| Metric | What It Measures |
|--------|-----------------|
| **AA Coding Index** | Artificial Analysis composite (MMLU-Pro, GPQA Diamond, MATH-500, HumanEval) |
| **LiveCodeBench** | Competitive programming, contamination-resistant |
| **$/Quality Point** | Output price ÷ Coding Quality Score. Lower = better value |
| **$/Pro Point** | Output price ÷ SWE-bench Pro score. Lower = better value |
| **Context** | Max input tokens |
| **Speed** | Tokens/sec |

### Source Selection (Research-Backed)

This leaderboard's benchmark selection follows independent analysis of the LLM leaderboard ecosystem (May 2026):

- **Trusted for general quality**: Arena AI (human preference ELO) + Artificial Analysis (benchmark composite)
- **Trusted for coding**: Aider Polyglot (gold standard for code editing), SWE-bench (agentic coding), LiveBench (contamination-free)
- **Avoided**: Vendor cherry-picked charts, single-benchmark boards (saturated MMLU), Reddit polls

## Current Value Winner (as of June 2026)

**DeepSeek V4 Pro** — Quality Score ~64, $0.87/1M output ($0.014 per quality point)

| Tier | Pick |
|------|------|
| 🏆 Best value | DeepSeek V4 Pro |
| 💪 Quality sweet spot | MiniMax M3 |
| 🚀 Long-horizon | GLM-5.2 |
| 🔓 Closed daily driver | Gemini 3.1 Pro or Claude Sonnet 4.6 |
| 🆓 Free tier | Gemini 3.1 Flash-Lite |

## Local Development

```bash
# Clone
git clone https://github.com/EthanHarwood97/coding-model-value-leaderboard
cd coding-model-value-leaderboard

# Serve locally (Python 3)
python -m http.server 8000

# Open http://localhost:8000
```

The site is pure static HTML/CSS/JS — no build step, no dependencies (Chart.js loads from CDN).

## Updating Data

### Automatic (daily)
The GitHub Action in `.github/workflows/update.yml` runs daily at 06:00 UTC. It pulls real-time data from:

- **[OpenRouter `/api/v1/models`](https://openrouter.ai/api/v1/models)** — current pricing, context windows, `aa_coding_index` benchmarks for 300+ models
- **[Aider LLM Leaderboard](https://aider.chat/docs/leaderboards/)** — Aider Polyglot coding scores (225 Exercism exercises, 6 languages)
- **[HuggingFace API](https://huggingface.co/api/models)** — discovers new coding model releases
- **HuggingFace model READMEs** — extracts SWE-bench scores from official model cards
- **[BenchLM.ai](https://benchlm.ai)** — SWE-bench Verified scores for 55+ models (live scrape)
- **[tbench.ai](https://www.tbench.ai)** — Terminal-Bench 2.1 agentic CLI scores (live scrape)
- **[WhatLLM.org](https://whatllm.org)** — SciCode, Terminal-Bench, and LiveCodeBench scores (live scrape)

The scraper is conservative — it only updates fields with high confidence. New models are added with `null` benchmark fields until their scores can be verified.

### Manual

```bash
# Install dependencies
pip install requests

# Full refresh (OpenRouter + HuggingFace discovery)
python scripts/update.py

# Just check what would change (don't write to disk)
python scripts/update.py --check-only

# Discover only (find new models, don't refresh existing)
python scripts/update.py --discover
```

### Adding a New Model

Edit `data/models.json` and add an entry following the existing schema:

```json
{
  "name": "New Model Name",
  "provider": "Provider Name",
  "openrouter_id": "provider/model-id",
  "huggingface_id": "org/model-name",
  "released": "2026-01-15",
  "license": "MIT",
  "open_weight": true,
  "pricing": {
    "input_per_1m": 0.50,
    "output_per_1m": 1.50,
    "cache_hit_per_1m": 0.05,
    "currency": "USD"
  },
  "context_window": 128000,
  "max_output": 8192,
  "speed_tok_s": 50,
  "benchmarks": {
    "swe_bench_verified": 75.0,
    "swe_bench_pro": 45.0,
    "terminal_bench_2_1": null,
    "livecodebench": null,
    "humaneval": null,
    "aa_coding_index": null
  },
  "tag": "New Pick",
  "best_for": "What this model excels at",
  "sources": {
    "pricing": "https://provider.com/pricing",
    "benchmark": "https://huggingface.co/org/model"
  }
}
```

Then open a PR. The Action will run a sanity check on the data file.

## Deploying to GitHub Pages

1. Push this repo to GitHub
2. Settings → Pages → Source: `Deploy from a branch` → `main` / `(root)`
3. Wait ~2 minutes
4. Visit `https://your-username.github.io/coding-model-value-leaderboard/`

## Roadmap

- [ ] More models
- [ ] Arena AI ELO scores integration
- [ ] Provider-specific routing recommendations
- [ ] "Cascade strategy" preset (cheapest model for X% of tasks)
- [ ] Export as CSV / Markdown table
- [ ] RSS feed for price drops

## Contributing

PRs welcome. For new models, please include source URLs for both pricing and benchmark scores.

## Sources

Pricing data sourced from:
- [DeepSeek API Docs](https://api-docs.deepseek.com/quick_start/pricing)
- [Z.AI Blog](https://z.ai/blog)
- [Alibaba Qwen Cloud](https://www.qwencloud.com/models)
- [Moonshot Kimi Docs](https://www.kimi.com/code/docs/)
- [OpenRouter](https://openrouter.ai) (aggregator fallback)
- [Anthropic Pricing](https://www.anthropic.com/pricing)
- [OpenAI Pricing](https://openai.com/api/pricing/)
- [Google AI Pricing](https://ai.google.dev/pricing)

Benchmark data sourced from:
- [SWE-bench Verified Leaderboard](https://www.swebench.com/)
- [BenchLM.ai](https://benchlm.ai) — SWE-bench Verified aggregator (55+ models)
- [Aider Polyglot Coding Leaderboard](https://aider.chat/docs/leaderboards/) — gold standard for code editing
- [Artificial Analysis](https://artificialanalysis.ai) — broad benchmark composite, speed, latency
- [LiveBench](https://livebench.ai) — contamination-resistant, questions refresh monthly
- [Terminal-Bench](https://www.tbench.ai/) — agentic CLI performance
- [WhatLLM.org](https://whatllm.org) — multi-benchmark aggregator (SciCode, Terminal-Bench, LiveCodeBench)

## Disclaimer

Prices and benchmarks change. Verify on the provider's official docs before production use. Some benchmarks are self-reported by model providers.

## License

MIT — see `LICENSE`.