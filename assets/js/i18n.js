(function () {
    const translations = {
        "en": {
            // Top Nav
            "产品": "Products",
            "解决方案": "Solutions",
            "服务案例": "Case Studies",
            "公司简介": "About Us",
            "线上店铺": "Shop",
            "联系我们": "Contact",

            // Mega Menu - Products
            "新品推荐": "New Arrivals",
            "行业分类": "Industries",
            "测量对象": "Parameters",
            "产品种类": "Categories",
            "产品列表": "All Products",

            // Mega Menu - Sections
            "最新发布": "Latest Releases",
            "应用领域": "Applications",
            "搜索产品": "Search Products",
            "查看所有产品": "View All Products",

            // Mega Menu - Industries
            "氢能源产业链": "H2 Energy Chain",
            "智慧电力安全": "Power Safety",
            "工业检漏监测": "Leak Detection",
            "绿色能源存储": "Green Energy Storage",
            "大气环境监测": "Environment Monitor",

            // Mega Menu - Parameters
            "氢气": "Hydrogen",
            "湿度": "Humidity",
            "溶解氢": "Dissolved H2",
            "油中水含量": "Oil Moisture",
            "露点": "Dew Point",
            "压力": "Pressure",

            // Mega Menu - Solutions
            "行业解决方案": "Industry Solutions",
            "科研服务": "Research Service",
            "科研服务首页": "Service Home",
            "传感器微纳加工": "Micro-Nano Fab",
            "传感器开发、测试与应用": "Sensor R&D",
            "产学研深度合作": "Cooperation",

            // Mega Menu - Cases
            "精选案例": "Featured Cases",
            "所有案例": "All Cases",
            "更多案例": "More Cases",
            "查看全部案例": "View All",
            "氢能重卡氢气检测": "H2 Truck Detection",
            "氢能源列车检测": "H2 Train Detection",
            "输氢管道人员安全": "Pipeline Safety",
            "科研实验室配气": "Lab Gas Mixing",
            "柴油机真空检漏": "Diesel Leak Detect",

            // Mega Menu - Contact
            "加入我们": "Join Us",
            "联系方式": "Contact Info",
            "合作招募": "Partnership",
            "成长空间": "Growth",
            "人才理念": "Talent Culture",
            "在线招聘": "Careers",
            "在线留言": "Feedback",

            // Search
            "搜索 (Ctrl+K)": "Search (Ctrl+K)"
        }
    };

    let currentLang = localStorage.getItem('site_lang') || 'cn';

    function setLanguage(lang) {
        currentLang = lang;
        localStorage.setItem('site_lang', lang);

        // Update Toggle Text
        const toggleBtn = document.getElementById('language-toggle');
        if (toggleBtn) {
            // Highlight current lang if needed, or just keep "CN / EN"
            // toggleBtn.innerHTML = lang === 'en' ? '<b>EN</b> / CN' : 'EN / <b>CN</b>';
        }

        // Apply translations
        const dict = translations[lang];
        if (!dict && lang !== 'cn') return; // fallback to CN (default HTML)

        // If switching back to CN, we might need a reload OR we need a "cn" dictionary.
        // Since HTML is already CN, reload is easiest. But let's try to map back if possible.
        // Actually, simplest is: if 'en', replace. If 'cn', reload or replace back?
        // To replace back, we need a reverse dictionary or reliable selectors.
        // Text Content Replacement is destructive (loses original).
        // A better way: store original text in data attribute on first run.

        const elements = document.querySelectorAll('a, h3, span, div, p, i'); // Broad selection

        elements.forEach(el => {
            // Skip script tags, style tags, etc (already filtered by selector)
            // Skip children loop (process only leaf nodes or simple text nodes ideally)
            if (el.children.length > 0 && el.tagName !== 'A') { // Allow <a> with <i> children but be careful
                // Check immediate text nodes?
            }

            // Simple approach: Match exact text content (trimmed)
            const text = el.textContent.trim();
            if (!text) return;

            // Store original if not stored
            if (!el.getAttribute('data-original-text')) {
                el.setAttribute('data-original-text', text);
            }

            const original = el.getAttribute('data-original-text');

            if (lang === 'en') {
                if (translations['en'][original]) {
                    // Special case for text nodes to preserve icons?  
                    // If element has children (like <i>), setting textContent wipes them.
                    // We should iterate childNodes.

                    let replaced = false;
                    el.childNodes.forEach(node => {
                        if (node.nodeType === 3) { // Text node
                            const nodeText = node.nodeValue.trim();
                            if (translations['en'][nodeText]) {
                                node.nodeValue = node.nodeValue.replace(nodeText, translations['en'][nodeText]);
                                replaced = true;
                            }
                            // Also check keys that might contain specific substrings?
                            // Exact match is safer.
                        }
                    });

                    // If no text node matched but the WHOLE text matched (e.g. text inside span), AND no other children.
                    if (!replaced && el.children.length === 0 && translations['en'][text]) {
                        el.textContent = translations['en'][text];
                    }
                }
            } else {
                // Restore CN
                // We use the data-original-text logic? 
                // Actually, if we just reload the page for CN it's safer/easier. 
                // But let's try restore.
                if (el.getAttribute('data-original-text')) {
                    // Mixed content restoration is hard.
                    // Simplest: Reload page if switching to CN?
                }
            }
        });
    }

    // Init
    document.addEventListener('DOMContentLoaded', () => {
        const toggleBtn = document.getElementById('language-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const newLang = currentLang === 'cn' ? 'en' : 'cn';
                if (newLang === 'cn') {
                    localStorage.setItem('site_lang', 'cn');
                    location.reload();
                } else {
                    setLanguage('en');
                }
            });
        }

        if (currentLang === 'en') {
            setLanguage('en');
        }
    });

})();
