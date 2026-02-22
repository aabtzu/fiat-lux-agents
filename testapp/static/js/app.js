// --- State ---
let showFilteredOut = false;
let queryScope = 'filtered'; // 'filtered' | 'all'
let queryCharts = []; // track all inline charts for cleanup

// --- Tab switching ---
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'data' || tab.dataset.tab === 'filter') loadData();
  });
});

// --- Data loading ---
async function loadData() {
  const res = await fetch('/api/data');
  const d = await res.json();
  applyState(d);
}

function applyState(d) {
  renderTable('data-table', d.data);
  renderTable('filter-table', d.data);
  document.getElementById('stat-total').textContent = `Total: ${d.total}`;
  document.getElementById('stat-filtered').textContent = `Showing: ${d.filtered}`;
  document.getElementById('stat-filters').textContent = `Filters: ${d.filters.length}`;
  renderFilterTags(d.filters);
}

// --- Table rendering ---
function renderTable(id, rows) {
  const tbody = document.querySelector(`#${id} tbody`);

  const visibleRows = rows.filter(r => r._visible);
  const hiddenRows  = rows.filter(r => !r._visible);

  const toRender = showFilteredOut ? rows : visibleRows;

  if (!toRender.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty" style="padding:16px">No data</td></tr>';
    return;
  }

  tbody.innerHTML = toRender.map(r => `
    <tr class="${r._visible ? '' : 'filtered-out'}">
      <td>${r.name}</td><td>${r.region}</td><td>${r.category}</td>
      <td>${r.status}</td><td>$${r.amount.toLocaleString()}</td><td>${r.units}</td><td>${r.month}</td>
    </tr>`).join('');
}

function toggleShowFiltered() {
  showFilteredOut = !showFilteredOut;
  const label = showFilteredOut ? 'Hide filtered out' : 'Show filtered out';
  ['btn-show-filtered', 'btn-show-filtered-filter'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.toggle('active', showFilteredOut);
    btn.textContent = label;
  });
  loadData();
}

// --- Filter tags ---
function renderFilterTags(filters) {
  const el = document.getElementById('filter-tags');
  if (!filters.length) {
    el.innerHTML = '<span class="empty">No active filters</span>';
    return;
  }
  el.innerHTML = filters.map(f => {
    const enabled = f.enabled !== false;
    return `<span class="filter-tag ${enabled ? '' : 'disabled'}">
      <button class="btn-toggle" onclick="toggleFilter('${f.id}')" title="${enabled ? 'Disable' : 'Enable'}">
        ${enabled ? '●' : '○'}
      </button>
      ${f.description}
      <button class="btn-delete" onclick="removeFilter('${f.id}')" title="Remove">×</button>
    </span>`;
  }).join('');
}

// --- Filter actions ---
function setFilter(text) { document.getElementById('filter-input').value = text; }

async function addFilter() {
  const input  = document.getElementById('filter-input');
  const status = document.getElementById('filter-status');
  const message = input.value.trim();
  if (!message) return;

  status.textContent = 'Interpreting filter…';
  const res = await fetch('/api/filter/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });
  const d = await res.json();
  if (d.error) { status.textContent = '❌ ' + d.error; return; }

  input.value = '';
  status.textContent = `✓ ${d.description}`;
  applyState(d);
}

async function toggleFilter(id) {
  const res = await fetch('/api/filter/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filter_id: id })
  });
  applyState(await res.json());
}

async function removeFilter(id) {
  const res = await fetch('/api/filter/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filter_id: id })
  });
  applyState(await res.json());
}

async function clearFilters() {
  const res = await fetch('/api/filter/clear', { method: 'POST' });
  document.getElementById('filter-status').textContent = '';
  applyState(await res.json());
}

// --- Chart rendering from server-generated Plotly JSON ---
function renderFigInline(containerId, figJson) {
  if (!figJson) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'msg chart-msg';
  wrapper.style.height = '360px';

  const container = document.getElementById(containerId);
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;

  try {
    const fig = JSON.parse(figJson);
    const layout = Object.assign({
      height: 340,
      margin: {t: 40, r: 20, b: 60, l: 60},
      paper_bgcolor: 'white',
      plot_bgcolor: '#fafafa',
      font: {size: 11},
    }, fig.layout || {});
    Plotly.newPlot(wrapper, fig.data || [], layout, {responsive: false, displayModeBar: false});
    queryCharts.push(wrapper);
  } catch (e) {
    console.error('Failed to render fig_json:', e);
  }
}

// --- Query scope toggle ---
function setQueryScope(scope) {
  queryScope = scope;
  document.querySelectorAll('.query-scope-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.scope === scope);
  });
  updateScopeLabel();
}

function updateScopeLabel() {
  const el = document.getElementById('query-scope-label');
  if (!el) return;
  el.textContent = queryScope === 'filtered' ? '(filtered rows)' : '(all rows)';
}

// --- Histogram bin summary for table display ---
function formatHistogramBins(data, valueCol, nbins) {
  const values = data.map(r => r[valueCol]).filter(v => v != null && !isNaN(v));
  if (!values.length) return 'No data';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const binWidth = (max - min) / nbins;
  const bins = Array.from({length: nbins}, (_, i) => ({
    lo: min + i * binWidth,
    hi: min + (i + 1) * binWidth,
    count: 0
  }));
  values.forEach(v => {
    let i = Math.floor((v - min) / binWidth);
    if (i >= nbins) i = nbins - 1;
    bins[i].count++;
  });
  const fmt = n => Number.isInteger(n) ? n.toString() : n.toFixed(2);
  return bins
    .filter(b => b.count > 0)
    .map(b => `${fmt(b.lo)} – ${fmt(b.hi)}: ${b.count}`)
    .join('\n');
}

// --- Query ---
async function sendQuery() {
  const input = document.getElementById('query-input');
  const message = input.value.trim();
  if (!message) return;

  addMessage('query-messages', 'user', message);
  addMessage('query-messages', 'assistant', '…');
  input.value = '';

  const res = await fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, scope: queryScope })
  });
  const d = await res.json();

  setMessageText(document.getElementById('query-messages').lastChild, d.error || d.answer, 'assistant');
  document.getElementById('query-code').textContent = d.query || 'No query generated';

  if (d.result?.success) {
    document.getElementById('query-result').textContent =
      JSON.stringify(d.result.data, null, 2).slice(0, 800);
  } else {
    document.getElementById('query-result').textContent = d.error || '';
  }
  if (d.fig_json) {
    renderFigInline('query-messages', d.fig_json);
  }
}

async function clearQueryHistory() {
  await fetch('/api/query/clear', { method: 'POST' });
  queryCharts.forEach(div => { try { Plotly.purge(div); } catch (e) {} });
  queryCharts = [];
  document.getElementById('query-messages').innerHTML =
    '<div class="msg assistant">Ask a question about the data.</div>';
  document.getElementById('query-code').textContent   = 'None yet';
  document.getElementById('query-result').textContent = 'None yet';
}

// --- Filter Chat ---
async function sendFilterChat() {
  const input = document.getElementById('filterchat-input');
  const message = input.value.trim();
  if (!message) return;

  addMessage('filterchat-messages', 'user', message);
  addMessage('filterchat-messages', 'assistant', '…');
  input.value = '';

  const res = await fetch('/api/filterchat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });
  const d = await res.json();

  setMessageText(document.getElementById('filterchat-messages').lastChild, d.response || d.error, 'assistant');

  if (d.filters !== undefined) {
    const tags = document.getElementById('filterchat-tags');
    tags.innerHTML = d.filters.length
      ? d.filters.map(f => `<div style="font-size:12px;margin:2px 0">• ${f.description}</div>`).join('')
      : '<span class="empty">None</span>';
  }

  if (d.data) {
    applyState(d);
    document.getElementById('filterchat-result').textContent =
      `${d.filtered} items\n` + JSON.stringify(d.data.filter(r => r._visible).slice(0, 5), null, 2).slice(0, 600);
  }
}

async function clearFiltersFromChat() {
  const res = await fetch('/api/filter/clear', { method: 'POST' });
  const d = await res.json();
  applyState(d);
  const tags = document.getElementById('filterchat-tags');
  tags.innerHTML = '<span class="empty">None</span>';
  document.getElementById('filterchat-result').textContent = 'None yet';
  addMessage('filterchat-messages', 'assistant', 'All filters cleared.');
}

async function clearFilterChat() {
  await fetch('/api/filterchat/clear', { method: 'POST' });
  document.getElementById('filterchat-messages').innerHTML =
    '<div class="msg assistant">Ask questions or request filters.</div>';
  document.getElementById('filterchat-tags').innerHTML  = '<span class="empty">None</span>';
  document.getElementById('filterchat-result').textContent = 'None yet';
}

// --- Helpers ---
function addMessage(containerId, role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  if (role === 'assistant') {
    el.innerHTML = marked.parse(text);
  } else {
    el.textContent = text;
  }
  const container = document.getElementById(containerId);
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return el;
}

function setMessageText(el, text, role) {
  if (role === 'assistant') {
    el.innerHTML = marked.parse(text);
  } else {
    el.textContent = text;
  }
}

// Enter key support
document.getElementById('filter-input').addEventListener('keydown',     e => { if (e.key === 'Enter') addFilter(); });
document.getElementById('query-input').addEventListener('keydown',      e => { if (e.key === 'Enter') sendQuery(); });
document.getElementById('filterchat-input').addEventListener('keydown', e => { if (e.key === 'Enter') sendFilterChat(); });

// Initial load
loadData();
