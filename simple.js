/* ==========================================================================
   Coding Model Scorecard - renders data/simple.json as a compact table
   Columns: Rank, Model, Agentic Coding, Coding, Vision, Out $/1M, Value
   ========================================================================== */

(function () {
  'use strict';

  const STATE = {
    models: [],
    lastUpdated: null,
    release: null,
    sortBy: 'frontend_score',
    sortDir: 'desc'
  };

  const COLUMNS = [
    { key: 'rank', label: 'Rank', sort: 'frontend_score', cls: 'rank-cell', title: 'Position in the current sort. Default order is the Frontend score' },
    { key: 'name', label: 'Model', sort: 'name', cls: 'model-cell' },
    { key: 'agentic_coding', label: 'Agentic', sort: 'agentic_coding', cls: 'quality-score', title: 'LiveBench Agentic Coding: mean of the python, javascript, and typescript tasks. Dotted underline = counts at 60% in the scores' },
    { key: 'coding', label: 'Coding', sort: 'coding', cls: 'quality-score', title: 'LiveBench Coding: mean of the code_generation and code_completion tasks' },
    { key: 'coder_score', label: 'Coder', sort: 'coder_score', cls: 'quality-score', title: 'Mean of the two LiveBench scores. Agentic below 42 counts at 60%. Basis for Value' },
    { key: 'vision_score', label: 'Vision', sort: 'vision_score', cls: 'quality-score', title: 'MMMU-Pro via BenchLM.ai, then llm-stats.com. Image, chart, diagram, and document understanding' },
    { key: 'frontend_score', label: 'Frontend', sort: 'frontend_score', cls: 'quality-score', title: 'Mean of all three tracked scores, vision included. Falls back to the LiveBench pair when vision is missing' },
    { key: 'output_price_per_1m', label: 'Out $/1M', sort: 'output_price_per_1m', cls: 'price-cell', title: 'Output price per million tokens (USD)' },
    { key: 'value', label: 'Value', sort: 'value', cls: 'value-cell', title: 'Coder score per $/1M output, scaled by 60% below the agentic floor. Higher means more score per dollar' }
  ];

  async function loadData() {
    let data = null;
    if (location.protocol === 'file:') {
      data = await loadViaScript();
    } else {
      try {
        const res = await fetch('data/simple.json', { cache: 'no-store' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        data = await res.json();
      } catch (err) {
        console.warn('fetch failed, trying local fallback:', err);
        data = await loadViaScript();
      }
    }
    if (!data) {
      document.getElementById('table-body').innerHTML =
        '<tr><td colspan="9" class="loading-cell">Could not load data. Check that data/simple.json (or data/simple.js) sits next to this page.</td></tr>';
      return;
    }
    STATE.models = data.models || [];
    STATE.lastUpdated = data.last_updated;
    STATE.release = data.livebench_release;
    init();
  }

  function loadViaScript() {
    return new Promise(resolve => {
      const s = document.createElement('script');
      s.src = 'data/simple.js?t=' + Date.now();
      s.onload = () => resolve(window.__SCORECARD_DATA__ || null);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
    });
  }

  function init() {
    document.getElementById('release').textContent = STATE.release || '—';
    document.getElementById('footer-release').textContent = STATE.release || '—';
    document.getElementById('last-updated').textContent = STATE.lastUpdated || '—';
    document.getElementById('footer-updated').textContent = STATE.lastUpdated || '—';
    document.getElementById('visible-count').textContent = STATE.models.length;

    restoreTheme();
    buildHeader();
    bindEvents();
    render();
  }

  function restoreTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) {
      document.documentElement.dataset.theme = saved;
      document.getElementById('theme-toggle').textContent = saved === 'dark' ? '🌙' : '☀️';
    }
  }

  function buildHeader() {
    const row = document.querySelector('#scorecard thead tr');
    row.innerHTML = COLUMNS.map(col => {
      const sortAttr = col.sort ? ` data-sort="${col.sort}"` : '';
      const titleAttr = col.title ? ` title="${escapeHtml(col.title)}"` : '';
      return `<th scope="col"${sortAttr}${titleAttr}>${col.label}</th>`;
    }).join('');
  }

  function getSortValue(m, key) {
    if (key === 'name') return m.name;
    if (key === 'coder_score') return m.coder_score;
    if (key === 'frontend_score') return m.frontend_score;
    if (key === 'agentic_coding') return m.agentic_coding;
    if (key === 'coding') return m.coding;
    if (key === 'vision_score') return m.vision_score;
    if (key === 'output_price_per_1m') return m.output_price_per_1m;
    if (key === 'value') return m.value;
    return m[key];
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
      if (typeof av === 'string') return av.localeCompare(bv) * dir;
      return (av - bv) * dir;
    });
  }

  function render() {
    const sorted = sortModels(STATE.models);
    const tbody = document.getElementById('table-body');
    document.getElementById('visible-count').textContent = sorted.length;

    tbody.innerHTML = sorted.map((m, i) => rowHtml(m, i + 1)).join('');
    updateSortIndicators();
  }

  function rowHtml(m, rank) {
    const variant = m.variant ? `<span class="variant">${escapeHtml(m.variant)}</span>` : '';
    return `
      <tr>
        <td class="rank-cell">${rank}</td>
        <td class="model-cell">${escapeHtml(m.name)}${variant}</td>
        <td class="quality-score">${agenticHtml(m)}</td>
        <td class="quality-score">${num(m.coding, 1)}</td>
        <td class="quality-score">${num(m.coder_score, 1)}</td>
        <td class="quality-score">${visionHtml(m)}</td>
        <td class="quality-score">${num(m.frontend_score, 1)}</td>
        <td class="price-cell">${priceHtml(m.output_price_per_1m)}</td>
        <td class="value-cell">${num(m.value, 1)}</td>
      </tr>
    `;
  }

  function bindEvents() {
    document.querySelectorAll('#scorecard th[data-sort]').forEach(th => {
      th.setAttribute('tabindex', '0');
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (STATE.sortBy === key) {
          STATE.sortDir = STATE.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          STATE.sortBy = key;
          STATE.sortDir = key === 'output_price_per_1m' || key === 'name' ? 'asc' : 'desc';
        }
        render();
      });
      th.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          th.click();
        }
      });
    });

    document.getElementById('theme-toggle').addEventListener('click', () => {
      const html = document.documentElement;
      const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
      html.dataset.theme = next;
      document.getElementById('theme-toggle').textContent = next === 'dark' ? '🌙' : '☀️';
      localStorage.setItem('theme', next);
    });
  }

  function updateSortIndicators() {
    document.querySelectorAll('#scorecard th[data-sort]').forEach(th => {
      th.classList.remove('sorted-asc', 'sorted-desc');
      th.removeAttribute('aria-sort');
      if (th.dataset.sort === STATE.sortBy) {
        th.classList.add(STATE.sortDir === 'asc' ? 'sorted-asc' : 'sorted-desc');
        th.setAttribute('aria-sort', STATE.sortDir === 'asc' ? 'ascending' : 'descending');
      }
    });
  }

  function num(v, decimals) {
    if (v == null) return '<span class="null-val">—</span>';
    return v.toFixed(decimals);
  }

  function agenticHtml(m) {
    if (m.agentic_coding == null) return '<span class="null-val">—</span>';
    if (m.agentic_effective != null) {
      const tip = `Counts at 60% (${m.agentic_effective.toFixed(1)}) in Coder and Frontend: below the 42 floor, these runs fail too often to take at face value.`;
      return `<span class="agentic-penalized" title="${escapeHtml(tip)}">${m.agentic_coding.toFixed(1)}</span>`;
    }
    return m.agentic_coding.toFixed(1);
  }

  function visionHtml(m) {
    if (m.vision_score != null) {
      const sources = {
        aa: 'Artificial Analysis (independent MMMU-Pro run)',
        benchlm: 'published MMMU-Pro score (BenchLM.ai)',
        'llm-stats': 'published MMMU-Pro score (llm-stats.com)'
      };
      const src = sources[m.vision_source] || 'MMMU-Pro';
      return `<span title="MMMU-Pro · ${escapeHtml(src)}">${m.vision_score.toFixed(1)}</span>`;
    }
    if (m.vision_est) {
      const est = m.vision_est;
      const tip = `No MMMU-Pro result yet. Floor carried from ${est.from} (${est.value.toFixed(1)}): the newest scored model in the same line. Newer is usually at least as good.`;
      return `<span class="vision-est" title="${escapeHtml(tip)}">${est.value.toFixed(1)}+<span class="est-label">est.</span></span>`;
    }
    return '<span class="null-val">—</span>';
  }

  function priceHtml(price) {
    if (price == null) return '<span class="null-val">—</span>';
    if (price === 0) return 'Free';
    return '$' + price.toFixed(2);
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

  document.addEventListener('DOMContentLoaded', loadData);
})();
