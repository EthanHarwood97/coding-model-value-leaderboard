/* ==========================================================================
   Coding Model Value Leaderboard - Main app
   Renders table, filters, sorting, and chart from data/models.json
   ========================================================================== */

(function () {
  'use strict';

  const STATE = {
    models: [],
    lastUpdated: null,
    sortBy: 'coding_quality',
    sortDir: 'desc',
    filters: {
      maxPrice: 30,
      minPro: 0,
      minContext: 0,
      license: 'all',
      hideUnrated: false,
      reasoning: 'all'
    }
  };

  /* Coding Quality Score: weighted composite of coding-specific benchmarks */
  const QUALITY_WEIGHTS = {
    swe_bench_pro: 0.40,
    aider_polyglot: 0.35,
    livecodebench: 0.25
  };

  function computeQualityScore(m) {
    const b = m.benchmarks || {};
    let score = 0;
    let totalWeight = 0;
    for (const [key, weight] of Object.entries(QUALITY_WEIGHTS)) {
      const val = b[key];
      if (val != null) {
        score += val * weight;
        totalWeight += weight;
      }
    }
    if (totalWeight === 0) return null;
    // Normalize to 0-100 scale (values are already percentages 0-100)
    return +(score / totalWeight).toFixed(1);
  }

  function computeCostPerQuality(m) {
    const qs = m.coding_quality_score;
    const out = m.pricing?.output_per_1m;
    if (qs != null && out != null && qs > 0) {
      return +(out / qs).toFixed(3);
    }
    return null;
  }

  /* ---------- Data loading ---------- */
  async function loadData() {
    try {
      const res = await fetch('data/models.json');
      if (!res.ok) throw new Error('Failed to load models.json');
      const data = await res.json();
      STATE.models = data.models || [];
      STATE.lastUpdated = data.last_updated;
      enrichModels(STATE.models);
    } catch (err) {
      console.error(err);
      document.getElementById('table-body').innerHTML =
        `<tr><td colspan="16" style="text-align:center;padding:2rem;color:var(--danger)">
          Failed to load data. If viewing locally, serve via <code>python -m http.server</code> or similar.
        </td></tr>`;
      return;
    }
    init();
  }

  function renderReasoning(rl) {
    if (!rl) return '<span class="null-val">—</span>';
    const labels = {
      standard: 'Standard',
      high: 'High',
      low: 'Low',
      thinking: 'Thinking',
      adaptive: 'Adaptive',
      max: 'Max'
    };
    const cls = 'reasoning-' + rl;
    return `<span class="reasoning-badge ${cls}">${labels[rl] || rl}</span>`;
  }

  /* Add computed fields to each model */
  function enrichModels(models) {
    models.forEach(m => {
      m.benchmarks = m.benchmarks || {};

      // Coding Quality Score (blended composite)
      m.coding_quality_score = computeQualityScore(m);

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

  /* ---------- Rendering ---------- */
  function init() {
    document.getElementById('last-updated').textContent = STATE.lastUpdated || '—';
    document.getElementById('footer-updated').textContent = STATE.lastUpdated || '—';
    document.getElementById('total-count').textContent = STATE.models.length;

    updateSpotlight();
    bindEvents();
    render();
    renderChart();
  }

  function updateSpotlight() {
    const candidates = STATE.models.filter(m => m.cost_per_quality != null);
    if (candidates.length === 0) return;
    const winner = candidates.reduce((a, b) =>
      a.cost_per_quality < b.cost_per_quality ? a : b
    );
    document.getElementById('spotlight-model').textContent = winner.name;
    const stats = [];
    if (winner.coding_quality_score != null) stats.push(`Quality: ${winner.coding_quality_score}/100`);
    if (winner.pricing) stats.push(`$${winner.pricing.output_per_1m}/1M out · $${winner.cost_per_quality}/Qual`);
    if (winner.context_window) stats.push(`${formatContext(winner.context_window)} context`);
    document.getElementById('spotlight-stats').textContent = stats.join(' · ');
  }

  function getFilteredModels() {
    return STATE.models.filter(m => {
      const out = m.pricing?.output_per_1m ?? Infinity;
      if (out > STATE.filters.maxPrice) return false;

      const pro = m.benchmarks?.swe_bench_pro ?? 0;
      if (pro < STATE.filters.minPro) return false;

      const ctx = m.context_window ?? 0;
      if (ctx < STATE.filters.minContext * 1000) return false;

      if (STATE.filters.license === 'open' && !m.open_weight) return false;
      if (STATE.filters.license === 'proprietary' && m.open_weight) return false;

      // Hide unrated
      if (STATE.filters.hideUnrated) {
        const b = m.benchmarks || {};
        const hasAny = b.swe_bench_pro != null || b.aider_polyglot != null || b.livecodebench != null
          || b.swe_bench_verified != null || b.terminal_bench_2_1 != null;
        if (!hasAny) return false;
      }

      // Reasoning level filter
      if (STATE.filters.reasoning !== 'all' && m.reasoning_level !== STATE.filters.reasoning) return false;

      return true;
    });
  }

  function sortModels(models) {
    const key = STATE.sortBy;
    const dir = STATE.sortDir === 'asc' ? 1 : -1;
    return [...models].sort((a, b) => {
      const av = getSortValue(a, key);
      const bv = getSortValue(b, key);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') {
        return av.localeCompare(bv) * dir;
      }
      return (av - bv) * dir;
    });
  }

  function reasoningSortValue(rl) {
    const order = { null: 0, low: 1, standard: 2, high: 3, thinking: 4, adaptive: 5, max: 6 };
    return order[rl] || 0;
  }

  function getSortValue(m, key) {
    if (key === 'output_price') return m.pricing?.output_per_1m;
    if (key === 'cost_per_pro_point') return m.cost_per_pro_point;
    if (key === 'cost_per_quality') return m.cost_per_quality;
    if (key === 'coding_quality') return m.coding_quality_score;
    if (key === 'swe_bench_pro') return m.benchmarks?.swe_bench_pro;
    if (key === 'swe_bench_verified') return m.benchmarks?.swe_bench_verified;
    if (key === 'aider_polyglot') return m.benchmarks?.aider_polyglot;
    if (key === 'aa_coding_index') return m.benchmarks?.aa_coding_index;
    if (key === 'terminal_bench') return m.benchmarks?.terminal_bench_2_1;
    if (key === 'context_window') return m.context_window;
    if (key === 'speed') return m.speed_tok_s;
    if (key === 'reasoning') return reasoningSortValue(m.reasoning_level);
    if (key === 'released') return m.released;
    return m[key];
  }

  function render() {
    const filtered = sortModels(getFilteredModels());
    const tbody = document.getElementById('table-body');
    document.getElementById('visible-count').textContent = filtered.length;

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="16" style="text-align:center;padding:2rem;color:var(--text-secondary)">No models match your filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(m => rowHtml(m)).join('');
    updateSortIndicators();
  }

  function rowHtml(m) {
    const b = m.benchmarks || {};
    const tagClass = m.tag ? `tag-${m.tag.toLowerCase().replace(/\s+/g, '-')}` : 'tag-default';
    return `
      <tr>
        <td class="model-cell">
          ${escapeHtml(m.name)}
          ${m.tag ? `<br><span class="tag ${tagClass}">${escapeHtml(m.tag)}</span>` : ''}
        </td>
        <td>${escapeHtml(m.provider)}</td>
        <td class="price">$${fmt(m.pricing?.output_per_1m, 2)}</td>
        <td class="quality-score">${m.coding_quality_score != null ? m.coding_quality_score.toFixed(0) : '<span class="null-val">—</span>'}</td>
        <td>${pct(b.swe_bench_pro)}</td>
        <td>${pct(b.aider_polyglot)}</td>
        <td>${b.aa_coding_index != null ? b.aa_coding_index.toFixed(0) : '<span class="null-val">—</span>'}</td>
        <td>${pct(b.swe_bench_verified)}</td>
        <td>${pct(b.terminal_bench_2_1)}</td>
        <td class="cost-per-point">${m.cost_per_quality != null ? '$' + m.cost_per_quality.toFixed(2) : '<span class="null-val">—</span>'}</td>
        <td class="cost-per-point">${m.cost_per_pro_point != null ? '$' + m.cost_per_pro_point.toFixed(2) : '<span class="null-val">—</span>'}</td>
        <td class="reasoning-cell">${renderReasoning(m.reasoning_level)}</td>
        <td>${m.context_window ? formatContext(m.context_window) : '<span class="null-val">—</span>'}</td>
        <td>${m.speed_tok_s ? m.speed_tok_s + ' tok/s' : '<span class="null-val">—</span>'}</td>
        <td class="${m.open_weight ? 'license-open' : 'license-proprietary'}">
          ${m.open_weight ? '✓ Open' : 'Proprietary'}
        </td>
        <td class="best-for">${escapeHtml(m.best_for || '—')}</td>
      </tr>
    `;
  }

  /* ---------- Chart ---------- */
  let chartInstance = null;
  function renderChart() {
    const canvas = document.getElementById('scatter-chart');
    if (!canvas) return;

    const points = STATE.models
      .filter(m => m.pricing && m.coding_quality_score != null)
      .map(m => ({
        x: m.pricing.output_per_1m,
        y: m.coding_quality_score,
        r: Math.max(6, Math.min(20, (m.context_window || 100000) / 60000)),
        label: m.name,
        provider: m.provider
      }));

    const isDark = document.documentElement.dataset.theme === 'dark';
    const gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
    const textColor = isDark ? '#e6edf3' : '#1f2328';

    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(canvas, {
      type: 'bubble',
      data: {
        datasets: [{
          label: 'Models',
          data: points,
          backgroundColor: 'rgba(88, 166, 255, 0.5)',
          borderColor: 'rgba(88, 166, 255, 0.9)',
          borderWidth: 1.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                return `${p.label} — $${p.x}/1M out, Quality: ${p.y}/100, ${p.provider}`;
              }
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: 'Output price ($/1M tokens)', color: textColor },
            ticks: { color: textColor, callback: v => '$' + v },
            grid: { color: gridColor }
          },
          y: {
            title: { display: true, text: 'Coding Quality Score', color: textColor },
            ticks: { color: textColor },
            grid: { color: gridColor },
            suggestedMin: 30,
            suggestedMax: 75
          }
        }
      }
    });
  }

  /* ---------- Events ---------- */
  function bindEvents() {
    // Filter sliders
    const priceSlider = document.getElementById('price-max');
    const priceVal = document.getElementById('price-max-val');
    priceSlider.addEventListener('input', () => {
      STATE.filters.maxPrice = +priceSlider.value;
      priceVal.textContent = '$' + priceSlider.value;
      render();
    });

    const proSlider = document.getElementById('min-pro');
    const proVal = document.getElementById('min-pro-val');
    proSlider.addEventListener('input', () => {
      STATE.filters.minPro = +proSlider.value;
      proVal.textContent = proSlider.value + '%';
      render();
    });

    const ctxSlider = document.getElementById('min-context');
    const ctxVal = document.getElementById('min-context-val');
    ctxSlider.addEventListener('input', () => {
      STATE.filters.minContext = +ctxSlider.value;
      ctxVal.textContent = ctxSlider.value + 'K';
      render();
    });

    document.getElementById('license-filter').addEventListener('change', (e) => {
      STATE.filters.license = e.target.value;
      render();
    });

    document.getElementById('filter-reasoning').addEventListener('change', (e) => {
      STATE.filters.reasoning = e.target.value;
      render();
    });

    document.getElementById('hide-unrated').addEventListener('change', (e) => {
      STATE.filters.hideUnrated = e.target.checked;
      render();
    });

    document.getElementById('sort-by').addEventListener('change', (e) => {
      STATE.sortBy = e.target.value;
      // Default direction: cost/price ASC, quality/score DESC
      if (e.target.value.includes('cost') || e.target.value.includes('price')) {
        STATE.sortDir = 'asc';
      } else {
        STATE.sortDir = 'desc';
      }
      render();
    });

    // Table header sort
    document.querySelectorAll('th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        const sortKey = key === 'name' || key === 'provider' || key === 'license' || key === 'reasoning'
          ? key
          : (key === 'output_price' ? 'output_price'
            : (key === 'context_window' ? 'context_window'
              : (key === 'speed' ? 'speed' : key)));
        if (STATE.sortBy === sortKey) {
          STATE.sortDir = STATE.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          STATE.sortBy = sortKey;
          STATE.sortDir = (sortKey.includes('cost') || sortKey.includes('price') || sortKey === 'output_price') ? 'asc' : 'desc';
        }
        render();
      });
    });

    // Theme toggle
    document.getElementById('theme-toggle').addEventListener('click', () => {
      const html = document.documentElement;
      const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
      html.dataset.theme = next;
      document.getElementById('theme-toggle').textContent = next === 'dark' ? '🌙' : '☀️';
      localStorage.setItem('theme', next);
      renderChart();
    });

    // Restore theme
    const saved = localStorage.getItem('theme');
    if (saved) {
      document.documentElement.dataset.theme = saved;
      document.getElementById('theme-toggle').textContent = saved === 'dark' ? '🌙' : '☀️';
    }
  }

  function updateSortIndicators() {
    document.querySelectorAll('th[data-sort]').forEach(th => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      const key = th.dataset.sort;
      const sortKey = key === 'output_price' ? 'output_price'
        : (key === 'context_window' ? 'context_window'
          : (key === 'speed' ? 'speed'
            : (key === 'reasoning' ? 'reasoning'
              : (key === 'coding_quality' ? 'coding_quality'
                : (key === 'aider_polyglot' ? 'aider_polyglot'
                  : (key === 'aa_coding_index' ? 'aa_coding_index'
                    : (key === 'cost_per_quality' ? 'cost_per_quality'
                      : key)))))));
      if (STATE.sortBy === sortKey) {
        th.classList.add(STATE.sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
      }
    });
  }

  /* ---------- Helpers ---------- */
  function pct(v) {
    if (v == null) return '<span class="null-val">—</span>';
    return v.toFixed(1) + '%';
  }

  function fmt(v, decimals = 2) {
    if (v == null) return '—';
    return v.toFixed(decimals);
  }

  function formatContext(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(0) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(0) + 'K';
    return n;
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Boot
  document.addEventListener('DOMContentLoaded', loadData);
})();