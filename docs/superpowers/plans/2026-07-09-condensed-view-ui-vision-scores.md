# Condensed View + UI/Vision Scores — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Condensed view" toggle that renders a 10-column quick-compare table, a computed UI Score (0–100) from `frontend_tier`, and a Vision Score (0–100) backed by MMMU-Pro via an automated BenchLM.ai scraper.

**Architecture:** The table becomes data-driven via a `COLUMNS` config object in `app.js` so both Full and Condensed views render from the same `rowHtml`/`buildHeader` functions. UI Score is computed at load time in `enrichModels()`; Vision Score is a top-level field seeded manually then refreshed by a new `fetch_benchlm_mmmu_pro()` scraper wired into `update.py`.

**Tech Stack:** Static HTML/CSS/JS (no build step), Python 3 + `requests` for scrapers.

## Global Constraints

- Site must remain a pure static site (no build step, no new runtime dependencies in the browser).
- `vision_score` is a **top-level** field on each model (mirrors `frontend_tier`/`design2code_score` precedent), `null` when unavailable.
- `ui_score` is **computed at render time** in `enrichModels()` and is **never** written to `models.json`.
- The Full view must look identical to today after the refactor (same 21 columns, same order, same sort behaviour).
- View mode persists in `localStorage` key `view-mode` (`"full"` | `"condensed"`).
- Follow existing patterns: benchmarks scraped via `fetch_benchlm_*` + `match_live_scores*` in `live_benchmarks.py`, wired in `update.py`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `scripts/live_benchmarks.py` | Add `fetch_benchlm_mmmu_pro()` and `match_live_scores_top_level()`. |
| `scripts/seed_vision_scores.py` | Seed `vision_score` for the ~31 known MMMU-Pro models (re-runnable). |
| `scripts/update.py` | Import + call the new scraper so the daily Action populates `vision_score`. |
| `tests/fixtures/benchlm_mmmu_pro.html` | Saved HTML fixture for the scraper test. |
| `tests/test_vision_score.py` | Fixture-based test for scraper + top-level matcher (runnable with `python`). |
| `app.js` | `COLUMNS` config, `buildHeader()`, refactored `render()`/`rowHtml()`, `ui_score` in `enrichModels()`, `getSortValue()` + `updateSortIndicators()` additions, view toggle + `localStorage`. |
| `index.html` | Remove hardcoded `<thead>`, add `#view-toggle` button, add methodology blurbs. |
| `style.css` | Style `#view-toggle`. |

---

### Task 1: Vision Score scraper + top-level matcher

**Files:**
- Modify: `scripts/live_benchmarks.py` (after `fetch_benchlm_swe_bench`, ~line 118)
- Create: `tests/fixtures/benchlm_mmmu_pro.html`
- Create: `tests/test_vision_score.py`

**Interfaces:**
- Produces: `fetch_benchlm_mmmu_pro() -> dict[str, float]` (model_name → 0–100 score)
- Produces: `match_live_scores_top_level(models, scores, key, log_fn=None) -> int`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vision_score.py`:

```python
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
    # Monkeypatch _fetch_text by injecting the fixture into the module's cache.
    import live_benchmarks
    live_benchmarks._fetch_text = lambda url: html
    return html


def test_scraper_parses_scores():
    _load_fixture()
    scores = fetch_benchlm_mmmu_pro()
    assert len(scores) >= 3, f"expected several scores, got {len(scores)}"
    # GPT-5.4 Pro is the known leader at 94
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
```

- [ ] **Step 2: Create the HTML fixture**

Create `tests/fixtures/benchlm_mmmu_pro.html` with a representative BenchLM.ai MMMU-Pro page fragment (mirrors the embedded-JSON structure used by `fetch_benchlm_swe_bench`). Include at least these rows so the test passes:

```html
<html><body>
<script>__next_f.push(["benchmarkData", "{\"rows\":["
  + "{\"model\":\"GPT-5.4 Pro\",\"score\":94},"
  + "{\"model\":\"Claude Mythos 5\",\"score\":92.7},"
  + "{\"model\":\"Gemini 3.1 Pro\",\"score\":83.9},"
  + "{\"model\":\"GPT-5.4\",\"score\":81.2}"
  + "]}"]) </script>
</body></html>
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python tests/test_vision_score.py`
Expected: `ModuleNotFoundError` / `AttributeError: fetch_benchlm_mmmu_pro` (function not defined yet).

- [ ] **Step 4: Implement the scraper + matcher**

Append to `scripts/live_benchmarks.py` (after `fetch_benchlm_swe_bench`, before the tbench section at line 120):

```python
# ── Source 1b: BenchLM.ai — MMMU-Pro (vision/multimodal) ────────────────

def fetch_benchlm_mmmu_pro() -> dict[str, float]:
    """Scrape MMMU-Pro (vision) scores from BenchLM.ai.

    Same embedded-JSON strategy as fetch_benchlm_swe_bench. MMMU-Pro is the
    harder multimodal benchmark; scores are 0–100.

    Returns dict of model_name → score (0-100).
    """
    print("[INFO] Fetching BenchLM.ai MMMU-Pro scores ...")
    html = _fetch_text("https://benchlm.ai/benchmarks/mmmuPro")
    if not html:
        print("[WARN] Failed to fetch BenchLM MMMU-Pro page")
        return {}

    scores = {}

    # Strategy 1: embedded JSON ("model":"Name","score":94)
    json_pattern = re.compile(
        r'"model"\s*:\s*"([^"]+)".*?"score"\s*:\s*([\d.]+)',
        re.DOTALL
    )
    for m in json_pattern.finditer(html):
        name = m.group(1)
        try:
            score = float(m.group(2))
            if 0 < score <= 100 and name not in scores:
                scores[name] = score
        except ValueError:
            continue

    # Strategy 2: escaped __next_f variant  \"model\":\"Name\",\"score\":94
    if len(scores) < 10:
        esc_pattern = re.compile(
            r'\\"model\\"\\s*:\\s*\\"([^\\"]+)\\".*?\\"score\\"\\s*:\\s*([\d.]+)',
            re.DOTALL
        )
        for m in esc_pattern.finditer(html):
            name = m.group(1)
            try:
                score = float(m.group(2))
                if 0 < score <= 100 and name not in scores:
                    scores[name] = score
            except ValueError:
                continue

    print(f"[INFO] Found {len(scores)} MMMU-Pro model scores on BenchLM.ai")
    return scores


def match_live_scores_top_level(
    models: list[dict],
    scores: dict[str, float],
    key: str,
    log_fn=None,
) -> int:
    """Match scraped scores to a TOP-LEVEL model field (e.g. vision_score).

    Mirrors match_live_scores but writes model[key] instead of
    model["benchmarks"][key]. Returns count of newly matched models.
    """
    matched = 0
    for model in models:
        name = model.get("name", "")
        if not name:
            continue
        if model.get(key) is not None:
            continue
        stripped = _strip_provider(name)
        candidates = [_norm(name), _norm(stripped)]
        found = False
        for scraped_name, score in scores.items():
            scraped_norm = _norm(scraped_name)
            if scraped_norm in candidates:
                model[key] = round(score, 1)
                matched += 1
                if log_fn:
                    log_fn(f"  {key}: {name} = {score} (live exact)")
                found = True
                break
            if not found:
                for c in candidates:
                    if len(c) > 10 and len(scraped_norm) > 10:
                        shorter = min(len(c), len(scraped_norm))
                        longer = max(len(c), len(scraped_norm))
                        if shorter / longer > 0.6:
                            if c in scraped_norm or scraped_norm in c:
                                model[key] = round(score, 1)
                                matched += 1
                                if log_fn:
                                    log_fn(f"  {key}: {name} = {score} (live fuzzy)")
                                found = True
                                break
            if found:
                break
    return matched
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python tests/test_vision_score.py`
Expected: `All vision-score tests passed.`

- [ ] **Step 6: Commit**

```bash
git add scripts/live_benchmarks.py tests/fixtures/benchlm_mmmu_pro.html tests/test_vision_score.py
git commit -m "feat: add MMMU-Pro vision scraper + top-level matcher"
```

---

### Task 2: Seed vision_score into models.json

**Files:**
- Create: `scripts/seed_vision_scores.py`
- Modify: `data/models.json` (via the script)

**Interfaces:**
- Consumes: `match_live_scores_top_level` (Task 1)
- Produces: `data/models.json` with `vision_score` populated for ~31 models

- [ ] **Step 1: Write the seed script**

Create `scripts/seed_vision_scores.py`:

```python
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
    "MiMo-V2.5": 77.9,
    "Xiaomi: MiMo-V2.5-Pro": 77.9,
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
```

- [ ] **Step 2: Run the seed script**

Run: `python scripts/seed_vision_scores.py`
Expected: `Seeded vision_score for NN models.` (NN ≥ 20)

- [ ] **Step 3: Verify the data file is valid JSON and field is present**

Run: `python -c "import json; d=json.load(open('data/models.json')); print([(m['name'], m.get('vision_score')) for m in d['models'] if m.get('vision_score') is not None][:5])"`
Expected: prints a list of (name, score) tuples, e.g. `('GPT-5.4 Pro', 94.0), ...`

- [ ] **Step 4: Commit**

```bash
git add data/models.json scripts/seed_vision_scores.py
git commit -m "feat: seed vision_score (MMMU-Pro) for known models"
```

---

### Task 3: Wire scraper into update.py

**Files:**
- Modify: `scripts/update.py:49-52` (imports) and `scripts/update.py:638-646` (scraper calls)

**Interfaces:**
- Consumes: `fetch_benchlm_mmmu_pro`, `match_live_scores_top_level` (Task 1)

- [ ] **Step 1: Add imports**

In `scripts/update.py`, extend the import block (lines 49–52):

```python
from live_benchmarks import (
    fetch_benchlm_swe_bench,
    fetch_benchlm_mmmu_pro,
    fetch_tbench_scores,
    fetch_whatllm_scores,
    match_live_scores,
    match_live_scores_top_level,
)
```

- [ ] **Step 2: Call the scraper after the whatllm block**

After line 646 (`log(f"WhatLLM multi-benchmark: matched {wl_matched} fields")`), add:

```python
        # BenchLM.ai — MMMU-Pro (vision/multimodal)
        mmmu_scores = fetch_benchlm_mmmu_pro()
        if mmmu_scores:
            vs_matched = match_live_scores_top_level(
                data.get("models", []), mmmu_scores, "vision_score", log_fn=log
            )
            log(f"MMMU-Pro Vision: matched {vs_matched} models")
```

- [ ] **Step 3: Verify update.py imports cleanly**

Run: `python -c "import sys; sys.path.insert(0,'scripts'); import update; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: Commit**

```bash
git add scripts/update.py
git commit -m "feat: wire MMMU-Pro vision scraper into update.py"
```

---

### Task 4: app.js — data-driven columns + UI Score + view toggle

**Files:**
- Modify: `app.js` (multiple sections)

**Interfaces:**
- Consumes: `m.ui_score` (computed here), `m.vision_score` (top-level, Task 2), `m.frontend_tier` (existing)
- Produces: `COLUMNS` config, `buildHeader()`, refactored `render()`/`rowHtml()`, `getActiveColumns()`, view toggle handlers

- [ ] **Step 1: Add `viewMode` to STATE and `COLUMNS` config**

In the `STATE` object (top of IIFE), add `viewMode: 'full'`. Then, after the `NORM_RANGES` block (around line 40), add the column config:

```js
  STATE.viewMode = 'full'; // 'full' | 'condensed'

  // Column definitions drive both the header and rows.
  // render(m) returns the INNER html of the <td>. cellClass adds a <td> class.
  const COLUMNS = {
    full: [
      { key: 'name', label: 'Model', sort: 'name',
        render: m => {
          const tagClass = m.tag ? `tag-${m.tag.toLowerCase().replace(/\s+/g, '-')}` : 'tag-default';
          return `${escapeHtml(m.name)}${m.tag ? `<br><span class="tag ${tagClass}">${escapeHtml(m.tag)}</span>` : ''}`;
        } },
      { key: 'provider', label: 'Provider', sort: 'provider', render: m => escapeHtml(m.provider) },
      { key: 'output_price', label: 'Out $/1M', sort: 'output_price', cellClass: 'price',
        render: m => `$${fmt(m.pricing?.output_per_1m, 2)}` },
      { key: 'coding_quality', label: 'Quality', sort: 'coding_quality', cellClass: 'quality-score',
        render: m => m.coding_quality_score != null ? m.coding_quality_score.toFixed(0) : '<span class="null-val">—</span>' },
      { key: 'swe_bench_pro', label: 'SWE-Pro', sort: 'swe_bench_pro', render: m => pct(m.benchmarks?.swe_bench_pro) },
      { key: 'aider_polyglot', label: 'Aider', sort: 'aider_polyglot', render: m => pct(m.benchmarks?.aider_polyglot) },
      { key: 'livecodebench', label: 'LCB', sort: 'livecodebench', render: m => pct(m.benchmarks?.livecodebench) },
      { key: 'aa_coding_index', label: 'AA Code', sort: 'aa_coding_index',
        render: m => m.benchmarks?.aa_coding_index != null ? m.benchmarks.aa_coding_index.toFixed(0) : '<span class="null-val">—</span>' },
      { key: 'livebench', label: 'LiveBench', sort: 'livebench',
        render: m => m.benchmarks?.livebench != null ? m.benchmarks.livebench.toFixed(1) + '%' : '<span class="null-val">—</span>' },
      { key: 'swe_bench_verified', label: 'SWE-Ver', sort: 'swe_bench_verified', render: m => pct(m.benchmarks?.swe_bench_verified) },
      { key: 'terminal_bench', label: 'Term-Bench', sort: 'terminal_bench', render: m => pct(m.benchmarks?.terminal_bench_2_1) },
      { key: 'scicode', label: 'SciCode', sort: 'scicode', render: m => pct(m.benchmarks?.scicode) },
      { key: 'cost_per_quality', label: '$/Qual', sort: 'cost_per_quality', cellClass: 'cost-per-point',
        render: m => m.cost_per_quality != null ? '$' + m.cost_per_quality.toFixed(2) : '<span class="null-val">—</span>' },
      { key: 'cost_per_pro_point', label: '$/Pro Pt', sort: 'cost_per_pro_point', cellClass: 'cost-per-point',
        render: m => m.cost_per_pro_point != null ? '$' + m.cost_per_pro_point.toFixed(2) : '<span class="null-val">—</span>' },
      { key: 'reasoning', label: 'Reasoning', sort: 'reasoning', cellClass: 'reasoning-cell', render: m => renderReasoning(m.reasoning_level) },
      { key: 'context_window', label: 'Context', sort: 'context_window', render: m => m.context_window ? formatContext(m.context_window) : '<span class="null-val">—</span>' },
      { key: 'speed', label: 'Speed', sort: 'speed', render: m => m.speed_tok_s ? m.speed_tok_s + ' tok/s' : '<span class="null-val">—</span>' },
      { key: 'license', label: 'License', sort: 'license',
        cellClass: m => m.open_weight ? 'license-open' : 'license-proprietary',
        render: m => m.open_weight ? '✓ Open' : 'Proprietary' },
      { key: 'frontend_tier', label: 'FE Tier', sort: 'frontend_tier', cellClass: 'frontend-tier-cell', render: m => renderFrontendTier(m.frontend_tier) },
      { key: 'design2code', label: 'D2C', sort: 'design2code', render: m => m.design2code_score != null ? m.design2code_score.toFixed(3) : '<span class="null-val">—</span>' },
      { key: 'best_for', label: 'Best For', sort: null, cellClass: 'best-for', render: m => escapeHtml(m.best_for || '—') },
    ],
    condensed: [
      { key: 'name', label: 'Model', sort: 'name',
        render: m => {
          const tagClass = m.tag ? `tag-${m.tag.toLowerCase().replace(/\s+/g, '-')}` : 'tag-default';
          return `${escapeHtml(m.name)}${m.tag ? `<br><span class="tag ${tagClass}">${escapeHtml(m.tag)}</span>` : ''}`;
        } },
      { key: 'provider', label: 'Provider', sort: 'provider', render: m => escapeHtml(m.provider) },
      { key: 'coding_quality', label: 'Quality', sort: 'coding_quality', cellClass: 'quality-score',
        render: m => m.coding_quality_score != null ? m.coding_quality_score.toFixed(0) : '<span class="null-val">—</span>' },
      { key: 'ui_score', label: 'UI', sort: 'ui_score', cellClass: 'quality-score',
        render: m => m.ui_score != null ? m.ui_score.toFixed(0) : '<span class="null-val">—</span>' },
      { key: 'vision_score', label: 'Vision', sort: 'vision_score', cellClass: 'quality-score',
        render: m => m.vision_score != null ? m.vision_score.toFixed(1) : '<span class="null-val">—</span>' },
      { key: 'output_price', label: 'Out $/1M', sort: 'output_price', cellClass: 'price',
        render: m => `$${fmt(m.pricing?.output_per_1m, 2)}` },
      { key: 'speed', label: 'Speed', sort: 'speed', render: m => m.speed_tok_s ? m.speed_tok_s + ' tok/s' : '<span class="null-val">—</span>' },
      { key: 'released', label: 'Released', sort: 'released', render: m => escapeHtml(m.released || '—') },
      { key: 'license', label: 'License', sort: 'license',
        cellClass: m => m.open_weight ? 'license-open' : 'license-proprietary',
        render: m => m.open_weight ? '✓ Open' : 'Proprietary' },
      { key: 'context_window', label: 'Context', sort: 'context_window', render: m => m.context_window ? formatContext(m.context_window) : '<span class="null-val">—</span>' },
    ],
  };

  function getActiveColumns() {
    return COLUMNS[STATE.viewMode] || COLUMNS.full;
  }
```

- [ ] **Step 2: Compute `ui_score` in `enrichModels()`**

Replace the `enrichModels` function (currently lines 127–145) with:

```js
  function enrichModels(models) {
    models.forEach(m => {
      m.benchmarks = m.benchmarks || {};

      // Coding Quality Score (blended composite)
      m.coding_quality_score = computeQualityScore(m);

      // UI Score (0-100) derived from curated frontend tier
      m.ui_score = computeUiScore(m);

      // Cost per quality point (output price / quality score)
      m.cost_per_quality = computeCostPerQuality(m);

      // Cost per SWE-bench Pro point (output price / pro score)
      if (m.pricing && m.benchmarks.swe_bench_pro != null) {
        m.cost_per_pro_point = +(m.pricing.output_per_1m / m.benchmarks.swe_bench_pro).toFixed(3);
      } else {
        m.cost_per_pro_point = null;
      }
    });
  }

  function computeUiScore(m) {
    const map = { S: 95, A: 82, B: 68, C: 50 };
    const tier = m.frontend_tier;
    return tier != null && map[tier] != null ? map[tier] : null;
  }
```

- [ ] **Step 3: Refactor `render()` and add `buildHeader()`**

Replace `render()` (lines 245–257) and `rowHtml()` (lines 259–290) with:

```js
  function render() {
    const filtered = sortModels(getFilteredModels());
    const columns = getActiveColumns();
    const tbody = document.getElementById('table-body');
    document.getElementById('visible-count').textContent = filtered.length;

    // (Re)build header for the active view
    buildHeader(columns);

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="${columns.length}" style="text-align:center;padding:2rem;color:var(--text-secondary)">No models match your filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(m => rowHtml(m, columns)).join('');
    updateSortIndicators();
  }

  function buildHeader(columns) {
    const thead = document.querySelector('#leaderboard thead tr');
    if (!thead) return;
    thead.innerHTML = columns.map(col =>
      `<th data-sort="${col.sort || ''}" title="${col.title || ''}">${col.label}</th>`
    ).join('');
    // Re-bind click-to-sort on the freshly built headers
    thead.querySelectorAll('th[data-sort]').forEach(th => {
      if (!th.dataset.sort) return;
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (STATE.sortBy === key) {
          STATE.sortDir = STATE.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          STATE.sortBy = key;
          STATE.sortDir = (key.includes('cost') || key.includes('price') || key === 'output_price') ? 'asc' : 'desc';
        }
        render();
      });
    });
  }

  function rowHtml(m, columns) {
    return `<tr>${columns.map(col => {
      const cls = typeof col.cellClass === 'function' ? col.cellClass(m) : (col.cellClass || '');
      return `<td class="${cls}">${col.render(m)}</td>`;
    }).join('')}</tr>`;
  }
```

- [ ] **Step 4: Add `ui_score` and `vision_score` to `getSortValue()`**

In `getSortValue()` (lines 225–243), add before the `released` case:

```js
    if (key === 'ui_score') return m.ui_score;
    if (key === 'vision_score') return m.vision_score;
```

- [ ] **Step 5: Update `updateSortIndicators()` sortable list**

In `updateSortIndicators()` (lines ~447–460), extend the `sortable` array to include `'ui_score', 'vision_score'` and `'provider'`:

```js
      const sortable = ['output_price', 'context_window', 'speed', 'reasoning', 'provider',
        'coding_quality', 'ui_score', 'vision_score', 'aider_polyglot', 'livecodebench', 'aa_coding_index',
        'livebench', 'cost_per_quality', 'cost_per_pro_point', 'swe_bench_pro',
        'swe_bench_verified', 'terminal_bench', 'scicode', 'released',
        'frontend_tier', 'design2code'];
```

- [ ] **Step 6: Add view-toggle handler + localStorage + header sync**

In `bindEvents()`, after the existing sort `<select>` handler, add:

```js
    // View toggle (Full / Condensed)
    const viewToggle = document.getElementById('view-toggle');
    if (viewToggle) {
      viewToggle.addEventListener('click', () => {
        STATE.viewMode = STATE.viewMode === 'full' ? 'condensed' : 'full';
        localStorage.setItem('view-mode', STATE.viewMode);
        viewToggle.textContent = STATE.viewMode === 'full' ? 'Condensed view' : 'Full view';
        syncSortOptions();
        // Reset sort if not available in the active view
        const cols = getActiveColumns();
        if (!cols.some(c => c.sort === STATE.sortBy)) {
          STATE.sortBy = 'coding_quality';
          STATE.sortDir = 'desc';
          document.getElementById('sort-by').value = 'coding_quality';
        }
        render();
      });
    }
```

Add a helper `syncSortOptions()` near `bindEvents`:

```js
  function syncSortOptions() {
    const cols = getActiveColumns();
    const sortSelect = document.getElementById('sort-by');
    if (!sortSelect) return;
    Array.from(sortSelect.options).forEach(opt => {
      opt.style.display = cols.some(c => c.sort === opt.value) ? '' : 'none';
    });
  }
```

- [ ] **Step 7: Restore viewMode on load + set initial button label**

In `init()` (lines 148–157), after `document.getElementById('total-count').textContent = STATE.models.length;`, add:

```js
    STATE.viewMode = localStorage.getItem('view-mode') || 'full';
    const vt = document.getElementById('view-toggle');
    if (vt) vt.textContent = STATE.viewMode === 'full' ? 'Condensed view' : 'Full view';
    syncSortOptions();
```

- [ ] **Step 8: Commit**

```bash
git add app.js
git commit -m "feat: data-driven columns, UI Score, condensed view toggle"
```

---

### Task 5: index.html — remove hardcoded thead, add toggle, methodology

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `#view-toggle` (Task 4), `COLUMNS`-driven `<thead>` (Task 4)
- Produces: button markup, empty `<thead><tr></tr></thead>`, methodology blurbs

- [ ] **Step 1: Add the view-toggle button**

In the Filters section, immediately after the `<h2>Filters</h2>` line (around line 41), add:

```html
      <div class="filter-actions">
        <button id="view-toggle" class="view-toggle-btn">Condensed view</button>
      </div>
```

- [ ] **Step 2: Empty the hardcoded table header**

Replace the entire `<thead>...</thead>` block (lines 117–139) with:

```html
            <thead>
              <tr></tr>
            </thead>
```

(The `<tr>` is filled by `buildHeader()` in Task 4.)

- [ ] **Step 3: Add methodology blurbs**

In the methodology `<details>` (after the Design2Code `<p>`), add:

```html
        <p><strong>UI Score</strong> is a curated 0–100 rating of frontend/UI generation quality, derived from the Frontend Tier: S=95, A=82, B=68, C=50. It is a practitioner-consensus mapping, not a raw benchmark — use it for quick comparison, not precise ranking.</p>

        <p><strong>Vision Score</strong> is the MMMU-Pro benchmark score (0–100): how well a model understands images, charts, diagrams, and documents. Sourced from <a href="https://benchlm.ai/benchmarks/mmmuPro" target="_blank" rel="noopener">BenchLM.ai</a>. Relevant for Design2Code, screenshot understanding, and document tasks.</p>
```

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: condensed-view toggle button, dynamic header, methodology blurbs"
```

---

### Task 6: style.css — view-toggle styling

**Files:**
- Modify: `style.css`

**Interfaces:**
- Consumes: `.view-toggle-btn`, `.filter-actions`

- [ ] **Step 1: Add styles**

After the `.filter-row` rule (or near the `.filter-group` styles), add:

```css
.filter-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.75rem;
}

.view-toggle-btn {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  transition: background-color 0.2s, border-color 0.2s;
}

.view-toggle-btn:hover {
  background: var(--border);
  border-color: var(--border-hover);
}
```

- [ ] **Step 2: Commit**

```bash
git add style.css
git commit -m "style: condensed-view toggle button"
```

---

### Task 7: Manual test + validate + push

**Files:** none (verification only)

- [ ] **Step 1: Validate data JSON**

Run: `python -c "import json; json.load(open('data/models.json')); print('JSON ok')"`
Expected: `JSON ok`

- [ ] **Step 2: Run scraper unit test**

Run: `python tests/test_vision_score.py`
Expected: `All vision-score tests passed.`

- [ ] **Step 3: Run update.py in check-only mode**

Run: `python scripts/update.py --check-only`
Expected: runs without error, logs `MMMU-Pro Vision: matched N models`.

- [ ] **Step 4: Serve locally and verify in browser**

Run: `python -m http.server 8000` (background), open `http://localhost:8000`.
Verify:
  - Default = Full view, all 21 columns present and ordered as before.
  - Click "Condensed view" → 10 columns: Model, Provider, Quality, UI, Vision, Out $/1M, Speed, Released, License, Context.
  - UI column shows 95/82/68/50 per tier; nulls show "—".
  - Vision column shows seeded scores (e.g. GPT-5.4 Pro = 94.0); nulls show "—".
  - Sort by UI and Vision works (nulls last).
  - Reload page → view mode persists (localStorage).
  - Frontend Tier filter + price filter work in both views.
  - Sort dropdown hides options not in the active view.

- [ ] **Step 5: Commit any stray changes and push**

```bash
git add -A
git commit -m "chore: post-review tweaks" || echo "nothing to commit"
git push origin main
```

Expected: push succeeds; GitHub Pages rebuilds (~1–2 min).

---

## Self-Review Notes

- **Spec coverage:** Condensed toggle (Task 4/5), UI Score (Task 4), Vision Score field+scraper (Task 1/2/3), Full-view parity (Task 4 Step 1/3), localStorage persistence (Task 4 Step 7), methodology (Task 5). All covered.
- **Type consistency:** `vision_score` is top-level (`m.vision_score`) in both the seed (Task 2), `match_live_scores_top_level` (Task 1), `getSortValue` (Task 4), and column render (Task 4). `ui_score` is computed in `enrichModels` (Task 4) and read as `m.ui_score` everywhere. No name drift.
- **No placeholders:** Every step has concrete code or commands.
