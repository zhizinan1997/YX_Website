(function () {
    const root = document.getElementById('view-site-reports');
    if (!root) return;

    const metricMap = [
        ['siteReportPvCompare', 'summary', 'pageviews'],
        ['siteReportUvCompare', 'summary', 'unique_visitors'],
        ['siteReportSessionsCompare', 'summary', 'sessions'],
        ['siteReportAvgSessionCompare', 'summary', 'avg_session_duration_sec'],
        ['siteReportBounceRateCompare', 'summary', 'bounce_rate', true, true],
        ['siteReportConversionsCompare', 'summary', 'conversion_events'],
        ['siteReportConversionRateCompare', 'summary', 'conversion_rate', false, true],
        ['siteReportCrawlerSessionsCompare', 'crawler_summary', 'sessions'],
        ['siteReportCrawlerPageviewsCompare', 'crawler_summary', 'pageviews'],
        ['siteReportCrawlerUniqueIpsCompare', 'crawler_summary', 'unique_ips'],
        ['siteReportCrawlerSourcesCompare', 'crawler_summary', 'sources']
    ];
    let comparisonRequest = 0;

    function setComparison(id, current, previous, inverse, rate, rangeLabel) {
        const element = document.getElementById(id);
        if (!element) return;
        element.classList.remove('is-positive', 'is-negative', 'is-neutral');

        if (current == null || previous == null || !Number.isFinite(Number(current)) || !Number.isFinite(Number(previous))) {
            element.classList.add('is-neutral');
            element.innerHTML = '<span>--</span><small>较上期</small>';
            element.removeAttribute('title');
            return;
        }

        const value = Number(current);
        const previousValue = Number(previous);
        const difference = value - previousValue;
        let label;
        if (rate) {
            label = `${Math.abs(difference).toFixed(2)}%`;
        } else if (previousValue === 0) {
            label = value === 0 ? '0.0%' : '新增';
        } else {
            label = `${Math.abs(difference / previousValue * 100).toFixed(1)}%`;
        }

        const direction = Math.sign(difference);
        const favorable = inverse ? direction < 0 : direction > 0;
        element.classList.add(direction === 0 ? 'is-neutral' : favorable ? 'is-positive' : 'is-negative');
        const arrow = direction > 0 ? '▲' : direction < 0 ? '▼' : '';
        element.innerHTML = `<span>${arrow} ${label}</span><small>较上期</small>`;
        element.title = rate ? `较上期变化 ${difference.toFixed(2)} 个百分点；${rangeLabel}` : `较上期变化；${rangeLabel}`;
    }

    function formatIsoDate(date) {
        return date.toISOString().slice(0, 10);
    }

    function previousRange(startText, endText) {
        const start = new Date(`${startText}T00:00:00Z`);
        const end = new Date(`${endText}T00:00:00Z`);
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end < start) return null;
        const length = Math.round((end - start) / 86400000) + 1;
        return {
            start: formatIsoDate(new Date(start.getTime() - length * 86400000)),
            end: formatIsoDate(new Date(start.getTime() - 86400000))
        };
    }

    async function renderComparison(currentData) {
        const currentRequest = ++comparisonRequest;
        metricMap.forEach(([id]) => setComparison(id, NaN, NaN));
        const startDate = document.getElementById('siteReportStartDate')?.value;
        const endDate = document.getElementById('siteReportEndDate')?.value;
        const range = previousRange(startDate, endDate);
        if (!range) return;

        const params = new URLSearchParams({
            start_date: range.start,
            end_date: range.end,
            granularity: document.getElementById('siteReportGranularity')?.value || 'day'
        });
        try {
            const response = await fetch(`/api/admin/site-reports?${params}`, { cache: 'no-store' });
            if (!response.ok) return;
            const previousData = await response.json();
            if (currentRequest !== comparisonRequest || previousData.success !== true) return;
            metricMap.forEach(([id, group, key, inverse, rate]) => {
                setComparison(id, currentData?.[group]?.[key], previousData?.[group]?.[key], inverse, rate,
                    `${range.start} 至 ${range.end}`);
            });
        } catch (_) {
            // Current-period statistics stay usable when the comparison request fails.
        }
    }

    function mirrorTrendFilters() {
        const pairs = [
            ['siteReportStartDate', 'siteReportTrendStartDate'],
            ['siteReportEndDate', 'siteReportTrendEndDate'],
            ['siteReportGranularity', 'siteReportTrendGranularity']
        ];
        pairs.forEach(([sourceId, targetId]) => {
            const source = document.getElementById(sourceId);
            const target = document.getElementById(targetId);
            if (source && target) target.value = source.value;
        });
    }

    function syncSiteReportTrendFilters() {
        const pairs = [
            ['siteReportTrendStartDate', 'siteReportStartDate'],
            ['siteReportTrendEndDate', 'siteReportEndDate'],
            ['siteReportTrendGranularity', 'siteReportGranularity']
        ];
        pairs.forEach(([sourceId, targetId]) => {
            const source = document.getElementById(sourceId);
            const target = document.getElementById(targetId);
            if (source && target) target.value = source.value;
        });
        if (typeof window.loadSiteReports === 'function') window.loadSiteReports();
    }

    function switchSiteReportTab(tabName, scrollToTabs = false) {
        const tabs = [...root.querySelectorAll('.site-report-tab')];
        if (!tabs.some(tab => tab.dataset.reportTab === tabName)) return;
        tabs.forEach(tab => {
            const active = tab.dataset.reportTab === tabName;
            tab.classList.toggle('is-active', active);
            tab.setAttribute('aria-selected', active ? 'true' : 'false');
            tab.tabIndex = active ? 0 : -1;
        });
        root.querySelectorAll('[data-site-report-tab]').forEach(section => {
            section.hidden = section.dataset.siteReportTab !== tabName;
        });
        if (scrollToTabs) root.querySelector('.site-report-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function exportSiteReportTrend() {
        const source = document.querySelector('#siteReportTrend .site-report-line-svg');
        if (!source) return;
        const svg = source.cloneNode(true);
        const namespace = 'http://www.w3.org/2000/svg';
        svg.setAttribute('xmlns', namespace);
        const styles = document.createElementNS(namespace, 'style');
        styles.textContent = `
            text { font-family: Arial, sans-serif; }
            .site-report-line-grid { stroke: #e3ebf5; stroke-width: 1; stroke-dasharray: 4 4; }
            .site-report-line-axis { stroke: #bfd0e5; stroke-width: 1.5; }
            .site-report-line-pv { fill: none; stroke: #2077f4; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
            .site-report-line-uv { fill: none; stroke: #05bf69; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
            .site-report-line-point-pv { fill: #fff; stroke: #2077f4; stroke-width: 2; }
            .site-report-line-point-uv { fill: #fff; stroke: #05bf69; stroke-width: 2; }
            .site-report-line-label, .site-report-line-y-label { fill: #627999; font-size: 12px; }
        `;
        svg.insertBefore(styles, svg.firstChild);
        const background = document.createElementNS(namespace, 'rect');
        background.setAttribute('width', '100%');
        background.setAttribute('height', '100%');
        background.setAttribute('fill', '#ffffff');
        svg.insertBefore(background, styles.nextSibling);
        const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `site-trend-${document.getElementById('siteReportStartDate')?.value || 'start'}-${document.getElementById('siteReportEndDate')?.value || 'end'}.svg`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    root.querySelector('.site-report-tabs')?.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const tabs = [...root.querySelectorAll('.site-report-tab')];
        const current = tabs.indexOf(document.activeElement);
        if (current < 0) return;
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
            : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        switchSiteReportTab(tabs[next].dataset.reportTab);
        tabs[next].focus();
    });

    window.AdminSiteReportUI = {
        afterLoad(data) {
            mirrorTrendFilters();
            renderComparison(data);
        }
    };
    window.switchSiteReportTab = switchSiteReportTab;
    window.syncSiteReportTrendFilters = syncSiteReportTrendFilters;
    window.exportSiteReportTrend = exportSiteReportTrend;
    switchSiteReportTab('overview');
})();
