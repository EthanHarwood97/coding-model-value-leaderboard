# Condensed View + UI/Vision Scores — Design Spec

**Date:** 2026-07-09
**Status:** Approved

## Problem

The leaderboard now has 21 columns, which is overwhelming. Users want a "quick view"
showing only the most important comparison metrics. Additionally, the leaderboard
tracks Coding Quality but not two other dimensions users care about for model
selection:

- **UI / Frontend quality** — how good a model is at generating beautiful UIs
  (partially addressed by `frontend_tier` + `design2code_score`, but not as a
  single comparable number)
- **Vision / multimodal quality** — how well a model understands images, charts,
  and visual input (needed for Design2Code, screenshots, document understanding)

## Goals

1. Add a **Condensed View toggle** that shows a 10-column "quick compare" table.
2. Add a computed **UI Score** (0–100) derived from `frontend_tier`.
3. Add a **Vision Score** (0–100) backed by MMMU-Pro, with an automated scraper.
4. Keep both views sharing the same filters, sorting, and data.

## Non-Goals

- No new backend / build step (static site stays static).
- No changes to the existing Full view column set.
- No LLM-as-judge or screenshot-based evaluation (out of scope for now).

---

## Section 1: Condensed View Toggle

A toggle button placed above the table (in or near the Filters section heading)
switches between two render modes:

| Mode | Columns shown | Default |
|------|---------------|---------|
| **Full** | All 21 existing columns | Yes |
| **Condensed** | 10 selected columns (see Section 2) | No |

**Behavior:**
- The toggle persists in `localStorage` key `view-mode` (`"full"` | `"condensed"`).
- Filters, sorting, and search apply identically in both modes.
- Switching mode re-renders only the `<tbody>` (and optionally the sort `<select>`
  options). No data reload.
- Button label reflects the *action*: when in Full mode it reads "Condensed view",
  when in Condensed it reads "Full view".

**Implementation note:** Rendering is driven by a `COLUMNS` config object that
declares which columns belong to each view. `rowHtml(m, columns)` iterates the
config instead of hardcoding 21 `<td>`s. This avoids maintaining two table builders.

---

## Section 2: Condensed View Columns

| # | Header | Field | Sortable | Direction |
|---|--------|-------|----------|-----------|
| 1 | Model | `name` | Yes | alpha |
| 2 | Provider | `provider` | Yes | alpha |
| 3 | Quality | `coding_quality_score` | Yes | DESC |
| 4 | UI | `ui_score` (computed) | Yes | DESC |
| 5 | Vision | `vision_score` (new field) | Yes | DESC |
| 6 | Out $/1M | `pricing.output_per_1m` | Yes | ASC |
| 7 | Speed | `speed_tok_s` | Yes | DESC |
| 8 | Released | `released` | Yes | DESC (newest) |
| 9 | License | `open_weight` | Yes | — |
| 10 | Context | `context_window` | Yes | DESC |

The sort `<select>` dropdown keeps all options; options whose column is not in the
active view are simply hidden via `display:none` when in Condensed mode (or left
visible but harmless). Decision: hide non-visible options to avoid confusion.

---

## Section 3: UI Score (computed)

A new field `ui_score` (float 0–100, `null` if no tier) is computed in
`enrichModels()` from `frontend_tier`:

| `frontend_tier` | `ui_score` |
|-----------------|------------|
| `S` | 95 |
| `A` | 82 |
| `B` | 68 |
| `C` | 50 |
| `null` | `null` |

**Rationale:** Tier-based mapping keeps coverage across all 70 tiered models
without depending on the sparse Design2Code scores (only 1 model has one). The
score is *curated*, not benchmark-derived — the methodology section must state this
explicitly so users don't mistake it for a raw benchmark.

`ui_score` is **not** written to `models.json` (it's derived at render time, like
`coding_quality_score` which is already computed in `enrichModels()`). It lives on
the in-memory model object only.

---

## Section 4: Vision Score (new field + scraper)

New field `vision_score` (float 0–100, `null` if unavailable) added to each model
in `models.json`. Backed by **MMMU-Pro** (BenchLM.ai), chosen because:
- It's the harder, more discriminative multimodal benchmark (good separation at frontier).
- 31 models already tracked (July 2026), enough for meaningful coverage.
- Same source the existing `fetch_benchlm_swe_bench()` scraper already uses, so the
  scraping pattern is proven.

### Scraper

New function `fetch_benchlm_mmmu_pro()` in `live_benchmarks.py`:
1. Fetches `https://benchlm.ai/benchmarks/mmmuPro`
2. Extracts embedded JSON leaderboard (same technique as `fetch_benchlm_swe_bench`)
3. Returns `dict[model_name -> score]` (0–100)
4. Matched to local models via existing `match_live_scores()` helper

Wired into `update.py` so the daily GitHub Action populates `vision_score`
automatically (alongside the other BenchLM/SWE-bench fields).

### Initial seed (manual)

Because the scraper runs in CI but local/dev runs need data immediately, seed
`vision_score` for the ~31 known MMMU-Pro models from the BenchLM leaderboard
(July 4, 2026 snapshot). Examples:

| Model | Vision Score |
|-------|--------------|
| GPT-5.4 Pro | 94 |
| Claude Mythos 5 | 92.7 |
| Claude Fable 5 | 92.7 |
| Gemini 3.1 Pro | 83.9 |
| Gemini 3.5 Flash | 83.6 |
| GPT-5.4 | 81.2 |
| GPT-5.5 | 81.2 |
| Gemini 3 Pro | 81 |
| GPT-5.2 | 79.5 |
| Kimi K2.6 | 79.4 |
| Qwen3.7 Plus | 79 |
| Qwen3.5 397B | 79 |
| Qwen3.6 Plus | 78.8 |
| Kimi K2.5 | 78.5 |
| MiniMax M3 | 78.1 |
| Grok 4.3 | 78.1 |
| MiMo-V2.5 | 77.9 |
| Claude Opus 4.6 | 77.3 |
| Gemma 4 31B | 76.9 |
| GPT-5.4 mini | 76.6 |
| … | … |

Models without MMMU-Pro data → `vision_score: null`.

---

## Section 5: UI / Frontend Changes

### index.html
- Add `<button id="view-toggle">Condensed view</button>` near the Filters heading.
- No new table markup needed — the `<thead>`/`<tbody>` are rendered from the
  `COLUMNS` config in JS (refactor required, see Section 6).

### app.js
- Add `COLUMNS = { full: [...], condensed: [...] }` config listing column defs
  (key, header, sortable, tooltip, render fn).
- Refactor `rowHtml(m)` → `rowHtml(m, columns)` iterating the config.
- Refactor `render()` to pass the active column set.
- Add `getActiveColumns()` returning `COLUMNS[STATE.viewMode]`.
- Add `STATE.viewMode` (`"full"` | `"condensed"`), default `"full"`.
- Bind `#view-toggle` click → flip `STATE.viewMode`, persist to `localStorage`,
  re-render + update button label + update sort `<select>` visible options.
- On `DOMContentLoaded`, restore `viewMode` from `localStorage`.
- Add `ui_score` computation in `enrichModels()`.
- Add `ui_score` and `vision_score` to `getSortValue()`.
- Update `updateSortIndicators()` sortable list.
- Update methodology `<details>` with UI Score + Vision Score blurbs.

### style.css
- Style `#view-toggle` to match existing button aesthetic (theme-aware).
- Optional: subtle "condensed" badge on the table when active.

---

## Section 6: Refactor Notes (important)

Currently `index.html` hardcodes the `<thead>` and `app.js` hardcodes `rowHtml()`.
To support two column sets cleanly, both the header and rows must become
data-driven from the `COLUMNS` config. This is a moderate refactor of `app.js`
(`render`, `rowHtml`, `getSortValue`, `updateSortIndicators`) and a small change
to `index.html` (remove hardcoded `<thead>`, let JS build it). The Full view must
remain visually identical to today after the refactor.

Risk: the table header click-to-sort handlers currently bind to `th[data-sort]`.
After refactor, headers are built in JS, so bind there. Behavior unchanged.

---

## Section 7: Data Sourcing Summary

| Field | Source | Coverage | Automated? |
|-------|--------|----------|------------|
| `ui_score` | derived from `frontend_tier` | 70 models | N/A (computed) |
| `vision_score` | MMMU-Pro (BenchLM.ai) | ~31 models | Yes (`fetch_benchlm_mmmu_pro`) |

---

## Testing

1. `python -m http.server` → load page.
2. Default = Full view, all 21 columns, identical to current.
3. Click "Condensed view" → 10 columns, Vision + UI scores visible.
4. Toggle persists across reload.
5. Sort by UI / Vision in condensed view works; nulls sort last.
6. Filters (price, frontend tier, license) work in both views.
7. `python scripts/update.py --check-only` runs without error; `vision_score`
   populated for seeded models.
8. `python -c "import json; json.load(open('data/models.json'))"` valid.

## Rollout

1. Commit spec.
2. Implement refactor + condensed view + UI score.
3. Add `fetch_benchlm_mmmu_pro` + seed `vision_score`.
4. Manual test locally.
5. Commit, push to `main` → GitHub Pages deploys.
6. Next scheduled Action run auto-refreshes `vision_score` from BenchLM.
