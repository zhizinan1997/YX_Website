(function () {
    const viewTitles = {
        'site-reports': '网站数据',
        'image-seo': '图片 SEO',
        'promotion-links': '推广链接',
        'messages': '留言系统',
        'home': '首页设置',
        'h2-home': '氢气首页设置',
        'products': '气体产品',
        'bio-products': '生物产品',
        'hydrogen-solutions': '行业方案',
        'news-create': '添加资讯',
        'jobs': '招聘信息',
        'chatbot': 'AI 与知识库',
        'chatbot-knowledge': '知识库管理',
        'chatbot-history': '历史对话',
        'site-settings': '站点设置',
        'settings': '账号设置',
        'backup': '备份恢复',
        'cdn-assets': 'CDN 素材',
        'log-records': '系统日志'
    };

    const shellSections = [
        { key: 'overview', label: '总览', items: [{ type: 'view', key: 'site-reports' }, { type: 'view', key: 'messages' }] },
        { key: 'content', label: '内容运营', items: [{ type: 'view', key: 'home' }, { type: 'view', key: 'image-seo' }, { type: 'view', key: 'promotion-links' }, { type: 'view', key: 'news-create' }, { type: 'view', key: 'jobs' }] },
        { key: 'products', label: '产品与方案', items: [{ type: 'group', key: 'gas-related' }, { type: 'group', key: 'bio-related' }] },
        { key: 'ai', label: 'AI 管理', items: [{ type: 'view', key: 'chatbot' }, { type: 'view', key: 'chatbot-knowledge' }, { type: 'view', key: 'chatbot-history' }] },
        { key: 'system', label: '系统', items: [{ type: 'view', key: 'settings' }, { type: 'view', key: 'log-records' }, { type: 'view', key: 'site-settings' }, { type: 'selector', key: '#sidebarLogoutItem' }] }
    ];

    window.Admin2State = {
        defaultView: 'site-reports',
        titleSuffix: '管理后台',
        viewTitles,
        shellSections,
    };
})();
