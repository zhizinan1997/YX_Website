/**
 * 新闻预览加载器
 * 自动从后端 API 获取各分类的最新新闻，并更新首页巨幕菜单中的预览
 */

(function () {
    'use strict';

    if (window.__mcNewsPreviewLoaderInitialized) {
        return;
    }
    window.__mcNewsPreviewLoaderInitialized = true;

    const NAV_READY_EVENT = 'mc-nav:ready';
    // 配置：每个分类显示的新闻数量
    const NEWS_COUNT_PER_CATEGORY = 4;
    const PANEL_WAIT_TIMEOUT_MS = 5000;
    const PANEL_WAIT_INTERVAL_MS = 120;

    // 新闻分类配置
    const CATEGORIES = {
        enterprise: {
            panelId: 'panel-news-enterprise',
            title: '最新企业新闻',
            moreLink: '/pages/news/news.html#enterprise',
            moreLinkText: '查看更多企业新闻'
        },
        industry: {
            panelId: 'panel-news-industry',
            title: '行业动态前沿',
            moreLink: '/pages/news/news.html#industry',
            moreLinkText: '查看更多行业动态'
        },
        science: {
            panelId: 'panel-news-science',
            title: '传感器科普知识',
            moreLink: '/pages/news/news.html#science',
            moreLinkText: '查看更多科普知识'
        }
    };

    let pendingLoadPromise = null;

    function hasNewsPanels() {
        return Object.keys(CATEGORIES).some(category => {
            const config = CATEGORIES[category];
            return Boolean(config && document.getElementById(config.panelId));
        });
    }

    function normalizeUrl(url, fallback = '#') {
        const value = String(url || '').trim();
        if (!value) {
            return fallback;
        }
        if (/^(?:[a-z]+:)?\/\//i.test(value) || value.startsWith('/') || value.startsWith('#')) {
            return value;
        }
        return `/${value.replace(/^\.?\//, '')}`;
    }

    function waitForNewsPanels() {
        if (hasNewsPanels()) {
            return Promise.resolve(true);
        }

        return new Promise(resolve => {
            const startedAt = Date.now();
            let intervalId = null;
            let observer = null;

            function finish(found) {
                if (intervalId) {
                    window.clearInterval(intervalId);
                }
                if (observer) {
                    observer.disconnect();
                }
                resolve(found);
            }

            function check() {
                if (hasNewsPanels()) {
                    finish(true);
                    return;
                }
                if (Date.now() - startedAt >= PANEL_WAIT_TIMEOUT_MS) {
                    finish(false);
                }
            }

            if (window.MutationObserver && document.documentElement) {
                observer = new MutationObserver(check);
                observer.observe(document.documentElement, { childList: true, subtree: true });
            }

            intervalId = window.setInterval(check, PANEL_WAIT_INTERVAL_MS);
            check();
        });
    }

    /**
     * 从后端 API 获取新闻数据
     */
    async function fetchNewsData() {
        try {
            const response = await fetch(`/api/news?count=${NEWS_COUNT_PER_CATEGORY}`);
            if (!response.ok) {
                throw new Error('Failed to fetch news data');
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching news data:', error);
            return null;
        }
    }

    /**
     * 生成单条新闻的 HTML
     */
    function createNewsItemHTML(news) {
        return `
      <a class="vs-mobile-news-link" href="${normalizeUrl(news.link)}" style="text-decoration: none; display: flex; gap: 15px; align-items: flex-start;">
        <img class="vs-mobile-news-thumb" src="${normalizeUrl(news.image, '/cdn_assets/images/common/f1dcc87cdcca.png')}" style="width: 100px; height: 60px; object-fit: cover; border-radius: 4px;" alt="news" onerror="this.src='/cdn_assets/images/common/f1dcc87cdcca.png'">
        <div class="vs-mobile-news-copy">
          <h4 class="vs-mobile-news-title" style="font-size: 14px; font-weight: 600; color: #333; margin-bottom: 5px; line-height: 1.4;">
            ${news.title}
          </h4>
          <span class="vs-mobile-news-date" style="font-size: 12px; color: #888;">${news.date}</span>
        </div>
      </a>
    `;
    }

    /**
     * 生成分类面板的完整 HTML
     */
    function createPanelHTML(config, newsItems) {
        const newsListHTML = newsItems
            .slice(0, NEWS_COUNT_PER_CATEGORY)
            .map(createNewsItemHTML)
            .join('');

        return `
      <h3 style="margin-bottom: 20px; font-size: 18px; color: #333;">${config.title}</h3>
      <div class="vs-mobile-news-list" style="display: flex; flex-direction: column; gap: 20px;">
        ${newsListHTML}
      </div>
      <div class="vs-mobile-news-more" style="margin-top: 20px; text-align: right;">
        <a class="vs-mobile-news-more-link" href="${config.moreLink}" style="color: var(--color-primary); font-size: 14px; font-weight: 500;">
          ${config.moreLinkText} &rarr;
        </a>
      </div>
    `;
    }

    /**
     * 更新巨幕菜单中的新闻预览
     */
    function updateNewsPanels(newsByCategory) {
        Object.keys(CATEGORIES).forEach(category => {
            const config = CATEGORIES[category];
            const panel = document.getElementById(config.panelId);
            const newsItems = newsByCategory[category] || [];

            if (panel && newsItems.length > 0) {
                panel.innerHTML = createPanelHTML(config, newsItems);
            }
        });
    }

    /**
     * 初始化
     */
    async function init() {
        document.addEventListener(NAV_READY_EVENT, event => {
            if (event && event.detail && event.detail.profile && event.detail.profile !== 'home') {
                return;
            }
            loadNews();
        });

        // 等待 DOM 加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', loadNews);
        } else {
            loadNews();
        }
    }

    async function loadNews() {
        if (pendingLoadPromise) {
            return pendingLoadPromise;
        }

        pendingLoadPromise = (async () => {
            const panelsReady = await waitForNewsPanels();
            if (!panelsReady) {
                console.warn('News preview panels were not found before timeout');
                return;
            }

            const newsData = await fetchNewsData();
            if (newsData) {
                updateNewsPanels(newsData);
                console.log('News preview updated successfully from API');
            }
        })();

        try {
            await pendingLoadPromise;
        } finally {
            pendingLoadPromise = null;
        }
    }

    // 启动
    init();

})();
