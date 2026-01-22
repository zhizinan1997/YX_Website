/**
 * 新闻预览加载器
 * 自动从后端 API 获取各分类的最新新闻，并更新首页巨幕菜单中的预览
 */

(function () {
    'use strict';

    // 配置：每个分类显示的新闻数量
    const NEWS_COUNT_PER_CATEGORY = 2;

    // 新闻分类配置
    const CATEGORIES = {
        enterprise: {
            panelId: 'panel-news-enterprise',
            title: '最新企业新闻',
            moreLink: 'pages/news/news.html#enterprise',
            moreLinkText: '查看更多企业新闻'
        },
        industry: {
            panelId: 'panel-news-industry',
            title: '行业动态前沿',
            moreLink: 'pages/news/news.html#industry',
            moreLinkText: '查看更多行业动态'
        },
        science: {
            panelId: 'panel-news-science',
            title: '传感器科普知识',
            moreLink: 'pages/news/news.html#science',
            moreLinkText: '查看更多科普知识'
        }
    };

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
      <a href="${news.link}" style="text-decoration: none; display: flex; gap: 15px; align-items: flex-start;">
        <img src="${news.image}" style="width: 100px; height: 60px; object-fit: cover; border-radius: 4px;" alt="news" onerror="this.src='assets/images/logo.png'">
        <div>
          <h4 style="font-size: 14px; font-weight: 600; color: #333; margin-bottom: 5px; line-height: 1.4;">
            ${news.title}
          </h4>
          <span style="font-size: 12px; color: #888;">${news.date}</span>
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
      <div style="display: flex; flex-direction: column; gap: 20px;">
        ${newsListHTML}
      </div>
      <div style="margin-top: 20px; text-align: right;">
        <a href="${config.moreLink}" style="color: var(--color-primary); font-size: 14px; font-weight: 500;">
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
        // 等待 DOM 加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', loadNews);
        } else {
            loadNews();
        }
    }

    async function loadNews() {
        const newsData = await fetchNewsData();
        if (newsData) {
            updateNewsPanels(newsData);
            console.log('News preview updated successfully from API');
        }
    }

    // 启动
    init();

})();
