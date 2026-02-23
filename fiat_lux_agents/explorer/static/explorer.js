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

    let sessionId      = null;
    let abortCtrl      = null;
    let scope          = cfg.defaultScope || 'all';
    let pendingQuestion = '';   // used in scroll mode to label each result block

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
        const msgs = $('fla-messages');
        if (msgs) msgs.innerHTML = '';
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

        if (data.query_error) html += _errorBanner('Query error', data.query_error);
        if (data.fig_error)   html += _errorBanner('Chart error', data.fig_error);

        if (data.metadata) {
            const tokens = (data.metadata.input_tokens || 0) + (data.metadata.output_tokens || 0);
            html += `<div class="fla-meta">Tokens: ${tokens} | Model: ${escapeHtml(data.metadata.model)}</div>`;
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
        const input = $('fla-input');
        if (input) {
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _send(); }
            });
        }
        if (cfg.defaultScope) _setScope(cfg.defaultScope);
    });

}());
