/**
 * Site-wide Search Functionality
 */

(function () {
  'use strict';

  const SEARCH_CONFIG = {
    apiUrl: '/api/search',
    debounceDelay: 300,
    minQueryLength: 2,
    maxResults: 20
  };

  const POPULAR_KEYWORDS = [
    '\u6c22\u6c14\u4f20\u611f\u5668',
    '\u751f\u7269\u4f20\u611f\u5668',
    '\u6c14\u4f53\u68c0\u6d4b',
    '\u8f66\u8f7d\u6c22\u6c14',
    '\u73af\u5883\u76d1\u6d4b',
    '\u50a8\u80fd\u5b89\u5168'
  ];

  let searchModal = null;
  let searchInput = null;
  let searchWrapper = null;
  let searchResults = null;
  let searchBody = null;
  let searchClear = null;
  let searchOverlay = null;
  let debounceTimer = null;

  function init() {
    createSearchModal();
    bindEvents();
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeRegExp(text) {
    return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function highlightText(text, query) {
    const safe = escapeHtml(text);
    if (!query) return safe;
    const pattern = new RegExp('(' + escapeRegExp(query) + ')', 'gi');
    return safe.replace(pattern, '<mark>$1</mark>');
  }

  function getResultMeta(item) {
    const url = String((item && item.url) || '').toLowerCase();

    if (url.indexOf('/pages/gassensing/cases/') !== -1) {
      return { label: '\u670d\u52a1\u6848\u4f8b', icon: 'fa-diagram-project', tone: 'case' };
    }
    if (url.indexOf('/pages/solutions/') !== -1) {
      return { label: '\u89e3\u51b3\u65b9\u6848', icon: 'fa-layer-group', tone: 'solution' };
    }
    if (url.indexOf('/pages/research/') !== -1) {
      return { label: '\u79d1\u7814\u670d\u52a1', icon: 'fa-flask', tone: 'research' };
    }
    if (
      url.indexOf('/pages/gassensing/') !== -1 ||
      url.indexOf('/pages/customization/') !== -1 ||
      url.indexOf('/pages/biosensing/') !== -1
    ) {
      return { label: '\u4ea7\u54c1\u9875\u9762', icon: 'fa-microchip', tone: 'product' };
    }
    if (url.indexOf('/pages/news/') !== -1) {
      return { label: '\u65b0\u95fb\u8d44\u8baf', icon: 'fa-newspaper', tone: 'news' };
    }
    if (url.indexOf('/pages/contact/') !== -1) {
      return { label: '\u8054\u7cfb\u6211\u4eec', icon: 'fa-envelope-open-text', tone: 'contact' };
    }

    return { label: '\u7ad9\u5185\u9875\u9762', icon: 'fa-file-lines', tone: 'page' };
  }

  function formatResultPath(url) {
    try {
      const parsed = new URL(String(url || ''), window.location.origin);
      const path = String(parsed.pathname || '')
        .replace(/^\/+/, '')
        .replace(/\.html$/i, '');

      if (!path) return '/';

      const segments = path.split('/').filter(Boolean);
      if (!segments.length) return '/';
      if (segments.length <= 3) return '/' + segments.join(' / ');
      return '/' + segments.slice(segments.length - 3).join(' / ');
    } catch (err) {
      return String(url || '');
    }
  }

  function createSearchModal() {
    searchOverlay = document.createElement('div');
    searchOverlay.className = 'vs-search-overlay';
    document.body.appendChild(searchOverlay);

    searchModal = document.createElement('div');
    searchModal.className = 'vs-search-modal';

    const html = `
      <div class="vs-search-wrapper">
        <div class="vs-search-hero">
          <div class="vs-search-hero-copy">
            <span class="vs-search-badge">\u5168\u7ad9\u641c\u7d22</span>
            <h2 class="vs-search-hero-title">\u5feb\u901f\u627e\u5230\u4ea7\u54c1\u3001\u65b9\u6848\u4e0e\u6848\u4f8b</h2>
            <p class="vs-search-hero-desc">\u8f93\u5165\u5173\u952e\u8bcd\uff0c\u53ef\u4ece\u4ea7\u54c1\u3001\u89e3\u51b3\u65b9\u6848\u3001\u79d1\u7814\u670d\u52a1\u548c\u670d\u52a1\u6848\u4f8b\u4e2d\u5feb\u901f\u5b9a\u4f4d\u76ee\u6807\u5185\u5bb9\u3002</p>
          </div>
          <div class="vs-search-shortcut-pill" aria-hidden="true">
            <kbd>Ctrl</kbd>
            <span>+</span>
            <kbd>K</kbd>
          </div>
        </div>

        <div class="vs-search-header">
          <div class="vs-search-input-shell">
            <i class="fas fa-search vs-search-icon"></i>
            <input type="text" class="vs-search-input" placeholder="\u641c\u7d22\u4ea7\u54c1\u3001\u89e3\u51b3\u65b9\u6848\u3001\u79d1\u7814\u670d\u52a1..." autocomplete="off" />
            <button class="vs-search-clear" aria-label="\u6e05\u9664"><i class="fas fa-times"></i></button>
          </div>
          <button class="vs-search-close-btn">\u5173\u95ed</button>
        </div>

        <div class="vs-search-body">
          <div class="vs-search-results"></div>
        </div>

        <div class="vs-search-footer">
          <div class="vs-search-footer-brand">
            <span class="vs-search-footer-dot"></span>
            <span>Metachip Search</span>
          </div>
          <div class="vs-shortcuts">
            <div class="vs-key-group"><kbd>\u2191</kbd><kbd>\u2193</kbd><span>\u5207\u6362</span></div>
            <div class="vs-key-group"><kbd>Enter</kbd><span>\u6253\u5f00</span></div>
            <div class="vs-key-group"><kbd>Esc</kbd><span>\u5173\u95ed</span></div>
          </div>
        </div>
      </div>
    `;

    searchModal.innerHTML = html;
    document.body.appendChild(searchModal);

    searchWrapper = searchModal.querySelector('.vs-search-wrapper');
    searchInput = searchModal.querySelector('.vs-search-input');
    searchBody = searchModal.querySelector('.vs-search-body');
    searchResults = searchModal.querySelector('.vs-search-results');
    searchClear = searchModal.querySelector('.vs-search-clear');

    showHints();
  }

  function bindEvents() {
    document.addEventListener('click', function (e) {
      const trigger = e.target.closest('.vs-search-trigger, [href="#"][class*="fa-search"]');
      if (trigger) {
        e.preventDefault();
        openSearch();
      }
    });

    const closeBtn = searchModal.querySelector('.vs-search-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', closeSearch);

    searchOverlay.addEventListener('click', closeSearch);

    searchClear.addEventListener('click', function () {
      searchInput.value = '';
      searchClear.classList.remove('visible');
      showHints();
      searchInput.focus();
    });

    searchInput.addEventListener('input', function () {
      const query = this.value.trim();

      searchClear.classList.toggle('visible', query.length > 0);
      clearTimeout(debounceTimer);

      if (query.length === 0) {
        showHints();
        return;
      }

      debounceTimer = setTimeout(function () {
        if (query.length >= SEARCH_CONFIG.minQueryLength) {
          performSearch(query);
        }
      }, SEARCH_CONFIG.debounceDelay);
    });

    searchInput.addEventListener('keydown', handleKeyNavigation);

    searchResults.addEventListener('click', function (e) {
      const item = e.target.closest('.vs-search-result-item');
      if (item) {
        setTimeout(closeSearch, 100);
      }

      const tag = e.target.closest('.vs-tag-btn');
      if (tag) {
        const keyword = tag.dataset.keyword;
        searchInput.value = keyword;
        searchClear.classList.add('visible');
        performSearch(keyword);
      }
    });

    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchModal.classList.contains('active') ? closeSearch() : openSearch();
      }
      if (e.key === 'Escape' && searchModal.classList.contains('active')) {
        closeSearch();
      }
    });
  }

  function openSearch() {
    searchOverlay.classList.add('active');
    searchModal.classList.add('active');
    document.body.style.overflow = 'hidden';
    searchInput.value = '';
    searchClear.classList.remove('visible');
    showHints();
    setTimeout(function () {
      searchInput.focus();
    }, 100);
  }

  function closeSearch() {
    searchOverlay.classList.remove('active');
    searchModal.classList.remove('active');
    document.body.style.overflow = '';
    setTimeout(function () {
      if (!searchModal.classList.contains('active')) {
        searchInput.value = '';
        searchClear.classList.remove('visible');
        showHints();
      }
    }, 300);
  }

  function showHints() {
    searchResults.innerHTML = `
      <div class="vs-search-intro">
        <div class="vs-search-intro-head">
          <span class="vs-search-intro-kicker">\u5feb\u901f\u5165\u53e3</span>
          <div class="vs-state-title">\u8bd5\u8bd5\u8fd9\u4e9b\u70ed\u95e8\u5173\u952e\u8bcd</div>
          <div class="vs-state-desc">\u70b9\u51fb\u5173\u952e\u8bcd\u5373\u53ef\u5feb\u901f\u641c\u7d22\u7ad9\u5185\u5185\u5bb9</div>
        </div>
        <div class="vs-tags-cloud">
          ${POPULAR_KEYWORDS.map(function (keyword) {
            return '<button class="vs-tag-btn" data-keyword="' + escapeHtml(keyword) + '">' + escapeHtml(keyword) + '</button>';
          }).join('')}
        </div>
        <div class="vs-search-feature-grid">
          <div class="vs-search-feature-card">
            <span class="vs-search-feature-label">\u4ea7\u54c1</span>
            <strong>\u6c14\u4f53\u4f20\u611f\u3001\u68c0\u6d4b\u4eea\u3001\u62a5\u8b66\u5668</strong>
          </div>
          <div class="vs-search-feature-card">
            <span class="vs-search-feature-label">\u89e3\u51b3\u65b9\u6848</span>
            <strong>\u6c22\u80fd\u3001\u50a8\u80fd\u3001\u5de5\u4e1a\u76d1\u6d4b\u4e0e\u73af\u5883\u5b89\u5168</strong>
          </div>
          <div class="vs-search-feature-card">
            <span class="vs-search-feature-label">\u670d\u52a1</span>
            <strong>\u79d1\u7814\u670d\u52a1\u3001\u6848\u4f8b\u5e94\u7528\u548c\u7ad9\u5185\u8d44\u8baf</strong>
          </div>
        </div>
      </div>
    `;
  }

  function performSearch(query) {
    searchResults.innerHTML = `
      <div class="vs-state-container">
        <div class="spinner"></div>
        <div class="vs-state-title">\u6b63\u5728\u641c\u7d22</div>
        <div class="vs-state-desc">\u6b63\u5728\u4e3a\u4f60\u6574\u7406\u5339\u914d\u5185\u5bb9</div>
      </div>
    `;

    fetch(SEARCH_CONFIG.apiUrl + '?q=' + encodeURIComponent(query) + '&limit=' + SEARCH_CONFIG.maxResults)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        renderResults(data.results, query);
      })
      .catch(function () {
        searchResults.innerHTML = `
          <div class="vs-state-container">
            <div class="vs-state-icon"><i class="fas fa-exclamation-triangle"></i></div>
            <div class="vs-state-title">\u641c\u7d22\u670d\u52a1\u6682\u65f6\u4e0d\u53ef\u7528</div>
            <div class="vs-state-desc">\u8bf7\u68c0\u67e5\u7f51\u7edc\u8fde\u63a5\uff0c\u6216\u7a0d\u540e\u518d\u8bd5</div>
          </div>
        `;
      });
  }

  function renderResults(results, query) {
    if (!results || results.length === 0) {
      searchResults.innerHTML = `
        <div class="vs-state-container">
          <div class="vs-state-icon"><i class="fas fa-search"></i></div>
          <div class="vs-state-title">\u672a\u627e\u5230\u76f8\u5173\u7ed3\u679c</div>
          <div class="vs-state-desc">\u53ef\u4ee5\u5c1d\u8bd5\u66f4\u6362\u5173\u952e\u8bcd\uff0c\u6216\u7f29\u77ed\u641c\u7d22\u8bcd</div>
        </div>
      `;
      return;
    }

    let html = '' +
      '<div class="vs-search-group-title">' +
      '  <span>\u627e\u5230 ' + results.length + ' \u4e2a\u7ed3\u679c</span>' +
      '  <span class="vs-search-result-count">\u53ef\u7528\u65b9\u5411\u952e\u5207\u6362</span>' +
      '</div>';

    html += results.map(function (item, idx) {
      const meta = getResultMeta(item);
      return '' +
        '<a href="' + escapeHtml(item.url) + '" class="vs-search-result-item" data-index="' + idx + '">' +
        '  <div class="g-icon g-icon--' + meta.tone + '">' +
        '    <i class="fas ' + meta.icon + '"></i>' +
        '  </div>' +
        '  <div class="g-content">' +
        '    <div class="g-title">' + highlightText(item.title, query) + '</div>' +
        '    <div class="g-snippet">' + highlightText(item.snippet, query) + '</div>' +
        '    <div class="g-meta">' +
        '      <span class="g-tag g-tag--' + meta.tone + '">' + escapeHtml(meta.label) + '</span>' +
        '      <span class="g-path">' + escapeHtml(formatResultPath(item.url)) + '</span>' +
        '    </div>' +
        '  </div>' +
        '  <div class="g-arrow"><i class="fas fa-arrow-up-right-from-square"></i></div>' +
        '</a>';
    }).join('');

    searchResults.innerHTML = html;
  }

  function handleKeyNavigation(e) {
    const items = searchResults.querySelectorAll('.vs-search-result-item');
    if (items.length === 0) return;

    let current = -1;
    items.forEach(function (el, idx) {
      if (el.classList.contains('focused')) current = idx;
    });

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      updateFocus(items, current < items.length - 1 ? current + 1 : 0);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      updateFocus(items, current > 0 ? current - 1 : items.length - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (current >= 0) {
        items[current].click();
      } else {
        items[0].click();
      }
    }
  }

  function updateFocus(items, index) {
    items.forEach(function (el) {
      el.classList.remove('focused');
    });

    const target = items[index];
    if (!target) return;
    target.classList.add('focused');
    target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.VsSearch = { open: openSearch, close: closeSearch };
})();
