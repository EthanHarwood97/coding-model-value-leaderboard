"""
live_benchmarks.py — Live scrapers for coding benchmark leaderboards

Scrapes real-time benchmark data from:
1. BenchLM.ai — SWE-bench Verified (55+ models)
2. tbench.ai — Terminal-Bench 2.1 (agentic CLI)
3. whatllm.org — Multi-benchmark aggregator (SciCode, Terminal-Bench)

Each function returns a dict of model_name → score, matched against local
models using the same normalisation helpers as benchmark_snapshots.py.

Usage:
    from live_benchmarks import fetch_benchlm_swe_bench, fetch_tbench_scores, fetch_whatllm_scores
    swe_scores = fetch_benchlm_swe_bench()
    matched = match_live_scores(local_models, swe_scores, "swe_bench_verified", log_fn=log)
"""

import json
import re
import time
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

USER_AGENT = "coding-model-value-leaderboard/1.0 (+https://github.com/EthanHarwood97/coding-model-value-leaderboard)"
REQUEST_TIMEOUT = 30


# ── HTTP helpers ─────────────────────────────────────────────────────────

def _fetch_text(url: str) -> Optional[str]:
    """Fetch text content from URL with retries."""
    if requests is None:
        return None
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
                print(f"[WARN] Failed to fetch {url}: {e}")
    return None


# ── Name normalisation (mirrors benchmark_snapshots.py) ──────────────────

def _norm(s: str) -> str:
    """Lowercase, strip whitespace, remove all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", s.lower().strip())


def _strip_provider(model_name: str) -> str:
    """Remove leading 'Provider: ' prefix from OpenRouter-style names."""
    return re.sub(r"^[^:]+:\s*", "", model_name).strip()


# ── Source 1: BenchLM.ai — SWE-bench Verified ───────────────────────────

def fetch_benchlm_swe_bench() -> dict[str, float]:
    """Scrape SWE-bench Verified scores from BenchLM.ai.

    The page is a Next.js SSR app with all 55 models embedded as JSON
    in the HTML source. We extract the JSON array and parse model/score pairs.

    Returns dict of model_name → score (0-100).
    """
    print("[INFO] Fetching BenchLM.ai SWE-bench Verified scores ...")
    html = _fetch_text("https://benchlm.ai/benchmarks/sweVerified")
    if not html:
        print("[WARN] Failed to fetch BenchLM page")
        return {}

    scores = {}

    # Strategy 1: Extract embedded JSON data
    # The page contains JSON objects with "model" and "score" fields
    # Pattern: "model":"Name","slug":"...","creator":"Org",...,"score":95.5
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

    # Strategy 2: Fallback — parse HTML table spans with percentage pattern
    if len(scores) < 10:
        # Look for pattern: model name link text followed by percentage span
        # e.g. <a ...>Model Name</a> ... <span ...>95.5%</span>
        row_pattern = re.compile(
            r'<a[^>]*class="[^"]*font-medium[^"]*"[^>]*>([^<]+)</a>.*?'
            r'<span[^>]*class="[^"]*font-mono[^"]*text-right[^"]*"[^>]*>([\d.]+)%</span>',
            re.DOTALL
        )
        for m in row_pattern.finditer(html):
            name = m.group(1).strip()
            try:
                score = float(m.group(2))
                if 0 < score <= 100 and name not in scores:
                    scores[name] = score
            except ValueError:
                continue

    print(f"[INFO] Found {len(scores)} model scores on BenchLM.ai")
    return scores


# ── Source 2: tbench.ai — Terminal-Bench 2.1 ────────────────────────────

def fetch_tbench_scores() -> dict[str, float]:
    """Scrape Terminal-Bench 2.1 scores from tbench.ai.

    The page is a Next.js SSR app with leaderboard data embedded as JSON
    in __next_f script tags with escaped quotes. We find the "rows" array
    and parse model/accuracy pairs. When a model appears multiple times
    (different agents), we keep the highest score.

    Returns dict of model_name → score (0-100).
    """
    print("[INFO] Fetching tbench.ai Terminal-Bench 2.1 scores ...")
    html = _fetch_text("https://www.tbench.ai/leaderboard/terminal-bench/2.1")
    if not html:
        print("[WARN] Failed to fetch tbench.ai page")
        return {}

    scores = {}

    # Strategy 1: Extract embedded JSON rows from __next_f script tags
    # The data uses escaped quotes: \"rows\":[{...}]
    # Find the start of the rows array
    rows_start = html.find('\\"rows\\":[')
    if rows_start < 0:
        # Try unescaped version
        rows_start = html.find('"rows":[')

    if rows_start >= 0:
        # Find the opening bracket
        bracket_start = html.find('[', rows_start)
        if bracket_start >= 0:
            # Find matching closing bracket
            depth = 0
            bracket_end = bracket_start
            for i in range(bracket_start, min(bracket_start + 20000, len(html))):
                if html[i] == '[':
                    depth += 1
                elif html[i] == ']':
                    depth -= 1
                    if depth == 0:
                        bracket_end = i + 1
                        break

            raw = html[bracket_start:bracket_end]
            # Unescape the JSON
            unescaped = raw.replace('\\"', '"').replace('\\\\', '\\')

            try:
                rows = json.loads(unescaped)
                for row in rows:
                    model_names = row.get("model", [])
                    accuracy = row.get("accuracy")
                    if model_names and accuracy is not None:
                        score = round(float(accuracy) * 100, 1)
                        for name in model_names:
                            # Keep highest score per model
                            if name and (name not in scores or score > scores[name]):
                                scores[name] = score
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[WARN] Failed to parse tbench JSON: {e}")

    # Strategy 2: Fallback — parse HTML table cells
    if not scores:
        # Look for pattern: <span>MODEL</span> ... <span class="font-bold">SCORE%</span>
        row_pattern = re.compile(
            r'<span>([A-Za-z0-9][\w\s.\-]+)</span>.*?'
            r'<span\s+class="font-bold">([\d.]+)<!-- -->%</span>',
            re.DOTALL
        )
        for m in row_pattern.finditer(html):
            name = m.group(1).strip()
            try:
                score = float(m.group(2))
                if 0 < score <= 100 and (name not in scores or score > scores[name]):
                    scores[name] = score
            except ValueError:
                continue

    print(f"[INFO] Found {len(scores)} model scores on tbench.ai")
    return scores


# ── Source 3: whatllm.org — Multi-benchmark ─────────────────────────────

def fetch_whatllm_scores() -> dict[str, dict[str, float]]:
    """Scrape multi-benchmark scores from whatllm.org/best-llm-for-coding.

    The page has a single HTML table with columns: Rank, Model, Quality,
    LiveCodeBench, Terminal-Bench, SciCode, License.

    Returns dict of model_name → {"livecodebench": float, "terminal_bench": float, "scicode": float}.
    """
    print("[INFO] Fetching whatllm.org coding scores ...")
    html = _fetch_text("https://whatllm.org/best-llm-for-coding")
    if not html:
        print("[WARN] Failed to fetch whatllm page")
        return {}

    results = {}

    # Parse the table — each row has model name and multiple benchmark scores
    # Find all <tr> elements in the table body
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
    pct_pattern = re.compile(r'([\d.]+)%')
    model_name_pattern = re.compile(r'<p\s+class="font-semibold[^"]*"[^>]*>([^<]+)</p>')

    for tr_match in tr_pattern.finditer(html):
        tr_html = tr_match.group(1)
        tds = [m.group(1) for m in td_pattern.finditer(tr_html)]

        if len(tds) < 7:
            continue

        # Extract model name from 2nd <td>
        name_match = model_name_pattern.search(tds[1])
        if not name_match:
            continue
        model_name = name_match.group(1).strip()

        # Extract scores from columns 4 (LiveCodeBench), 5 (Terminal-Bench), 6 (SciCode)
        entry = {}

        # Column 4: LiveCodeBench
        lcb = pct_pattern.search(tds[3])
        if lcb and tds[3].strip() != '-':
            entry["livecodebench"] = float(lcb.group(1))

        # Column 5: Terminal-Bench
        tb = pct_pattern.search(tds[4])
        if tb and tds[4].strip() != '-':
            entry["terminal_bench_2_1"] = float(tb.group(1))

        # Column 6: SciCode
        sc = pct_pattern.search(tds[5])
        if sc and tds[5].strip() != '-':
            entry["scicode"] = float(sc.group(1))

        if entry:
            results[model_name] = entry

    total_fields = sum(len(v) for v in results.values())
    print(f"[INFO] Found {len(results)} models with {total_fields} benchmark fields on whatllm.org")
    return results


# ── Matching helper ──────────────────────────────────────────────────────

def match_live_scores(
    models: list[dict],
    scores: dict[str, float],
    benchmark_key: str,
    log_fn=None,
) -> int:
    """Match scraped scores to local models by normalised name.

    Uses the same matching strategy as benchmark_snapshots.match_snapshot:
    1. Exact match via normalised model name
    2. Exact match via stripped provider name
    3. Fuzzy substring match for names > 8 chars

    Returns the number of models that received a new (non-overwritten) score.
    """
    matched = 0

    for model in models:
        name = model.get("name", "")
        if not name:
            continue

        b = model.setdefault("benchmarks", {})
        if b.get(benchmark_key) is not None:
            continue

        stripped = _strip_provider(name)
        candidates = [_norm(name), _norm(stripped)]

        # Try each scraped score
        found = False
        for scraped_name, score in scores.items():
            scraped_norm = _norm(scraped_name)

            # 1. Exact match
            if scraped_norm in candidates:
                b[benchmark_key] = round(score, 1)
                matched += 1
                if log_fn:
                    log_fn(f"  {benchmark_key}: {name} = {score} (live exact)")
                found = True
                break

            # 2. Fuzzy substring for longer names
            # Only allow fuzzy match if both names are long enough and the
            # shorter one is at least 60% of the longer one's length
            # (prevents "DeepSeek V3" matching "DeepSeek V3.2 Exp")
            for c in candidates:
                if len(c) > 10 and len(scraped_norm) > 10:
                    shorter = min(len(c), len(scraped_norm))
                    longer = max(len(c), len(scraped_norm))
                    if shorter / longer > 0.6:
                        if c in scraped_norm or scraped_norm in c:
                            b[benchmark_key] = round(score, 1)
                            matched += 1
                            if log_fn:
                                log_fn(f"  {benchmark_key}: {name} = {score} (live fuzzy)")
                            found = True
                            break
            if found:
                break

    return matched


def match_whatllm_multi(
    models: list[dict],
    whatllm_data: dict[str, dict[str, float]],
    log_fn=None,
) -> int:
    """Match whatllm.org multi-benchmark data to local models.

    whatllm_data is model_name → {"livecodebench": float, "terminal_bench_2_1": float, "scicode": float}.
    """
    matched = 0

    for model in models:
        name = model.get("name", "")
        if not name:
            continue

        stripped = _strip_provider(name)
        candidates = [_norm(name), _norm(stripped)]
        b = model.setdefault("benchmarks", {})

        for scraped_name, entry in whatllm_data.items():
            scraped_norm = _norm(scraped_name)

            # Check if this scraped model matches our local model
            is_match = False
            if scraped_norm in candidates:
                is_match = True
            else:
                for c in candidates:
                    if len(c) > 8 and len(scraped_norm) > 8:
                        if c in scraped_norm or scraped_norm in c:
                            is_match = True
                            break

            if is_match:
                for key, score in entry.items():
                    if b.get(key) is None:
                        b[key] = round(score, 1)
                        matched += 1
                        if log_fn:
                            log_fn(f"  {key}: {name} = {score} (whatllm)")
                break

    return matched
