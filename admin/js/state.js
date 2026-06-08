(function () {
    const viewTitles = {
        'site-reports': '网站数据',
        'messages': '留言系统',
        'home': '首页设置',
        'h2-home': '氢气首页设置',
        'products': '气体产品',
        'bio-products': '生物产品',
        'hydrogen-solutions': '行业方案',
        'news-create': '添加资讯',
        'jobs': '招聘信息',
        'chatbot': 'AI 与知识库',
        'site-settings': '站点设置',
        'settings': '账号设置',
        'backup': '备份恢复',
        'cdn-assets': 'CDN 素材',
        'log-records': '系统日志'
    };

    const shellSections = [
        { label: '总览', items: [{ type: 'view', key: 'site-reports' }, { type: 'view', key: 'messages' }] },
        { label: '内容运营', items: [{ type: 'view', key: 'home' }, { type: 'view', key: 'news-create' }, { type: 'view', key: 'jobs' }, { type: 'view', key: 'site-settings' }] },
        { label: '产品与方案', items: [{ type: 'group', key: 'gas-related' }, { type: 'group', key: 'bio-related' }] },
        { label: 'AI 与知识库', items: [{ type: 'view', key: 'chatbot' }] },
        { label: '系统', items: [{ type: 'view', key: 'settings' }, { type: 'view', key: 'cdn-assets' }, { type: 'view', key: 'log-records' }, { type: 'selector', key: '#sidebarLogoutItem' }] }
    ];

    window.Admin2State = {
        defaultView: 'site-reports',
        titleSuffix: '管理后台',
        viewTitles,
        shellSections,
    };
})();
