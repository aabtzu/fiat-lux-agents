/**
 * Explorer.js — fiat-lux-agents Data Explorer
 *
 * Configured via window.EXPLORER_CONFIG (set by explorer_tab.html):
 *   queryUrl, clearUrl, welcomeTitle, welcomeText,
 *   show_scope_toggle (bool), defaultScope ('all'|'filtered'),
 *   results_mode ('single'|'scroll')
 */

(function () {
    const cfg = window.EXPLORER_CONFIG || {};
    const QUERY_URL    = cfg.query_url    || '/explorer/query';
    const CLEAR_URL    = cfg.clear_url    || '/explorer/query/clear';
    const RESULTS_MODE = cfg.results_mode || 'single';   // 'single' | 'scroll'

    let sessionId       = null;
    let abortCtrl       = null;
    let scope           = cfg.defaultScope || 'all';
    let pendingQuestion = '';   // used in scroll mode to label each result block
    let inputHistory    = [];   // submitted queries, oldest first
    let historyIdx      = -1;   // -1 = not browsing; 0..n-1 = index into history
    let historyDraft    = '';   // saves current draft when user starts browsing
    let activeFeature   = null; // optional feature column to focus queries on

    // ── localStorage persistence ─────────────────────────────────────────────
    // Keyed by query_url so each explorer blueprint has its own slot.

    const STORE_KEY = 'fla_state_' + QUERY_URL;

    function _saveState(lastResult) {
        try {
            const msgs = $('fla-messages');
            localStorage.setItem(STORE_KEY, JSON.stringify({
                sessionId,
                inputHistory,
                messagesHtml: msgs ? msgs.innerHTML : '',
                lastResult: lastResult || null,
            }));
        } catch (_) {}
    }

    function _loadState() {
        try {
            const raw = localStorage.getItem(STORE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (_) { return null; }
    }

    function _clearState() {
        try { localStorage.removeItem(STORE_KEY); } catch (_) {}
    }

    // ── DOM helpers ──────────────────────────────────────────────────────────

    function $(id) { return document.getElementById(id); }

    function escapeHtml(text) {
        const d = document.createElement('div');
        d.textContent = String(text ?? '');
        return d.innerHTML;
    }

    // ── Public API (called from inline onclick) ───────────────────────────────

    window.Explorer = {
        send()         { _send(); },
        cancel()       { if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; } },
        clear()        { _clear(); },
        setScope(s)    { _setScope(s); },
        ask(question)  {
            const input = $('fla-input');
            if (input) { input.value = question; _send(); }
        },

        suggest(question) {
            const input = $('fla-input');
            if (input) { input.value = question; input.focus(); }
        },

        setFeature(name)   { activeFeature = name || null; },
        clearFeature()     { activeFeature = null; },

        _toggleCode(codeId, btn) {
            const el = $(codeId);
            if (!el) return;
            el.hidden = !el.hidden;
            btn.classList.toggle('fla-icon-active', !el.hidden);
        },

        _copyCode(codeId, btn) {
            const el = $(codeId);
            const pre = el && el.querySelector('pre');
            if (!pre) return;
            navigator.clipboard.writeText(pre.textContent).then(function () {
                btn.classList.add('fla-icon-flash');
                setTimeout(function () { btn.classList.remove('fla-icon-flash'); }, 1200);
            });
        },

        _copyImg: async function (chartId, btn) {
            const div = $(chartId);
            if (!div || typeof Plotly === 'undefined') return;
            let dataUrl;
            try {
                dataUrl = await Plotly.toImage(div, { format: 'png', scale: 2 });
                const blob = await (await fetch(dataUrl)).blob();
                await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                btn.classList.add('fla-icon-flash');
                setTimeout(function () { btn.classList.remove('fla-icon-flash'); }, 1200);
            } catch (_) {
                if (dataUrl) window.open(dataUrl, '_blank');
            }
        },
    };

    // ── Scope toggle ─────────────────────────────────────────────────────────

    function _setScope(s) {
        scope = s;
        document.querySelectorAll('.fla-scope-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.scope === s);
        });
        const label = $('fla-scope-label');
        if (label) label.textContent = s === 'filtered' ? '(using active filters)' : '(all data)';
    }

    // ── Send ─────────────────────────────────────────────────────────────────

    async function _send() {
        const input = $('fla-input');
        const message = input ? input.value.trim() : '';
        if (!message) return;
        input.value = '';
        pendingQuestion = message;
        // Record in history (avoid consecutive duplicates)
        if (inputHistory[inputHistory.length - 1] !== message) inputHistory.push(message);
        historyIdx = -1;
        historyDraft = '';

        _setBusy(true);
        _appendMsg('user', message);
        const loadId = _appendLoading();

        const activeFilters = (typeof globalFilterState !== 'undefined')
            ? (globalFilterState.activeFilters || []) : [];

        abortCtrl = new AbortController();
        try {
            const res = await fetch(QUERY_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    session_id: sessionId,
                    scope,
                    active_filters: activeFilters,
                    active_feature: activeFeature,
                }),
                signal: abortCtrl.signal,
            });

            const data = await res.json();
            _removeLoading(loadId);

            if (!data.success) {
                _appendMsg('error', data.error || 'An error occurred');
                _clearLoadingBlock();
            } else {
                sessionId = data.session_id;
                _renderResult(data);
                _appendMsg('assistant', data.answer);
                _saveState(data);
            }
        } catch (err) {
            _removeLoading(loadId);
            _clearLoadingBlock();
            _appendMsg('error', err.name === 'AbortError' ? 'Request cancelled' : 'Request failed: ' + err.message);
        }

        _setBusy(false);
        abortCtrl = null;
    }

    // ── Clear ─────────────────────────────────────────────────────────────────

    async function _clear() {
        if (sessionId) {
            try {
                await fetch(CLEAR_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId }),
                });
            } catch (_) {}
            sessionId = null;
        }
        inputHistory = [];
        const msgs = $('fla-messages');
        if (msgs) msgs.innerHTML = '';
        _clearState();
        _showWelcome();
    }

    function _showWelcome() {
        const results = $('fla-results');
        if (results) results.innerHTML = `
            <div class="fla-no-results">
                <h3>${escapeHtml(cfg.welcome_title || 'Data Explorer')}</h3>
                <p>${escapeHtml(cfg.welcome_text || '')}</p>
            </div>`;
    }

    // ── Build result HTML (shared between modes) ──────────────────────────────

    function _buildResultHtml(data, chartId) {
        let html = `<div class="fla-answer">${escapeHtml(data.answer)}</div>`;

        const qr = data.query_result;
        if (qr?.success && Array.isArray(qr.data) && qr.data.length) {
            // Suppress raw data tables when a chart is present and show_table is false.
            // In scroll mode large tables bury previous results; suppress by default when charting.
            if (chartId && qr.data.length > 20 && cfg.show_table === false) {
                html += `<p class="fla-trunc">Table suppressed (${qr.data.length} rows) — see chart above.</p>`;
            } else {
                const cols = qr.columns || Object.keys(qr.data[0]);
                html += '<div class="fla-table-wrap"><h3>Data Table</h3>';
                html += '<table><thead><tr>';
                cols.forEach(c => { html += `<th>${escapeHtml(c)}</th>`; });
                html += '</tr></thead><tbody>';
                qr.data.slice(0, 100).forEach(row => {
                    html += '<tr>';
                    cols.forEach(c => {
                        let v = row[c];
                        if (typeof v === 'number') v = v.toLocaleString();
                        html += `<td>${escapeHtml(v ?? '')}</td>`;
                    });
                    html += '</tr>';
                });
                html += '</tbody></table>';
                if (qr.data.length > 100) {
                    html += `<p class="fla-trunc">Showing first 100 of ${qr.data.length} rows</p>`;
                }
                html += '</div>';
            }
        }

        if (data.query_error) html += _errorBanner('Query error', data.query_error);
        if (data.fig_error)   html += _errorBanner('Chart error', data.fig_error);

        if (data.metadata) {
            const tokens = (data.metadata.input_tokens || 0) + (data.metadata.output_tokens || 0);
            html += `<div class="fla-meta">Tokens: ${tokens} | Model: ${escapeHtml(data.metadata.model)}</div>`;
        }

        // Icon toolbar: toggle code / copy code / copy chart image
        if (data.code_snippet || chartId) {
            const codeId = 'fla-code-' + Date.now();
            const ICO_CODE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>';
            const ICO_COPY = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
            const ICO_IMG  = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>';

            const codeBtn = data.code_snippet
                ? `<button class="fla-icon-btn" title="Show/hide code" onclick="Explorer._toggleCode('${codeId}',this)">${ICO_CODE}</button>
                   <button class="fla-icon-btn" title="Copy code" onclick="Explorer._copyCode('${codeId}',this)">${ICO_COPY}</button>`
                : '';
            const imgBtn = chartId
                ? `<button class="fla-icon-btn" title="Copy chart as image" onclick="Explorer._copyImg('${chartId}',this)">${ICO_IMG}</button>`
                : '';

            html += `<div class="fla-result-toolbar">${codeBtn}${imgBtn}</div>`;
            if (data.code_snippet) {
                html += `<div class="fla-code-block" id="${codeId}" hidden><pre>${escapeHtml(data.code_snippet)}</pre></div>`;
            }
        }

        // Prepend chart placeholder if needed
        if (chartId) {
            html = `<div class="fla-chart" id="${chartId}"></div>` + html;
        }

        return html;
    }

    function _renderChart(chartId, fig_json) {
        if (!chartId || !fig_json) return;
        setTimeout(() => {
            const div = $(chartId);
            if (!div) return;
            try {
                const fig = JSON.parse(fig_json);
                const layout = Object.assign({
                    margin: { t: 50, r: 20, b: 60, l: 60 },
                    paper_bgcolor: 'white',
                    plot_bgcolor: '#fafafa',
                    font: { size: 12 },
                }, fig.layout || {});
                Plotly.newPlot(div, fig.data || [], layout, { responsive: true, displayModeBar: false });
            } catch (e) {
                div.innerHTML = `<p class="fla-chart-err">Chart render error: ${escapeHtml(e.message)}</p>`;
            }
        }, 50);
    }

    // ── Render result ─────────────────────────────────────────────────────────

    function _renderResult(data) {
        const results = $('fla-results');
        if (!results) return;

        const chartId = data.fig_json ? ('fla-chart-' + Date.now()) : null;
        const html = _buildResultHtml(data, chartId);

        if (RESULTS_MODE === 'scroll') {
            // Build a result block and replace the loading placeholder
            const block = document.createElement('div');
            block.className = 'fla-result-block';
            block.innerHTML =
                `<div class="fla-result-q">${escapeHtml(pendingQuestion)}</div>` + html;

            const loader = results.querySelector('.fla-result-loading');
            if (loader) loader.replaceWith(block);
            else results.appendChild(block);

            results.scrollTop = results.scrollHeight;
        } else {
            // Single-pane: replace entire results panel
            results.innerHTML = html;
        }

        _renderChart(chartId, data.fig_json);
    }

    function _errorBanner(label, msg) {
        return `<div class="fla-error-banner"><strong>${escapeHtml(label)}:</strong> ${escapeHtml(msg)}</div>`;
    }

    function _clearLoadingBlock() {
        const results = $('fla-results');
        if (!results) return;
        const loader = results.querySelector('.fla-result-loading');
        if (loader) loader.remove();
        // If scroll mode and now empty, show welcome
        if (RESULTS_MODE === 'scroll' && !results.querySelector('.fla-result-block')) {
            _showWelcome();
        }
    }

    // ── Chat sidebar messages ─────────────────────────────────────────────────

    function _appendMsg(role, text) {
        const msgs = $('fla-messages');
        if (!msgs) return;
        const div = document.createElement('div');
        div.className = `fla-msg fla-msg-${role}`;
        const preview = role === 'assistant'
            ? escapeHtml(text.substring(0, 120)) + (text.length > 120 ? '…' : '')
            : escapeHtml(text);
        div.innerHTML = `<span class="fla-msg-role">${role === 'user' ? 'You' : role === 'error' ? 'Error' : 'AI'}</span>${preview}`;
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function _appendLoading() {
        const msgs = $('fla-messages');
        if (!msgs) return null;
        const id = 'fla-load-' + Date.now();
        const div = document.createElement('div');
        div.id = id;
        div.className = 'fla-msg fla-msg-loading';
        div.innerHTML = '<span class="fla-spinner"></span>Processing…';
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;

        const results = $('fla-results');
        if (results) {
            if (RESULTS_MODE === 'scroll') {
                // Remove welcome message on first query
                const welcome = results.querySelector('.fla-no-results');
                if (welcome) welcome.remove();
                // Append a loading block at the bottom
                const block = document.createElement('div');
                block.className = 'fla-result-block fla-result-loading';
                block.innerHTML = `
                    <div class="fla-result-q">${escapeHtml(pendingQuestion)}</div>
                    <div class="fla-loading-panel">
                        <span class="fla-spinner fla-spinner-lg"></span>
                        <p>Processing…</p>
                    </div>`;
                results.appendChild(block);
                results.scrollTop = results.scrollHeight;
            } else {
                results.innerHTML = `
                    <div class="fla-loading-panel">
                        <span class="fla-spinner fla-spinner-lg"></span>
                        <p>Processing your question…</p>
                    </div>`;
            }
        }

        return id;
    }

    function _removeLoading(id) {
        const el = $(id);
        if (el) el.remove();
    }

    // ── Busy state ────────────────────────────────────────────────────────────

    function _setBusy(busy) {
        const send   = $('fla-send');
        const cancel = $('fla-cancel');
        if (send)   send.style.display   = busy ? 'none' : '';
        if (cancel) cancel.style.display = busy ? '' : 'none';
    }

    // ── Init ──────────────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', function () {
        // Restore persisted state from previous visit
        const saved = _loadState();
        if (saved && saved.sessionId) {
            sessionId    = saved.sessionId;
            inputHistory = saved.inputHistory || [];

            const msgs = $('fla-messages');
            if (msgs && saved.messagesHtml) msgs.innerHTML = saved.messagesHtml;

            if (saved.lastResult) {
                _renderResult(saved.lastResult);
            }
        }

        const input = $('fla-input');
        if (input) {
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault(); _send();
                } else if (e.key === 'ArrowUp') {
                    if (inputHistory.length === 0) return;
                    e.preventDefault();
                    if (historyIdx === -1) {
                        historyDraft = input.value;
                        historyIdx = inputHistory.length - 1;
                    } else if (historyIdx > 0) {
                        historyIdx--;
                    }
                    input.value = inputHistory[historyIdx];
                    input.setSelectionRange(input.value.length, input.value.length);
                } else if (e.key === 'ArrowDown') {
                    if (historyIdx === -1) return;
                    e.preventDefault();
                    if (historyIdx < inputHistory.length - 1) {
                        historyIdx++;
                        input.value = inputHistory[historyIdx];
                    } else {
                        historyIdx = -1;
                        input.value = historyDraft;
                    }
                    input.setSelectionRange(input.value.length, input.value.length);
                }
            });
        }
        if (cfg.defaultScope) _setScope(cfg.defaultScope);
    });

}());
