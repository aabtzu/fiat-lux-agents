// --- State ---
let showFilteredOut = false;

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
      <td>${r.name}</td><td>${r.department}</td><td>${r.role}</td>
      <td>${r.age}</td><td>${r.tenure_years}yr</td><td>${r.education}</td>
      <td>${r.remote}</td><td>${r.hours_per_week}</td><td>${r.projects_completed}</td>
      <td>${r.training_hours}</td><td>${r.absences}</td><td>${r.performance_score}</td>
      <td>${r.satisfaction_score}</td><td>$${r.salary.toLocaleString()}</td>
      <td>${r.bonus_pct}%</td><td>${r.last_review}</td>
      <td>${r.promoted ? '✓' : ''}</td><td>${r.churned ? '✓' : ''}</td>
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

// ── ML Tab ────────────────────────────────────────────────────────────────────

function setMLTask(text) {
  document.getElementById('ml-input').value = text;
  runML();
}

async function runML() {
  const input = document.getElementById('ml-input');
  const msg   = input.value.trim();
  if (!msg) return;

  appendMsg('ml-messages', msg, 'user');
  input.value = '';
  setStatus('ml-status', 'Running model…');

  const res = await fetch('/api/ml', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg }),
  }).then(r => r.json());

  setStatus('ml-status', '');

  // Answer
  const answer = res.answer || (res.error ? `Error: ${res.error}` : 'No response');
  appendMsg('ml-messages', answer, 'assistant');

  // Metrics card
  if (res.metrics && Object.keys(res.metrics).length) {
    const card = document.getElementById('ml-metrics-card');
    const div  = document.getElementById('ml-metrics');
    div.innerHTML = Object.entries(res.metrics)
      .map(([k, v]) => `<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f0f0f0;font-size:13px">
        <span style="color:#555">${k}</span>
        <span style="font-weight:600">${typeof v === 'number' ? v.toLocaleString(undefined, {maximumFractionDigits: 4}) : v}</span>
      </div>`).join('');
    card.style.display = '';
  }

  // Chart
  if (res.fig_json) {
    const chartDiv = document.getElementById('ml-chart');
    chartDiv.innerHTML = '<div id="ml-plotly" style="background:#fff;border-radius:6px;padding:8px"></div>';
    Plotly.newPlot('ml-plotly', JSON.parse(res.fig_json));
  }

  // Feature importance + predictions tables
  const tablesDiv = document.getElementById('ml-tables');
  tablesDiv.innerHTML = '';
  if (res.feature_importance?.length) {
    tablesDiv.appendChild(buildMLTable('Feature Importance', res.feature_importance, ['Feature', 'Importance'], v =>
      typeof v === 'number' ? v.toFixed(4) : v
    ));
  }
  if (res.predictions?.length) {
    const cols = Object.keys(res.predictions[0]);
    tablesDiv.appendChild(buildMLTable(`Predictions (${res.predictions.length} rows)`, res.predictions, cols));
  }
}

function buildMLTable(title, rows, cols, fmt) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'flex:1;min-width:280px;max-width:540px';
  wrap.innerHTML = `<h4 style="font-size:13px;font-weight:600;margin-bottom:8px">${title}</h4>`;
  const scroll = document.createElement('div');
  scroll.style.cssText = 'overflow-x:auto;max-height:320px;overflow-y:auto';
  const table = document.createElement('table');
  table.style.cssText = 'font-size:12px;white-space:nowrap';
  table.innerHTML = `<thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${cols.map(c => {
      const v = r[c] ?? '';
      return `<td>${fmt ? fmt(v, c) : v}</td>`;
    }).join('')}</tr>`).join('')}</tbody>`;
  scroll.appendChild(table);
  wrap.appendChild(scroll);
  return wrap;
}

async function clearML() {
  await fetch('/api/ml/clear', { method: 'POST' });
  document.getElementById('ml-messages').innerHTML =
    '<div class="msg assistant">History cleared. Describe a modeling task to begin.</div>';
  document.getElementById('ml-metrics-card').style.display = 'none';
  document.getElementById('ml-chart').innerHTML = '';
  document.getElementById('ml-tables').innerHTML = '';
}

// Enter key support
document.getElementById('filter-input').addEventListener('keydown',     e => { if (e.key === 'Enter') addFilter(); });
document.getElementById('filterchat-input').addEventListener('keydown', e => { if (e.key === 'Enter') sendFilterChat(); });
document.getElementById('ml-input').addEventListener('keydown',         e => { if (e.key === 'Enter') runML(); });

// Initial load
loadData();
