/* ==========================================================================
   电商风险控制系统 - 前端单页应用（原生 JS + Hash 路由）
   所有业务数据均来自后端 API，无任何外部依赖
   ========================================================================== */
(function () {
    'use strict';

    /* ---------------------------------------------------------------------
     * 基础工具与状态
     * ------------------------------------------------------------------- */
    const $ = (selector, scope) => (scope || document).querySelector(selector);
    const $$ = (selector, scope) => Array.prototype.slice.call((scope || document).querySelectorAll(selector));

    const state = {
        meta: null,
        demos: [],
        users: [],
        reviewers: [],
        features: [],
        featureGroups: [],
        featureMap: {},
        dicts: { event: {}, level: {}, decision: {}, caseStatus: {}, blacklist: {}, blacklistBonus: {} },
        page: 'check',
        params: new URLSearchParams(),
        renderToken: 0,
        lastCheckPayload: null,
        rules: [],
        rulesFilter: { keyword: '', status: '' },
        casesFilter: { status: '', level: '', keyword: '' },
        blacklistFilter: { type: '', status: '', keyword: '' },
        profileUser: 'U1001'
    };

    const API = {
        async request(path, options) {
            const config = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
            const response = await fetch(path, config);
            if (!response.ok) {
                let message = '请求失败（HTTP ' + response.status + '）';
                try {
                    const body = await response.json();
                    if (body && body.detail) {
                        message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
                    }
                } catch (error) { /* 保留默认错误信息 */ }
                const err = new Error(message);
                err.status = response.status;
                throw err;
            }
            return response.json();
        },
        get(path, params) {
            let url = path;
            if (params) {
                const query = Object.keys(params)
                    .filter((key) => params[key] !== undefined && params[key] !== null && params[key] !== '')
                    .map((key) => encodeURIComponent(key) + '=' + encodeURIComponent(params[key]))
                    .join('&');
                if (query) url += (url.indexOf('?') >= 0 ? '&' : '?') + query;
            }
            return API.request(url);
        },
        post(path, body) {
            return API.request(path, { method: 'POST', body: JSON.stringify(body || {}) });
        }
    };

    const ICONS = {
        shield: '<path d="M12 2.8l7.2 3.1v5.3c0 4.7-3.1 8.4-7.2 9.9-4.1-1.5-7.2-5.2-7.2-9.9V5.9L12 2.8z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8.8 12.1l2.1 2.1 4.3-4.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        search: '<circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.8"/><path d="M16.5 16.5L21 21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
        plus: '<path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
        refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        edit: '<path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17v3z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M13.5 7.5l3 3" stroke="currentColor" stroke-width="1.7"/>',
        trash: '<path d="M4 7h16M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2M6.5 7l.8 12a2 2 0 002 1.9h5.4a2 2 0 002-1.9l.8-12" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 11v6M14 11v6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        close: '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
        chevron: '<path d="M9 5l7 7-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        filter: '<path d="M4 5h16l-6.2 7.2V20l-3.6-2v-5.8L4 5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
        bolt: '<path d="M13.2 2.5L4.5 13h5.4l-1 8.5L19.5 10h-5.6l-.7-7.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
        clock: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 7.5V12l3 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        users: '<circle cx="9" cy="8" r="3.2" stroke="currentColor" stroke-width="1.7"/><path d="M3.5 19c.5-3.2 2.8-5 5.5-5s5 1.8 5.5 5M16 5.5a3 3 0 010 5.8M17.5 14.2c1.8.6 3 2.1 3.3 4.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        order: '<path d="M6 3.5h9l3 3v14H6v-17z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M9 9h6M9 13h6M9 17h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        alert: '<path d="M12 3.5L22 20H2L12 3.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 9v5M12 17.2v.3" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
        folder: '<path d="M3.5 7.5a2 2 0 012-2h4l2 2.2h7a2 2 0 012 2v8a2 2 0 01-2 2h-13a2 2 0 01-2-2V7.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 13.5h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        ban: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M6 6l12 12" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
        check: '<path d="M4.5 12.5l4.5 4.5L19.5 6.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        checkCircle: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M8 12.2l2.6 2.6 5.4-5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        xCircle: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M9 9l6 6M15 9l-6 6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        info: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 11v5M12 7.6v.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
        arrowUpRight: '<path d="M7 17L17 7M9 7h8v8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        phone: '<rect x="7" y="2.8" width="10" height="18.4" rx="2.2" stroke="currentColor" stroke-width="1.7"/><path d="M10.5 18.2h3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        device: '<rect x="3.5" y="4.5" width="17" height="11.5" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M8 20h8M12 16v4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        ip: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M3.8 9h16.4M3.8 15h16.4M12 3.5c2.5 2.4 3.8 5.2 3.8 8.5S14.5 18.1 12 20.5C9.5 18.1 8.2 15.3 8.2 12S9.5 5.9 12 3.5z" stroke="currentColor" stroke-width="1.4"/>',
        address: '<path d="M12 21s7-5.2 7-11a7 7 0 10-14 0c0 5.8 7 11 7 11z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="12" cy="10" r="2.4" stroke="currentColor" stroke-width="1.7"/>',
        user: '<circle cx="12" cy="8" r="3.6" stroke="currentColor" stroke-width="1.7"/><path d="M5 20c.6-3.5 3.3-5.6 7-5.6s6.4 2.1 7 5.6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
        list: '<rect x="4" y="3.5" width="16" height="17" rx="2.5" stroke="currentColor" stroke-width="1.7"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        download: '<path d="M12 3.5v11M7.5 10.5L12 15l4.5-4.5M4 19.5h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        upload: '<path d="M12 15.5v-11M7.5 8.5L12 4l4.5 4.5M4 19.5h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        play: '<path d="M8 5.5v13l11-6.5L8 5.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
        spark: '<path d="M12 2.8l1.8 5.4 5.4 1.8-5.4 1.8L12 17.2l-1.8-5.4-5.4-1.8 5.4-1.8L12 2.8z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
        arrowRight: '<path d="M4 12h15M14 6.5l5.5 5.5-5.5 5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
        tool: '<path d="M14.5 6.5a4.5 4.5 0 00-6 6L3.5 17.5a2.1 2.1 0 003 3l5-5a4.5 4.5 0 006-6l-2.7 2.7-3-3 2.7-2.7z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>'
    };

    function icon(name, className) {
        return '<svg class="' + (className || '') + '" viewBox="0 0 24 24" fill="none" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
    }

    const PAGE_TITLES = {
        check: '风险检查', rules: '规则管理', cases: '案件管理',
        blacklist: '黑名单管理', profile: '用户画像', dashboard: '运营看板'
    };
    const LEVEL_COLORS = { low: '#12b76a', medium: '#f79009', high: '#f04438' };
    const BLACKLIST_COLORS = { user: '#f04438', phone: '#f79009', address: '#7a5af8', device: '#0e9384', ip: '#2f6bff' };

    function esc(value) {
        return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, (ch) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[ch]));
    }

    function attr(value) { return esc(value); }

    function fmtNumber(value, digits) {
        const number = Number(value);
        if (!isFinite(number)) return '0';
        const d = digits === undefined ? 1 : digits;
        return number.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: d });
    }

    function fmtMoney(value) {
        return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function fmtPct(value, digits) {
        return (Number(value || 0) * 100).toFixed(digits === undefined ? 1 : digits) + '%';
    }

    function fmtTimeShort(value) {
        if (!value) return '—';
        const text = String(value);
        return text.length >= 16 ? text.slice(5, 16) : text;
    }

    function fmtTimeFull(value) {
        if (!value) return '—';
        const text = String(value);
        return text.length >= 16 ? text.slice(0, 16) : text;
    }

    function labelOf(map, key, fallback) {
        if (map && map[key]) return map[key];
        return fallback || key || '—';
    }

    function levelBadge(level, label) {
        return '<span class="badge badge-' + attr(level || 'neutral') + '"><span class="dot"></span>' + esc(label || labelOf(state.dicts.level, level)) + '</span>';
    }

    function decisionBadge(decision, label) {
        const cls = decision === 'pass' ? 'pass' : (decision === 'manual_review' ? 'manual' : (decision === 'reject' ? 'reject' : 'neutral'));
        return '<span class="badge badge-' + cls + '">' + esc(label || labelOf(state.dicts.decision, decision)) + '</span>';
    }

    function caseStatusBadge(status, label) {
        const clsMap = { pending: 'medium', reviewing: 'info', approved: 'low', rejected: 'high', resolved: 'teal' };
        return '<span class="badge badge-' + (clsMap[status] || 'neutral') + '"><span class="dot"></span>' + esc(label || labelOf(state.dicts.caseStatus, status)) + '</span>';
    }

    function blacklistTypeBadge(type, label) {
        const clsMap = { user: 'high', phone: 'medium', address: 'purple', device: 'teal', ip: 'info' };
        return '<span class="badge badge-' + (clsMap[type] || 'neutral') + '">' + esc(label || labelOf(state.dicts.blacklist, type)) + '</span>';
    }

    function debounce(fn, wait) {
        let timer = null;
        return function () {
            const args = arguments;
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(null, args), wait || 280);
        };
    }

    /* ---------------------------------------------------------------------
     * Toast / 弹窗 / 抽屉
     * ------------------------------------------------------------------- */
    function toast(message, type, title) {
        const container = $('#toast-container');
        if (!container) return;
        const kind = type || 'success';
        const iconName = kind === 'error' ? 'xCircle' : (kind === 'warning' ? 'alert' : 'checkCircle');
        const defaultTitle = kind === 'error' ? '操作失败' : (kind === 'warning' ? '提示' : '操作成功');
        const node = document.createElement('div');
        node.className = 'toast ' + kind;
        node.innerHTML = '<span class="toast-icon">' + icon(iconName) + '</span><div class="toast-text"><strong>' +
            esc(title || defaultTitle) + '</strong><span>' + esc(message) + '</span></div>';
        container.appendChild(node);
        setTimeout(() => {
            node.style.opacity = '0';
            node.style.transform = 'translateX(16px)';
            node.style.transition = 'all .2s ease';
            setTimeout(() => node.remove(), 220);
        }, 3600);
    }

    function syncBodyLock() {
        const hasModal = !!$('#modal-root .modal-overlay');
        const hasDrawer = !!$('#drawer-root .drawer-overlay');
        document.body.style.overflow = (hasModal || hasDrawer) ? 'hidden' : '';
    }

    function openModal(panelHtml, onMount) {
        const root = $('#modal-root');
        root.innerHTML = '<div class="modal-overlay">' + panelHtml + '</div>';
        const overlay = root.firstElementChild;
        if (overlay) {
            overlay.addEventListener('click', (event) => {
                if (event.target === overlay) closeModal();
            });
            $$('[data-close-modal]', overlay).forEach((button) => {
                button.addEventListener('click', closeModal);
            });
        }
        syncBodyLock();
        if (onMount) onMount(root);
    }

    function closeModal() {
        $('#modal-root').innerHTML = '';
        syncBodyLock();
    }

    function openConfirm(options) {
        const danger = options.danger !== false;
        openModal(
            '<div class="modal-panel">' +
                '<div class="modal-head">' +
                    '<div class="modal-head-icon" style="' + (danger ? 'background:#fef3f2;color:#b42318' : '') + '">' + icon(danger ? 'alert' : 'info') + '</div>' +
                    '<div class="modal-head-text"><h3>' + esc(options.title || '确认操作') + '</h3><p>' + esc(options.subtitle || '该操作会立即生效') + '</p></div>' +
                    '<button class="modal-close" data-close-modal type="button">' + icon('close') + '</button>' +
                '</div>' +
                '<div class="confirm-body"><p>' + (options.message || '确认执行该操作吗？') + '</p>' +
                    (options.warning ? '<div class="confirm-warning">' + esc(options.warning) + '</div>' : '') +
                '</div>' +
                '<div class="modal-foot"><button class="btn" data-close-modal type="button">取消</button>' +
                    '<button class="btn ' + (danger ? 'btn-danger' : 'btn-primary') + '" id="confirm-action" type="button">' + esc(options.confirmText || '确认') + '</button></div>' +
            '</div>',
            (root) => {
                const button = $('#confirm-action', root);
                button.addEventListener('click', async () => {
                    button.disabled = true;
                    try {
                        await options.onConfirm();
                        closeModal();
                    } catch (error) {
                        toast(error.message, 'error');
                        button.disabled = false;
                    }
                });
            }
        );
    }

    function closeDrawer() {
        $('#drawer-root').innerHTML = '';
        syncBodyLock();
    }

    /* ---------------------------------------------------------------------
     * 图表
     * ------------------------------------------------------------------- */
    function gaugeSvg(score, level, size) {
        const value = Math.max(0, Math.min(100, Number(score) || 0));
        const radius = 50;
        const circumference = 2 * Math.PI * radius;
        const offset = circumference * (1 - value / 100);
        const color = LEVEL_COLORS[level] || '#2f6bff';
        const dim = size || 122;
        return '<svg class="gauge-svg" width="' + dim + '" height="' + dim + '" viewBox="0 0 120 120" role="img" aria-label="风险评分 ' + value + '">' +
            '<circle cx="60" cy="60" r="' + radius + '" fill="none" stroke="#edf1f7" stroke-width="9"/>' +
            '<circle cx="60" cy="60" r="' + radius + '" fill="none" stroke="' + color + '" stroke-width="9" stroke-linecap="round" ' +
                'stroke-dasharray="' + circumference.toFixed(2) + '" stroke-dashoffset="' + offset.toFixed(2) + '" transform="rotate(-90 60 60)"/>' +
            '<text x="60" y="59" text-anchor="middle" class="gauge-score-text" fill="' + color + '">' + value.toFixed(1) + '</text>' +
            '<text x="60" y="74" text-anchor="middle" class="gauge-sub-text">风险评分</text>' +
        '</svg>';
    }

    function lineChartSvg(trend) {
        const width = 640, height = 230;
        const pad = { left: 34, right: 14, top: 18, bottom: 26 };
        const points = trend || [];
        const maxRaw = Math.max(1, ...points.map((item) => Math.max(Number(item.event_count) || 0, Number(item.high_count) || 0)));
        const maxValue = Math.max(4, Math.ceil(maxRaw / 4) * 4);
        const innerW = width - pad.left - pad.right;
        const innerH = height - pad.top - pad.bottom;
        const stepX = points.length > 1 ? innerW / (points.length - 1) : 0;
        const xAt = (index) => pad.left + (points.length > 1 ? index * stepX : innerW / 2);
        const yAt = (value) => pad.top + innerH * (1 - (Number(value) || 0) / maxValue);
        let grid = '';
        for (let i = 0; i <= 4; i += 1) {
            const value = (maxValue / 4) * i;
            const y = yAt(value);
            grid += '<line x1="' + pad.left + '" y1="' + y + '" x2="' + (width - pad.right) + '" y2="' + y + '" stroke="#eef1f6" stroke-width="1" stroke-dasharray="' + (i === 0 ? '0' : '3 4') + '"/>' +
                '<text x="' + (pad.left - 7) + '" y="' + (y + 3) + '" text-anchor="end" font-size="8" fill="#98a2b3">' + Math.round(value) + '</text>';
        }
        const eventPoints = points.map((item, index) => [xAt(index), yAt(item.event_count)]);
        const highPoints = points.map((item, index) => [xAt(index), yAt(item.high_count)]);
        const linePath = (pts) => pts.map((point, index) => (index === 0 ? 'M' : 'L') + point[0].toFixed(1) + ' ' + point[1].toFixed(1)).join(' ');
        const areaPath = eventPoints.length
            ? 'M' + eventPoints[0][0].toFixed(1) + ' ' + (pad.top + innerH) + ' ' +
              eventPoints.map((point) => 'L' + point[0].toFixed(1) + ' ' + point[1].toFixed(1)).join(' ') +
              ' L' + eventPoints[eventPoints.length - 1][0].toFixed(1) + ' ' + (pad.top + innerH) + ' Z'
            : '';
        let xLabels = '';
        points.forEach((item, index) => {
            xLabels += '<text x="' + xAt(index) + '" y="' + (height - 8) + '" text-anchor="middle" font-size="8" fill="#98a2b3">' + esc(item.label || '') + '</text>';
        });
        let dots = '';
        highPoints.forEach((point, index) => {
            const value = points[index].high_count || 0;
            dots += '<circle cx="' + point[0].toFixed(1) + '" cy="' + point[1].toFixed(1) + '" r="' + (value > 0 ? 3 : 2) + '" fill="#fff" stroke="#f04438" stroke-width="1.8"/>';
            if (value > 0) {
                dots += '<text x="' + point[0].toFixed(1) + '" y="' + (point[1].toFixed(1) - 7) + '" text-anchor="middle" font-size="8" font-weight="700" fill="#b42318">' + value + '</text>';
            }
        });
        return '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="近7日风险趋势">' +
            '<defs><linearGradient id="riskAreaGradient" x1="0" y1="0" x2="0" y2="1">' +
                '<stop offset="0%" stop-color="#2f6bff" stop-opacity=".18"/><stop offset="100%" stop-color="#2f6bff" stop-opacity="0"/>' +
            '</linearGradient></defs>' +
            grid +
            (areaPath ? '<path d="' + areaPath + '" fill="url(#riskAreaGradient)"/>' : '') +
            '<path d="' + linePath(eventPoints) + '" fill="none" stroke="#2f6bff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>' +
            '<path d="' + linePath(highPoints) + '" fill="none" stroke="#f04438" stroke-width="1.8" stroke-dasharray="5 4" stroke-linecap="round"/>' +
            dots + xLabels +
        '</svg>';
    }

    function donutSvg(segments, size, centerValue, centerLabel) {
        const dim = size || 176;
        const radius = 62;
        const circumference = 2 * Math.PI * radius;
        const total = segments.reduce((sum, item) => sum + Number(item.value || 0), 0);
        let offset = 0;
        let circles = '';
        segments.forEach((segment) => {
            const value = Number(segment.value || 0);
            if (value <= 0 || total <= 0) return;
            const length = (value / total) * circumference;
            circles += '<circle cx="90" cy="90" r="' + radius + '" fill="none" stroke="' + segment.color + '" stroke-width="15" ' +
                'stroke-dasharray="' + length.toFixed(2) + ' ' + (circumference - length).toFixed(2) + '" ' +
                'stroke-dashoffset="' + (-offset).toFixed(2) + '" transform="rotate(-90 90 90)" stroke-linecap="butt"/>';
            offset += length;
        });
        return '<svg class="donut-svg" width="' + dim + '" height="' + dim + '" viewBox="0 0 180 180" role="img" aria-label="等级分布">' +
            '<circle cx="90" cy="90" r="' + radius + '" fill="none" stroke="#f0f3f8" stroke-width="15"/>' + circles +
            '<text x="90" y="88" text-anchor="middle" font-size="24" font-weight="800" fill="#101828">' + esc(centerValue) + '</text>' +
            '<text x="90" y="103" text-anchor="middle" font-size="8" fill="#98a2b3">' + esc(centerLabel || '评估总数') + '</text>' +
        '</svg>';
    }

    function scoreTrendSvg(trend) {
        const points = trend || [];
        const width = 320, height = 158;
        const pad = { left: 24, right: 12, top: 16, bottom: 24 };
        const innerW = width - pad.left - pad.right;
        const innerH = height - pad.top - pad.bottom;
        const stepX = points.length > 1 ? innerW / (points.length - 1) : 0;
        const xAt = (index) => pad.left + (points.length > 1 ? index * stepX : innerW / 2);
        const yAt = (score) => pad.top + innerH * (1 - Math.max(0, Math.min(100, Number(score) || 0)) / 100);
        let grid = '';
        [0, 50, 100].forEach((value) => {
            const y = yAt(value);
            grid += '<line x1="' + pad.left + '" y1="' + y + '" x2="' + (width - pad.right) + '" y2="' + y + '" stroke="#eef1f6" stroke-dasharray="3 4"/>' +
                '<text x="' + (pad.left - 6) + '" y="' + (y + 3) + '" text-anchor="end" font-size="7.5" fill="#98a2b3">' + value + '</text>';
        });
        const coords = points.map((item, index) => [xAt(index), yAt(item.risk_score)]);
        const path = coords.map((point, index) => (index === 0 ? 'M' : 'L') + point[0].toFixed(1) + ' ' + point[1].toFixed(1)).join(' ');
        const area = coords.length
            ? 'M' + coords[0][0].toFixed(1) + ' ' + (pad.top + innerH) + ' ' + coords.map((point) => 'L' + point[0].toFixed(1) + ' ' + point[1].toFixed(1)).join(' ') + ' L' + coords[coords.length - 1][0].toFixed(1) + ' ' + (pad.top + innerH) + ' Z'
            : '';
        let dots = '';
        points.forEach((item, index) => {
            const point = coords[index];
            const color = LEVEL_COLORS[item.risk_level] || '#2f6bff';
            dots += '<circle cx="' + point[0].toFixed(1) + '" cy="' + point[1].toFixed(1) + '" r="3.2" fill="#fff" stroke="' + color + '" stroke-width="2"/>';
            dots += '<text x="' + point[0].toFixed(1) + '" y="' + (point[1].toFixed(1) - 7) + '" text-anchor="middle" font-size="7.5" font-weight="700" fill="' + color + '">' + Math.round(item.risk_score) + '</text>';
        });
        let labels = '';
        points.forEach((item, index) => {
            if (points.length > 6 && index % 2 === 1) return;
            labels += '<text x="' + xAt(index) + '" y="' + (height - 8) + '" text-anchor="middle" font-size="7" fill="#98a2b3">' + esc((item.date || '').slice(5)) + '</text>';
        });
        return '<svg class="chart-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="用户风险趋势">' +
            '<defs><linearGradient id="profileAreaGradient" x1="0" y1="0" x2="0" y2="1">' +
                '<stop offset="0%" stop-color="#2f6bff" stop-opacity=".16"/><stop offset="100%" stop-color="#2f6bff" stop-opacity="0"/>' +
            '</linearGradient></defs>' + grid +
            (area ? '<path d="' + area + '" fill="url(#profileAreaGradient)"/>' : '') +
            (path ? '<path d="' + path + '" fill="none" stroke="#2f6bff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' : '') +
            dots + labels +
        '</svg>';
    }

    /* ---------------------------------------------------------------------
     * 通用 HTML 片段
     * ------------------------------------------------------------------- */
    function pageHead(title, subtitle, actions) {
        return '<div class="page-head"><div class="page-title-wrap"><h1>' + esc(title) + '</h1><p>' + subtitle + '</p></div>' +
            '<div class="head-actions">' + (actions || '') + '</div></div>';
    }

    function emptyState(iconName, title, description, actions) {
        return '<div class="empty-state"><div class="empty-icon">' + icon(iconName || 'shield') + '</div>' +
            '<h3>' + esc(title) + '</h3><p>' + esc(description) + '</p>' +
            (actions ? '<div class="empty-actions">' + actions + '</div>' : '') + '</div>';
    }

    function pageError(message) {
        return '<div class="card">' + emptyState('alert', '页面加载失败', message, '<button class="btn btn-primary" onclick="location.reload()">重新加载</button>') + '</div>';
    }

    function statCard(iconName, colorClass, label, value, sub) {
        return '<div class="card stat-card"><div class="stat-icon ' + colorClass + '">' + icon(iconName) + '</div>' +
            '<div class="stat-info"><span>' + esc(label) + '</span><strong>' + value + '</strong><small>' + esc(sub || '') + '</small></div></div>';
    }

    function kpiCard(iconName, colorClass, label, value, unit, sub) {
        return '<div class="card kpi-card"><div class="kpi-icon ' + colorClass + '">' + icon(iconName) + '</div>' +
            '<div class="kpi-label">' + esc(label) + '</div><div class="kpi-value">' + value + (unit ? '<small>' + esc(unit) + '</small>' : '') + '</div>' +
            '<div class="kpi-sub">' + sub + '</div></div>';
    }

    function featureValueInfo(key, value) {
        const meta = state.featureMap[key] || {};
        const pctKeys = ['user_refund_rate', 'user_night_order_ratio', 'address_concentration', 'order_discount_rate', 'order_freight_ratio'];
        const flagKeys = ['user_blacklist_hit', 'address_blacklist_hit', 'device_blacklist_hit', 'phone_blacklist_hit', 'ip_blacklist_hit'];
        if (pctKeys.indexOf(key) >= 0) return { text: (Number(value) * 100).toFixed(1) + '%', cls: '' };
        if (key === 'order_amount' || key === 'user_avg_order_amount') return { text: '¥' + fmtMoney(value), cls: '' };
        if (key === 'blacklist_hit_detail') return { text: String(value || '无'), cls: value && value !== '无' ? 'risk text' : 'text' };
        if (flagKeys.indexOf(key) >= 0) return { text: Number(value) === 1 ? '命中' : '未命中', cls: Number(value) === 1 ? 'risk' : '' };
        if (key === 'address_phone_consistency') return { text: Number(value) === 1 ? '一致' : '不一致', cls: Number(value) === 1 ? '' : 'risk' };
        if (key === 'address_province_risk') return { text: Number(value) === 1 ? '偏远地区' : '非偏远', cls: Number(value) === 1 ? 'warn' : '' };
        if (key === 'order_is_new_address' || key === 'user_is_enterprise') return { text: Number(value) === 1 ? '是' : '否', cls: '' };
        if (key === 'event_type') return { text: labelOf(state.dicts.event, value), cls: 'text' };
        if (key === 'blacklist_hit_cnt') return { text: String(value), cls: Number(value) > 0 ? 'risk' : '' };
        if (key === 'user_high_risk_cnt') return { text: String(value), cls: Number(value) > 0 ? 'warn' : '' };
        if (key === 'order_hour') return { text: String(value), unit: '时' };
        if (typeof value === 'number') return { text: fmtNumber(value, Number.isInteger(value) ? 0 : 2), unit: meta.unit || '' };
        return { text: String(value === null || value === undefined ? '—' : value), cls: 'text' };
    }

    function featureGroupsHtml(snapshot) {
        return state.featureGroups.map((group) => {
            const items = state.features.filter((feature) => feature.group === group.group && Object.prototype.hasOwnProperty.call(snapshot, feature.key));
            if (!items.length) return '';
            const rows = items.map((feature) => {
                const info = featureValueInfo(feature.key, snapshot[feature.key]);
                return '<div class="feature-row" data-feature-group="' + attr(group.group) + '">' +
                    '<span class="feature-name" title="' + attr(feature.description) + '">' + esc(feature.name) + '</span>' +
                    '<span class="feature-value ' + (info.cls || '') + '" title="' + attr(JSON.stringify(snapshot[feature.key])) + '">' +
                        esc(info.text) + (info.unit ? '<small>' + esc(info.unit) + '</small>' : '') + '</span></div>';
            }).join('');
            return '<div class="feature-group" data-feature-group="' + attr(group.group) + '">' +
                '<div class="feature-group-title"><span class="fg-dot"></span>' + esc(group.group_name) +
                '<span class="fg-count">' + items.length + ' 项</span></div>' + rows + '</div>';
        }).join('');
    }

    function hitListHtml(hits) {
        if (!hits || !hits.length) return '<div class="hit-empty">未命中风险规则，当前事件风险可控</div>';
        return '<ul class="hit-list">' + hits.map((hit, index) => (
            '<li class="hit-item">' +
                '<div class="hit-head"><span class="hit-code">' + esc(hit.rule_code) + '</span>' +
                    '<span class="hit-name" title="' + attr(hit.rule_name) + '">' + esc(hit.rule_name) + '</span>' +
                    '<span class="hit-score">+' + Number(hit.hit_score).toFixed(1) + '</span></div>' +
                '<div class="hit-reason" title="' + attr(hit.hit_message) + '">' + esc(hit.hit_message) + '</div>' +
                '<div class="hit-meta"><span>优先级 ' + esc(hit.priority) + '</span><span>基准分 ' + esc(hit.rule_score) + '</span>' +
                    '<span>权重 ×' + Number(hit.weight || 1).toFixed(2) + '</span><span>#' + (index + 1) + '</span></div>' +
            '</li>'
        )).join('') + '</ul>';
    }

    function traceHtml(trace) {
        if (!trace || !trace.length) return '<div class="hit-empty">暂无 Agent 轨迹</div>';
        return '<div class="trace-grid">' + trace.map((step) => {
            const statusClass = step.status === 'warning' ? 'warning' : (step.status === 'skipped' ? 'skipped' : '');
            const statusText = step.status === 'warning' ? '注意' : (step.status === 'skipped' ? '跳过' : '完成');
            return '<div class="trace-step ' + statusClass + '">' +
                '<div class="trace-top"><span class="trace-no">' + String(step.step).padStart(2, '0') + '</span>' +
                    '<span class="trace-name">' + esc(step.name) + '</span><span class="trace-status" title="' + statusText + '"></span></div>' +
                '<div class="trace-time">耗时 ' + Number(step.duration_ms).toFixed(2) + ' ms · ' + statusText + '</div>' +
                '<div class="trace-summary" title="' + attr(step.summary) + '">' + esc(step.summary) + '</div>' +
            '</div>';
        }).join('') + '</div>';
    }

    function bindFeatureFilters(scope) {
        $$('[data-feature-filter]', scope).forEach((button) => {
            button.addEventListener('click', () => {
                const group = button.dataset.featureFilter;
                $$('[data-feature-filter]', scope).forEach((item) => item.classList.toggle('active', item === button));
                $$('[data-feature-group]', scope).forEach((item) => {
                    item.style.display = (group === 'all' || item.dataset.featureGroup === group) ? '' : 'none';
                });
            });
        });
    }

    /* ---------------------------------------------------------------------
     * 初始化与路由
     * ------------------------------------------------------------------- */
    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        updateClock();
        setInterval(updateClock, 30000);
        $('#page-content').addEventListener('click', onContentClick);
        $('#page-content').addEventListener('change', onContentChange);
        $('#page-content').addEventListener('input', onContentInput);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                if ($('#modal-root').innerHTML) closeModal();
                else if ($('#drawer-root').innerHTML) closeDrawer();
            }
        });
        try {
            const meta = await API.get('/api/risk/meta');
            state.meta = meta;
            state.features = meta.features.items;
            state.featureGroups = meta.features.groups;
            state.featureMap = {};
            state.features.forEach((feature) => { state.featureMap[feature.key] = feature; });
            state.dicts.event = toMap(meta.event_types);
            state.dicts.level = toMap(meta.risk_levels);
            state.dicts.decision = toMap(meta.decisions);
            state.dicts.caseStatus = toMap(meta.case_statuses);
            state.dicts.blacklist = toMap(meta.blacklist_types);
            state.dicts.blacklistBonus = {};
            meta.blacklist_types.forEach((item) => { state.dicts.blacklistBonus[item.value] = item.bonus_score; });
            try {
                const demoData = await API.get('/api/risk/demo-samples');
                state.demos = demoData.items || [];
            } catch (error) { state.demos = []; }
            try {
                const userData = await API.get('/api/risk/users', { limit: 50 });
                state.users = userData.items || [];
            } catch (error) { state.users = []; }
            state.reviewers = meta.reviewers || [];
            refreshNavBadge();
            window.addEventListener('hashchange', route);
            route();
        } catch (error) {
            $('#page-content').innerHTML = pageError('系统初始化失败：' + error.message);
            $('#breadcrumb-page').textContent = '系统错误';
            toast('无法连接后端服务，请确认 uvicorn 已启动', 'error');
        }
    }

    function toMap(items) {
        const map = {};
        (items || []).forEach((item) => { map[item.value] = item.label; });
        return map;
    }

    function updateClock() {
        const now = new Date();
        const pad = (value) => String(value).padStart(2, '0');
        const week = '日一二三四五六'[now.getDay()];
        const timeEl = $('#clock-time');
        const dateEl = $('#clock-date');
        if (timeEl) timeEl.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes());
        if (dateEl) dateEl.textContent = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + ' 周' + week;
    }

    function parseHash() {
        const raw = window.location.hash.replace(/^#\/?/, '') || 'check';
        const parts = raw.split('?');
        const page = (parts[0] || 'check').split('/')[0];
        return { page: page, params: new URLSearchParams(parts[1] || '') };
    }

    function route() {
        if (!state.meta) return;
        const parsed = parseHash();
        const renderer = {
            check: renderCheck, rules: renderRules, cases: renderCases,
            blacklist: renderBlacklist, profile: renderProfile, dashboard: renderDashboard
        }[parsed.page];
        if (!renderer) {
            window.location.hash = '#/check';
            return;
        }
        state.page = parsed.page;
        state.params = parsed.params;
        state.renderToken += 1;
        setActiveNav(parsed.page);
        $('#breadcrumb-page').textContent = PAGE_TITLES[parsed.page];
        document.title = PAGE_TITLES[parsed.page] + ' · 电商风险控制系统';
        const content = $('#page-content');
        content.innerHTML = '';
        window.scrollTo({ top: 0 });
        closeDrawer();
        renderer(parsed.params).catch((error) => {
            if (state.page !== parsed.page) return;
            content.innerHTML = pageError(error.message || '页面加载失败');
            toast(error.message || '页面加载失败', 'error');
        });
    }

    function setActiveNav(page) {
        $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
    }

    async function refreshNavBadge() {
        try {
            const data = await API.get('/api/risk/cases', { case_status: 'pending', page_size: 1 });
            const badge = $('#nav-case-badge');
            if (badge) {
                badge.textContent = data.total > 99 ? '99+' : String(data.total);
                badge.hidden = !data.total;
            }
        } catch (error) { /* 忽略徽标刷新失败 */ }
    }

    /* ---------------------------------------------------------------------
     * 风险检查页
     * ------------------------------------------------------------------- */
    async function renderCheck(params) {
        const content = $('#page-content');
        content.innerHTML =
            pageHead(
                '风险检查',
                '发起业务事件检查，Agent 自动完成 <span class="accent">39 项特征</span> 与 <span class="accent">30 条规则</span> 的实时评估',
                '<span class="badge badge-info"><span class="dot"></span>实时检测</span><span class="badge badge-neutral">离线可运行</span>'
            ) +
            '<div class="check-layout">' +
                '<section class="card check-form-card">' +
                    '<div class="form-head"><h2>检查参数</h2><span class="tag">四类业务事件</span></div>' +
                    '<form id="check-form" autocomplete="off">' +
                        '<div class="field"><label for="event-type">业务事件类型 <span class="req">*</span></label>' +
                            '<select id="event-type" name="event_type" class="select">' +
                                state.meta.event_types.map((item) => '<option value="' + attr(item.value) + '">' + esc(item.label) + ' · ' + esc(item.value) + '</option>').join('') +
                            '</select></div>' +
                        '<div class="field"><label for="user-id">用户编号 <span class="req">*</span></label>' +
                            '<input id="user-id" name="user_id" class="input" list="user-options" placeholder="例如 U1001" autocomplete="off">' +
                            '<datalist id="user-options">' + state.users.map((user) => '<option value="' + attr(user.user_id) + '">' + esc(user.user_name) + '</option>').join('') + '</datalist></div>' +
                        '<div class="field"><label for="order-id">订单编号 <span class="req">*</span></label>' +
                            '<input id="order-id" name="order_id" class="input" list="order-options" placeholder="例如 O1101" autocomplete="off">' +
                            '<datalist id="order-options"></datalist></div>' +
                        '<div class="field"><label for="source-id">来源编号</label>' +
                            '<input id="source-id" name="source_id" class="input" value="APP" maxlength="50"></div>' +
                        '<div class="field"><label for="demo-select">示例场景 <span class="hint">自动填充真实数据</span></label>' +
                            '<select id="demo-select" class="select"><option value="">选择示例场景</option>' +
                                state.demos.map((sample) => '<option value="' + attr(sample.sample_key) + '">' + esc(sample.label) + ' · ' + esc(sample.event_type_label) + '</option>').join('') +
                            '</select></div>' +
                        '<button type="submit" class="btn btn-primary btn-block" id="check-submit">' + icon('play') + '执行风险检查</button>' +
                    '</form>' +
                    '<div class="form-tip">' + icon('info') + '<span>检查将写入一条真实风险事件，并保存原始入参、特征快照、命中规则与 Agent 轨迹。</span></div>' +
                    '<div class="agent-mini-card">' +
                        '<div class="agent-mini-head"><strong>Agent 编排</strong><span>● 就绪</span></div>' +
                        '<div class="agent-steps">' +
                            ['事件校验', '特征计算', '规则匹配', '评分决策', '黑名单校验', '案件生成'].map((name, index) =>
                                '<div class="agent-step"><i>' + (index + 1) + '</i>' + esc(name) + '</div>').join('') +
                        '</div>' +
                        '<div class="agent-mini-note">确定性编排 · 不调用大模型 · 每一步耗时与状态均留痕</div>' +
                    '</div>' +
                '</section>' +
                '<section class="result-area" id="check-result">' + checkEmptyHtml() + '</section>' +
            '</div>';

        const eventSelect = $('#event-type');
        eventSelect.addEventListener('change', () => {
            $('#source-id').value = eventSelect.value === 'order_create' ? 'WEB' : 'APP';
        });
        $('#demo-select').addEventListener('change', (event) => {
            const sample = state.demos.find((item) => item.sample_key === event.target.value);
            if (sample) fillCheckSample(sample);
        });
        $('#check-form').addEventListener('submit', (event) => {
            event.preventDefault();
            runCheck();
        });

        if (params.get('demo')) {
            const sample = state.demos.find((item) => item.sample_key === 'high') || state.demos[0];
            if (sample) {
                fillCheckSample(sample);
                $('#demo-select').value = sample.sample_key;
                await runCheck();
            }
        }
    }

    function checkEmptyHtml() {
        return '<div class="card result-empty">' +
            emptyState('shield', '等待风险检查',
                '选择左侧业务事件并输入用户、订单编号，Agent 将依次完成事件校验、39 项特征计算、30 条规则匹配、评分决策、黑名单校验与案件生成。',
                '<span class="badge badge-info">六步编排</span><span class="badge badge-neutral">全链路留痕</span>') +
            '</div>';
    }

    function fillCheckSample(sample) {
        if (!sample) return;
        const form = $('#check-form');
        if (!form) return;
        form.querySelector('[name="event_type"]').value = sample.event_type;
        form.querySelector('[name="user_id"]').value = sample.user_id;
        form.querySelector('[name="order_id"]').value = sample.order_id;
        form.querySelector('[name="source_id"]').value = sample.source_id || 'APP';
    }

    async function runCheck() {
        const form = $('#check-form');
        if (!form) return;
        const userField = form.querySelector('[name="user_id"]');
        const orderField = form.querySelector('[name="order_id"]');
        if (!userField.value.trim() || !orderField.value.trim()) {
            toast('请输入用户编号与订单编号', 'warning');
            return;
        }
        const payload = {
            event_type: form.querySelector('[name="event_type"]').value,
            user_id: userField.value.trim(),
            order_id: orderField.value.trim(),
            source_id: form.querySelector('[name="source_id"]').value.trim() || 'WEB'
        };
        state.lastCheckPayload = payload;
        const button = $('#check-submit');
        const result = $('#check-result');
        if (!result) return;
        const token = state.renderToken;
        const original = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner"></span> Agent 执行中...';
        result.innerHTML = '<div class="card result-empty"><div class="empty-state">' +
            '<div class="spinner spinner-dark" style="width:28px;height:28px;border-width:3px;margin:0 auto 16px"></div>' +
            '<h3>Agent 正在执行风险检查</h3><p>事件校验 → 特征计算 → 规则匹配 → 评分决策 → 黑名单校验 → 案件生成</p></div></div>';
        try {
            const data = await API.post('/api/risk/check', payload);
            if (token !== state.renderToken) return;
            renderCheckResult(data);
            refreshNavBadge();
        } catch (error) {
            if (token !== state.renderToken) return;
            result.innerHTML = '<div class="card result-empty">' +
                emptyState('alert', '检查失败', error.message, '<button class="btn btn-primary" data-action="retry-check">重新检查</button>') +
                '</div>';
            toast(error.message, 'error');
        } finally {
            if (token === state.renderToken && button) {
                button.disabled = false;
                button.innerHTML = original;
            }
        }
    }

    function renderCheckResult(data) {
        const result = $('#check-result');
        if (!result) return;
        const hits = data.rule_hits || [];
        const blacklistHits = data.blacklist_hits || [];
        const capped = data.score_detail && data.score_detail.score_capped;
        const hasCase = !!data.case_id;
        const summaryText = hits.length
            ? '命中 ' + hits.length + ' 条风险规则' + (blacklistHits.length ? '、' + blacklistHits.length + ' 条黑名单' : '') +
              '，系统建议' + labelOf(state.dicts.decision, data.decision) + (hasCase ? '并已自动创建案件。' : '。')
            : '未命中风险规则，当前事件风险可控。';
        const featureCount = Object.keys(data.feature_snapshot || {}).length;
        const traceTotal = (data.trace || []).reduce((sum, item) => sum + Number(item.duration_ms || 0), 0);
        const groupCounts = {};
        state.features.forEach((feature) => {
            if (Object.prototype.hasOwnProperty.call(data.feature_snapshot || {}, feature.key)) {
                groupCounts[feature.group] = (groupCounts[feature.group] || 0) + 1;
            }
        });
        const filters = ['<button class="feature-filter active" data-feature-filter="all">全部 ' + featureCount + '</button>']
            .concat(state.featureGroups.filter((group) => groupCounts[group.group]).map((group) =>
                '<button class="feature-filter" data-feature-filter="' + attr(group.group) + '">' + esc(group.group_name.replace('维度', '')) + ' ' + (groupCounts[group.group] || 0) + '</button>'
            )).join('');

        result.innerHTML =
            '<div class="result-summary card level-' + attr(data.risk_level) + '">' +
                '<div class="summary-main">' +
                    '<div class="gauge-box">' + gaugeSvg(data.risk_score, data.risk_level, 122) + '</div>' +
                    '<div class="summary-info">' +
                        '<div class="summary-title-row"><h2>评估结果</h2>' + levelBadge(data.risk_level, data.risk_level_label) + decisionBadge(data.decision, data.decision_label) +
                            (blacklistHits.length ? '<span class="badge badge-high"><span class="dot"></span>黑名单 ×' + blacklistHits.length + '</span>' : '') +
                            (capped ? '<span class="badge badge-neutral">分数已封顶</span>' : '') + '</div>' +
                        '<p class="summary-desc">' + esc(summaryText) + '</p>' +
                        '<div class="summary-badges"><span class="badge badge-neutral">' + esc(data.event_label) + '</span>' +
                            '<span class="badge badge-neutral">' + esc(data.user_id) + '</span><span class="badge badge-neutral">' + esc(data.order_id) + '</span></div>' +
                        '<div class="summary-meta"><span>评估编号 <strong>' + esc(data.assessment_no) + '</strong></span>' +
                            '<span>案件 <strong class="' + (hasCase ? 'meta-link' : '') + '" ' + (hasCase ? 'data-action="open-case" data-id="' + data.case_id + '"' : '') + '>' + (hasCase ? esc(data.case_no) : '未触发') + '</strong></span>' +
                            '<span>Agent 耗时 <strong>' + Number(data.agent_elapsed_ms || 0).toFixed(2) + ' ms</strong></span>' +
                            '<span>评估时间 <strong>' + esc(fmtTimeShort(data.created_at)) + '</strong></span></div>' +
                    '</div>' +
                '</div>' +
                '<div class="summary-side">' +
                    '<div class="score-bars">' +
                        '<div class="score-bar-row"><span>规则命中分</span><strong>' + Number(data.score_detail.rule_score_total).toFixed(1) + '</strong></div>' +
                        '<div class="score-bar-row"><span>黑名单加权</span><strong>+' + Number(data.score_detail.blacklist_score_total).toFixed(1) + '</strong></div>' +
                        '<div class="score-bar-row"><span>最终评分</span><strong style="color:' + (LEVEL_COLORS[data.risk_level] || '#101828') + '">' + Number(data.risk_score).toFixed(1) + '</strong></div>' +
                    '</div>' +
                    '<div class="score-cap-note">评分 = 规则分值 × 优先级权重 + 黑名单加权，上限 100 分。</div>' +
                    (hasCase ? '<button class="btn btn-primary btn-sm" data-action="open-case" data-id="' + data.case_id + '">' + icon('folder') + '查看关联案件</button>' : '<span class="badge badge-low">无需人工介入</span>') +
                '</div>' +
            '</div>' +
            '<div class="result-grid">' +
                '<section class="card panel-card"><div class="card-head"><div class="card-title">' + icon('list', 'title-icon') + '命中规则 <span class="count">' + hits.length + '</span></div><span class="card-sub">按优先级排序</span></div>' +
                    '<div class="scroll-panel">' + hitListHtml(hits) + '</div></section>' +
                '<section class="card panel-card"><div class="card-head"><div class="card-title">' + icon('chart', 'title-icon') + '特征快照 <span class="count">' + featureCount + '</span></div><span class="card-sub">键值对已落库</span></div>' +
                    '<div class="feature-toolbar">' + filters + '</div>' +
                    '<div class="feature-groups">' + featureGroupsHtml(data.feature_snapshot || {}) + '</div></section>' +
            '</div>' +
            '<section class="card trace-card"><div class="card-head"><div class="card-title">' + icon('bolt', 'title-icon') + 'Agent 执行轨迹</div><span class="card-sub">6 步 · 总耗时 ' + traceTotal.toFixed(2) + ' ms</span></div>' +
                traceHtml(data.trace) + '</section>';
        bindFeatureFilters(result);
    }

    /* ---------------------------------------------------------------------
     * 规则管理页
     * ------------------------------------------------------------------- */
    async function renderRules() {
        const content = $('#page-content');
        content.innerHTML =
            pageHead('规则管理', '维护风险规则、优先级与命中分值，条件 JSON 采用可校验的 AST 结构',
                '<button class="btn btn-primary" data-action="add-rule">' + icon('plus') + '新增规则</button>') +
            '<div class="stats-grid" id="rules-stats">' + skeletonStats(4) + '</div>' +
            '<div class="card toolbar-card">' +
                '<div class="search-box">' + icon('search') + '<input id="rule-search" class="input" placeholder="搜索规则编码 / 名称"></div>' +
                '<select id="rule-status-filter" class="select"><option value="">全部状态</option><option value="enabled">启用中</option><option value="disabled">已停用</option></select>' +
                '<button class="btn btn-sm" data-action="refresh-rules">' + icon('refresh') + '刷新</button>' +
                '<div class="spacer"></div><span class="card-sub">支持 &gt; &lt; &gt;= &lt;= == != contains in and or not</span>' +
            '</div>' +
            '<div class="card table-card">' +
                '<div class="table-card-head"><h3>' + icon('list', 'title-icon') + '规则列表 <span class="count" id="rules-count"></span></h3>' +
                    '<span class="card-sub" id="rules-tip">启用规则参与实时检查</span></div>' +
                '<div class="table-card-body" id="rules-table-wrap">' + skeletonTable(6) + '</div>' +
            '</div>';
        await refreshRules();
    }

    async function refreshRules() {
        if (state.page !== 'rules') return;
        const data = await API.get('/api/risk/rules', state.rulesFilter);
        if (state.page !== 'rules') return;
        state.rules = data.items;
        $('#rules-stats').innerHTML =
            statCard('list', '', '规则总数', data.total, '覆盖用户 / 订单 / 地址维度') +
            statCard('checkCircle', 'green', '启用规则', data.enabled_count, '停用 ' + data.disabled_count + ' 条') +
            statCard('bolt', 'orange', '累计命中', data.total_hits, '全部评估累计命中次数') +
            statCard('chart', 'purple', '平均规则分', data.avg_score, '单条规则平均基础分值');
        $('#rules-count').textContent = '共 ' + data.filtered_total + ' 条';
        $('#rules-tip').textContent = '启用 ' + data.enabled_count + ' 条 · 停用 ' + data.disabled_count + ' 条';
        renderRuleTable(data.items);
    }

    function renderRuleTable(items) {
        if (!items.length) {
            $('#rules-table-wrap').innerHTML = '<div class="table-empty">没有符合条件的规则</div>';
            return;
        }
        const rows = items.map((rule) => {
            const enabled = rule.rule_status === 'enabled';
            const priorityClass = rule.priority >= 8 ? 'high' : (rule.priority >= 5 ? 'mid' : '');
            return '<tr>' +
                '<td><span class="mono">' + esc(rule.rule_code) + '</span></td>' +
                '<td><div class="rule-name-cell"><strong>' + esc(rule.rule_name) + '</strong><span title="' + attr(rule.description) + '">' + esc(rule.description) + '</span></div></td>' +
                '<td><div class="switch-wrap"><button class="switch ' + (enabled ? 'on' : '') + '" data-action="toggle-rule" data-id="' + rule.id + '" title="' + (enabled ? '点击停用' : '点击启用') + '"></button>' +
                    '<span class="switch-label ' + (enabled ? 'on' : '') + '">' + (enabled ? '启用' : '停用') + '</span></div></td>' +
                '<td><span class="priority-pill ' + priorityClass + '">' + esc(rule.priority) + '</span></td>' +
                '<td><span class="score-text">' + esc(rule.score) + '</span></td>' +
                '<td><span class="hit-count-badge ' + (rule.hit_count ? 'active' : '') + '">' + esc(rule.hit_count) + '</span></td>' +
                '<td class="mono">' + esc(fmtTimeShort(rule.updated_at)) + '</td>' +
                '<td><div class="row-actions">' +
                    '<button class="icon-btn" data-action="edit-rule" data-id="' + rule.id + '" title="编辑规则">' + icon('edit') + '</button>' +
                    '<button class="icon-btn danger" data-action="delete-rule" data-id="' + rule.id + '" title="删除规则">' + icon('trash') + '</button>' +
                '</div></td></tr>';
        }).join('');
        $('#rules-table-wrap').innerHTML =
            '<div class="table-wrap rules-table" style="max-height:552px"><table class="data-table rules-table">' +
                '<thead><tr><th style="width:64px">编码</th><th>名称 / 描述</th><th style="width:86px">状态</th><th style="width:62px">优先级</th><th style="width:56px">分值</th><th style="width:68px">命中次数</th><th style="width:112px">更新时间</th><th style="width:76px;text-align:right">操作</th></tr></thead>' +
                '<tbody>' + rows + '</tbody></table></div>';
    }

    function skeletonStats(count) {
        return new Array(count).fill(0).map(() => '<div class="card stat-card"><div class="skeleton" style="width:37px;height:37px;border-radius:11px"></div><div style="flex:1"><div class="skeleton skeleton-line" style="width:44%"></div><div class="skeleton skeleton-line" style="width:30%;height:16px"></div></div></div>').join('');
    }

    function skeletonTable(rows) {
        return '<div style="padding:14px">' + new Array(rows).fill(0).map(() => '<div class="skeleton skeleton-line"></div>').join('') + '</div>';
    }

    async function toggleRule(ruleId) {
        const rule = state.rules.find((item) => Number(item.id) === Number(ruleId));
        if (!rule) return;
        const next = rule.rule_status === 'enabled' ? 'disabled' : 'enabled';
        try {
            await API.post('/api/risk/rules/status', { rule_id: rule.id, rule_status: next });
            toast('规则 ' + rule.rule_code + ' 已' + (next === 'enabled' ? '启用' : '停用'), 'success');
            await refreshRules();
        } catch (error) {
            toast(error.message, 'error');
        }
    }

    function openRuleModal(rule) {
        const editing = !!rule;
        const conditionText = editing ? rule.condition_json : JSON.stringify({
            and: [
                { field: 'order_amount', op: '>=', value: 1000 },
                { field: 'user_register_days', op: '<', value: 30 }
            ]
        }, null, 2);
        const statusOptions = ['enabled', 'disabled'].map((value) =>
            '<option value="' + value + '"' + (editing && rule.rule_status === value ? ' selected' : '') + '>' + (value === 'enabled' ? '启用' : '停用') + '</option>').join('');
        openModal(
            '<div class="modal-panel lg">' +
                '<div class="modal-head"><div class="modal-head-icon">' + icon(editing ? 'edit' : 'plus') + '</div>' +
                    '<div class="modal-head-text"><h3>' + (editing ? '编辑风险规则' : '新增风险规则') + '</h3><p>条件 JSON 将在前后端同时校验，保存后立即生效</p></div>' +
                    '<button class="modal-close" data-close-modal type="button">' + icon('close') + '</button></div>' +
                '<div class="modal-body">' +
                    '<div class="form-grid">' +
                        '<div class="field"><label>规则编码 <span class="req">*</span></label><input id="rule-code" class="input" value="' + attr(editing ? rule.rule_code : '') + '" placeholder="例如 R031" ' + (editing ? 'disabled' : '') + '></div>' +
                        '<div class="field"><label>规则名称 <span class="req">*</span></label><input id="rule-name" class="input" value="' + attr(editing ? rule.rule_name : '') + '" placeholder="例如 高额优惠券套利"></div>' +
                        '<div class="field"><label>优先级</label><input id="rule-priority" class="input" type="number" min="1" max="10" value="' + attr(editing ? rule.priority : 5) + '"></div>' +
                        '<div class="field"><label>命中分值</label><input id="rule-score" class="input" type="number" min="0" max="100" value="' + attr(editing ? rule.score : 10) + '"></div>' +
                        '<div class="field"><label>规则状态</label><select id="rule-status" class="select">' + statusOptions + '</select></div>' +
                        '<div class="field"><label>规则说明</label><input id="rule-description" class="input" value="' + attr(editing ? rule.description : '') + '" placeholder="说明规则业务含义"></div>' +
                    '</div>' +
                    '<div class="field"><label>条件 JSON（AST） <span class="req">*</span></label>' +
                        '<div class="condition-box"><textarea id="rule-condition" spellcheck="false">' + esc(conditionText) + '</textarea></div>' +
                        '<div class="condition-toolbar"><span class="condition-help">支持 <code>and</code> <code>or</code> <code>not</code>、比较、<code>contains</code>、<code>in</code>；字段须为已定义特征</span>' +
                            '<span><button class="btn btn-sm" id="format-condition" type="button">格式化</button> <button class="btn btn-sm" id="validate-condition" type="button">校验条件</button></span></div>' +
                        '<div class="condition-feedback" id="condition-feedback"></div></div>' +
                '</div>' +
                '<div class="modal-foot"><span class="left-note">保存后 updated_at 自动更新</span><button class="btn" data-close-modal type="button">取消</button>' +
                    '<button class="btn btn-primary" id="save-rule" type="button">' + icon('check') + (editing ? '保存修改' : '创建规则') + '</button></div>' +
            '</div>',
            () => {
                const textarea = $('#rule-condition');
                const feedback = $('#condition-feedback');
                const showFeedback = (ok, message) => {
                    feedback.className = 'condition-feedback show ' + (ok ? 'ok' : 'error');
                    feedback.textContent = message;
                };
                $('#format-condition').addEventListener('click', () => {
                    try {
                        const parsed = JSON.parse(textarea.value);
                        textarea.value = JSON.stringify(parsed, null, 2);
                        showFeedback(true, 'JSON 格式化完成');
                    } catch (error) {
                        showFeedback(false, 'JSON 解析失败：' + error.message);
                    }
                });
                $('#validate-condition').addEventListener('click', () => {
                    try {
                        const parsed = parseConditionText(textarea.value);
                        const count = countConditionNodes(parsed);
                        showFeedback(true, '条件格式正确，共 ' + count + ' 个节点');
                    } catch (error) {
                        showFeedback(false, error.message);
                    }
                });
                $('#save-rule').addEventListener('click', async () => {
                    const button = $('#save-rule');
                    button.disabled = true;
                    try {
                        const name = $('#rule-name').value.trim();
                        if (!name) throw new Error('规则名称不能为空');
                        const parsed = parseConditionText(textarea.value);
                        const payload = {
                            rule_name: name,
                            rule_status: $('#rule-status').value,
                            priority: Number($('#rule-priority').value),
                            score: Number($('#rule-score').value),
                            description: $('#rule-description').value.trim(),
                            condition_json: parsed
                        };
                        if (editing) {
                            payload.rule_id = rule.id;
                            await API.post('/api/risk/rules/update', payload);
                        } else {
                            payload.rule_code = $('#rule-code').value.trim().toUpperCase();
                            if (!payload.rule_code) throw new Error('规则编码不能为空');
                            await API.post('/api/risk/rules', payload);
                        }
                        toast(editing ? '规则已更新' : '规则已创建', 'success');
                        closeModal();
                        await refreshRules();
                    } catch (error) {
                        showFeedback(false, error.message);
                        toast(error.message, 'error');
                        button.disabled = false;
                    }
                });
            }
        );
    }

    function parseConditionText(text) {
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (error) {
            throw new Error('JSON 解析失败：' + error.message);
        }
        validateConditionNode(parsed, 1);
        return parsed;
    }

    function validateConditionNode(node, depth) {
        if (depth > 5) throw new Error('条件嵌套不能超过 5 层');
        if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error('条件节点必须为 JSON 对象');
        const keys = Object.keys(node);
        if (keys.indexOf('and') >= 0 || keys.indexOf('or') >= 0) {
            if (keys.length !== 1) throw new Error('逻辑节点只能包含 and 或 or 一个字段');
            const key = keys[0];
            const children = node[key];
            if (!Array.isArray(children) || children.length < 2) throw new Error(key + ' 至少需要 2 个子条件');
            children.forEach((child) => validateConditionNode(child, depth + 1));
            return;
        }
        if (keys.indexOf('not') >= 0) {
            if (keys.length !== 1) throw new Error('not 节点只能包含一个子条件');
            validateConditionNode(node.not, depth + 1);
            return;
        }
        if (keys.indexOf('field') < 0 || keys.indexOf('op') < 0 || keys.indexOf('value') < 0) {
            throw new Error('条件叶子节点必须包含 field、op、value');
        }
        if (!state.featureMap[node.field]) throw new Error('未知特征字段：' + node.field);
        const operators = ['>', '<', '>=', '<=', '==', '!=', 'contains', 'in'];
        if (operators.indexOf(node.op) < 0) throw new Error('不支持的运算符：' + node.op);
        if (['>', '<', '>=', '<='].indexOf(node.op) >= 0 && typeof node.value !== 'number') {
            throw new Error('比较运算符的阈值必须为数字');
        }
        if (node.op === 'contains' && (typeof node.value !== 'string' || !node.value)) {
            throw new Error('contains 的阈值必须为非空字符串');
        }
        if (node.op === 'in' && (!Array.isArray(node.value) || !node.value.length)) {
            throw new Error('in 的阈值必须为非空数组');
        }
    }

    function countConditionNodes(node) {
        if (node.and) return 1 + node.and.reduce((sum, child) => sum + countConditionNodes(child), 0);
        if (node.or) return 1 + node.or.reduce((sum, child) => sum + countConditionNodes(child), 0);
        if (node.not) return 1 + countConditionNodes(node.not);
        return 1;
    }

    function deleteRule(ruleId) {
        const rule = state.rules.find((item) => Number(item.id) === Number(ruleId));
        if (!rule) return;
        openConfirm({
            title: '删除风险规则',
            subtitle: '规则将从规则库移除',
            message: '确认删除规则 <strong>' + esc(rule.rule_code) + ' · ' + esc(rule.rule_name) + '</strong> 吗？',
            warning: '该规则的历史命中明细会被同步清理，规则命中统计将立即变化。',
            confirmText: '确认删除',
            onConfirm: async () => {
                const result = await API.post('/api/risk/rules/delete', { rule_id: rule.id });
                toast('规则 ' + result.rule_code + ' 已删除', 'success');
                await refreshRules();
            }
        });
    }

    /* ---------------------------------------------------------------------
     * 案件管理页
     * ------------------------------------------------------------------- */
    async function renderCases(params) {
        const content = $('#page-content');
        content.innerHTML =
            pageHead('案件管理', '查看自动生成的风险案件，完成人工复核并留存审核日志',
                '<button class="btn" data-action="refresh-cases">' + icon('refresh') + '刷新案件</button>') +
            '<div class="case-summary-chips" id="case-chips">' + skeletonChips() + '</div>' +
            '<div class="card case-filter-card">' +
                '<select id="case-status-filter" class="select"><option value="">全部状态</option>' +
                    state.meta.case_statuses.map((item) => '<option value="' + attr(item.value) + '">' + esc(item.label) + '</option>').join('') + '</select>' +
                '<select id="case-level-filter" class="select"><option value="">全部等级</option>' +
                    state.meta.risk_levels.map((item) => '<option value="' + attr(item.value) + '">' + esc(item.label) + '</option>').join('') + '</select>' +
                '<div class="search-box">' + icon('search') + '<input id="case-search" class="input" placeholder="案件号 / 用户 / 订单 / 审核人"></div>' +
                '<button class="btn btn-sm" data-action="reset-case-filter">' + icon('refresh') + '重置</button>' +
                '<div class="spacer"></div><span class="card-sub">点击任意案件行打开右侧详情</span>' +
            '</div>' +
            '<div class="card table-card">' +
                '<div class="table-card-head"><h3>' + icon('folder', 'title-icon') + '案件列表 <span class="count" id="cases-count"></span></h3><span class="card-sub">自动建案规则：高风险或建议人工审核 / 拒绝</span></div>' +
                '<div class="table-card-body" id="cases-table-wrap">' + skeletonTable(8) + '</div>' +
            '</div>';
        const data = await refreshCases();
        if (params.get('demo') && data && data.items.length) {
            const demoUser = (state.demos.find((item) => item.sample_key === 'high') || {}).user_id;
            const target = data.items.find((item) => item.case_status === 'pending' && demoUser && item.user_id === demoUser) ||
                data.items.find((item) => item.case_status === 'pending') || data.items[0];
            if (target) openCaseDrawer(target.case_id);
        }
    }

    function skeletonChips() {
        return new Array(6).fill(0).map(() => '<div class="skeleton" style="width:102px;height:30px;border-radius:8px"></div>').join('');
    }

    async function refreshCases() {
        if (state.page !== 'cases') return null;
        const data = await API.get('/api/risk/cases', {
            page_size: 100,
            case_status: state.casesFilter.status,
            risk_level: state.casesFilter.level,
            keyword: state.casesFilter.keyword
        });
        if (state.page !== 'cases') return null;
        renderCaseChips(data);
        renderCaseTable(data);
        return data;
    }

    function renderCaseChips(data) {
        const counts = data.status_stats || {};
        const total = Object.keys(counts).reduce((sum, key) => sum + Number(counts[key] || 0), 0);
        let html = '<button class="chip ' + (!state.casesFilter.status ? 'active' : '') + '" data-action="filter-case" data-status="">全部案件 <span class="chip-count">' + total + '</span></button>';
        state.meta.case_statuses.forEach((item) => {
            const count = counts[item.value] || 0;
            html += '<button class="chip ' + (state.casesFilter.status === item.value ? 'active' : '') + '" data-action="filter-case" data-status="' + attr(item.value) + '">' +
                esc(item.label) + ' <span class="chip-count">' + count + '</span></button>';
        });
        $('#case-chips').innerHTML = html;
    }

    function renderCaseTable(data) {
        $('#cases-count').textContent = '共 ' + data.total + ' 条';
        if (!data.items.length) {
            $('#cases-table-wrap').innerHTML = '<div class="table-empty">没有符合条件的案件</div>';
            return;
        }
        const rows = data.items.map((item) => {
            const reviewer = item.reviewer_name
                ? '<span class="strong">' + esc(item.reviewer_name) + '</span>'
                : '<span class="reviewer-empty">待分配</span>';
            return '<tr class="clickable" data-action="open-case" data-id="' + item.case_id + '">' +
                '<td><span class="case-no">' + esc(item.case_no) + '</span></td>' +
                '<td><div class="case-user"><span class="mini-avatar">' + esc((item.user_name || '?').slice(0, 1)) + '</span>' +
                    '<div class="case-user-text"><strong>' + esc(item.user_name || '—') + '</strong><span>' + esc(item.user_id) + '</span></div></div></td>' +
                '<td class="mono">' + esc(item.order_id || '—') + '</td>' +
                '<td><span class="badge badge-neutral">' + esc(item.event_type_label) + '</span></td>' +
                '<td>' + levelBadge(item.risk_level, item.risk_level_label) + '</td>' +
                '<td><span class="score-text">' + Number(item.risk_score).toFixed(1) + '</span></td>' +
                '<td>' + caseStatusBadge(item.case_status, item.case_status_label) + '</td>' +
                '<td>' + reviewer + '</td>' +
                '<td class="mono">' + esc(fmtTimeShort(item.created_at)) + '</td>' +
                '<td><div class="row-actions"><button class="btn btn-sm" data-action="open-case" data-id="' + item.case_id + '">' + icon('arrowRight') + '详情</button></div></td></tr>';
        }).join('');
        $('#cases-table-wrap').innerHTML =
            '<div class="table-wrap cases-table" style="max-height:600px"><table class="data-table cases-table">' +
                '<thead><tr><th style="width:112px">案件编号</th><th>关联用户</th><th style="width:92px">关联订单</th><th style="width:94px">事件</th><th style="width:82px">等级</th><th style="width:54px">评分</th><th style="width:90px">状态</th><th style="width:90px">审核人</th><th style="width:106px">创建时间</th><th style="width:72px;text-align:right">操作</th></tr></thead>' +
                '<tbody>' + rows + '</tbody></table></div>';
    }

    async function openCaseDrawer(caseId) {
        const root = $('#drawer-root');
        root.innerHTML = '<div class="drawer-overlay" data-drawer-overlay><aside class="drawer-panel">' +
            '<div class="drawer-head"><div class="drawer-head-icon">' + icon('folder') + '</div>' +
                '<div class="drawer-title"><strong>案件详情</strong><span>正在加载风险结果与审核记录...</span></div>' +
                '<button class="drawer-close" data-close-drawer type="button">' + icon('close') + '</button></div>' +
            '<div class="drawer-body"><div class="skeleton skeleton-line" style="width:40%"></div><div class="skeleton skeleton-card" style="height:180px;margin-top:12px"></div>' +
                '<div class="skeleton skeleton-card" style="height:150px;margin-top:12px"></div></div>' +
            '</aside></div>';
        syncBodyLock();
        const overlay = root.firstElementChild;
        overlay.addEventListener('click', (event) => { if (event.target === overlay) closeDrawer(); });
        $$('[data-close-drawer]', overlay).forEach((button) => button.addEventListener('click', closeDrawer));
        try {
            const detail = await API.get('/api/risk/cases/' + caseId);
            if (!root.contains(overlay)) return;
            renderCaseDrawer(detail);
        } catch (error) {
            toast(error.message, 'error');
            closeDrawer();
        }
    }

    function renderCaseDrawer(detail) {
        const root = $('#drawer-root');
        const panel = root.querySelector('.drawer-panel');
        if (!panel) return;
        const assessment = detail.assessment || {};
        const featureCount = Object.keys(detail.feature_snapshot || {}).length;
        const blacklistHits = detail.blacklist_hits || [];
        const final = ['approved', 'rejected', 'resolved'].indexOf(detail.case_status) >= 0;
        const ruleScore = (detail.rule_hits || []).reduce((sum, hit) => sum + Number(hit.hit_score || 0), 0);
        const blacklistScore = blacklistHits.reduce((sum, hit) => sum + Number(hit.added_score || 0), 0);
        const formHtml = final ? reviewResultHtml(detail) : reviewFormHtml(detail);

        panel.innerHTML =
            '<div class="drawer-head">' +
                '<div class="drawer-head-icon">' + icon('folder') + '</div>' +
                '<div class="drawer-title"><strong>' + esc(detail.case_no) + '</strong><span>关联评估 AS-' + String(assessment.assessment_id || '').padStart(6, '0') + ' · 创建于 ' + esc(fmtTimeFull(detail.created_at)) + '</span></div>' +
                caseStatusBadge(detail.case_status, detail.case_status_label) +
                '<button class="drawer-close" data-close-drawer type="button">' + icon('close') + '</button>' +
            '</div>' +
            '<div class="drawer-body">' +
                '<div class="detail-card">' +
                    '<div class="case-risk-summary">' +
                        '<div class="case-risk-gauge">' + gaugeSvg(assessment.risk_score || 0, assessment.risk_level, 88) + '</div>' +
                        '<div class="case-risk-main">' +
                            '<h2>' + levelBadge(assessment.risk_level, assessment.risk_level_label) + decisionBadge(assessment.decision, assessment.decision_label) +
                                (blacklistHits.length ? '<span class="badge badge-high">黑名单 ×' + blacklistHits.length + '</span>' : '') + '</h2>' +
                            '<p class="risk-desc">' + esc(assessment.event_type_label) + '事件 · 命中 <strong>' + (detail.rule_hits || []).length + '</strong> 条规则 · 特征快照 <strong>' + featureCount + '</strong> 项</p>' +
                            '<div class="summary-meta"><span>用户 <strong>' + esc(detail.user.user_id) + ' ' + esc(detail.user.user_name || '') + '</strong></span>' +
                                '<span>订单 <strong>' + esc(detail.order.order_id || '—') + '</strong></span>' +
                                '<span>订单金额 <strong>¥' + fmtMoney(detail.order.amount) + '</strong></span></div>' +
                        '</div>' +
                        '<div class="case-risk-side">' +
                            '<div class="row"><span>规则命中分</span><strong>' + ruleScore.toFixed(1) + '</strong></div>' +
                            '<div class="row"><span>黑名单加权</span><strong>+' + blacklistScore.toFixed(1) + '</strong></div>' +
                            '<div class="row"><span>最终评分</span><strong style="color:' + (LEVEL_COLORS[assessment.risk_level] || '#101828') + '">' + Number(assessment.risk_score || 0).toFixed(1) + '</strong></div>' +
                            '<div class="row"><span>审核人</span><strong>' + esc(detail.reviewer_name || '待分配') + '</strong></div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="case-info-grid">' +
                        '<div class="case-info-item"><span>用户编号</span><strong>' + esc(detail.user.user_id) + '</strong></div>' +
                        '<div class="case-info-item"><span>订单编号</span><strong>' + esc(detail.order.order_id || '—') + '</strong></div>' +
                        '<div class="case-info-item"><span>事件来源</span><strong>' + esc(assessment.source_id || '—') + '</strong></div>' +
                        '<div class="case-info-item"><span>案件创建</span><strong>' + esc(fmtTimeShort(detail.created_at)) + '</strong></div>' +
                    '</div>' +
                    (blacklistHits.length ? '<div class="summary-badges" style="margin-top:10px">' + blacklistHits.map((hit) =>
                        '<span class="badge badge-high">' + esc(labelOf(state.dicts.blacklist, hit.blacklist_type)) + '：' + esc(hit.blacklist_value) + ' +' + Number(hit.added_score).toFixed(0) + '</span>').join('') + '</div>' : '') +
                '</div>' +
                '<div class="drawer-grid">' +
                    '<div class="detail-card"><div class="detail-card-head"><h3>命中规则 <span class="count">' + (detail.rule_hits || []).length + '</span></h3><span class="sub">按优先级</span></div>' +
                        '<div class="drawer-scroll drawer-rules">' + hitListHtml(detail.rule_hits) + '</div></div>' +
                    '<div class="detail-card"><div class="detail-card-head"><h3>特征快照 <span class="count">' + featureCount + '</span></h3><span class="sub">键值对</span></div>' +
                        '<div class="drawer-scroll feature">' + featureGroupsHtml(detail.feature_snapshot || {}) + '</div></div>' +
                '</div>' +
                '<div class="detail-card"><div class="detail-card-head"><h3>审核记录 <span class="count">' + (detail.review_logs || []).length + '</span></h3><span class="sub">操作留痕不可篡改</span></div>' +
                    '<div class="drawer-log-list">' + ((detail.review_logs || []).length ? detail.review_logs.map((log) =>
                        '<div class="drawer-log"><div class="drawer-log-top"><strong>' + esc(log.action_label) + '</strong><span>' + esc(log.operator_name || log.operator_id) + ' · ' + esc(fmtTimeFull(log.created_at)) + '</span></div>' +
                        '<p>' + esc(log.action_remark || '无备注') + '</p></div>').join('') : '<div class="hit-empty">暂无审核记录</div>') + '</div></div>' +
                '<div class="detail-card ' + (final ? '' : 'review-form-card') + '">' + formHtml + '</div>' +
            '</div>';

        $$('[data-close-drawer]', panel).forEach((button) => button.addEventListener('click', closeDrawer));
        syncBodyLock();
        if (!final) bindReviewForm(detail);
    }

    function reviewResultHtml(detail) {
        const approved = detail.case_status === 'approved';
        const rejected = detail.case_status === 'rejected';
        const iconName = rejected ? 'xCircle' : 'checkCircle';
        const color = rejected ? '#b42318' : (approved ? '#027a48' : '#1849a9');
        return '<div class="detail-card-head"><h3>处理结论</h3>' + caseStatusBadge(detail.case_status, detail.case_status_label) + '</div>' +
            '<div class="review-result-panel"><div class="rr-icon" style="color:' + color + ';background:' + (rejected ? '#fef3f2' : '#ecfdf3') + '">' + icon(iconName) + '</div>' +
            '<div class="rr-main"><strong>审核人：' + esc(detail.reviewer_name || '—') + '（' + esc(detail.reviewer_id || '') + '）</strong>' +
                '<p>' + esc(detail.review_remark || '无审核备注') + '</p>' +
                '<span>审核时间：' + esc(fmtTimeFull(detail.reviewed_at || detail.updated_at)) + '</span></div></div>';
    }

    function reviewFormHtml() {
        const reviewer = state.reviewers[0] || { reviewer_id: 'RV001', name: '张审核' };
        return '<div class="detail-card-head"><h3>人工审核</h3><span class="sub">结论提交后不可重复审核</span></div>' +
            '<div class="review-options">' +
                '<div class="review-option"><input type="radio" name="review-result" id="review-approved" value="approved" checked><label class="approved" for="review-approved">' + icon('checkCircle') + '审核通过</label></div>' +
                '<div class="review-option"><input type="radio" name="review-result" id="review-rejected" value="rejected"><label class="rejected" for="review-rejected">' + icon('xCircle') + '审核拒绝</label></div>' +
                '<div class="review-option"><input type="radio" name="review-result" id="review-resolved" value="resolved"><label class="resolved" for="review-resolved">' + icon('check') + '标记解决</label></div>' +
            '</div>' +
            '<textarea id="review-remark" class="textarea" rows="2" placeholder="请填写审核备注（必填），例如：已电话核实为本人操作，风险信号解除。"></textarea>' +
            '<div class="review-form-actions"><span class="reviewer-note">审核人：' + esc(reviewer.name) + '（' + esc(reviewer.reviewer_id) + '） · 提交后同步更新案件状态与日志</span>' +
                '<button class="btn btn-primary" id="review-submit" type="button">' + icon('check') + '提交审核</button></div>';
    }

    function bindReviewForm(detail) {
        const button = $('#review-submit');
        if (!button) return;
        button.addEventListener('click', async () => {
            const selected = document.querySelector('input[name="review-result"]:checked');
            const remark = $('#review-remark').value.trim();
            if (!selected) { toast('请选择审核结论', 'warning'); return; }
            if (!remark) { toast('请填写审核备注，保证处置可追溯', 'warning'); $('#review-remark').focus(); return; }
            button.disabled = true;
            const original = button.innerHTML;
            button.innerHTML = '<span class="spinner"></span> 提交中...';
            try {
                const updated = await API.post('/api/risk/cases/review', {
                    case_id: detail.case_id,
                    review_result: selected.value,
                    review_remark: remark,
                    reviewer_id: (state.reviewers[0] || {}).reviewer_id || 'RV001'
                });
                toast('审核结论已提交，案件状态已更新', 'success');
                renderCaseDrawer(updated);
                refreshNavBadge();
                if (state.page === 'cases') refreshCases();
            } catch (error) {
                toast(error.message, 'error');
                button.disabled = false;
                button.innerHTML = original;
            }
        });
    }

    /* ---------------------------------------------------------------------
     * 黑名单管理页
     * ------------------------------------------------------------------- */
    async function renderBlacklist() {
        const content = $('#page-content');
        content.innerHTML =
            pageHead('黑名单管理', '维护用户、手机号、地址、设备与 IP 黑名单，命中后在检查时直接加权',
                '<button class="btn" data-action="import-blacklist">' + icon('upload') + '批量导入</button>' +
                '<button class="btn btn-primary" data-action="add-blacklist">' + icon('plus') + '新增黑名单</button>') +
            '<div class="blacklist-types" id="bl-type-cards">' + skeletonStats(5) + '</div>' +
            '<div class="card toolbar-card">' +
                '<div class="search-box">' + icon('search') + '<input id="blacklist-search" class="input" placeholder="搜索命中值 / 备注"></div>' +
                '<select id="blacklist-type-filter" class="select"><option value="">全部类型</option>' +
                    state.meta.blacklist_types.map((item) => '<option value="' + attr(item.value) + '">' + esc(item.label) + '</option>').join('') + '</select>' +
                '<select id="blacklist-status-filter" class="select"><option value="">全部状态</option><option value="active">生效中</option><option value="inactive">已停用</option></select>' +
                '<button class="btn btn-sm" data-action="refresh-blacklist">' + icon('refresh') + '刷新</button>' +
                '<div class="spacer"></div><span class="card-sub">黑名单命中直接计入评分，不影响规则命中</span>' +
            '</div>' +
            '<div class="blacklist-layout">' +
                '<div class="card table-card"><div class="table-card-head"><h3>' + icon('ban', 'title-icon') + '黑名单列表 <span class="count" id="bl-count"></span></h3><span class="card-sub">历史命中留痕保留</span></div>' +
                    '<div class="table-card-body" id="bl-table-wrap">' + skeletonTable(8) + '</div></div>' +
                '<div class="blacklist-aside" id="bl-aside">' + skeletonAside() + '</div>' +
            '</div>';
        await refreshBlacklists();
    }

    function skeletonAside() {
        return '<div class="card aside-card"><div class="skeleton skeleton-line" style="width:44%"></div><div class="skeleton skeleton-line" style="height:120px;margin-top:14px"></div></div>' +
            '<div class="card aside-card"><div class="skeleton skeleton-line" style="width:52%"></div><div class="skeleton skeleton-line"></div></div>';
    }

    async function refreshBlacklists() {
        if (state.page !== 'blacklist') return;
        const data = await API.get('/api/risk/blacklists', state.blacklistFilter);
        if (state.page !== 'blacklist') return;
        state.blacklistData = data;
        const typeCards = state.meta.blacklist_types.map((type) => {
            const count = data.type_stats[type.value] || 0;
            return '<div class="card bl-type-card ' + type.value + '"><div class="bl-type-icon">' + icon(typeIcon(type.value)) + '</div>' +
                '<div class="bl-type-info"><span>' + esc(type.label) + '黑名单</span><strong>' + count + '</strong><small>命中加 ' + type.bonus_score + ' 分</small></div></div>';
        }).join('');
        $('#bl-type-cards').innerHTML = typeCards;
        $('#bl-count').textContent = '共 ' + data.filtered_total + ' 条 · 生效 ' + data.active_count + ' 条';
        renderBlacklistTable(data);
        renderBlacklistAside(data);
    }

    function typeIcon(type) {
        return { user: 'user', phone: 'phone', address: 'address', device: 'device', ip: 'ip' }[type] || 'ban';
    }

    function renderBlacklistTable(data) {
        if (!data.items.length) {
            $('#bl-table-wrap').innerHTML = '<div class="table-empty">没有符合条件的黑名单</div>';
            return;
        }
        const rows = data.items.map((item) => (
            '<tr>' +
                '<td>' + blacklistTypeBadge(item.blacklist_type, item.blacklist_type_label) + '</td>' +
                '<td><span class="bl-value">' + esc(item.blacklist_value) + '</span></td>' +
                '<td><span class="bl-remark" title="' + attr(item.remark) + '">' + esc(item.remark || '—') + '</span></td>' +
                '<td><span class="badge ' + (item.status === 'active' ? 'badge-low' : 'badge-neutral') + '">' + esc(item.status_label) + '</span></td>' +
                '<td><span class="hit-count-badge ' + (item.hit_count ? 'active' : '') + '">' + esc(item.hit_count) + '</span></td>' +
                '<td class="mono">' + esc(fmtTimeShort(item.created_at)) + '</td>' +
                '<td><div class="row-actions"><button class="icon-btn danger" data-action="delete-blacklist" data-id="' + item.id + '" data-value="' + attr(item.blacklist_value) + '" title="删除">' + icon('trash') + '</button></div></td>' +
            '</tr>'
        )).join('');
        $('#bl-table-wrap').innerHTML =
            '<div class="table-wrap blacklist-table" style="max-height:524px"><table class="data-table blacklist-table">' +
                '<thead><tr><th style="width:74px">类型</th><th style="width:172px">命中值</th><th>备注</th><th style="width:76px">状态</th><th style="width:58px">命中</th><th style="width:102px">创建时间</th><th style="width:46px"></th></tr></thead>' +
                '<tbody>' + rows + '</tbody></table></div>';
    }

    function renderBlacklistAside(data) {
        const segments = state.meta.blacklist_types.map((type) => ({
            label: type.label, value: data.type_stats[type.value] || 0, color: BLACKLIST_COLORS[type.value] || '#2f6bff'
        }));
        const total = segments.reduce((sum, item) => sum + item.value, 0);
        const legend = segments.map((item) =>
            '<div class="legend-item"><span class="legend-dot" style="background:' + item.color + '"></span><span>' + esc(item.label) + '</span><strong>' + item.value + '</strong></div>').join('');
        const recent = (data.items || []).filter((item) => item.hit_count > 0).sort((a, b) => b.hit_count - a.hit_count).slice(0, 3);
        $('#bl-aside').innerHTML =
            '<div class="card aside-card"><h3>' + icon('chart') + '类型分布</h3>' +
                '<div class="donut-mini-wrap">' + donutSvg(segments, 122, total, '黑名单总数') + '<div class="legend">' + legend + '</div></div></div>' +
            '<div class="card aside-card"><h3>' + icon('bolt') + '生效机制</h3>' +
                '<div class="mechanism-list">' +
                    '<div class="mechanism-item"><i>1</i><p><strong>检查时匹配</strong>：按用户 / 手机号 / 地址 / 设备 / IP 五类实时比对生效条目。</p></div>' +
                    '<div class="mechanism-item"><i>2</i><p><strong>直接加权</strong>：命中后按类型加分，并写入特征快照与命中留痕。</p></div>' +
                    '<div class="mechanism-item"><i>3</i><p><strong>审计保留</strong>：删除黑名单不清理历史命中记录，评估结果可回溯。</p></div>' +
                '</div></div>' +
            '<div class="card aside-card"><h3>' + icon('ban') + '近期命中</h3>' +
                (recent.length ? '<div class="blacklist-mini-list">' + recent.map((item) =>
                    '<div class="blacklist-mini"><span class="bl-type">' + esc(item.blacklist_type_label) + '</span><span class="bl-val" title="' + attr(item.blacklist_value) + '">' + esc(item.blacklist_value) + '</span><span class="bl-score">×' + item.hit_count + '</span></div>').join('') + '</div>'
                    : '<div class="hit-empty">暂无命中记录</div>') + '</div>';
    }

    function openBlacklistModal() {
        openModal(
            '<div class="modal-panel">' +
                '<div class="modal-head"><div class="modal-head-icon">' + icon('ban') + '</div>' +
                    '<div class="modal-head-text"><h3>新增黑名单</h3><p>命中后在风险检查中直接加分并进入特征快照</p></div>' +
                    '<button class="modal-close" data-close-modal type="button">' + icon('close') + '</button></div>' +
                '<div class="modal-body">' +
                    '<div class="form-grid">' +
                        '<div class="field"><label>黑名单类型 <span class="req">*</span></label><select id="bl-type" class="select">' +
                            state.meta.blacklist_types.map((item) => '<option value="' + attr(item.value) + '">' + esc(item.label) + '（+' + item.bonus_score + ' 分）</option>').join('') + '</select></div>' +
                        '<div class="field"><label>状态</label><select id="bl-status" class="select"><option value="active">生效中</option><option value="inactive">已停用</option></select></div>' +
                    '</div>' +
                    '<div class="field"><label>命中值 <span class="req">*</span></label><input id="bl-value" class="input" placeholder="用户编号 / 手机号 / 地址ID / 设备ID / IP"></div>' +
                    '<div class="field"><label>备注</label><input id="bl-remark" class="input" placeholder="说明拉黑原因，最多 200 字"></div>' +
                    '<div class="import-help">示例：<code>device</code> 类型填写 <code>DEV-9900</code>；<code>phone</code> 填写完整手机号；<code>ip</code> 填写 IPv4 / IPv6。</div>' +
                '</div>' +
                '<div class="modal-foot"><span class="left-note">新增后立即参与风险检查</span><button class="btn" data-close-modal type="button">取消</button>' +
                    '<button class="btn btn-primary" id="save-blacklist" type="button">' + icon('check') + '保存黑名单</button></div>' +
            '</div>',
            () => {
                $('#save-blacklist').addEventListener('click', async () => {
                    const button = $('#save-blacklist');
                    const value = $('#bl-value').value.trim();
                    if (!value) { toast('请填写命中值', 'warning'); return; }
                    button.disabled = true;
                    try {
                        await API.post('/api/risk/blacklists', {
                            blacklist_type: $('#bl-type').value,
                            blacklist_value: value,
                            remark: $('#bl-remark').value.trim(),
                            status: $('#bl-status').value
                        });
                        toast('黑名单已新增', 'success');
                        closeModal();
                        await refreshBlacklists();
                    } catch (error) {
                        toast(error.message, 'error');
                        button.disabled = false;
                    }
                });
            }
        );
    }

    function openImportModal() {
        openModal(
            '<div class="modal-panel">' +
                '<div class="modal-head"><div class="modal-head-icon">' + icon('upload') + '</div>' +
                    '<div class="modal-head-text"><h3>批量导入黑名单</h3><p>每行一条，格式：类型, 命中值, 备注（备注可省略）</p></div>' +
                    '<button class="modal-close" data-close-modal type="button">' + icon('close') + '</button></div>' +
                '<div class="modal-body">' +
                    '<div class="import-help">类型可填写 <code>user</code> / <code>phone</code> / <code>address</code> / <code>device</code> / <code>ip</code>，也支持中文类型。重复条目会进入失败明细。</div>' +
                    '<textarea id="import-text" class="textarea import-textarea" placeholder="device,DEV-TEST-001,测试设备拉黑&#10;phone,13800009999,异常号码&#10;ip,203.0.113.9,代理 IP"></textarea>' +
                    '<div class="import-help" style="margin-top:8px">最多单次导入 500 条；导入成功后立即参与风险检查。</div>' +
                '</div>' +
                '<div class="modal-foot"><span class="left-note">支持中文逗号分隔</span><button class="btn" data-close-modal type="button">取消</button>' +
                    '<button class="btn btn-primary" id="do-import" type="button">' + icon('upload') + '开始导入</button></div>' +
            '</div>',
            () => {
                $('#do-import').addEventListener('click', async () => {
                    const button = $('#do-import');
                    const lines = $('#import-text').value.split(/\r?\n/).map((line) => line.trim()).filter((line) => line && line.indexOf('#') !== 0);
                    if (!lines.length) { toast('请粘贴至少一条黑名单', 'warning'); return; }
                    const aliases = { '用户': 'user', '手机号': 'phone', '地址': 'address', '设备': 'device', 'IP': 'ip', 'ip': 'ip' };
                    const items = [];
                    const invalid = [];
                    lines.forEach((line, index) => {
                        const parts = line.split(/[,，]/).map((part) => part.trim());
                        const type = aliases[parts[0]] || parts[0];
                        if (!type || !parts[1]) { invalid.push(index + 1); return; }
                        items.push({ blacklist_type: type, blacklist_value: parts[1], remark: parts.slice(2).join(','), status: 'active' });
                    });
                    if (!items.length) { toast('没有解析到有效条目，请检查格式', 'error'); return; }
                    button.disabled = true;
                    try {
                        const result = await API.post('/api/risk/blacklists/import', { items: items });
                        let message = '成功导入 ' + result.success_count + ' 条';
                        if (result.failed_count) message += '，失败 ' + result.failed_count + ' 条';
                        if (invalid.length) message += '，格式错误 ' + invalid.length + ' 行';
                        toast(message, result.failed_count ? 'warning' : 'success');
                        closeModal();
                        await refreshBlacklists();
                    } catch (error) {
                        toast(error.message, 'error');
                        button.disabled = false;
                    }
                });
            }
        );
    }

    function deleteBlacklist(id, value) {
        openConfirm({
            title: '删除黑名单',
            subtitle: '删除后立即停止匹配',
            message: '确认删除黑名单条目 <strong>' + esc(value) + '</strong> 吗？',
            warning: '历史命中记录会保留用于审计，但后续风险检查将不再命中该条目。',
            confirmText: '确认删除',
            onConfirm: async () => {
                await API.post('/api/risk/blacklists/delete', { id: id });
                toast('黑名单条目已删除', 'success');
                await refreshBlacklists();
            }
        });
    }

    /* ---------------------------------------------------------------------
     * 用户画像页
     * ------------------------------------------------------------------- */
    async function renderProfile() {
        const content = $('#page-content');
        content.innerHTML =
            pageHead('用户画像', '聚合用户交易、售后、投诉、设备、风险事件与关联案件',
                '<div class="profile-search"><div class="search-box">' + icon('search') +
                    '<input id="profile-search" class="input" list="profile-user-options" placeholder="输入用户编号，例如 U1001"></div>' +
                    '<datalist id="profile-user-options">' + state.users.map((user) => '<option value="' + attr(user.user_id) + '">' + esc(user.user_name) + '</option>').join('') + '</datalist>' +
                    '<button class="btn btn-primary" id="profile-search-btn">' + icon('search') + '查询画像</button></div>') +
            '<div class="case-summary-chips" style="margin-top:-4px">' +
                state.demos.map((sample) => '<button class="chip" data-action="load-profile" data-user="' + attr(sample.user_id) + '">' +
                    esc(sample.user_name || sample.user_id) + ' · ' + esc(sample.user_id) + ' <span class="chip-count">' + esc(sample.event_type_label) + '</span></button>').join('') +
            '</div>' +
            '<div id="profile-body">' + profileSkeleton() + '</div>';
        const submit = () => {
            const userId = $('#profile-search').value.trim().toUpperCase();
            if (!userId) { toast('请输入用户编号', 'warning'); return; }
            loadProfile(userId);
        };
        $('#profile-search-btn').addEventListener('click', submit);
        $('#profile-search').addEventListener('keydown', (event) => {
            if (event.key === 'Enter') submit();
        });
        const defaultUser = (state.demos.find((item) => item.sample_key === 'high') || {}).user_id ||
            (state.users[0] || {}).user_id || 'U1001';
        await loadProfile(defaultUser);
    }

    function profileSkeleton() {
        return '<div class="card skeleton" style="height:96px;margin-bottom:15px"></div>' +
            '<div class="profile-stats">' + new Array(6).fill(0).map(() => '<div class="card skeleton" style="height:78px"></div>').join('') + '</div>' +
            '<div class="profile-grid"><div class="profile-left"><div class="card skeleton" style="height:220px"></div></div>' +
            '<div class="profile-right"><div class="card skeleton" style="height:220px"></div></div></div>';
    }

    async function loadProfile(userId) {
        const body = $('#profile-body');
        if (!body) return;
        body.innerHTML = profileSkeleton();
        try {
            const data = await API.get('/api/risk/users/' + encodeURIComponent(userId) + '/profile');
            if (state.page !== 'profile') return;
            renderProfileData(data);
            $('#profile-search').value = userId;
            state.profileUser = userId;
        } catch (error) {
            if (state.page !== 'profile') return;
            body.innerHTML = '<div class="card">' + emptyState('user', '未找到用户', error.message) + '</div>';
            toast(error.message, 'error');
        }
    }

    function renderProfileData(data) {
        const user = data.user;
        const stats = data.stats;
        const heroBadges = [
            '<span class="badge badge-info">' + (user.is_enterprise ? '企业采购' : '个人用户') + '</span>',
            '<span class="badge badge-neutral">' + esc(user.vip_level) + '</span>',
            user.blacklisted ? '<span class="badge badge-high"><span class="dot"></span>黑名单用户</span>' : '<span class="badge badge-low"><span class="dot"></span>黑名单正常</span>'
        ].join('');
        const recentRows = (data.recent_events || []).length ? data.recent_events.map((item) => (
            '<tr' + (item.case_id ? ' class="clickable" data-action="open-case" data-id="' + item.case_id + '"' : '') + '>' +
                '<td class="mono">' + esc(fmtTimeShort(item.created_at)) + '</td>' +
                '<td><span class="badge badge-neutral">' + esc(item.event_type_label) + '</span></td>' +
                '<td class="mono">' + esc(item.order_id) + '</td>' +
                '<td><span class="score-text">' + Number(item.risk_score).toFixed(1) + '</span></td>' +
                '<td>' + levelBadge(item.risk_level, item.risk_level_label) + '</td>' +
                '<td>' + decisionBadge(item.decision, item.decision_label) + '</td>' +
                '<td>' + (item.case_no ? '<span class="case-no">' + esc(item.case_no) + '</span>' : '<span class="reviewer-empty">—</span>') + '</td></tr>'
        )).join('') : '<tr><td colspan="7"><div class="table-empty">暂无风险事件</div></td></tr>';
        const caseRows = (data.cases || []).length ? data.cases.map((item) => (
            '<tr class="clickable" data-action="open-case" data-id="' + item.case_id + '">' +
                '<td><span class="case-no">' + esc(item.case_no) + '</span></td>' +
                '<td><span class="badge badge-neutral">' + esc(item.event_type_label) + '</span></td>' +
                '<td><span class="score-text">' + Number(item.risk_score).toFixed(1) + '</span></td>' +
                '<td>' + levelBadge(item.risk_level, item.risk_level_label) + '</td>' +
                '<td>' + caseStatusBadge(item.case_status, item.case_status_label) + '</td>' +
                '<td>' + esc(item.reviewer_name || '待分配') + '</td>' +
                '<td class="mono">' + esc(fmtTimeShort(item.created_at)) + '</td></tr>'
        )).join('') : '<tr><td colspan="7"><div class="table-empty">暂无关联案件</div></td></tr>';
        const addressHtml = (data.addresses || []).length ? data.addresses.slice(0, 3).map((item) => (
            '<div class="address-item"><div class="addr-top"><strong>' + esc(item.city) + '</strong>' +
                (item.is_default ? '<span class="badge badge-info">默认</span>' : '') + '</div>' +
                '<p>' + esc(item.full_address) + '</p><div class="addr-meta">变更 ' + esc(item.change_cnt) + ' 次 · 创建于 ' + esc(fmtTimeShort(item.created_at)) + '</div></div>'
        )).join('') : '<div class="hit-empty">暂无地址信息</div>';
        const blacklistHtml = (data.blacklist_hits || []).length ? data.blacklist_hits.map((hit) => (
            '<div class="blacklist-mini"><span class="bl-type">' + esc(labelOf(state.dicts.blacklist, hit.blacklist_type)) + '</span>' +
                '<span class="bl-val" title="' + attr(hit.blacklist_value) + '">' + esc(hit.blacklist_value) + '</span>' +
                '<span class="bl-score">+' + Number(hit.added_score).toFixed(0) + '</span></div>'
        )).join('') : '<div class="hit-empty">暂无黑名单命中</div>';

        $('#profile-body').innerHTML =
            '<div class="card profile-hero"><div class="profile-avatar">' + esc((user.user_name || '?').slice(0, 1)) + '</div>' +
                '<div class="profile-main"><div class="profile-name-row"><h2>' + esc(user.user_name) + '</h2>' + heroBadges + '</div>' +
                    '<div class="profile-sub"><span>用户编号 <strong>' + esc(user.user_id) + '</strong></span><span class="sep"></span>' +
                        '<span>手机号 ' + esc(user.phone) + '</span><span class="sep"></span><span>' + esc(user.register_province) + ' · ' + esc(user.register_city) + '</span>' +
                        '<span class="sep"></span><span>注册 ' + user.register_days + ' 天</span><span class="sep"></span><span>注册时间 ' + esc(fmtTimeFull(user.register_at)) + '</span></div></div>' +
                '<div class="profile-hero-side">' +
                    '<div class="hero-metric"><span>信用分</span><strong class="' + (user.credit_score < 60 ? 'red' : user.credit_score < 75 ? 'orange' : 'green') + '">' + user.credit_score + '</strong></div>' +
                    '<div class="hero-metric"><span>历史高风险</span><strong class="red">' + stats.high_risk_count + '</strong></div>' +
                    '<div class="hero-metric"><span>退款率</span><strong>' + fmtPct(stats.refund_rate) + '</strong></div>' +
                '</div></div>' +
            '<div class="profile-stats">' +
                profileStat('order', '历史订单', stats.order_count, '累计 ' + fmtMoney(stats.total_amount) + ' 元') +
                profileStat('refresh', '退款次数', stats.refund_count, '退款率 ' + fmtPct(stats.refund_rate)) +
                profileStat('alert', '投诉次数', stats.complaint_count, '物流 / 售后投诉') +
                profileStat('address', '收货地址', stats.address_count, '地址变更可追溯') +
                profileStat('device', '关联设备', stats.device_count, '登录城市 ' + stats.login_city_count + ' 个') +
                profileStat('shield', '高风险次数', stats.high_risk_count, '历史高风险评估') +
            '</div>' +
            '<div class="profile-grid">' +
                '<div class="profile-left">' +
                    '<div class="card table-card"><div class="table-card-head"><h3>' + icon('clock', 'title-icon') + '最近风险事件 <span class="count">' + (data.recent_events || []).length + '</span></h3><span class="card-sub">最近 10 条</span></div>' +
                        '<div class="table-card-body"><div class="table-wrap"><table class="data-table profile-table"><thead><tr><th>时间</th><th>事件</th><th>订单</th><th>评分</th><th>等级</th><th>建议</th><th>案件</th></tr></thead><tbody>' + recentRows + '</tbody></table></div></div></div>' +
                    '<div class="card table-card"><div class="table-card-head"><h3>' + icon('folder', 'title-icon') + '关联案件 <span class="count">' + (data.cases || []).length + '</span></h3><span class="card-sub">点击查看详情</span></div>' +
                        '<div class="table-card-body"><div class="table-wrap"><table class="data-table profile-table"><thead><tr><th>案件号</th><th>事件</th><th>评分</th><th>等级</th><th>状态</th><th>审核人</th><th>创建</th></tr></thead><tbody>' + caseRows + '</tbody></table></div></div></div>' +
                '</div>' +
                '<div class="profile-right">' +
                    '<div class="card profile-aside-card"><div class="detail-card-head"><h3>风险趋势</h3><span class="sub">最近 ' + (data.risk_trend || []).length + ' 次评估</span></div>' +
                        '<div class="mini-chart-wrap">' + scoreTrendSvg(data.risk_trend) + '</div></div>' +
                    '<div class="card profile-aside-card"><div class="detail-card-head"><h3>收货地址</h3><span class="sub">' + (data.addresses || []).length + ' 个</span></div>' +
                        '<div class="address-list">' + addressHtml + '</div></div>' +
                    '<div class="card profile-aside-card"><div class="detail-card-head"><h3>黑名单命中</h3><span class="sub">最近 5 条</span></div>' +
                        '<div class="blacklist-mini-list">' + blacklistHtml + '</div></div>' +
                '</div>' +
            '</div>';
    }

    function profileStat(iconName, label, value, sub) {
        return '<div class="card profile-stat"><div class="p-icon">' + icon(iconName) + '</div><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong><small>' + esc(sub) + '</small></div>';
    }

    /* ---------------------------------------------------------------------
     * 运营看板页
     * ------------------------------------------------------------------- */
    async function renderDashboard() {
        const content = $('#page-content');
        content.innerHTML =
            pageHead('运营看板', '实时监测风险事件、案件处理效率、规则命中与黑名单处置效果',
                '<span class="badge badge-low"><span class="dot"></span>实时数据</span><button class="btn" data-action="refresh-dashboard">' + icon('refresh') + '刷新数据</button>') +
            '<div class="kpi-grid" id="dashboard-kpis">' + skeletonKpis() + '</div>' +
            '<div class="dashboard-grid">' +
                '<div class="card chart-card"><div class="chart-head"><div><h3>近 7 日风险趋势</h3><p>风险事件量、高风险事件与新增案件</p></div><span class="chart-tag">按日统计</span></div>' +
                    '<div class="chart-body" id="trend-chart">' + skeletonChart() + '</div>' +
                    '<div class="chart-legend"><span class="item"><span class="line" style="background:#2f6bff"></span>风险事件 <strong id="trend-events">—</strong></span>' +
                        '<span class="item"><span class="line dashed"></span>高风险 <strong id="trend-high">—</strong></span>' +
                        '<span class="item" style="margin-left:auto">数据更新 <strong id="dashboard-updated">—</strong></span></div></div>' +
                '<div class="card chart-card donut-card"><div class="chart-head"><div><h3>风险等级分布</h3><p>全部风险评估结果构成</p></div><span class="chart-tag">0-100 分</span></div>' +
                    '<div class="chart-body"><div class="donut-wrap" id="level-donut">' + skeletonChart() + '</div></div></div>' +
            '</div>' +
            '<div class="dashboard-grid">' +
                '<div class="card rank-card"><div class="chart-head"><div><h3>规则命中排行</h3><p>按累计命中次数排序，展示规则运营效果</p></div><span class="chart-tag">TOP 8</span></div>' +
                    '<div class="rank-list" id="rule-rank">' + skeletonRows(6) + '</div></div>' +
                '<div class="card rank-card"><div class="chart-head"><div><h3>黑名单命中</h3><p>按类型与取值聚合命中次数</p></div><span class="chart-tag">实时</span></div>' +
                    '<div class="blacklist-hit-list" id="blacklist-rank">' + skeletonRows(5) + '</div></div>' +
            '</div>' +
            '<div class="dashboard-foot"><span>数据来源：risk_events / risk_assessments / risk_cases / rule_hits / blacklist_hit_records</span><span id="dashboard-generated">—</span></div>';
        await refreshDashboard();
    }

    function skeletonKpis() {
        return new Array(6).fill(0).map(() => '<div class="card skeleton" style="height:118px"></div>').join('');
    }

    function skeletonChart() {
        return '<div class="skeleton" style="width:100%;height:180px;border-radius:10px"></div>';
    }

    function skeletonRows(count) {
        return new Array(count).fill(0).map(() => '<div class="skeleton skeleton-line" style="height:16px"></div>').join('');
    }

    async function refreshDashboard() {
        if (state.page !== 'dashboard') return;
        const data = await API.get('/api/risk/dashboard');
        if (state.page !== 'dashboard') return;
        const kpi = data.kpi;
        $('#dashboard-kpis').innerHTML =
            kpiCard('alert', 'red', '风险事件总数', kpi.event_total, '次', '高风险 <span class="up">' + kpi.high_risk_count + '</span> 次') +
            kpiCard('chart', 'orange', '高风险占比', (kpi.event_total ? (kpi.high_risk_count / kpi.event_total * 100) : 0).toFixed(1), '%', '高风险 / 全部评估') +
            kpiCard('folder', '', '待处理案件', kpi.pending_case_count, '件', '含审核中 <span class="up">' + (data.case_status_distribution.reviewing || 0) + '</span> 件') +
            kpiCard('clock', 'green', '平均处理时长', Number(kpi.avg_handle_hours).toFixed(1), '小时', '已审核 ' + kpi.finished_case_count + ' 件') +
            kpiCard('bolt', 'purple', '规则命中次数', kpi.rule_hit_total, '次', '启用规则 ' + kpi.rule_enabled_count + ' 条') +
            kpiCard('ban', 'teal', '黑名单命中次数', kpi.blacklist_hit_total, '次', '生效黑名单 ' + kpi.blacklist_total + ' 条');

        $('#trend-chart').innerHTML = lineChartSvg(data.trend_7d);
        const weekEvents = data.trend_7d.reduce((sum, item) => sum + Number(item.event_count || 0), 0);
        const weekHigh = data.trend_7d.reduce((sum, item) => sum + Number(item.high_count || 0), 0);
        $('#trend-events').textContent = weekEvents + ' 次';
        $('#trend-high').textContent = weekHigh + ' 次';

        const levels = data.level_distribution;
        const levelTotal = Number(levels.low || 0) + Number(levels.medium || 0) + Number(levels.high || 0);
        const segments = [
            { label: '低风险', value: levels.low || 0, color: '#12b76a' },
            { label: '中风险', value: levels.medium || 0, color: '#f79009' },
            { label: '高风险', value: levels.high || 0, color: '#f04438' }
        ];
        $('#level-donut').innerHTML = donutSvg(segments, 176, levelTotal, '评估总数') +
            '<div class="donut-legend">' + segments.map((item) =>
                '<div class="item"><span class="dot" style="background:' + item.color + '"></span><strong>' + item.value + '</strong><span>' + item.label + ' · ' + (levelTotal ? ((item.value / levelTotal) * 100).toFixed(1) : '0.0') + '%</span></div>').join('') + '</div>';

        const topRows = data.rule_hit_top || [];
        const maxHit = Math.max(1, ...topRows.map((item) => Number(item.hit_count || 0)));
        $('#rule-rank').innerHTML = topRows.length ? topRows.map((item, index) => (
            '<div class="rank-row"><span class="rank-no ' + (index === 0 ? 'top1' : index === 1 ? 'top2' : index === 2 ? 'top3' : '') + '">' + (index + 1) + '</span>' +
                '<div class="rank-name"><strong title="' + attr(item.rule_name) + '">' + esc(item.rule_name) + '</strong><span>' + esc(item.rule_code) + ' · P' + esc(item.priority) + '</span></div>' +
                '<div class="rank-bar"><div class="rank-fill ' + (index === 0 ? 'hot' : '') + '" style="width:' + Math.max(4, (Number(item.hit_count) / maxHit) * 100).toFixed(1) + '%"></div></div>' +
                '<span class="rank-count">' + item.hit_count + ' 次</span></div>'
        )).join('') : '<div class="hit-empty">暂无规则命中数据</div>';

        const blRows = data.blacklist_hits || [];
        $('#blacklist-rank').innerHTML = blRows.length ? blRows.map((item) => (
            '<div class="bl-hit-row">' + blacklistTypeBadge(item.blacklist_type, item.blacklist_type_label) +
                '<div class="bl-hit-info"><strong title="' + attr(item.blacklist_value) + '">' + esc(item.blacklist_value) + '</strong><span>最近命中 ' + esc(fmtTimeShort(item.last_hit_at)) + ' · 加权 ' + Number(item.total_score).toFixed(0) + ' 分</span></div>' +
                '<div class="bl-hit-count"><strong>' + item.hit_count + '</strong><span>次命中</span></div></div>'
        )).join('') : '<div class="hit-empty">暂无黑名单命中</div>';

        $('#dashboard-updated').textContent = fmtTimeShort(data.generated_at);
        $('#dashboard-generated').textContent = '统计口径：' + data.kpi.event_total + ' 条事件 / ' + data.kpi.case_total + ' 个案件 · ' + fmtTimeFull(data.generated_at);
    }

    /* ---------------------------------------------------------------------
     * 全局事件分发
     * ------------------------------------------------------------------- */
    function onContentClick(event) {
        const target = event.target.closest('[data-action]');
        if (!target) return;
        const action = target.dataset.action;
        if (action === 'retry-check' && state.lastCheckPayload) {
            const form = $('#check-form');
            if (form) {
                form.querySelector('[name="event_type"]').value = state.lastCheckPayload.event_type;
                form.querySelector('[name="user_id"]').value = state.lastCheckPayload.user_id;
                form.querySelector('[name="order_id"]').value = state.lastCheckPayload.order_id;
                form.querySelector('[name="source_id"]').value = state.lastCheckPayload.source_id;
                runCheck();
            }
            return;
        }
        if (action === 'open-case') {
            openCaseDrawer(Number(target.dataset.id));
            return;
        }
        if (action === 'add-rule') { openRuleModal(null); return; }
        if (action === 'edit-rule') {
            const rule = state.rules.find((item) => Number(item.id) === Number(target.dataset.id));
            if (rule) openRuleModal(rule);
            return;
        }
        if (action === 'delete-rule') { deleteRule(Number(target.dataset.id)); return; }
        if (action === 'toggle-rule') { toggleRule(Number(target.dataset.id)); return; }
        if (action === 'refresh-rules') { refreshRules().catch((error) => toast(error.message, 'error')); return; }
        if (action === 'refresh-cases') { refreshCases().catch((error) => toast(error.message, 'error')); return; }
        if (action === 'filter-case') {
            const status = target.dataset.status || '';
            state.casesFilter.status = state.casesFilter.status === status ? '' : status;
            $('#case-status-filter').value = state.casesFilter.status;
            refreshCases().catch((error) => toast(error.message, 'error'));
            return;
        }
        if (action === 'reset-case-filter') {
            state.casesFilter = { status: '', level: '', keyword: '' };
            $('#case-status-filter').value = '';
            $('#case-level-filter').value = '';
            $('#case-search').value = '';
            refreshCases().catch((error) => toast(error.message, 'error'));
            return;
        }
        if (action === 'add-blacklist') { openBlacklistModal(); return; }
        if (action === 'import-blacklist') { openImportModal(); return; }
        if (action === 'delete-blacklist') { deleteBlacklist(Number(target.dataset.id), target.dataset.value || ''); return; }
        if (action === 'refresh-blacklist') { refreshBlacklists().catch((error) => toast(error.message, 'error')); return; }
        if (action === 'load-profile') {
            const userId = target.dataset.user;
            if (userId) loadProfile(userId);
            return;
        }
        if (action === 'refresh-dashboard') { refreshDashboard().catch((error) => toast(error.message, 'error')); return; }
    }

    function onContentChange(event) {
        const target = event.target;
        if (target.id === 'rule-status-filter') {
            state.rulesFilter.status = target.value;
            refreshRules().catch((error) => toast(error.message, 'error'));
        }
        if (target.id === 'case-status-filter') {
            state.casesFilter.status = target.value;
            refreshCases().catch((error) => toast(error.message, 'error'));
        }
        if (target.id === 'case-level-filter') {
            state.casesFilter.level = target.value;
            refreshCases().catch((error) => toast(error.message, 'error'));
        }
        if (target.id === 'blacklist-type-filter') {
            state.blacklistFilter.type = target.value;
            refreshBlacklists().catch((error) => toast(error.message, 'error'));
        }
        if (target.id === 'blacklist-status-filter') {
            state.blacklistFilter.status = target.value;
            refreshBlacklists().catch((error) => toast(error.message, 'error'));
        }
    }

    function onContentInput(event) {
        const target = event.target;
        if (target.id === 'rule-search') {
            state.rulesFilter.keyword = target.value.trim();
            delayedRules();
        }
        if (target.id === 'case-search') {
            state.casesFilter.keyword = target.value.trim();
            delayedCases();
        }
        if (target.id === 'blacklist-search') {
            state.blacklistFilter.keyword = target.value.trim();
            delayedBlacklists();
        }
    }

    const delayedRules = debounce(() => refreshRules().catch((error) => toast(error.message, 'error')), 280);
    const delayedCases = debounce(() => refreshCases().catch((error) => toast(error.message, 'error')), 280);
    const delayedBlacklists = debounce(() => refreshBlacklists().catch((error) => toast(error.message, 'error')), 280);
})();
