(function () {
    'use strict';

    var ROOT_ID = 'mc-nav-root';
    var PROFILE_ATTR = 'data-nav-profile';
    var NAV_CSS_ID = 'mc-nav-component-css';
    var CHATBOT_SCRIPT_SRC = '/assets/js/chatbot.js';

    function getRoot() {
        return document.getElementById(ROOT_ID);
    }

    function getProfile(root) {
        var profile = (root.getAttribute(PROFILE_ATTR) || '').trim();
        if (profile === 'home' || profile === 'gas' || profile === 'bio') {
            return profile;
        }
        return 'home';
    }

    function ensureNoScriptFallback(root, profile) {
        var fallback = root.nextElementSibling;
        if (!fallback || fallback.tagName.toLowerCase() !== 'noscript') {
            return;
        }
        if (!fallback.innerHTML || !fallback.innerHTML.trim()) {
            fallback.innerHTML = '<div>导航不可用</div>';
        }
        fallback.setAttribute('data-nav-noscript-profile', profile);
    }

    function fetchText(url) {
        return fetch(url, { credentials: 'same-origin' }).then(function (res) {
            if (!res.ok) {
                throw new Error('Failed to load: ' + url + ' (' + res.status + ')');
            }
            return res.text();
        });
    }

    function ensureNavStylesheet() {
        if (document.getElementById(NAV_CSS_ID)) return;
        var link = document.createElement('link');
        link.id = NAV_CSS_ID;
        link.rel = 'stylesheet';
        link.href = '/assets/css/nav-component.css';
        document.head.appendChild(link);
    }

    function ensureChatbotScript() {
        var exists = Array.prototype.some.call(document.getElementsByTagName('script'), function (s) {
            var src = s.getAttribute('src') || '';
            return src.indexOf('chatbot.js') !== -1;
        });
        if (exists) return;
        var script = document.createElement('script');
        script.src = CHATBOT_SCRIPT_SRC;
        script.defer = true;
        document.body.appendChild(script);
    }

    function injectPartial(root, profile) {
        return fetchText('/assets/partials/nav-' + profile + '.html').then(function (html) {
            root.innerHTML = html;
        });
    }

    function bindCommonInteractions(root) {
        window.showPanel = function (panelId, tab) {
            var menu = tab && tab.closest('.vs-mega-menu');
            if (!menu) return;
            menu.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(function (p) { p.classList.remove('active'); });
            var panel = document.getElementById('panel-' + panelId);
            if (panel) panel.classList.add('active');
        };

        window.showPanelContact = function (panelId, tab) {
            var menu = tab && tab.closest('.vs-mega-menu');
            if (!menu) return;
            menu.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(function (p) { p.classList.remove('active'); });
            var panel = document.getElementById('panel-contact-' + panelId);
            if (panel) panel.classList.add('active');
        };

        window.showPanelSolutions = function (panelId, tab) {
            var menu = tab && tab.closest('.vs-mega-menu');
            if (!menu) return;
            menu.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(function (p) { p.classList.remove('active'); });
            var panel = document.getElementById('panel-solutions-' + panelId);
            if (panel) panel.classList.add('active');
        };

        window.showPanelCases = function (panelId, tab) {
            var menu = tab && tab.closest('.vs-mega-menu');
            if (!menu) return;
            menu.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(function (p) { p.classList.remove('active'); });
            var panel = document.getElementById('panel-cases-' + panelId);
            if (panel) panel.classList.add('active');
        };

        window.showPanelNews = function (panelId, tab) {
            var menu = tab && tab.closest('.vs-mega-menu');
            if (!menu) return;
            menu.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            menu.querySelectorAll('.vs-mega-panel').forEach(function (p) { p.classList.remove('active'); });
            var panel = document.getElementById('panel-news-' + panelId);
            if (panel) panel.classList.add('active');
        };

        window.activateLinkTab = function (tab) {
            var sidebar = tab && tab.closest('.vs-mega-sidebar');
            if (!sidebar) return;
            sidebar.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
        };

        var mobileToggle = root.querySelector('.vs-mobile-toggle');
        var nav = root.querySelector('.vs-nav');
        if (mobileToggle && nav) {
            mobileToggle.addEventListener('click', function () {
                nav.classList.toggle('is-open');
                mobileToggle.classList.toggle('is-open');
            });
        }

        // Smooth mega-menu switching on fast pointer movement.
        (function bindMegaHoverBuffer() {
            var items = root.querySelectorAll('.vs-nav__item--has-mega');
            if (!items.length) return;
            var closeTimer = null;
            var closeDelay = 90;

            function closeAll() {
                items.forEach(function (it) { it.classList.remove('is-mega-open'); });
            }

            items.forEach(function (item) {
                item.addEventListener('mouseenter', function () {
                    if (closeTimer) {
                        clearTimeout(closeTimer);
                        closeTimer = null;
                    }
                    closeAll();
                    item.classList.add('is-mega-open');
                });

                item.addEventListener('mouseleave', function () {
                    if (closeTimer) clearTimeout(closeTimer);
                    closeTimer = setTimeout(function () {
                        item.classList.remove('is-mega-open');
                    }, closeDelay);
                });
            });

            root.addEventListener('mouseleave', function () {
                if (closeTimer) clearTimeout(closeTimer);
                closeTimer = setTimeout(closeAll, closeDelay);
            });
        })();
    }

    function safeSetHtml(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    function buildRecommendationLink(item) {
        var url = (item && item.url) ? String(item.url) : '#';
        var name = (item && item.name) ? String(item.name) : '未命名链接';
        var external = /^https?:\/\//i.test(url);
        var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        return '<li><a href="' + url + '"' + target + '>' + name + '</a></li>';
    }

    function buildProductHref(product) {
        var id = String(product.id || '');
        if (!id) return '#';
        if (id.startsWith('../customization/')) {
            return '/pages/customization/' + id.replace('../customization/', '') + '.html';
        }
        if (id.startsWith('../biosensing/')) {
            return '/pages/biosensing/' + id.replace('../biosensing/', '') + '.html';
        }
        if (id.startsWith('/')) return id;
        if (id.endsWith('.html')) return '/pages/gassensing/' + id;
        return '/pages/gassensing/' + id + '.html';
    }

    function bindGasDynamicData() {
        var jobs = [];

        if (document.getElementById('dynamic-product-list')) {
            jobs.push(
                fetch('/api/products/with-settings', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var products = (data.products || []).filter(function (p) { return !p.hidden; });
                        if (!products.length) {
                            safeSetHtml('dynamic-product-list', '<p style="color:#666;">暂无产品</p>');
                            return;
                        }
                        var half = Math.ceil(products.length / 2);
                        var render = function (p) {
                            var displayName = p.displayName || p.shortName || p.name || '';
                            var badge = p.isNew ? '<span style="background:#ff4444;color:white;font-size:10px;padding:1px 5px;border-radius:8px;margin-left:5px;vertical-align:middle;">NEW</span>' : '';
                            return '<li><a href="' + buildProductHref(p) + '">' + displayName + badge + '</a></li>';
                        };
                        var left = products.slice(0, half).map(render).join('');
                        var right = products.slice(half).map(render).join('');
                        safeSetHtml('dynamic-product-list', '<div><ul class="vs-mega-list-v2">' + left + '</ul></div><div><ul class="vs-mega-list-v2">' + right + '</ul></div>');
                    })
                    .catch(function () {
                        safeSetHtml('dynamic-product-list', '<p style="color:#666;">加载产品列表失败</p>');
                    })
            );
        }

        if (document.getElementById('latestReleasesList') || document.getElementById('applicationAreasList')) {
            jobs.push(
                fetch('/api/recommendations', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (document.getElementById('latestReleasesList')) {
                            safeSetHtml('latestReleasesList', (data.latestReleases || []).map(buildRecommendationLink).join('') || '<li><a href="#">暂无数据</a></li>');
                        }
                        if (document.getElementById('applicationAreasList')) {
                            safeSetHtml('applicationAreasList', (data.applicationAreas || []).map(buildRecommendationLink).join('') || '<li><a href="#">暂无数据</a></li>');
                        }
                    })
                    .catch(function () {
                        if (document.getElementById('latestReleasesList')) safeSetHtml('latestReleasesList', '<li><a href="#">加载失败</a></li>');
                        if (document.getElementById('applicationAreasList')) safeSetHtml('applicationAreasList', '<li><a href="#">加载失败</a></li>');
                    })
            );
        }

        if (document.getElementById('categoriesLeft') || document.getElementById('categoriesRight')) {
            jobs.push(
                fetch('/api/products/industry-filters', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var categories = Array.isArray(data.categories) ? data.categories : [];
                        var half = Math.ceil(categories.length / 2);
                        var left = categories.slice(0, half);
                        var right = categories.slice(half);
                        var render = function (cat) {
                            return '<li><a href="/pages/gassensing/all-products.html?filter=' + encodeURIComponent(cat.key) + '">' + cat.name + '</a></li>';
                        };
                        if (document.getElementById('categoriesLeft')) {
                            safeSetHtml('categoriesLeft', left.length ? left.map(render).join('') : '<li><a href="/pages/gassensing/all-products.html">全部产品</a></li>');
                        }
                        if (document.getElementById('categoriesRight')) {
                            safeSetHtml('categoriesRight', right.length ? right.map(render).join('') : '');
                        }
                    })
                    .catch(function () {
                        if (document.getElementById('categoriesLeft')) safeSetHtml('categoriesLeft', '<li><a href="/pages/gassensing/all-products.html">加载失败</a></li>');
                    })
            );
        }

        if (document.getElementById('measurementTargetsLeft') || document.getElementById('measurementTargetsRight')) {
            jobs.push(
                fetch('/api/measurement-targets', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        var half = Math.ceil(items.length / 2);
                        var left = items.slice(0, half);
                        var right = items.slice(half);
                        var render = function (item) {
                            var url = (item && item.url) ? String(item.url) : '#';
                            var name = (item && item.name) ? String(item.name) : '未命名';
                            var external = /^https?:\/\//i.test(url);
                            var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';
                            return '<li><a href="' + url + '"' + target + '>' + name + '</a></li>';
                        };
                        if (document.getElementById('measurementTargetsLeft')) {
                            safeSetHtml('measurementTargetsLeft', left.length ? left.map(render).join('') : '<li><a href="#">暂无数据</a></li>');
                        }
                        if (document.getElementById('measurementTargetsRight')) {
                            safeSetHtml('measurementTargetsRight', right.length ? right.map(render).join('') : '<li><a href="#">暂无数据</a></li>');
                        }
                    })
                    .catch(function () {
                        if (document.getElementById('measurementTargetsLeft')) safeSetHtml('measurementTargetsLeft', '<li><a href="#">加载失败</a></li>');
                        if (document.getElementById('measurementTargetsRight')) safeSetHtml('measurementTargetsRight', '');
                    })
            );
        }

        return Promise.all(jobs);
    }

    function bindBioDynamicData() {
        // 保持现状等价：生物导航仅保留交互绑定，不强行注入 admin 领域分类逻辑。
        return Promise.resolve();
    }

    function boot() {
        ensureChatbotScript();

        var root = getRoot();
        if (!root) return;
        var profile = getProfile(root);
        ensureNavStylesheet();
        ensureNoScriptFallback(root, profile);

        injectPartial(root, profile)
            .then(function () {
                bindCommonInteractions(root);
                if (profile === 'gas') return bindGasDynamicData();
                if (profile === 'bio') return bindBioDynamicData();
                return Promise.resolve();
            })
            .catch(function (err) {
                console.error('[nav-loader] failed:', err);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
