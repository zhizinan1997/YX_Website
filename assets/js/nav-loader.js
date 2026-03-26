(function () {
    'use strict';

    var ROOT_ID = 'mc-nav-root';
    var PROFILE_ATTR = 'data-nav-profile';
    var NAV_CSS_ID = 'mc-nav-component-css';
    var CHATBOT_SCRIPT_SRC = '/assets/js/chatbot.js';
    var NAV_ASSET_VERSION = '20260325d';

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
        link.href = '/assets/css/nav-component.css?v=' + NAV_ASSET_VERSION;
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
        return fetchText('/assets/partials/nav-' + profile + '.html?v=' + NAV_ASSET_VERSION).then(function (html) {
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

        var nav = root.querySelector('.vs-nav');
        var headerInner = root.querySelector('.vs-header__inner') || root.querySelector('.vs-container') || root;
        var mobileToggle = root.querySelector('.vs-mobile-toggle');

        function isMobileViewport() {
            return window.matchMedia('(max-width: 1024px)').matches;
        }

        function getDirectItemToggle(item) {
            if (!item || !item.children) return null;
            for (var i = 0; i < item.children.length; i++) {
                var child = item.children[i];
                if (child && child.classList && child.classList.contains('vs-nav__item-toggle')) {
                    return child;
                }
            }
            return null;
        }

        function closeMobileMegaMenus(exceptItem) {
            var megaItems = root.querySelectorAll('.vs-nav__item--has-mega');
            megaItems.forEach(function (item) {
                if (exceptItem && item === exceptItem) return;
                item.classList.remove('is-mobile-open');
                var toggleBtn = getDirectItemToggle(item);
                if (toggleBtn) {
                    toggleBtn.classList.remove('is-open');
                    toggleBtn.setAttribute('aria-expanded', 'false');
                }
            });
        }

        function setMobileToggleVisual(opened) {
            if (!mobileToggle) return;
            mobileToggle.classList.toggle('is-open', !!opened);
            mobileToggle.setAttribute('aria-expanded', opened ? 'true' : 'false');
            var icon = mobileToggle.querySelector('i');
            if (icon) {
                icon.className = opened ? 'fas fa-times' : 'fas fa-bars';
            }
        }

        function setMobileNavOpen(opened) {
            if (!mobileToggle || !nav) return;
            nav.classList.toggle('is-open', !!opened);
            setMobileToggleVisual(!!opened);
            document.body.classList.toggle('mc-nav-mobile-open', !!opened);
            if (!opened) closeMobileMegaMenus();
        }

        function ensureMobileStructure() {
            if (!nav || !headerInner) return;

            if (!mobileToggle) {
                mobileToggle = document.createElement('button');
                mobileToggle.type = 'button';
                mobileToggle.className = 'vs-mobile-toggle';
                mobileToggle.innerHTML = '<i class="fas fa-bars" aria-hidden="true"></i><span>菜单</span>';
                mobileToggle.setAttribute('aria-label', '打开导航菜单');
                var actions = root.querySelector('.mc-nav-actions');
                if (actions && actions.parentNode === headerInner) {
                    headerInner.insertBefore(mobileToggle, actions);
                } else {
                    headerInner.appendChild(mobileToggle);
                }
            }

            if (!nav.id) nav.id = 'mc-nav-menu';
            mobileToggle.setAttribute('aria-controls', nav.id);
            setMobileToggleVisual(false);

            var megaItems = root.querySelectorAll('.vs-nav__item--has-mega');
            megaItems.forEach(function (item) {
                if (getDirectItemToggle(item)) return;
                var toggleBtn = document.createElement('button');
                toggleBtn.type = 'button';
                toggleBtn.className = 'vs-nav__item-toggle';
                toggleBtn.setAttribute('aria-label', '展开子菜单');
                toggleBtn.setAttribute('aria-expanded', 'false');
                toggleBtn.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
                item.appendChild(toggleBtn);

                toggleBtn.addEventListener('click', function (event) {
                    if (!isMobileViewport()) return;
                    event.preventDefault();
                    event.stopPropagation();
                    var willOpen = !item.classList.contains('is-mobile-open');
                    closeMobileMegaMenus(item);
                    item.classList.toggle('is-mobile-open', willOpen);
                    toggleBtn.classList.toggle('is-open', willOpen);
                    toggleBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                });
            });

            mobileToggle.addEventListener('click', function (event) {
                event.preventDefault();
                var opened = !nav.classList.contains('is-open');
                setMobileNavOpen(opened);
            });

            nav.querySelectorAll('.vs-nav__item > .vs-nav__link').forEach(function (link) {
                link.addEventListener('click', function () {
                    if (!isMobileViewport()) return;
                    var parent = link.parentElement;
                    if (parent && parent.classList && parent.classList.contains('vs-nav__item--has-mega')) return;
                    setMobileNavOpen(false);
                });
            });

            document.addEventListener('click', function (event) {
                if (!isMobileViewport()) return;
                if (root.contains(event.target)) return;
                setMobileNavOpen(false);
            });

            window.addEventListener('resize', function () {
                if (isMobileViewport()) return;
                setMobileNavOpen(false);
                closeMobileMegaMenus();
            });
        }

        ensureMobileStructure();

        // Smooth mega-menu switching on fast pointer movement.
        (function bindMegaHoverBuffer() {
            var items = root.querySelectorAll('.vs-nav__item--has-mega');
            if (!items.length) return;
            var closeTimer = null;
            var closeDelay = 90;

            function resetMenuOffset(item) {
                var menu = item && item.querySelector('.vs-mega-menu');
                if (menu) menu.style.marginLeft = '';
            }

            function clampMenuToViewport(item) {
                var menu = item && item.querySelector('.vs-mega-menu');
                if (!menu) return;

                // Reset offset first, then re-measure to compute the needed shift.
                menu.style.marginLeft = '0px';

                var rect = menu.getBoundingClientRect();
                var viewportWidth = window.innerWidth || document.documentElement.clientWidth || rect.right;
                var gutter = 12;
                var shiftX = 0;

                if (rect.right > viewportWidth - gutter) {
                    shiftX -= (rect.right - (viewportWidth - gutter));
                }
                if (rect.left < gutter) {
                    shiftX += (gutter - rect.left);
                }

                menu.style.marginLeft = Math.abs(shiftX) > 0.5 ? (Math.round(shiftX) + 'px') : '0px';
            }

            function closeAll() {
                items.forEach(function (it) {
                    it.classList.remove('is-mega-open');
                    resetMenuOffset(it);
                });
            }

            items.forEach(function (item) {
                item.addEventListener('mouseenter', function () {
                    if (isMobileViewport()) return;
                    if (closeTimer) {
                        clearTimeout(closeTimer);
                        closeTimer = null;
                    }
                    closeAll();
                    item.classList.add('is-mega-open');
                    window.requestAnimationFrame(function () {
                        clampMenuToViewport(item);
                    });
                });

                item.addEventListener('mouseleave', function () {
                    if (isMobileViewport()) return;
                    if (closeTimer) clearTimeout(closeTimer);
                    closeTimer = setTimeout(function () {
                        item.classList.remove('is-mega-open');
                        resetMenuOffset(item);
                    }, closeDelay);
                });
            });

            root.addEventListener('mouseleave', function () {
                if (isMobileViewport()) return;
                if (closeTimer) clearTimeout(closeTimer);
                closeTimer = setTimeout(closeAll, closeDelay);
            });

            window.addEventListener('resize', function () {
                if (isMobileViewport()) {
                    items.forEach(function (it) { resetMenuOffset(it); });
                    return;
                }
                var opened = root.querySelector('.vs-nav__item--has-mega.is-mega-open');
                if (opened) clampMenuToViewport(opened);
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

    function escapeHtmlText(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function detectCurrentProductId() {
        var path = String(window.location.pathname || '');
        var m = path.match(/^\/pages\/gassensing\/([a-z0-9_]+)\.html$/i);
        if (m && m[1]) {
            var slug = String(m[1]).toLowerCase();
            if (slug === 'all-products' || slug === 'index') return '';
            return slug;
        }
        m = path.match(/^\/pages\/customization\/([a-z0-9_]+)\.html$/i);
        if (m && m[1]) {
            return '../customization/' + String(m[1]).toLowerCase();
        }
        return '';
    }

    function renderProductRelatedNews(items) {
        var grid = document.querySelector('.vs-related-news .vs-news-grid');
        if (!grid || !Array.isArray(items) || !items.length) return;
        var html = items.slice(0, 2).map(function (item) {
            var link = (item && item.link) ? String(item.link) : '#';
            var title = (item && item.title) ? String(item.title) : '相关新闻';
            var image = (item && item.image) ? String(item.image) : '/cdn_assets/images/common/f1dcc87cdcca.png';
            var desc = (item && item.desc) ? String(item.desc) : '';
            return '' +
                '<a href="' + link + '" class="vs-news-item">' +
                '  <img src="' + image + '" alt="新闻图片">' +
                '  <div class="vs-news-item__content">' +
                '    <h4>' + escapeHtmlText(title) + '</h4>' +
                '    <p>' + escapeHtmlText(desc) + '</p>' +
                '  </div>' +
                '</a>';
        }).join('');
        if (html) grid.innerHTML = html;
    }

    function bindProductRelatedNewsData() {
        var productId = detectCurrentProductId();
        if (!productId) return Promise.resolve();
        if (!document.querySelector('.vs-related-news .vs-news-grid')) return Promise.resolve();
        return fetch('/api/products/related-news?id=' + encodeURIComponent(productId), { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data && data.success && Array.isArray(data.items)) {
                    renderProductRelatedNews(data.items);
                }
            })
            .catch(function () { });
    }

    function shuffleArray(list) {
        var arr = Array.isArray(list) ? list.slice() : [];
        for (var i = arr.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var tmp = arr[i];
            arr[i] = arr[j];
            arr[j] = tmp;
        }
        return arr;
    }

    function normalizeProductCardTitle(product) {
        return String(
            (product && (product.cardTitle || product.displayName || product.shortName || product.name)) || '产品'
        );
    }

    function normalizeProductCardImage(product) {
        var image = String((product && (product.cardImage || product.image)) || '').trim();
        return image || '/cdn_assets/images/common/f1dcc87cdcca.png';
    }

    function renderProductRelatedProducts(items) {
        var grid = document.querySelector('.vs-related-products .vs-related-grid');
        if (!grid) return;
        if (!Array.isArray(items) || !items.length) {
            grid.innerHTML = '<p style="grid-column: 1 / -1; color: #64748b; text-align: center; margin: 24px 0;">暂无相关产品</p>';
            return;
        }

        var html = items.map(function (item) {
            var href = buildProductHref(item);
            var title = normalizeProductCardTitle(item);
            var image = normalizeProductCardImage(item);
            return '' +
                '<a href="' + href + '" class="vs-related-item">' +
                '  <img src="' + image + '" alt="' + escapeHtmlText(title) + '">' +
                '  <h4>' + escapeHtmlText(title) + '</h4>' +
                '</a>';
        }).join('');

        grid.innerHTML = html;
    }

    function bindProductRelatedProductsData() {
        var productId = detectCurrentProductId();
        if (!productId) return Promise.resolve();
        if (!document.querySelector('.vs-related-products .vs-related-grid')) return Promise.resolve();
        var isCustomizationPage = productId.indexOf('../customization/') === 0;

        return fetch('/api/products/with-settings', { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var allProducts = (data && Array.isArray(data.products)) ? data.products : [];
                var seen = Object.create(null);
                var filtered = [];

                allProducts.forEach(function (product) {
                    var id = String((product && product.id) || '');
                    if (!id || (product && product.hidden)) return;
                    if (isCustomizationPage) {
                        if (id.indexOf('../customization/') !== 0) return;
                    } else {
                        if (id.indexOf('../') === 0) return;
                    }
                    if (id === productId) return;
                    if (id === 'all-products' || id === 'index') return;
                    if (seen[id]) return;
                    seen[id] = true;
                    filtered.push(product);
                });

                var picked = shuffleArray(filtered).slice(0, 8);
                renderProductRelatedProducts(picked);
            })
            .catch(function () { });
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

        if (document.getElementById('gasIndustryLeft') || document.getElementById('gasIndustryRight')) {
            jobs.push(
                fetch('/api/nav-industry-categories', { credentials: 'same-origin' })
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
                        if (document.getElementById('gasIndustryLeft')) {
                            safeSetHtml('gasIndustryLeft', left.length ? left.map(render).join('') : '<li><a href="#">暂无数据</a></li>');
                        }
                        if (document.getElementById('gasIndustryRight')) {
                            safeSetHtml('gasIndustryRight', right.length ? right.map(render).join('') : '<li><a href="#">暂无数据</a></li>');
                        }
                    })
                    .catch(function () {
                        if (document.getElementById('gasIndustryLeft')) safeSetHtml('gasIndustryLeft', '<li><a href="#">加载失败</a></li>');
                        if (document.getElementById('gasIndustryRight')) safeSetHtml('gasIndustryRight', '');
                    })
            );
        }

        jobs.push(bindProductRelatedNewsData());
        jobs.push(bindProductRelatedProductsData());

        return Promise.all(jobs);
    }

    function bindStandaloneProductData() {
        return Promise.all([
            bindProductRelatedNewsData(),
            bindProductRelatedProductsData()
        ]);
    }

    function bindBioDynamicData() {
        // 保持现状等价：生物导航仅保留交互绑定，不强行注入 admin 领域分类逻辑。
        return Promise.resolve();
    }

    function boot() {
        ensureChatbotScript();

        var root = getRoot();
        if (!root) {
            bindStandaloneProductData();
            return;
        }
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
            })
            .finally(function () {
                bindStandaloneProductData();
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
