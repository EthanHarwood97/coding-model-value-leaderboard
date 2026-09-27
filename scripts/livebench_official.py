"""
livebench_official.py — Official LiveBench data (table, categories, cost).

Fetches the same static files livebench.ai itself loads:

  ./table_<release>.csv        task-level accuracy scores (0-100)
  ./categories_<release>.json  task -> category grouping
  ./cost_<release>.csv         per-task cost + API prices

Category scores are unweighted means of their task columns, matching the
livebench.ai leaderboard exactly (verified against the 2026-06-25 release).

Usage:
    from livebench_official import resolve_release, fetch_table, fetch_categories
    release = resolve_release()
    rows = fetch_table(release)
    cats = fetch_categories(release)
"""

import csv
import io
import json
import re
from urllib.parse import urljoin

import live_benchmarks

PINNED_RELEASE = "2026-06-25"
SITE_URL = "https://livebench.ai/"
BUNDLE_RE = re.compile(r"/?static/js/main\.[0-9a-f]+\.js")
RELEASES_ARRAY_RE = re.compile(r'\[(?:\s*"20\d{2}-\d{2}-\d{2}"\s*,?)+\]')
DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")

_SUFFIX_TOKENS = {
    "thinking", "auto", "high", "xhigh", "medium", "low", "max",
    "effort", "64k", "preview", "adaptive", "reasoning",
}
_BRAND_HYPHEN = {"gpt", "glm"}
_WORD_MAP = {
    "gpt": "GPT", "glm": "GLM", "xhigh": "xHigh", "xai": "xAI",
    "oss": "OSS", "ai": "AI", "deepseek": "DeepSeek",
    "minimax": "MiniMax", "kimi": "Kimi", "gemini": "Gemini",
    "grok": "Grok", "smaug": "Smaug", "muse": "Muse",
    "nemotron": "Nemotron", "inkling": "Inkling",
}
_PROVIDERS = {
    "claude": "Anthropic",
    "gpt": "OpenAI",
    "gemini": "Google",
    "grok": "xAI",
    "deepseek": "DeepSeek",
    "qwen": "Alibaba",
    "glm": "Z.ai",
    "kimi": "Moonshot AI",
    "minimax": "MiniMax",
    "muse": "Meta",
    "smaug": "Abacus.AI",
    "nemotron": "NVIDIA",
}


def _fetch_text(url):
    """HTTP fetch, delegated to live_benchmarks (monkeypatchable in tests)."""
    return live_benchmarks._fetch_text(url)


def _release_url(release, kind, ext):
    return f"https://livebench.ai/{kind}_{release.replace('-', '_')}.{ext}"


def discover_latest_release():
    """Find the newest release date from the livebench.ai JS bundle."""
    html = _fetch_text(SITE_URL)
    if not html:
        return None
    m = BUNDLE_RE.search(html)
    if not m:
        return None
    bundle = _fetch_text(urljoin(SITE_URL, m.group(0).lstrip("./")))
    if not bundle:
        return None
    latest = None
    for arr in RELEASES_ARRAY_RE.finditer(bundle):
        dates = DATE_RE.findall(arr.group(0))
        if dates and (latest is None or max(dates) > latest):
            latest = max(dates)
    return latest


def resolve_release(explicit=None, log_fn=None):
    """Explicit date > auto-discovered > pinned fallback."""
    if explicit:
        return explicit
    found = discover_latest_release()
    if found:
        return found
    if log_fn:
        log_fn(f"[WARN] LiveBench release discovery failed; using pinned {PINNED_RELEASE}")
    return PINNED_RELEASE


def _fetch_csv(url):
    text = _fetch_text(url)
    if not text:
        return []
    return list(csv.DictReader(io.StringIO(text)))


def fetch_table(release):
    """Task-level accuracy rows: list[dict] with a 'model' key."""
    return _fetch_csv(_release_url(release, "table", "csv"))


def fetch_cost(release):
    """Cost rows: list[dict] with model, prices, cost_per_successful_task."""
    return _fetch_csv(_release_url(release, "cost", "csv"))


def fetch_categories(release):
    """Official task -> category grouping."""
    text = _fetch_text(_release_url(release, "categories", "json"))
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _num(v):
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def category_means(task_row, categories):
    """Unweighted mean of each category's task columns (livebench.ai method)."""
    out = {}
    for cat, tasks in categories.items():
        vals = [_num(task_row.get(t)) for t in tasks]
        vals = [v for v in vals if v is not None]
        out[cat] = round(sum(vals) / len(vals), 1) if vals else None
    return out


def core_name(raw):
    """Variant-insensitive key for matching eval configs to model names.

    Drops date stamps and tuning suffixes so
    'claude-opus-4-6-thinking-auto-high-effort' -> 'claudeopus46'.
    """
    s = re.sub(r"\d{4}-\d{2}-\d{2}", " ", raw.lower())
    s = re.sub(r"\d{8}", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = [t for t in s.split() if t not in _SUFFIX_TOKENS]
    return re.sub(r"[^a-z0-9]", "", " ".join(toks))


def _format_token(t: str) -> str:
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return t
    m = re.fullmatch(r"([a-z]?)(\d+)([a-z])", t)
    if m:
        return m.group(1).upper() + m.group(2) + m.group(3).upper()
    mapped = _WORD_MAP.get(t.lower())
    return mapped if mapped is not None else t[:1].upper() + t[1:]


def name_parts(raw):
    """Split an eval config name into (display base, tuning variant).

    'claude-opus-4-6-thinking-auto-high-effort' -> ('Claude Opus 4.6',
    'Thinking Auto High Effort'); 'gpt-5.4-mini-xhigh' -> ('GPT-5.4 Mini',
    'xHigh').
    """
    s = re.sub(r"\d{8}", " ", raw.lower())
    s = re.sub(r"\d{4}-\d{2}-\d{2}", " ", s)
    toks = [t for t in (tok.strip() for tok in s.split("-")) if t]

    merged: list[str] = []
    i = 0
    while i < len(toks):
        if re.fullmatch(r"\d{1,2}", toks[i]) and i + 1 < len(toks) and re.fullmatch(r"\d{1,2}", toks[i + 1]):
            merged.append(toks[i] + "." + toks[i + 1])
            i += 2
        else:
            merged.append(toks[i])
            i += 1

    j = len(merged)
    while j > 0 and (merged[j - 1] in _SUFFIX_TOKENS or re.fullmatch(r"\d{3,4}", merged[j - 1])):
        j -= 1
    core, variant = merged[:j], merged[j:]

    parts: list[str] = []
    k = 0
    while k < len(core):
        if core[k] in _BRAND_HYPHEN and k + 1 < len(core):
            parts.append(_format_token(core[k]) + "-" + _format_token(core[k + 1]))
            k += 2
        else:
            parts.append(_format_token(core[k]))
            k += 1

    base = " ".join(parts)
    return base, " ".join(_format_token(t) for t in variant)


def prettify_name(raw):
    """Human-readable display name (base plus variant when present)."""
    base, variant = name_parts(raw)
    return f"{base} · {variant}" if variant else base


def infer_provider(raw):
    """Provider inferred from the model-name prefix."""
    lower = raw.lower()
    for key, provider in _PROVIDERS.items():
        if lower.startswith(key):
            return provider
    return raw.split("-")[0].capitalize()
