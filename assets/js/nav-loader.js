(function () {
    'use strict';

    var ROOT_ID = 'mc-nav-root';
    var PROFILE_ATTR = 'data-nav-profile';
    var NAV_CSS_ID = 'mc-nav-component-css';
    var NAV_READY_EVENT = 'mc-nav:ready';
    var CHATBOT_SCRIPT_SRC = '/assets/js/chatbot.js?v=20260604i';
    var NEWS_PREVIEW_SCRIPT_SRC = '/assets/js/news-preview-loader.js?v=20260626d';
    var NAV_CACHE_TAG = '20260715a';

    function getRoot() {
        return document.getElementById(ROOT_ID);
    }

    function onDomReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
            return;
        }
        callback();
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
            fallback.innerHTML = '<div>导航暂不可用</div>';
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
        link.href = withCacheTag('/assets/css/nav-component.css');
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

    function ensureNewsPreviewScript() {
        var exists = Array.prototype.some.call(document.getElementsByTagName('script'), function (s) {
            var src = s.getAttribute('src') || '';
            return src.indexOf('news-preview-loader.js') !== -1;
        });
        if (exists) return;
        var script = document.createElement('script');
        script.src = NEWS_PREVIEW_SCRIPT_SRC;
        script.defer = true;
        document.body.appendChild(script);
    }

    function injectPartial(root, profile) {
        return fetchText(withCacheTag('/assets/partials/nav-' + profile + '.html')).then(function (html) {
            root.innerHTML = html;
        });
    }

    function withCacheTag(url) {
        var value = String(url || '');
        var hashIndex = value.indexOf('#');
        var fragment = hashIndex >= 0 ? value.slice(hashIndex) : '';
        var withoutHash = hashIndex >= 0 ? value.slice(0, hashIndex) : value;
        var parts = withoutHash.split('?');
        var base = parts.shift();
        var query = parts.join('?');
        var params = [];
        if (query) {
            query.split('&').forEach(function (part) {
                if (!part) return;
                var key = part.split('=')[0];
                if (decodeURIComponent(key || '') === 'v') return;
                params.push(part);
            });
        }
        params.push('v=' + encodeURIComponent(NAV_CACHE_TAG));
        return base + '?' + params.join('&') + fragment;
    }

    function dispatchNavReady(root, profile) {
        var detail = { profile: profile, rootId: ROOT_ID };
        if (root && root.id) {
            detail.rootId = root.id;
        }

        var event;
        if (typeof window.CustomEvent === 'function') {
            event = new CustomEvent(NAV_READY_EVENT, { detail: detail });
        } else {
            event = document.createEvent('CustomEvent');
            event.initCustomEvent(NAV_READY_EVENT, false, false, detail);
        }

        document.dispatchEvent(event);
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

        function getDirectItemLink(item) {
            if (!item || !item.children) return null;
            for (var i = 0; i < item.children.length; i++) {
                var child = item.children[i];
                if (child && child.classList && child.classList.contains('vs-nav__link')) {
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
                var link = getDirectItemLink(item);
                if (link) link.setAttribute('aria-expanded', 'false');
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

        function toggleMobileMegaItem(item, toggleBtn) {
            if (!item) return;
            var button = toggleBtn || getDirectItemToggle(item);
            var link = getDirectItemLink(item);
            var willOpen = !item.classList.contains('is-mobile-open');
            closeMobileMegaMenus(item);
            item.classList.toggle('is-mobile-open', willOpen);
            if (button) {
                button.classList.toggle('is-open', willOpen);
                button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            }
            if (link) {
                link.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            }
        }

        function activateMobileMegaTab(tab) {
            if (!tab) return;
            var inlineHandler = tab.getAttribute('onmouseover') || '';
            var match = inlineHandler.match(/\b(showPanel(?:Contact|Solutions|Cases|News)?|activateLinkTab)\('([^']*)',\s*this\)/);
            if (match) {
                var fn = window[match[1]];
                if (typeof fn === 'function') {
                    if (match[1] === 'activateLinkTab') {
                        fn(tab);
                    } else {
                        fn(match[2], tab);
                    }
                    return;
                }
            }

            var sidebar = tab.closest('.vs-mega-sidebar');
            if (!sidebar) return;
            sidebar.querySelectorAll('.vs-mega-tab').forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
        }

        function shouldSwitchMobileMegaTab(tab) {
            if (!tab || !tab.classList || !tab.classList.contains('vs-mega-tab')) return false;
            var inlineHandler = tab.getAttribute('onmouseover') || '';
            if (/\bshowPanel(?:Contact|Solutions|Cases|News)?\(/.test(inlineHandler)) return true;
            var href = tab.tagName && tab.tagName.toLowerCase() === 'a'
                ? (tab.getAttribute('href') || '').trim()
                : '';
            return !href || href === '#';
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
                var itemLink = getDirectItemLink(item);
                if (itemLink) {
                    itemLink.setAttribute('aria-haspopup', 'true');
                    itemLink.setAttribute('aria-expanded', 'false');
                    itemLink.addEventListener('click', function (event) {
                        if (!isMobileViewport()) return;
                        event.preventDefault();
                        event.stopPropagation();
                        toggleMobileMegaItem(item);
                    });
                }

                if (getDirectItemToggle(item)) return;
                var toggleBtn = document.createElement('button');
                toggleBtn.type = 'button';
                toggleBtn.className = 'vs-nav__item-toggle';
                toggleBtn.setAttribute('aria-label', '\u5c55\u5f00\u5b50\u83dc\u5355');
                toggleBtn.setAttribute('aria-expanded', 'false');
                toggleBtn.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i>';
                item.appendChild(toggleBtn);

                toggleBtn.addEventListener('click', function (event) {
                    if (!isMobileViewport()) return;
                    event.preventDefault();
                    event.stopPropagation();
                    toggleMobileMegaItem(item, toggleBtn);
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

            nav.querySelectorAll('.vs-mega-menu a').forEach(function (link) {
                link.addEventListener('click', function () {
                    if (!isMobileViewport()) return;
                    if (shouldSwitchMobileMegaTab(link)) return;
                    setMobileNavOpen(false);
                });
            });

            nav.querySelectorAll('.vs-mega-tab').forEach(function (tab) {
                tab.addEventListener('click', function (event) {
                    if (!isMobileViewport()) return;
                    if (!shouldSwitchMobileMegaTab(tab)) return;
                    event.preventDefault();
                    event.stopPropagation();
                    activateMobileMegaTab(tab);
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
        var name = (item && item.name) ? String(item.name) : '\u672a\u547d\u540d\u94fe\u63a5';
        var external = /^https?:\/\//i.test(url);
        var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        return '<li><a href="' + escapeHtmlText(url) + '"' + target + '>' + escapeHtmlText(name) + '</a></li>';
    }

    function normalizeRecommendationLookupKey(url) {
        var raw = String(url || '').trim();
        if (!raw) return '';
        try {
            var resolved = new URL(raw, window.location.href);
            var currentOrigin = String(window.location.origin || '').toLowerCase();
            var origin = String(resolved.origin || '').toLowerCase();
            var pathWithQuery = String((resolved.pathname || '') + (resolved.search || '')).toLowerCase();
            return origin === currentOrigin ? pathWithQuery : (origin + pathWithQuery);
        } catch (e) {
            return raw.toLowerCase();
        }
    }

    function buildRecommendationProductMap(products) {
        var map = Object.create(null);
        if (!Array.isArray(products)) return map;
        products.forEach(function (product) {
            if (!product || product.hidden) return;
            var key = normalizeRecommendationLookupKey(buildProductHref(product));
            if (!key) return;
            map[key] = {
                image: normalizeProductCardImage(product),
                title: normalizeProductCardTitle(product)
            };
        });
        return map;
    }

    function buildRecommendationCard(item, productMap, ctaText, imageFit) {
        var url = (item && item.url) ? String(item.url).trim() : '#';
        var name = (item && item.name) ? String(item.name).trim() : '\u672a\u547d\u540d\u4ea7\u54c1';
        var external = /^https?:\/\//i.test(url);
        var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        var key = normalizeRecommendationLookupKey(url);
        var matched = key && productMap ? productMap[key] : null;
        var image = (item && item.image) ? String(item.image).trim() : '';
        var actionLabel = (ctaText && String(ctaText).trim()) ? String(ctaText).trim() : '\u4e86\u89e3\u9886\u57df';
        var isNew = !!(item && item.isNew);
        var newBadge = isNew ? '<span class="vs-recommend-badge">NEW</span>' : '';
        if (!image && matched && matched.image) image = matched.image;
        if (!image) image = '/cdn_assets/images/common/f1dcc87cdcca.png';
        var fitMode = imageFit === 'cover' ? 'cover' : 'contain';

        return '' +
            '<li class="vs-recommend-card">' +
            '  <a class="vs-recommend-link" href="' + escapeHtmlText(url) + '"' + target + '>' +
            '    <span class="vs-recommend-thumb">' +
            '      <img src="' + escapeHtmlText(image) + '" alt="' + escapeHtmlText(name) + '" style="object-fit:' + fitMode + ';">' +
            '    </span>' +
            '    <span class="vs-recommend-body">' +
            '      <span class="vs-recommend-title-row">' +
            '        <span class="vs-recommend-title">' + escapeHtmlText(name) + '</span>' +
                     newBadge +
            '      </span>' +
            '      <span class="vs-recommend-cta">' + escapeHtmlText(actionLabel) + ' <i class="fas fa-arrow-right"></i></span>' +
            '    </span>' +
            '  </a>' +
            '</li>';
    }

    function buildProductMenuCard(product) {
        return {
            name: normalizeProductCardTitle(product),
            url: buildProductHref(product),
            image: normalizeProductCardImage(product),
            isNew: !!(product && product.isNew)
        };
    }

    function buildSolutionPreviewTab(item, index, active) {
        var url = (item && item.url) ? String(item.url).trim() : '#';
        var name = (item && item.name) ? String(item.name).trim() : '\u672a\u547d\u540d\u65b9\u6848';
        var external = /^https?:\/\//i.test(url);
        var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';
        var cls = 'vs-mega-tab vs-mega-tab-link vs-solution-preview-tab' + (active ? ' active' : '');
        return '' +
            '<a class="' + cls + '" href="' + escapeHtmlText(url) + '"' + target + ' data-preview-index="' + index + '">' +
            '  <span>' + escapeHtmlText(name) + '</span>' +
            '  <i class="fas fa-chevron-right"></i>' +
            '</a>';
    }

    function buildSolutionPreviewCard(item, options) {
        var url = (item && item.url) ? String(item.url).trim() : '#';
        var name = (item && item.name) ? String(item.name).trim() : '\u89e3\u51b3\u65b9\u6848';
        var pageTitle = (item && item.title) ? String(item.title).trim() : '';
        var defaultEyebrow = (options && options.defaultEyebrow) ? String(options.defaultEyebrow) : '\u89e3\u51b3\u65b9\u6848';
        var ctaText = (options && options.ctaText) ? String(options.ctaText) : '\u8fdb\u5165\u65b9\u6848';
        var defaultDesc = (options && options.defaultDesc)
            ? String(options.defaultDesc)
            : '\u6d4f\u89c8\u8be5\u9886\u57df\u7684\u5178\u578b\u5e94\u7528\u573a\u666f\u3001\u7cfb\u7edf\u914d\u7f6e\u4e0e\u4ea7\u54c1\u7ec4\u5408\u3002';
        var eyebrow = pageTitle && pageTitle !== name ? pageTitle : defaultEyebrow;
        var desc = (item && item.desc) ? String(item.desc).trim() : defaultDesc;
        var image = (item && item.image) ? String(item.image).trim() : '/cdn_assets/images/common/f1dcc87cdcca.png';
        var external = /^https?:\/\//i.test(url);
        var target = external ? ' target="_blank" rel="noopener noreferrer"' : '';

        return '' +
            '<a class="vs-nav-preview-card" href="' + escapeHtmlText(url) + '"' + target + '>' +
            '  <span class="vs-nav-preview-media">' +
            '    <img src="' + escapeHtmlText(image) + '" alt="' + escapeHtmlText(name) + '">' +
            '  </span>' +
            '  <span class="vs-nav-preview-overlay"></span>' +
            '  <span class="vs-nav-preview-copy">' +
            '    <span class="vs-nav-preview-eyebrow">' + escapeHtmlText(eyebrow) + '</span>' +
            '    <span class="vs-nav-preview-title">' + escapeHtmlText(name) + '</span>' +
            '    <span class="vs-nav-preview-desc">' + escapeHtmlText(desc) + '</span>' +
            '    <span class="vs-nav-preview-cta">' + escapeHtmlText(ctaText) + ' <i class="fas fa-arrow-right"></i></span>' +
            '  </span>' +
            '</a>';
    }

    function renderSolutionPreviewMenu(listId, contentId, items, options) {
        var listEl = document.getElementById(listId);
        var contentEl = document.getElementById(contentId);
        if (!listEl || !contentEl) return;

        var list = Array.isArray(items) ? items.filter(function (item) {
            return item && item.name && item.url;
        }) : [];
        if (!list.length) return;

        listEl.innerHTML = list.map(function (item, index) {
            return buildSolutionPreviewTab(item, index, index === 0);
        }).join('');

        function activate(index) {
            var safeIndex = Math.max(0, Math.min(index, list.length - 1));
            Array.prototype.forEach.call(listEl.querySelectorAll('.vs-solution-preview-tab'), function (tab, tabIndex) {
                tab.classList.toggle('active', tabIndex === safeIndex);
            });
            contentEl.innerHTML = buildSolutionPreviewCard(list[safeIndex], options);
        }

        Array.prototype.forEach.call(listEl.querySelectorAll('.vs-solution-preview-tab'), function (tab) {
            var index = parseInt(tab.getAttribute('data-preview-index'), 10);
            if (!Number.isFinite(index)) index = 0;
            var activateTab = function () { activate(index); };
            tab.addEventListener('mouseenter', activateTab);
            tab.addEventListener('focus', activateTab);
        });

        activate(0);
    }

    function renderPaginatedNavCards(containerId, items, options) {
        var container = document.getElementById(containerId);
        if (!container) return;

        var list = Array.isArray(items) ? items.slice() : [];
        var pageSize = Math.max(1, parseInt(options && options.pageSize, 10) || 6);
        var ctaText = (options && options.ctaText) ? String(options.ctaText) : '\u4e86\u89e3\u9886\u57df';
        var emptyLabel = (options && options.emptyLabel) ? String(options.emptyLabel) : '\u6682\u65e0\u6570\u636e';
        var imageFit = (options && options.imageFit) ? String(options.imageFit) : 'contain';
        var page = 0;
        var pageCount = Math.max(1, Math.ceil(list.length / pageSize));

        function renderPage() {
            if (!list.length) {
                container.innerHTML =
                    '<div class="vs-nav-card-shell">' +
                    '  <p class="vs-nav-card-empty">' + escapeHtmlText(emptyLabel) + '</p>' +
                    '</div>';
                return;
            }

            if (page < 0) page = 0;
            if (page > pageCount - 1) page = pageCount - 1;

            var start = page * pageSize;
            var pageItems = list.slice(start, start + pageSize);
            var cards = pageItems.map(function (item) {
                var itemCta = (item && item.ctaText) ? String(item.ctaText) : ctaText;
                return buildRecommendationCard(item, null, itemCta, imageFit);
            }).join('');

            var pager = '';
            if (pageCount > 1) {
                pager = '' +
                    '<div class="vs-nav-card-pagination">' +
                    '  <span class="vs-nav-card-page-label">\u7b2c ' + (page + 1) + ' / ' + pageCount + ' \u9875</span>' +
                    '  <div class="vs-nav-card-page-controls">' +
                    '    <button type="button" class="vs-nav-card-page-btn" data-nav-page="prev"' + (page === 0 ? ' disabled' : '') + '>\u4e0a\u4e00\u9875</button>' +
                    '    <button type="button" class="vs-nav-card-page-btn" data-nav-page="next"' + (page >= pageCount - 1 ? ' disabled' : '') + '>\u4e0b\u4e00\u9875</button>' +
                    '  </div>' +
                    '</div>';
            }

            container.innerHTML =
                '<div class="vs-nav-card-shell">' +
                '  <div class="vs-nav-card-grid">' +
                '    <ul class="vs-mega-list-v2 vs-mega-list-v2--cards">' + cards + '</ul>' +
                '  </div>' +
                pager +
                '</div>';

            Array.prototype.forEach.call(container.querySelectorAll('[data-nav-page]'), function (button) {
                button.addEventListener('click', function () {
                    if (button.disabled) return;
                    page += button.getAttribute('data-nav-page') === 'next' ? 1 : -1;
                    renderPage();
                });
            });
        }

        renderPage();
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

    function safeNavUrl(value, fallback) {
        var raw = String(value || '').trim();
        var defaultValue = fallback || '#';
        if (!raw) return defaultValue;
        if (raw.charAt(0) === '#' || raw.charAt(0) === '/' || raw.indexOf('./') === 0 || raw.indexOf('../') === 0) {
            return raw;
        }
        try {
            var parsed = new URL(raw, window.location.origin);
            if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return raw;
        } catch (error) {
            // 无效链接回落为不可跳转占位符。
        }
        return defaultValue;
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
            var link = safeNavUrl(item && item.link, '#');
            var title = (item && item.title) ? String(item.title) : '相关新闻';
            var image = safeNavUrl(item && item.image, '/cdn_assets/images/common/f1dcc87cdcca.png');
            var desc = (item && item.desc) ? String(item.desc) : '';
            return '' +
                '<a href="' + escapeHtmlText(link) + '" class="vs-news-item">' +
                '  <img src="' + escapeHtmlText(image) + '" alt="新闻图片">' +
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
            var href = safeNavUrl(buildProductHref(item), '#');
            var title = normalizeProductCardTitle(item);
            var image = safeNavUrl(normalizeProductCardImage(item), '/cdn_assets/images/common/f1dcc87cdcca.png');
            return '' +
                '<a href="' + escapeHtmlText(href) + '" class="vs-related-item">' +
                '  <img src="' + escapeHtmlText(image) + '" alt="' + escapeHtmlText(title) + '">' +
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
        var productsForNavPromise = null;

        if (document.getElementById('dynamic-product-list')) {
            productsForNavPromise = fetch('/api/products/with-settings', { credentials: 'same-origin' })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    return (data && Array.isArray(data.products)) ? data.products : [];
                });

            jobs.push(
                productsForNavPromise
                    .then(function (allProducts) {
                        var products = allProducts.filter(function (p) { return !p.hidden; });
                        renderPaginatedNavCards(
                            'dynamic-product-list',
                            products.map(buildProductMenuCard),
                            {
                                pageSize: 4,
                                ctaText: '\u67e5\u770b\u4ea7\u54c1',
                                emptyLabel: '\u6682\u65e0\u4ea7\u54c1'
                            }
                        );
                    })
                    .catch(function () {
                        safeSetHtml('dynamic-product-list', '<p class="vs-nav-card-empty">\u52a0\u8f7d\u5931\u8d25</p>');
                    })
            );
        }

        if (document.getElementById('latestReleasesList') || document.getElementById('applicationAreasList')) {
            var recommendationProductMapPromise = Promise.resolve(Object.create(null));
            if (document.getElementById('latestReleasesList')) {
                if (productsForNavPromise) {
                    recommendationProductMapPromise = productsForNavPromise
                        .then(function (allProducts) { return buildRecommendationProductMap(allProducts); })
                        .catch(function () { return Object.create(null); });
                } else {
                    recommendationProductMapPromise = fetch('/api/products/with-settings', { credentials: 'same-origin' })
                        .then(function (res) { return res.json(); })
                        .then(function (data) { return buildRecommendationProductMap(data.products || []); })
                        .catch(function () { return Object.create(null); });
                }
            }

            jobs.push(
                Promise.all([
                    fetch('/api/recommendations', { credentials: 'same-origin' })
                        .then(function (res) { return res.json(); }),
                    recommendationProductMapPromise
                ])
                    .then(function (results) {
                        var data = results[0] || {};
                        var recommendationProductMap = results[1] || Object.create(null);

                        var latestListEl = document.getElementById('latestReleasesList');
                        if (latestListEl) {
                            latestListEl.classList.add('vs-mega-list-v2--cards');
                            var latestItems = Array.isArray(data.latestReleases) ? data.latestReleases : [];
                            safeSetHtml('latestReleasesList', latestItems.map(function (item) {
                                return buildRecommendationCard(item, recommendationProductMap, '\u67e5\u770b\u65b0\u54c1');
                            }).join('') || '<li><a href="#">暂无数据</a></li>');
                        }

                        var appListEl = document.getElementById('applicationAreasList');
                        if (appListEl) {
                            appListEl.classList.remove('vs-mega-list-v2--cards');
                            safeSetHtml('applicationAreasList', (data.applicationAreas || []).map(buildRecommendationLink).join('') || '<li><a href="#">暂无数据</a></li>');
                        }
                    })
                    .catch(function () {
                        var latestListEl = document.getElementById('latestReleasesList');
                        if (latestListEl) {
                            latestListEl.classList.add('vs-mega-list-v2--cards');
                            safeSetHtml('latestReleasesList', '<li><a href="#">加载失败</a></li>');
                        }
                        if (document.getElementById('applicationAreasList')) safeSetHtml('applicationAreasList', '<li><a href="#">加载失败</a></li>');
                    })
            );
        }
        if (document.getElementById('solutionPreviewLinks') && document.getElementById('solutionPreviewContent')) {
            jobs.push(
                fetch('/api/nav-solution-previews', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        if (items.length) {
                            renderSolutionPreviewMenu('solutionPreviewLinks', 'solutionPreviewContent', items);
                        }
                    })
                    .catch(function () { })
            );
        }
        if (document.getElementById('researchPreviewLinks') && document.getElementById('researchPreviewContent')) {
            jobs.push(
                fetch('/api/nav-research-previews', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        if (items.length) {
                            renderSolutionPreviewMenu('researchPreviewLinks', 'researchPreviewContent', items, {
                                defaultEyebrow: '\u79d1\u7814\u670d\u52a1',
                                ctaText: '\u67e5\u770b\u670d\u52a1',
                                defaultDesc: '\u4e86\u89e3\u8be5\u670d\u52a1\u677f\u5757\u7684\u80fd\u529b\u8303\u56f4\u3001\u5178\u578b\u573a\u666f\u4e0e\u5408\u4f5c\u65b9\u5f0f\u3002'
                            });
                        }
                    })
                    .catch(function () { })
            );
        }
        if (document.getElementById('featuredCasesList')) {
            jobs.push(
                fetch('/api/nav-featured-cases', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        var listEl = document.getElementById('featuredCasesList');
                        if (!listEl) return;
                        listEl.classList.add('vs-mega-list-v2--cards');
                        safeSetHtml('featuredCasesList', items.map(function (item) {
                            return buildRecommendationCard(item, null, '\u67e5\u770b\u6848\u4f8b');
                        }).join('') || '<li><a href="#">\u6682\u65e0\u6570\u636e</a></li>');
                    })
                    .catch(function () {
                        safeSetHtml('featuredCasesList', '<li><a href="#">\u52a0\u8f7d\u5931\u8d25</a></li>');
                    })
            );
        }
        if (document.getElementById('categoriesList')) {
            jobs.push(
                fetch('/api/products/industry-filters', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var categories = Array.isArray(data.categories) ? data.categories : [];
                        var items = categories.map(function (category) {
                            return {
                                name: String((category && category.name) || '').trim(),
                                url: String((category && category.url) || ('/pages/gassensing/all-products.html?filter=' + encodeURIComponent((category && category.key) || ''))).trim(),
                                image: String((category && category.image) || '').trim()
                            };
                        }).filter(function (item) {
                            return item.name && item.url;
                        });

                        renderPaginatedNavCards(
                            'categoriesList',
                            items,
                            {
                                pageSize: 4,
                                ctaText: '\u67e5\u770b\u5206\u7c7b',
                                emptyLabel: '\u6682\u65e0\u6570\u636e'
                            }
                        );
                    })
                    .catch(function () {
                        safeSetHtml('categoriesList', '<p class="vs-nav-card-empty">\u52a0\u8f7d\u5931\u8d25</p>');
                    })
            );
        }

        if (document.getElementById('measurementTargetsList')) {
            jobs.push(
                fetch('/api/measurement-targets', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        renderPaginatedNavCards(
                            'measurementTargetsList',
                            items,
                            {
                                pageSize: 4,
                                ctaText: '\u66f4\u591a\u8be6\u60c5',
                                emptyLabel: '\u6682\u65e0\u6570\u636e',
                                imageFit: 'cover'
                            }
                        );
                    })
                    .catch(function () {
                        safeSetHtml('measurementTargetsList', '<p class="vs-nav-card-empty">\u52a0\u8f7d\u5931\u8d25</p>');
                    })
            );
        }

        if (document.getElementById('gasIndustryList')) {
            jobs.push(
                fetch('/api/nav-industry-categories', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        var listEl = document.getElementById('gasIndustryList');
                        var paginationEl = document.getElementById('gasIndustryPagination');
                        var pageLabel = document.getElementById('gasIndustryPageLabel');
                        var prevBtn = document.getElementById('gasIndustryPrev');
                        var nextBtn = document.getElementById('gasIndustryNext');

                        var pageSize = 4;
                        var currentPage = 1;
                        var totalPages = Math.ceil(items.length / pageSize) || 1;

                        listEl.classList.add('vs-mega-list-v2--cards');

                        function renderIndustryPage(page) {
                            var start = (page - 1) * pageSize;
                            var end = start + pageSize;
                            var pageItems = items.slice(start, end);

                            if (pageItems.length === 0) {
                                safeSetHtml('gasIndustryList', '<li><a href="#">\u6682\u65e0\u6570\u636e</a></li>');
                            } else {
                                safeSetHtml('gasIndustryList', pageItems.map(function(item) {
                                    return buildRecommendationCard(item, null, null, 'cover');
                                }).join(''));
                            }

                            pageLabel.textContent = '\u7b2c ' + page + ' / ' + totalPages + ' \u9875';
                            prevBtn.disabled = page <= 1;
                            nextBtn.disabled = page >= totalPages;
                            paginationEl.style.display = totalPages > 1 ? 'flex' : 'none';
                        }

                        prevBtn.addEventListener('click', function() {
                            if (currentPage > 1) {
                                currentPage--;
                                renderIndustryPage(currentPage);
                            }
                        });

                        nextBtn.addEventListener('click', function() {
                            if (currentPage < totalPages) {
                                currentPage++;
                                renderIndustryPage(currentPage);
                            }
                        });

                        renderIndustryPage(1);
                    })
                    .catch(function () {
                        safeSetHtml('gasIndustryList', '<li><a href="#">\u52a0\u8f7d\u5931\u8d25</a></li>');
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
        var jobs = [];

        if (document.getElementById('researchPreviewLinks') && document.getElementById('researchPreviewContent')) {
            jobs.push(
                fetch('/api/nav-research-previews', { credentials: 'same-origin' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        var items = Array.isArray(data.items) ? data.items : [];
                        if (items.length) {
                            renderSolutionPreviewMenu('researchPreviewLinks', 'researchPreviewContent', items, {
                                defaultEyebrow: '\u79d1\u7814\u670d\u52a1',
                                ctaText: '\u67e5\u770b\u670d\u52a1',
                                defaultDesc: '\u4e86\u89e3\u8be5\u670d\u52a1\u677f\u5757\u7684\u80fd\u529b\u8303\u56f4\u3001\u5178\u578b\u573a\u666f\u4e0e\u5408\u4f5c\u65b9\u5f0f\u3002'
                            });
                        }
                    })
                    .catch(function () { })
            );
        }

        return Promise.all(jobs);
    }

    function boot() {
        ensureChatbotScript();

        var root = getRoot();
        if (!root) {
            onDomReady(bindStandaloneProductData);
            return;
        }
        var profile = getProfile(root);
        ensureNavStylesheet();
        ensureNoScriptFallback(root, profile);

        injectPartial(root, profile)
            .then(function () {
                if (profile === 'home') ensureNewsPreviewScript();
                bindCommonInteractions(root);
                dispatchNavReady(root, profile);
                if (profile === 'gas') return bindGasDynamicData();
                if (profile === 'bio') return bindBioDynamicData();
                return Promise.resolve();
            })
            .catch(function (err) {
                console.error('[nav-loader] failed:', err);
            })
            .finally(function () {
                onDomReady(bindStandaloneProductData);
            });
    }

    if (getRoot()) {
        boot();
    } else {
        onDomReady(boot);
    }
})();
