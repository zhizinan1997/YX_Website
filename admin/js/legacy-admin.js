const SIDEBAR_COLLAPSE_KEY = 'yx_admin2_sidebar_collapsed';
        const ADMIN_LAST_VIEW_KEY = 'yx_admin2_last_view';
        const MOBILE_NAV_BREAKPOINT = 1024;
        const CHANGELOG_FALLBACK = {
            version: 'v1.0.0',
            build_time: document.lastModified || '',
            updates: ['新增后台「更新日志」入口，可查看版本号、构建时间与更新内容。']
        };
        const ADMIN_LOGIN_LOG_DEFAULT_PAGE_SIZE = 20;
        const CHATBOT_HISTORY_DEFAULT_PAGE_SIZE = 20;
        const SIDEBAR_MENU_GROUPS = {
            'gas-related': ['h2-home', 'products', 'hydrogen-solutions'],
            'bio-related': ['bio-products']
        };
        const MESSAGE_CENTER_PREVIEW_LIMIT = 5;
        const MESSAGE_CENTER_CACHE_TTL_MS = 60 * 1000;
        let adminLoginLogsPage = 1;
        let adminLoginLogsTotalPages = 1;
        let adminLoginLogsPageSize = ADMIN_LOGIN_LOG_DEFAULT_PAGE_SIZE;
        let adminLoginLogsTotal = 0;
        let chatbotHistoryPage = 1;
        let chatbotHistoryTotalPages = 1;
        let chatbotHistoryPageSize = CHATBOT_HISTORY_DEFAULT_PAGE_SIZE;
        let chatbotHistoryTotal = 0;
        let adminSessionCheckTimer = null;
        let turnstilePublicConfig = { enabled: false, site_key: '' };
        let turnstileWidgetId = null;
        let turnstileToken = '';
        let turnstileScriptPromise = null;
        let emailAuthAdminConfig = { email_auth_enabled: false, smtp_configured: false, smtp_password_expired: false };
        let adminLoginGeoConfig = {
            enabled: true,
            continents: {},
            countries: {}
        };
        let adminLoginGeoCatalog = { continents: [] };
        let adminLoginGeoDisplayNames = null;
        let adminLoginGeoDisplayNamesEn = null;
        let adminLoginGeoCountryMetaCache = new Map();
        let adminLoginGeoSelectedContinentKey = '';
        let adminLoginGeoSelectedCountryContinentKey = '';
        let adminLoginGeoSelectedCountryCode = '';
        let loginAuthMode = 'email_code';
        let pendingLoginId = '';
        let pendingLoginEmailMasked = '';
        let loginEmailCodeCountdown = 0;
        let loginEmailCodeTimer = null;
        let bindingRequiredState = false;
        let bindingCountdown = 0;
        let bindingTimer = null;
        let globalActionResolver = null;
        const DEFAULT_PERMISSION_CATALOG = [
            { key: 'site-reports', label: '网站数据' },
            { key: 'messages', label: '留言系统' },
            { key: 'home', label: '首页设置' },
            { key: 'h2-home', label: '氢气首页' },
            { key: 'products', label: '氢气产品' },
            { key: 'bio-products', label: '生物产品' },
            { key: 'hydrogen-solutions', label: '行业方案' },
            { key: 'news-create', label: '添加资讯' },
            { key: 'jobs', label: '招聘信息' },
            { key: 'chatbot', label: 'AI 与知识库' },
            { key: 'site-settings', label: '站点设置' },
            { key: 'settings', label: '账号设置' },
            { key: 'backup', label: '备份恢复' },
            { key: 'log-records', label: '日志记录' }
        ];
        let pendingKnowledgeFiles = [];
        let permissionCatalog = [...DEFAULT_PERMISSION_CATALOG];
        let currentAdminAuth = {
            username: '',
            is_super_admin: false,
            permissions: []
        };
        let messageCenterState = {
            messages: [],
            stats: {},
            lastFetchedAt: 0
        };
        let siteReportsStartDate = '';
        let siteReportsEndDate = '';
        let siteReportsGranularity = 'day';
        let siteReportsLoading = false;
        const SITE_REPORT_EVENT_PAGE_SIZE = 8;
        const SITE_REPORT_PROVINCE_PAGE_SIZE = 8;
        const SITE_REPORT_COUNTRY_PAGE_SIZE = 8;
        let siteReportEventRowsAll = [];
        let siteReportProvinceRowsAll = [];
        let siteReportCountryRowsAll = [];
        let siteReportRecentRowsAll = [];
        let siteReportEventPage = 1;
        let siteReportProvincePage = 1;
        let siteReportCountryPage = 1;
        let siteReportRecentPage = 1;
        const SITE_REPORT_OS_META = {
            windows: { label: 'Windows', icon: 'fab fa-windows' },
            macos: { label: 'macOS', icon: 'fab fa-apple' },
            ios: { label: 'iOS', icon: 'fas fa-mobile-alt' },
            android: { label: '安卓', icon: 'fab fa-android' },
            harmonyos: { label: '鸿蒙', icon: 'fas fa-microchip' },
            linux: { label: 'Linux', icon: 'fab fa-linux' },
            unknown: { label: '未知', icon: 'fas fa-question-circle' }
        };
        const CHINA_PROVINCE_SVG_URL = '/assets/vendor/svg-maps/china.svg';
        const CHINA_PROVINCE_SVG_IDS = {
            '安徽省': 'anhui',
            '北京市': 'beijing',
            '重庆市': 'chongqing',
            '福建省': 'fujian',
            '甘肃省': 'gansu',
            '广东省': 'guangdong',
            '广西壮族自治区': 'guangxi-zhuang',
            '贵州省': 'guizhou',
            '海南省': 'hainan',
            '河北省': 'hebei',
            '黑龙江省': 'heilongjiang',
            '河南省': 'henan',
            '香港特别行政区': 'hong-kong',
            '湖北省': 'hubei',
            '湖南省': 'hunan',
            '江苏省': 'jiangsu',
            '江西省': 'jiangxi',
            '吉林省': 'jilin',
            '辽宁省': 'liaoning',
            '澳门特别行政区': 'macau',
            '内蒙古自治区': 'nei-mongol',
            '宁夏回族自治区': 'ningxia-hui',
            '青海省': 'quinghai',
            '陕西省': 'shaanxi',
            '山东省': 'shandong',
            '上海市': 'shanghai',
            '山西省': 'shanxi',
            '四川省': 'sichuan',
            '台湾省': 'taiwan',
            '天津市': 'tianjin',
            '新疆维吾尔自治区': 'xinjiang-uygur',
            '西藏自治区': 'xizang',
            '云南省': 'yunnan',
            '浙江省': 'zhejiang'
        };
        const CHINA_PROVINCE_SVG_EXTRA_PATHS = {
            taiwan: {
                ariaLabel: '台湾',
                // SVG source lacks Taiwan; inject a coastline-based outline here.
                d: 'M 596.57 509.90 L 597.77 511.12 L 598.45 512.98 L 598.55 516.20 L 599.03 517.84 L 600.50 518.50 L 601.69 508.53 L 602.18 506.62 L 603.88 504.76 L 605.96 499.09 L 605.83 498.18 L 608.14 485.62 L 607.99 484.22 L 609.57 480.49 L 610.29 477.53 L 609.90 472.78 L 611.50 470.24 L 610.88 469.76 L 610.59 468.12 L 608.94 467.76 L 607.41 465.50 L 606.08 466.10 L 605.38 467.82 L 602.08 469.68 L 600.82 473.91 L 598.88 476.51 L 594.66 488.28 L 593.99 488.80 L 593.29 490.44 L 593.35 496.00 L 592.50 500.15 L 593.60 501.27 L 594.94 508.07 Z'
            }
        };
        let chinaProvinceSvgPromise = null;
        let chinaProvinceMapRenderToken = 0;
        const CHINA_PROVINCE_TILES = [
            { name: '新疆维吾尔自治区', short: '新疆', x: 0, y: 1, w: 2 },
            { name: '西藏自治区', short: '西藏', x: 1, y: 5, w: 2 },
            { name: '青海省', short: '青海', x: 3, y: 4 },
            { name: '甘肃省', short: '甘肃', x: 4, y: 3 },
            { name: '宁夏回族自治区', short: '宁夏', x: 5, y: 3 },
            { name: '内蒙古自治区', short: '内蒙古', x: 5, y: 1, w: 2 },
            { name: '黑龙江省', short: '黑龙江', x: 10, y: 0, w: 2 },
            { name: '吉林省', short: '吉林', x: 10, y: 1 },
            { name: '辽宁省', short: '辽宁', x: 9, y: 2 },
            { name: '北京市', short: '北京', x: 8, y: 3 },
            { name: '天津市', short: '天津', x: 9, y: 3 },
            { name: '河北省', short: '河北', x: 8, y: 4 },
            { name: '山西省', short: '山西', x: 7, y: 4 },
            { name: '陕西省', short: '陕西', x: 5, y: 4 },
            { name: '山东省', short: '山东', x: 10, y: 4 },
            { name: '河南省', short: '河南', x: 7, y: 5 },
            { name: '江苏省', short: '江苏', x: 10, y: 5 },
            { name: '上海市', short: '上海', x: 11, y: 6 },
            { name: '安徽省', short: '安徽', x: 9, y: 6 },
            { name: '湖北省', short: '湖北', x: 7, y: 6 },
            { name: '浙江省', short: '浙江', x: 10, y: 7 },
            { name: '福建省', short: '福建', x: 10, y: 8 },
            { name: '江西省', short: '江西', x: 8, y: 7 },
            { name: '湖南省', short: '湖南', x: 7, y: 7 },
            { name: '重庆市', short: '重庆', x: 5, y: 6 },
            { name: '四川省', short: '四川', x: 4, y: 6 },
            { name: '贵州省', short: '贵州', x: 5, y: 7 },
            { name: '云南省', short: '云南', x: 3, y: 8 },
            { name: '广西壮族自治区', short: '广西', x: 6, y: 9 },
            { name: '广东省', short: '广东', x: 8, y: 9 },
            { name: '海南省', short: '海南', x: 8, y: 11 },
            { name: '台湾省', short: '台湾', x: 11, y: 9 },
            { name: '香港特别行政区', short: '香港', x: 9, y: 10 },
            { name: '澳门特别行政区', short: '澳门', x: 8, y: 10 }
        ];

        function updateTopbarAccountDisplay() {
            const usernameEl = document.getElementById('topbarUsername');
            const menuUsernameEl = document.getElementById('accountMenuUsername');
            const menuEmailEl = document.getElementById('accountMenuEmail');
            const menuRoleEl = document.getElementById('accountMenuRole');
            const menuPermissionsEl = document.getElementById('accountMenuPermissions');
            const lastLoginTimeEl = document.getElementById('accountMenuLastLoginTime');
            const lastLoginIpEl = document.getElementById('accountMenuLastLoginIp');
            const lastLoginLocationEl = document.getElementById('accountMenuLastLoginLocation');

            const name = String(currentAdminAuth.username || '').trim();
            const email = String(currentAdminAuth.email || currentAdminAuth.email_masked || '').trim();
            const lastLoginAt = String(currentAdminAuth.last_login_at || '').trim();
            const lastLoginIp = String(currentAdminAuth.last_login_ip || '').trim();
            const lastLoginLocation = String(currentAdminAuth.last_login_location || '').trim();
            if (usernameEl) {
                usernameEl.textContent = name || '管理员';
            }
            if (menuUsernameEl) {
                menuUsernameEl.textContent = name || '管理员';
            }
            if (menuEmailEl) {
                menuEmailEl.textContent = email ? `绑定邮箱：${email}` : '绑定邮箱：未绑定';
                menuEmailEl.classList.toggle('is-empty', !email);
            }
            if (menuRoleEl) {
                menuRoleEl.textContent = currentAdminAuth.is_super_admin ? '超级管理员' : '子账号';
            }
            if (menuPermissionsEl) {
                renderAccountMenuPermissions(menuPermissionsEl);
            }
            if (lastLoginTimeEl) {
                lastLoginTimeEl.textContent = lastLoginAt ? formatLoginTime(lastLoginAt) : '首次登录';
            }
            if (lastLoginIpEl) {
                lastLoginIpEl.textContent = lastLoginIp || '-';
            }
            if (lastLoginLocationEl) {
                lastLoginLocationEl.textContent = lastLoginLocation || '未知';
            }
        }

        function renderAccountMenuPermissions(container) {
            container.innerHTML = '';

            const catalogMap = {};
            if (Array.isArray(permissionCatalog)) {
                permissionCatalog.forEach(item => {
                    if (item.key) {
                        catalogMap[item.key] = item.label || item.key;
                    }
                });
            }

            if (currentAdminAuth.is_super_admin) {
                const allKeys = Object.keys(catalogMap);
                if (allKeys.length === 0) {
                    const tag = document.createElement('span');
                    tag.className = 'account-menu-permission-tag';
                    tag.innerHTML = '<i class="fas fa-check"></i>全部功能';
                    container.appendChild(tag);
                } else {
                    allKeys.forEach(key => {
                        const label = catalogMap[key] || key;
                        const tag = document.createElement('span');
                        tag.className = 'account-menu-permission-tag';
                        tag.innerHTML = `<i class="fas fa-check"></i>${label}`;
                        container.appendChild(tag);
                    });
                }
            } else {
                const userPerms = currentAdminAuth.permissions || [];
                const permKeys = Object.keys(catalogMap);

                permKeys.forEach(key => {
                    const hasPermission = userPerms.includes(key);
                    const label = catalogMap[key] || key;

                    const tag = document.createElement('span');
                    if (hasPermission) {
                        tag.className = 'account-menu-permission-tag';
                        tag.innerHTML = `<i class="fas fa-check"></i>${label}`;
                    } else {
                        tag.className = 'account-menu-permission-tag read-only';
                        tag.innerHTML = `<i class="fas fa-eye"></i>${label}`;
                    }
                    container.appendChild(tag);
                });
            }
        }

        function normalizeMessagesPayload(payload) {
            const messages = Array.isArray(payload) ? payload : (Array.isArray(payload?.messages) ? payload.messages : []);
            const stats = (payload && !Array.isArray(payload) && payload.stats && typeof payload.stats === 'object')
                ? payload.stats
                : {};
            return { messages, stats };
        }

        function formatMessageCenterBadgeCount(count) {
            const value = Math.max(0, Number(count) || 0);
            return value > 99 ? '99+' : String(value);
        }

        function getMessageCenterSummary(messages, stats = {}) {
            const items = Array.isArray(messages) ? messages : [];
            const unreadItems = [];
            let unreadFeedbackCount = 0;
            let unreadResumeCount = 0;

            items.forEach(msg => {
                if (!msg || msg.is_read) return;
                unreadItems.push(msg);
                if (msg.message_type === 'job_application') unreadResumeCount += 1;
                else unreadFeedbackCount += 1;
            });

            const unreadTotal = getUnreadMessageCount(items, stats);
            const previewItems = (unreadItems.length ? unreadItems : items).slice(0, MESSAGE_CENTER_PREVIEW_LIMIT);
            return {
                unreadTotal,
                unreadFeedbackCount,
                unreadResumeCount,
                previewItems,
                previewTitle: unreadItems.length ? '优先处理的未读消息' : '最近消息'
            };
        }

        function getMessageCenterItemType(msg) {
            if (msg && msg.message_type === 'job_application') {
                return { label: '简历投递', icon: 'far fa-file-alt' };
            }
            return { label: '留言消息', icon: 'far fa-envelope' };
        }

        function getMessageCenterItemTitle(msg) {
            if (!msg) return '消息';
            const name = String(msg.name || '').trim() || '匿名访客';
            if (msg.message_type === 'job_application') {
                const jobTitle = String(msg.job_title || msg.job_id || '').trim() || '招聘岗位';
                return `${name} 投递了 ${jobTitle}`;
            }
            const title = String(msg.title || '').trim();
            const content = String(msg.content || '').trim();
            if (title) return title;
            if (content) return content.length > 56 ? `${content.slice(0, 56)}...` : content;
            return `${name} 提交了新留言`;
        }

        function getMessageCenterItemMeta(msg) {
            if (!msg) return '';
            const parts = [];
            const name = String(msg.name || '').trim();
            const phone = String(msg.phone || '').trim();
            const email = String(msg.email || '').trim();
            if (name) parts.push(name);
            if (msg.message_type === 'job_application') {
                const jobTitle = String(msg.job_title || msg.job_id || '').trim();
                if (jobTitle) parts.push(jobTitle);
            }
            if (phone) parts.push(phone);
            else if (email) parts.push(email);
            return parts.join(' · ');
        }

        function buildMessageCenterItemMarkup(msg) {
            const typeMeta = getMessageCenterItemType(msg);
            const title = getMessageCenterItemTitle(msg);
            const meta = getMessageCenterItemMeta(msg);
            const time = formatLoginTime(String(msg?.timestamp || ''));
            return `
                <div class="message-center-item ${msg && !msg.is_read ? 'is-unread' : ''}">
                    <div class="message-center-item-head">
                        <span class="message-center-item-type">
                            <i class="${typeMeta.icon}"></i>
                            ${escapeHtml(typeMeta.label)}
                        </span>
                        <span class="message-center-item-time">${escapeHtml(time || '-')}</span>
                    </div>
                    <div class="message-center-item-title">${escapeHtml(title)}</div>
                    <div class="message-center-item-meta">${escapeHtml(meta || '暂无补充信息')}</div>
                    ${msg && !msg.is_read ? '<span class="message-center-item-status">未读</span>' : ''}
                </div>
            `;
        }

        function renderMessageCenterPanel() {
            const totalEl = document.getElementById('messageCenterUnreadTotal');
            const feedbackEl = document.getElementById('messageCenterFeedbackUnreadCount');
            const resumeEl = document.getElementById('messageCenterResumeUnreadCount');
            const listTitleEl = document.getElementById('messageCenterListTitle');
            const listEl = document.getElementById('messageCenterList');
            if (!totalEl || !feedbackEl || !resumeEl || !listTitleEl || !listEl) return;

            const summary = getMessageCenterSummary(messageCenterState.messages, messageCenterState.stats);
            totalEl.textContent = String(summary.unreadTotal);
            feedbackEl.textContent = String(summary.unreadFeedbackCount);
            resumeEl.textContent = String(summary.unreadResumeCount);
            listTitleEl.textContent = summary.previewTitle;

            if (!summary.previewItems.length) {
                listEl.innerHTML = '<div class="message-center-empty">暂无站内消息</div>';
                return;
            }

            listEl.innerHTML = summary.previewItems.map(buildMessageCenterItemMarkup).join('');
        }

        function setMessageCenterLoadingState(message = '加载中...') {
            const listEl = document.getElementById('messageCenterList');
            const listTitleEl = document.getElementById('messageCenterListTitle');
            if (listTitleEl) listTitleEl.textContent = '最新消息';
            if (listEl) {
                listEl.innerHTML = `<div class="message-center-empty">${escapeHtml(message)}</div>`;
            }
        }

        function setMessageCenterData(messages, stats = {}) {
            messageCenterState.messages = Array.isArray(messages) ? messages : [];
            messageCenterState.stats = stats && typeof stats === 'object' ? stats : {};
            messageCenterState.lastFetchedAt = Date.now();
            const summary = getMessageCenterSummary(messageCenterState.messages, messageCenterState.stats);
            setMessagesUnreadIndicator(summary.unreadTotal);
            renderMessageCenterPanel();
            return summary;
        }

        async function fetchMessagesData(options = {}) {
            const fetchOptions = {};
            if (options.noStore) fetchOptions.cache = 'no-store';
            const res = await fetch('/api/messages', fetchOptions);
            if (!res.ok) {
                throw new Error(`加载消息失败 (${res.status})`);
            }
            const payload = await res.json();
            const { messages, stats } = normalizeMessagesPayload(payload);
            setMessageCenterData(messages, stats);
            return { messages, stats };
        }

        function closeMessageCenter() {
            const wrap = document.getElementById('messageCenter');
            const panel = document.getElementById('messageCenterPanel');
            const trigger = document.getElementById('messageCenterTrigger');
            if (wrap) wrap.classList.remove('is-open');
            if (panel) panel.hidden = true;
            if (trigger) trigger.setAttribute('aria-expanded', 'false');
        }

        async function openMessageCenter() {
            const wrap = document.getElementById('messageCenter');
            const panel = document.getElementById('messageCenterPanel');
            const trigger = document.getElementById('messageCenterTrigger');
            if (wrap) wrap.classList.add('is-open');
            if (panel) panel.hidden = false;
            if (trigger) trigger.setAttribute('aria-expanded', 'true');
            closeAccountMenu();

            if (!messageCenterState.lastFetchedAt) {
                setMessageCenterLoadingState();
            } else {
                renderMessageCenterPanel();
            }

            if (!messageCenterState.lastFetchedAt || (Date.now() - messageCenterState.lastFetchedAt) > MESSAGE_CENTER_CACHE_TTL_MS) {
                try {
                    await fetchMessagesData({ noStore: true });
                } catch (_) {
                    if (!messageCenterState.lastFetchedAt) {
                        setMessageCenterLoadingState('消息概览加载失败，请稍后重试');
                    }
                }
            }
        }

        async function toggleMessageCenter(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const panel = document.getElementById('messageCenterPanel');
            if (!panel || panel.hidden) {
                await openMessageCenter();
            } else {
                closeMessageCenter();
            }
        }

        function openMessagesViewFromCenter(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            closeMessageCenter();
            switchView('messages');
        }

        function closeAccountMenu() {
            const wrap = document.getElementById('accountMenu');
            const panel = document.getElementById('accountMenuPanel');
            const trigger = document.getElementById('accountMenuTrigger');
            if (wrap) wrap.classList.remove('is-open');
            if (panel) panel.hidden = true;
            if (trigger) trigger.setAttribute('aria-expanded', 'false');
        }

        function openAccountMenu() {
            const wrap = document.getElementById('accountMenu');
            const panel = document.getElementById('accountMenuPanel');
            const trigger = document.getElementById('accountMenuTrigger');
            if (wrap) wrap.classList.add('is-open');
            if (panel) panel.hidden = false;
            if (trigger) trigger.setAttribute('aria-expanded', 'true');
            closeMessageCenter();
            updateTopbarAccountDisplay();
        }

        function toggleAccountMenu(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            const panel = document.getElementById('accountMenuPanel');
            if (!panel || panel.hidden) {
                openAccountMenu();
            } else {
                closeAccountMenu();
            }
        }

        async function logoutFromAccountMenu(event) {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            closeAccountMenu();
            await logout();
        }

        function getLoginSubmitButton() {
            return document.getElementById('loginSubmitBtn') || document.querySelector('#loginForm button[type="submit"]');
        }

        function setLoginSubmitState(disabled, text) {
            const btn = getLoginSubmitButton();
            if (!btn) return;
            btn.disabled = !!disabled;
            btn.textContent = text || '登 录';
        }

        function closeGlobalActionModal(ok) {
            const modal = document.getElementById('globalActionModal');
            const inputWrap = document.getElementById('globalActionInputWrap');
            const inputEl = document.getElementById('globalActionInput');
            if (!modal) return;
            modal.hidden = true;
            const resolver = globalActionResolver;
            globalActionResolver = null;
            if (!resolver) return;
            resolver({
                ok: !!ok,
                value: inputEl ? String(inputEl.value || '') : ''
            });
            if (inputWrap) inputWrap.style.display = 'none';
            if (inputEl) inputEl.value = '';
        }

        function showGlobalActionModal(options = {}) {
            const modal = document.getElementById('globalActionModal');
            const titleEl = document.getElementById('globalActionTitle');
            const msgEl = document.getElementById('globalActionMessage');
            const okBtn = document.getElementById('globalActionOkBtn');
            const cancelBtn = document.getElementById('globalActionCancelBtn');
            const inputWrap = document.getElementById('globalActionInputWrap');
            const inputEl = document.getElementById('globalActionInput');
            if (!modal || !titleEl || !msgEl || !okBtn || !cancelBtn || !inputWrap || !inputEl) {
                return Promise.resolve({ ok: true, value: '' });
            }

            const mode = String(options.mode || 'alert');
            titleEl.textContent = String(options.title || '提示');
            msgEl.textContent = String(options.message || '');
            okBtn.textContent = String(options.okText || '确定');
            cancelBtn.textContent = String(options.cancelText || '取消');

            if (mode === 'alert') {
                cancelBtn.style.display = 'none';
                inputWrap.style.display = 'none';
            } else if (mode === 'prompt') {
                cancelBtn.style.display = '';
                inputWrap.style.display = '';
                inputEl.value = String(options.defaultValue || '');
                inputEl.placeholder = String(options.placeholder || '');
            } else {
                cancelBtn.style.display = '';
                inputWrap.style.display = 'none';
            }

            modal.hidden = false;

            return new Promise((resolve) => {
                globalActionResolver = resolve;
                okBtn.onclick = () => closeGlobalActionModal(true);
                cancelBtn.onclick = () => closeGlobalActionModal(false);
                if (mode === 'prompt') {
                    setTimeout(() => inputEl.focus(), 0);
                    inputEl.onkeydown = (e) => {
                        if (e.key === 'Enter') closeGlobalActionModal(true);
                    };
                } else {
                    setTimeout(() => okBtn.focus(), 0);
                }
            });
        }

        async function showGlobalAlert(message, title = '提示') {
            await showGlobalActionModal({ mode: 'alert', title, message, okText: '知道了' });
        }

        async function showGlobalConfirm(message, title = '请确认') {
            const result = await showGlobalActionModal({ mode: 'confirm', title, message, okText: '确定', cancelText: '取消' });
            return !!result.ok;
        }

        async function showGlobalPrompt(message, defaultValue = '', title = '请输入', placeholder = '') {
            const result = await showGlobalActionModal({
                mode: 'prompt',
                title,
                message,
                defaultValue,
                placeholder,
                okText: '确定',
                cancelText: '取消'
            });
            return result.ok ? result.value : null;
        }

        window.alert = function (message) {
            showGlobalAlert(String(message || ''));
        };

        function formatChangelogTime(raw) {
            if (!raw) return '-';
            const dt = new Date(raw);
            if (Number.isNaN(dt.getTime())) return String(raw);
            const pad = (n) => String(n).padStart(2, '0');
            return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}:${pad(dt.getSeconds())}`;
        }

        function initLoginBackground() {
            const loginPage = document.getElementById('loginPage');
            const canvas = document.getElementById('loginBgCanvas');
            if (!loginPage || !canvas) return;

            const ctx = canvas.getContext('2d', { alpha: true });
            if (!ctx) return;

            const reducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
            const motionScale = reducedMotion ? 0.42 : 1;
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            const dustCount = reducedMotion ? 12 : 26;

            let width = 0;
            let height = 0;
            let rafId = 0;
            let lastTs = performance.now();

            const bloomShapes = [
                { cx: 0.18, cy: 0.18, rx: 340, ry: 200, hue: 194, alpha: 0.21, phase: 0.3, speed: 0.16, swingX: 28, swingY: 14, tilt: 0.54 },
                { cx: 0.74, cy: 0.2, rx: 300, ry: 168, hue: 179, alpha: 0.18, phase: 1.7, speed: 0.2, swingX: 20, swingY: 16, tilt: -0.36 },
                { cx: 0.3, cy: 0.76, rx: 390, ry: 220, hue: 206, alpha: 0.14, phase: 2.3, speed: 0.14, swingX: 18, swingY: 20, tilt: 0.32 },
                { cx: 0.88, cy: 0.8, rx: 350, ry: 210, hue: 188, alpha: 0.15, phase: 3.2, speed: 0.13, swingX: 16, swingY: 16, tilt: -0.52 }
            ];

            const auroraBands = [
                { y: 0.26, width: 0.7, height: 134, hue: 198, alpha: 0.1, phase: 0.3, speed: 0.12, slope: 0.18 },
                { y: 0.6, width: 0.78, height: 118, hue: 183, alpha: 0.085, phase: 1.9, speed: 0.14, slope: -0.16 },
                { y: 0.42, width: 0.56, height: 90, hue: 207, alpha: 0.07, phase: 2.8, speed: 0.1, slope: 0.05 }
            ];

            const hazeLayers = [
                { x: 0.22, y: 0.36, radius: 360, hue: 205, alpha: 0.08, phase: 0.7, speed: 0.08 },
                { x: 0.72, y: 0.62, radius: 420, hue: 188, alpha: 0.07, phase: 2.1, speed: 0.07 }
            ];

            const dust = Array.from({ length: dustCount }, () => ({
                x: Math.random(),
                y: Math.random(),
                vx: (Math.random() - 0.5) * 0.018,
                vy: (Math.random() - 0.5) * 0.02,
                size: Math.random() * 1.5 + 0.4,
                twinkle: Math.random() * Math.PI * 2,
                alpha: Math.random() * 0.3 + 0.15
            }));

            function isLoginPageVisible() {
                return getComputedStyle(loginPage).display !== 'none' && !document.hidden;
            }

            function resizeCanvas() {
                const rect = loginPage.getBoundingClientRect();
                width = Math.max(1, Math.floor(rect.width));
                height = Math.max(1, Math.floor(rect.height));
                canvas.width = Math.floor(width * dpr);
                canvas.height = Math.floor(height * dpr);
                canvas.style.width = `${width}px`;
                canvas.style.height = `${height}px`;
                ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            }

            function drawBaseGradient() {
                const grad = ctx.createLinearGradient(0, 0, width, height);
                grad.addColorStop(0, '#01040d');
                grad.addColorStop(0.44, '#041326');
                grad.addColorStop(1, '#072645');
                ctx.fillStyle = grad;
                ctx.fillRect(0, 0, width, height);
            }

            function drawHaze(timeSec) {
                for (const haze of hazeLayers) {
                    const r = haze.radius * (1 + Math.sin(timeSec * haze.speed + haze.phase) * 0.06);
                    const x = width * haze.x + Math.sin(timeSec * haze.speed + haze.phase) * 18;
                    const y = height * haze.y + Math.cos(timeSec * haze.speed * 0.9 + haze.phase) * 14;
                    const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
                    grad.addColorStop(0, `hsla(${haze.hue}, 75%, 60%, ${haze.alpha})`);
                    grad.addColorStop(1, `hsla(${haze.hue}, 70%, 45%, 0)`);
                    ctx.fillStyle = grad;
                    ctx.fillRect(x - r, y - r, r * 2, r * 2);
                }
            }

            function drawAurora(timeSec) {
                ctx.save();
                ctx.globalCompositeOperation = 'screen';
                for (const band of auroraBands) {
                    const w = width * band.width;
                    const h = band.height * (1 + Math.sin(timeSec * band.speed + band.phase) * 0.15);
                    const y = height * band.y + Math.cos(timeSec * band.speed * 0.8 + band.phase) * 22;

                    ctx.save();
                    ctx.translate(width * 0.5, y);
                    ctx.rotate(band.slope + Math.sin(timeSec * 0.12 + band.phase) * 0.04);
                    const grad = ctx.createLinearGradient(-w / 2, 0, w / 2, 0);
                    grad.addColorStop(0, `hsla(${band.hue}, 95%, 55%, 0)`);
                    grad.addColorStop(0.35, `hsla(${band.hue}, 95%, 64%, ${band.alpha})`);
                    grad.addColorStop(0.65, `hsla(${band.hue + 8}, 95%, 62%, ${band.alpha * 0.85})`);
                    grad.addColorStop(1, `hsla(${band.hue + 12}, 95%, 52%, 0)`);
                    ctx.fillStyle = grad;
                    ctx.fillRect(-w / 2, -h / 2, w, h);
                    ctx.restore();
                }
                ctx.restore();
            }

            function drawBloomShapes(timeSec) {
                ctx.save();
                ctx.globalCompositeOperation = 'screen';
                ctx.filter = 'blur(10px)';
                for (const shape of bloomShapes) {
                    const driftX = Math.sin(timeSec * shape.speed + shape.phase) * shape.swingX;
                    const driftY = Math.cos(timeSec * shape.speed * 0.9 + shape.phase) * shape.swingY;
                    const px = width * shape.cx + driftX;
                    const py = height * shape.cy + driftY;
                    const rx = shape.rx * (1 + Math.sin(timeSec * shape.speed * 0.7 + shape.phase) * 0.09);
                    const ry = shape.ry * (1 + Math.cos(timeSec * shape.speed * 0.65 + shape.phase) * 0.1);
                    const rot = shape.tilt + Math.sin(timeSec * 0.1 + shape.phase) * 0.06;

                    ctx.save();
                    ctx.translate(px, py);
                    ctx.rotate(rot);
                    const grad = ctx.createRadialGradient(-rx * 0.18, -ry * 0.12, 0, 0, 0, rx);
                    grad.addColorStop(0, `hsla(${shape.hue}, 98%, 66%, ${shape.alpha})`);
                    grad.addColorStop(0.44, `hsla(${shape.hue + 6}, 94%, 58%, ${shape.alpha * 0.5})`);
                    grad.addColorStop(1, `hsla(${shape.hue + 12}, 98%, 48%, 0)`);
                    ctx.fillStyle = grad;
                    ctx.beginPath();
                    ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.restore();
                }
                ctx.filter = 'none';
                ctx.restore();
            }

            function drawDust(dt, timeSec) {
                for (const p of dust) {
                    p.x += p.vx * dt;
                    p.y += p.vy * dt;
                    if (p.x < -0.02) p.x = 1.02;
                    else if (p.x > 1.02) p.x = -0.02;
                    if (p.y < -0.02) p.y = 1.02;
                    else if (p.y > 1.02) p.y = -0.02;

                    const px = p.x * width;
                    const py = p.y * height;
                    const flicker = (Math.sin(timeSec * 1.2 + p.twinkle) + 1) * 0.18;
                    const alpha = p.alpha + flicker;
                    ctx.fillStyle = `rgba(196, 230, 255, ${alpha.toFixed(3)})`;
                    ctx.beginPath();
                    ctx.arc(px, py, p.size, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            function drawVignette() {
                const g = ctx.createRadialGradient(width * 0.52, height * 0.48, Math.min(width, height) * 0.12, width * 0.5, height * 0.5, Math.max(width, height) * 0.74);
                g.addColorStop(0, 'rgba(1, 7, 16, 0)');
                g.addColorStop(1, 'rgba(1, 6, 14, 0.56)');
                ctx.fillStyle = g;
                ctx.fillRect(0, 0, width, height);
            }

            function drawFrame(now) {
                rafId = 0;
                if (!isLoginPageVisible()) return;

                const dt = Math.min((now - lastTs) / 1000, 0.04);
                lastTs = now;
                const timeSec = (now / 1000) * motionScale;

                drawBaseGradient();
                drawHaze(timeSec);
                drawAurora(timeSec);
                drawBloomShapes(timeSec);
                drawDust(dt * motionScale, timeSec);
                drawVignette();
                rafId = requestAnimationFrame(drawFrame);
            }

            function start() {
                if (rafId || !isLoginPageVisible()) return;
                lastTs = performance.now();
                rafId = requestAnimationFrame(drawFrame);
            }

            function stop() {
                if (!rafId) return;
                cancelAnimationFrame(rafId);
                rafId = 0;
            }

            const loginObserver = new MutationObserver(() => {
                if (isLoginPageVisible()) {
                    resizeCanvas();
                    start();
                } else {
                    stop();
                }
            });
            loginObserver.observe(loginPage, { attributes: true, attributeFilter: ['style', 'class'] });

            document.addEventListener('visibilitychange', () => {
                if (document.hidden) stop();
                else start();
            });
            window.addEventListener('resize', resizeCanvas, { passive: true });

            resizeCanvas();
            start();
        }

        let adminAuthRedirectPending = false;

        function handleAdminApiUnauthorized() {
            if (adminAuthRedirectPending) return;
            adminAuthRedirectPending = true;
            if (adminSessionCheckTimer) {
                clearInterval(adminSessionCheckTimer);
                adminSessionCheckTimer = null;
            }
            const dashboard = document.getElementById('dashboard');
            const loginPage = document.getElementById('loginPage');
            const loginError = document.getElementById('loginError');
            if (dashboard) dashboard.style.display = 'none';
            if (loginPage) loginPage.style.display = 'flex';
            if (loginError) loginError.textContent = '登录已过期，请重新登录。';
            resetLoginTurnstile();
        }

        const nativeFetch = window.fetch.bind(window);
        window.fetch = async function (input, init) {
            const response = await nativeFetch(input, init);
            const url = typeof input === 'string' ? input : String((input && input.url) || '');
            if (response.status === 401 && url.startsWith('/api/')) {
                handleAdminApiUnauthorized();
            }
            return response;
        };

        // --- Init ---
        initLoginBackground();
        initLoginSecurity();
        checkLoginStatus();
        loadVersionBadge();
        document.addEventListener('click', (event) => {
            const messageCenterWrap = document.getElementById('messageCenter');
            if (messageCenterWrap && !messageCenterWrap.contains(event.target)) {
                closeMessageCenter();
            }
            const wrap = document.getElementById('accountMenu');
            if (!wrap) return;
            if (!wrap.contains(event.target)) {
                closeAccountMenu();
            }
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeMessageCenter();
                closeAccountMenu();
                closeMobileSidebar();
            }
        });
        window.addEventListener('resize', () => {
            syncSidebarModeForViewport();
        }, { passive: true });
        let responsiveTableLabelObserver = null;
        let responsiveTableLabelQueued = false;

        function isMobileAdminViewport() {
            return window.matchMedia(`(max-width: ${MOBILE_NAV_BREAKPOINT}px)`).matches;
        }

        function applyResponsiveTableLabels(scope = document) {
            const root = scope && scope.querySelectorAll ? scope : document;
            const tables = root.querySelectorAll('table');
            tables.forEach((table) => {
                const isProductsManageTable = table.classList.contains('products-manage-table');
                const headers = Array.from(table.querySelectorAll('thead th'))
                    .map((th) => String((th.textContent || '')).trim());
                const hasBody = !!table.querySelector('tbody');
                const isDataTable = !isProductsManageTable && hasBody && headers.length > 0;
                if (isDataTable) {
                    table.setAttribute('data-mobile-card', '1');
                } else {
                    table.removeAttribute('data-mobile-card');
                }
                if (!isDataTable) return;
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach((row) => {
                    const cells = Array.from(row.children).filter((el) => el.tagName === 'TD');
                    if (!cells.length) return;
                    if (cells.length === 1 && Number(cells[0].colSpan || 1) > 1) {
                        cells[0].setAttribute('data-label', '');
                        return;
                    }
                    cells.forEach((cell, idx) => {
                        const label = headers[idx] || '';
                        if (label) {
                            cell.setAttribute('data-label', label);
                        } else {
                            cell.removeAttribute('data-label');
                        }
                    });
                });
            });
        }

        function queueResponsiveTableLabels() {
            if (responsiveTableLabelQueued) return;
            responsiveTableLabelQueued = true;
            requestAnimationFrame(() => {
                responsiveTableLabelQueued = false;
                applyResponsiveTableLabels(document);
            });
        }

        function initResponsiveTableLabels() {
            if (responsiveTableLabelObserver) return;
            const dashboard = document.getElementById('dashboard');
            if (!dashboard) return;
            queueResponsiveTableLabels();
            responsiveTableLabelObserver = new MutationObserver(() => {
                queueResponsiveTableLabels();
            });
            responsiveTableLabelObserver.observe(dashboard, { childList: true, subtree: true });
        }

        function setMobileMenuExpanded(expanded) {
            const btnEl = document.getElementById('mobileMenuBtn');
            if (btnEl) {
                btnEl.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            }
        }

        function setMobileSidebarOpen(open) {
            if (!isMobileAdminViewport()) {
                document.body.classList.remove('mobile-sidebar-open');
                setMobileMenuExpanded(false);
                return;
            }
            const willOpen = !!open;
            document.body.classList.toggle('mobile-sidebar-open', willOpen);
            setMobileMenuExpanded(willOpen);
        }

        function closeMobileSidebar() {
            setMobileSidebarOpen(false);
        }

        function updateSidebarToggleButton() {
            const textEl = document.getElementById('sidebarToggleText');
            const btnEl = document.getElementById('sidebarToggleBtn');
            if (!textEl || !btnEl) return;
            const collapsed = document.body.classList.contains('sidebar-collapsed');
            textEl.textContent = collapsed ? '显示侧边栏' : '折叠侧边栏';
            btnEl.setAttribute('aria-label', textEl.textContent);
            btnEl.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
            btnEl.title = textEl.textContent;
        }

        function setSidebarCollapsed(collapsed, save = true) {
            document.body.classList.toggle('sidebar-collapsed', !!collapsed);
            updateSidebarToggleButton();
            if (save) {
                localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? '1' : '0');
            }
        }

        function syncSidebarModeForViewport() {
            if (isMobileAdminViewport()) {
                setSidebarCollapsed(false, false);
                setMobileSidebarOpen(false);
                return;
            }
            document.body.classList.remove('mobile-sidebar-open');
            setMobileMenuExpanded(false);
            const collapsed = localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === '1';
            setSidebarCollapsed(collapsed, false);
        }

        function toggleSidebar() {
            if (isMobileAdminViewport()) {
                const opened = document.body.classList.contains('mobile-sidebar-open');
                setMobileSidebarOpen(!opened);
                return;
            }
            const collapsed = document.body.classList.contains('sidebar-collapsed');
            setSidebarCollapsed(!collapsed, true);
        }

        function setAdminAuthFromCheck(data) {
            const safe = data && typeof data === 'object' ? data : {};
            currentAdminAuth = {
                username: String(safe.username || ''),
                is_super_admin: safe.is_super_admin === true,
                permissions: Array.isArray(safe.permissions) ? safe.permissions.map(v => String(v || '').trim()).filter(Boolean) : [],
                email: String(safe.email || ''),
                email_masked: String(safe.email_masked || ''),
                email_verified: safe.email_verified === true,
                last_login_at: String(safe.last_login_at || ''),
                last_login_ip: String(safe.last_login_ip || ''),
                last_login_location: String(safe.last_login_location || ''),
                current_login_at: String(safe.current_login_at || ''),
                current_login_ip: String(safe.current_login_ip || ''),
                current_login_location: String(safe.current_login_location || '')
            };
            bindingRequiredState = safe.binding_required === true;
            if (Array.isArray(safe.permission_catalog) && safe.permission_catalog.length) {
                permissionCatalog = safe.permission_catalog
                    .map(item => ({
                        key: String((item && item.key) || '').trim(),
                        label: String((item && item.label) || '').trim()
                    }))
                    .filter(item => item.key);
            } else {
                permissionCatalog = [...DEFAULT_PERMISSION_CATALOG];
            }
            updateTopbarAccountDisplay();
            const usernameInput = document.getElementById('newUsername');
            if (usernameInput && currentAdminAuth.username) {
                usernameInput.value = currentAdminAuth.username;
            }
        }

        function hasViewPermission(viewName) {
            return true;
        }

        function canEditView(viewName) {
            if (currentAdminAuth.is_super_admin) return true;
            return currentAdminAuth.permissions.includes(String(viewName || '').trim());
        }

        function getSidebarMenuGroup(groupKey) {
            const key = String(groupKey || '').trim();
            if (!key) return null;
            return document.querySelector(`.sidebar-menu-group[data-menu-group="${key}"]`);
        }

        function setSidebarMenuGroupOpen(groupKey, open) {
            const group = getSidebarMenuGroup(groupKey);
            if (!group) return;
            const willOpen = !!open;
            group.classList.toggle('is-open', willOpen);
            const itemsWrap = group.querySelector('.sidebar-menu-group-items');
            if (itemsWrap) {
                itemsWrap.hidden = !willOpen;
            }
            const toggleBtn = group.querySelector('.sidebar-menu-group-toggle');
            if (toggleBtn) {
                toggleBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            }
        }

        function toggleSidebarMenuGroup(groupKey) {
            const group = getSidebarMenuGroup(groupKey);
            if (!group || group.style.display === 'none') return;
            if (document.body.classList.contains('sidebar-collapsed') && !isMobileAdminViewport()) {
                setSidebarCollapsed(false, true);
                setSidebarMenuGroupOpen(groupKey, true);
                return;
            }
            const opened = group.classList.contains('is-open');
            setSidebarMenuGroupOpen(groupKey, !opened);
        }

        function syncSidebarMenuGroups(activeView = '') {
            const view = String(activeView || '').trim();
            Object.entries(SIDEBAR_MENU_GROUPS).forEach(([groupKey, viewKeys]) => {
                const group = getSidebarMenuGroup(groupKey);
                if (!group) return;
                const hasActiveChild = viewKeys.includes(view);
                group.classList.toggle('has-active-child', hasActiveChild);
                if (hasActiveChild) {
                    setSidebarMenuGroupOpen(groupKey, true);
                }
            });
        }

        function syncSidebarMenuGroupVisibility() {
            Object.entries(SIDEBAR_MENU_GROUPS).forEach(([groupKey, viewKeys]) => {
                const group = getSidebarMenuGroup(groupKey);
                if (!group) return;
                const hasVisibleChildren = viewKeys.some((viewKey) => {
                    const item = document.querySelector(`.menu-item[data-view="${viewKey}"]`);
                    return !!item && item.style.display !== 'none';
                });
                group.style.display = hasVisibleChildren ? '' : 'none';
                if (!hasVisibleChildren) {
                    group.classList.remove('has-active-child');
                    setSidebarMenuGroupOpen(groupKey, false);
                }
            });
        }

        function getFirstAllowedView() {
            return 'site-reports';
        }

        function getHashAdminView() {
            const raw = String(window.location.hash || '').trim();
            if (!raw) return '';
            return raw.replace(/^#\/?/, '').trim();
        }

        function syncHashAdminView(viewName) {
            const name = String(viewName || '').trim();
            if (!name) return;
            const nextHash = `#/${name}`;
            if (window.location.hash !== nextHash) {
                history.replaceState(null, '', nextHash);
            }
        }

        function getStoredAdminView() {
            const raw = localStorage.getItem(ADMIN_LAST_VIEW_KEY);
            return String(raw || '').trim();
        }

        function saveStoredAdminView(viewName) {
            const name = String(viewName || '').trim();
            if (!name) return;
            localStorage.setItem(ADMIN_LAST_VIEW_KEY, name);
            syncHashAdminView(name);
        }

        function getPreferredInitialView() {
            const hashed = getHashAdminView();
            if (
                hashed &&
                hasViewPermission(hashed) &&
                document.querySelector(`.menu-item[data-view="${hashed}"]`) &&
                document.getElementById(`view-${hashed}`)
            ) {
                return hashed;
            }
            const stored = getStoredAdminView();
            if (
                stored &&
                hasViewPermission(stored) &&
                document.querySelector(`.menu-item[data-view="${stored}"]`) &&
                document.getElementById(`view-${stored}`)
            ) {
                return stored;
            }
            return getFirstAllowedView();
        }

        function applySidebarPermissions() {
            const menuItems = Array.from(document.querySelectorAll('.menu-item[data-view]'));
            for (const el of menuItems) {
                const key = String(el.dataset.view || '').trim();
                const allowed = hasViewPermission(key);
                el.style.display = '';
                const isEditable = canEditView(key);
                el.classList.toggle('read-only-menu', allowed && !isEditable);
            }
            syncSidebarMenuGroupVisibility();
        }

        function syncSubAccountManageVisibility() {
            const noAccess = document.getElementById('subAccountsNoAccess');
            const manageArea = document.getElementById('subAccountsManageArea');
            if (!noAccess || !manageArea) return;
            if (currentAdminAuth.is_super_admin) {
                noAccess.style.display = 'none';
                manageArea.style.display = '';
            } else {
                noAccess.style.display = 'block';
                manageArea.style.display = 'none';
            }
        }

        function getUnreadMessageCount(messages, stats = {}) {
            if (stats.unread_count !== undefined && stats.unread_count !== null && Number.isFinite(Number(stats.unread_count))) {
                return Math.max(0, Number(stats.unread_count) || 0);
            }
            const total = Number(stats.total_count);
            const read = Number(stats.read_count);
            if (Number.isFinite(total) && Number.isFinite(read)) {
                return Math.max(0, total - read);
            }
            if (!Array.isArray(messages)) return 0;
            return messages.reduce((count, msg) => count + (msg && !msg.is_read ? 1 : 0), 0);
        }

        function setMessagesUnreadIndicator(unreadCount) {
            const dot = document.getElementById('messagesUnreadDot');
            const item = document.querySelector('.menu-item[data-view="messages"]');
            const count = Math.max(0, Number(unreadCount) || 0);
            const trigger = document.getElementById('messageCenterTrigger');
            const badge = document.getElementById('messageCenterUnreadBadge');
            const label = count > 0 ? `有 ${count} 条未读站内消息` : '无未读站内消息';

            if (dot && item) {
                dot.hidden = count <= 0;
                item.classList.toggle('has-unread-messages', count > 0);
                item.title = count > 0 ? label : '';
                dot.setAttribute('aria-label', label);
            }

            if (trigger) {
                trigger.classList.toggle('has-unread', count > 0);
                trigger.setAttribute('aria-label', label);
                trigger.title = count > 0 ? label : '站内消息';
            }
            if (badge) {
                badge.hidden = count <= 0;
                badge.textContent = formatMessageCenterBadgeCount(count);
            }
        }

        async function refreshMessagesUnreadIndicator() {
            try {
                await fetchMessagesData({ noStore: true });
            } catch (_) {
                // Keep the previous indicator state when the lightweight refresh fails.
            }
        }

        // --- Auth Functions ---
        const TURNSTILE_LOAD_TIMEOUT_MS = 30000;

        async function initLoginSecurity() {
            const wrap = document.getElementById('loginTurnstileWrap');
            const errEl = document.getElementById('loginTurnstileError');
            if (errEl) errEl.textContent = '';
            if (wrap) wrap.style.display = 'none';
            resetPendingLoginState();
            await loadEmailAuthPublicConfig();
            setLoginSubmitState(true, '加载中...');
            try {
                const res = await fetch('/api/admin/security/turnstile/public', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                turnstilePublicConfig = {
                    enabled: data.enabled === true,
                    site_key: String(data.site_key || '').trim()
                };

                if (!turnstilePublicConfig.enabled || !turnstilePublicConfig.site_key) {
                    turnstileToken = '';
                    setLoginSubmitState(false, '登 录');
                    updateLoginActionState();
                    return;
                }

                if (wrap) wrap.style.display = 'block';
                await ensureTurnstileScriptLoaded();
                renderLoginTurnstile();
                setLoginSubmitState(true, '请先完成人机验证');
                updateLoginActionState();
            } catch (e) {
                const isCfTimeout = e && e.message && e.message.includes('Turnstile');
                if (errEl) errEl.textContent = 'Cloudflare 人机挑战验证暂时无法连通，请稍后再次尝试或者更换网络。';
                setLoginSubmitState(true, '人机验证不可用');
                updateLoginActionState();
            }
        }

        function ensureTurnstileScriptLoaded() {
            if (window.turnstile) return Promise.resolve();
            if (turnstileScriptPromise) return turnstileScriptPromise;

            const loadPromise = new Promise((resolve, reject) => {
                const existing = document.querySelector('script[data-turnstile="1"]');
                if (existing) {
                    existing.addEventListener('load', () => resolve(), { once: true });
                    existing.addEventListener('error', () => reject(new Error('Turnstile script load failed')), { once: true });
                    return;
                }

                const script = document.createElement('script');
                script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
                script.async = true;
                script.defer = true;
                script.dataset.turnstile = '1';
                script.onload = () => resolve();
                script.onerror = () => reject(new Error('Turnstile script load failed'));
                document.head.appendChild(script);
            });

            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Turnstile script load timeout')), TURNSTILE_LOAD_TIMEOUT_MS);
            });

            turnstileScriptPromise = Promise.race([loadPromise, timeoutPromise]).catch(err => {
                turnstileScriptPromise = null;
                throw err;
            });
            return turnstileScriptPromise;
        }

        function renderLoginTurnstile() {
            const target = document.getElementById('loginTurnstileWidget');
            const errEl = document.getElementById('loginTurnstileError');
            if (!target || !window.turnstile || !turnstilePublicConfig.site_key) return;
            target.innerHTML = '';
            turnstileWidgetId = window.turnstile.render('#loginTurnstileWidget', {
                sitekey: turnstilePublicConfig.site_key,
                theme: 'light',
                callback: function (token) {
                    turnstileToken = String(token || '');
                    if (errEl) errEl.textContent = '';
                    setLoginSubmitState(false, '登 录');
                    updateLoginActionState();
                },
                'expired-callback': function () {
                    turnstileToken = '';
                    if (errEl) errEl.textContent = '验证已过期，请重新验证';
                    setLoginSubmitState(true, '请先完成人机验证');
                    updateLoginActionState();
                },
                'error-callback': function () {
                    turnstileToken = '';
                    if (errEl) errEl.textContent = '人机验证异常，请刷新后重试';
                    setLoginSubmitState(true, '请先完成人机验证');
                    updateLoginActionState();
                }
            });
        }

        function resetLoginTurnstile() {
            turnstileToken = '';
            const errEl = document.getElementById('loginTurnstileError');
            if (errEl) errEl.textContent = '';
            if (turnstilePublicConfig.enabled) {
                setLoginSubmitState(true, '请先完成人机验证');
            }
            if (window.turnstile && turnstileWidgetId !== null && turnstileWidgetId !== undefined) {
                try {
                    window.turnstile.reset(turnstileWidgetId);
                } catch (_) { }
            }
            updateLoginActionState();
        }

        async function checkLoginStatus() {
            try {
                const res = await fetch('/admin/check');
                const data = await parseJsonSafe(res);
                if (data.logged_in) {
                    setAdminAuthFromCheck(data);
                    showDashboard(data);
                } else {
                    bindingRequiredState = false;
                    document.getElementById('loginPage').style.display = 'flex';
                    document.getElementById('dashboard').style.display = 'none';
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function loadVersionBadge() {
            const badge = document.getElementById('versionBadge');
            if (!badge) return;
            try {
                const res = await fetch('/api/changelog/latest');
                const data = await res.json();
                const version = data?.version || '?.?.?';
                badge.innerHTML = `
                    <span class="version-label">版本号：</span><span class="version-number">${version}</span>
                `;
                badge.title = `最新版本：${version}`;
            } catch (e) {
                badge.innerHTML = '<span class="version-label">版本号：</span><span class="version-number">?.?.?</span>';
            }
        }

        function showLoginFailModal(reason) {
            const modal = document.getElementById('loginFailModal');
            const reasonEl = document.getElementById('loginFailReason');
            if (reasonEl) reasonEl.textContent = String(reason || '登录失败，请稍后重试。');
            if (modal) modal.hidden = false;
        }

        function closeLoginFailModal() {
            const modal = document.getElementById('loginFailModal');
            if (!modal) return;
            modal.hidden = true;
        }

        async function parseJsonSafe(res) {
            try {
                return await res.json();
            } catch (e) {
                return {};
            }
        }

        /* --- IP 预检弹窗逻辑 --- */
        let ipPreflightResolver = null;

        function showIpPreflightModal() {
            const modal = document.getElementById('ipPreflightModal');
            const body = document.getElementById('ipPreflightBody');
            const actions = document.getElementById('ipPreflightActions');
            const headIcon = document.getElementById('ipPreflightHeadIcon');
            const title = document.getElementById('ipPreflightTitle');
            if (!modal || !body) return;
            title.textContent = 'IP 安全核验';
            headIcon.style.background = '#dbeafe';
            headIcon.style.color = '#1d4ed8';
            headIcon.innerHTML = '<i class="fas fa-shield-halved"></i>';
            body.innerHTML = '<div class="ip-preflight-spinner"></div><div class="ip-preflight-status">正在核验您的登录 IP…</div>';
            actions.style.display = 'none';
            modal.hidden = false;
        }

        function showIpPreflightAllowed(ip, location) {
            const body = document.getElementById('ipPreflightBody');
            const headIcon = document.getElementById('ipPreflightHeadIcon');
            const title = document.getElementById('ipPreflightTitle');
            if (!body) return;
            title.textContent = 'IP 核验通过';
            headIcon.style.background = '#dcfce7';
            headIcon.style.color = '#15803d';
            headIcon.innerHTML = '<i class="fas fa-circle-check"></i>';
            body.innerHTML = `
                <div class="ip-preflight-icon-ok is-ok"><i class="fas fa-circle-check"></i></div>
                <div class="ip-preflight-status">IP 核验通过，正在登录…</div>
                <div class="ip-preflight-detail">
                    <span class="ip-addr">${ip}</span>
                    <span style="margin:0 4px;">·</span>
                    <span class="ip-location">${location}</span>
                </div>
            `;
        }

        function showIpPreflightBlocked(ip, location) {
            const body = document.getElementById('ipPreflightBody');
            const actions = document.getElementById('ipPreflightActions');
            const headIcon = document.getElementById('ipPreflightHeadIcon');
            const title = document.getElementById('ipPreflightTitle');
            if (!body) return;
            title.textContent = '登录被拒绝';
            headIcon.style.background = '#fee2e2';
            headIcon.style.color = '#b91c1c';
            headIcon.innerHTML = '<i class="fas fa-circle-exclamation"></i>';
            body.innerHTML = `
                <div class="ip-preflight-icon-ok is-blocked"><i class="fas fa-ban"></i></div>
                <div class="ip-preflight-detail" style="text-align:left;">
                    <div class="ip-preflight-warn">
                        <div class="warn-title"><i class="fas fa-triangle-exclamation"></i> 禁止登录</div>
                        您的 IP <span class="ip-addr">${ip}</span> 归属地为 <span class="ip-location">${location}</span>，不符合当前后台地域访问规则，已被禁止登录。
                        <br><br>
                        <span style="color:#7f1d1d;font-weight:600;">⚠ 您的登录 IP 已被记录在系统中！</span>
                    </div>
                </div>
            `;
            if (actions) actions.style.display = 'flex';
        }

        function showIpPreflightError(message) {
            const body = document.getElementById('ipPreflightBody');
            const actions = document.getElementById('ipPreflightActions');
            const headIcon = document.getElementById('ipPreflightHeadIcon');
            const title = document.getElementById('ipPreflightTitle');
            if (!body) return;
            title.textContent = 'IP 核验失败';
            headIcon.style.background = '#fef3c7';
            headIcon.style.color = '#92400e';
            headIcon.innerHTML = '<i class="fas fa-triangle-exclamation"></i>';
            body.innerHTML = `
                <div class="ip-preflight-icon-ok" style="background:#fef3c7;color:#92400e;"><i class="fas fa-triangle-exclamation"></i></div>
                <div class="ip-preflight-status">${message || 'IP 核验失败，请稍后重试'}</div>
            `;
            if (actions) actions.style.display = 'flex';
        }

        function closeIpPreflightModal() {
            const modal = document.getElementById('ipPreflightModal');
            if (modal) modal.hidden = true;
        }

        async function runIpPreflight() {
            showIpPreflightModal();
            try {
                const res = await fetch('/api/admin/ip-preflight', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                const ip = String(data.ip || '').trim() || '未知';
                const location = String(data.location || '').trim() || '未知';
                const allowed = data.allowed === true;

                if (allowed) {
                    showIpPreflightAllowed(ip, location);
                    return { allowed: true, ip, location };
                } else {
                    showIpPreflightBlocked(ip, location);
                    return { allowed: false, ip, location };
                }
            } catch (e) {
                showIpPreflightError('IP 核验服务暂时不可用，请稍后重试。');
                return { allowed: false, ip: '', location: '' };
            }
        }

        function updateLoginActionState() {
            const sendBtn = document.getElementById('loginSendCodeBtn');
            const submitBtn = document.getElementById('loginSubmitBtn');
            const codeWrap = document.getElementById('loginEmailCodeWrap');
            const emailEnabled = emailAuthAdminConfig.email_auth_enabled === true;
            const emailAvailable = emailEnabled && emailAuthAdminConfig.smtp_ready !== false;
            const inCodeStep = emailEnabled && !!pendingLoginId;
            const isQuickEmailMode = loginAuthMode === 'email_code';
            const canUseEmailCode = emailAvailable;
            const needsTurnstile = turnstilePublicConfig.enabled && !turnstileToken;
            if (sendBtn) {
                sendBtn.style.display = (isQuickEmailMode || inCodeStep) ? '' : 'none';
                sendBtn.disabled = !canUseEmailCode || needsTurnstile || loginEmailCodeCountdown > 0 || (!isQuickEmailMode && !inCodeStep);
                if (isQuickEmailMode || inCodeStep) {
                    sendBtn.textContent = emailAuthAdminConfig.smtp_ready === false
                        ? '邮箱验证暂不可用'
                        : (loginEmailCodeCountdown > 0 ? `重新发送（${loginEmailCodeCountdown}s）` : '发送邮箱验证码');
                }
            }
            if (submitBtn) {
                submitBtn.style.display = '';
                if (isQuickEmailMode) {
                    submitBtn.textContent = '验证并登录';
                    submitBtn.disabled = !inCodeStep;
                } else {
                    submitBtn.textContent = inCodeStep ? '验证并登录' : (emailAvailable ? '下一步：邮箱验证' : '登 录');
                    submitBtn.disabled = !!needsTurnstile;
                }
            }
            if (codeWrap) {
                codeWrap.style.display = inCodeStep ? 'block' : 'none';
            }
        }

        function getLoginModeLabel(mode = loginAuthMode) {
            if (mode === 'account_password') return '用户名/邮箱登录';
            if (mode === 'username_password') return '用户名 + 密码';
            if (mode === 'email_password') return '邮箱 + 密码';
            return '邮箱验证码快捷登录';
        }

        function setLoginAuthMode(mode, options = {}) {
            const nextMode = ['email_code', 'account_password', 'username_password', 'email_password'].includes(mode) ? mode : 'email_code';
            const emailAvailable = emailAuthAdminConfig.email_auth_enabled === true && emailAuthAdminConfig.smtp_ready !== false;
            loginAuthMode = nextMode;
            if (!options.keepPending) {
                resetPendingLoginState({
                    hint: nextMode === 'email_code'
                        ? '验证码将发送到已验证安全邮箱。'
                        : (emailAvailable ? '账号密码验证通过后，可发送邮箱验证码。' : '邮箱验证暂不可用，账号密码校验通过后将直接登录。')
                });
            }

            const subtitle = document.getElementById('loginSubtitle');
            const methodSwitch = document.querySelector('.login-method-switch');
            const emailWrap = document.getElementById('loginEmailWrap');
            const usernameWrap = document.getElementById('loginUsernameWrap');
            const passwordWrap = document.getElementById('loginPasswordWrap');
            const emailInput = document.getElementById('loginEmail');
            const usernameInput = document.getElementById('username');
            const passwordInput = document.getElementById('password');
            const quickBtn = document.getElementById('loginModeEmailCodeBtn');
            const accountBtn = document.getElementById('loginModeAccountBtn');

            if (subtitle) {
                subtitle.textContent = nextMode === 'account_password'
                    ? (emailAvailable ? '请输入用户名或已验证邮箱和密码，通过邮箱验证码后进入后台。' : '邮箱验证暂不可用，请使用用户名/邮箱和密码登录。')
                    : (nextMode === 'username_password'
                        ? '请输入用户名和密码，通过邮箱验证码后进入后台。'
                    : (nextMode === 'email_password'
                        ? '请输入已验证邮箱和密码，通过邮箱验证码后进入后台。'
                        : '仅授权管理员可访问，请使用已验证邮箱快捷登录。'));
            }
            if (methodSwitch) methodSwitch.style.display = emailAvailable ? '' : 'none';
            if (emailWrap) emailWrap.style.display = (nextMode === 'username_password' || nextMode === 'account_password') ? 'none' : 'block';
            if (usernameWrap) usernameWrap.style.display = (nextMode === 'username_password' || nextMode === 'account_password') ? 'block' : 'none';
            if (passwordWrap) passwordWrap.style.display = nextMode === 'email_code' ? 'none' : 'block';

            if (emailInput) emailInput.required = !(nextMode === 'username_password' || nextMode === 'account_password');
            if (usernameInput) usernameInput.required = nextMode === 'username_password' || nextMode === 'account_password';
            if (passwordInput) passwordInput.required = nextMode !== 'email_code';

            if (quickBtn) quickBtn.hidden = nextMode === 'email_code' || !emailAvailable;
            if (accountBtn) accountBtn.classList.toggle('active', nextMode === 'account_password');

            updateLoginActionState();
        }

        function stopLoginCodeTimer() {
            if (loginEmailCodeTimer) {
                clearInterval(loginEmailCodeTimer);
                loginEmailCodeTimer = null;
            }
        }

        function startLoginCodeTimer(seconds) {
            stopLoginCodeTimer();
            loginEmailCodeCountdown = Math.max(0, Number(seconds || 0));
            updateLoginActionState();
            if (loginEmailCodeCountdown <= 0) return;
            loginEmailCodeTimer = setInterval(() => {
                loginEmailCodeCountdown = Math.max(0, loginEmailCodeCountdown - 1);
                updateLoginActionState();
                if (loginEmailCodeCountdown <= 0) stopLoginCodeTimer();
            }, 1000);
        }

        function resetPendingLoginState(options = {}) {
            pendingLoginId = '';
            pendingLoginEmailMasked = '';
            stopLoginCodeTimer();
            loginEmailCodeCountdown = 0;
            const codeInput = document.getElementById('loginEmailCode');
            const hintEl = document.getElementById('loginEmailHint');
            if (codeInput) codeInput.value = '';
            if (hintEl) hintEl.textContent = options.hint || '验证码将发送到已绑定安全邮箱。';
            updateLoginActionState();
        }

        async function loadEmailAuthPublicConfig() {
            try {
                const res = await fetch('/api/admin/email-auth/public', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                emailAuthAdminConfig = data && typeof data === 'object' ? data : { email_auth_enabled: false };
            } catch (_) {
                emailAuthAdminConfig = { email_auth_enabled: false, smtp_configured: false, smtp_password_expired: false };
            }
            const emailAvailable = emailAuthAdminConfig.email_auth_enabled === true && emailAuthAdminConfig.smtp_ready !== false;
            if (!emailAvailable && loginAuthMode === 'email_code') {
                setLoginAuthMode('account_password');
                return;
            }
            setLoginAuthMode(loginAuthMode, { keepPending: true });
        }

        function getLoginEmailValue() {
            return String(document.getElementById('loginEmail')?.value || '').trim();
        }

        function getLoginDisplayName() {
            if (loginAuthMode === 'username_password' || loginAuthMode === 'account_password') {
                return String(document.getElementById('username')?.value || '').trim();
            }
            return getLoginEmailValue();
        }

        function getPasswordLoginPayload() {
            const payload = {
                login_method: loginAuthMode,
                password: document.getElementById('password')?.value || '',
                turnstileToken: turnstileToken
            };
            if (loginAuthMode === 'account_password') {
                payload.account = document.getElementById('username')?.value || '';
            } else if (loginAuthMode === 'email_password') {
                payload.email = getLoginEmailValue();
            } else {
                payload.username = document.getElementById('username')?.value || '';
            }
            return payload;
        }

        async function handleLoginStart() {
            const err = document.getElementById('loginError');
            const turnstileErr = document.getElementById('loginTurnstileError');
            if (err) err.textContent = '';
            if (turnstileErr) turnstileErr.textContent = '';

            if (loginAuthMode === 'email_code') {
                await sendLoginEmailCode();
                return true;
            }

            if (turnstilePublicConfig.enabled && !turnstileToken) {
                if (turnstileErr) turnstileErr.textContent = '请先完成人机验证';
                updateLoginActionState();
                return false;
            }

            const preflight = await runIpPreflight();
            if (!preflight.allowed) {
                updateLoginActionState();
                return false;
            }
            await new Promise(r => setTimeout(r, 800));
            closeIpPreflightModal();

            const res = await fetch('/admin/login/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(getPasswordLoginPayload())
            });
            const data = await parseJsonSafe(res);
            if (!res.ok || !data.success) {
                const reason = String(data.message || `登录失败（HTTP ${res.status || '-'}）`);
                if (err) err.textContent = reason;
                showLoginFailModal(reason);
                resetPendingLoginState();
                resetLoginTurnstile();
                return false;
            }

            if (data.requires_email_code) {
                pendingLoginId = String(data.pending_login_id || '');
                pendingLoginEmailMasked = String(data.email_masked || '');
                const hintEl = document.getElementById('loginEmailHint');
                if (hintEl) hintEl.textContent = `请点击“发送邮箱验证码”，验证码将发送到 ${pendingLoginEmailMasked || '已绑定邮箱'}。`;
                updateLoginActionState();
                return true;
            }

            if (data.last_login_at || data.last_login_ip || data.current_login_ip) {
                showLastLoginToast(getLoginDisplayName(), data.last_login_at, data.last_login_ip, data.current_login_at, data.current_login_ip);
            }
            await checkLoginStatus();
            return true;
        }

        async function sendLoginEmailCode() {
            const err = document.getElementById('loginError');
            const turnstileErr = document.getElementById('loginTurnstileError');
            if (err) err.textContent = '';
            if (turnstileErr) turnstileErr.textContent = '';
            const sendBtn = document.getElementById('loginSendCodeBtn');
            if (sendBtn) sendBtn.disabled = true;
            try {
                if (!pendingLoginId) {
                    if (loginAuthMode !== 'email_code') {
                        if (err) err.textContent = '请先完成账号密码验证，再发送邮箱验证码。';
                        updateLoginActionState();
                        return;
                    }
                    const email = getLoginEmailValue();
                    if (!email) {
                        if (err) err.textContent = '请输入已验证安全邮箱。';
                        updateLoginActionState();
                        return;
                    }
                    if (turnstilePublicConfig.enabled && !turnstileToken) {
                        if (turnstileErr) turnstileErr.textContent = '请先完成人机验证';
                        updateLoginActionState();
                        return;
                    }
                    const preflight = await runIpPreflight();
                    if (!preflight.allowed) {
                        updateLoginActionState();
                        return;
                    }
                    await new Promise(r => setTimeout(r, 800));
                    closeIpPreflightModal();

                    const startRes = await fetch('/admin/login/email-code/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, turnstileToken: turnstileToken })
                    });
                    const startData = await parseJsonSafe(startRes);
                    if (!startRes.ok || !startData.success) {
                        const reason = String(startData.message || `发送失败（HTTP ${startRes.status || '-'}）`);
                        if (err) err.textContent = reason;
                        showLoginFailModal(reason);
                        resetPendingLoginState();
                        resetLoginTurnstile();
                        return;
                    }
                    pendingLoginId = String(startData.pending_login_id || '');
                    pendingLoginEmailMasked = String(startData.email_masked || '');
                    const hintEl = document.getElementById('loginEmailHint');
                    if (hintEl) hintEl.textContent = `验证码已发送到 ${pendingLoginEmailMasked || '已验证邮箱'}。`;
                    startLoginCodeTimer(Number(startData.resend_after || 60));
                    return;
                }
                const res = await fetch('/admin/login/send-email-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pending_login_id: pendingLoginId })
                });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    const reason = String(data.message || `发送失败（HTTP ${res.status || '-'}）`);
                    if (err) err.textContent = reason;
                    showLoginFailModal(reason);
                    if (res.status === 401) resetPendingLoginState();
                    updateLoginActionState();
                    return;
                }
                const hintEl = document.getElementById('loginEmailHint');
                if (hintEl) hintEl.textContent = `验证码已发送到 ${String(data.email_masked || pendingLoginEmailMasked || '已绑定邮箱')}。`;
                startLoginCodeTimer(Number(data.resend_after || 60));
            } catch (e) {
                const reason = '网络错误，请检查连接后重试。';
                if (err) err.textContent = reason;
                showLoginFailModal(reason);
                updateLoginActionState();
            }
        }

        async function verifyLoginEmailCode() {
            const err = document.getElementById('loginError');
            if (err) err.textContent = '';
            if (!pendingLoginId) {
                if (err) err.textContent = '请先发送邮箱验证码。';
                return;
            }
            const code = String(document.getElementById('loginEmailCode')?.value || '').trim();
            if (!code) {
                if (err) err.textContent = '请输入邮箱验证码。';
                return;
            }
            setLoginSubmitState(true, '验证中...');
            try {
                const res = await fetch('/admin/login/verify-email-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pending_login_id: pendingLoginId, code })
                });
                const data = await parseJsonSafe(res);
                if (res.ok && data.success) {
                    if (data.last_login_at || data.last_login_ip || data.current_login_ip) {
                        showLastLoginToast(getLoginDisplayName(), data.last_login_at, data.last_login_ip, data.current_login_at, data.current_login_ip);
                    }
                    resetPendingLoginState();
                    await checkLoginStatus();
                    return;
                }
                const reason = String(data.message || `验证失败（HTTP ${res.status || '-'}）`);
                if (err) err.textContent = reason;
                showLoginFailModal(reason);
            } catch (e) {
                const reason = '网络错误，请检查连接后重试。';
                if (err) err.textContent = reason;
                showLoginFailModal(reason);
            } finally {
                updateLoginActionState();
            }
        }

        const loginSendCodeBtn = document.getElementById('loginSendCodeBtn');
        if (loginSendCodeBtn && loginSendCodeBtn.dataset.bound !== '1') {
            loginSendCodeBtn.dataset.bound = '1';
            loginSendCodeBtn.addEventListener('click', async () => {
                await sendLoginEmailCode();
            });
        }

        document.querySelectorAll('[data-login-mode]').forEach((btn) => {
            if (btn.dataset.bound === '1') return;
            btn.dataset.bound = '1';
            btn.addEventListener('click', () => {
                const nextMode = String(btn.dataset.loginMode || '').trim();
                const err = document.getElementById('loginError');
                const turnstileErr = document.getElementById('loginTurnstileError');
                if (err) err.textContent = '';
                if (turnstileErr) turnstileErr.textContent = '';
                setLoginAuthMode(nextMode);
            });
        });

        setLoginAuthMode('email_code', { keepPending: true });

        const loginForm = document.getElementById('loginForm');
        if (loginForm && loginForm.dataset.loginBound !== '1') {
            loginForm.dataset.loginBound = '1';
            loginForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (emailAuthAdminConfig.email_auth_enabled && pendingLoginId) {
                    await verifyLoginEmailCode();
                } else {
                    await handleLoginStart();
                }
            });
        }

        async function logout() {
            if (!await showGlobalConfirm('确定要退出登录吗？')) return;
            closeAccountMenu();
            if (adminSessionCheckTimer) {
                clearInterval(adminSessionCheckTimer);
                adminSessionCheckTimer = null;
            }
            await fetch('/admin/logout', { method: 'POST' });
            location.reload();
        }

        function startAdminSessionWatcher() {
            if (adminSessionCheckTimer) return;
            adminSessionCheckTimer = setInterval(async () => {
                try {
                    const res = await fetch('/admin/check', { cache: 'no-store' });
                    const data = await parseJsonSafe(res);
                    if (!data.logged_in) {
                        clearInterval(adminSessionCheckTimer);
                        adminSessionCheckTimer = null;
                        location.reload();
                    } else {
                        setAdminAuthFromCheck(data);
                        applySidebarPermissions();
                        syncSubAccountManageVisibility();
                        refreshMessagesUnreadIndicator();
                        if (bindingRequiredState) {
                            switchView('settings');
                        }
                    }
                } catch (_) {
                    // Network errors are ignored here; next interval will retry.
                }
            }, 60 * 1000);
        }

        function closeLastLoginToast() {
            const toast = document.getElementById('lastLoginToast');
            if (toast) {
                toast.classList.add('hidden');
            }
            localStorage.setItem('lastLoginToastShown', '1');
        }

        function getGreeting() {
            const hour = new Date().getHours();
            if (hour < 6) return { text: '凌晨好', emoji: '🌙' };
            if (hour < 9) return { text: '早上好', emoji: '☀️' };
            if (hour < 12) return { text: '上午好', emoji: '☀️' };
            if (hour < 14) return { text: '中午好', emoji: '☀️' };
            if (hour < 18) return { text: '下午好', emoji: '☕️' };
            if (hour < 22) return { text: '晚上好', emoji: '🌙' };
            return { text: '夜里好', emoji: '🌙' };
        }

        function formatLoginTime(isoString) {
            if (!isoString) return '-';
            try {
                const match = isoString.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
                if (match) {
                    const [_, year, month, day, hour, minute, second] = match;
                    const pad = (n) => String(n).padStart(2, '0');
                    return `${year}-${pad(month)}-${pad(day)} ${pad(hour)}:${pad(minute)}:${pad(second)}`;
                }
                return isoString;
            } catch (e) {
                return isoString;
            }
        }

        function showLastLoginToast(username, lastLoginAt, lastLoginIP, currentLoginAt, currentLoginIP) {
            const toast = document.getElementById('lastLoginToast');
            if (!toast) return;

            const currentTimeEl = document.getElementById('currentLoginTime');
            const currentIPEl = document.getElementById('currentLoginIP');
            const lastTimeEl = document.getElementById('lastLoginTime');
            const lastIPEl = document.getElementById('lastLoginIP');
            const greetingEl = document.getElementById('greetingText');

            if (currentTimeEl) {
                if (currentLoginAt) {
                    currentTimeEl.textContent = formatLoginTime(currentLoginAt);
                } else {
                    const now = new Date();
                    const nowLocal = new Date(now.getTime() + 8 * 60 * 60 * 1000);
                    currentTimeEl.textContent = nowLocal.toLocaleString('zh-CN', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false
                    });
                }
            }

            if (currentIPEl) {
                currentIPEl.textContent = currentLoginIP || '-';
            }

            if (lastTimeEl) {
                lastTimeEl.textContent = formatLoginTime(lastLoginAt);
            }

            if (lastIPEl) {
                lastIPEl.textContent = lastLoginIP || '首次登录';
            }

            if (greetingEl) {
                const greeting = getGreeting();
                greetingEl.textContent = username + '，' + greeting.text + '！' + greeting.emoji;
            }

            toast.classList.remove('hidden');
        }

        function showDashboard() {
            document.getElementById('loginPage').style.display = 'none';
            document.getElementById('dashboard').style.display = 'flex';
            syncSidebarModeForViewport();
            initResponsiveTableLabels();
            queueResponsiveTableLabels();
            applySidebarPermissions();
            syncSubAccountManageVisibility();
            startAdminSessionWatcher();
            refreshMessagesUnreadIndicator();
            switchView(bindingRequiredState ? 'settings' : getPreferredInitialView());
        }

        const TAB_GUIDES = {
            'product-tab-industries': '设置说明：先定义领域分类名称，再勾选每个产品所属领域；分类与勾选都会自动保存。',
            'product-tab-add': '设置说明：本页为“产品列表”管理，可在下方设置卡片标题/图片/摘要与显示状态。',
            'product-tab-ai': '设置说明：先填写资料并点击“AI 生成完整HTML”，确认源码后点击“保存为产品页面文件”。',
            'bio-product-tab-add': '设置说明：本页为“生物传感产品列表”管理，可设置卡片标题/图片/摘要与显示状态。',
            'bio-product-tab-ai': '设置说明：先填写资料并点击“AI 生成完整HTML”，确认源码后点击“保存为产品页面文件”。',
            'bio-product-tab-manual-edit': '设置说明：选择生物产品后可直接编辑页面区块内容，保存后对应产品页立即更新。',
            'bio-product-tab-industries': '设置说明：先定义生物产品领域分类，再勾选每个产品所属领域；分类与勾选都会自动保存。',
            'view-bio-products': '设置说明：管理生物传感产品展示与筛选分类，前台 /pages/biosensing/?filter=xxx 会按本页配置展示。',
            'view-hydrogen-solutions': '设置说明：为氢能源产业链、智慧电力安全、工业检漏监测、储能锂电池热失控预警、环境气体监测等方案分别设置 1-4 个“相关产品”，保存后对应前台方案页会按方案展示。',
            'view-site-reports': '设置说明：本页展示网站基础统计、完整分析报表、中国按省/海外按洲地图与历史登录日志；可切换时间范围查看趋势、来源、设备、页面与行为事件。',
            'home-tab-hero': '设置说明：用于管理官网首页轮播，支持上传和 CDN；调整顺序后保存即可生效。',
            'home-tab-partners': '设置说明：用于管理合作伙伴徽标，支持上传与链接，拖拽可调整展示顺序。',
            'home-tab-news': '设置说明：选择首页展示的 3 条资讯，保存后首页资讯区会同步更新。',
            'home-tab-products': '设置说明：选择首页产品展示位的 3 个产品，保存后首页模块立即按此展示。',
            'home-tab-solutions': '设置说明：选择首页解决方案展示位，支持替换为你指定的方案卡片。',
            'h2-home-tab-video': '设置说明：配置氢气首页首屏视频链接与顺序，保存后用于页面轮播播放。',
            'h2-home-tab-products': '设置说明：设置氢气首页默认展示产品（未选择分类时显示）。',
            'h2-home-tab-measurement-objects': '设置说明：为测量对象页面分别指定推荐产品，保存后 /pages/measurement 下对应页面底部同步更新。',
            'h2-home-tab-cases': '设置说明：设置氢气首页案例位，支持为每个案例自定义主副标题。',
            'h2-home-tab-news': '设置说明：设置氢气首页最近动态，支持自定义标签、标题和摘要。',
            'h2-home-tab-navbar': '设置说明：集中管理导航栏巨幕菜单（产品列表预览、新品推荐、测量对象）；链接支持 http(s) 和相对路径。',
            'chatbot-tab-config': '设置说明：配置智能客服接口参数与模型，保存后前台客服将按此配置运行。',
            'chatbot-tab-product-ai': '设置说明：配置“产品页编程 AI”接口参数和系统提示词，供气体传感产品与生物传感产品的 AI 自动上架流程调用。',
            'chatbot-tab-knowledge': '设置说明：上传和管理知识库文件，智能客服将优先参考这些资料回答。',
            'chatbot-tab-history': '设置说明：本页按时间倒序记录前台智能客服的逐条问答，可查看会话、页面、提问与回复全文。'
        };

        function getTabGuideElement(tabEl) {
            if (!tabEl) return null;
            const first = tabEl.firstElementChild;
            if (first && first.classList.contains('tab-guide')) return first;
            return null;
        }

        function renderTabGuide(tabEl) {
            if (!tabEl || !tabEl.id) return;
            const text = TAB_GUIDES[tabEl.id];
            const existing = getTabGuideElement(tabEl);

            if (!text) {
                if (existing) existing.remove();
                return;
            }

            if (existing) {
                existing.textContent = text;
                return;
            }

            const guide = document.createElement('div');
            guide.className = 'card tab-guide';
            guide.textContent = text;
            tabEl.insertBefore(guide, tabEl.firstChild);
        }

        function renderGuidesForView(viewName) {
            const view = document.getElementById(`view-${viewName}`);
            if (!view) return;
            view.querySelectorAll('.tab-content.active').forEach(tabEl => renderTabGuide(tabEl));
        }

        function renderChangelog(payload) {
            const versionEl = document.getElementById('changelogVersion');
            const buildTimeEl = document.getElementById('changelogBuildTime');
            const updatesEl = document.getElementById('changelogUpdates');
            const countEl = document.getElementById('changelogCountBadge');
            if (!versionEl || !buildTimeEl || !updatesEl) return;

            const data = (payload && typeof payload === 'object') ? payload : {};
            const historyRaw = Array.isArray(data.history) ? data.history : [];
            const history = historyRaw
                .map((entry) => {
                    const item = (entry && typeof entry === 'object') ? entry : {};
                    const updates = Array.isArray(item.updates) ? item.updates : [];
                    const normalizedUpdates = updates
                        .map(text => String(text || '').trim())
                        .filter(Boolean);
                    return {
                        version: String(item.version || '').trim(),
                        build_time: String(item.build_time || '').trim(),
                        updates: normalizedUpdates
                    };
                })
                .filter(item => item.version || item.build_time || item.updates.length);

            if (!history.length) {
                const fallbackUpdates = Array.isArray(data.updates) ? data.updates : CHANGELOG_FALLBACK.updates;
                history.push({
                    version: String(data.version || CHANGELOG_FALLBACK.version || '').trim(),
                    build_time: String(data.build_time || CHANGELOG_FALLBACK.build_time || '').trim(),
                    updates: fallbackUpdates.map(text => String(text || '').trim()).filter(Boolean)
                });
            }

            const latest = history[0] || { version: '-', build_time: '', updates: [] };
            versionEl.textContent = latest.version || '-';
            buildTimeEl.textContent = formatChangelogTime(latest.build_time) || '-';
            updatesEl.innerHTML = '';

            if (!history.length) {
                const emptyItem = document.createElement('li');
                emptyItem.className = 'changelog-update-empty';
                emptyItem.textContent = '暂无更新记录';
                updatesEl.appendChild(emptyItem);
                if (countEl) countEl.textContent = '0 版';
                return;
            }

            history.forEach((release, index) => {
                const li = document.createElement('li');
                li.className = 'changelog-update-item';

                const number = document.createElement('span');
                number.className = 'changelog-update-index';
                number.textContent = String(index + 1).padStart(2, '0');

                const body = document.createElement('div');
                body.className = 'changelog-update-text';

                const head = document.createElement('div');
                head.className = 'changelog-update-head';
                const showVersion = release.version || `v${index + 1}`;
                const showTime = formatChangelogTime(release.build_time);
                head.textContent = showTime && showTime !== '-'
                    ? `${showVersion} · ${showTime}`
                    : showVersion;

                const detail = document.createElement('div');
                detail.className = 'changelog-update-detail';
                const detailLines = release.updates.length ? release.updates : ['暂无更新内容'];
                detail.textContent = detailLines.map(line => `• ${line}`).join('\n');

                body.appendChild(head);
                body.appendChild(detail);

                li.appendChild(number);
                li.appendChild(body);
                updatesEl.appendChild(li);
            });

            if (countEl) countEl.textContent = `${history.length} 版`;
        }

        function setChangelogLoading(isLoading) {
            const btn = document.getElementById('changelogRefreshBtn');
            if (!btn) return;
            btn.disabled = !!isLoading;
            btn.innerHTML = isLoading
                ? '<i class="fas fa-sync-alt fa-spin"></i> 刷新中...'
                : '<i class="fas fa-sync-alt"></i> 刷新日志';
        }

        async function loadChangelog(manual = false) {
            if (!manual) renderChangelog(CHANGELOG_FALLBACK);
            setChangelogLoading(true);
            try {
                const res = await fetch('/api/admin/changelog', { cache: 'no-store' });
                if (!res.ok) return;
                const data = await res.json();
                renderChangelog(data);
            } catch (err) {
                console.warn('Load changelog failed:', err);
            } finally {
                setChangelogLoading(false);
            }
        }

        let dockerLogsData = null;

        function switchDockerLogsTab(tabName) {
            document.querySelectorAll('.docker-logs-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.tab === tabName);
            });
            document.getElementById('dockerLogsContent1').classList.toggle('active', tabName === 'container1');
            document.getElementById('dockerLogsContent2').classList.toggle('active', tabName === 'container2');
        }

        function setDockerLogsLoading(isLoading) {
            const btn = document.getElementById('dockerLogsRefreshBtn');
            if (!btn) return;
            btn.disabled = !!isLoading;
            btn.innerHTML = isLoading
                ? '<i class="fas fa-sync-alt fa-spin"></i> 刷新中...'
                : '<i class="fas fa-sync-alt"></i> 刷新日志';
        }

        function renderDockerLogs(data) {
            if (!data) return;
            dockerLogsData = data;

            const container1 = data.container1 || {};
            const container2 = data.container2 || {};
            const singleContainer = !!data.single_container;

            const tab1Label = document.getElementById('dockerLogsTab1Label');
            const tab2Label = document.getElementById('dockerLogsTab2Label');
            if (tab1Label) tab1Label.textContent = container1.name || '应用服务';
            if (tab2Label) tab2Label.textContent = container2.name || 'Nginx 服务';
            const tab2 = document.querySelector('.docker-logs-tab[data-tab="container2"]');
            const content2 = document.getElementById('dockerLogsContent2');
            if (tab2) tab2.hidden = singleContainer;
            if (content2) content2.hidden = singleContainer;
            if (singleContainer) switchDockerLogsTab('container1');

            const title1 = document.getElementById('dockerLogsTitle1');
            const title2 = document.getElementById('dockerLogsTitle2');
            if (title1) title1.textContent = `${container1.name || '应用服务'} 日志`;
            if (title2) title2.textContent = `${container2.name || 'Nginx 服务'} 日志`;

            renderDockerLogContent('1', container1.logs || '暂无日志');
            if (!singleContainer) renderDockerLogContent('2', container2.logs || '暂无日志');
            updateDockerLogsFilterInfo();
        }

        function renderDockerLogContent(num, logs) {
            const output = document.getElementById(`dockerLogsOutput${num}`);
            const empty = document.getElementById(`dockerLogsEmpty${num}`);
            const body = document.getElementById(`dockerLogsBody${num}`);

            if (!output || !empty || !body) return;

            if (logs && logs !== '暂无日志' && logs !== '日志获取超时' && !logs.startsWith('获取日志失败')) {
                empty.style.display = 'none';
                output.style.display = 'block';
                body.textContent = logs;
                body.scrollTop = body.scrollHeight;
            } else {
                empty.style.display = 'block';
                output.style.display = 'none';
                empty.innerHTML = `<i class="fas fa-info-circle"></i> ${logs || '暂无日志记录'}`;
            }
        }

        function toggleDockerLogsErrorFilter() {
            const toggle = document.getElementById('dockerLogsErrorToggle');
            if (toggle) {
                toggle.classList.toggle('active');
                applyDockerLogsFilter();
            }
        }

        function applyDockerLogsFilter() {
            if (!dockerLogsData) return;
            const dateFilter = document.getElementById('dockerLogsDateFilter')?.value;
            const errorOnly = document.getElementById('dockerLogsErrorToggle')?.classList.contains('active');
            
            const container1 = dockerLogsData.container1 || {};
            const container2 = dockerLogsData.container2 || {};
            const singleContainer = !!dockerLogsData.single_container;
            
            let logs1 = container1.logs || '';
            let logs2 = container2.logs || '';
            
            if (errorOnly) {
                logs1 = filterErrorLogs(logs1);
                logs2 = filterErrorLogs(logs2);
            }
            
            if (dateFilter) {
                logs1 = filterLogsByDate(logs1, dateFilter);
                logs2 = filterLogsByDate(logs2, dateFilter);
            }
            
            renderDockerLogContent('1', logs1 || '暂无日志');
            if (!singleContainer) renderDockerLogContent('2', logs2 || '暂无日志');
            updateDockerLogsFilterInfo();
        }

        function filterErrorLogs(logs) {
            if (!logs) return '';
            const lines = logs.split('\n');
            const errorPatterns = [
                /\b(ERROR|FATAL|CRITICAL|Exception|Traceback|Error)\b/i,
                /\b\d{4}-\d{2}-\d{2}.*\[(ERROR|FATAL|WARNING)\]/i
            ];
            return lines.filter(line => errorPatterns.some(p => p.test(line))).join('\n');
        }

        function filterLogsByDate(logs, date) {
            if (!logs || !date) return logs;
            const lines = logs.split('\n');
            const datePattern = new RegExp(`^${date.replace(/-/g, '[/-]')}`);
            return lines.filter(line => datePattern.test(line)).join('\n');
        }

        function updateDockerLogsFilterInfo() {
            const dateFilter = document.getElementById('dockerLogsDateFilter')?.value;
            const errorOnly = document.getElementById('dockerLogsErrorToggle')?.classList.contains('active');
            const info = document.getElementById('dockerLogsFilterInfo');
            if (!info) return;
            
            const parts = [];
            if (dateFilter) {
                parts.push(`日期: ${dateFilter}`);
            }
            if (errorOnly) {
                parts.push('仅显示错误日志');
            }
            
            if (parts.length > 0) {
                info.textContent = `筛选条件: ${parts.join(' | ')}`;
                info.classList.add('visible');
            } else {
                info.classList.remove('visible');
            }
        }

        async function clearDockerLogs() {
            if (!confirm('确定要清除所有日志文件吗？此操作不可恢复！')) return;
            
            const btn = document.getElementById('dockerLogsClearBtn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 清除中...';
            }
            
            try {
                const res = await fetch('/api/admin/docker-logs/clear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                const data = await res.json();
                
                if (data.success) {
                    alert('日志已清除');
                    loadDockerLogs(true);
                } else {
                    alert('清除失败: ' + (data.message || '未知错误'));
                }
            } catch (err) {
                alert('清除失败: ' + err.message);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-trash-alt"></i> 清除日志';
                }
            }
        }

        async function loadDockerLogs(manual = false) {
            setDockerLogsLoading(true);
            try {
                const res = await fetch('/api/admin/docker-logs?lines=200', { cache: 'no-store' });
                if (!res.ok) {
                    renderDockerLogs({
                        container1: { name: '应用服务', logs: `请求失败: ${res.status}` },
                        container2: { name: 'Nginx 服务', logs: `请求失败: ${res.status}` }
                    });
                    return;
                }
                const data = await res.json();
                renderDockerLogs(data);
            } catch (err) {
                console.warn('Load docker logs failed:', err);
                renderDockerLogs({
                    container1: { name: '应用服务', logs: `加载失败: ${err.message}` },
                    container2: { name: 'Nginx 服务', logs: `加载失败: ${err.message}` }
                });
            } finally {
                setDockerLogsLoading(false);
            }
        }

        function formatSiteReportNumber(value) {
            const num = Number(value || 0);
            if (!Number.isFinite(num)) return '0';
            return num.toLocaleString('zh-CN');
        }

        function formatSiteReportPercent(value) {
            const num = Number(value || 0);
            if (!Number.isFinite(num)) return '0%';
            return `${num.toFixed(2)}%`;
        }

        function formatSiteReportDuration(seconds) {
            const sec = Math.max(0, Math.round(Number(seconds || 0)));
            if (!sec) return '0秒';
            const h = Math.floor(sec / 3600);
            const m = Math.floor((sec % 3600) / 60);
            const s = sec % 60;
            if (h > 0) return `${h}小时 ${m}分钟`;
            if (m > 0) return `${m}分钟 ${s}秒`;
            return `${s}秒`;
        }

        function getSiteReportOsMeta(rawKey) {
            const key = String(rawKey || '').trim().toLowerCase();
            return SITE_REPORT_OS_META[key] || {
                label: key || '未知',
                icon: 'fas fa-laptop'
            };
        }

        function normalizeProvinceName(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return '';
            const provinceMap = {
                北京: '北京市',
                北京市: '北京市',
                上海: '上海市',
                上海市: '上海市',
                天津: '天津市',
                天津市: '天津市',
                重庆: '重庆市',
                重庆市: '重庆市',
                河北: '河北省',
                河北省: '河北省',
                山西: '山西省',
                山西省: '山西省',
                辽宁: '辽宁省',
                辽宁省: '辽宁省',
                吉林: '吉林省',
                吉林省: '吉林省',
                黑龙江: '黑龙江省',
                黑龙江省: '黑龙江省',
                江苏: '江苏省',
                江苏省: '江苏省',
                浙江: '浙江省',
                浙江省: '浙江省',
                安徽: '安徽省',
                安徽省: '安徽省',
                福建: '福建省',
                福建省: '福建省',
                江西: '江西省',
                江西省: '江西省',
                山东: '山东省',
                山东省: '山东省',
                河南: '河南省',
                河南省: '河南省',
                湖北: '湖北省',
                湖北省: '湖北省',
                湖南: '湖南省',
                湖南省: '湖南省',
                广东: '广东省',
                广东省: '广东省',
                海南: '海南省',
                海南省: '海南省',
                四川: '四川省',
                四川省: '四川省',
                贵州: '贵州省',
                贵州省: '贵州省',
                云南: '云南省',
                云南省: '云南省',
                陕西: '陕西省',
                陕西省: '陕西省',
                甘肃: '甘肃省',
                甘肃省: '甘肃省',
                青海: '青海省',
                青海省: '青海省',
                台湾: '台湾省',
                台湾省: '台湾省',
                内蒙古: '内蒙古自治区',
                内蒙古自治区: '内蒙古自治区',
                广西: '广西壮族自治区',
                广西壮族自治区: '广西壮族自治区',
                西藏: '西藏自治区',
                西藏自治区: '西藏自治区',
                宁夏: '宁夏回族自治区',
                宁夏回族自治区: '宁夏回族自治区',
                新疆: '新疆维吾尔自治区',
                新疆维吾尔自治区: '新疆维吾尔自治区',
                香港: '香港特别行政区',
                香港特别行政区: '香港特别行政区',
                澳门: '澳门特别行政区',
                澳门特别行政区: '澳门特别行政区'
            };
            return provinceMap[value] || value;
        }

        function normalizeCountryName(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return '';
            const countryMap = {
                'China': '中国',
                'United States': '美国',
                'United Kingdom': '英国',
                'Japan': '日本',
                'Germany': '德国',
                'France': '法国',
                'Russia': '俄罗斯',
                'Canada': '加拿大',
                'Australia': '澳大利亚',
                'Brazil': '巴西',
                'India': '印度',
                'South Korea': '韩国',
                'Italy': '意大利',
                'Spain': '西班牙',
                'Mexico': '墨西哥',
                'Netherlands': '荷兰',
                'Singapore': '新加坡',
                'Hong Kong': '香港',
                'Taiwan': '台湾',
                'Macao': '澳门',
                'Turkey': '土耳其',
                'Indonesia': '印度尼西亚',
                'Switzerland': '瑞士',
                'Poland': '波兰',
                'Sweden': '瑞典',
                'Belgium': '比利时',
                'Argentina': '阿根廷',
                'Austria': '奥地利',
                'Norway': '挪威',
                'Israel': '以色列',
                'Ireland': '爱尔兰',
                'Denmark': '丹麦',
                'Finland': '芬兰',
                'Vietnam': '越南',
                'Thailand': '泰国',
                'Malaysia': '马来西亚',
                'Philippines': '菲律宾',
                'Pakistan': '巴基斯坦',
                'Bangladesh': '孟加拉国',
                'Egypt': '埃及',
                'South Africa': '南非',
                'Nigeria': '尼日利亚',
                'Kenya': '肯尼亚',
                'Morocco': '摩洛哥',
                'United Arab Emirates': '阿联酋',
                'Saudi Arabia': '沙特阿拉伯',
                'Iran': '伊朗',
                'Iraq': '伊拉克',
                'Ukraine': '乌克兰',
                'Romania': '罗马尼亚',
                'Czech Republic': '捷克',
                'Portugal': '葡萄牙',
                'Greece': '希腊',
                'Hungary': '匈牙利',
                'Chile': '智利',
                'Colombia': '哥伦比亚',
                'Peru': '秘鲁',
                'New Zealand': '新西兰',
                'Kazakhstan': '哈萨克斯坦',
                'Uzbekistan': '乌兹别克斯坦',
                'Pakistan': '巴基斯坦',
                'Nepal': '尼泊尔',
                'Sri Lanka': '斯里兰卡',
                'Myanmar': '缅甸',
                'Cambodia': '柬埔寨',
                'Laos': '老挝',
                'Mongolia': '蒙古',
                'North Korea': '朝鲜',
                ' Belarus': '白俄罗斯',
                'Slovakia': '斯洛伐克',
                'Bulgaria': '保加利亚',
                'Serbia': '塞尔维亚',
                'Croatia': '克罗地亚',
                'Slovenia': '斯洛文尼亚',
                'Lithuania': '立陶宛',
                'Latvia': '拉脱维亚',
                'Estonia': '爱沙尼亚',
                'Luxembourg': '卢森堡',
                'Iceland': '冰岛',
                'Malta': '马耳他',
                'Cyprus': '塞浦路斯'
            };
            if (countryMap[value]) return countryMap[value];
            return value;
        }

        function getSiteReportMapColor(value, maxValue) {
            const current = Math.max(0, Number(value || 0));
            const max = Math.max(1, Number(maxValue || 0));
            if (!current) return '#e5edf7';
            const ratio = Math.min(1, current / max);
            if (ratio < 0.2) return '#d8e7fb';
            if (ratio < 0.4) return '#b9d3f7';
            if (ratio < 0.6) return '#8fb8f1';
            if (ratio < 0.8) return '#5d95e7';
            return '#2563eb';
        }

        const WORLD_CONTINENT_PANELS = {
            west: {
                containerId: 'worldMapWestContainer',
                ariaLabel: '世界地图西半球访问热度图',
                footnote: '按中国以外访客会话聚合到洲，颜色越深表示热度越高。',
                continents: [
                    {
                        key: 'north-america',
                        label: '北美洲',
                        short: '北美',
                        path: 'M58 66 C73 47 101 41 123 46 C141 51 161 56 172 71 C180 82 178 94 166 102 C157 108 151 120 137 123 C125 126 112 122 100 129 C86 137 67 136 56 124 C46 113 42 96 45 82 C47 75 51 70 58 66 Z',
                        labelX: 110,
                        labelY: 92,
                        valueX: 110,
                        valueY: 107,
                    },
                    {
                        key: 'south-america',
                        label: '南美洲',
                        short: '南美',
                        path: 'M119 149 C134 147 147 154 154 166 C161 177 159 190 153 200 C148 209 146 221 145 234 C143 248 135 263 124 271 C117 276 110 273 107 264 C102 250 98 236 90 224 C84 214 82 201 86 191 C91 177 103 158 119 149 Z',
                        labelX: 118,
                        labelY: 211,
                        valueX: 118,
                        valueY: 226,
                    },
                ],
            },
            east: {
                containerId: 'worldMapEastContainer',
                ariaLabel: '世界地图东半球访问热度图',
                footnote: '按中国以外访客会话聚合到洲，颜色越深表示热度越高。',
                continents: [
                    {
                        key: 'europe',
                        label: '欧洲',
                        short: '欧洲',
                        path: 'M63 70 C70 61 82 57 94 60 C105 63 112 71 112 81 C112 88 104 94 94 94 C84 94 74 90 67 84 C62 80 60 75 63 70 Z',
                        labelX: 89,
                        labelY: 79,
                        valueX: 89,
                        valueY: 94,
                    },
                    {
                        key: 'africa',
                        label: '非洲',
                        short: '非洲',
                        path: 'M86 114 C99 109 114 113 124 124 C132 133 134 146 130 159 C126 174 124 188 118 201 C111 214 98 223 88 218 C79 214 76 202 74 190 C71 174 63 163 63 149 C63 132 71 120 86 114 Z',
                        labelX: 97,
                        labelY: 164,
                        valueX: 97,
                        valueY: 179,
                    },
                    {
                        key: 'asia',
                        label: '亚洲',
                        short: '亚洲',
                        path: 'M116 60 C134 45 165 45 190 53 C207 59 218 74 219 92 C221 107 213 121 199 130 C187 138 179 151 166 159 C151 168 132 169 116 161 C102 154 96 140 94 126 C91 110 95 92 101 79 C104 72 109 66 116 60 Z',
                        labelX: 160,
                        labelY: 107,
                        valueX: 160,
                        valueY: 122,
                    },
                    {
                        key: 'oceania',
                        label: '大洋洲',
                        short: '大洋',
                        path: 'M178 207 C187 201 200 201 208 208 C214 214 214 223 208 228 C201 235 189 238 179 234 C172 231 169 224 171 217 C172 213 174 210 178 207 Z',
                        labelX: 191,
                        labelY: 219,
                        valueX: 191,
                        valueY: 234,
                    },
                ],
            },
        };

        function loadChinaProvinceSvgMarkup() {
            if (!chinaProvinceSvgPromise) {
                chinaProvinceSvgPromise = fetch(CHINA_PROVINCE_SVG_URL, { cache: 'force-cache' })
                    .then((response) => {
                        if (!response.ok) throw new Error(`china svg http ${response.status}`);
                        return response.text();
                    });
            }
            return chinaProvinceSvgPromise;
        }

        function buildHeatMapLegendHtml(footnoteText, tooltipId = '') {
            const tooltipAttr = tooltipId ? ` id="${escapeHtml(tooltipId)}"` : '';
            return `
                <div class="china-map-legend">
                    <span class="china-map-legend-label">低</span>
                    <div class="china-map-legend-bar" aria-hidden="true">
                        <span style="background:#e5edf7"></span>
                        <span style="background:#d8e7fb"></span>
                        <span style="background:#b9d3f7"></span>
                        <span style="background:#8fb8f1"></span>
                        <span style="background:#5d95e7"></span>
                        <span style="background:#2563eb"></span>
                    </div>
                    <span class="china-map-legend-label">高</span>
                </div>
                <div class="china-map-footnote">${escapeHtml(footnoteText)}</div>
                <div class="china-map-tooltip"${tooltipAttr}></div>
            `;
        }

        function buildChinaProvinceMapLegendHtml() {
            return buildHeatMapLegendHtml('按中国省级行政区聚合访问会话数，颜色越深表示热度越高。', 'chinaMapTooltip');
        }

        function ensureChinaProvinceSvgExtraPaths(svgEl) {
            if (!svgEl) return;
            const svgNs = 'http://www.w3.org/2000/svg';
            const svgDoc = svgEl.ownerDocument || document;
            Object.entries(CHINA_PROVINCE_SVG_EXTRA_PATHS).forEach(([pathId, config]) => {
                if (svgEl.querySelector(`[id="${pathId}"]`)) return;
                const pathEl = svgDoc.createElementNS(svgNs, 'path');
                pathEl.setAttribute('id', pathId);
                pathEl.setAttribute('aria-label', config.ariaLabel || pathId);
                pathEl.setAttribute('d', config.d);
                if (config.transform) {
                    pathEl.setAttribute('transform', config.transform);
                }
                pathEl.setAttribute('stroke-linejoin', 'round');
                pathEl.setAttribute('stroke-linecap', 'round');
                svgEl.appendChild(pathEl);
            });
        }

        function bindChinaProvinceMapTooltip(mapWrap) {
            const tooltip = mapWrap.querySelector('#chinaMapTooltip');
            if (!tooltip) return;
            const regions = mapWrap.querySelectorAll('[data-province]');
            regions.forEach((region) => {
                const province = String(region.getAttribute('data-province') || '').trim();
                const sessions = Number(region.getAttribute('data-sessions') || 0);
                const ratio = Number(region.getAttribute('data-ratio') || 0);
                region.addEventListener('mousemove', (event) => {
                    const bounds = mapWrap.getBoundingClientRect();
                    tooltip.textContent = `${province}: ${formatSiteReportNumber(sessions)} 次会话 (${formatSiteReportPercent(ratio)})`;
                    tooltip.style.left = `${event.clientX - bounds.left + 14}px`;
                    tooltip.style.top = `${event.clientY - bounds.top + 14}px`;
                    tooltip.classList.add('visible');
                });
                region.addEventListener('mouseleave', () => {
                    tooltip.classList.remove('visible');
                });
            });
        }

        function bindWorldContinentMapTooltip(mapWrap) {
            const tooltip = mapWrap.querySelector('.china-map-tooltip');
            if (!tooltip) return;
            const regions = mapWrap.querySelectorAll('[data-continent]');
            regions.forEach((region) => {
                const continent = String(region.getAttribute('data-continent') || '').trim();
                const sessions = Number(region.getAttribute('data-sessions') || 0);
                const ratio = Number(region.getAttribute('data-ratio') || 0);
                region.addEventListener('mousemove', (event) => {
                    const bounds = mapWrap.getBoundingClientRect();
                    tooltip.textContent = `${continent}: ${formatSiteReportNumber(sessions)} 次会话 (${formatSiteReportPercent(ratio)})`;
                    tooltip.style.left = `${event.clientX - bounds.left + 14}px`;
                    tooltip.style.top = `${event.clientY - bounds.top + 14}px`;
                    tooltip.classList.add('visible');
                });
                region.addEventListener('mouseleave', () => {
                    tooltip.classList.remove('visible');
                });
            });
        }

        function buildWorldContinentSummaryHtml(continentDefs, continentMap) {
            return `
                <div class="world-map-summary">
                    ${continentDefs.map((continentDef) => {
                        const item = continentMap[continentDef.key] || { sessions: 0, ratio: 0, continent: continentDef.label };
                        return `
                            <div class="world-map-summary-item">
                                <div class="world-map-summary-name">${escapeHtml(continentDef.label)}</div>
                                <div class="world-map-summary-metrics">
                                    <strong>${formatSiteReportNumber(item.sessions)}</strong>
                                    <span>${formatSiteReportPercent(item.ratio)}</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }

        function renderWorldContinentPanel(panelKey, continentMap, maxValue) {
            const panel = WORLD_CONTINENT_PANELS[panelKey];
            if (!panel) return;
            const mapWrap = document.getElementById(panel.containerId);
            if (!mapWrap) return;

            const shapesHtml = panel.continents.map((continentDef) => {
                const item = continentMap[continentDef.key] || { sessions: 0, ratio: 0, continent: continentDef.label };
                const fill = getSiteReportMapColor(item.sessions, maxValue);
                const title = `${continentDef.label}：${formatSiteReportNumber(item.sessions)} 次会话，占比 ${formatSiteReportPercent(item.ratio)}`;
                return `
                    <g class="world-map-continent-group">
                        <path d="${continentDef.path}" fill="${fill}" data-continent="${escapeHtml(continentDef.label)}" data-sessions="${item.sessions}" data-ratio="${Number(item.ratio || 0).toFixed(2)}">
                            <title>${escapeHtml(title)}</title>
                        </path>
                        <text class="world-map-label" x="${continentDef.labelX}" y="${continentDef.labelY}" text-anchor="middle">${escapeHtml(continentDef.short)}</text>
                        <text class="world-map-value" x="${continentDef.valueX}" y="${continentDef.valueY}" text-anchor="middle">${escapeHtml(formatSiteReportNumber(item.sessions))}</text>
                    </g>
                `;
            }).join('');

            mapWrap.innerHTML = `
                <svg class="world-map-svg" viewBox="0 0 260 280" role="img" aria-label="${panel.ariaLabel}">
                    <ellipse class="world-map-globe-bg" cx="130" cy="140" rx="108" ry="122"></ellipse>
                    <ellipse class="world-map-globe-guide" cx="130" cy="140" rx="78" ry="122"></ellipse>
                    <ellipse class="world-map-globe-guide" cx="130" cy="140" rx="46" ry="122"></ellipse>
                    <line class="world-map-globe-guide" x1="22" y1="140" x2="238" y2="140"></line>
                    ${shapesHtml}
                </svg>
                ${buildWorldContinentSummaryHtml(panel.continents, continentMap)}
                ${buildHeatMapLegendHtml(panel.footnote)}
            `;
            bindWorldContinentMapTooltip(mapWrap);
        }

        function renderWorldContinentHeatMaps(rawRows) {
            const westWrap = document.getElementById(WORLD_CONTINENT_PANELS.west.containerId);
            const eastWrap = document.getElementById(WORLD_CONTINENT_PANELS.east.containerId);
            if (!westWrap && !eastWrap) return;
            const rows = Array.isArray(rawRows) ? rawRows : [];
            const normalizedRows = rows.map((item) => ({
                key: String(item?.continent_key || '').trim(),
                continent: String(item?.continent || '').trim(),
                sessions: Math.max(0, Number(item?.sessions || 0)),
                ratio: Number(item?.ratio || 0),
            })).filter(item => item.key);

            if (!normalizedRows.length) {
                const noDataHtml = '<div class="china-map-no-data">暂无中国以外地理分布数据</div>';
                if (westWrap) westWrap.innerHTML = noDataHtml;
                if (eastWrap) eastWrap.innerHTML = noDataHtml;
                return;
            }

            const continentMap = {};
            normalizedRows.forEach((item) => {
                continentMap[item.key] = item;
            });
            const maxValue = Math.max(1, ...normalizedRows.map(item => item.sessions));
            renderWorldContinentPanel('west', continentMap, maxValue);
            renderWorldContinentPanel('east', continentMap, maxValue);
        }

        function renderChinaProvinceTileHeatMap(normalizedRows) {
            const mapWrap = document.getElementById('chinaMapContainer');
            if (!mapWrap) return;
            const provinceMap = {};
            normalizedRows.forEach((item) => {
                provinceMap[item.name] = item;
            });

            const maxValue = Math.max(1, ...normalizedRows.map(item => item.sessions));
            const tileWidth = 54;
            const tileHeight = 34;
            const gap = 8;
            const cols = 13;
            const rowsCount = 12;
            const width = cols * tileWidth + (cols - 1) * gap + 24;
            const height = rowsCount * tileHeight + (rowsCount - 1) * gap + 24;

            const tilesHtml = CHINA_PROVINCE_TILES.map((tile) => {
                const item = provinceMap[tile.name] || { sessions: 0, ratio: 0 };
                const tileX = 12 + tile.x * (tileWidth + gap);
                const tileY = 12 + tile.y * (tileHeight + gap);
                const tileW = (tile.w || 1) * tileWidth + Math.max(0, (tile.w || 1) - 1) * gap;
                const fill = getSiteReportMapColor(item.sessions, maxValue);
                const title = `${tile.name}：${formatSiteReportNumber(item.sessions)} 次会话，占比 ${formatSiteReportPercent(item.ratio)}`;
                return `
                    <g class="china-map-province" data-province="${escapeHtml(tile.name)}" data-sessions="${item.sessions}" data-ratio="${Number(item.ratio || 0).toFixed(2)}">
                        <title>${escapeHtml(title)}</title>
                        <rect x="${tileX}" y="${tileY}" width="${tileW}" height="${tileHeight}" rx="10" ry="10" fill="${fill}" data-province="${escapeHtml(tile.name)}"></rect>
                        <text class="china-map-tile-label" x="${(tileX + tileW / 2).toFixed(2)}" y="${(tileY + tileHeight / 2 + 3).toFixed(2)}" text-anchor="middle">${escapeHtml(tile.short)}</text>
                    </g>
                `;
            }).join('');

            mapWrap.innerHTML = `
                <svg class="china-map-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="中国省份访问热度图">
                    ${tilesHtml}
                </svg>
                ${buildChinaProvinceMapLegendHtml()}
            `;

            bindChinaProvinceMapTooltip(mapWrap);
        }

        function renderChinaProvinceHeatMap(rawRows) {
            const mapWrap = document.getElementById('chinaMapContainer');
            if (!mapWrap) return;
            const rows = Array.isArray(rawRows) ? rawRows : [];
            const normalizedRows = rows.map((item) => ({
                name: normalizeProvinceName(item?.province || item?.name || ''),
                sessions: Math.max(0, Number(item?.sessions || item?.value || 0)),
                ratio: Number(item?.ratio || 0)
            })).filter(item => item.name);

            if (!normalizedRows.length) {
                mapWrap.innerHTML = '<div class="china-map-no-data">暂无地理分布数据</div>';
                return;
            }

            const provinceMap = {};
            normalizedRows.forEach((item) => {
                provinceMap[item.name] = item;
            });
            const maxValue = Math.max(1, ...normalizedRows.map(item => item.sessions));
            const renderToken = ++chinaProvinceMapRenderToken;

            mapWrap.innerHTML = '<div class="china-map-no-data">中国地图加载中...</div>';

            loadChinaProvinceSvgMarkup()
                .then((svgMarkup) => {
                    if (renderToken !== chinaProvinceMapRenderToken) return;
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(svgMarkup, 'image/svg+xml');
                    const svgEl = doc.documentElement;
                    if (!svgEl || String(svgEl.nodeName || '').toLowerCase() !== 'svg') {
                        throw new Error('invalid china svg');
                    }
                    svgEl.classList.add('china-map-svg', 'is-outline');
                    svgEl.setAttribute('role', 'img');
                    svgEl.setAttribute('aria-label', '中国省份访问热度图');
                    ensureChinaProvinceSvgExtraPaths(svgEl);

                    let matchedCount = 0;
                    Object.entries(CHINA_PROVINCE_SVG_IDS).forEach(([provinceName, pathId]) => {
                        const pathEl = svgEl.querySelector(`[id="${pathId}"]`);
                        if (!pathEl) return;
                        matchedCount += 1;
                        const item = provinceMap[provinceName] || { sessions: 0, ratio: 0 };
                        pathEl.setAttribute('fill', getSiteReportMapColor(item.sessions, maxValue));
                        pathEl.setAttribute('data-province', provinceName);
                        pathEl.setAttribute('data-sessions', String(item.sessions));
                        pathEl.setAttribute('data-ratio', Number(item.ratio || 0).toFixed(2));
                        pathEl.setAttribute('vector-effect', 'non-scaling-stroke');
                    });

                    if (!matchedCount) {
                        throw new Error('no province paths matched');
                    }

                    mapWrap.innerHTML = '';
                    mapWrap.appendChild(svgEl);
                    mapWrap.insertAdjacentHTML('beforeend', buildChinaProvinceMapLegendHtml());
                    bindChinaProvinceMapTooltip(mapWrap);
                })
                .catch((error) => {
                    console.warn('Render china svg map failed, fallback to tile map:', error);
                    if (renderToken !== chinaProvinceMapRenderToken) return;
                    renderChinaProvinceTileHeatMap(normalizedRows);
                });
        }

        const SITE_REPORT_METRIC_HELP = {
            pv: {
                title: '页面浏览量 (PV)',
                meaning: '统计范围内，页面被浏览的总次数；同一访客重复浏览会重复计数。',
                formula: 'PV = pageview 事件总数（按时间范围过滤）'
            },
            uv: {
                title: '独立访客 (UV)',
                meaning: '统计范围内，去重后的访客数量（按 visitor_id 去重）。',
                formula: 'UV = 去重(visitor_id) 计数'
            },
            sessions: {
                title: '会话数',
                meaning: '统计范围内，至少产生 1 次页面浏览的会话数量。',
                formula: '会话数 = 去重(session_id 且 pageview>=1) 计数'
            },
            avg_session_duration: {
                title: '平均会话时长',
                meaning: '每个会话的停留时长平均值，反映访问深度。',
                formula: '平均会话时长 = 所有会话时长之和 / 会话数；单会话时长取 max(最后事件时间-首次事件时间, session_end 上报时长)'
            },
            bounce_rate: {
                title: '跳出率',
                meaning: '只看了 1 个页面就离开的会话占比。',
                formula: '跳出率 = (pageview<=1 的会话数 / 会话总数) × 100%'
            },
            conversion_events: {
                title: '转化事件',
                meaning: '统计范围内记录到的转化总次数，按“次数”累计，不按“人数”去重。',
                formula: '转化事件 = 转化类事件次数 + 转化页面命中次数（按会话累计）',
                scope: '当前系统会把 contact_submit、quote_request、request_demo、download_brochure，以及所有以 conversion_ 开头的事件计为转化；同时，页面路径包含 /thank-you、/thanks、/success、/submitted、/done 也会额外计为转化页命中。',
                example: '例如 1 个访客在同一会话里提交表单 1 次、下载资料 1 次，又跳转到 thank-you 页面，那么这次访问可能累计 3 次转化事件。',
                note: '所以“转化事件”通常会大于或等于“发生过转化的会话数”，它更适合看总转化动作量，而不等于实际成交人数或提交人数。'
            },
            conversion_rate: {
                title: '转化率',
                meaning: '发生过至少 1 次转化的会话，占总会话的比例；这里按“会话”统计，不按“访客人数”统计。',
                formula: '转化率 = (发生过 >=1 次转化的会话数 / 会话总数) × 100%',
                scope: '一个会话里即使发生了多次转化，转化率分子也只记 1 次；只有至少浏览过 1 个页面的会话才会进入总会话统计。',
                example: '例如共有 100 个会话，其中 8 个会话至少发生过 1 次转化；即使这 8 个会话总共产生了 15 次转化事件，转化率仍然是 8%。',
                note: '因此转化率不等于“转化事件 ÷ UV”，也不等于“转化事件 ÷ 会话数”。如果你想看每次访问平均产生多少转化，要单独看转化事件总数。'
            },
            trend: {
                title: '趋势图',
                meaning: '趋势图用于观察流量变化，可按年、月、周、天四种粒度聚合 PV 和 UV。',
                formula: '年/月/周/天：按所选粒度聚合 PV/UV；所有桶都仅统计所选起止日期范围内的数据'
            },
            source: {
                title: '来源',
                meaning: '会话来源分类（直接、搜索、社交、外部引荐、投放等）。',
                formula: '依据 UTM 参数与 referrer 域名规则归类'
            },
            source_sessions: {
                title: '来源-会话数',
                meaning: '每个来源分类对应的会话数量。',
                formula: '会话数 = 该来源分类下去重(session_id) 计数'
            },
            source_ratio: {
                title: '来源-占比',
                meaning: '每个来源在总会话中的比例。',
                formula: '占比 = 来源会话数 / 总会话数 × 100%'
            },
            device: {
                title: '设备',
                meaning: '终端设备类型分类（桌面、移动、平板）。',
                formula: '根据 User-Agent 关键词规则分类'
            },
            device_sessions: {
                title: '设备-会话数',
                meaning: '每类设备对应的会话数量。',
                formula: '会话数 = 该设备分类下去重(session_id) 计数'
            },
            device_ratio: {
                title: '设备-占比',
                meaning: '每类设备在总会话中的比例。',
                formula: '占比 = 设备会话数 / 总会话数 × 100%'
            },
            os: {
                title: '操作系统',
                meaning: '按访客终端操作系统聚合，例如 Windows、macOS、iOS、安卓、鸿蒙。',
                formula: '根据 User-Agent 关键词规则分类后，按会话聚合'
            },
            os_sessions: {
                title: '系统-会话数',
                meaning: '每类操作系统对应的会话数量。',
                formula: '会话数 = 该系统下去重(session_id) 计数'
            },
            os_ratio: {
                title: '系统-占比',
                meaning: '每类操作系统在总会话中的比例。',
                formula: '占比 = 系统会话数 / 总会话数 × 100%'
            },
            province: {
                title: '省份',
                meaning: '按访问 IP 解析出的中国省级行政区分布。',
                formula: '根据访客公网 IP 地理位置解析结果聚合到省份'
            },
            province_sessions: {
                title: '省份-会话数',
                meaning: '各省份对应的访问会话数量。',
                formula: '会话数 = 该省份下去重(session_id) 计数'
            },
            province_ratio: {
                title: '省份-占比',
                meaning: '各省份在总会话中的比例。',
                formula: '占比 = 省份会话数 / 总会话数 × 100%'
            },
            page_name: {
                title: 'Top 页面-页面',
                meaning: '被访问最多的页面路径（优先显示页面标题）。',
                formula: '按页面 pageview 数降序排序取 Top N'
            },
            page_pv: {
                title: 'Top 页面-PV',
                meaning: '该页面在统计范围内的浏览总次数。',
                formula: 'PV = 该 page_path 对应 pageview 事件数'
            },
            page_uv: {
                title: 'Top 页面-UV',
                meaning: '访问该页面的独立访客数量。',
                formula: 'UV = 该 page_path 下去重(visitor_id) 计数'
            },
            page_sessions: {
                title: 'Top 页面-会话',
                meaning: '访问该页面的会话数量。',
                formula: '会话 = 该 page_path 下去重(session_id) 计数'
            },
            event_name: {
                title: 'Top 事件-事件名',
                meaning: '行为事件名称（已做中文映射，保留自定义事件）。',
                formula: '来自 event 事件的 event_name 字段'
            },
            event_count: {
                title: 'Top 事件-次数',
                meaning: '该事件在统计范围内的触发总次数。',
                formula: '次数 = event_name 匹配的事件记录数量'
            },
            recent_time: {
                title: '最近事件-时间',
                meaning: '事件发生时间（北京时间）。',
                formula: '由事件时间戳转换为北京时间'
            },
            recent_event: {
                title: '最近事件-事件',
                meaning: '最近触发的事件名称（中文化展示）。',
                formula: '优先使用 event_name；无名称时按事件类型显示'
            },
            recent_path: {
                title: '最近事件-页面',
                meaning: '事件发生时所在的页面路径。',
                formula: '取事件记录中的 page_path 字段'
            }
        };

        function showSiteMetricHelp(metricKey) {
            const key = String(metricKey || '').trim();
            const item = SITE_REPORT_METRIC_HELP[key] || {
                title: '指标说明',
                meaning: '该指标用于辅助理解报表。',
                formula: '按当前报表数据源进行聚合计算'
            };
            const sections = [
                `含义：${item.meaning}`,
                `计算方法：${item.formula}`
            ];
            if (item.scope) sections.push(`统计口径：${item.scope}`);
            if (item.example) sections.push(`示例：${item.example}`);
            if (item.note) sections.push(`注意：${item.note}`);
            const text = sections.join('\n\n');
            showGlobalAlert(text, `${item.title} · 说明`);
        }

        function formatSiteReportEventName(rawName, rawType = '') {
            const name = String(rawName || '').trim().toLowerCase();
            const type = String(rawType || '').trim().toLowerCase();
            const map = {
                page_view: '页面浏览',
                pageview: '页面浏览',
                scroll_depth: '滚动深度',
                engaged_15s: '停留 15 秒',
                engaged_30s: '停留 30 秒',
                engaged_60s: '停留 60 秒',
                click_link: '点击链接',
                click_button: '点击按钮',
                click: '点击',
                contact_submit: '提交联系表单',
                contact_form: '联系表单',
                job_apply: '提交招聘申请',
                job_form: '招聘申请',
                form_submit: '提交表单',
                form_start: '开始填写表单',
                phone_click: '点击电话',
                phone_view: '查看电话',
                email_click: '点击邮箱',
                email_view: '查看邮箱',
                quote_request: '提交询价',
                quote_form: '询价表单',
                request_demo: '提交演示申请',
                demo_form: '演示申请',
                download_brochure: '下载资料',
                download: '下载文件',
                video_play: '播放视频',
                video_pause: '暂停视频',
                video_complete: '看完视频',
                search: '搜索',
                search_submit: '提交搜索',
                add_to_cart: '加入购物车',
                remove_from_cart: '移出购物车',
                checkout: '结算',
                wishlist: '添加收藏',
                share: '分享',
                copy_link: '复制链接',
                print: '打印',
                tab_switch: '切换标签页',
                window_focus: '窗口获得焦点',
                window_blur: '窗口失去焦点',
                scroll_to_bottom: '滚动到底部',
                cta_click: '点击 CTA',
                banner_click: '点击横幅',
                nav_click: '点击导航',
                sidebar_click: '点击侧边栏',
                footer_click: '点击页脚',
                image_view: '查看图片',
                image_zoom: '放大图片',
                map_view: '查看地图',
                session_end: '会话结束',
                product_view: '浏览产品',
                product_click: '点击产品',
                category_view: '浏览分类',
                blog_view: '浏览博客',
                news_view: '浏览资讯',
                video_view: '浏览视频',
                faq_view: '查看 FAQ',
                help_view: '查看帮助',
                login: '登录',
                logout: '退出登录',
                register: '注册',
                subscribe: '订阅',
                unsubscribe: '取消订阅',
                feedback: '提交反馈',
                survey: '填写问卷',
                review: '发表评论',
                print_page: '打印页面'
            };

            if (name && map[name]) return map[name];
            if (name.startsWith('conversion_')) {
                const tail = name.slice('conversion_'.length);
                const tailText = map[tail] || `自定义转化(${tail})`;
                return `转化：${tailText}`;
            }
            if (!name) {
                if (type === 'pageview') return '页面浏览';
                if (type === 'session_end') return '会话结束';
                return '行为事件';
            }
            return `自定义事件(${name})`;
        }

        function getSiteReportGranularityLabel(granularity) {
            const key = String(granularity || '').trim().toLowerCase();
            const labelMap = {
                year: '按年显示',
                month: '按月显示',
                week: '按周显示',
                day: '按天显示',
                hour: '按小时显示'
            };
            return labelMap[key] || '按天显示';
        }

        function getSiteReportTrendTitle(granularity) {
            const key = String(granularity || '').trim().toLowerCase();
            const titleMap = {
                year: '按年趋势',
                month: '按月趋势',
                week: '按周趋势',
                day: '按天趋势',
                hour: '按小时趋势'
            };
            return titleMap[key] || '按天趋势';
        }

        function formatSiteReportTrendFullDate(dateText) {
            const text = String(dateText || '').trim();
            const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
            if (!match) return text;
            return `${match[1]}/${match[2]}/${match[3]}`;
        }

        function formatSiteReportTrendAxisLabel(item, granularity) {
            const key = String(granularity || 'day').trim().toLowerCase();
            const start = String(item?.bucketStart || item?.bucket_start || item?.date || '').trim();
            const end = String(item?.bucketEnd || item?.bucket_end || item?.date || '').trim();
            const label = String(item?.label || item?.date || '').trim();

            if (key === 'week') {
                const startFull = formatSiteReportTrendFullDate(start);
                const endFull = formatSiteReportTrendFullDate(end);
                if (startFull && endFull) return startFull === endFull ? startFull : `${startFull}-${endFull}`;
                return label;
            }
            if (key === 'month') return start ? start.slice(0, 7) : label;
            if (key === 'year') return start ? start.slice(0, 4) : label;
            if (key === 'day') return start ? start.slice(5) : label;
            return label;
        }

        function buildSiteReportTrendYAxis(maxValue, desiredTicks = 4) {
            const safeMax = Math.max(0, Number(maxValue) || 0);
            if (safeMax <= 0) {
                return { max: 1, step: 1, ticks: [1, 0] };
            }

            const targetTicks = Math.max(1, Number(desiredTicks) || 4);
            const rawStep = safeMax / targetTicks;
            const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
            const candidates = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude);
            let step = candidates[0];
            let bestDiff = Infinity;

            candidates.forEach((candidate) => {
                const diff = Math.abs(candidate - rawStep);
                if (diff < bestDiff) {
                    bestDiff = diff;
                    step = candidate;
                }
            });

            const chartMax = Math.ceil(safeMax / step) * step;
            const ticks = [];
            for (let value = chartMax; value > 0; value -= step) {
                ticks.push(value);
            }
            ticks.push(0);
            return { max: chartMax, step, ticks };
        }

        function formatSiteReportTrendTickValue(value) {
            const num = Number(value || 0);
            if (!Number.isFinite(num)) return '0';
            if (Number.isInteger(num)) return formatSiteReportNumber(num);
            return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
        }

        function getBeijingDateString(date = new Date()) {
            const parts = new Intl.DateTimeFormat('en-US', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            }).formatToParts(date);
            const valueMap = {};
            parts.forEach((part) => {
                if (part.type !== 'literal') valueMap[part.type] = part.value;
            });
            return `${valueMap.year || '1970'}-${valueMap.month || '01'}-${valueMap.day || '01'}`;
        }

        function shiftIsoDate(dateText, deltaDays) {
            const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateText || '').trim());
            if (!match) return '';
            const year = Number(match[1]);
            const month = Number(match[2]);
            const day = Number(match[3]);
            const baseTs = Date.UTC(year, month - 1, day);
            const shifted = new Date(baseTs + (Number(deltaDays || 0) * 86400000));
            return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}-${String(shifted.getUTCDate()).padStart(2, '0')}`;
        }

        function isValidIsoDate(dateText) {
            const text = String(dateText || '').trim();
            if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
            const ts = Date.parse(`${text}T00:00:00Z`);
            if (!Number.isFinite(ts)) return false;
            return shiftIsoDate(text, 0) === text;
        }

        function syncSiteReportDateInputLimits() {
            const startEl = document.getElementById('siteReportStartDate');
            const endEl = document.getElementById('siteReportEndDate');
            if (!startEl || !endEl) return;
            startEl.max = String(endEl.value || '').trim();
            endEl.min = String(startEl.value || '').trim();
        }

        function ensureSiteReportFiltersInitialized() {
            const startEl = document.getElementById('siteReportStartDate');
            const endEl = document.getElementById('siteReportEndDate');
            const granularityEl = document.getElementById('siteReportGranularity');
            if (!startEl || !endEl || !granularityEl) return;

            if (!isValidIsoDate(siteReportsEndDate)) {
                siteReportsEndDate = getBeijingDateString();
            }
            if (!isValidIsoDate(siteReportsStartDate)) {
                siteReportsStartDate = shiftIsoDate(siteReportsEndDate, -29);
            }
            if (!siteReportsGranularity) {
                siteReportsGranularity = 'day';
            }

            if (!isValidIsoDate(String(startEl.value || '').trim())) {
                startEl.value = siteReportsStartDate;
            } else {
                siteReportsStartDate = String(startEl.value || '').trim();
            }
            if (!isValidIsoDate(String(endEl.value || '').trim())) {
                endEl.value = siteReportsEndDate;
            } else {
                siteReportsEndDate = String(endEl.value || '').trim();
            }
            const currentGranularity = String(granularityEl.value || '').trim().toLowerCase();
            if (['year', 'month', 'week', 'day'].includes(currentGranularity)) {
                siteReportsGranularity = currentGranularity;
            } else {
                granularityEl.value = siteReportsGranularity;
            }
            syncSiteReportDateInputLimits();
        }

        function updateSiteReportTrendHeading(granularity) {
            const trendWrap = document.getElementById('siteReportTrend');
            const heading = trendWrap ? trendWrap.previousElementSibling : null;
            if (!heading) return;
            const titleText = getSiteReportTrendTitle(granularity);
            const firstNode = heading.firstChild;
            if (firstNode && firstNode.nodeType === Node.TEXT_NODE) {
                firstNode.textContent = titleText;
                return;
            }
            if (firstNode && firstNode.nodeType === Node.ELEMENT_NODE && firstNode.tagName === 'SPAN') {
                firstNode.textContent = titleText;
                return;
            }
            heading.insertBefore(document.createTextNode(titleText), heading.firstChild);
        }

        function setSiteReportsLoading(isLoading) {
            siteReportsLoading = !!isLoading;
            const btn = document.getElementById('siteReportRefreshBtn');
            if (!btn) return;
            btn.disabled = !!isLoading;
            btn.innerHTML = isLoading
                ? '<i class="fas fa-sync-alt fa-spin"></i> 加载中...'
                : '<i class="fas fa-sync-alt"></i> 刷新报表';
        }

        function renderSiteReportKpis(summary) {
            const safe = summary && typeof summary === 'object' ? summary : {};
            const setText = (id, value) => {
                const el = document.getElementById(id);
                if (el) el.textContent = value;
            };
            setText('siteReportPv', formatSiteReportNumber(safe.pageviews));
            setText('siteReportUv', formatSiteReportNumber(safe.unique_visitors));
            setText('siteReportSessions', formatSiteReportNumber(safe.sessions));
            setText('siteReportAvgSession', formatSiteReportDuration(safe.avg_session_duration_sec));
            setText('siteReportBounceRate', formatSiteReportPercent(safe.bounce_rate));
            setText('siteReportConversions', formatSiteReportNumber(safe.conversion_events));
            setText('siteReportConversionRate', formatSiteReportPercent(safe.conversion_rate));
        }

        function renderSiteReportTrend(rows, meta = {}) {
            const wrap = document.getElementById('siteReportTrend');
            if (!wrap) return;
            const granularity = String(meta.granularity || 'day').trim().toLowerCase() || 'day';
            updateSiteReportTrendHeading(granularity);
            const items = Array.isArray(rows) ? rows : [];
            if (!items.length) {
                wrap.innerHTML = '<div class="no-data">暂无趋势数据</div>';
                return;
            }
            const prepared = items.map((item) => ({
                date: String(item?.date || ''),
                label: String(item?.label || item?.date || ''),
                bucketStart: String(item?.bucket_start || item?.date || ''),
                bucketEnd: String(item?.bucket_end || item?.date || ''),
                pv: Math.max(0, Number(item?.pageviews || 0)),
                uv: Math.max(0, Number(item?.unique_visitors || 0)),
                axisLabel: formatSiteReportTrendAxisLabel(item, granularity),
            }));
            const maxValue = Math.max(1, ...prepared.map(item => Math.max(item.pv, item.uv)));
            const yAxis = buildSiteReportTrendYAxis(maxValue, 4);
            const chartMax = Math.max(1, Number(yAxis.max) || 1);

            const height = 340;
            const padding = { left: 52, right: 18, top: 22, bottom: 52 };
            const wrapRect = wrap.getBoundingClientRect ? wrap.getBoundingClientRect() : { width: 0 };
            const wrapStyle = window.getComputedStyle ? window.getComputedStyle(wrap) : null;
            const wrapPaddingX = wrapStyle
                ? ((parseFloat(wrapStyle.paddingLeft) || 0) + (parseFloat(wrapStyle.paddingRight) || 0))
                : 0;
            const availableWidth = Math.max(720, Math.floor((wrapRect.width || wrap.clientWidth || 0) - wrapPaddingX));
            const maxLabelChars = Math.max(5, ...prepared.map(item => (item.axisLabel || item.label || '').length));
            const slotBaseMap = { year: 88, month: 96, week: 190, day: 64, hour: 72 };
            const slotWidth = Math.max(slotBaseMap[granularity] || 72, Math.min(220, (maxLabelChars * 8) + 28));
            const dataWidth = padding.left + padding.right + (Math.max(1, prepared.length - 1) * slotWidth);
            const width = Math.ceil(Math.max(availableWidth, dataWidth));
            const plotWidth = Math.max(1, width - padding.left - padding.right);
            const plotHeight = Math.max(1, height - padding.top - padding.bottom);

            const toX = (idx) => {
                if (prepared.length <= 1) return padding.left + plotWidth / 2;
                return padding.left + (idx / (prepared.length - 1)) * plotWidth;
            };
            const toY = (value) => padding.top + ((chartMax - value) / chartMax) * plotHeight;

            const pvPoints = prepared.map((item, idx) => `${toX(idx).toFixed(2)},${toY(item.pv).toFixed(2)}`).join(' ');
            const uvPoints = prepared.map((item, idx) => `${toX(idx).toFixed(2)},${toY(item.uv).toFixed(2)}`).join(' ');

            const gridLines = [];
            const yTicks = Array.isArray(yAxis.ticks) && yAxis.ticks.length ? yAxis.ticks : [chartMax, 0];
            yTicks.forEach((tickValue) => {
                const y = toY(Number(tickValue) || 0);
                gridLines.push(`<line class="site-report-line-grid" x1="${padding.left}" y1="${y.toFixed(2)}" x2="${(padding.left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}"></line>`);
                gridLines.push(`<text class="site-report-line-y-label" x="${(padding.left - 10).toFixed(2)}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHtml(formatSiteReportTrendTickValue(tickValue))}</text>`);
            });

            const labelStep = prepared.length <= 10 ? 1 : Math.max(1, Math.ceil(prepared.length / 8));
            const xLabels = prepared.map((item, idx) => {
                const isLast = idx === prepared.length - 1;
                const isFirst = idx === 0;
                const shouldShow = isFirst || isLast || (idx % labelStep === 0);
                if (!shouldShow) return '';
                const x = toX(idx);
                const label = item.axisLabel || item.label || item.date;
                return `<text class="site-report-line-label" x="${x.toFixed(2)}" y="${(height - 10).toFixed(2)}" text-anchor="middle">${escapeHtml(label)}</text>`;
            }).join('');

            const drawPoints = prepared.length <= 60;
            const pvDots = drawPoints
                ? prepared.map((item, idx) => `<circle class="site-report-line-point-pv" cx="${toX(idx).toFixed(2)}" cy="${toY(item.pv).toFixed(2)}" r="3.8"></circle>`).join('')
                : '';
            const uvDots = drawPoints
                ? prepared.map((item, idx) => `<circle class="site-report-line-point-uv" cx="${toX(idx).toFixed(2)}" cy="${toY(item.uv).toFixed(2)}" r="3.4"></circle>`).join('')
                : '';

            const lastItem = prepared[prepared.length - 1] || { date: '-', axisLabel: '-', pv: 0, uv: 0 };
            const lastLabel = lastItem.axisLabel || lastItem.label || lastItem.date || '-';
            const summary = `最后一组(${lastLabel})：PV ${formatSiteReportNumber(lastItem.pv)}，UV ${formatSiteReportNumber(lastItem.uv)}`;

            const tooltipId = 'siteReportTrendTooltip';
            wrap.innerHTML = `
                <div class="site-report-line-wrap" style="position:relative;">
                    <svg class="site-report-line-svg" width="${width}" height="${height}" style="width:${width}px;" viewBox="0 0 ${width} ${height}" role="img" aria-label="站点趋势折线图">
                        ${gridLines.join('')}
                        <line class="site-report-line-axis" x1="${padding.left}" y1="${(padding.top + plotHeight).toFixed(2)}" x2="${(padding.left + plotWidth).toFixed(2)}" y2="${(padding.top + plotHeight).toFixed(2)}"></line>
                        <polyline class="site-report-line-pv" points="${pvPoints}"></polyline>
                        <polyline class="site-report-line-uv" points="${uvPoints}"></polyline>
                        ${pvDots}
                        ${uvDots}
                        ${xLabels}
                    </svg>
                    <div id="${tooltipId}" class="site-report-line-tooltip"></div>
                </div>
                <div class="site-report-line-legend">
                    <span class="site-report-line-legend-item"><i class="site-report-line-legend-dot pv"></i>PV</span>
                    <span class="site-report-line-legend-item"><i class="site-report-line-legend-dot uv"></i>UV</span>
                </div>
                <div class="site-report-line-summary">${escapeHtml(summary)}</div>
            `;

            const svg = wrap.querySelector('.site-report-line-svg');
            const tooltip = document.getElementById(tooltipId);

            svg.addEventListener('mousemove', (e) => {
                const lineWrap = svg.closest('.site-report-line-wrap');
                const svgRect = svg.getBoundingClientRect();
                const scaleX = svgRect.width / width;
                const scaleY = svgRect.height / height;
                const mouseX = (e.clientX - svgRect.left) / scaleX;
                let closestIdx = 0;
                let minDist = Infinity;
                prepared.forEach((item, idx) => {
                    const dist = Math.abs(toX(idx) - mouseX);
                    if (dist < minDist) {
                        minDist = dist;
                        closestIdx = idx;
                    }
                });
                const item = prepared[closestIdx];
                const rangeText = (item.bucketStart && item.bucketEnd && item.bucketStart !== item.bucketEnd)
                    ? `${item.bucketStart} 至 ${item.bucketEnd}`
                    : (item.bucketStart || item.bucketEnd || item.date);
                tooltip.innerHTML = `
                    <div class="site-report-line-tooltip-date">${escapeHtml(item.axisLabel || item.label || item.date)}</div>
                    <div class="site-report-line-tooltip-date">${escapeHtml(rangeText)}</div>
                    <div class="site-report-line-tooltip-pv"><span>PV</span><span>${formatSiteReportNumber(item.pv)}</span></div>
                    <div class="site-report-line-tooltip-uv"><span>UV</span><span>${formatSiteReportNumber(item.uv)}</span></div>
                `;
                tooltip.classList.add('visible');
                requestAnimationFrame(() => {
                    const tooltipRect = tooltip.getBoundingClientRect();
                    const tooltipWidth = tooltipRect.width;
                    const tooltipHeight = tooltipRect.height;
                    const scrollLeft = lineWrap ? lineWrap.scrollLeft : 0;
                    const viewportWidth = lineWrap ? lineWrap.clientWidth : svgRect.width;
                    let left = (toX(closestIdx) * scaleX) - (tooltipWidth / 2);
                    const minLeft = scrollLeft + 4;
                    const maxLeft = Math.max(minLeft, scrollLeft + viewportWidth - tooltipWidth - 4);
                    left = Math.max(minLeft, Math.min(left, maxLeft));
                    let top = (toY(item.pv) * scaleY) - tooltipHeight - 8;
                    top = Math.max(0, Math.min(top, svgRect.height - tooltipHeight));
                    tooltip.style.left = `${left}px`;
                    tooltip.style.top = `${top}px`;
                });
            });

            svg.addEventListener('mouseleave', () => {
                tooltip.classList.remove('visible');
            });
        }

        function renderSiteReportRows() {
            const sourceBody = document.getElementById('siteReportSourceBody');
            const deviceBody = document.getElementById('siteReportDeviceBody');
            const osBody = document.getElementById('siteReportOsBody');
            const provinceBody = document.getElementById('siteReportProvinceBody');
            const pagesBody = document.getElementById('siteReportPagesBody');
            const worldWestWrap = document.getElementById('worldMapWestContainer');
            const worldEastWrap = document.getElementById('worldMapEastContainer');
            if (sourceBody) sourceBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无数据</td></tr>';
            if (deviceBody) deviceBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无数据</td></tr>';
            if (osBody) osBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无数据</td></tr>';
            if (provinceBody) provinceBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无数据</td></tr>';
            if (pagesBody) pagesBody.innerHTML = '<tr><td colspan="4" class="no-data">暂无数据</td></tr>';
            const mapWrap = document.getElementById('chinaMapContainer');
            if (mapWrap) mapWrap.innerHTML = '<div class="china-map-no-data">暂无地理分布数据</div>';
            if (worldWestWrap) worldWestWrap.innerHTML = '<div class="china-map-no-data">暂无中国以外地理分布数据</div>';
            if (worldEastWrap) worldEastWrap.innerHTML = '<div class="china-map-no-data">暂无中国以外地理分布数据</div>';
            siteReportEventRowsAll = [];
            siteReportProvinceRowsAll = [];
            siteReportCountryRowsAll = [];
            siteReportRecentRowsAll = [];
            siteReportEventPage = 1;
            siteReportProvincePage = 1;
            siteReportCountryPage = 1;
            siteReportRecentPage = 1;
            renderSiteReportEventTablePage();
            renderSiteReportProvinceTablePage();
            renderSiteReportCountryTablePage();
            renderSiteReportRecentTablePage();
        }

        function updateSiteReportPager(totalRows, pageSize, currentPage, infoEl, prevBtn, nextBtn) {
            const totalPages = totalRows > 0 ? Math.ceil(totalRows / pageSize) : 0;
            const safePage = totalPages > 0 ? Math.min(Math.max(1, currentPage), totalPages) : 0;
            if (infoEl) infoEl.textContent = `第 ${safePage} / ${totalPages} 页`;
            if (prevBtn) prevBtn.disabled = totalPages <= 1 || safePage <= 1;
            if (nextBtn) nextBtn.disabled = totalPages <= 1 || safePage >= totalPages;
            return { totalPages, page: safePage };
        }

        function renderSiteReportEventTablePage() {
            const tbody = document.getElementById('siteReportEventsBody');
            const infoEl = document.getElementById('siteReportEventsPageInfo');
            const prevBtn = document.getElementById('siteReportEventsPrevBtn');
            const nextBtn = document.getElementById('siteReportEventsNextBtn');
            if (!tbody) return;

            const allRows = Array.isArray(siteReportEventRowsAll) ? siteReportEventRowsAll : [];
            const pager = updateSiteReportPager(allRows.length, SITE_REPORT_EVENT_PAGE_SIZE, siteReportEventPage, infoEl, prevBtn, nextBtn);
            if (!pager.totalPages) {
                tbody.innerHTML = '<tr><td colspan="2" class="no-data">暂无事件数据</td></tr>';
                siteReportEventPage = 1;
                return;
            }

            siteReportEventPage = pager.page;
            const start = (siteReportEventPage - 1) * SITE_REPORT_EVENT_PAGE_SIZE;
            const pageRows = allRows.slice(start, start + SITE_REPORT_EVENT_PAGE_SIZE);
            tbody.innerHTML = pageRows.map((item) => {
                const eventName = formatSiteReportEventName(item?.name || '', 'event');
                return `
                    <tr>
                        <td>${escapeHtml(eventName)}</td>
                        <td>${formatSiteReportNumber(item?.count)}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderSiteReportProvinceTablePage() {
            const tbody = document.getElementById('siteReportProvinceBody');
            const infoEl = document.getElementById('siteReportProvincePageInfo');
            const prevBtn = document.getElementById('siteReportProvincePrevBtn');
            const nextBtn = document.getElementById('siteReportProvinceNextBtn');
            if (!tbody) return;

            const allRows = Array.isArray(siteReportProvinceRowsAll) ? siteReportProvinceRowsAll : [];
            const pager = updateSiteReportPager(allRows.length, SITE_REPORT_PROVINCE_PAGE_SIZE, siteReportProvincePage, infoEl, prevBtn, nextBtn);
            if (!pager.totalPages) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">暂无省份数据</td></tr>';
                siteReportProvincePage = 1;
                return;
            }

            siteReportProvincePage = pager.page;
            const start = (siteReportProvincePage - 1) * SITE_REPORT_PROVINCE_PAGE_SIZE;
            const pageRows = allRows.slice(start, start + SITE_REPORT_PROVINCE_PAGE_SIZE);
            tbody.innerHTML = pageRows.map((item) => {
                const provinceName = normalizeProvinceName(item?.province || '');
                return `
                    <tr>
                        <td>${escapeHtml(provinceName || '未知')}</td>
                        <td>${formatSiteReportNumber(item?.sessions)}</td>
                        <td>${formatSiteReportPercent(item?.ratio)}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderSiteReportCountryTablePage() {
            const tbody = document.getElementById('siteReportCountryBody');
            const infoEl = document.getElementById('siteReportCountryPageInfo');
            const prevBtn = document.getElementById('siteReportCountryPrevBtn');
            const nextBtn = document.getElementById('siteReportCountryNextBtn');
            if (!tbody) return;

            const allRows = Array.isArray(siteReportCountryRowsAll) ? siteReportCountryRowsAll : [];
            const pager = updateSiteReportPager(allRows.length, SITE_REPORT_COUNTRY_PAGE_SIZE, siteReportCountryPage, infoEl, prevBtn, nextBtn);
            if (!pager.totalPages) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">暂无国家数据</td></tr>';
                siteReportCountryPage = 1;
                return;
            }

            siteReportCountryPage = pager.page;
            const start = (siteReportCountryPage - 1) * SITE_REPORT_COUNTRY_PAGE_SIZE;
            const pageRows = allRows.slice(start, start + SITE_REPORT_COUNTRY_PAGE_SIZE);
            tbody.innerHTML = pageRows.map((item) => {
                const countryName = normalizeCountryName(item?.country || '');
                return `
                    <tr>
                        <td>${escapeHtml(countryName || '未知')}</td>
                        <td>${formatSiteReportNumber(item?.sessions)}</td>
                        <td>${formatSiteReportPercent(item?.ratio)}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderSiteReportRecentTablePage() {
            const tbody = document.getElementById('siteReportRecentBody');
            const infoEl = document.getElementById('siteReportRecentPageInfo');
            const prevBtn = document.getElementById('siteReportRecentPrevBtn');
            const nextBtn = document.getElementById('siteReportRecentNextBtn');
            if (!tbody) return;

            const allRows = Array.isArray(siteReportRecentRowsAll) ? siteReportRecentRowsAll : [];
            const pager = updateSiteReportPager(allRows.length, SITE_REPORT_EVENT_PAGE_SIZE, siteReportRecentPage, infoEl, prevBtn, nextBtn);
            if (!pager.totalPages) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">暂无最近事件</td></tr>';
                siteReportRecentPage = 1;
                return;
            }

            siteReportRecentPage = pager.page;
            const start = (siteReportRecentPage - 1) * SITE_REPORT_EVENT_PAGE_SIZE;
            const pageRows = allRows.slice(start, start + SITE_REPORT_EVENT_PAGE_SIZE);
            tbody.innerHTML = pageRows.map((item) => {
                const eventName = formatSiteReportEventName(item?.name || '', item?.type || '');
                const path = String(item?.path || '-');
                return `
                    <tr>
                        <td>${escapeHtml(String(item?.timestamp || '-'))}</td>
                        <td>${escapeHtml(eventName)}</td>
                        <td title="${escapeHtml(path)}">${escapeHtml(path)}</td>
                    </tr>
                `;
            }).join('');
        }

        function changeSiteReportEventPage(delta) {
            const move = Number(delta || 0);
            if (!move) return;
            siteReportEventPage += move;
            renderSiteReportEventTablePage();
            queueResponsiveTableLabels();
        }

        function changeSiteReportProvincePage(delta) {
            const move = Number(delta || 0);
            if (!move) return;
            siteReportProvincePage += move;
            renderSiteReportProvinceTablePage();
            queueResponsiveTableLabels();
        }

        function changeSiteReportCountryPage(delta) {
            const move = Number(delta || 0);
            if (!move) return;
            siteReportCountryPage += move;
            renderSiteReportCountryTablePage();
            queueResponsiveTableLabels();
        }

        function changeSiteReportRecentPage(delta) {
            const move = Number(delta || 0);
            if (!move) return;
            siteReportRecentPage += move;
            renderSiteReportRecentTablePage();
            queueResponsiveTableLabels();
        }

        function renderSiteReports(payload) {
            const data = payload && typeof payload === 'object' ? payload : {};
            const sourceLabels = {
                direct: '直接访问',
                internal: '站内跳转',
                referral: '外部引荐',
                search: '搜索引擎',
                social: '社交媒体',
                paid: '广告投放',
                email: '邮件营销',
                affiliate: '联盟推广',
                display: '展示广告',
                campaign: '活动投放'
            };
            const deviceLabels = {
                desktop: '桌面端',
                mobile: '移动端',
                tablet: '平板',
                unknown: '未知'
            };

            renderSiteReportKpis(data.summary || {});
            renderSiteReportTrend(data.trend || [], {
                granularity: data.granularity || siteReportsGranularity,
                rangeLabel: data.range_label || ''
            });

            const sourceBody = document.getElementById('siteReportSourceBody');
            const sourceRows = Array.isArray(data.source_breakdown) ? data.source_breakdown : [];
            if (sourceBody) {
                if (!sourceRows.length) {
                    sourceBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无来源数据</td></tr>';
                } else {
                    sourceBody.innerHTML = sourceRows.map((item) => {
                        const sourceKey = String(item?.source || '').toLowerCase();
                        const sourceText = sourceLabels[sourceKey] || sourceKey || '未知';
                        return `
                            <tr>
                                <td>${escapeHtml(sourceText)}</td>
                                <td>${formatSiteReportNumber(item?.sessions)}</td>
                                <td>${formatSiteReportPercent(item?.ratio)}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            const deviceBody = document.getElementById('siteReportDeviceBody');
            const deviceRows = Array.isArray(data.device_breakdown) ? data.device_breakdown : [];
            if (deviceBody) {
                if (!deviceRows.length) {
                    deviceBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无设备数据</td></tr>';
                } else {
                    deviceBody.innerHTML = deviceRows.map((item) => {
                        const deviceKey = String(item?.device || '').toLowerCase();
                        const deviceText = deviceLabels[deviceKey] || deviceKey || '未知';
                        return `
                            <tr>
                                <td>${escapeHtml(deviceText)}</td>
                                <td>${formatSiteReportNumber(item?.sessions)}</td>
                                <td>${formatSiteReportPercent(item?.ratio)}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            const osBody = document.getElementById('siteReportOsBody');
            const osRows = Array.isArray(data.os_breakdown) ? data.os_breakdown : [];
            if (osBody) {
                if (!osRows.length) {
                    osBody.innerHTML = '<tr><td colspan="3" class="no-data">暂无系统数据</td></tr>';
                } else {
                    osBody.innerHTML = osRows.map((item) => {
                        const osKey = String(item?.os || '').toLowerCase();
                        const meta = getSiteReportOsMeta(osKey);
                        return `
                            <tr>
                                <td>
                                    <span class="os-icon">
                                        <i class="${escapeHtml(meta.icon)}" aria-hidden="true"></i>
                                        <span>${escapeHtml(meta.label)}</span>
                                    </span>
                                </td>
                                <td>${formatSiteReportNumber(item?.sessions)}</td>
                                <td>${formatSiteReportPercent(item?.ratio)}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            const provinceRows = Array.isArray(data.province_breakdown) ? data.province_breakdown : [];
            siteReportProvinceRowsAll = provinceRows;
            siteReportProvincePage = 1;
            renderSiteReportProvinceTablePage();

            const countryRows = Array.isArray(data.country_breakdown) ? data.country_breakdown : [];
            siteReportCountryRowsAll = countryRows;
            siteReportCountryPage = 1;
            renderSiteReportCountryTablePage();

            renderChinaProvinceHeatMap(provinceRows);
            renderWorldContinentHeatMaps(Array.isArray(data.continent_breakdown) ? data.continent_breakdown : []);

            const pagesBody = document.getElementById('siteReportPagesBody');
            const pageRows = Array.isArray(data.top_pages) ? data.top_pages : [];
            if (pagesBody) {
                if (!pageRows.length) {
                    pagesBody.innerHTML = '<tr><td colspan="4" class="no-data">暂无页面数据</td></tr>';
                } else {
                    pagesBody.innerHTML = pageRows.map((item) => {
                        const path = String(item?.path || '/');
                        const title = String(item?.title || '');
                        const pageLabel = title ? `${title} (${path})` : path;
                        return `
                            <tr>
                                <td title="${escapeHtml(pageLabel)}">${escapeHtml(pageLabel)}</td>
                                <td>${formatSiteReportNumber(item?.pageviews)}</td>
                                <td>${formatSiteReportNumber(item?.unique_visitors)}</td>
                                <td>${formatSiteReportNumber(item?.sessions)}</td>
                            </tr>
                        `;
                    }).join('');
                }
            }

            const eventRows = Array.isArray(data.top_events) ? data.top_events : [];
            const recentRows = Array.isArray(data.recent_events) ? data.recent_events : [];
            siteReportEventRowsAll = eventRows;
            siteReportRecentRowsAll = recentRows;
            siteReportEventPage = 1;
            siteReportRecentPage = 1;
            renderSiteReportEventTablePage();
            renderSiteReportRecentTablePage();

            const updatedEl = document.getElementById('siteReportLastUpdated');
            if (updatedEl) {
                if (isValidIsoDate(data.start_date)) siteReportsStartDate = String(data.start_date);
                if (isValidIsoDate(data.end_date)) siteReportsEndDate = String(data.end_date);
                if (String(data.granularity || '').trim()) siteReportsGranularity = String(data.granularity).trim();
                const rangeLabel = String(data.range_label || '').trim()
                    || `${siteReportsStartDate} 至 ${siteReportsEndDate} · ${getSiteReportGranularityLabel(siteReportsGranularity)}`;
                const generatedAt = formatChangelogTime(data.generated_at) || String(data.generated_at || '-');
                updatedEl.textContent = `统计范围：${rangeLabel} · 数据更新时间：${generatedAt}`;
            }
        }

        async function loadSiteReports(manual = false) {
            if (siteReportsLoading) return;
            ensureSiteReportFiltersInitialized();
            const startEl = document.getElementById('siteReportStartDate');
            const endEl = document.getElementById('siteReportEndDate');
            const granularityEl = document.getElementById('siteReportGranularity');

            const msgEl = document.getElementById('siteReportMsg');
            if (msgEl) {
                msgEl.style.color = '#28a745';
                msgEl.textContent = '';
            }

            const startDate = String(startEl?.value || '').trim();
            const endDate = String(endEl?.value || '').trim();
            const granularity = String(granularityEl?.value || 'day').trim().toLowerCase() || 'day';
            const validGranularities = new Set(['year', 'month', 'week', 'day']);
            syncSiteReportDateInputLimits();

            let validationError = '';
            if (!startDate || !endDate) {
                validationError = '请选择完整的开始日期和结束日期';
            } else if (!isValidIsoDate(startDate) || !isValidIsoDate(endDate)) {
                validationError = '日期格式无效，请重新选择日期';
            } else if (startDate > endDate) {
                validationError = '开始日期不能晚于结束日期';
            } else if (!validGranularities.has(granularity)) {
                validationError = '显示粒度无效，请重新选择';
            }

            if (validationError) {
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = validationError;
                }
                if (manual) {
                    showGlobalAlert(validationError);
                }
                return;
            }

            siteReportsStartDate = startDate;
            siteReportsEndDate = endDate;
            siteReportsGranularity = granularity;

            setSiteReportsLoading(true);
            try {
                const params = new URLSearchParams({
                    start_date: siteReportsStartDate,
                    end_date: siteReportsEndDate,
                    granularity: siteReportsGranularity
                });
                const res = await fetch(`/api/admin/site-reports?${params.toString()}`, { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                if (!res.ok || data.success !== true) {
                    throw new Error(String(data.message || `加载报表失败（HTTP ${res.status || '-'}）`));
                }
                renderSiteReports(data);
                if (msgEl && manual) {
                    msgEl.style.color = '#28a745';
                    msgEl.textContent = '报表已刷新';
                }
            } catch (err) {
                console.error('Load site reports failed:', err);
                renderSiteReportRows();
                const message = String(err?.message || '加载报表失败');
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = message;
                }
                if (manual) {
                    showGlobalAlert(message);
                }
            } finally {
                setSiteReportsLoading(false);
                queueResponsiveTableLabels();
            }
        }

        // --- Navigation ---
        function switchView(viewName, options = {}) {
            if (viewName === 'changelog' || viewName === 'docker-logs') {
                viewName = 'log-records';
            }
            const persist = options && options.persist !== false;
            const hashSync = !options || options.hash !== false;
            if (bindingRequiredState && viewName !== 'settings') {
                viewName = 'settings';
            }
            if (!hasViewPermission(viewName)) {
                showGlobalAlert('当前账号没有访问该功能的权限');
                return;
            }

            const targetView = document.getElementById(`view-${viewName}`);
            if (!targetView) return;

            // Update Menu
            document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
            const activeMenu = document.querySelector(`.menu-item[data-view="${viewName}"]`);
            if (activeMenu) activeMenu.classList.add('active');
            syncSidebarMenuGroups(viewName);

            // Update View
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            targetView.classList.add('active');
            if (persist) saveStoredAdminView(viewName);
            else if (hashSync) syncHashAdminView(viewName);

            // Update Title
            const titles = {
                'messages': '留言系统',
                'products': '氢气产品',
                'bio-products': '生物产品',
                'hydrogen-solutions': '行业方案',
                'home': '首页设置',
                'h2-home': '氢气首页设置',
                'news-create': '添加资讯',
                'jobs': '招聘信息',
                'chatbot': 'AI 与知识库',
                'site-settings': '站点设置',
                'site-reports': '网站数据',
                'settings': '账号设置',
                'backup': '备份恢复',
                'cdn-assets': 'CDN 素材',
                'log-records': '日志记录'
            };
            document.getElementById('pageTitle').textContent = titles[viewName] || viewName;

            // Load data for the view
            if (viewName === 'messages') loadMessages();
            if (viewName === 'products') {
                bindProductCreateEvents();
                loadProducts();
            }
            if (viewName === 'bio-products') {
                loadBioProducts();
            }
            if (viewName === 'hydrogen-solutions') loadHydrogenSolutionsConfig();
            if (viewName === 'home') {
                switchHomeTab('hero');
            }
            if (viewName === 'h2-home') switchH2HomeTab('video');
            if (viewName === 'news-create') loadNewsList();
            if (viewName === 'news-create') updateNewsPreview();
            if (viewName === 'jobs') loadJobsAdmin();
            if (viewName === 'chatbot') loadChatbotConfig();
            if (viewName === 'site-settings') {
                loadAdminLoginGeoSettings();
                loadTurnstileAdminConfig();
                loadEmailAuthSettings();
            }
            if (viewName === 'site-reports') {
                loadSiteReports();
                loadAdminLoginLogs();
            }
            if (viewName === 'settings') {
                if (!bindingRequiredState) loadSubAccounts();
                loadEmailBindingStatus();
            }
            if (viewName === 'log-records') {
                loadChangelog();
                loadDockerLogs();
            }
            if (viewName === 'cdn-assets') loadCdnAssets();

            renderGuidesForView(viewName);

            const isEditable = viewName === 'settings' ? true : canEditView(viewName);
            applyReadOnlyMode(viewName, !isEditable);

            if (isMobileAdminViewport()) {
                closeMobileSidebar();
            }
            queueResponsiveTableLabels();
        }

        function applyReadOnlyMode(viewName, readOnly) {
            const view = document.getElementById(`view-${viewName}`);
            if (!view) return;

            view.classList.toggle('read-only-mode', readOnly);

            let banner = view.querySelector('.read-only-banner');
            if (readOnly) {
                if (!banner) {
                    banner = document.createElement('div');
                    banner.className = 'read-only-banner';
                    banner.innerHTML = '<i class="fas fa-lock"></i> 当前账号无编辑权限，仅可查看数据';
                    view.insertBefore(banner, view.firstChild);
                }

                const editableSelectors = [
                    'button:not([disabled])',
                    'input:not([disabled])',
                    'textarea:not([disabled])',
                    'select:not([disabled])',
                    'a[href]',
                    '[contenteditable="true"]',
                    '.btn',
                    '.action-btn',
                    '[onclick*="save"]',
                    '[onclick*="delete"]',
                    '[onclick*="edit"]',
                    '[onclick*="update"]',
                    '[onclick*="create"]',
                    '[onclick*="remove"]'
                ];

                editableSelectors.forEach(selector => {
                    view.querySelectorAll(selector).forEach(el => {
                        if (!el.classList.contains('read-only-safe') &&
                            !el.closest('#emailBindingCard') &&
                            !el.closest('.read-only-banner')) {
                            el.dataset.originalDisabled = el.disabled || '';
                            el.dataset.originalReadOnly = el.readOnly || '';
                            el.disabled = true;
                            el.readOnly = true;
                            el.classList.add('read-only-disabled');
                        }
                    });
                });

                view.querySelectorAll('[contenteditable]').forEach(el => {
                    if (el.contentEditable === 'true') {
                        el.dataset.originalContentEditable = el.contentEditable;
                        el.contentEditable = 'false';
                        el.classList.add('read-only-disabled');
                    }
                });

                view.querySelectorAll('[onclick]').forEach(el => {
                    const onclick = el.getAttribute('onclick') || '';
                    const isAction = onclick.match(/save|delete|edit|update|create|remove|add/i);
                    if (isAction && !el.classList.contains('read-only-safe') && !el.closest('#emailBindingCard')) {
                        el.dataset.originalOnclick = onclick;
                        el.removeAttribute('onclick');
                        el.classList.add('read-only-disabled');
                    }
                });
            } else {
                if (banner) {
                    banner.remove();
                }

                view.querySelectorAll('.read-only-disabled').forEach(el => {
                    if (el.dataset.originalDisabled !== undefined) {
                        el.disabled = el.dataset.originalDisabled === 'true';
                    }
                    if (el.dataset.originalReadOnly !== undefined) {
                        el.readOnly = el.dataset.originalReadOnly === 'true';
                    }
                    el.classList.remove('read-only-disabled');
                });

                view.querySelectorAll('[data-original-contenteditable]').forEach(el => {
                    el.contentEditable = el.dataset.originalContentEditable;
                    el.classList.remove('read-only-disabled');
                });

                view.querySelectorAll('[data-original-onclick]').forEach(el => {
                    el.setAttribute('onclick', el.dataset.originalOnclick);
                });
            }
        }

        // --- Products Logic ---
        let productsData = [];
        let industryFiltersData = [];
        let bioProductsData = [];
        let bioIndustryFiltersData = [];
        let industryFiltersSaveToken = 0;
        let bioIndustryFiltersSaveToken = 0;
        let productEditorMode = 'visual';
        let editingProductSlug = '';
        let productPreviewTimer = null;
        let productTemplatePlaceholderKeys = [];
        let productTemplateFieldsData = {};
        let productTemplateGroupVisibleCounts = {};
        let aiProductEventsBound = false;
        let aiUploadedImageUrls = [];
        let bioAiProductEventsBound = false;
        let bioAiUploadedImageUrls = [];
        let hydrogenSolutionDefinitions = [];
        let hydrogenSolutionsConfig = [];
        let hydrogenSolutionProductOptions = [];
        const AI_STREAM_IDLE_TIMEOUT_MS = 45000;
        const AI_STREAM_TOTAL_TIMEOUT_MS = 7 * 60 * 1000;

        function syncProductEditorSourceFromVisual() {
            const visual = document.getElementById('productEditorVisual');
            const source = document.getElementById('productEditorSource');
            if (!visual || !source) return;
            source.value = visual.innerHTML.trim();
        }

        function syncProductEditorVisualFromSource() {
            const visual = document.getElementById('productEditorVisual');
            const source = document.getElementById('productEditorSource');
            if (!visual || !source) return;
            visual.innerHTML = source.value || '';
        }

        function switchProductEditorMode(mode) {
            const visual = document.getElementById('productEditorVisual');
            const source = document.getElementById('productEditorSource');
            const visualBtn = document.getElementById('productModeVisualBtn');
            const sourceBtn = document.getElementById('productModeSourceBtn');
            if (!visual || !source || !visualBtn || !sourceBtn) return;

            if (mode === 'source') {
                syncProductEditorSourceFromVisual();
                visual.style.display = 'none';
                source.style.display = 'block';
                sourceBtn.classList.add('active');
                visualBtn.classList.remove('active');
                productEditorMode = 'source';
            } else {
                syncProductEditorVisualFromSource();
                source.style.display = 'none';
                visual.style.display = 'block';
                visualBtn.classList.add('active');
                sourceBtn.classList.remove('active');
                productEditorMode = 'visual';
            }
            scheduleProductPreview();
        }

        function applyProductFormat(command, value = null) {
            const visual = document.getElementById('productEditorVisual');
            if (!visual || productEditorMode !== 'visual') return;
            visual.focus();
            try {
                if (command === 'formatBlock' && value) {
                    document.execCommand(command, false, `<${value}>`);
                } else {
                    document.execCommand(command, false, value);
                }
                syncProductEditorSourceFromVisual();
                scheduleProductPreview();
            } catch (e) {
                console.error('applyProductFormat failed:', e);
            }
        }

        function getProductEditorHtml() {
            const visual = document.getElementById('productEditorVisual');
            const source = document.getElementById('productEditorSource');
            if (!visual || !source) return '';
            if (productEditorMode === 'source') {
                return (source.value || '').trim();
            }
            return (visual.innerHTML || '').trim();
        }

        function getProductDetailPartsFromEditor() {
            const html = getProductEditorHtml();
            if (!html) return ['', ''];
            const container = document.createElement('div');
            container.innerHTML = html;
            const ps = Array.from(container.querySelectorAll('p'))
                .map(p => (p.textContent || '').trim())
                .filter(Boolean);
            if (ps.length > 0) return [ps[0], ps[1] || ''];
            const lines = (container.textContent || '')
                .split(/\n+/)
                .map(v => v.trim())
                .filter(Boolean);
            return [lines[0] || '', lines[1] || ''];
        }

        function getProductTemplateDefaultMap() {
            const title = document.getElementById('productCreateTitle')?.value.trim() || '';
            const summary = document.getElementById('productCreateSummary')?.value.trim() || '';
            const image = document.getElementById('productCreateImage')?.value.trim() || '/cdn_assets/images/common/f1dcc87cdcca.png';
            const [detail1, detail2] = getProductDetailPartsFromEditor();
            const defaults = {};
            productTemplatePlaceholderKeys.forEach(key => {
                if (key.includes('链接')) {
                    if (key.includes('图片') || key.includes('主图') || key.includes('缩略图') || key.includes('详情图') || key.includes('应用图')) {
                        defaults[key] = image;
                    } else if (key.includes('新闻链接') || key.includes('相关产品链接')) {
                        defaults[key] = '#';
                    } else {
                        defaults[key] = '';
                    }
                } else {
                    defaults[key] = '';
                }
            });
            ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】'].forEach(k => defaults[k] = title);
            defaults['【产品描述】'] = summary;
            defaults['【主图链接】'] = image;
            defaults['【缩略图1链接】'] = image;
            defaults['【产品详情1】'] = detail1;
            defaults['【产品详情2】'] = detail2;
            return defaults;
        }

        function isProductTemplateImageLinkKey(key) {
            return key.includes('链接') && (key.includes('图片') || key.includes('主图') || key.includes('缩略图') || key.includes('详情图') || key.includes('应用图'));
        }

        function normalizeProductTemplateFieldValue(key, value) {
            const v = (value || '').trim();
            if (!v) return '';
            if (isProductTemplateImageLinkKey(key)) {
                if (/^assets\//i.test(v)) return `/${v}`;
                return v;
            }
            return v;
        }

        function isLongProductTemplateKey(key) {
            return !key.includes('链接') && (key.includes('描述') || key.includes('详情'));
        }

        function getTemplateFieldSimpleName(key) {
            return String(key || '').replace(/^【|】$/g, '');
        }

        function buildProductTemplateEditorModel() {
            const keySet = new Set(productTemplatePlaceholderKeys);
            const used = new Set();
            const productNameKeys = ['【这里是产品名字】', '【本页的产品名字】', '【产品名字】'].filter(k => keySet.has(k));
            productNameKeys.forEach(k => used.add(k));

            const repeatDefs = [
                {
                    id: 'thumbs',
                    title: '缩略图',
                    defaultVisible: 3,
                    fields: (i) => [{ key: `【缩略图${i}链接】`, label: `缩略图${i}` }]
                },
                {
                    id: 'features',
                    title: '产品特性',
                    defaultVisible: 3,
                    fields: (i) => [{ key: `【特性${i}】`, label: `特性${i}` }]
                },
                {
                    id: 'advantages',
                    title: '产品优势',
                    defaultVisible: 2,
                    fields: (i) => [
                        { key: `【优势${i}】`, label: `优势${i}` },
                        { key: `【优势${i}的描述】`, label: `优势${i}描述` }
                    ]
                },
                {
                    id: 'detail_images',
                    title: '详情图',
                    defaultVisible: 2,
                    fields: (i) => [
                        { key: `【详情图${i}链接】`, label: `详情图${i}` },
                        { key: `【详情图${i}的描述】`, label: `详情图${i}描述` }
                    ]
                },
                {
                    id: 'applications',
                    title: '应用场景',
                    defaultVisible: 2,
                    fields: (i) => [
                        { key: `【应用图${i}链接】`, label: `应用图${i}` },
                        { key: `【应用${i}】`, label: `应用${i}标题` },
                        { key: `【应用${i}的描述】`, label: `应用${i}描述` }
                    ]
                },
                {
                    id: 'news',
                    title: '关联新闻',
                    defaultVisible: 2,
                    fields: (i) => [
                        { key: `【新闻链接${i}】`, label: `新闻${i}链接` },
                        { key: `【新闻图片${i}链接】`, label: `新闻${i}图片` },
                        { key: `【新闻标题${i}】`, label: `新闻${i}标题` },
                        { key: `【新闻描述${i}】`, label: `新闻${i}描述` }
                    ]
                },
                {
                    id: 'related_products',
                    title: '相关产品',
                    defaultVisible: 4,
                    fields: (i) => [
                        { key: `【相关产品链接${i}】`, label: `相关产品${i}链接` },
                        { key: `【相关产品图片${i}链接】`, label: `相关产品${i}图片` },
                        { key: `【相关产品标题${i}】`, label: `相关产品${i}标题` }
                    ]
                }
            ];

            const repeatGroups = [];
            repeatDefs.forEach(def => {
                const items = [];
                for (let i = 1; i <= 24; i += 1) {
                    const fields = def.fields(i).filter(f => keySet.has(f.key));
                    if (!fields.length) continue;
                    fields.forEach(f => used.add(f.key));
                    items.push({ index: i, fields });
                }
                if (items.length) {
                    repeatGroups.push({
                        id: def.id,
                        title: def.title,
                        defaultVisible: Math.min(def.defaultVisible || 1, items.length),
                        items
                    });
                }
            });

            const specKeys = [];
            const coreKeys = [];
            const otherKeys = [];
            productTemplatePlaceholderKeys.forEach(key => {
                if (used.has(key)) return;
                if (['【主图链接】', '【产品描述】', '【产品详情1】', '【产品详情2】'].includes(key)) {
                    coreKeys.push(key);
                } else if (/(技术|检测|范围|精度|响应|温度|尺寸|重量|功耗|续航)/.test(key)) {
                    specKeys.push(key);
                } else {
                    otherKeys.push(key);
                }
            });

            const singleSections = [];
            if (coreKeys.length) singleSections.push({ id: 'core', title: '核心信息', keys: coreKeys });
            if (specKeys.length) singleSections.push({ id: 'spec', title: '技术参数', keys: specKeys });
            if (otherKeys.length) singleSections.push({ id: 'other', title: '其他字段', keys: otherKeys });

            return { productNameKeys, repeatGroups, singleSections };
        }

        function ensureProductTemplateGroupVisibleCounts(model) {
            model.repeatGroups.forEach(group => {
                const current = productTemplateGroupVisibleCounts[group.id];
                const maxIndexWithValue = group.items.reduce((max, item, idx) => {
                    const hasValue = item.fields.some(f => (productTemplateFieldsData[f.key] || '').trim());
                    return hasValue ? idx + 1 : max;
                }, 0);
                const fallback = maxIndexWithValue || group.defaultVisible || 1;
                const next = current == null ? fallback : current;
                productTemplateGroupVisibleCounts[group.id] = Math.max(1, Math.min(group.items.length, next));
            });
        }

        function renderProductTemplateInputField(fieldKey, fieldLabel, fieldValue) {
            const isLong = isLongProductTemplateKey(fieldKey);
            const isImageLink = isProductTemplateImageLinkKey(fieldKey);
            const helper = isImageLink
                ? '<div style="margin-top:6px; font-size:12px; color:#5f6b7a;">支持 <code>/assets/images/xxx.png</code> 或 <code>https://...</code></div>'
                : '';
            if (isLong) {
                return `
                    <div style="margin-top:8px;">
                        <div style="font-size:12px; color:#425166; margin-bottom:6px;">${escapeHtml(fieldLabel)}</div>
                        <textarea class="form-control product-template-field" data-key="${escapeHtml(fieldKey)}" rows="2">${escapeHtml(fieldValue || '')}</textarea>
                    </div>
                `;
            }
            return `
                <div style="margin-top:8px;">
                    <div style="font-size:12px; color:#425166; margin-bottom:6px;">${escapeHtml(fieldLabel)}</div>
                    <input type="text" class="form-control product-template-field" data-key="${escapeHtml(fieldKey)}"
                        value="${escapeHtml(fieldValue || '')}"
                        placeholder="${isImageLink ? '例如 /cdn_assets/images/common/f1dcc87cdcca.png 或 https://cdn.example.com/a.png' : ''}">
                    ${helper}
                </div>
            `;
        }

        function changeProductTemplateGroupCount(groupId, action) {
            const model = buildProductTemplateEditorModel();
            const group = model.repeatGroups.find(g => g.id === groupId);
            if (!group) return;
            const current = productTemplateGroupVisibleCounts[groupId] || 1;
            let next = current;
            if (action === 'add') next = Math.min(group.items.length, current + 1);
            if (action === 'remove') next = Math.max(1, current - 1);
            if (next === current) return;

            if (next < current) {
                for (let i = next; i < current; i += 1) {
                    const item = group.items[i];
                    if (!item) continue;
                    item.fields.forEach(f => {
                        productTemplateFieldsData[f.key] = '';
                    });
                }
            }
            productTemplateGroupVisibleCounts[groupId] = next;
            renderProductTemplateFieldsEditor();
            scheduleProductPreview();
        }
        window.changeProductTemplateGroupCount = changeProductTemplateGroupCount;

        function renderProductTemplateFieldsEditor() {
            const container = document.getElementById('productTemplateFieldsEditor');
            if (!container) return;
            if (!productTemplatePlaceholderKeys.length) {
                container.innerHTML = '<div style="color:#888; padding:6px 0;">模板字段加载中...</div>';
                return;
            }
            const model = buildProductTemplateEditorModel();
            ensureProductTemplateGroupVisibleCounts(model);

            const nameSectionHtml = model.productNameKeys.length ? `
                <div style="border:1px solid #dbe3ef; border-radius: 12px; background:#fff; padding:16px; margin-bottom:14px;">
                    <div style="font-size:13px; font-weight:700; color:#0f2f5f;">产品名称（已合并 ${model.productNameKeys.length} 个占位符）</div>
                    <div style="font-size:12px; color:#6b7280; margin-top:4px;">同步映射到：${model.productNameKeys.map(k => `<code>${escapeHtml(k)}</code>`).join('、')}</div>
                    <input type="text" class="form-control product-template-merged-field"
                        data-keys="${escapeHtml(model.productNameKeys.join('||'))}"
                        style="margin-top:10px;"
                        value="${escapeHtml(model.productNameKeys.map(k => productTemplateFieldsData[k] || '').find(v => v) || '')}">
                </div>
            ` : '';

            const repeatSectionHtml = model.repeatGroups.map(group => {
                const visible = productTemplateGroupVisibleCounts[group.id] || 1;
                const blocks = group.items.slice(0, visible).map((item, idx) => `
                    <div style="border:1px solid #e5ebf5; border-radius:10px; padding:12px; background:${idx % 2 ? '#fbfdff' : '#fff'};">
                        <div style="font-size:12px; font-weight:700; color:#334155;">第 ${item.index} 条</div>
                        ${item.fields.map(f => renderProductTemplateInputField(f.key, f.label, productTemplateFieldsData[f.key] || '')).join('')}
                    </div>
                `).join('');
                return `
                    <div style="border:1px solid #dbe3ef; border-radius: 12px; background:#fff; padding:16px; margin-bottom:14px;">
                        <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;">
                            <div>
                                <div style="font-size:13px; font-weight:700; color:#0f2f5f;">${escapeHtml(group.title)}</div>
                                <div style="font-size:12px; color:#6b7280;">已显示 ${visible} / ${group.items.length} 条</div>
                            </div>
                            <div style="display:flex; gap:8px;">
                                <button type="button" class="btn-sm" style="width:auto;" onclick="changeProductTemplateGroupCount('${escapeHtml(group.id)}','remove')">删除一条</button>
                                <button type="button" class="btn-sm" style="width:auto;" onclick="changeProductTemplateGroupCount('${escapeHtml(group.id)}','add')">添加一条</button>
                            </div>
                        </div>
                        <div style="margin-top:10px; display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:10px;">
                            ${blocks}
                        </div>
                    </div>
                `;
            }).join('');

            const singleSectionHtml = model.singleSections.map(section => `
                <div style="border:1px solid #dbe3ef; border-radius: 12px; background:#fff; padding:16px; margin-bottom:14px;">
                    <div style="font-size:13px; font-weight:700; color:#0f2f5f;">${escapeHtml(section.title)}</div>
                    <div style="margin-top:10px; display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:10px;">
                        ${section.keys.map(k => `
                            <div style="border:1px solid #e5ebf5; border-radius:10px; padding:12px; background:#fff;">
                                ${renderProductTemplateInputField(k, getTemplateFieldSimpleName(k), productTemplateFieldsData[k] || '')}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');

            container.innerHTML = `
                <div style="border:1px solid #dbe3ef; border-radius: 12px; background:#f7faff; padding:14px; box-shadow: 0 6px 18px rgba(15, 47, 95, 0.06);">
                    ${nameSectionHtml}
                    ${repeatSectionHtml}
                    ${singleSectionHtml}
                    ${(!nameSectionHtml && !repeatSectionHtml && !singleSectionHtml) ? '<div style="color:#6b7280;">暂无可配置模板字段</div>' : ''}
                </div>
            `;

            container.querySelectorAll('.product-template-field').forEach(el => {
                el.addEventListener('input', () => {
                    const key = el.dataset.key || '';
                    productTemplateFieldsData[key] = normalizeProductTemplateFieldValue(key, el.value || '');
                    scheduleProductPreview();
                });
            });
            container.querySelectorAll('.product-template-merged-field').forEach(el => {
                el.addEventListener('input', () => {
                    const keys = String(el.dataset.keys || '').split('||').filter(Boolean);
                    const value = (el.value || '').trim();
                    keys.forEach(k => {
                        productTemplateFieldsData[k] = value;
                    });
                    scheduleProductPreview();
                });
            });
        }

        function collectProductTemplateFieldsFromDom() {
            const els = Array.from(document.querySelectorAll('.product-template-field'));
            const mergedEls = Array.from(document.querySelectorAll('.product-template-merged-field'));
            if (!els.length && !mergedEls.length) return { ...productTemplateFieldsData };
            const data = { ...productTemplateFieldsData };
            els.forEach(el => {
                const key = el.dataset.key || '';
                if (!key) return;
                data[key] = normalizeProductTemplateFieldValue(key, el.value || '');
            });
            mergedEls.forEach(el => {
                const keys = String(el.dataset.keys || '').split('||').filter(Boolean);
                const value = (el.value || '').trim();
                keys.forEach(k => {
                    data[k] = value;
                });
            });
            productTemplateFieldsData = data;
            return data;
        }

        function applyProductTemplateDefaults(onlyEmpty = true) {
            const defaults = getProductTemplateDefaultMap();
            productTemplatePlaceholderKeys.forEach(key => {
                if (!onlyEmpty || !productTemplateFieldsData[key]) {
                    productTemplateFieldsData[key] = defaults[key] || '';
                }
            });
        }

        async function loadProductTemplatePlaceholders() {
            if (productTemplatePlaceholderKeys.length) return;
            try {
                const res = await fetch('/api/products/template/placeholders');
                const data = await res.json();
                productTemplatePlaceholderKeys = Array.isArray(data.items) ? data.items : [];
                if (!Object.keys(productTemplateFieldsData).length) {
                    applyProductTemplateDefaults(false);
                }
                productTemplateGroupVisibleCounts = {};
                renderProductTemplateFieldsEditor();
            } catch (e) {
                const container = document.getElementById('productTemplateFieldsEditor');
                if (container) container.innerHTML = '<div style="color:#dc3545; padding:6px 0;">模板字段加载失败</div>';
            }
        }

        function resetProductTemplateFieldsToDefaults() {
            collectProductTemplateFieldsFromDom();
            applyProductTemplateDefaults(false);
            productTemplateGroupVisibleCounts = {};
            renderProductTemplateFieldsEditor();
            scheduleProductPreview();
        }

        function getProductCreatePayload() {
            collectProductTemplateFieldsFromDom();
            applyProductTemplateDefaults(true);
            return {
                title: document.getElementById('productCreateTitle')?.value.trim() || '',
                short_name: document.getElementById('productCreateShortName')?.value.trim() || '',
                slug: document.getElementById('productCreateSlug')?.value.trim() || '',
                category: document.getElementById('productCreateCategory')?.value || 'sensor',
                image_url: document.getElementById('productCreateImage')?.value.trim() || '',
                summary: document.getElementById('productCreateSummary')?.value.trim() || '',
                content: getProductEditorHtml(),
                content_is_html: true,
                template_fields: productTemplateFieldsData
            };
        }

        async function updateProductPreview() {
            const iframe = document.getElementById('productPreviewFrame');
            if (!iframe) return;
            const payload = getProductCreatePayload();
            try {
                const res = await fetch('/api/products/preview-page', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success && data.page_html) {
                    iframe.srcdoc = data.page_html;
                }
            } catch (e) {
                // ignore preview errors, keep current frame
            }
        }

        function scheduleProductPreview() {
            if (productPreviewTimer) {
                clearTimeout(productPreviewTimer);
                productPreviewTimer = null;
            }
            productPreviewTimer = setTimeout(() => {
                updateProductPreview();
            }, 500);
        }

        function cancelProductEdit() {
            editingProductSlug = '';
            const submitBtn = document.getElementById('productCreateSubmitBtn');
            const cancelBtn = document.getElementById('productCreateCancelBtn');
            if (submitBtn) submitBtn.textContent = '生成产品页面';
            if (cancelBtn) cancelBtn.style.display = 'none';
            const form = document.getElementById('productCreateForm');
            if (form) form.reset();
            const visual = document.getElementById('productEditorVisual');
            const source = document.getElementById('productEditorSource');
            if (visual) visual.innerHTML = '';
            if (source) source.value = '';
            productTemplateFieldsData = {};
            productTemplateGroupVisibleCounts = {};
            applyProductTemplateDefaults(false);
            renderProductTemplateFieldsEditor();
            switchProductEditorMode('visual');
            scheduleProductPreview();
        }

        async function editProductItem(productId) {
            if (!productId || String(productId).startsWith('../')) return;
            try {
                const res = await fetch(`/api/products/detail?id=${encodeURIComponent(productId)}`);
                const data = await res.json();
                if (!data.success || !data.detail) {
                    alert(data.message || '读取产品详情失败');
                    return;
                }
                const detail = data.detail;
                editingProductSlug = detail.id || productId;
                document.getElementById('productCreateTitle').value = detail.title || '';
                document.getElementById('productCreateShortName').value = detail.short_name || '';
                document.getElementById('productCreateSlug').value = detail.id || productId;
                document.getElementById('productCreateCategory').value = detail.category || 'sensor';
                document.getElementById('productCreateImage').value = detail.image_url || '';
                document.getElementById('productCreateSummary').value = detail.summary || '';
                const visual = document.getElementById('productEditorVisual');
                const source = document.getElementById('productEditorSource');
                if (visual) visual.innerHTML = detail.content_html || '';
                if (source) source.value = detail.content_html || '';
                await loadProductTemplatePlaceholders();
                productTemplateFieldsData = (detail.template_fields && typeof detail.template_fields === 'object')
                    ? { ...detail.template_fields }
                    : {};
                productTemplateGroupVisibleCounts = {};
                applyProductTemplateDefaults(true);
                renderProductTemplateFieldsEditor();
                switchProductEditorMode('visual');
                const submitBtn = document.getElementById('productCreateSubmitBtn');
                const cancelBtn = document.getElementById('productCreateCancelBtn');
                if (submitBtn) submitBtn.textContent = '保存修改';
                if (cancelBtn) cancelBtn.style.display = 'inline-flex';
                scheduleProductPreview();
                window.scrollTo({ top: 0, behavior: 'smooth' });
            } catch (e) {
                alert('网络错误');
            }
        }

        async function submitCreateProduct() {
            const msg = document.getElementById('productCreateMsg');
            const linkEl = document.getElementById('productCreateLink');
            if (msg) {
                msg.style.color = '#28a745';
                msg.textContent = '';
            }
            if (linkEl) linkEl.textContent = '';

            const payload = getProductCreatePayload();

            if (!payload.title || !payload.short_name || !payload.slug || !payload.summary || !payload.content) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请完整填写标题、简称、链接标识、摘要和正文';
                }
                return;
            }

            try {
                const endpoint = editingProductSlug ? '/api/products/update' : '/api/products/create';
                if (editingProductSlug) payload.original_slug = editingProductSlug;
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!data.success) {
                    throw new Error(data.message || '生成失败');
                }

                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = editingProductSlug ? '✓ 修改成功' : '✓ 生成成功';
                }
                if (linkEl && data.link) {
                    const stamped = `${data.link}${data.link.includes('?') ? '&' : '?'}t=${Date.now()}`;
                    linkEl.innerHTML = `页面：<a href="${stamped}" target="_blank">${stamped}</a>`;
                }

                cancelProductEdit();

                await loadProducts();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e.message || '保存失败';
                }
            }
        }

        function bindProductCreateEvents() {
            const submitBtn = document.getElementById('productCreateSubmitBtn');
            if (submitBtn && !submitBtn.dataset.bound) {
                submitBtn.addEventListener('click', submitCreateProduct);
                submitBtn.dataset.bound = '1';
            }

            const titleInput = document.getElementById('productCreateTitle');
            const slugInput = document.getElementById('productCreateSlug');
            if (titleInput && slugInput && !titleInput.dataset.slugBound) {
                titleInput.addEventListener('input', () => {
                    if (slugInput.value.trim()) return;
                    const generated = (titleInput.value || '')
                        .toLowerCase()
                        .replace(/\s+/g, '_')
                        .replace(/[^a-z0-9_]/g, '')
                        .replace(/_+/g, '_')
                        .replace(/^_+|_+$/g, '');
                    slugInput.value = generated;
                });
                titleInput.dataset.slugBound = '1';
            }

            const visual = document.getElementById('productEditorVisual');
            if (visual && !visual.dataset.bound) {
                visual.addEventListener('input', () => {
                    syncProductEditorSourceFromVisual();
                    scheduleProductPreview();
                });
                visual.dataset.bound = '1';
            }

            const source = document.getElementById('productEditorSource');
            if (source && !source.dataset.bound) {
                source.addEventListener('input', scheduleProductPreview);
                source.dataset.bound = '1';
            }

            ['productCreateTitle', 'productCreateShortName', 'productCreateSlug', 'productCreateCategory', 'productCreateImage', 'productCreateSummary']
                .forEach(id => {
                    const el = document.getElementById(id);
                    if (el && !el.dataset.previewBound) {
                        el.addEventListener('input', scheduleProductPreview);
                        el.addEventListener('change', scheduleProductPreview);
                        el.dataset.previewBound = '1';
                    }
                });

            if (!window.__productPreviewHeightBound) {
                window.addEventListener('message', (event) => {
                    const data = event.data || {};
                    if (data.type === 'product-preview-height' && data.height) {
                        const iframe = document.getElementById('productPreviewFrame');
                        if (iframe) iframe.style.height = `${Math.max(560, Number(data.height) || 560)}px`;
                    }
                });
                window.__productPreviewHeightBound = true;
            }

            loadProductTemplatePlaceholders();
            scheduleProductPreview();
        }

        function aiGuessSlugFromText(rawText) {
            const text = String(rawText || '');
            const modelMatch = text.match(/产品名称[:：]\s*([^\n]+)/);
            const modelToken = modelMatch && modelMatch[1]
                ? (modelMatch[1].match(/[A-Za-z0-9_.-]+/) || [])[0]
                : '';
            const base = (modelToken || '')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '_')
                .replace(/_+/g, '_')
                .replace(/^_+|_+$/g, '');
            return base || '';
        }

        function aiParseProductFromFullText(fullText) {
            const text = String(fullText || '').trim();
            const titleMatch = text.match(/(?:^|\n)\s*(?:\d+\.\s*)?产品名称[:：]\s*([^\n]+)/);
            const summaryMatch = text.match(/(?:^|\n)\s*(?:\d+\.\s*)?一句概述[:：]\s*([^\n]+)/);
            const title = (titleMatch && titleMatch[1] ? titleMatch[1].trim() : '').replace(/\s+$/, '');
            const summary = summaryMatch && summaryMatch[1] ? summaryMatch[1].trim() : '';
            const shortNameMatch = title.match(/[A-Za-z0-9_.-]+/);
            const shortName = shortNameMatch ? shortNameMatch[0] : '';
            return { title, summary, shortName };
        }

        function renderAiUploadedImages() {
            const list = document.getElementById('aiProductImagesList');
            if (!list) return;
            if (!aiUploadedImageUrls.length) {
                list.innerHTML = '<div style="font-size:12px; color:#94a3b8;">尚未上传图片</div>';
                return;
            }
            list.innerHTML = aiUploadedImageUrls.map((url, index) => `
                <div style="border:1px solid #e2e8f0; border-radius:8px; padding:8px; background:#fff;">
                    <img src="${url}" alt="product-image-${index + 1}" style="width:100%; height:90px; object-fit:cover; border-radius:6px; background:#f8fafc;">
                    <div style="margin-top:6px; font-size:11px; color:#475569; overflow-wrap:anywhere; word-break:break-word;">${escapeHtml(url)}</div>
                </div>
            `).join('');
        }

        async function uploadAiProductImages(files) {
            const msg = document.getElementById('aiProductImagesMsg');
            const fullContent = document.getElementById('aiProductFullContent')?.value || '';
            const parsed = aiParseProductFromFullText(fullContent);
            const slugInput = document.getElementById('aiProductSlug');
            const slugValue = (slugInput?.value || '').trim() || aiGuessSlugFromText(fullContent);
            const shortName = parsed.shortName || '';

            if (!slugValue) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = '请先在总输入框写“产品名称”，或手动填写链接标识后再上传图片。';
                }
                return;
            }
            if (!/^[a-z0-9_]+$/.test(slugValue)) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = '链接标识仅支持小写字母、数字、下划线。';
                }
                return;
            }
            if (slugInput && !slugInput.value.trim()) slugInput.value = slugValue;
            if (!files || !files.length) return;

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = `正在上传 ${files.length} 张图片...`;
            }

            const formData = new FormData();
            formData.append('slug', slugValue);
            formData.append('short_name', shortName);
            Array.from(files).forEach(file => formData.append('files', file));

            try {
                const res = await fetch('/api/products/ai-upload-images', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '上传失败');
                }
                const uploadedUrls = Array.isArray(data.urls) ? data.urls : [];
                const merged = Array.isArray(aiUploadedImageUrls) ? [...aiUploadedImageUrls] : [];
                uploadedUrls.forEach(url => {
                    const v = String(url || '').trim();
                    if (!v) return;
                    if (!merged.includes(v)) merged.push(v);
                });
                aiUploadedImageUrls = merged;
                renderAiUploadedImages();
                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = `✓ 本次上传 ${uploadedUrls.length} 张，累计 ${aiUploadedImageUrls.length} 张（${data.folder || ''}）`;
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = e?.message || '图片上传失败';
                }
            }
        }

        function getAiProductPayload() {
            const fullContent = document.getElementById('aiProductFullContent')?.value.trim() || '';
            const parsed = aiParseProductFromFullText(fullContent);
            const slugInput = document.getElementById('aiProductSlug');
            const manualSlug = (slugInput?.value || '').trim();
            const slug = manualSlug || aiGuessSlugFromText(fullContent);
            if (slugInput && !manualSlug && slug) slugInput.value = slug;
            const category = 'detector';
            const imageUrls = Array.isArray(aiUploadedImageUrls) ? aiUploadedImageUrls : [];
            const imageUrl = imageUrls[0] || '/cdn_assets/images/common/f1dcc87cdcca.png';

            return {
                title: parsed.title || slug || '未命名产品',
                short_name: parsed.shortName || (slug ? slug.replace(/_/g, '-').toUpperCase() : 'UNKNOWN'),
                slug: slug,
                category: category,
                image_url: imageUrl,
                detail_image_urls: imageUrls.join('\n'),
                news_urls: '',
                related_product_urls: '',
                summary: parsed.summary || '',
                context_text: fullContent,
                full_text: fullContent
            };
        }

        function buildAiProductContextText(payload) {
            return [
                payload.full_text ? `产品资料全文:\n${payload.full_text}` : '',
                payload.detail_image_urls ? `已上传产品图片链接：\n${payload.detail_image_urls}` : ''
            ].filter(Boolean).join('\n\n');
        }

        function getAiGeneratedHtml() {
            return document.getElementById('aiProductFieldsJson')?.value || '';
        }

        function setAiGeneratedHtmlOutput(text) {
            const box = document.getElementById('aiProductFieldsJson');
            if (!box) return;
            box.value = text || '';
            // Always follow latest streamed output.
            box.scrollTop = box.scrollHeight;
        }

        function buildAiPreviewHtmlWithResizeBridge(rawHtml) {
            const source = String(rawHtml || '').trim();
            if (!source) {
                return '<!doctype html><html><body style="font-family:sans-serif;padding:24px;color:#666;">预览为空</body></html>';
            }
            if (source.includes('ai-product-preview-height')) {
                return source;
            }

            const bridge = `<script>
(function () {
  function getDocHeight() {
    var body = document.body;
    var html = document.documentElement;
    if (!body || !html) return 0;
    return Math.max(
      body.scrollHeight || 0,
      body.offsetHeight || 0,
      html.clientHeight || 0,
      html.scrollHeight || 0,
      html.offsetHeight || 0
    );
  }
  function notifyHeight() {
    var h = getDocHeight();
    if (!h || !isFinite(h)) return;
    try {
      parent.postMessage({ type: 'ai-product-preview-height', height: Math.ceil(h) }, '*');
    } catch (_) {}
  }
  window.addEventListener('load', function () {
    notifyHeight();
    setTimeout(notifyHeight, 60);
    setTimeout(notifyHeight, 300);
    setTimeout(notifyHeight, 900);
  });
  window.addEventListener('resize', notifyHeight);
  if (typeof MutationObserver !== 'undefined') {
    var observer = new MutationObserver(function () { notifyHeight(); });
    observer.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: true
    });
  }
  if (typeof ResizeObserver !== 'undefined') {
    var ro = new ResizeObserver(function () { notifyHeight(); });
    if (document.documentElement) ro.observe(document.documentElement);
    if (document.body) ro.observe(document.body);
  }
  notifyHeight();
})();
<\/script>`;

            const lower = source.toLowerCase();
            const bodyCloseIdx = lower.lastIndexOf('</body>');
            if (bodyCloseIdx >= 0) {
                return source.slice(0, bodyCloseIdx) + bridge + source.slice(bodyCloseIdx);
            }
            const htmlCloseIdx = lower.lastIndexOf('</html>');
            if (htmlCloseIdx >= 0) {
                return source.slice(0, htmlCloseIdx) + bridge + source.slice(htmlCloseIdx);
            }
            return source + bridge;
        }

        function syncAiPreviewFrameHeightFromMessage(event) {
            const data = event.data || {};
            if (data.type !== 'ai-product-preview-height' || !data.height) return;
            const frames = Array.from(document.querySelectorAll('iframe[data-ai-preview-frame="1"]'));
            if (!frames.length) return;
            frames.forEach((iframe) => {
                if (event.source && iframe.contentWindow !== event.source) return;
                iframe.style.height = `${Math.max(560, Number(data.height) || 560)}px`;
            });
        }

        async function updateAiProductPreview() {
            const iframe = document.getElementById('aiProductPreviewFrame');
            if (!iframe) return;
            const html = getAiGeneratedHtml().trim();
            if (!html) return;
            iframe.srcdoc = buildAiPreviewHtmlWithResizeBridge(html);
        }

        async function readAiProductHtmlStream(res, handlers = {}, options = {}) {
            if (!res.body) {
                throw new Error('浏览器不支持流式读取');
            }
            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');
            const idleTimeoutMs = Number(options.idleTimeoutMs) || AI_STREAM_IDLE_TIMEOUT_MS;
            const totalTimeoutMs = Number(options.totalTimeoutMs) || AI_STREAM_TOTAL_TIMEOUT_MS;
            const startedAt = Date.now();
            let buffer = '';
            let htmlText = '';
            const readWithIdleTimeout = async () => {
                let timer = null;
                try {
                    return await Promise.race([
                        reader.read(),
                        new Promise((_, reject) => {
                            timer = setTimeout(() => {
                                reject(new Error(`流式输出超过 ${Math.round(idleTimeoutMs / 1000)} 秒无响应`));
                            }, idleTimeoutMs);
                        })
                    ]);
                } finally {
                    if (timer) clearTimeout(timer);
                }
            };

            try {
                while (true) {
                    if (Date.now() - startedAt > totalTimeoutMs) {
                        throw new Error(`流式生成超时（>${Math.round(totalTimeoutMs / 60000)} 分钟）`);
                    }
                    const { done, value } = await readWithIdleTimeout();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    while (true) {
                        const sep = buffer.indexOf('\n\n');
                        if (sep < 0) break;
                        const block = buffer.slice(0, sep);
                        buffer = buffer.slice(sep + 2);
                        const dataLines = block
                            .split('\n')
                            .filter(line => line.startsWith('data: '))
                            .map(line => line.slice(6));
                        if (!dataLines.length) continue;
                        const payloadText = dataLines.join('\n').trim();
                        if (!payloadText || payloadText === '[DONE]') continue;
                        let evt = null;
                        try {
                            evt = JSON.parse(payloadText);
                        } catch (e) {
                            continue;
                        }
                        if (evt.type === 'error') {
                            throw new Error(evt.error || 'AI 请求失败');
                        }
                        if (evt.type === 'retry') {
                            if (typeof handlers.onRetry === 'function') handlers.onRetry(evt);
                            continue;
                        }
                        if (evt.type === 'chunk') {
                            htmlText += evt.content || '';
                            if (typeof handlers.onChunk === 'function') handlers.onChunk(htmlText, evt);
                            continue;
                        }
                        if (evt.type === 'done') {
                            if (evt.page_html) htmlText = evt.page_html;
                            if (typeof handlers.onDone === 'function') handlers.onDone(htmlText, evt);
                        }
                    }
                }
                return htmlText;
            } catch (e) {
                try { await reader.cancel(); } catch (_) { }
                throw e;
            } finally {
                try { reader.releaseLock(); } catch (_) { }
            }
        }

        async function fetchAiProductHtmlFallback(payload) {
            const res = await fetch('/api/products/ai-generate-html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...payload,
                    context_text: buildAiProductContextText(payload)
                })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                throw new Error(data.message || '稳定模式生成失败');
            }
            return data.page_html || '';
        }

        async function fetchAiProductRevisedHtmlFallback(payload, instruction, currentHtml) {
            const res = await fetch('/api/products/ai-revise-html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: payload.title || payload.short_name || '产品页面',
                    category: payload.category,
                    image_url: payload.image_url,
                    detail_image_urls: payload.detail_image_urls,
                    news_urls: payload.news_urls,
                    related_product_urls: payload.related_product_urls,
                    summary: payload.summary,
                    context_text: buildAiProductContextText(payload),
                    instruction,
                    current_html: currentHtml
                })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                throw new Error(data.message || '稳定模式修改失败');
            }
            return data.page_html || '';
        }

        async function aiGenerateProductTemplateFields() {
            const msg = document.getElementById('aiProductMsg');
            const modifyMsg = document.getElementById('aiProductModifyMsg');
            const payload = getAiProductPayload();
            if (!payload.slug || !payload.context_text) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先填写产品资料总输入框，并提供可用的链接标识。';
                }
                return;
            }
            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = 'AI 正在流式生成完整HTML...';
            }
            if (modifyMsg) {
                modifyMsg.textContent = '';
            }
            setAiGeneratedHtmlOutput('');

            const streamController = new AbortController();
            const streamAbortTimer = setTimeout(() => {
                streamController.abort();
            }, AI_STREAM_TOTAL_TIMEOUT_MS);

            try {
                const res = await fetch('/api/products/ai-generate-html-stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: streamController.signal,
                    body: JSON.stringify({
                        ...payload,
                        context_text: buildAiProductContextText(payload)
                    })
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.message || 'AI 生成失败');
                }
                let lastPreviewAt = Date.now();
                const htmlText = await readAiProductHtmlStream(res, {
                    onRetry: (evt) => {
                        if (msg) {
                            msg.style.color = '#d97706';
                            msg.textContent = `第 ${evt.attempt || 2} 轮续写中...`;
                        }
                    },
                    onChunk: (chunkedHtml) => {
                        setAiGeneratedHtmlOutput(chunkedHtml);
                        const now = Date.now();
                        if (now - lastPreviewAt > 1500) {
                            lastPreviewAt = now;
                            updateAiProductPreview().catch(() => { });
                        }
                    },
                    onDone: (doneHtml) => {
                        setAiGeneratedHtmlOutput(doneHtml);
                    }
                }, {
                    idleTimeoutMs: AI_STREAM_IDLE_TIMEOUT_MS,
                    totalTimeoutMs: AI_STREAM_TOTAL_TIMEOUT_MS
                });

                if (!htmlText.trim()) throw new Error('AI 未返回内容');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ AI 完整HTML生成完成';
                }
                await updateAiProductPreview();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#d97706';
                    msg.textContent = `流式生成异常：${e?.message || '未知错误'}，正在自动切换稳定模式...`;
                }
                try {
                    const fallbackHtml = await fetchAiProductHtmlFallback(payload);
                    if (!fallbackHtml.trim()) throw new Error('稳定模式未返回内容');
                    setAiGeneratedHtmlOutput(fallbackHtml);
                    await updateAiProductPreview();
                    if (msg) {
                        msg.style.color = '#16a34a';
                        msg.textContent = '✓ 流式中断，已自动切换稳定模式并完成生成';
                    }
                    return;
                } catch (fallbackErr) {
                    e = fallbackErr;
                }
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || 'AI 生成失败';
                }
            } finally {
                clearTimeout(streamAbortTimer);
            }
        }

        async function aiReviseGeneratedHtml() {
            const msg = document.getElementById('aiProductMsg');
            const modifyMsg = document.getElementById('aiProductModifyMsg');
            const instruction = document.getElementById('aiProductModifyInstruction')?.value.trim() || '';
            const currentHtml = getAiGeneratedHtml().trim();
            const payload = getAiProductPayload();

            if (!currentHtml) {
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = '请先生成 HTML，再进行修改';
                }
                return;
            }
            if (!instruction) {
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = '请先输入修改意见';
                }
                return;
            }

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = 'AI 正在按意见流式修改HTML...';
            }
            if (modifyMsg) {
                modifyMsg.style.color = '#2563eb';
                modifyMsg.textContent = '流式修改中...';
            }
            setAiGeneratedHtmlOutput('');

            const streamController = new AbortController();
            const streamAbortTimer = setTimeout(() => {
                streamController.abort();
            }, AI_STREAM_TOTAL_TIMEOUT_MS);

            try {
                const res = await fetch('/api/products/ai-revise-html-stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: streamController.signal,
                    body: JSON.stringify({
                        title: payload.title || payload.short_name || '产品页面',
                        category: payload.category,
                        image_url: payload.image_url,
                        detail_image_urls: payload.detail_image_urls,
                        news_urls: payload.news_urls,
                        related_product_urls: payload.related_product_urls,
                        summary: payload.summary,
                        context_text: buildAiProductContextText(payload),
                        instruction,
                        current_html: currentHtml
                    })
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.message || 'AI 修改失败');
                }
                let lastPreviewAt = Date.now();
                const htmlText = await readAiProductHtmlStream(res, {
                    onRetry: (evt) => {
                        if (msg) {
                            msg.style.color = '#d97706';
                            msg.textContent = `修改第 ${evt.attempt || 2} 轮续写中...`;
                        }
                        if (modifyMsg) {
                            modifyMsg.style.color = '#d97706';
                            modifyMsg.textContent = `第 ${evt.attempt || 2} 轮续写中...`;
                        }
                    },
                    onChunk: (chunkedHtml) => {
                        setAiGeneratedHtmlOutput(chunkedHtml);
                        const now = Date.now();
                        if (now - lastPreviewAt > 1500) {
                            lastPreviewAt = now;
                            updateAiProductPreview().catch(() => { });
                        }
                    },
                    onDone: (doneHtml) => {
                        setAiGeneratedHtmlOutput(doneHtml);
                    }
                }, {
                    idleTimeoutMs: AI_STREAM_IDLE_TIMEOUT_MS,
                    totalTimeoutMs: AI_STREAM_TOTAL_TIMEOUT_MS
                });

                if (!htmlText.trim()) throw new Error('AI 未返回内容');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ AI 修改完成';
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#16a34a';
                    modifyMsg.textContent = '✓ 已按意见更新 HTML，可继续输入下一轮意见';
                }
                await updateAiProductPreview();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#d97706';
                    msg.textContent = `流式修改异常：${e?.message || '未知错误'}，正在自动切换稳定模式...`;
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#d97706';
                    modifyMsg.textContent = '流式异常，切换稳定模式中...';
                }
                try {
                    const fallbackHtml = await fetchAiProductRevisedHtmlFallback(payload, instruction, currentHtml);
                    if (!fallbackHtml.trim()) throw new Error('稳定模式未返回内容');
                    setAiGeneratedHtmlOutput(fallbackHtml);
                    await updateAiProductPreview();
                    if (msg) {
                        msg.style.color = '#16a34a';
                        msg.textContent = '✓ 流式中断，已自动切换稳定模式并完成修改';
                    }
                    if (modifyMsg) {
                        modifyMsg.style.color = '#16a34a';
                        modifyMsg.textContent = '✓ 稳定模式修改完成';
                    }
                    return;
                } catch (fallbackErr) {
                    e = fallbackErr;
                }
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || 'AI 修改失败';
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = e?.message || 'AI 修改失败';
                }
            } finally {
                clearTimeout(streamAbortTimer);
            }
        }

        async function aiCreateProductPage() {
            const msg = document.getElementById('aiProductMsg');
            const linkEl = document.getElementById('aiProductLink');
            const payload = getAiProductPayload();
            if (!payload.slug || !payload.context_text) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先填写产品资料总输入框，并提供可用的链接标识。';
                }
                return;
            }
            const pageHtml = getAiGeneratedHtml().trim();
            if (!pageHtml) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先点击“AI 生成完整HTML”';
                }
                return;
            }

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = '正在保存产品页面文件...';
            }
            if (linkEl) linkEl.innerHTML = '';

            try {
                const res = await fetch('/api/products/ai-create-html', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ...payload,
                        page_html: pageHtml
                    })
                });
                const data = await res.json();
                if (!data.success) throw new Error(data.message || '生成失败');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ 产品页已生成';
                }
                if (linkEl && data.link) {
                    const stamped = `${data.link}${data.link.includes('?') ? '&' : '?'}t=${Date.now()}`;
                    linkEl.innerHTML = `页面：<a href="${stamped}" target="_blank">${stamped}</a>`;
                }
                await loadProducts();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || '生成失败';
                }
            }
        }

        function bindAiProductEvents() {
            if (aiProductEventsBound) return;
            aiProductEventsBound = true;

            const fullContentInput = document.getElementById('aiProductFullContent');
            const slugInput = document.getElementById('aiProductSlug');
            if (fullContentInput && slugInput) {
                fullContentInput.addEventListener('input', () => {
                    if (slugInput.value.trim()) return;
                    const guessed = aiGuessSlugFromText(fullContentInput.value || '');
                    if (guessed) slugInput.value = guessed;
                });
            }

            const genBtn = document.getElementById('aiGenerateFieldsBtn');
            if (genBtn) genBtn.addEventListener('click', aiGenerateProductTemplateFields);
            const createBtn = document.getElementById('aiCreateProductBtn');
            if (createBtn) createBtn.addEventListener('click', aiCreateProductPage);
            const modifyBtn = document.getElementById('aiProductModifyBtn');
            if (modifyBtn) modifyBtn.addEventListener('click', aiReviseGeneratedHtml);
            const uploadBtn = document.getElementById('aiProductUploadImagesBtn');
            const imagesInput = document.getElementById('aiProductImagesInput');
            if (uploadBtn && imagesInput) {
                uploadBtn.addEventListener('click', () => imagesInput.click());
                imagesInput.addEventListener('change', async () => {
                    const files = imagesInput.files;
                    await uploadAiProductImages(files);
                    imagesInput.value = '';
                });
            }

            if (!window.__aiProductPreviewHeightBound) {
                window.addEventListener('message', syncAiPreviewFrameHeightFromMessage);
                window.__aiProductPreviewHeightBound = true;
            }

            ['aiProductSlug', 'aiProductFullContent', 'aiProductFieldsJson']
                .forEach(id => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.addEventListener('change', () => { updateAiProductPreview().catch(() => { }); });
                });

            const generatedHtmlBox = document.getElementById('aiProductFieldsJson');
            if (generatedHtmlBox) {
                generatedHtmlBox.addEventListener('input', () => { updateAiProductPreview().catch(() => { }); });
            }

            renderAiUploadedImages();
        }

        function renderBioAiUploadedImages() {
            const list = document.getElementById('bioAiProductImagesList');
            if (!list) return;
            if (!bioAiUploadedImageUrls.length) {
                list.innerHTML = '<div style="font-size:12px; color:#94a3b8;">尚未上传图片</div>';
                return;
            }
            list.innerHTML = bioAiUploadedImageUrls.map((url, index) => `
                <div style="border:1px solid #e2e8f0; border-radius:8px; padding:8px; background:#fff;">
                    <img src="${url}" alt="bio-product-image-${index + 1}" style="width:100%; height:90px; object-fit:cover; border-radius:6px; background:#f8fafc;">
                    <div style="margin-top:6px; font-size:11px; color:#475569; overflow-wrap:anywhere; word-break:break-word;">${escapeHtml(url)}</div>
                </div>
            `).join('');
        }

        async function uploadBioAiProductImages(files) {
            const msg = document.getElementById('bioAiProductImagesMsg');
            const fullContent = document.getElementById('bioAiProductFullContent')?.value || '';
            const parsed = aiParseProductFromFullText(fullContent);
            const slugInput = document.getElementById('bioAiProductSlug');
            const slugValue = (slugInput?.value || '').trim() || aiGuessSlugFromText(fullContent);
            const shortName = parsed.shortName || '';

            if (!slugValue) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = '请先在总输入框写“产品名称”，或手动填写链接标识后再上传图片。';
                }
                return;
            }
            if (!/^[a-z0-9_]+$/.test(slugValue)) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = '链接标识仅支持小写字母、数字、下划线。';
                }
                return;
            }
            if (slugInput && !slugInput.value.trim()) slugInput.value = slugValue;
            if (!files || !files.length) return;

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = `正在上传 ${files.length} 张图片...`;
            }

            const formData = new FormData();
            formData.append('slug', slugValue);
            formData.append('short_name', shortName);
            Array.from(files).forEach(file => formData.append('files', file));

            try {
                const res = await fetch('/api/bio-products/ai-upload-images', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '上传失败');
                }
                const uploadedUrls = Array.isArray(data.urls) ? data.urls : [];
                const merged = Array.isArray(bioAiUploadedImageUrls) ? [...bioAiUploadedImageUrls] : [];
                uploadedUrls.forEach(url => {
                    const v = String(url || '').trim();
                    if (!v) return;
                    if (!merged.includes(v)) merged.push(v);
                });
                bioAiUploadedImageUrls = merged;
                renderBioAiUploadedImages();
                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = `✓ 本次上传 ${uploadedUrls.length} 张，累计 ${bioAiUploadedImageUrls.length} 张（${data.folder || ''}）`;
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc2626';
                    msg.textContent = e?.message || '图片上传失败';
                }
            }
        }

        function getBioAiProductPayload() {
            const fullContent = document.getElementById('bioAiProductFullContent')?.value.trim() || '';
            const parsed = aiParseProductFromFullText(fullContent);
            const slugInput = document.getElementById('bioAiProductSlug');
            const manualSlug = (slugInput?.value || '').trim();
            const slug = manualSlug || aiGuessSlugFromText(fullContent);
            if (slugInput && !manualSlug && slug) slugInput.value = slug;
            const category = 'sensor';
            const imageUrls = Array.isArray(bioAiUploadedImageUrls) ? bioAiUploadedImageUrls : [];
            const imageUrl = imageUrls[0] || '/cdn_assets/images/common/f1dcc87cdcca.png';

            return {
                title: parsed.title || slug || '未命名产品',
                short_name: parsed.shortName || (slug ? slug.replace(/_/g, '-').toUpperCase() : 'UNKNOWN'),
                slug: slug,
                category: category,
                image_url: imageUrl,
                detail_image_urls: imageUrls.join('\n'),
                news_urls: '',
                related_product_urls: '',
                summary: parsed.summary || '',
                context_text: fullContent,
                full_text: fullContent
            };
        }

        function getBioAiGeneratedHtml() {
            return document.getElementById('bioAiProductFieldsJson')?.value || '';
        }

        function setBioAiGeneratedHtmlOutput(text) {
            const box = document.getElementById('bioAiProductFieldsJson');
            if (!box) return;
            box.value = text || '';
            box.scrollTop = box.scrollHeight;
        }

        async function updateBioAiProductPreview() {
            const iframe = document.getElementById('bioAiProductPreviewFrame');
            if (!iframe) return;
            const html = getBioAiGeneratedHtml().trim();
            if (!html) return;
            iframe.srcdoc = buildAiPreviewHtmlWithResizeBridge(html);
        }

        async function fetchBioAiProductHtmlFallback(payload) {
            const res = await fetch('/api/bio-products/ai-generate-html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...payload,
                    context_text: buildAiProductContextText(payload)
                })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                throw new Error(data.message || '稳定模式生成失败');
            }
            return data.page_html || '';
        }

        async function fetchBioAiProductRevisedHtmlFallback(payload, instruction, currentHtml) {
            const res = await fetch('/api/bio-products/ai-revise-html', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: payload.title || payload.short_name || '产品页面',
                    category: payload.category,
                    image_url: payload.image_url,
                    detail_image_urls: payload.detail_image_urls,
                    news_urls: payload.news_urls,
                    related_product_urls: payload.related_product_urls,
                    summary: payload.summary,
                    context_text: buildAiProductContextText(payload),
                    instruction,
                    current_html: currentHtml
                })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.success) {
                throw new Error(data.message || '稳定模式修改失败');
            }
            return data.page_html || '';
        }

        async function aiGenerateBioProductTemplateFields() {
            const msg = document.getElementById('bioAiProductMsg');
            const modifyMsg = document.getElementById('bioAiProductModifyMsg');
            const payload = getBioAiProductPayload();
            if (!payload.slug || !payload.context_text) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先填写产品资料总输入框，并提供可用的链接标识。';
                }
                return;
            }
            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = 'AI 正在流式生成完整HTML...';
            }
            if (modifyMsg) {
                modifyMsg.textContent = '';
            }
            setBioAiGeneratedHtmlOutput('');

            const streamController = new AbortController();
            const streamAbortTimer = setTimeout(() => {
                streamController.abort();
            }, AI_STREAM_TOTAL_TIMEOUT_MS);

            try {
                const res = await fetch('/api/bio-products/ai-generate-html-stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: streamController.signal,
                    body: JSON.stringify({
                        ...payload,
                        context_text: buildAiProductContextText(payload)
                    })
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.message || 'AI 生成失败');
                }
                let lastPreviewAt = Date.now();
                const htmlText = await readAiProductHtmlStream(res, {
                    onRetry: (evt) => {
                        if (msg) {
                            msg.style.color = '#d97706';
                            msg.textContent = `第 ${evt.attempt || 2} 轮续写中...`;
                        }
                    },
                    onChunk: (chunkedHtml) => {
                        setBioAiGeneratedHtmlOutput(chunkedHtml);
                        const now = Date.now();
                        if (now - lastPreviewAt > 1500) {
                            lastPreviewAt = now;
                            updateBioAiProductPreview().catch(() => { });
                        }
                    },
                    onDone: (doneHtml) => {
                        setBioAiGeneratedHtmlOutput(doneHtml);
                    }
                }, {
                    idleTimeoutMs: AI_STREAM_IDLE_TIMEOUT_MS,
                    totalTimeoutMs: AI_STREAM_TOTAL_TIMEOUT_MS
                });

                if (!htmlText.trim()) throw new Error('AI 未返回内容');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ AI 完整HTML生成完成';
                }
                await updateBioAiProductPreview();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#d97706';
                    msg.textContent = `流式生成异常：${e?.message || '未知错误'}，正在自动切换稳定模式...`;
                }
                try {
                    const fallbackHtml = await fetchBioAiProductHtmlFallback(payload);
                    if (!fallbackHtml.trim()) throw new Error('稳定模式未返回内容');
                    setBioAiGeneratedHtmlOutput(fallbackHtml);
                    await updateBioAiProductPreview();
                    if (msg) {
                        msg.style.color = '#16a34a';
                        msg.textContent = '✓ 流式中断，已自动切换稳定模式并完成生成';
                    }
                    return;
                } catch (fallbackErr) {
                    e = fallbackErr;
                }
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || 'AI 生成失败';
                }
            } finally {
                clearTimeout(streamAbortTimer);
            }
        }

        async function aiReviseBioGeneratedHtml() {
            const msg = document.getElementById('bioAiProductMsg');
            const modifyMsg = document.getElementById('bioAiProductModifyMsg');
            const instruction = document.getElementById('bioAiProductModifyInstruction')?.value.trim() || '';
            const currentHtml = getBioAiGeneratedHtml().trim();
            const payload = getBioAiProductPayload();

            if (!currentHtml) {
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = '请先生成 HTML，再进行修改';
                }
                return;
            }
            if (!instruction) {
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = '请先输入修改意见';
                }
                return;
            }

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = 'AI 正在按意见流式修改HTML...';
            }
            if (modifyMsg) {
                modifyMsg.style.color = '#2563eb';
                modifyMsg.textContent = '流式修改中...';
            }
            setBioAiGeneratedHtmlOutput('');

            const streamController = new AbortController();
            const streamAbortTimer = setTimeout(() => {
                streamController.abort();
            }, AI_STREAM_TOTAL_TIMEOUT_MS);

            try {
                const res = await fetch('/api/bio-products/ai-revise-html-stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    signal: streamController.signal,
                    body: JSON.stringify({
                        title: payload.title || payload.short_name || '产品页面',
                        category: payload.category,
                        image_url: payload.image_url,
                        detail_image_urls: payload.detail_image_urls,
                        news_urls: payload.news_urls,
                        related_product_urls: payload.related_product_urls,
                        summary: payload.summary,
                        context_text: buildAiProductContextText(payload),
                        instruction,
                        current_html: currentHtml
                    })
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    throw new Error(data.message || 'AI 修改失败');
                }
                let lastPreviewAt = Date.now();
                const htmlText = await readAiProductHtmlStream(res, {
                    onRetry: (evt) => {
                        if (msg) {
                            msg.style.color = '#d97706';
                            msg.textContent = `修改第 ${evt.attempt || 2} 轮续写中...`;
                        }
                        if (modifyMsg) {
                            modifyMsg.style.color = '#d97706';
                            modifyMsg.textContent = `第 ${evt.attempt || 2} 轮续写中...`;
                        }
                    },
                    onChunk: (chunkedHtml) => {
                        setBioAiGeneratedHtmlOutput(chunkedHtml);
                        const now = Date.now();
                        if (now - lastPreviewAt > 1500) {
                            lastPreviewAt = now;
                            updateBioAiProductPreview().catch(() => { });
                        }
                    },
                    onDone: (doneHtml) => {
                        setBioAiGeneratedHtmlOutput(doneHtml);
                    }
                }, {
                    idleTimeoutMs: AI_STREAM_IDLE_TIMEOUT_MS,
                    totalTimeoutMs: AI_STREAM_TOTAL_TIMEOUT_MS
                });

                if (!htmlText.trim()) throw new Error('AI 未返回内容');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ AI 修改完成';
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#16a34a';
                    modifyMsg.textContent = '✓ 已按意见更新 HTML，可继续输入下一轮意见';
                }
                await updateBioAiProductPreview();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#d97706';
                    msg.textContent = `流式修改异常：${e?.message || '未知错误'}，正在自动切换稳定模式...`;
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#d97706';
                    modifyMsg.textContent = '流式异常，切换稳定模式中...';
                }
                try {
                    const fallbackHtml = await fetchBioAiProductRevisedHtmlFallback(payload, instruction, currentHtml);
                    if (!fallbackHtml.trim()) throw new Error('稳定模式未返回内容');
                    setBioAiGeneratedHtmlOutput(fallbackHtml);
                    await updateBioAiProductPreview();
                    if (msg) {
                        msg.style.color = '#16a34a';
                        msg.textContent = '✓ 流式中断，已自动切换稳定模式并完成修改';
                    }
                    if (modifyMsg) {
                        modifyMsg.style.color = '#16a34a';
                        modifyMsg.textContent = '✓ 稳定模式修改完成';
                    }
                    return;
                } catch (fallbackErr) {
                    e = fallbackErr;
                }
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || 'AI 修改失败';
                }
                if (modifyMsg) {
                    modifyMsg.style.color = '#dc3545';
                    modifyMsg.textContent = e?.message || 'AI 修改失败';
                }
            } finally {
                clearTimeout(streamAbortTimer);
            }
        }

        async function aiCreateBioProductPage() {
            const msg = document.getElementById('bioAiProductMsg');
            const linkEl = document.getElementById('bioAiProductLink');
            const payload = getBioAiProductPayload();
            if (!payload.slug || !payload.context_text) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先填写产品资料总输入框，并提供可用的链接标识。';
                }
                return;
            }
            const pageHtml = getBioAiGeneratedHtml().trim();
            if (!pageHtml) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请先点击“AI 生成完整HTML”';
                }
                return;
            }

            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = '正在保存产品页面文件...';
            }
            if (linkEl) linkEl.innerHTML = '';

            try {
                const res = await fetch('/api/bio-products/ai-create-html', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ...payload,
                        page_html: pageHtml
                    })
                });
                const data = await res.json();
                if (!data.success) throw new Error(data.message || '生成失败');

                if (msg) {
                    msg.style.color = '#16a34a';
                    msg.textContent = '✓ 产品页已生成';
                }
                if (linkEl && data.link) {
                    const stamped = `${data.link}${data.link.includes('?') ? '&' : '?'}t=${Date.now()}`;
                    linkEl.innerHTML = `页面：<a href="${stamped}" target="_blank">${stamped}</a>`;
                }
                await loadBioProducts();
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || '生成失败';
                }
            }
        }

        function bindBioAiProductEvents() {
            if (bioAiProductEventsBound) return;
            bioAiProductEventsBound = true;

            const fullContentInput = document.getElementById('bioAiProductFullContent');
            const slugInput = document.getElementById('bioAiProductSlug');
            if (fullContentInput && slugInput) {
                fullContentInput.addEventListener('input', () => {
                    if (slugInput.value.trim()) return;
                    const guessed = aiGuessSlugFromText(fullContentInput.value || '');
                    if (guessed) slugInput.value = guessed;
                });
            }

            const genBtn = document.getElementById('bioAiGenerateFieldsBtn');
            if (genBtn) genBtn.addEventListener('click', aiGenerateBioProductTemplateFields);
            const createBtn = document.getElementById('bioAiCreateProductBtn');
            if (createBtn) createBtn.addEventListener('click', aiCreateBioProductPage);
            const modifyBtn = document.getElementById('bioAiProductModifyBtn');
            if (modifyBtn) modifyBtn.addEventListener('click', aiReviseBioGeneratedHtml);
            const uploadBtn = document.getElementById('bioAiProductUploadImagesBtn');
            const imagesInput = document.getElementById('bioAiProductImagesInput');
            if (uploadBtn && imagesInput) {
                uploadBtn.addEventListener('click', () => imagesInput.click());
                imagesInput.addEventListener('change', async () => {
                    const files = imagesInput.files;
                    await uploadBioAiProductImages(files);
                    imagesInput.value = '';
                });
            }

            if (!window.__aiProductPreviewHeightBound) {
                window.addEventListener('message', syncAiPreviewFrameHeightFromMessage);
                window.__aiProductPreviewHeightBound = true;
            }

            ['bioAiProductSlug', 'bioAiProductFullContent', 'bioAiProductFieldsJson']
                .forEach(id => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    el.addEventListener('change', () => { updateBioAiProductPreview().catch(() => { }); });
                });

            const generatedHtmlBox = document.getElementById('bioAiProductFieldsJson');
            if (generatedHtmlBox) {
                generatedHtmlBox.addEventListener('input', () => { updateBioAiProductPreview().catch(() => { }); });
            }

            renderBioAiUploadedImages();
        }

        function escapeAttr(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }

        function normalizeRelatedNewsLinks(links) {
            const list = Array.isArray(links) ? links : [];
            const out = [];
            list.forEach(item => {
                const link = String(item || '').trim();
                if (!link || out.includes(link)) return;
                out.push(link);
            });
            return out.slice(0, 2);
        }

        function buildNewsOptionsHtml(newsItems, selected) {
            const selectedLink = String(selected || '');
            const base = '<option value="">默认（最新两条）</option>';
            const options = (newsItems || []).map(item => {
                const link = String(item.link || '');
                const date = String(item.date || '');
                const title = String(item.title || item.link || '');
                const label = `${date ? `[${date}] ` : ''}${title}`;
                return `<option value="${escapeAttr(link)}" ${selectedLink === link ? 'selected' : ''}>${escapeHtml(label)}</option>`;
            }).join('');
            return base + options;
        }

        function triggerProductCodeDownload(productId, endpoint = '/api/products/code/download') {
            if (!productId) return;
            const url = `${endpoint}?id=${encodeURIComponent(productId)}`;
            window.open(url, '_blank');
        }

        async function uploadProductCodeFile(
            productId,
            file,
            endpoint = '/api/products/code/upload',
            messageSelector = '.product-code-action-msg',
            tableBodyId = 'productsTableBody'
        ) {
            const tbody = document.getElementById(tableBodyId);
            const msgEl = tbody
                ? Array.from(tbody.querySelectorAll(messageSelector)).find(el => String(el.dataset.id) === String(productId))
                : null;
            if (!file) return;
            if (!/\.html?$/i.test(file.name || '')) {
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = '请上传 .html 文件';
                }
                return;
            }
            if (msgEl) {
                msgEl.style.color = '#666';
                msgEl.textContent = '上传中...';
            }
            try {
                const formData = new FormData();
                formData.append('id', productId);
                formData.append('file', file);
                const res = await fetch(endpoint, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '上传失败');
                }
                if (msgEl) {
                    msgEl.style.color = '#2e7d32';
                    msgEl.textContent = '✓ 上传覆盖成功';
                }
            } catch (e) {
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = e?.message || '上传失败';
                }
            }
        }

        async function deleteProductItem(productId) {
            if (!productId) return;
            const product = (productsData || []).find(item => String(item?.id || '') === String(productId));
            const productName = String(product?.name || productId);
            const tbody = document.getElementById('productsTableBody');
            const msgEl = tbody
                ? Array.from(tbody.querySelectorAll('.product-code-action-msg')).find(el => String(el.dataset.id) === String(productId))
                : null;

            if (!await showGlobalConfirm(`确定删除产品“${productName}”吗？这会直接删除产品页面代码，且无法撤销。`)) {
                return;
            }

            if (msgEl) {
                msgEl.style.color = '#666';
                msgEl.textContent = '删除中...';
            }

            try {
                const res = await fetch('/api/products/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: productId })
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '删除失败');
                }
                await loadProducts();
            } catch (e) {
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = e?.message || '删除失败';
                } else {
                    alert(e?.message || '删除失败');
                }
            }
        }

        async function loadProducts() {
            const tbody = document.getElementById('productsTableBody');
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding: 20px;">加载中...</td></tr>';

            try {
                const [res, newsRes] = await Promise.all([
                    fetch('/api/products/with-settings'),
                    fetch('/api/news/list')
                ]);
                const data = await res.json();
                const newsData = await newsRes.json();
                const rawProducts = data.products || [];
                const newsItems = (newsData.items || []).filter(item => !item.hidden);
                productsData = rawProducts.filter(p => {
                    const pid = String(p?.id || '');
                    if (!pid) return false;
                    if (pid === 'all-products') return false;
                    if (pid.startsWith('../biosensing/')) return false;
                    if (pid.startsWith('../customization/')) return true;
                    return !pid.startsWith('../');
                });

                if (productsData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" class="no-data">暂无产品数据</td></tr>';
                    return;
                }

                tbody.innerHTML = productsData.map(p => {
                    const relatedNews = normalizeRelatedNewsLinks(p.relatedNews || []);
                    const news1 = relatedNews[0] || '';
                    const news2 = relatedNews[1] || '';
                    const pidEsc = escapeHtml(p.id);
                    return `
                    <tr style="${p.hidden ? 'opacity: 0.5;' : ''}">
                        <td class="cell-image">
                            <img src="${p.image}" alt="${p.name}" 
                                onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 60 40%22><rect fill=%22%23eee%22 width=%2260%22 height=%2240%22/><text x=%2230%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%228%22>无图</text></svg>'">
                        </td>
                        <td class="cell-name"><strong>${p.name}</strong></td>
                        <td class="cell-visible">
                            <label class="toggle-switch" style="margin: 0;">
                                <input type="checkbox" class="product-list-visible" data-id="${escapeHtml(p.id)}" ${!p.hidden ? 'checked' : ''}>
                                <span class="toggle-slider"></span>
                            </label>
                        </td>
                        <td class="cell-title">
                            <input type="text" class="form-control product-card-title" data-id="${escapeHtml(p.id)}"
                                value="${escapeHtml(p.cardTitle || '')}"
                                placeholder="${escapeHtml(p.name || '')}">
                        </td>
                        <td class="cell-image-config">
                            <input type="text" class="form-control product-card-image" data-id="${escapeHtml(p.id)}"
                                value="${escapeHtml(p.cardImage || '')}"
                                placeholder="${escapeHtml(p.image || '')}">
                            <div style="display:flex; gap:8px; align-items:center; margin-top:6px;">
                                <button type="button" class="btn-sm product-card-image-upload-btn" data-id="${escapeHtml(p.id)}">本地上传</button>
                                <input type="file" class="product-card-image-file" data-id="${escapeHtml(p.id)}" accept="image/png,image/jpeg,image/webp" style="display:none;">
                                <span class="product-card-image-msg" data-id="${escapeHtml(p.id)}" style="font-size:11px; color:#666;"></span>
                            </div>
                        </td>
                        <td class="cell-summary">
                            <textarea class="form-control product-card-summary" data-id="${pidEsc}" rows="2"
                                placeholder="${escapeHtml(p.description || '')}">${escapeHtml(p.cardSummary || '')}</textarea>
                        </td>
                        <td class="cell-fileid"><code style="background: #f5f5f5; padding: 2px 6px; border-radius: 4px;">${p.id}</code></td>
                        <td class="cell-news">
                            <select class="form-control product-related-news-select" data-id="${pidEsc}" data-slot="1" style="margin-bottom:6px;">
                                ${buildNewsOptionsHtml(newsItems, news1)}
                            </select>
                            <select class="form-control product-related-news-select" data-id="${pidEsc}" data-slot="2">
                                ${buildNewsOptionsHtml(newsItems, news2)}
                            </select>
                        </td>
                        <td class="cell-actions">
                            <div class="action-wrap">
                                <button type="button" class="btn-sm product-download-code-btn" data-id="${pidEsc}">下载代码</button>
                                <button type="button" class="btn-sm product-upload-code-btn" data-id="${pidEsc}">上传覆盖代码</button>
                                <button type="button" class="btn-sm btn-danger product-delete-btn" data-id="${pidEsc}">删除产品</button>
                                <input type="file" class="product-upload-code-file" data-id="${pidEsc}" accept=".html,text/html" style="display:none;">
                            </div>
                            <div class="product-code-action-msg" data-id="${pidEsc}" style="font-size:11px; color:#666; margin-top:6px;"></div>
                        </td>
                    </tr>
                `;
                }).join('');

                tbody.querySelectorAll('.product-card-title').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveProductSetting(e.target.dataset.id, 'cardTitle', e.target.value);
                    });
                });
                tbody.querySelectorAll('.product-card-image').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveProductSetting(e.target.dataset.id, 'cardImage', e.target.value);
                    });
                });
                tbody.querySelectorAll('.product-card-summary').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveProductSetting(e.target.dataset.id, 'cardSummary', e.target.value);
                    });
                });
                tbody.querySelectorAll('.product-list-visible').forEach(checkbox => {
                    checkbox.addEventListener('change', (e) => {
                        const hidden = !e.target.checked;
                        const row = e.target.closest('tr');
                        if (row) row.style.opacity = hidden ? '0.5' : '1';
                        const product = productsData.find(p => String(p.id) === String(e.target.dataset.id));
                        if (product) product.hidden = hidden;
                        saveProductSetting(e.target.dataset.id, 'hidden', hidden);
                        renderIndustrySettings();
                    });
                });
                tbody.querySelectorAll('.product-card-image-upload-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const pid = btn.dataset.id;
                        const fileInput = tbody.querySelector(`.product-card-image-file[data-id="${pid}"]`);
                        if (fileInput) fileInput.click();
                    });
                });
                tbody.querySelectorAll('.product-card-image-file').forEach(input => {
                    input.addEventListener('change', async (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        const pid = e.target.dataset.id;
                        await uploadProductCardImage(pid, file);
                        e.target.value = '';
                    });
                });
                tbody.querySelectorAll('.product-related-news-select').forEach(select => {
                    select.addEventListener('change', async (e) => {
                        const pid = e.target.dataset.id;
                        const row = e.target.closest('tr');
                        if (!pid || !row) return;
                        const values = Array.from(row.querySelectorAll('.product-related-news-select'))
                            .map(el => String(el.value || '').trim())
                            .filter(Boolean);
                        const deduped = values.filter((v, idx) => values.indexOf(v) === idx).slice(0, 2);
                        await saveProductSetting(pid, 'relatedNews', deduped);
                    });
                });
                tbody.querySelectorAll('.product-download-code-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        triggerProductCodeDownload(btn.dataset.id);
                    });
                });
                tbody.querySelectorAll('.product-upload-code-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const pid = btn.dataset.id;
                        const fileInput = Array.from(tbody.querySelectorAll('.product-upload-code-file'))
                            .find(el => String(el.dataset.id) === String(pid));
                        if (fileInput) fileInput.click();
                    });
                });
                tbody.querySelectorAll('.product-upload-code-file').forEach(input => {
                    input.addEventListener('change', async (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        const pid = e.target.dataset.id;
                        await uploadProductCodeFile(pid, file);
                        e.target.value = '';
                    });
                });
                tbody.querySelectorAll('.product-delete-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        deleteProductItem(btn.dataset.id);
                    });
                });
                // Update menu preview
                updateMenuPreview();
                // Update industry filter settings
                await loadIndustryFilters();
                // Load recommendations
                loadRecommendations();

            } catch (e) {
                console.error('Load products error:', e);
                tbody.innerHTML = '<tr><td colspan="9" class="no-data">加载失败，请刷新重试</td></tr>';
            }
        }

        async function loadBioProducts() {
            const tbody = document.getElementById('bioProductsTableBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding: 20px;">加载中...</td></tr>';

            try {
                const res = await fetch('/api/bio-products/with-settings');
                const data = await res.json();
                const rawProducts = Array.isArray(data.products) ? data.products : [];
                bioProductsData = rawProducts.filter(p => String(p?.id || '').startsWith('../biosensing/'));

                let newsItems = [];
                try {
                    const newsRes = await fetch('/api/news/list');
                    if (newsRes.ok) {
                        const newsData = await newsRes.json();
                        newsItems = (newsData.items || []).filter(item => !item.hidden);
                    }
                } catch (_) {
                    newsItems = [];
                }

                if (bioProductsData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" class="no-data">暂无生物产品数据</td></tr>';
                    return;
                }

                tbody.innerHTML = bioProductsData.map(p => {
                    const relatedNews = normalizeRelatedNewsLinks(p.relatedNews || []);
                    const news1 = relatedNews[0] || '';
                    const news2 = relatedNews[1] || '';
                    const pidEsc = escapeHtml(p.id);
                    return `
                    <tr style="${p.hidden ? 'opacity: 0.5;' : ''}">
                        <td class="cell-image">
                            <img src="${p.image}" alt="${p.name}" 
                                onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 60 40%22><rect fill=%22%23eee%22 width=%2260%22 height=%2240%22/><text x=%2230%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%228%22>无图</text></svg>'">
                        </td>
                        <td class="cell-name"><strong>${p.name}</strong></td>
                        <td class="cell-visible">
                            <label class="toggle-switch" style="margin: 0;">
                                <input type="checkbox" class="bio-product-list-visible" data-id="${pidEsc}" ${!p.hidden ? 'checked' : ''}>
                                <span class="toggle-slider"></span>
                            </label>
                        </td>
                        <td class="cell-title">
                            <input type="text" class="form-control bio-product-card-title" data-id="${pidEsc}"
                                value="${escapeHtml(p.cardTitle || '')}"
                                placeholder="${escapeHtml(p.name || '')}">
                        </td>
                        <td class="cell-image-config">
                            <input type="text" class="form-control bio-product-card-image" data-id="${pidEsc}"
                                value="${escapeHtml(p.cardImage || '')}"
                                placeholder="${escapeHtml(p.image || '')}">
                            <div style="display:flex; gap:8px; align-items:center; margin-top:6px;">
                                <button type="button" class="btn-sm bio-product-card-image-upload-btn" data-id="${pidEsc}">本地上传</button>
                                <input type="file" class="bio-product-card-image-file" data-id="${pidEsc}" accept="image/png,image/jpeg,image/webp" style="display:none;">
                                <span class="bio-product-card-image-msg" data-id="${pidEsc}" style="font-size:11px; color:#666;"></span>
                            </div>
                        </td>
                        <td class="cell-summary">
                            <textarea class="form-control bio-product-card-summary" data-id="${pidEsc}" rows="2"
                                placeholder="${escapeHtml(p.description || '')}">${escapeHtml(p.cardSummary || '')}</textarea>
                        </td>
                        <td class="cell-fileid"><code style="background: #f5f5f5; padding: 2px 6px; border-radius: 4px;">${p.id}</code></td>
                        <td class="cell-news">
                            <select class="form-control bio-product-related-news-select" data-id="${pidEsc}" data-slot="1" style="margin-bottom:6px;">
                                ${buildNewsOptionsHtml(newsItems, news1)}
                            </select>
                            <select class="form-control bio-product-related-news-select" data-id="${pidEsc}" data-slot="2">
                                ${buildNewsOptionsHtml(newsItems, news2)}
                            </select>
                        </td>
                        <td class="cell-actions">
                            <div class="action-wrap">
                                <button type="button" class="btn-sm bio-product-download-code-btn" data-id="${pidEsc}">下载代码</button>
                                <button type="button" class="btn-sm bio-product-upload-code-btn" data-id="${pidEsc}">上传覆盖代码</button>
                                <input type="file" class="bio-product-upload-code-file" data-id="${pidEsc}" accept=".html,text/html" style="display:none;">
                            </div>
                            <div class="bio-product-code-action-msg" data-id="${pidEsc}" style="font-size:11px; color:#666; margin-top:6px;"></div>
                        </td>
                    </tr>
                `;
                }).join('');

                tbody.querySelectorAll('.bio-product-card-title').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveBioProductSetting(e.target.dataset.id, 'cardTitle', e.target.value);
                    });
                });
                tbody.querySelectorAll('.bio-product-card-image').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveBioProductSetting(e.target.dataset.id, 'cardImage', e.target.value);
                    });
                });
                tbody.querySelectorAll('.bio-product-card-summary').forEach(input => {
                    input.addEventListener('change', (e) => {
                        saveBioProductSetting(e.target.dataset.id, 'cardSummary', e.target.value);
                    });
                });
                tbody.querySelectorAll('.bio-product-list-visible').forEach(checkbox => {
                    checkbox.addEventListener('change', (e) => {
                        const hidden = !e.target.checked;
                        const row = e.target.closest('tr');
                        if (row) row.style.opacity = hidden ? '0.5' : '1';
                        const product = bioProductsData.find(p => String(p.id) === String(e.target.dataset.id));
                        if (product) product.hidden = hidden;
                        saveBioProductSetting(e.target.dataset.id, 'hidden', hidden);
                        renderBioIndustrySettings();
                    });
                });
                tbody.querySelectorAll('.bio-product-card-image-upload-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const pid = btn.dataset.id;
                        const fileInput = tbody.querySelector(`.bio-product-card-image-file[data-id="${pid}"]`);
                        if (fileInput) fileInput.click();
                    });
                });
                tbody.querySelectorAll('.bio-product-card-image-file').forEach(input => {
                    input.addEventListener('change', async (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        await uploadBioProductCardImage(e.target.dataset.id, file);
                        e.target.value = '';
                    });
                });
                tbody.querySelectorAll('.bio-product-related-news-select').forEach(select => {
                    select.addEventListener('change', async (e) => {
                        const pid = e.target.dataset.id;
                        const row = e.target.closest('tr');
                        if (!pid || !row) return;
                        const values = Array.from(row.querySelectorAll('.bio-product-related-news-select'))
                            .map(el => String(el.value || '').trim())
                            .filter(Boolean);
                        const deduped = values.filter((v, idx) => values.indexOf(v) === idx).slice(0, 2);
                        await saveBioProductSetting(pid, 'relatedNews', deduped);
                    });
                });
                tbody.querySelectorAll('.bio-product-download-code-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        triggerProductCodeDownload(btn.dataset.id, '/api/bio-products/code/download');
                    });
                });
                tbody.querySelectorAll('.bio-product-upload-code-btn').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const pid = btn.dataset.id;
                        const fileInput = Array.from(tbody.querySelectorAll('.bio-product-upload-code-file'))
                            .find(el => String(el.dataset.id) === String(pid));
                        if (fileInput) fileInput.click();
                    });
                });
                tbody.querySelectorAll('.bio-product-upload-code-file').forEach(input => {
                    input.addEventListener('change', async (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        const pid = e.target.dataset.id;
                        await uploadProductCodeFile(pid, file, '/api/bio-products/code/upload', '.bio-product-code-action-msg', 'bioProductsTableBody');
                        e.target.value = '';
                    });
                });
                await loadBioIndustryFilters();
            } catch (e) {
                console.error('Load bio products error:', e);
                tbody.innerHTML = '<tr><td colspan="9" class="no-data">加载失败，请刷新重试</td></tr>';
            }
        }

        async function saveBioProductSetting(productId, field, value) {
            try {
                const res = await fetch('/api/bio-products/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: productId,
                        [field]: value
                    })
                });
                const result = await res.json();
                if (!result.success) {
                    console.error('Save bio product setting failed:', result.message);
                    return;
                }
                const target = bioProductsData.find(p => String(p.id) === String(productId));
                if (target) target[field] = value;
            } catch (e) {
                console.error('Save bio product setting error:', e);
            }
        }

        async function uploadBioProductCardImage(productId, file) {
            const tbody = document.getElementById('bioProductsTableBody');
            const msgEl = tbody ? tbody.querySelector(`.bio-product-card-image-msg[data-id="${productId}"]`) : null;
            const imageInput = tbody ? tbody.querySelector(`.bio-product-card-image[data-id="${productId}"]`) : null;
            if (msgEl) {
                msgEl.style.color = '#666';
                msgEl.textContent = '上传中...';
            }

            try {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/bio-products/card-image/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await res.json();
                if (!result.success || !result.url) {
                    throw new Error(result.message || '上传失败');
                }

                if (imageInput) {
                    imageInput.value = result.url;
                }
                await saveBioProductSetting(productId, 'cardImage', result.url);

                if (msgEl) {
                    msgEl.style.color = '#2e7d32';
                    msgEl.textContent = '✓ 上传并保存成功';
                }
            } catch (e) {
                console.error('Upload bio product card image error:', e);
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = '上传失败';
                }
            }
        }

        async function loadBioIndustryFilters() {
            try {
                const res = await fetch('/api/bio-products/industry-filters');
                const data = await res.json();
                bioIndustryFiltersData = Array.isArray(data.categories) ? data.categories : [];
                renderBioIndustrySettings();
            } catch (e) {
                console.error('Load bio industry filters error:', e);
                const editor = document.getElementById('bioIndustryFilterEditor');
                if (editor) {
                    editor.innerHTML = '<div style="color:#dc3545;">加载领域分类失败，请刷新重试</div>';
                }
            }
        }

        function renderBioIndustrySettings() {
            const filterEditor = document.getElementById('bioIndustryFilterEditor');
            const assignEditor = document.getElementById('bioIndustryAssignEditor');
            if (!filterEditor || !assignEditor) return;
            const visibleProducts = bioProductsData.filter(p => !p.hidden);

            const rowsHtml = bioIndustryFiltersData.map((item, idx) => `
                <tr data-index="${idx}" style="border-bottom: 1px solid #eee;">
                    <td style="padding: 8px;"><code>${escapeIndustryHtml(item.key)}</code></td>
                    <td style="padding: 8px;">
                        <input type="text" class="form-control bio-industry-name-input" data-index="${idx}" value="${escapeIndustryHtml(item.name)}">
                    </td>
                    <td style="padding: 8px; text-align: center;">
                        <button class="btn-sm btn-danger" onclick="removeBioIndustryFilter(${idx})" ${bioIndustryFiltersData.length <= 1 ? 'disabled' : ''}>删除</button>
                    </td>
                </tr>
            `).join('');

            filterEditor.innerHTML = `
                <h4 style="margin-bottom: 12px; color: #333;">1) 定义筛选分类</h4>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
                    <thead>
                        <tr style="background: #f5f5f5;">
                            <th style="padding: 10px; text-align: left; width: 220px; border-bottom: 2px solid #ddd;">分类键值</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">分类名称</th>
                            <th style="padding: 10px; text-align: center; width: 90px; border-bottom: 2px solid #ddd;">操作</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
                <div style="display:flex; gap:10px; align-items:center;">
                    <input type="text" id="newBioIndustryName" class="form-control" placeholder="新分类名称（例如：生物传感产品）" style="max-width: 320px;">
                    <button class="btn-primary" style="width:auto; padding:10px 20px;" onclick="addBioIndustryFilter()">添加分类（自动保存）</button>
                    <button class="btn-primary" style="width:auto; padding:10px 20px;" onclick="saveBioIndustryFilters()">保存分类定义</button>
                </div>
                <div id="bioIndustrySaveMsg" style="margin-top: 10px; font-size: 13px;"></div>
            `;

            assignEditor.innerHTML = `
                <h4 style="margin-bottom: 12px; color: #333;">2) 勾选产品所属领域</h4>
                <table style="width:100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background:#f5f5f5;">
                            <th style="padding: 12px; text-align:left; border-bottom:2px solid #ddd; width: 220px;">产品</th>
                            ${bioIndustryFiltersData.map(c => `
                                <th style="padding: 8px 4px; text-align:center; border-bottom:2px solid #ddd; font-size: 12px;">${escapeIndustryHtml(c.name)}</th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${visibleProducts.length === 0 ? `
                            <tr>
                                <td colspan="${bioIndustryFiltersData.length + 1}" style="padding:14px; text-align:center; color:#999;">
                                    当前没有可显示的产品（隐藏产品不会出现在此处）
                                </td>
                            </tr>
                        ` : visibleProducts.map(p => {
                const selected = Array.isArray(p.industryCategories) ? p.industryCategories : [];
                return `
                            <tr style="border-bottom:1px solid #eee;">
                                <td style="padding:10px;">
                                    <div style="font-weight:500; color:#333;">${escapeIndustryHtml(p.name)}</div>
                                    <div style="font-size:11px; color:#999;">${escapeIndustryHtml(p.id)}</div>
                                </td>
                                ${bioIndustryFiltersData.map(c => `
                                    <td style="padding:8px 4px; text-align:center;">
                                        <input type="checkbox"
                                            class="bio-industry-checkbox"
                                            data-id="${escapeIndustryHtml(p.id)}"
                                            data-industry="${escapeIndustryHtml(c.key)}"
                                            ${selected.includes(c.key) ? 'checked' : ''}
                                            style="width: 18px; height: 18px; cursor: pointer;">
                                    </td>
                                `).join('')}
                            </tr>
                        `;
            }).join('')}
                    </tbody>
                </table>
                <div style="margin-top: 12px; padding: 12px; background: #e8f5e9; border-radius: 6px; font-size: 13px; color: #2e7d32;">
                    <i class="fas fa-check-circle"></i> 勾选和分类名称变更都会自动保存，刷新产品页即可看到新选项卡。
                </div>
            `;

            assignEditor.querySelectorAll('.bio-industry-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    updateBioProductIndustryCategories(e.target.dataset.id);
                });
            });

            filterEditor.querySelectorAll('.bio-industry-name-input').forEach(input => {
                input.addEventListener('change', async (e) => {
                    const idx = parseInt(e.target.dataset.index, 10);
                    if (!Number.isNaN(idx) && bioIndustryFiltersData[idx]) {
                        bioIndustryFiltersData[idx].name = e.target.value.trim() || bioIndustryFiltersData[idx].name;
                        await persistBioIndustryFilters('✓ 分类名称已自动保存');
                    }
                });
            });

            const newIndustryInput = document.getElementById('newBioIndustryName');
            if (newIndustryInput) {
                newIndustryInput.addEventListener('keydown', async (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        await addBioIndustryFilter();
                    }
                });
            }
        }

        async function addBioIndustryFilter() {
            const input = document.getElementById('newBioIndustryName');
            const name = (input?.value || '').trim();
            if (!name) return;

            const existingKeys = new Set(bioIndustryFiltersData.map(i => i.key));
            let key = normalizeIndustryKey(name, bioIndustryFiltersData.length);
            let suffix = 2;
            while (existingKeys.has(key)) {
                key = normalizeIndustryKey(`${name}-${suffix}`, bioIndustryFiltersData.length + suffix);
                suffix += 1;
            }

            bioIndustryFiltersData.push({ key, name });
            input.value = '';
            await persistBioIndustryFilters('✓ 已添加并自动保存');
        }

        async function removeBioIndustryFilter(index) {
            if (bioIndustryFiltersData.length <= 1) return;
            syncIndustryNamesFromInputs(bioIndustryFiltersData, '.bio-industry-name-input');
            bioIndustryFiltersData.splice(index, 1);
            await persistBioIndustryFilters('✓ 已删除并自动保存');
        }

        async function persistBioIndustryFilters(successText = '✓ 分类定义已保存') {
            const msg = document.getElementById('bioIndustrySaveMsg');
            const token = ++bioIndustryFiltersSaveToken;
            syncIndustryNamesFromInputs(bioIndustryFiltersData, '.bio-industry-name-input');

            const payload = {
                categories: bioIndustryFiltersData.map((item, idx) => ({
                    key: normalizeIndustryKey(item.key || item.name, idx),
                    name: (item.name || '').trim()
                })).filter(item => item.name)
            };

            try {
                const res = await fetch('/api/bio-products/industry-filters', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                if (token !== bioIndustryFiltersSaveToken) {
                    return;
                }
                if (!result.success) {
                    throw new Error(result.message || '保存失败');
                }
                bioIndustryFiltersData = Array.isArray(result.categories) ? result.categories : payload.categories;
                if (msg) {
                    msg.style.color = '#2e7d32';
                    msg.textContent = successText;
                }
                renderBioIndustrySettings();
            } catch (e) {
                if (token !== bioIndustryFiltersSaveToken) {
                    return;
                }
                console.error('Save bio industry filters error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '保存失败，请重试';
                }
            }
        }

        async function saveBioIndustryFilters() {
            await persistBioIndustryFilters('✓ 分类定义已保存');
        }

        function updateBioProductIndustryCategories(productId) {
            const all = document.querySelectorAll('.bio-industry-checkbox');
            const checkboxes = Array.from(all).filter(cb => cb.dataset.id === productId);
            const industryCategories = [];
            checkboxes.forEach(cb => {
                if (cb.checked) {
                    industryCategories.push(cb.dataset.industry);
                }
            });

            saveBioProductSetting(productId, 'industryCategories', industryCategories);
            const product = bioProductsData.find(p => p.id === productId);
            if (product) {
                product.industryCategories = industryCategories;
            }
        }

        function normalizeHydrogenSolutionConfigRows(definitions, configRows) {
            const cfgMap = {};
            (Array.isArray(configRows) ? configRows : []).forEach(item => {
                if (!item || typeof item !== 'object') return;
                const sid = String(item.id || '').trim();
                if (!sid) return;
                const list = Array.isArray(item.relatedProductIds) ? item.relatedProductIds : [];
                const deduped = [];
                list.forEach(pid => {
                    const id = String(pid || '').trim();
                    if (!id || deduped.includes(id)) return;
                    deduped.push(id);
                });
                cfgMap[sid] = deduped.slice(0, 4);
            });

            return (Array.isArray(definitions) ? definitions : []).map(def => ({
                id: String(def.id || '').trim(),
                title: String(def.title || '').trim(),
                relatedProductIds: (cfgMap[String(def.id || '').trim()] || []).slice(0, 4)
            }));
        }

        function renderHydrogenSolutionsEditor() {
            const editor = document.getElementById('hydrogenSolutionsEditor');
            if (!editor) return;

            if (!hydrogenSolutionDefinitions.length) {
                editor.innerHTML = '<div style="color:#888; padding: 8px 0;">暂无方案配置项</div>';
                return;
            }
            if (!hydrogenSolutionProductOptions.length) {
                editor.innerHTML = '<div style="color:#dc3545; padding: 8px 0;">未读取到产品列表，请先检查【氢气产品】配置</div>';
                return;
            }

            const baseOption = '<option value="">未选择</option>';
            const allOptions = hydrogenSolutionProductOptions.map(item => {
                const title = String(item.title || item.id || '');
                return `<option value="${escapeAttr(item.id)}">${escapeHtml(title)}</option>`;
            }).join('');

            editor.innerHTML = `
                <div class="table-container" style="overflow-x:auto;">
                    <table style="width:100%; border-collapse: collapse; min-width: 1180px;">
                        <thead>
                            <tr style="background:#f6f8fb;">
                                <th style="padding:10px; text-align:left; border-bottom:2px solid #e5e7eb; width: 320px;">方案</th>
                                <th style="padding:10px; text-align:left; border-bottom:2px solid #e5e7eb;">相关产品1</th>
                                <th style="padding:10px; text-align:left; border-bottom:2px solid #e5e7eb;">相关产品2</th>
                                <th style="padding:10px; text-align:left; border-bottom:2px solid #e5e7eb;">相关产品3</th>
                                <th style="padding:10px; text-align:left; border-bottom:2px solid #e5e7eb;">相关产品4</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${hydrogenSolutionsConfig.map(row => {
                const selected = Array.isArray(row.relatedProductIds) ? row.relatedProductIds : [];
                const makeSelect = slot => `
                                    <select class="form-control hydrogen-solution-product-select" data-solution-id="${escapeAttr(row.id)}" data-slot="${slot}" style="min-width:200px;">
                                        ${baseOption}${allOptions}
                                    </select>
                                `;
                return `
                                <tr style="border-bottom:1px solid #eef2f7;">
                                    <td style="padding:10px;">
                                        <div style="font-weight:600; color:#0f2f5f;">${escapeHtml(row.title || row.id)}</div>
                                        <div style="font-size:12px; color:#6b7280; margin-top:4px;">${escapeHtml(row.id)}</div>
                                    </td>
                                    <td style="padding:10px;">${makeSelect(1)}</td>
                                    <td style="padding:10px;">${makeSelect(2)}</td>
                                    <td style="padding:10px;">${makeSelect(3)}</td>
                                    <td style="padding:10px;">${makeSelect(4)}</td>
                                </tr>
                            `;
            }).join('')}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top:12px; padding:12px; background:#eef6ff; border-radius:8px; font-size:13px; color:#334155;">
                    每个方案至少选择 1 个，最多 4 个；同一方案内不允许重复产品。
                </div>
            `;

            editor.querySelectorAll('.hydrogen-solution-product-select').forEach(select => {
                const sid = String(select.dataset.solutionId || '');
                const slot = Math.max(0, Number(select.dataset.slot || 1) - 1);
                const row = hydrogenSolutionsConfig.find(item => item.id === sid);
                const selected = Array.isArray(row?.relatedProductIds) ? row.relatedProductIds : [];
                select.value = selected[slot] || '';
                select.addEventListener('change', () => {
                    const msg = document.getElementById('hydrogenSolutionsMsg');
                    if (msg) msg.textContent = '';
                    const currentRow = hydrogenSolutionsConfig.find(item => item.id === sid);
                    if (!currentRow) return;
                    const values = Array.from(editor.querySelectorAll(`.hydrogen-solution-product-select[data-solution-id="${sid}"]`))
                        .map(el => String(el.value || '').trim())
                        .filter(Boolean);
                    currentRow.relatedProductIds = values.filter((pid, idx) => values.indexOf(pid) === idx).slice(0, 4);
                    Array.from(editor.querySelectorAll(`.hydrogen-solution-product-select[data-solution-id="${sid}"]`))
                        .forEach((el, idx) => { el.value = currentRow.relatedProductIds[idx] || ''; });
                });
            });
        }

        async function loadHydrogenSolutionsConfig() {
            const editor = document.getElementById('hydrogenSolutionsEditor');
            const msg = document.getElementById('hydrogenSolutionsMsg');
            if (!editor) return;
            editor.innerHTML = '<div style="color:#888; padding: 8px 0;">加载中...</div>';
            if (msg) msg.textContent = '';

            try {
                const res = await fetch('/api/admin/hydrogen-solutions/config');
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.message || '加载失败');

                hydrogenSolutionDefinitions = Array.isArray(data.definitions) ? data.definitions : [];
                hydrogenSolutionProductOptions = Array.isArray(data.products) ? data.products : [];
                const configRows = (data.config && Array.isArray(data.config.solutions)) ? data.config.solutions : [];
                hydrogenSolutionsConfig = normalizeHydrogenSolutionConfigRows(hydrogenSolutionDefinitions, configRows);
                renderHydrogenSolutionsEditor();
            } catch (e) {
                editor.innerHTML = `<div style="color:#dc3545; padding: 8px 0;">${escapeHtml(e?.message || '加载失败')}</div>`;
            }
        }

        async function saveHydrogenSolutionsConfig() {
            const msg = document.getElementById('hydrogenSolutionsMsg');
            if (msg) {
                msg.style.color = '#2563eb';
                msg.textContent = '保存中...';
            }

            const payloadSolutions = hydrogenSolutionsConfig.map(item => {
                const ids = Array.isArray(item.relatedProductIds) ? item.relatedProductIds : [];
                const deduped = ids.map(x => String(x || '').trim()).filter(Boolean)
                    .filter((pid, idx, arr) => arr.indexOf(pid) === idx)
                    .slice(0, 4);
                return { id: item.id, relatedProductIds: deduped };
            });

            const invalidRow = payloadSolutions.find(item => item.relatedProductIds.length < 1 || item.relatedProductIds.length > 4);
            if (invalidRow) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = `方案“${invalidRow.id}”请至少选择 1 个、最多 4 个产品`;
                }
                return;
            }

            try {
                const res = await fetch('/api/admin/hydrogen-solutions/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ solutions: payloadSolutions })
                });
                const data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.message || '保存失败');

                const rows = (data.config && Array.isArray(data.config.solutions)) ? data.config.solutions : payloadSolutions;
                hydrogenSolutionsConfig = normalizeHydrogenSolutionConfigRows(hydrogenSolutionDefinitions, rows);
                renderHydrogenSolutionsEditor();
                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = '✓ 保存成功';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || '保存失败';
                }
            }
        }

        function updateMenuPreview() {
            const container = document.getElementById('menuPreview');
            const menuProducts = productsData.filter(p => !p.id.includes('../'));

            container.innerHTML = `
                <div style="width: 100%;">
                    <div style="margin-bottom: 15px; padding: 10px; background: #fff3cd; border-radius: 6px; font-size: 13px; color: #856404;">
                        <i class="fas fa-arrows-alt"></i> 拖动左侧手柄调整产品顺序，关闭"显示"开关可隐藏该产品
                    </div>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f5f5f5;">
                                <th style="padding: 12px; text-align: center; border-bottom: 2px solid #ddd; width: 50px;">排序</th>
                                <th style="padding: 12px; text-align: center; border-bottom: 2px solid #ddd; width: 80px;">显示</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">原始名称</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">菜单显示名称</th>
                                <th style="padding: 12px; text-align: center; border-bottom: 2px solid #ddd; width: 80px;">新品</th>
                                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">预览效果</th>
                            </tr>
                        </thead>
                        <tbody id="sortableProductList">
                            ${menuProducts.map(p => `
                                <tr data-product-id="${p.id}" style="border-bottom: 1px solid #eee; ${p.hidden ? 'opacity: 0.5;' : ''}">
                                    <td style="padding: 10px; text-align: center; cursor: grab;" class="drag-handle">
                                        <i class="fas fa-grip-vertical" style="color: #999; font-size: 16px;"></i>
                                    </td>
                                    <td style="padding: 10px; text-align: center;">
                                        <label class="toggle-switch" style="margin: 0;">
                                            <input type="checkbox" class="product-visible" data-id="${p.id}" ${!p.hidden ? 'checked' : ''}>
                                            <span class="toggle-slider"></span>
                                        </label>
                                    </td>
                                    <td style="padding: 10px;">
                                        <div style="font-weight: 500; color: #333;">${p.name}</div>
                                        <div style="font-size: 11px; color: #999;">${p.id}</div>
                                    </td>
                                    <td style="padding: 10px;">
                                        <input type="text" 
                                            class="form-control product-display-name" 
                                            data-id="${p.id}"
                                            placeholder="${p.shortName || p.name}"
                                            value="${p.displayName || ''}"
                                            style="width: 100%; padding: 8px; font-size: 13px;">
                                    </td>
                                    <td style="padding: 10px; text-align: center;">
                                        <label class="toggle-switch" style="margin: 0;">
                                            <input type="checkbox" class="product-is-new" data-id="${p.id}" ${p.isNew ? 'checked' : ''}>
                                            <span class="toggle-slider"></span>
                                        </label>
                                    </td>
                                    <td style="padding: 10px;">
                                        <span class="preview-name" style="color: #003366; font-weight: 500;">
                                            ${p.displayName || p.shortName || p.name}
                                        </span>
                                        ${p.isNew ? '<span style="background: #ff4444; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: 6px;">NEW</span>' : ''}
                                        ${p.hidden ? '<span style="background: #999; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: 6px;">隐藏</span>' : ''}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    <div style="margin-top: 15px; padding: 12px; background: #e8f5e9; border-radius: 6px; font-size: 13px; color: #2e7d32;">
                        <i class="fas fa-check-circle"></i> 修改后自动保存，刷新 hydrogen.html 页面即可看到效果
                    </div>
                </div>
            `;

            // Initialize SortableJS
            const sortableList = document.getElementById('sortableProductList');
            if (sortableList && typeof Sortable !== 'undefined') {
                new Sortable(sortableList, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function () {
                        saveSortOrder();
                    }
                });
            }

            // Bind events
            container.querySelectorAll('.product-display-name').forEach(input => {
                input.addEventListener('change', (e) => saveProductSetting(e.target.dataset.id, 'displayName', e.target.value));
                input.addEventListener('input', (e) => updatePreviewName(e.target.dataset.id));
            });

            container.querySelectorAll('.product-is-new').forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    saveProductSetting(e.target.dataset.id, 'isNew', e.target.checked);
                    updatePreviewBadge(e.target.dataset.id, e.target.checked);
                });
            });

            container.querySelectorAll('.product-visible').forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    const row = e.target.closest('tr');
                    const hidden = !e.target.checked;
                    const product = productsData.find(p => String(p.id) === String(e.target.dataset.id));
                    if (product) product.hidden = hidden;
                    saveProductSetting(e.target.dataset.id, 'hidden', hidden);
                    row.style.opacity = hidden ? '0.5' : '1';
                    // Update hidden badge
                    const previewCell = row.querySelector('td:last-child');
                    const existingHiddenBadge = previewCell.querySelector('span[style*="background: #999"]');
                    if (hidden && !existingHiddenBadge) {
                        previewCell.innerHTML += '<span style="background: #999; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: 6px;">隐藏</span>';
                    } else if (!hidden && existingHiddenBadge) {
                        existingHiddenBadge.remove();
                    }
                    renderIndustrySettings();
                });
            });
        }

        async function saveSortOrder() {
            const rows = document.querySelectorAll('#sortableProductList tr[data-product-id]');
            const order = Array.from(rows).map(row => row.dataset.productId);

            try {
                const res = await fetch('/api/products/settings/sort', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order })
                });
                const result = await res.json();
                if (!result.success) {
                    console.error('Sort save failed:', result.message);
                }
            } catch (e) {
                console.error('Sort save error:', e);
            }
        }

        function normalizeIndustryKey(name, index = 0) {
            let key = (name || '').toLowerCase().trim().replace(/[^a-z0-9_-]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
            if (!key) key = `industry-${index + 1}`;
            return key;
        }

        function syncIndustryNamesFromInputs(filters, selector) {
            const rows = Array.from(document.querySelectorAll(selector));
            if (!Array.isArray(filters) || rows.length !== filters.length) return;
            rows.forEach(input => {
                const idx = parseInt(input.dataset.index, 10);
                if (!Number.isNaN(idx) && filters[idx]) {
                    filters[idx].name = input.value.trim() || filters[idx].name;
                }
            });
        }

        function escapeIndustryHtml(str) {
            return String(str || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        async function loadIndustryFilters() {
            try {
                const res = await fetch('/api/products/industry-filters');
                const data = await res.json();
                industryFiltersData = Array.isArray(data.categories) ? data.categories : [];
                renderIndustrySettings();
            } catch (e) {
                console.error('Load industry filters error:', e);
                const editor = document.getElementById('industryFilterEditor');
                if (editor) {
                    editor.innerHTML = '<div style="color:#dc3545;">加载领域分类失败，请刷新重试</div>';
                }
            }
        }

        function renderIndustrySettings() {
            const filterEditor = document.getElementById('industryFilterEditor');
            const assignEditor = document.getElementById('industryAssignEditor');
            if (!filterEditor || !assignEditor) return;
            const visibleProducts = productsData.filter(p => !p.hidden);

            const rowsHtml = industryFiltersData.map((item, idx) => `
                <tr data-index="${idx}" style="border-bottom: 1px solid #eee;">
                    <td style="padding: 8px;"><code>${escapeIndustryHtml(item.key)}</code></td>
                    <td style="padding: 8px;">
                        <input type="text" class="form-control industry-name-input" data-index="${idx}" value="${escapeIndustryHtml(item.name)}">
                    </td>
                    <td style="padding: 8px; text-align: center;">
                        <button class="btn-sm btn-danger" onclick="removeIndustryFilter(${idx})" ${industryFiltersData.length <= 1 ? 'disabled' : ''}>删除</button>
                    </td>
                </tr>
            `).join('');

            filterEditor.innerHTML = `
                <h4 style="margin-bottom: 12px; color: #333;">1) 定义筛选分类</h4>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
                    <thead>
                        <tr style="background: #f5f5f5;">
                            <th style="padding: 10px; text-align: left; width: 220px; border-bottom: 2px solid #ddd;">分类键值</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">分类名称</th>
                            <th style="padding: 10px; text-align: center; width: 90px; border-bottom: 2px solid #ddd;">操作</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
                <div style="display:flex; gap:10px; align-items:center;">
                    <input type="text" id="newIndustryName" class="form-control" placeholder="新分类名称（例如：氢能源产品）" style="max-width: 320px;">
                    <button class="btn-primary" style="width:auto; padding:10px 20px;" onclick="addIndustryFilter()">添加分类（自动保存）</button>
                    <button class="btn-primary" style="width:auto; padding:10px 20px;" onclick="saveIndustryFilters()">保存分类定义</button>
                </div>
                <div id="industrySaveMsg" style="margin-top: 10px; font-size: 13px;"></div>
            `;

            assignEditor.innerHTML = `
                <h4 style="margin-bottom: 12px; color: #333;">2) 勾选产品所属领域</h4>
                <table style="width:100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background:#f5f5f5;">
                            <th style="padding: 12px; text-align:left; border-bottom:2px solid #ddd; width: 220px;">产品</th>
                            ${industryFiltersData.map(c => `
                                <th style="padding: 8px 4px; text-align:center; border-bottom:2px solid #ddd; font-size: 12px;">${escapeIndustryHtml(c.name)}</th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${visibleProducts.length === 0 ? `
                            <tr>
                                <td colspan="${industryFiltersData.length + 1}" style="padding:14px; text-align:center; color:#999;">
                                    当前没有可显示的产品（隐藏产品不会出现在此处）
                                </td>
                            </tr>
                        ` : visibleProducts.map(p => {
                const selected = Array.isArray(p.industryCategories) ? p.industryCategories : [];
                return `
                            <tr style="border-bottom:1px solid #eee;">
                                <td style="padding:10px;">
                                    <div style="font-weight:500; color:#333;">${escapeIndustryHtml(p.name)}</div>
                                    <div style="font-size:11px; color:#999;">${escapeIndustryHtml(p.id)}</div>
                                </td>
                                ${industryFiltersData.map(c => `
                                    <td style="padding:8px 4px; text-align:center;">
                                        <input type="checkbox"
                                            class="industry-checkbox"
                                            data-id="${escapeIndustryHtml(p.id)}"
                                            data-industry="${escapeIndustryHtml(c.key)}"
                                            ${selected.includes(c.key) ? 'checked' : ''}
                                            style="width: 18px; height: 18px; cursor: pointer;">
                                    </td>
                                `).join('')}
                            </tr>
                        `;
            }).join('')}
                    </tbody>
                </table>
                <div style="margin-top: 12px; padding: 12px; background: #e8f5e9; border-radius: 6px; font-size: 13px; color: #2e7d32;">
                    <i class="fas fa-check-circle"></i> 勾选和分类名称变更都会自动保存，刷新产品页即可看到新选项卡。
                </div>
            `;

            assignEditor.querySelectorAll('.industry-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    updateProductIndustryCategories(e.target.dataset.id);
                });
            });

            filterEditor.querySelectorAll('.industry-name-input').forEach(input => {
                input.addEventListener('change', async (e) => {
                    const idx = parseInt(e.target.dataset.index, 10);
                    if (!Number.isNaN(idx) && industryFiltersData[idx]) {
                        industryFiltersData[idx].name = e.target.value.trim() || industryFiltersData[idx].name;
                        await persistIndustryFilters('✓ 分类名称已自动保存');
                    }
                });
            });

            const newIndustryInput = document.getElementById('newIndustryName');
            if (newIndustryInput) {
                newIndustryInput.addEventListener('keydown', async (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        await addIndustryFilter();
                    }
                });
            }
        }

        async function addIndustryFilter() {
            const input = document.getElementById('newIndustryName');
            const name = (input?.value || '').trim();
            if (!name) return;

            const existingKeys = new Set(industryFiltersData.map(i => i.key));
            let key = normalizeIndustryKey(name, industryFiltersData.length);
            let suffix = 2;
            while (existingKeys.has(key)) {
                key = normalizeIndustryKey(`${name}-${suffix}`, industryFiltersData.length + suffix);
                suffix += 1;
            }

            industryFiltersData.push({ key, name });
            input.value = '';
            await persistIndustryFilters('✓ 已添加并自动保存');
        }

        async function removeIndustryFilter(index) {
            if (industryFiltersData.length <= 1) return;
            syncIndustryNamesFromInputs(industryFiltersData, '.industry-name-input');
            industryFiltersData.splice(index, 1);
            await persistIndustryFilters('✓ 已删除并自动保存');
        }

        async function persistIndustryFilters(successText = '✓ 分类定义已保存') {
            const msg = document.getElementById('industrySaveMsg');
            const token = ++industryFiltersSaveToken;
            syncIndustryNamesFromInputs(industryFiltersData, '.industry-name-input');

            const payload = {
                categories: industryFiltersData.map((item, idx) => ({
                    key: normalizeIndustryKey(item.key || item.name, idx),
                    name: (item.name || '').trim()
                })).filter(item => item.name)
            };

            try {
                const res = await fetch('/api/products/industry-filters', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                if (token !== industryFiltersSaveToken) {
                    return;
                }
                if (!result.success) {
                    throw new Error(result.message || '保存失败');
                }
                industryFiltersData = Array.isArray(result.categories) ? result.categories : payload.categories;
                if (msg) {
                    msg.style.color = '#2e7d32';
                    msg.textContent = successText;
                }
                renderIndustrySettings();
            } catch (e) {
                if (token !== industryFiltersSaveToken) {
                    return;
                }
                console.error('Save industry filters error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '保存失败，请重试';
                }
            }
        }

        async function saveIndustryFilters() {
            await persistIndustryFilters('✓ 分类定义已保存');
        }

        function updateProductIndustryCategories(productId) {
            const all = document.querySelectorAll('.industry-checkbox');
            const checkboxes = Array.from(all).filter(cb => cb.dataset.id === productId);
            const industryCategories = [];
            checkboxes.forEach(cb => {
                if (cb.checked) {
                    industryCategories.push(cb.dataset.industry);
                }
            });

            saveProductSetting(productId, 'industryCategories', industryCategories);
            const product = productsData.find(p => p.id === productId);
            if (product) {
                product.industryCategories = industryCategories;
            }
        }

        // --- Product Category Images Functions ---
        let productCategoryImagesData = [];

        function renderProductCategoryImagesEditor() {
            const container = document.getElementById('productCategoryImagesEditor');
            if (!container) return;

            const rows = productCategoryImagesData.map((item, idx) => `
                <div style="display: flex; align-items: center; gap: 15px; padding: 12px 0; border-bottom: 1px solid #eee;">
                    <div style="flex: 1; min-width: 120px;">
                        <strong style="color: #333;">${escapeHtml(item.name || '')}</strong>
                    </div>
                    <div style="flex: 2; display: flex; align-items: center; gap: 10px;">
                        <input type="text" class="form-control product-category-image" data-key="${escapeHtml(item.key || '')}"
                            value="${escapeHtml(item.image || '')}" placeholder="相对路径或 https:// 链接"
                            title="不设置将使用默认图片"
                            style="flex: 1; min-width: 200px;">
                        <div class="product-category-image-preview" data-key="${escapeHtml(item.key || '')}"
                            style="width: 56px; height: 40px; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; background: #f7f8fa; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                            ${item.image ? `<img src="${escapeHtml(item.image)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">` : '<span style="font-size: 10px; color: #999;">预览</span>'}
                        </div>
                    </div>
                </div>
            `).join('');

            container.innerHTML = rows || '<div style="color: #888;">暂无产品分类数据</div>';
            initProductCategoryImagePreviews();
        }

        function initProductCategoryImagePreviews() {
            const imageInputs = document.querySelectorAll('.product-category-image');
            imageInputs.forEach(input => {
                input.addEventListener('input', function() {
                    const key = this.dataset.key;
                    const preview = document.querySelector(`.product-category-image-preview[data-key="${key}"]`);
                    if (!preview) return;

                    const value = this.value.trim();
                    if (!value) {
                        preview.innerHTML = '<span style="font-size: 10px; color: #999;">预览</span>';
                        return;
                    }

                    preview.innerHTML = `<img src="${escapeHtml(value)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">`;
                });
            });
        }

        async function loadProductCategoryImages() {
            const container = document.getElementById('productCategoryImagesEditor');
            if (!container) return;
            container.innerHTML = '<div style="color:#888;">加载中...</div>';
            try {
                const res = await fetch('/api/categories/images');
                const data = await res.json();
                productCategoryImagesData = Array.isArray(data.categories) ? data.categories : [];
                renderProductCategoryImagesEditor();
            } catch (e) {
                console.error('Load product category images error:', e);
                container.innerHTML = '<div style="color:#dc3545;">加载失败，请刷新重试</div>';
            }
        }

        async function saveProductCategoryImages() {
            const msg = document.getElementById('productCategoryImagesMsg');
            const images = {};
            const inputs = document.querySelectorAll('.product-category-image');
            inputs.forEach(input => {
                const key = input.dataset.key;
                const value = (input.value || '').trim();
                if (key && value) {
                    images[key] = value;
                }
            });

            try {
                const res = await fetch('/api/categories/images', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ images })
                });
                const result = await res.json();
                if (result.success) {
                    productCategoryImagesData = Array.isArray(result.categories) ? result.categories : [];
                    renderProductCategoryImagesEditor();
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功！';
                    }
                    setTimeout(() => {
                        if (msg) msg.textContent = '';
                    }, 3000);
                } else {
                    throw new Error(result.message || '保存失败');
                }
            } catch (e) {
                console.error('Save product category images error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '保存失败';
                }
            }
        }

        // --- Recommendations Functions ---
        let recommendationsProductsAll = [];

        async function loadRecommendations() {
            try {
                const [productsRes, recommendationsRes] = await Promise.all([
                    fetch('/api/products/with-settings'),
                    fetch('/api/recommendations')
                ]);
                const productsDataResult = await productsRes.json();
                const recommendationsData = await recommendationsRes.json();

                const rawProducts = productsDataResult.products || [];
                recommendationsProductsAll = rawProducts.filter(p => {
                    const pid = String(p?.id || '');
                    if (!pid) return false;
                    if (pid === 'all-products') return false;
                    if (pid.startsWith('../biosensing/')) return false;
                    if (pid.startsWith('../customization/')) return true;
                    return !pid.startsWith('../');
                });

                const options = ['<option value="">不选择</option>']
                    .concat(recommendationsProductsAll.map(item => {
                        const label = item.displayName || item.shortName || item.name || item.id;
                        return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)}</option>`;
                    }));

                [1, 2, 3, 4].forEach((idx) => {
                    const select = document.getElementById(`latest${idx}Select`);
                    if (select) {
                        select.innerHTML = options.join('');
                    }
                });

                const latest = Array.isArray(recommendationsData.latestReleases) ? recommendationsData.latestReleases : [];

                [1, 2, 3, 4].forEach((idx) => {
                    const item = latest[idx - 1] || {};
                    const select = document.getElementById(`latest${idx}Select`);
                    if (select && item.url) {
                        const matchedProduct = recommendationsProductsAll.find(p => {
                            const productUrl = `../gassensing/${p.id}.html`;
                            return item.url === productUrl || item.url === p.id || item.url === `/${p.id}`;
                        });
                        if (matchedProduct) {
                            select.value = matchedProduct.id;
                        }
                    }
                });

                updateRecommendationPreview();
            } catch (e) {
                console.error('Load recommendations error:', e);
            }
        }

        function updateRecommendationPreview() {
            [1, 2, 3, 4].forEach((idx) => {
                const select = document.getElementById(`latest${idx}Select`);
                const preview = document.getElementById(`latest${idx}Preview`);
                if (!select || !preview) return;

                const selectedId = select.value;
                if (!selectedId) {
                    preview.innerHTML = '';
                    return;
                }

                const product = recommendationsProductsAll.find(p => p.id === selectedId);
                if (!product) {
                    preview.innerHTML = '';
                    return;
                }

                const image = product.cardImage || product.image || '';
                const name = product.displayName || product.shortName || product.name || '';

                preview.innerHTML = `
                    <img src="${image}" alt="${escapeHtml(name)}" 
                        style="width: 48px; height: 32px; object-fit: contain; border-radius: 4px; border: 1px solid #ddd; background: #f7f8fa;"
                        onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 60 40%22><rect fill=%22%23eee%22 width=%2260%22 height=%2240%22/><text x=%2230%22 y=%2225%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%228%22>无图</text></svg>'">
                    <span style="font-size: 13px; color: #666;">${escapeHtml(name)}</span>
                `;
            });
        }

        async function saveRecommendations() {
            const latestReleases = [1, 2, 3, 4].map((idx) => {
                const select = document.getElementById(`latest${idx}Select`);
                const selectedId = select?.value || '';

                if (!selectedId) {
                    return { name: '', url: '' };
                }

                const product = recommendationsProductsAll.find(p => p.id === selectedId);
                if (!product) {
                    return { name: '', url: '' };
                }

                return {
                    name: product.displayName || product.shortName || product.name || product.id,
                    url: `../gassensing/${product.id}.html`
                };
            });

            const validItems = latestReleases.filter(item => item.name && item.url);
            if (validItems.length === 0) {
                document.getElementById('recommendationsMsg').style.color = '#dc3545';
                document.getElementById('recommendationsMsg').textContent = '请至少选择 1 个产品';
                return;
            }

            try {
                const res = await fetch('/api/recommendations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ latestReleases })
                });
                const result = await res.json();
                if (result.success) {
                    document.getElementById('recommendationsMsg').style.color = '#28a745';
                    document.getElementById('recommendationsMsg').textContent = '✓ 保存成功！刷新 hydrogen.html 页面即可看到效果';
                    setTimeout(() => {
                        document.getElementById('recommendationsMsg').textContent = '';
                    }, 3000);
                } else {
                    document.getElementById('recommendationsMsg').style.color = '#dc3545';
                    document.getElementById('recommendationsMsg').textContent = result.message || '保存失败';
                }
            } catch (e) {
                console.error('Save recommendations error:', e);
                document.getElementById('recommendationsMsg').style.color = '#dc3545';
                document.getElementById('recommendationsMsg').textContent = '保存失败';
            }
        }

        let measurementTargetsData = [];

        function isValidNavLink(value) {
            const url = (value || '').trim();
            if (!url) return false;
            if (/^https?:\/\//i.test(url)) return true;
            if (/^(\/|\.\/|\.\.\/)/.test(url)) return true;
            if (url.includes('://')) return false;
            if (/^[A-Za-z0-9._/-]+\.[A-Za-z0-9]+([?#].*)?$/.test(url)) return true;
            return false;
        }

        let measurementPagesList = [];

        function buildMeasurementPagesOptions(selectedUrl = '') {
            if (measurementPagesList.length === 0) {
                return '<option value="">加载中...</option>';
            }
            const options = ['<option value="">不选择</option>'];
            measurementPagesList.forEach(page => {
                const selected = page.url === selectedUrl ? 'selected' : '';
                options.push(`<option value="${escapeHtml(page.url)}" ${selected}>${escapeHtml(page.name)}</option>`);
            });
            return options.join('');
        }

        function renderMeasurementTargetsEditor() {
            const container = document.getElementById('measurementTargetsEditor');
            if (!container) return;

            const rows = measurementTargetsData.map((item, idx) => `
                <tr style="border-bottom:1px solid #eee;">
                    <td class="drag-handle" style="padding:8px; width:44px; text-align:center;">
                        <i class="fas fa-grip-vertical"></i>
                    </td>
                    <td style="padding:8px; width:48px; color:#666;">${idx + 1}</td>
                    <td style="padding:8px;">
                        <input type="text" class="form-control measurement-target-name" data-index="${idx}"
                            value="${escapeHtml(item.name || '')}" placeholder="显示名称（如：氢气 (H2)）">
                    </td>
                    <td style="padding:8px;">
                        <select class="form-control measurement-target-url" data-index="${idx}" onchange="onMeasurementTargetUrlChange(this)">
                            ${buildMeasurementPagesOptions(item.url || '')}
                        </select>
                    </td>
                    <td style="padding:8px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <input type="text" class="form-control measurement-target-image" data-index="${idx}"
                                value="${escapeHtml(item.image || '')}" placeholder="相对路径或 https:// 链接"
                                title="不设置此项将使用页面内的首张图片作为缩略图显示"
                                style="flex: 1; min-width: 150px;">
                            <div class="measurement-target-image-preview" data-index="${idx}" 
                                style="width: 56px; height: 40px; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; background: #f7f8fa; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                ${item.image ? `<img src="${escapeHtml(item.image)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">` : '<span style="font-size: 10px; color: #999;">预览</span>'}
                            </div>
                        </div>
                    </td>
                    <td style="padding:8px; width:90px; text-align:center;">
                        <button class="btn-sm btn-danger" onclick="removeMeasurementTargetRow(${idx})">删除</button>
                    </td>
                </tr>
            `).join('');

            container.innerHTML = `
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f5f5f5;">
                            <th style="padding:10px; text-align:center; width:44px; border-bottom:2px solid #ddd;">拖拽</th>
                            <th style="padding:10px; text-align:left; width:48px; border-bottom:2px solid #ddd;">#</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">显示名称</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">跳转链接</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">缩略图（可选）</th>
                            <th style="padding:10px; text-align:center; width:90px; border-bottom:2px solid #ddd;">操作</th>
                        </tr>
                    </thead>
                    <tbody id="measurementTargetsTbody">${rows}</tbody>
                </table>
            `;
            initMeasurementTargetsSortable();
            initMeasurementTargetImagePreviews();
        }

        function onMeasurementTargetUrlChange(select) {
            const idx = select.dataset.index;
            const nameInput = document.querySelector(`.measurement-target-name[data-index="${idx}"]`);
            if (!nameInput) return;

            const selectedOption = select.options[select.selectedIndex];
            if (selectedOption && selectedOption.value && !nameInput.value.trim()) {
                nameInput.value = selectedOption.text;
            }
        }

        function initMeasurementTargetImagePreviews() {
            const imageInputs = document.querySelectorAll('#measurementTargetsTbody .measurement-target-image');
            imageInputs.forEach(input => {
                input.addEventListener('input', function() {
                    const idx = this.dataset.index;
                    const preview = document.querySelector(`.measurement-target-image-preview[data-index="${idx}"]`);
                    if (!preview) return;

                    const value = this.value.trim();
                    if (!value) {
                        preview.innerHTML = '<span style="font-size: 10px; color: #999;">预览</span>';
                        return;
                    }

                    preview.innerHTML = `<img src="${escapeHtml(value)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">`;
                });
            });
        }

        function collectMeasurementTargetsFromDom() {
            const names = Array.from(document.querySelectorAll('#measurementTargetsTbody .measurement-target-name'));
            const urls = Array.from(document.querySelectorAll('#measurementTargetsTbody .measurement-target-url'));
            const images = Array.from(document.querySelectorAll('#measurementTargetsTbody .measurement-target-image'));
            return names.map((nameInput, idx) => ({
                name: (nameInput.value || '').trim(),
                url: (urls[idx]?.value || '').trim(),
                image: (images[idx]?.value || '').trim()
            }));
        }

        function syncMeasurementTargetsFromDom() {
            const tbody = document.getElementById('measurementTargetsTbody');
            if (!tbody) return;
            measurementTargetsData = collectMeasurementTargetsFromDom();
        }

        function initMeasurementTargetsSortable() {
            const tbody = document.getElementById('measurementTargetsTbody');
            if (!tbody || typeof Sortable === 'undefined') return;
            new Sortable(tbody, {
                handle: '.drag-handle',
                animation: 150,
                onEnd: function () {
                    syncMeasurementTargetsFromDom();
                    renderMeasurementTargetsEditor();
                }
            });
        }

        async function loadMeasurementTargets() {
            const container = document.getElementById('measurementTargetsEditor');
            if (!container) return;
            container.innerHTML = '<div style="color:#888; padding: 8px 0;">加载中...</div>';
            try {
                const [pagesRes, targetsRes] = await Promise.all([
                    fetch('/api/measurement-pages'),
                    fetch('/api/measurement-targets')
                ]);
                const pagesData = await pagesRes.json();
                const targetsData = await targetsRes.json();

                measurementPagesList = Array.isArray(pagesData.pages) ? pagesData.pages : [];
                measurementTargetsData = Array.isArray(targetsData.items) ? targetsData.items : [];
                renderMeasurementTargetsEditor();
            } catch (e) {
                console.error('Load measurement targets error:', e);
                container.innerHTML = '<div style="color:#dc3545; padding: 8px 0;">加载失败，请刷新重试</div>';
            }
        }

        function addMeasurementTargetRow() {
            syncMeasurementTargetsFromDom();
            measurementTargetsData.push({ name: '', url: '', image: '' });
            renderMeasurementTargetsEditor();
        }

        function removeMeasurementTargetRow(index) {
            syncMeasurementTargetsFromDom();
            measurementTargetsData.splice(index, 1);
            renderMeasurementTargetsEditor();
        }

        async function saveMeasurementTargets() {
            const msg = document.getElementById('measurementTargetsMsg');
            const items = collectMeasurementTargetsFromDom();

            const invalid = items.find(item => !item.name || !item.url);
            if (invalid) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请填写完整名称并选择跳转链接';
                }
                return;
            }

            try {
                const res = await fetch('/api/measurement-targets', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const result = await res.json();
                if (!result.success) {
                    throw new Error(result.message || '保存失败');
                }
                measurementTargetsData = Array.isArray(result.items) ? result.items : items;
                renderMeasurementTargetsEditor();
                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = '✓ 保存成功！刷新 gassensing/index.html 即可生效';
                }
            } catch (e) {
                console.error('Save measurement targets error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '保存失败';
                }
            }
        }

        let navIndustryCategoriesData = [];
        let solutionsPagesList = [];

        function buildSolutionsPagesOptions(selectedUrl = '') {
            if (solutionsPagesList.length === 0) {
                return '<option value="">加载中...</option>';
            }
            const options = ['<option value="">不选择</option>'];
            solutionsPagesList.forEach(page => {
                const selected = page.url === selectedUrl ? 'selected' : '';
                options.push(`<option value="${escapeHtml(page.url)}" ${selected}>${escapeHtml(page.name)}</option>`);
            });
            return options.join('');
        }

        function renderNavIndustryCategoriesEditor() {
            const container = document.getElementById('navIndustryCategoriesEditor');
            if (!container) return;

            const rows = navIndustryCategoriesData.map((item, idx) => `
                <tr style="border-bottom:1px solid #eee;">
                    <td class="drag-handle" style="padding:8px; width:44px; text-align:center;">
                        <i class="fas fa-grip-vertical"></i>
                    </td>
                    <td style="padding:8px; width:48px; color:#666;">${idx + 1}</td>
                    <td style="padding:8px;">
                        <input type="text" class="form-control nav-industry-name" data-index="${idx}"
                            value="${escapeHtml(item.name || '')}" placeholder="按钮名称（如：氢能源产业链）">
                    </td>
                    <td style="padding:8px;">
                        <select class="form-control nav-industry-url" data-index="${idx}" onchange="onSolutionsPageUrlChange(this)">
                            ${buildSolutionsPagesOptions(item.url || '')}
                        </select>
                    </td>
                    <td style="padding:8px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <input type="text" class="form-control nav-industry-image" data-index="${idx}"
                                value="${escapeHtml(item.image || '')}" placeholder="相对路径或 https:// 链接"
                                title="不设置此项将使用页面内的首张图片作为缩略图显示"
                                style="flex: 1; min-width: 150px;">
                            <div class="nav-industry-image-preview" data-index="${idx}" 
                                style="width: 56px; height: 40px; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; background: #f7f8fa; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                ${item.image ? `<img src="${escapeHtml(item.image)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">` : '<span style="font-size: 10px; color: #999;">预览</span>'}
                            </div>
                        </div>
                    </td>
                    <td style="padding:8px; width:90px; text-align:center;">
                        <button class="btn-sm btn-danger" onclick="removeNavIndustryCategoryRow(${idx})">删除</button>
                    </td>
                </tr>
            `).join('');

            container.innerHTML = `
                <table style="width:100%; border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f5f5f5;">
                            <th style="padding:10px; text-align:center; width:44px; border-bottom:2px solid #ddd;">拖拽</th>
                            <th style="padding:10px; text-align:left; width:48px; border-bottom:2px solid #ddd;">#</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">按钮名称</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">跳转链接</th>
                            <th style="padding:10px; text-align:left; border-bottom:2px solid #ddd;">缩略图（可选）</th>
                            <th style="padding:10px; text-align:center; width:90px; border-bottom:2px solid #ddd;">操作</th>
                        </tr>
                    </thead>
                    <tbody id="navIndustryCategoriesTbody">${rows}</tbody>
                </table>
            `;
            initNavIndustryCategoriesSortable();
            initNavIndustryCategoriesImagePreviews();
        }

        function onSolutionsPageUrlChange(select) {
            const idx = select.dataset.index;
            const nameInput = document.querySelector(`.nav-industry-name[data-index="${idx}"]`);
            if (!nameInput) return;

            const selectedOption = select.options[select.selectedIndex];
            if (selectedOption && selectedOption.value && !nameInput.value.trim()) {
                nameInput.value = selectedOption.text;
            }
        }

        function collectNavIndustryCategoriesFromDom() {
            const names = Array.from(document.querySelectorAll('#navIndustryCategoriesTbody .nav-industry-name'));
            const urls = Array.from(document.querySelectorAll('#navIndustryCategoriesTbody .nav-industry-url'));
            const images = Array.from(document.querySelectorAll('#navIndustryCategoriesTbody .nav-industry-image'));
            return names.map((nameInput, idx) => ({
                name: (nameInput.value || '').trim(),
                url: (urls[idx]?.value || '').trim(),
                image: (images[idx]?.value || '').trim()
            }));
        }

        function initNavIndustryCategoriesImagePreviews() {
            const imageInputs = document.querySelectorAll('#navIndustryCategoriesTbody .nav-industry-image');
            imageInputs.forEach(input => {
                input.addEventListener('input', function() {
                    const idx = this.dataset.index;
                    const preview = document.querySelector(`.nav-industry-image-preview[data-index="${idx}"]`);
                    if (!preview) return;

                    const value = this.value.trim();
                    if (!value) {
                        preview.innerHTML = '<span style="font-size: 10px; color: #999;">预览</span>';
                        return;
                    }

                    preview.innerHTML = `<img src="${escapeHtml(value)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.parentElement.innerHTML='<span style=\\'font-size:10px;color:#999;\\'>加载失败</span>'">`;
                });
            });
        }

        function syncNavIndustryCategoriesFromDom() {
            const tbody = document.getElementById('navIndustryCategoriesTbody');
            if (!tbody) return;
            navIndustryCategoriesData = collectNavIndustryCategoriesFromDom();
        }

        function initNavIndustryCategoriesSortable() {
            const tbody = document.getElementById('navIndustryCategoriesTbody');
            if (!tbody || typeof Sortable === 'undefined') return;
            new Sortable(tbody, {
                handle: '.drag-handle',
                animation: 150,
                onEnd: function () {
                    syncNavIndustryCategoriesFromDom();
                    renderNavIndustryCategoriesEditor();
                }
            });
        }

        async function loadNavIndustryCategories() {
            const container = document.getElementById('navIndustryCategoriesEditor');
            if (!container) return;
            container.innerHTML = '<div style="color:#888; padding: 8px 0;">加载中...</div>';
            try {
                const [pagesRes, categoriesRes] = await Promise.all([
                    fetch('/api/solutions-pages'),
                    fetch('/api/nav-industry-categories')
                ]);
                const pagesData = await pagesRes.json();
                const categoriesData = await categoriesRes.json();

                solutionsPagesList = Array.isArray(pagesData.pages) ? pagesData.pages : [];
                navIndustryCategoriesData = Array.isArray(categoriesData.items) ? categoriesData.items : [];
                renderNavIndustryCategoriesEditor();
            } catch (e) {
                console.error('Load nav industry categories error:', e);
                container.innerHTML = '<div style="color:#dc3545; padding: 8px 0;">加载失败，请刷新重试</div>';
            }
        }

        function addNavIndustryCategoryRow() {
            syncNavIndustryCategoriesFromDom();
            navIndustryCategoriesData.push({ name: '', url: '', image: '' });
            renderNavIndustryCategoriesEditor();
        }

        function removeNavIndustryCategoryRow(index) {
            syncNavIndustryCategoriesFromDom();
            navIndustryCategoriesData.splice(index, 1);
            renderNavIndustryCategoriesEditor();
        }

        async function saveNavIndustryCategories() {
            const msg = document.getElementById('navIndustryCategoriesMsg');
            const items = collectNavIndustryCategoriesFromDom();

            const invalid = items.find(item => !item.name || !item.url);
            if (invalid) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '请填写完整名称并选择跳转链接';
                }
                return;
            }

            try {
                const res = await fetch('/api/nav-industry-categories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const result = await res.json();
                if (!result.success) {
                    throw new Error(result.message || '保存失败');
                }
                navIndustryCategoriesData = Array.isArray(result.items) ? result.items : items;
                renderNavIndustryCategoriesEditor();
                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = '✓ 保存成功！刷新 gas 页面即可生效';
                }
            } catch (e) {
                console.error('Save nav industry categories error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '保存失败';
                }
            }
        }

        function updatePreviewName(productId) {
            const row = document.querySelector(`tr[data-product-id="${productId}"]`);
            if (!row) return;
            const input = row.querySelector('.product-display-name');
            const preview = row.querySelector('.preview-name');
            const product = productsData.find(p => p.id === productId);
            if (preview && product) {
                preview.textContent = input.value || product.shortName || product.name;
            }
        }

        function updatePreviewBadge(productId, isNew) {
            const row = document.querySelector(`tr[data-product-id="${productId}"]`);
            if (!row) return;
            const previewCell = row.querySelector('td:last-child');
            const existingBadge = previewCell.querySelector('span[style*="background: #ff4444"]');
            if (isNew && !existingBadge) {
                previewCell.innerHTML += '<span style="background: #ff4444; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; margin-left: 6px;">NEW</span>';
            } else if (!isNew && existingBadge) {
                existingBadge.remove();
            }
        }

        async function saveProductSetting(productId, field, value) {
            try {
                const data = { id: productId };
                data[field] = value;

                const res = await fetch('/api/products/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await res.json();
                if (!result.success) {
                    console.error('Save failed:', result.message);
                    return;
                }
                const target = productsData.find(p => String(p.id) === String(productId));
                if (target) target[field] = value;
            } catch (e) {
                console.error('Save error:', e);
            }
        }

        async function uploadProductCardImage(productId, file) {
            const tbody = document.getElementById('productsTableBody');
            const msgEl = tbody ? tbody.querySelector(`.product-card-image-msg[data-id="${productId}"]`) : null;
            const imageInput = tbody ? tbody.querySelector(`.product-card-image[data-id="${productId}"]`) : null;
            if (msgEl) {
                msgEl.style.color = '#666';
                msgEl.textContent = '上传中...';
            }

            try {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/products/card-image/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await res.json();
                if (!result.success || !result.url) {
                    throw new Error(result.message || '上传失败');
                }

                if (imageInput) {
                    imageInput.value = result.url;
                }
                await saveProductSetting(productId, 'cardImage', result.url);

                if (msgEl) {
                    msgEl.style.color = '#2e7d32';
                    msgEl.textContent = '✓ 上传并保存成功';
                }
            } catch (e) {
                console.error('Upload product card image error:', e);
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = '上传失败';
                }
            }
        }

        function switchProductTab(tabName, btn) {
            // Update tab buttons
            document.querySelectorAll('#view-products .tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update tab content
            document.querySelectorAll('#view-products .tab-content').forEach(c => c.classList.remove('active'));
            const tab = document.getElementById(`product-tab-${tabName}`);
            if (tab) {
                tab.classList.add('active');
                renderTabGuide(tab);
                if (tabName === 'add') bindProductCreateEvents();
                if (tabName === 'ai') bindAiProductEvents();
                if (tabName === 'manual-edit') initManualEditTab();
            }
        }

        let manualEditInitialized = false;
        let manualEditCurrentProductId = null;
        let bioManualEditInitialized = false;
        let bioManualEditCurrentProductId = null;

        function getManualEditScopeConfig(scope = 'gas') {
            const isBio = scope === 'bio';
            return {
                scope,
                isBio,
                selectId: isBio ? 'bioManualEditProductSelect' : 'manualEditProductSelect',
                fieldsContainerId: isBio ? 'bioManualEditFieldsContainer' : 'manualEditFieldsContainer',
                msgId: isBio ? 'bioManualEditMsg' : 'manualEditMsg',
                previewLinkId: isBio ? 'bioManualEditPreviewLink' : 'manualEditPreviewLink',
                saveBtnId: isBio ? 'bioManualEditSaveBtn' : 'manualEditSaveBtn',
                titleId: isBio ? 'bioMeFieldTitle' : 'meFieldTitle',
                descriptionId: isBio ? 'bioMeFieldDescription' : 'meFieldDescription',
                detailId: isBio ? 'bioMeFieldDetail' : 'meFieldDetail',
                appIntroId: isBio ? 'bioMeFieldAppIntro' : 'meFieldAppIntro',
                sectionPrefix: isBio ? 'bio-me-section-' : 'me-section-',
                imagesContainerId: isBio ? 'bioMeImagesContainer' : 'meImagesContainer',
                highlightsContainerId: isBio ? 'bioMeHighlightsContainer' : 'meHighlightsContainer',
                advantagesContainerId: isBio ? 'bioMeAdvantagesContainer' : 'meAdvantagesContainer',
                applicationsContainerId: isBio ? 'bioMeApplicationsContainer' : 'meApplicationsContainer',
                specsTableBodyId: isBio ? 'bioMeSpecsTableBody' : 'meSpecsTableBody',
                newsContainerId: isBio ? 'bioMeNewsContainer' : 'meNewsContainer',
                pageSectionsEndpoint: isBio ? '/api/bio-products/page-sections' : '/api/products/page-sections',
                previewBasePath: isBio ? '/pages/biosensing' : '/pages/gassensing',
            };
        }

        function buildManualEditPreviewLink(productId, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const raw = String(productId || '').trim();
            if (!raw) return '#';
            if (cfg.isBio) {
                const slug = raw.replace('../biosensing/', '').replace(/^\/+|\/+$/g, '');
                return `${cfg.previewBasePath}/${slug}.html`;
            }
            return `${cfg.previewBasePath}/${raw}.html`;
        }

        function initManualEditTab() {
            const sel = document.getElementById('manualEditProductSelect');
            if (!sel) return;
            if (!manualEditInitialized) {
                manualEditInitialized = true;
                sel.addEventListener('change', function() {
                    if (this.value) loadManualEditSections(this.value, 'gas');
                    else document.getElementById('manualEditFieldsContainer').style.display = 'none';
                });
            }
            // Populate dropdown from productsData (only gassensing products)
            const currentVal = sel.value;
            sel.innerHTML = '<option value="">-- 请选择产品 --</option>';
            (productsData || []).forEach(p => {
                if (p.isBiosensing || p.isCustomization) return; // only gas sensing for now
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = (p.displayName || p.cardTitle || p.name || p.id) + '  (' + p.id + ')';
                sel.appendChild(opt);
            });
            if (currentVal) sel.value = currentVal;
        }

        function initBioManualEditTab() {
            const sel = document.getElementById('bioManualEditProductSelect');
            if (!sel) return;
            if (!bioManualEditInitialized) {
                bioManualEditInitialized = true;
                sel.addEventListener('change', function() {
                    if (this.value) loadManualEditSections(this.value, 'bio');
                    else document.getElementById('bioManualEditFieldsContainer').style.display = 'none';
                });
            }
            const currentVal = sel.value;
            sel.innerHTML = '<option value="">-- 请选择产品 --</option>';
            (bioProductsData || []).forEach(p => {
                if (!String(p.id || '').startsWith('../biosensing/')) return;
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = (p.displayName || p.cardTitle || p.name || p.id) + '  (' + p.id.replace('../biosensing/', '') + ')';
                sel.appendChild(opt);
            });
            if (currentVal) sel.value = currentVal;
        }

        function meToggleSection(name, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const card = document.getElementById(cfg.sectionPrefix + name);
            if (!card) return;
            card.classList.toggle('is-collapsed');
        }

        // ---- Image rows ----
        function meRenderImages(images, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.imagesContainerId);
            if (!c) return;
            c.innerHTML = '';
            (images || []).forEach((src, i) => meAddImageRow(src, i === 0, scope));
        }
        function meAddImageRow(src, isFirst, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.imagesContainerId);
            if (!c) return;
            const row = document.createElement('div');
            row.className = 'me-row-card';
            row.style.cssText = 'display:flex; gap:10px; align-items:flex-start; padding:10px 12px;';
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'form-control me-image-input';
            inp.value = src || '';
            inp.placeholder = isFirst ? '主图链接（第一张）' : '附图链接';
            inp.style.flex = '1';
            const img = document.createElement('img');
            img.className = 'me-image-preview';
            img.src = src || '';
            img.onerror = () => img.style.display = 'none';
            img.style.display = src ? '' : 'none';
            inp.addEventListener('input', () => { img.src = inp.value; img.style.display = inp.value ? '' : 'none'; });
            const del = document.createElement('button');
            del.type = 'button';
            del.textContent = '✕';
            del.className = 'me-row-del';
            del.style.cssText = 'position:static; margin-left:4px; align-self:center;';
            del.onclick = () => row.remove();
            row.appendChild(inp);
            row.appendChild(img);
            row.appendChild(del);
            c.appendChild(row);
        }
        function meGetImages(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.imagesContainerId} .me-image-input`))
                .map(el => el.value.trim()).filter(Boolean);
        }

        // ---- Highlight rows ----
        function meRenderHighlights(items, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.highlightsContainerId);
            if (!c) return;
            c.innerHTML = '';
            (items || []).forEach(text => meAddHighlightRow(text, scope));
        }
        function meAddHighlightRow(text, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.highlightsContainerId);
            if (!c) return;
            const row = document.createElement('div');
            row.className = 'me-row-card';
            row.style.cssText = 'display:flex; gap:8px; align-items:center; padding:8px 10px;';
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'form-control me-highlight-input';
            inp.value = text || '';
            inp.placeholder = '亮点文案';
            inp.style.flex = '1';
            const del = document.createElement('button');
            del.type = 'button';
            del.textContent = '✕';
            del.className = 'me-row-del';
            del.style.cssText = 'position:static; margin-left:4px;';
            del.onclick = () => row.remove();
            row.appendChild(inp);
            row.appendChild(del);
            c.appendChild(row);
        }
        function meGetHighlights(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.highlightsContainerId} .me-highlight-input`))
                .map(el => el.value.trim()).filter(Boolean);
        }

        // ---- Advantage rows ----
        function meRenderAdvantages(items, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.advantagesContainerId);
            if (!c) return;
            c.innerHTML = '';
            (items || []).forEach(item => meAddAdvantageRow(item, scope));
        }
        function meAddAdvantageRow(item, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.advantagesContainerId);
            if (!c) return;
            item = item || {};
            const row = document.createElement('div');
            row.className = 'me-row-card';
            row.innerHTML = `
                <button type="button" class="me-row-del" onclick="this.closest('.me-row-card').remove()">✕</button>
                <div style="display:grid; grid-template-columns:1fr 1fr 2fr; gap:10px; padding-right:30px;">
                    <div>
                        <span class="me-row-label">图标类名（FontAwesome）</span>
                        <input type="text" class="form-control me-adv-icon" value="${escapeHtml(item.icon || '')}" placeholder="fas fa-check-circle">
                    </div>
                    <div>
                        <span class="me-row-label">标题</span>
                        <input type="text" class="form-control me-adv-title" value="${escapeHtml(item.title || '')}" placeholder="优势标题">
                    </div>
                    <div>
                        <span class="me-row-label">描述</span>
                        <textarea class="form-control me-adv-desc" rows="2" placeholder="优势描述">${escapeHtml(item.desc || '')}</textarea>
                    </div>
                </div>`;
            c.appendChild(row);
        }
        function meGetAdvantages(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.advantagesContainerId} .me-row-card`)).map(row => ({
                icon: (row.querySelector('.me-adv-icon') || {}).value || '',
                title: (row.querySelector('.me-adv-title') || {}).value || '',
                desc: (row.querySelector('.me-adv-desc') || {}).value || '',
            }));
        }

        // ---- Application rows ----
        function meRenderApplications(items, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.applicationsContainerId);
            if (!c) return;
            c.innerHTML = '';
            (items || []).forEach(item => meAddApplicationRow(item, scope));
        }
        function meAddApplicationRow(item, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.applicationsContainerId);
            if (!c) return;
            item = item || {};
            const row = document.createElement('div');
            row.className = 'me-row-card';
            row.innerHTML = `
                <button type="button" class="me-row-del" onclick="this.closest('.me-row-card').remove()">✕</button>
                <div style="display:grid; grid-template-columns:1fr 1fr 2fr 1fr; gap:10px; padding-right:30px;">
                    <div>
                        <span class="me-row-label">图标类名</span>
                        <input type="text" class="form-control me-app-icon" value="${escapeHtml(item.icon || '')}" placeholder="fas fa-circle">
                    </div>
                    <div>
                        <span class="me-row-label">标题</span>
                        <input type="text" class="form-control me-app-title" value="${escapeHtml(item.title || '')}" placeholder="应用场景标题">
                    </div>
                    <div>
                        <span class="me-row-label">描述</span>
                        <textarea class="form-control me-app-desc" rows="2" placeholder="应用描述">${escapeHtml(item.desc || '')}</textarea>
                    </div>
                    <div>
                        <span class="me-row-label">场景标签</span>
                        <input type="text" class="form-control me-app-scenario" value="${escapeHtml(item.scenario || '')}" placeholder="场景文字">
                    </div>
                </div>`;
            c.appendChild(row);
        }
        function meGetApplications(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.applicationsContainerId} .me-row-card`)).map(row => ({
                icon: (row.querySelector('.me-app-icon') || {}).value || '',
                title: (row.querySelector('.me-app-title') || {}).value || '',
                desc: (row.querySelector('.me-app-desc') || {}).value || '',
                scenario: (row.querySelector('.me-app-scenario') || {}).value || '',
            }));
        }

        // ---- Spec rows ----
        function meRenderSpecs(items, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const tbody = document.getElementById(cfg.specsTableBodyId);
            if (!tbody) return;
            tbody.innerHTML = '';
            (items || []).forEach(row => meAddSpecRow(row, scope));
        }
        function meAddSpecRow(item, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const tbody = document.getElementById(cfg.specsTableBodyId);
            if (!tbody) return;
            item = item || {};
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="padding:4px 6px; border:1px solid #dde6ef;">
                    <input type="text" class="form-control me-spec-key" value="${escapeHtml(item.key || '')}" placeholder="参数名" style="padding:6px 8px; font-size:13px;">
                </td>
                <td style="padding:4px 6px; border:1px solid #dde6ef;">
                    <input type="text" class="form-control me-spec-val" value="${escapeHtml(item.value || '')}" placeholder="参数值" style="padding:6px 8px; font-size:13px;">
                </td>
                <td style="padding:4px 6px; border:1px solid #dde6ef; text-align:center;">
                    <button type="button" onclick="this.closest('tr').remove()" style="border:none;background:transparent;color:#dc3545;cursor:pointer;font-size:14px;">✕</button>
                </td>`;
            tbody.appendChild(tr);
        }
        function meGetSpecs(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.specsTableBodyId} tr`)).map(tr => ({
                key: (tr.querySelector('.me-spec-key') || {}).value || '',
                value: (tr.querySelector('.me-spec-val') || {}).value || '',
            })).filter(r => r.key);
        }

        // ---- News rows ----
        function meRenderNews(items, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.newsContainerId);
            if (!c) return;
            c.innerHTML = '';
            (items || []).forEach(item => meAddNewsRow(item, scope));
        }
        function meAddNewsRow(item, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const c = document.getElementById(cfg.newsContainerId);
            if (!c) return;
            item = item || {};
            const row = document.createElement('div');
            row.className = 'me-row-card';
            row.innerHTML = `
                <button type="button" class="me-row-del" onclick="this.closest('.me-row-card').remove()">✕</button>
                <div style="display:grid; grid-template-columns:2fr 2fr 3fr 3fr; gap:10px; padding-right:30px;">
                    <div>
                        <span class="me-row-label">新闻链接 (href)</span>
                        <input type="text" class="form-control me-news-href" value="${escapeHtml(item.href || '')}" placeholder="/news/...">
                    </div>
                    <div>
                        <span class="me-row-label">封面图链接</span>
                        <input type="text" class="form-control me-news-img" value="${escapeHtml(item.img || '')}" placeholder="图片链接">
                    </div>
                    <div>
                        <span class="me-row-label">标题</span>
                        <input type="text" class="form-control me-news-title" value="${escapeHtml(item.title || '')}" placeholder="新闻标题">
                    </div>
                    <div>
                        <span class="me-row-label">摘要</span>
                        <textarea class="form-control me-news-desc" rows="2" placeholder="新闻摘要">${escapeHtml(item.desc || '')}</textarea>
                    </div>
                </div>`;
            c.appendChild(row);
        }
        function meGetNews(scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            return Array.from(document.querySelectorAll(`#${cfg.newsContainerId} .me-row-card`)).map(row => ({
                href: (row.querySelector('.me-news-href') || {}).value || '',
                img: (row.querySelector('.me-news-img') || {}).value || '',
                title: (row.querySelector('.me-news-title') || {}).value || '',
                desc: (row.querySelector('.me-news-desc') || {}).value || '',
            })).filter(r => r.href || r.title);
        }

        // ---- Load / Save ----
        async function loadManualEditSections(productId, scope = 'gas') {
            if (scope === 'bio') bioManualEditCurrentProductId = productId;
            else manualEditCurrentProductId = productId;
            const cfg = getManualEditScopeConfig(scope);
            const container = document.getElementById(cfg.fieldsContainerId);
            const msg = document.getElementById(cfg.msgId);
            msg.textContent = '加载中...';
            msg.style.color = '#2563eb';
            container.style.display = 'block';
            try {
                const res = await fetch(cfg.pageSectionsEndpoint + '?id=' + encodeURIComponent(productId));
                const data = await res.json();
                if (!data.success) { msg.textContent = data.message || '加载失败'; msg.style.color = '#dc3545'; return; }
                msg.textContent = '';
                const sec = data.sections || {};

                // Populate fields
                const titleEl = document.getElementById(cfg.titleId);
                const descEl = document.getElementById(cfg.descriptionId);
                const detailEl = document.getElementById(cfg.detailId);
                const appIntroEl = document.getElementById(cfg.appIntroId);
                if (titleEl) titleEl.value = sec.title || '';
                if (descEl) descEl.value = sec.description || '';
                if (detailEl) detailEl.value = sec.detail || '';
                if (appIntroEl) appIntroEl.value = sec.app_intro || '';

                meRenderImages(sec.images || [], scope);
                meRenderHighlights(sec.highlights || [], scope);
                meRenderAdvantages(sec.advantages || [], scope);
                meRenderApplications(sec.applications || [], scope);
                meRenderSpecs(sec.specs || [], scope);
                meRenderNews(sec.news || [], scope);

                // Show empty notice for sections with no data
                const missing = [];
                if (!sec.advantages || !sec.advantages.length) missing.push('产品优势');
                if (!sec.applications || !sec.applications.length) missing.push('主要应用');
                if (!sec.specs || !sec.specs.length) missing.push('技术指标');
                if (missing.length) {
                    msg.textContent = '提示：以下区块在该产品页暂未找到对应结构，添加内容后保存可能无效：' + missing.join('、');
                    msg.style.color = '#f59e0b';
                }

                // Preview link
                const previewLink = document.getElementById(cfg.previewLinkId);
                if (previewLink) {
                    previewLink.href = buildManualEditPreviewLink(productId, scope);
                    previewLink.style.display = '';
                }

                // Bind save
                document.getElementById(cfg.saveBtnId).onclick = () => saveManualEditSections(productId, scope);
            } catch (e) {
                msg.textContent = '加载失败: ' + e.message;
                msg.style.color = '#dc3545';
            }
        }

        async function saveManualEditSections(productId, scope = 'gas') {
            const cfg = getManualEditScopeConfig(scope);
            const msg = document.getElementById(cfg.msgId);
            msg.textContent = '保存中...';
            msg.style.color = '#2563eb';
            const sections = {
                title: (document.getElementById(cfg.titleId) || {}).value || '',
                description: (document.getElementById(cfg.descriptionId) || {}).value || '',
                detail: (document.getElementById(cfg.detailId) || {}).value || '',
                app_intro: (document.getElementById(cfg.appIntroId) || {}).value || '',
                images: meGetImages(scope),
                highlights: meGetHighlights(scope),
                advantages: meGetAdvantages(scope),
                applications: meGetApplications(scope),
                specs: meGetSpecs(scope),
                news: meGetNews(scope),
            };
            try {
                const res = await fetch(cfg.pageSectionsEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ productId, sections }),
                });
                const data = await res.json();
                if (data.success) {
                    msg.textContent = '✓ 保存成功';
                    msg.style.color = '#16a34a';
                } else {
                    msg.textContent = data.message || '保存失败';
                    msg.style.color = '#dc3545';
                }
            } catch (e) {
                msg.textContent = '保存失败: ' + e.message;
                msg.style.color = '#dc3545';
            }
        }

        function bioMeToggleSection(name) { meToggleSection(name, 'bio'); }
        function bioMeAddImageRow(src = '', isFirst = false) { meAddImageRow(src, isFirst, 'bio'); }
        function bioMeAddHighlightRow(text = '') { meAddHighlightRow(text, 'bio'); }
        function bioMeAddAdvantageRow(item = null) { meAddAdvantageRow(item, 'bio'); }
        function bioMeAddApplicationRow(item = null) { meAddApplicationRow(item, 'bio'); }
        function bioMeAddSpecRow(item = null) { meAddSpecRow(item, 'bio'); }
        function bioMeAddNewsRow(item = null) { meAddNewsRow(item, 'bio'); }

        function switchBioProductTab(tabName, btn) {
            document.querySelectorAll('#view-bio-products .tab-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');

            document.querySelectorAll('#view-bio-products .tab-content').forEach(c => c.classList.remove('active'));
            const tab = document.getElementById(`bio-product-tab-${tabName}`);
            if (tab) {
                tab.classList.add('active');
                renderTabGuide(tab);
            }
            if (tabName === 'ai') bindBioAiProductEvents();
            if (tabName === 'manual-edit') {
                if (!bioProductsData.length) {
                    loadBioProducts().then(() => initBioManualEditTab()).catch(() => initBioManualEditTab());
                } else {
                    initBioManualEditTab();
                }
            }
            if (tabName === 'industries' && !bioIndustryFiltersData.length) {
                loadBioIndustryFilters();
            }
        }

        function switchHomeTab(tabName, btn) {
            const homeView = document.getElementById('view-home');
            if (!homeView) return;

            const targetBtn = btn || homeView.querySelector(`[data-home-tab="${tabName}"]`);
            homeView.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (targetBtn) targetBtn.classList.add('active');

            homeView.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            const tab = document.getElementById(`home-tab-${tabName}`);
            if (tab) {
                tab.classList.add('active');
                renderTabGuide(tab);
            }

            if (tabName === 'hero') loadHeroConfig();
            if (tabName === 'partners') loadPartnersConfig();
            if (tabName === 'news') loadFeaturedNews();
            if (tabName === 'products') loadFeaturedProducts();
            if (tabName === 'solutions') loadFeaturedSolutions();
        }

        // --- Hero Carousel Logic ---
        let heroConfig = { interval_seconds: 5, items: [] };

        async function loadHeroConfig() {
            const listEl = document.getElementById('heroList');
            if (!listEl) return;
            listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">加载中...</div>';

            try {
                const res = await fetch(`/api/hero?admin_t=${Date.now()}`, { cache: 'no-store' });
                const data = await res.json();
                heroConfig = data || { interval_seconds: 5, items: [] };
                document.getElementById('heroInterval').value = heroConfig.interval_seconds || 5;
                renderHeroList();
            } catch (e) {
                listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">加载失败</div>';
            }
        }

        function renderHeroList() {
            const listEl = document.getElementById('heroList');
            if (!listEl) return;
            const items = heroConfig.items || [];

            if (items.length === 0) {
                listEl.innerHTML = '<div class="no-data">暂无轮播项</div>';
                return;
            }

            listEl.innerHTML = items.map(item => `
                <div class="hero-item" data-id="${item.id}">
                    <div class="drag-handle"><i class="fas fa-grip-vertical"></i></div>
                    <div class="hero-preview">
                        ${item.type === 'video'
                    ? `<video src="${item.url}" muted playsinline></video>`
                    : `<img src="${item.url}" alt="hero">`}
                    </div>
                    <div class="hero-meta">
                        <div style="font-weight: 600; color: #333;">
                            ${item.type === 'video' ? '视频' : '图片'} · ${item.source === 'upload' ? '本地上传' : 'CDN链接'}
                        </div>
                        <div class="hero-url">${escapeHtml(item.url)}</div>
                    </div>
                    <button class="btn-sm btn-danger" onclick="deleteHeroItem('${item.id}')">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            `).join('');

            if (typeof Sortable !== 'undefined') {
                new Sortable(listEl, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function () {
                        syncHeroOrder();
                        saveHeroConfig(true);
                    }
                });
            }
        }

        function syncHeroOrder() {
            const listEl = document.getElementById('heroList');
            if (!listEl) return;
            const ids = Array.from(listEl.querySelectorAll('.hero-item')).map(el => el.dataset.id);
            heroConfig.items = ids.map(id => heroConfig.items.find(item => item.id === id)).filter(Boolean);
        }

        async function saveHeroConfig(silent = false) {
            const msg = document.getElementById('heroSaveMsg');
            if (msg) msg.textContent = '';

            syncHeroOrder();
            const interval = parseInt(document.getElementById('heroInterval').value, 10);
            heroConfig.interval_seconds = isNaN(interval) ? 5 : interval;

            try {
                const res = await fetch('/api/hero', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(heroConfig)
                });
                const data = await res.json();
                if (data.success) {
                    heroConfig = data.config || heroConfig;
                    if (!silent && msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                    renderHeroList();
                } else if (!silent && msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (!silent && msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        function addHeroUrlItem() {
            const urlInput = document.getElementById('heroUrlInput');
            const typeInput = document.getElementById('heroUrlType');
            const url = (urlInput.value || '').trim();
            const type = (typeInput.value || 'image').toLowerCase();
            if (!url) {
                alert('请输入链接');
                return;
            }

            heroConfig.items = heroConfig.items || [];
            heroConfig.items.push(makeHeroUrlItem(url, type));

            urlInput.value = '';
            renderHeroList();
            saveHeroConfig();
        }

        function addHeroUrlBatch() {
            const batchInput = document.getElementById('heroUrlBatch');
            const typeInput = document.getElementById('heroUrlType');
            const type = (typeInput.value || 'image').toLowerCase();
            const raw = (batchInput.value || '').trim();
            if (!raw) {
                alert('请输入链接');
                return;
            }

            const urls = raw.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
            if (urls.length === 0) {
                alert('请输入有效链接');
                return;
            }

            heroConfig.items = heroConfig.items || [];
            urls.forEach(url => {
                heroConfig.items.push(makeHeroUrlItem(url, type));
            });

            batchInput.value = '';
            renderHeroList();
            saveHeroConfig();
        }

        function makeHeroUrlItem(url, type) {
            return {
                id: `url_${Date.now()}_${Math.random().toString(16).slice(2)}`,
                type,
                url,
                source: 'url'
            };
        }

        async function deleteHeroItem(id) {
            if (!await showGlobalConfirm('确定删除该轮播项吗？此操作无法撤销。')) return;
            try {
                const res = await fetch(`/api/hero/items/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    loadHeroConfig();
                } else {
                    alert('删除失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        // Hero file upload handling
        const heroUploadZone = document.getElementById('heroUploadZone');
        const heroFileInput = document.getElementById('heroFileInput');

        if (heroUploadZone && heroFileInput) {
            heroUploadZone.addEventListener('click', () => heroFileInput.click());

            heroUploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                heroUploadZone.classList.add('dragover');
            });

            heroUploadZone.addEventListener('dragleave', () => {
                heroUploadZone.classList.remove('dragover');
            });

            heroUploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                heroUploadZone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) uploadHeroFile(files[0]);
            });

            heroFileInput.addEventListener('change', () => {
                if (heroFileInput.files.length > 0) {
                    uploadHeroFile(heroFileInput.files[0]);
                }
            });
        }

        async function uploadHeroFile(file) {
            const name = (file.name || '').toLowerCase();
            const type = (file.type || '').toLowerCase();
            const nameOk = (/\.(png|jpg|jpeg|mp4)$/i).test(name);
            const typeOk = (type === 'image/png' || type === 'image/jpeg' || type === 'video/mp4');
            if (!nameOk && !typeOk) {
                alert('只支持 PNG/JPG/JPEG/MP4 文件');
                return;
            }

            const progress = document.getElementById('heroUploadProgress');
            if (progress) progress.style.display = 'block';

            try {
                const formData = new FormData();
                formData.append('file', file);

                const res = await fetch('/api/hero/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    loadHeroConfig();
                } else {
                    alert(data.message || '上传失败');
                }
            } catch (e) {
                alert('上传失败: 网络错误');
            } finally {
                if (progress) progress.style.display = 'none';
                if (heroFileInput) heroFileInput.value = '';
            }
        }

        // --- Partners Logic ---
        let partnersConfig = { items: [] };
        let homeSectionVisibility = { partners: true, products: true, news: true, solutions: true };

        function updateHomeSectionVisibilityUI(section) {
            const isVisible = !!homeSectionVisibility[section];
            const statusEl = document.getElementById(`${section}VisibilityStatus`);
            const btnEl = document.getElementById(`${section}VisibilityToggleBtn`);
            if (statusEl) {
                statusEl.textContent = isVisible ? '显示中' : '已隐藏';
                statusEl.style.color = isVisible ? '#28a745' : '#dc3545';
            }
            if (btnEl) {
                btnEl.textContent = isVisible ? '隐藏' : '显示';
            }
        }

        async function loadHomeSectionVisibility() {
            try {
                const res = await fetch('/api/home/section-visibility');
                const data = await res.json();
                homeSectionVisibility = {
                    partners: data.partners !== false,
                    products: data.products !== false,
                    news: data.news !== false,
                    solutions: data.solutions !== false
                };
            } catch (e) {
                homeSectionVisibility = { partners: true, products: true, news: true, solutions: true };
            }
            updateHomeSectionVisibilityUI('partners');
            updateHomeSectionVisibilityUI('products');
            updateHomeSectionVisibilityUI('news');
            updateHomeSectionVisibilityUI('solutions');
        }

        async function toggleHomeSectionVisibility(section) {
            const nextVisible = !homeSectionVisibility[section];
            try {
                const payload = { ...homeSectionVisibility, [section]: nextVisible };
                const res = await fetch('/api/home/section-visibility', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    homeSectionVisibility = data.config || payload;
                    updateHomeSectionVisibilityUI(section);
                    return;
                }
                alert(data.message || '保存失败');
            } catch (e) {
                alert('网络错误');
            }
        }

        async function loadPartnersConfig() {
            const listEl = document.getElementById('partnersList');
            if (!listEl) return;
            listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">加载中...</div>';
            loadHomeSectionVisibility();

            try {
                const res = await fetch('/api/partners');
                const data = await res.json();
                partnersConfig = data || { items: [] };
                renderPartnersList();
            } catch (e) {
                listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">加载失败</div>';
            }
        }

        function renderPartnersList() {
            const listEl = document.getElementById('partnersList');
            if (!listEl) return;
            const items = partnersConfig.items || [];

            if (items.length === 0) {
                listEl.innerHTML = '<div class="no-data">暂无徽标</div>';
                return;
            }

            listEl.innerHTML = items.map(item => `
                <div class="hero-item" data-id="${item.id}">
                    <div class="drag-handle"><i class="fas fa-grip-vertical"></i></div>
                    <div class="hero-preview">
                        <img src="${item.url}" alt="logo">
                    </div>
                    <div class="hero-meta">
                        <div style="font-weight: 600; color: #333;">${item.source === 'upload' ? '本地上传' : 'CDN链接'}</div>
                        <div class="hero-url">${escapeHtml(item.url)}</div>
                    </div>
                    <button class="btn-sm btn-danger" onclick="deletePartnerItem('${item.id}')">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            `).join('');

            if (typeof Sortable !== 'undefined') {
                new Sortable(listEl, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function () {
                        syncPartnersOrder();
                        savePartnersConfig(true);
                    }
                });
            }
        }

        function syncPartnersOrder() {
            const listEl = document.getElementById('partnersList');
            if (!listEl) return;
            const ids = Array.from(listEl.querySelectorAll('.hero-item')).map(el => el.dataset.id);
            partnersConfig.items = ids.map(id => partnersConfig.items.find(item => item.id === id)).filter(Boolean);
        }

        async function savePartnersConfig(silent = false) {
            syncPartnersOrder();
            try {
                const res = await fetch('/api/partners', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(partnersConfig)
                });
                const data = await res.json();
                if (data.success) {
                    partnersConfig = data.config || partnersConfig;
                    if (!silent) {
                        alert('保存成功');
                    }
                    renderPartnersList();
                } else if (!silent) {
                    alert(data.message || '保存失败');
                }
            } catch (e) {
                if (!silent) alert('网络错误');
            }
        }

        function addPartnerUrlItem() {
            const urlInput = document.getElementById('partnersUrlInput');
            const url = (urlInput.value || '').trim();
            if (!url) {
                alert('请输入链接');
                return;
            }
            partnersConfig.items = partnersConfig.items || [];
            partnersConfig.items.push({
                id: `url_${Date.now()}_${Math.random().toString(16).slice(2)}`,
                url,
                source: 'url'
            });
            urlInput.value = '';
            savePartnersConfig(true);
            renderPartnersList();
        }

        function addPartnerUrlBatch() {
            const batchInput = document.getElementById('partnersUrlBatch');
            const raw = (batchInput.value || '').trim();
            if (!raw) {
                alert('请输入链接');
                return;
            }
            const urls = raw.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
            if (urls.length === 0) {
                alert('请输入有效链接');
                return;
            }
            partnersConfig.items = partnersConfig.items || [];
            urls.forEach(url => {
                partnersConfig.items.push({
                    id: `url_${Date.now()}_${Math.random().toString(16).slice(2)}`,
                    url,
                    source: 'url'
                });
            });
            batchInput.value = '';
            savePartnersConfig(true);
            renderPartnersList();
        }

        async function deletePartnerItem(id) {
            if (!await showGlobalConfirm('确定删除该徽标吗？此操作无法撤销。')) return;
            try {
                const res = await fetch(`/api/partners/items/${id}`, { method: 'DELETE' });
                if (res.ok) {
                    loadPartnersConfig();
                } else {
                    alert('删除失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        const partnersUploadZone = document.getElementById('partnersUploadZone');
        const partnersFileInput = document.getElementById('partnersFileInput');

        if (partnersUploadZone && partnersFileInput) {
            partnersUploadZone.addEventListener('click', () => partnersFileInput.click());

            partnersUploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                partnersUploadZone.classList.add('dragover');
            });

            partnersUploadZone.addEventListener('dragleave', () => {
                partnersUploadZone.classList.remove('dragover');
            });

            partnersUploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                partnersUploadZone.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) uploadPartnerFile(files[0]);
            });

            partnersFileInput.addEventListener('change', () => {
                if (partnersFileInput.files.length > 0) {
                    uploadPartnerFile(partnersFileInput.files[0]);
                }
            });
        }

        async function uploadPartnerFile(file) {
            const name = (file.name || '').toLowerCase();
            const type = (file.type || '').toLowerCase();
            const nameOk = (/\.(png|jpg|jpeg|svg|webp)$/i).test(name);
            const typeOk = (type === 'image/png' || type === 'image/jpeg' || type === 'image/svg+xml' || type === 'image/webp');
            if (!nameOk && !typeOk) {
                alert('只支持 PNG/JPG/JPEG/SVG/WEBP 文件');
                return;
            }

            const progress = document.getElementById('partnersUploadProgress');
            if (progress) progress.style.display = 'block';

            try {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/partners/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    loadPartnersConfig();
                } else {
                    alert(data.message || '上传失败');
                }
            } catch (e) {
                alert('上传失败: 网络错误');
            } finally {
                if (progress) progress.style.display = 'none';
                if (partnersFileInput) partnersFileInput.value = '';
            }
        }

        // --- Featured News Logic ---
        let allNewsItems = [];

        async function loadFeaturedNews() {
            const selects = [
                document.getElementById('featuredNews1'),
                document.getElementById('featuredNews2'),
                document.getElementById('featuredNews3')
            ];

            selects.forEach(sel => {
                if (sel) sel.innerHTML = '<option value="">加载中...</option>';
            });
            loadHomeSectionVisibility();

            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/news/all'),
                    fetch('/api/news/featured')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                allNewsItems = allData.items || [];
                const featuredItems = featuredData.items || [];
                const featuredLinks = featuredItems.map(item => item.link);

                const options = ['<option value="">请选择资讯</option>']
                    .concat(allNewsItems.map(item => {
                        const label = `${item.date || ''} ${item.title || ''}`.trim();
                        return `<option value="${item.link}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    sel.value = featuredLinks[idx] || '';
                    sel.addEventListener('change', updateFeaturedNewsPreview);
                });

                updateFeaturedNewsPreview();
            } catch (e) {
                console.error('Load featured news error:', e);
            }
        }

        function updateFeaturedNewsPreview() {
            const preview = document.getElementById('featuredNewsPreview');
            if (!preview) return;

            const selectedLinks = [
                document.getElementById('featuredNews1')?.value,
                document.getElementById('featuredNews2')?.value,
                document.getElementById('featuredNews3')?.value
            ].filter(Boolean);

            if (selectedLinks.length === 0) {
                preview.innerHTML = '<div style="color:#888;">未选择资讯</div>';
                return;
            }

            const items = selectedLinks.map(link => allNewsItems.find(n => n.link === link)).filter(Boolean);
            preview.innerHTML = items.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="news" style="width: 64px; height: 40px; object-fit: cover; border-radius: 6px;">
                        <div>
                            <div style="font-weight: 500;">${escapeHtml(item.title || '')}</div>
                            <div class="file-meta">${item.date || ''}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveFeaturedNews() {
            const msg = document.getElementById('featuredNewsMsg');
            if (msg) msg.textContent = '';

            const links = [
                document.getElementById('featuredNews1')?.value,
                document.getElementById('featuredNews2')?.value,
                document.getElementById('featuredNews3')?.value
            ].filter(Boolean);

            try {
                const res = await fetch('/api/news/featured', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ links })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        // --- Featured Products Logic ---
        let allProductItems = [];

        async function loadFeaturedProducts() {
            const selects = [
                document.getElementById('featuredProduct1'),
                document.getElementById('featuredProduct2'),
                document.getElementById('featuredProduct3')
            ];
            loadHomeSectionVisibility();

            selects.forEach(sel => {
                if (sel) sel.innerHTML = '<option value="">加载中...</option>';
            });

            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/products/with-settings'),
                    fetch('/api/products/featured')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                allProductItems = (allData.products || []).filter(p => !p.hidden);
                const featuredItems = featuredData.items || [];
                const featuredIds = featuredItems.map(item => item.id);

                const options = ['<option value="">请选择产品</option>']
                    .concat(allProductItems.map(item => {
                        const displayName = item.displayName || item.shortName || item.name || item.id;
                        const label = `${displayName}`.trim();
                        return `<option value="${item.id}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    sel.value = featuredIds[idx] || '';
                    sel.addEventListener('change', updateFeaturedProductsPreview);
                });

                updateFeaturedProductsPreview();
            } catch (e) {
                console.error('Load featured products error:', e);
            }
        }

        function updateFeaturedProductsPreview() {
            const preview = document.getElementById('featuredProductsPreview');
            if (!preview) return;

            const selectedIds = [
                document.getElementById('featuredProduct1')?.value,
                document.getElementById('featuredProduct2')?.value,
                document.getElementById('featuredProduct3')?.value
            ].filter(Boolean);

            if (selectedIds.length === 0) {
                preview.innerHTML = '<div style="color:#888;">未选择产品</div>';
                return;
            }

            const items = selectedIds.map(id => allProductItems.find(p => p.id === id)).filter(Boolean);
            preview.innerHTML = items.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="product" style="width: 64px; height: 40px; object-fit: contain; border-radius: 6px; background: #f7f8fa;">
                        <div>
                            <div style="font-weight: 500;">${escapeHtml(item.displayName || item.shortName || item.name || '')}</div>
                            <div class="file-meta">${escapeHtml(item.category || '')}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveFeaturedProducts() {
            const msg = document.getElementById('featuredProductsMsg');
            if (msg) msg.textContent = '';

            const ids = [
                document.getElementById('featuredProduct1')?.value,
                document.getElementById('featuredProduct2')?.value,
                document.getElementById('featuredProduct3')?.value
            ].filter(Boolean);

            try {
                const res = await fetch('/api/products/featured', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        // --- Featured Solutions Logic ---
        let allSolutionItems = [];

        async function loadFeaturedSolutions() {
            const selects = [
                document.getElementById('featuredSolution1'),
                document.getElementById('featuredSolution2'),
                document.getElementById('featuredSolution3')
            ];

            selects.forEach(sel => {
                if (sel) sel.innerHTML = '<option value="">加载中...</option>';
            });
            loadHomeSectionVisibility();

            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/solutions/all'),
                    fetch('/api/solutions/featured')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                allSolutionItems = allData.items || [];
                const featuredItems = featuredData.items || [];
                const featuredIds = featuredItems.map(item => item.id);

                const options = ['<option value="">请选择方案</option>']
                    .concat(allSolutionItems.map(item => {
                        const label = `${item.title || item.id || ''}`.trim();
                        return `<option value="${item.id}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    sel.value = featuredIds[idx] || '';
                    sel.addEventListener('change', updateFeaturedSolutionsPreview);
                });

                updateFeaturedSolutionsPreview();
            } catch (e) {
                console.error('Load featured solutions error:', e);
            }
        }

        function updateFeaturedSolutionsPreview() {
            const preview = document.getElementById('featuredSolutionsPreview');
            if (!preview) return;

            const selectedIds = [
                document.getElementById('featuredSolution1')?.value,
                document.getElementById('featuredSolution2')?.value,
                document.getElementById('featuredSolution3')?.value
            ].filter(Boolean);

            if (selectedIds.length === 0) {
                preview.innerHTML = '<div style="color:#888;">未选择方案</div>';
                return;
            }

            const items = selectedIds.map(id => allSolutionItems.find(s => s.id === id)).filter(Boolean);
            preview.innerHTML = items.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="solution" style="width: 64px; height: 40px; object-fit: cover; border-radius: 6px; background: #f7f8fa;">
                        <div>
                            <div style="font-weight: 500;">${escapeHtml(item.title || '')}</div>
                            <div class="file-meta">${escapeHtml(item.id || '')}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveFeaturedSolutions() {
            const msg = document.getElementById('featuredSolutionsMsg');
            if (msg) msg.textContent = '';

            const ids = [
                document.getElementById('featuredSolution1')?.value,
                document.getElementById('featuredSolution2')?.value,
                document.getElementById('featuredSolution3')?.value
            ].filter(Boolean);

            try {
                const res = await fetch('/api/solutions/featured', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        // --- H2 Home Video Logic ---
        let h2HomeConfig = { items: [] };

        async function loadH2HomeConfig() {
            const listEl = document.getElementById('h2HomeList');
            if (!listEl) return;
            listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">加载中...</div>';
            try {
                const res = await fetch(`/api/h2-home?admin_t=${Date.now()}`, { cache: 'no-store' });
                const data = await res.json();
                h2HomeConfig = data || { items: [] };
                renderH2HomeList();
            } catch (e) {
                listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">加载失败</div>';
            }
        }

        function renderH2HomeList() {
            const listEl = document.getElementById('h2HomeList');
            if (!listEl) return;
            const items = h2HomeConfig.items || [];

            if (items.length === 0) {
                listEl.innerHTML = '<div class="no-data">暂无视频</div>';
                return;
            }

            listEl.innerHTML = items.map(item => `
                <div class="hero-item" data-id="${item.id}">
                    <div class="drag-handle"><i class="fas fa-grip-vertical"></i></div>
                    <div class="hero-preview">
                        <video src="${item.url}" muted playsinline></video>
                    </div>
                    <div class="hero-meta">
                        <div style="font-weight: 600; color: #333;">视频 · ${isH2HomeLocalVideo(item.url) ? '本地上传' : 'CDN链接'}</div>
                        <div class="hero-url">${escapeHtml(item.url)}</div>
                    </div>
                    <button class="btn-sm btn-danger" onclick="deleteH2HomeItem('${item.id}')">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            `).join('');

            if (typeof Sortable !== 'undefined') {
                new Sortable(listEl, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function () {
                        syncH2HomeOrder();
                    }
                });
            }
        }

        function isH2HomeLocalVideo(url) {
            return typeof url === 'string' && url.startsWith('/media/h2-home/');
        }

        function syncH2HomeOrder() {
            const listEl = document.getElementById('h2HomeList');
            if (!listEl) return;
            const ids = Array.from(listEl.querySelectorAll('.hero-item')).map(el => el.dataset.id);
            h2HomeConfig.items = ids.map(id => h2HomeConfig.items.find(item => item.id === id)).filter(Boolean);
        }

        function generateClientId() {
            if (window.crypto && window.crypto.randomUUID) {
                return window.crypto.randomUUID();
            }
            return `id_${Date.now()}_${Math.floor(Math.random() * 100000)}`;
        }

        function addH2HomeUrlItem() {
            const input = document.getElementById('h2HomeUrlInput');
            const url = input?.value.trim();
            if (!url) return;
            h2HomeConfig.items = h2HomeConfig.items || [];
            h2HomeConfig.items.push({ id: generateClientId(), url });
            if (input) input.value = '';
            renderH2HomeList();
        }

        function addH2HomeUrlBatch() {
            const textarea = document.getElementById('h2HomeUrlBatch');
            const value = textarea?.value.trim();
            if (!value) return;
            const urls = value.split('\n').map(v => v.trim()).filter(Boolean);
            h2HomeConfig.items = h2HomeConfig.items || [];
            urls.forEach(url => {
                h2HomeConfig.items.push({ id: generateClientId(), url });
            });
            if (textarea) textarea.value = '';
            renderH2HomeList();
        }

        function triggerH2HomeVideoUpload() {
            const input = document.getElementById('h2HomeVideoFileInput');
            if (input) input.click();
        }

        async function uploadH2HomeVideoFiles(inputEl) {
            const msg = document.getElementById('h2HomeVideoUploadMsg');
            const files = Array.from(inputEl?.files || []);
            if (!files.length) return;

            if (msg) {
                msg.style.color = '#666';
                msg.textContent = `正在上传 ${files.length} 个视频...`;
            }

            let successCount = 0;
            const errors = [];

            for (const file of files) {
                try {
                    const formData = new FormData();
                    formData.append('file', file);
                    const res = await fetch('/api/h2-home/upload-video', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (!res.ok || !data.success || !data.item?.url) {
                        throw new Error(data.message || '上传失败');
                    }
                    h2HomeConfig.items = h2HomeConfig.items || [];
                    h2HomeConfig.items.push({
                        id: data.item.id || generateClientId(),
                        url: data.item.url
                    });
                    successCount += 1;
                } catch (e) {
                    errors.push(`${file.name}: ${e?.message || '上传失败'}`);
                }
            }

            renderH2HomeList();

            if (msg) {
                if (errors.length) {
                    msg.style.color = '#dc3545';
                    msg.textContent = `已上传 ${successCount} 个，失败 ${errors.length} 个。${errors[0] || ''}`;
                } else {
                    msg.style.color = '#28a745';
                    msg.textContent = `✓ 已上传 ${successCount} 个视频，请点击“保存设置”生效。`;
                }
            }

            if (inputEl) inputEl.value = '';
        }

        function deleteH2HomeItem(id) {
            h2HomeConfig.items = (h2HomeConfig.items || []).filter(item => item.id !== id);
            renderH2HomeList();
        }

        async function saveH2HomeConfig() {
            const msg = document.getElementById('h2HomeSaveMsg');
            if (msg) msg.textContent = '';
            syncH2HomeOrder();
            try {
                const res = await fetch('/api/h2-home', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(h2HomeConfig)
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                    h2HomeConfig = data.config || h2HomeConfig;
                    renderH2HomeList();
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        function switchH2HomeTab(tabName, btn) {
            const view = document.getElementById('view-h2-home');
            if (!view) return;
            view.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            view.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            const tab = document.getElementById(`h2-home-tab-${tabName}`);
            if (tab) {
                tab.classList.add('active');
                renderTabGuide(tab);
            }
            if (tabName === 'video') loadH2HomeConfig();
            if (tabName === 'products') loadH2HomeProducts();
            if (tabName === 'measurement-objects') loadH2MeasurementProducts();
            if (tabName === 'cases') loadH2HomeCases();
            if (tabName === 'news') loadH2HomeNews();
            if (tabName === 'navbar') {
                if (productsData.length === 0) {
                    loadProducts();
                } else {
                    updateMenuPreview();
                    loadRecommendations();
                }
                if (measurementPagesList.length === 0) {
                    loadMeasurementTargets();
                } else {
                    loadMeasurementTargets();
                }
                loadNavIndustryCategories();
            }
        }

        let h2HomeProductsAll = [];

        async function loadH2HomeProducts() {
            const selects = [
                document.getElementById('h2HomeProduct1'),
                document.getElementById('h2HomeProduct2'),
                document.getElementById('h2HomeProduct3')
            ];
            selects.forEach(sel => { if (sel) sel.innerHTML = '<option value="">加载中...</option>'; });
            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/products/gassensing'),
                    fetch('/api/h2-home/products')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                h2HomeProductsAll = (allData.products || []).filter(p => !p.hidden);
                const featuredIds = (featuredData.items || []).map(item => item.id);

                const options = ['<option value="">请选择产品</option>']
                    .concat(h2HomeProductsAll.map(item => {
                        const label = item.displayName || item.shortName || item.name || item.id;
                        return `<option value="${item.id}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    sel.value = featuredIds[idx] || '';
                    sel.addEventListener('change', updateH2HomeProductsPreview);
                });
                updateH2HomeProductsPreview();
            } catch (e) {
                console.error('Load h2 products error:', e);
            }
        }

        function updateH2HomeProductsPreview() {
            const preview = document.getElementById('h2HomeProductsPreview');
            if (!preview) return;
            const selectedIds = [
                document.getElementById('h2HomeProduct1')?.value,
                document.getElementById('h2HomeProduct2')?.value,
                document.getElementById('h2HomeProduct3')?.value
            ].filter(Boolean);
            if (!selectedIds.length) {
                preview.innerHTML = '<div style="color:#888;">未选择产品</div>';
                return;
            }
            const items = selectedIds.map(id => h2HomeProductsAll.find(p => p.id === id)).filter(Boolean);
            preview.innerHTML = items.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="product" style="width: 64px; height: 40px; object-fit: contain; border-radius: 6px; background: #f7f8fa;">
                        <div>
                            <div style="font-weight: 500;">${escapeHtml(item.displayName || item.shortName || item.name || '')}</div>
                            <div class="file-meta">${escapeHtml(item.category || '')}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveH2HomeProducts() {
            const msg = document.getElementById('h2HomeProductsMsg');
            if (msg) msg.textContent = '';
            const ids = [
                document.getElementById('h2HomeProduct1')?.value,
                document.getElementById('h2HomeProduct2')?.value,
                document.getElementById('h2HomeProduct3')?.value
            ].filter(Boolean);
            try {
                const res = await fetch('/api/h2-home/products', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        let h2MeasurementProductsAll = [];
        let h2MeasurementProductsPages = [];
        const H2_MEASUREMENT_PRODUCT_SLOTS = 4;

        function getH2MeasurementProductLabel(item) {
            return item.displayName || item.cardTitle || item.shortName || item.name || item.id || '';
        }

        function getH2MeasurementProductOptionsHtml() {
            return ['<option value="">请选择产品</option>']
                .concat(h2MeasurementProductsAll.map(item => `
                    <option value="${item.id}">${escapeHtml(getH2MeasurementProductLabel(item))}</option>
                `))
                .join('');
        }

        function getH2MeasurementPageById(pageId) {
            return h2MeasurementProductsPages.find(item => item.id === pageId) || null;
        }

        function renderH2MeasurementProductsPreview(pageId) {
            const preview = document.getElementById(`h2MeasurementPreview-${pageId}`);
            if (!preview) return;
            const page = getH2MeasurementPageById(pageId);
            const selectedIds = Array.isArray(page?.selectedIds) ? page.selectedIds : [];
            const items = selectedIds
                .map(id => h2MeasurementProductsAll.find(product => product.id === id))
                .filter(Boolean);

            if (!items.length) {
                preview.innerHTML = '<div style="color:#888;">未选择产品，前台将保留页面原有内容</div>';
                return;
            }

            preview.innerHTML = items.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.cardImage || item.image || ''}" alt="product"
                            style="width:64px; height:40px; object-fit:contain; border-radius:6px; background:#f7f8fa;">
                        <div>
                            <div style="font-weight:500;">${escapeHtml(getH2MeasurementProductLabel(item))}</div>
                            <div class="file-meta">${escapeHtml(item.category || '')}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function syncH2MeasurementProductsPage(pageId) {
            const page = getH2MeasurementPageById(pageId);
            if (!page) return;
            const selects = Array.from(document.querySelectorAll(`.h2-measurement-product-select[data-page-id="${pageId}"]`));
            const seen = new Set();
            const selectedIds = [];

            selects.forEach(sel => {
                const value = (sel.value || '').trim();
                if (!value || seen.has(value)) {
                    if (value && seen.has(value)) sel.value = '';
                    return;
                }
                seen.add(value);
                selectedIds.push(value);
            });

            page.selectedIds = selectedIds.slice(0, H2_MEASUREMENT_PRODUCT_SLOTS);
            renderH2MeasurementProductsPreview(pageId);
        }

        function renderH2MeasurementProductsEditor() {
            const container = document.getElementById('h2MeasurementProductsEditor');
            if (!container) return;

            if (!h2MeasurementProductsPages.length) {
                container.innerHTML = '<div style="color:#888;">未找到测量页面</div>';
                return;
            }

            const optionsHtml = getH2MeasurementProductOptionsHtml();
            container.innerHTML = h2MeasurementProductsPages.map(page => {
                const selectedIds = Array.isArray(page.selectedIds) ? page.selectedIds : [];
                const selectsHtml = Array.from({ length: H2_MEASUREMENT_PRODUCT_SLOTS }, (_, idx) => `
                    <div class="form-group" style="margin-bottom:0;">
                        <label>产品 ${idx + 1}</label>
                        <select class="form-control h2-measurement-product-select"
                            data-page-id="${page.id}" data-slot="${idx}">
                            ${optionsHtml}
                        </select>
                    </div>
                `).join('');

                return `
                    <div class="card" style="padding:20px;">
                        <div style="display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; align-items:center;">
                            <div>
                                <div style="font-weight:600; color:#333;">${escapeHtml(page.title || page.filename || page.id)}</div>
                                <div class="file-meta"><code>/pages/measurement/${escapeHtml(page.filename || `${page.id}.html`)}</code></div>
                            </div>
                            <div style="color:#888; font-size:13px;">最多选择 ${H2_MEASUREMENT_PRODUCT_SLOTS} 个产品</div>
                        </div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-top:16px;">
                            ${selectsHtml}
                        </div>
                        <div id="h2MeasurementPreview-${page.id}" class="file-list" style="margin-top:16px;"></div>
                    </div>
                `;
            }).join('');

            h2MeasurementProductsPages.forEach(page => {
                const selectedIds = Array.isArray(page.selectedIds) ? page.selectedIds : [];
                const selects = Array.from(document.querySelectorAll(`.h2-measurement-product-select[data-page-id="${page.id}"]`));
                selects.forEach((sel, idx) => {
                    sel.value = selectedIds[idx] || '';
                    sel.addEventListener('change', function () {
                        syncH2MeasurementProductsPage(page.id);
                    });
                });
                renderH2MeasurementProductsPreview(page.id);
            });
        }

        async function loadH2MeasurementProducts() {
            const container = document.getElementById('h2MeasurementProductsEditor');
            if (container) {
                container.innerHTML = '<div style="color:#888;">加载中...</div>';
            }
            try {
                const [productsRes, pagesRes] = await Promise.all([
                    fetch('/api/products/gassensing'),
                    fetch('/api/h2-home/measurement-products')
                ]);
                const productsData = await productsRes.json();
                const pagesData = await pagesRes.json();

                h2MeasurementProductsAll = (productsData.products || []).filter(item => !item.hidden);
                h2MeasurementProductsPages = (pagesData.pages || []).map(page => ({
                    ...page,
                    selectedIds: Array.isArray(page.selectedIds) ? page.selectedIds : []
                }));
                renderH2MeasurementProductsEditor();
            } catch (e) {
                console.error('Load h2 measurement products error:', e);
                if (container) {
                    container.innerHTML = '<div style="color:#dc3545;">加载失败，请刷新后重试</div>';
                }
            }
        }

        async function saveH2MeasurementProducts() {
            const msg = document.getElementById('h2MeasurementProductsMsg');
            if (msg) msg.textContent = '';

            h2MeasurementProductsPages.forEach(page => syncH2MeasurementProductsPage(page.id));
            const items = h2MeasurementProductsPages.map(page => ({
                id: page.id,
                productIds: Array.isArray(page.selectedIds) ? page.selectedIds : []
            }));

            try {
                const res = await fetch('/api/h2-home/measurement-products', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                    if (data.config?.measurementProducts) {
                        h2MeasurementProductsPages = h2MeasurementProductsPages.map(page => ({
                            ...page,
                            selectedIds: Array.isArray(data.config.measurementProducts[page.id])
                                ? data.config.measurementProducts[page.id]
                                : []
                        }));
                        renderH2MeasurementProductsEditor();
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                console.error('Save h2 measurement products error:', e);
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        let h2HomeCasesAll = [];

        async function loadH2HomeCases() {
            const selects = [
                document.getElementById('h2HomeCase1'),
                document.getElementById('h2HomeCase2'),
                document.getElementById('h2HomeCase3'),
                document.getElementById('h2HomeCase4'),
                document.getElementById('h2HomeCase5'),
                document.getElementById('h2HomeCase6')
            ];
            const subtitleInputs = [
                document.getElementById('h2HomeCaseSubtitle1'),
                document.getElementById('h2HomeCaseSubtitle2'),
                document.getElementById('h2HomeCaseSubtitle3'),
                document.getElementById('h2HomeCaseSubtitle4'),
                document.getElementById('h2HomeCaseSubtitle5'),
                document.getElementById('h2HomeCaseSubtitle6')
            ];
            const titleInputs = [
                document.getElementById('h2HomeCaseTitle1'),
                document.getElementById('h2HomeCaseTitle2'),
                document.getElementById('h2HomeCaseTitle3'),
                document.getElementById('h2HomeCaseTitle4'),
                document.getElementById('h2HomeCaseTitle5'),
                document.getElementById('h2HomeCaseTitle6')
            ];
            selects.forEach(sel => { if (sel) sel.innerHTML = '<option value="">加载中...</option>'; });
            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/cases/gassensing'),
                    fetch('/api/h2-home/cases')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                h2HomeCasesAll = allData.items || [];
                const featuredItems = featuredData.items || [];

                const options = ['<option value="">请选择案例</option>']
                    .concat(h2HomeCasesAll.map(item => {
                        const label = item.title || item.id;
                        return `<option value="${item.id}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    const featured = featuredItems[idx];
                    if (featured) {
                        sel.value = featured.id || '';
                        if (subtitleInputs[idx]) subtitleInputs[idx].value = featured.customSubtitle || '';
                        if (titleInputs[idx]) titleInputs[idx].value = featured.customTitle || '';
                    }
                    sel.addEventListener('change', updateH2HomeCasesPreview);
                });

                // Add event listeners for title inputs to update preview
                subtitleInputs.forEach(input => { if (input) input.addEventListener('input', updateH2HomeCasesPreview); });
                titleInputs.forEach(input => { if (input) input.addEventListener('input', updateH2HomeCasesPreview); });

                updateH2HomeCasesPreview();
            } catch (e) {
                console.error('Load h2 cases error:', e);
            }
        }

        function updateH2HomeCasesPreview() {
            const preview = document.getElementById('h2HomeCasesPreview');
            if (!preview) return;

            const previewItems = [];
            for (let i = 1; i <= 6; i++) {
                const caseId = document.getElementById(`h2HomeCase${i}`)?.value;
                if (!caseId) continue;
                const caseItem = h2HomeCasesAll.find(p => p.id === caseId);
                if (!caseItem) continue;

                const customSubtitle = document.getElementById(`h2HomeCaseSubtitle${i}`)?.value || '典型案例';
                const customTitle = document.getElementById(`h2HomeCaseTitle${i}`)?.value || caseItem.title || '';

                previewItems.push({
                    ...caseItem,
                    displaySubtitle: customSubtitle,
                    displayTitle: customTitle
                });
            }

            if (!previewItems.length) {
                preview.innerHTML = '<div style="color:#888;">未选择案例</div>';
                return;
            }

            preview.innerHTML = previewItems.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="case" style="width: 64px; height: 40px; object-fit: cover; border-radius: 6px; background: #f7f8fa;">
                        <div>
                            <div style="font-size: 11px; color: #0066cc; font-weight: 600;">${escapeHtml(item.displaySubtitle)}</div>
                            <div style="font-weight: 500;">${escapeHtml(item.displayTitle)}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveH2HomeCases() {
            const msg = document.getElementById('h2HomeCasesMsg');
            if (msg) msg.textContent = '';

            const items = [];
            for (let i = 1; i <= 6; i++) {
                const caseId = document.getElementById(`h2HomeCase${i}`)?.value;
                if (!caseId) continue;
                items.push({
                    id: caseId,
                    customSubtitle: document.getElementById(`h2HomeCaseSubtitle${i}`)?.value || '',
                    customTitle: document.getElementById(`h2HomeCaseTitle${i}`)?.value || ''
                });
            }

            try {
                const res = await fetch('/api/h2-home/cases', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        // --- H2 Home News ---
        let h2HomeNewsAll = [];

        async function loadH2HomeNews() {
            const selects = [
                document.getElementById('h2HomeNews1'),
                document.getElementById('h2HomeNews2'),
                document.getElementById('h2HomeNews3')
            ];
            const tagInputs = [
                document.getElementById('h2HomeNewsTag1'),
                document.getElementById('h2HomeNewsTag2'),
                document.getElementById('h2HomeNewsTag3')
            ];
            const titleInputs = [
                document.getElementById('h2HomeNewsTitle1'),
                document.getElementById('h2HomeNewsTitle2'),
                document.getElementById('h2HomeNewsTitle3')
            ];
            const descInputs = [
                document.getElementById('h2HomeNewsDesc1'),
                document.getElementById('h2HomeNewsDesc2'),
                document.getElementById('h2HomeNewsDesc3')
            ];
            selects.forEach(sel => { if (sel) sel.innerHTML = '<option value="">加载中...</option>'; });
            try {
                const [allRes, featuredRes] = await Promise.all([
                    fetch('/api/news/list'),
                    fetch('/api/h2-home/news')
                ]);
                const allData = await allRes.json();
                const featuredData = await featuredRes.json();

                h2HomeNewsAll = allData.items || [];
                const featuredItems = featuredData.items || [];

                const options = ['<option value="">请选择新闻</option>']
                    .concat(h2HomeNewsAll.map(item => {
                        const label = item.title || item.link;
                        return `<option value="${item.link}">${escapeHtml(label)}</option>`;
                    }))
                    .join('');

                selects.forEach((sel, idx) => {
                    if (!sel) return;
                    sel.innerHTML = options;
                    const featured = featuredItems[idx];
                    if (featured) {
                        sel.value = featured.link || '';
                        if (tagInputs[idx]) tagInputs[idx].value = featured.customTag || '';
                        if (titleInputs[idx]) titleInputs[idx].value = featured.customTitle || '';
                        if (descInputs[idx]) descInputs[idx].value = featured.customDesc || '';
                    }
                    sel.addEventListener('change', updateH2HomeNewsPreview);
                });

                tagInputs.forEach(input => { if (input) input.addEventListener('input', updateH2HomeNewsPreview); });
                titleInputs.forEach(input => { if (input) input.addEventListener('input', updateH2HomeNewsPreview); });
                descInputs.forEach(input => { if (input) input.addEventListener('input', updateH2HomeNewsPreview); });

                updateH2HomeNewsPreview();
            } catch (e) {
                console.error('Load h2 news error:', e);
            }
        }

        function updateH2HomeNewsPreview() {
            const preview = document.getElementById('h2HomeNewsPreview');
            if (!preview) return;

            const previewItems = [];
            for (let i = 1; i <= 3; i++) {
                const newsLink = document.getElementById(`h2HomeNews${i}`)?.value;
                if (!newsLink) continue;
                const newsItem = h2HomeNewsAll.find(p => p.link === newsLink);
                if (!newsItem) continue;

                const customTag = document.getElementById(`h2HomeNewsTag${i}`)?.value || '新闻资讯';
                const customTitle = document.getElementById(`h2HomeNewsTitle${i}`)?.value || newsItem.title || '';
                const customDesc = document.getElementById(`h2HomeNewsDesc${i}`)?.value || newsItem.summary || '';

                previewItems.push({
                    ...newsItem,
                    displayTag: customTag,
                    displayTitle: customTitle,
                    displayDesc: customDesc
                });
            }

            if (!previewItems.length) {
                preview.innerHTML = '<div style="color:#888;">未选择新闻</div>';
                return;
            }

            preview.innerHTML = previewItems.map(item => `
                <div class="file-item">
                    <div class="file-info">
                        <img src="${item.image || ''}" alt="news" style="width: 64px; height: 40px; object-fit: cover; border-radius: 6px; background: #f7f8fa;">
                        <div>
                            <div style="font-size: 11px; color: #0066cc; font-weight: 600;">${escapeHtml(item.displayTag)}</div>
                            <div style="font-weight: 500;">${escapeHtml(item.displayTitle)}</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function saveH2HomeNews() {
            const msg = document.getElementById('h2HomeNewsMsg');
            if (msg) msg.textContent = '';

            const items = [];
            for (let i = 1; i <= 3; i++) {
                const newsLink = document.getElementById(`h2HomeNews${i}`)?.value;
                if (!newsLink) continue;
                items.push({
                    link: newsLink,
                    customTag: document.getElementById(`h2HomeNewsTag${i}`)?.value || '',
                    customTitle: document.getElementById(`h2HomeNewsTitle${i}`)?.value || '',
                    customDesc: document.getElementById(`h2HomeNewsDesc${i}`)?.value || ''
                });
            }

            try {
                const res = await fetch('/api/h2-home/news', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const data = await res.json();
                if (data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ 保存成功';
                        setTimeout(() => { msg.textContent = ''; }, 3000);
                    }
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误';
                }
            }
        }

        // --- News Create ---
        let editingNewsLink = '';
        let newsEditorMode = 'visual';
        let newsEditorSavedRange = null;
        let aiTypesetPending = false;
        let aiTypesetBeforeHtml = '';
        let newsPreviewBridgeBound = false;
        let newsImageProcessingPromise = Promise.resolve({ imported: 0, failed: 0, total: 0 });
        const newsEditorEl = document.getElementById('newsContentEditor');
        const newsSourceEl = document.getElementById('newsContent');
        const newsAiActionsEl = document.getElementById('newsAiActions');

        function updateAiTypesetActionVisibility() {
            if (!newsAiActionsEl) return;
            newsAiActionsEl.style.display = aiTypesetPending ? 'flex' : 'none';
        }

        function bindNewsPreviewBridge() {
            if (newsPreviewBridgeBound) return;
            window.addEventListener('message', (event) => {
                const data = event.data || {};
                if (data.type !== 'news-preview-height') return;
                const frameEl = document.getElementById('newsPreviewFrame');
                if (!frameEl) return;
                if (event.source !== frameEl.contentWindow) return;
                const h = Number(data.height || 0);
                if (!Number.isFinite(h) || h <= 0) return;
                const target = Math.min(Math.max(Math.ceil(h + 20), 640), 5200);
                const current = parseInt(frameEl.style.height || '640', 10);
                if (Math.abs(target - current) > 6) {
                    frameEl.style.height = `${target}px`;
                }
            });
            newsPreviewBridgeBound = true;
        }

        function revertAiTypesetChange() {
            if (!aiTypesetPending) return;
            setNewsEditorHtml(aiTypesetBeforeHtml || '');
            switchNewsEditorMode('visual');
            aiTypesetPending = false;
            aiTypesetBeforeHtml = '';
            updateAiTypesetActionVisibility();
            updateNewsPreview();
            const msg = document.getElementById('newsCreateMsg');
            if (msg) {
                msg.style.color = '#666';
                msg.textContent = '已撤销替换，恢复到 AI 排版前内容';
            }
        }

        function saveNewsEditorSelection() {
            if (!newsEditorEl || newsEditorMode !== 'visual') return;
            const sel = window.getSelection();
            if (!sel || sel.rangeCount === 0) return;
            const range = sel.getRangeAt(0);
            if (!newsEditorEl.contains(range.commonAncestorContainer)) return;
            newsEditorSavedRange = range.cloneRange();
        }

        function restoreNewsEditorSelection() {
            if (!newsEditorEl || newsEditorMode !== 'visual' || !newsEditorSavedRange) return;
            const sel = window.getSelection();
            if (!sel) return;
            sel.removeAllRanges();
            sel.addRange(newsEditorSavedRange);
        }

        function getNewsEditorHtml() {
            if (!newsEditorEl || !newsSourceEl) return '';
            if (newsEditorMode === 'source') {
                return (newsSourceEl.value || '').trim();
            }
            newsSourceEl.value = (newsEditorEl.innerHTML || '').trim();
            return newsSourceEl.value;
        }

        function setNewsEditorHtml(html) {
            if (!newsEditorEl || !newsSourceEl) return;
            const value = html || '';
            newsEditorEl.innerHTML = value;
            newsSourceEl.value = value;
        }

        function getNewsFeishuImportMsgEl() {
            return document.getElementById('newsFeishuImportMsg');
        }

        function setNewsFeishuImportMessage(message, color = '#666') {
            const el = getNewsFeishuImportMsgEl();
            if (!el) return;
            el.style.color = color;
            el.textContent = String(message || '');
        }

        function getNewsImageProcessMsgEl() {
            return document.getElementById('newsImageProcessMsg');
        }

        function getNewsImageProcessUi() {
            const el = getNewsImageProcessMsgEl();
            if (!el) return null;
            if (el.dataset.enhanced !== '1') {
                el.dataset.enhanced = '1';
                el.innerHTML = [
                    '<span class="news-image-process-icon" aria-hidden="true"></span>',
                    '<div class="news-image-process-main">',
                    '<div class="news-image-process-title"></div>',
                    '<div class="news-image-process-caption" hidden></div>',
                    '<div class="news-image-process-progress" hidden><div class="news-image-process-progress-bar"></div></div>',
                    '</div>'
                ].join('');
            }
            return {
                el,
                titleEl: el.querySelector('.news-image-process-title'),
                captionEl: el.querySelector('.news-image-process-caption'),
                progressEl: el.querySelector('.news-image-process-progress'),
                progressBarEl: el.querySelector('.news-image-process-progress-bar')
            };
        }

        function getNewsImageProcessMeta(message, color = '#666') {
            const text = String(message || '').trim();
            if (!text) {
                return { state: 'hidden', title: '', caption: '', progress: null };
            }

            const convertingMatch = text.match(/正在转换第\s*(\d+)\s*张图，共\s*(\d+)\s*张/);
            if (convertingMatch) {
                const current = Number(convertingMatch[1]) || 0;
                const total = Math.max(Number(convertingMatch[2]) || 0, current, 1);
                return {
                    state: 'processing',
                    title: `图片转存中 ${current}/${total}`,
                    caption: text,
                    progress: Math.max(10, Math.min(100, Math.round((current / total) * 100)))
                };
            }

            if (text.includes('正在识别粘贴图片')) {
                return {
                    state: 'processing',
                    title: '正在识别待转存图片',
                    caption: text,
                    progress: 12
                };
            }

            if (text.includes('正在上传图片')) {
                return {
                    state: 'processing',
                    title: '正在上传图片',
                    caption: text,
                    progress: 20
                };
            }

            if (text.includes('正在下载并导入图片')) {
                return {
                    state: 'processing',
                    title: '正在导入远程图片',
                    caption: text,
                    progress: 24
                };
            }

            if (text.includes('正在重试转换')) {
                return {
                    state: 'warning',
                    title: '正在重试图片转存',
                    caption: text,
                    progress: null
                };
            }

            if (text.startsWith('正在')) {
                return {
                    state: 'processing',
                    title: text,
                    caption: '处理中，请稍候...',
                    progress: null
                };
            }

            const tone = String(color || '').toLowerCase();
            if (tone.includes('28a745') || tone.includes('17935f')) {
                return {
                    state: 'success',
                    title: text,
                    caption: '已完成自动转存，可以继续编辑或发布',
                    progress: 100
                };
            }

            if (tone.includes('dc3545') || tone.includes('c84658')) {
                return {
                    state: 'error',
                    title: text,
                    caption: '请处理失败图片后再继续操作',
                    progress: null
                };
            }

            if (tone.includes('d97706') || tone.includes('d18a18')) {
                return {
                    state: 'warning',
                    title: text,
                    caption: '部分图片需要手动处理',
                    progress: null
                };
            }

            return {
                state: 'info',
                title: text,
                caption: '',
                progress: null
            };
        }

        function setNewsImageProcessMessage(message, color = '#666') {
            const ui = getNewsImageProcessUi();
            if (!ui) return;

            const { el, titleEl, captionEl, progressEl, progressBarEl } = ui;
            const meta = getNewsImageProcessMeta(message, color);
            const stateClasses = ['is-hidden', 'is-processing', 'is-success', 'is-warning', 'is-error', 'is-info'];
            el.classList.remove(...stateClasses);

            if (meta.state === 'hidden') {
                el.classList.add('is-hidden');
                el.setAttribute('aria-hidden', 'true');
                if (titleEl) titleEl.textContent = '';
                if (captionEl) {
                    captionEl.textContent = '';
                    captionEl.hidden = true;
                }
                if (progressEl) progressEl.hidden = true;
                if (progressBarEl) progressBarEl.style.width = '0%';
                return;
            }

            el.classList.add(`is-${meta.state}`);
            el.removeAttribute('aria-hidden');

            if (titleEl) titleEl.textContent = meta.title;
            if (captionEl) {
                captionEl.textContent = meta.caption || '';
                captionEl.hidden = !meta.caption;
            }
            if (progressEl && progressBarEl) {
                if (typeof meta.progress === 'number') {
                    progressEl.hidden = false;
                    progressBarEl.style.width = `${Math.max(0, Math.min(meta.progress, 100))}%`;
                } else {
                    progressEl.hidden = true;
                    progressBarEl.style.width = '0%';
                }
            }
        }

        function getNewsPlainTextFromHtml(html) {
            const div = document.createElement('div');
            div.innerHTML = html || '';
            return String(div.textContent || div.innerText || '').replace(/\s+/g, ' ').trim();
        }

        function hasNewsDraftContent() {
            const fields = [
                document.getElementById('newsTitle')?.value,
                document.getElementById('newsDate')?.value,
                document.getElementById('newsImage')?.value,
                document.getElementById('newsSummary')?.value,
                document.getElementById('newsDivision')?.value,
            ];
            if (fields.some((value) => String(value || '').trim())) {
                return true;
            }
            return !!getNewsPlainTextFromHtml(getNewsEditorHtml());
        }

        function resetNewsImportedDraftState() {
            cancelNewsEdit();
            aiTypesetPending = false;
            aiTypesetBeforeHtml = '';
            updateAiTypesetActionVisibility();
            const createMsg = document.getElementById('newsCreateMsg');
            const createLink = document.getElementById('newsCreateLink');
            if (createMsg) createMsg.textContent = '';
            if (createLink) createLink.textContent = '';
        }

        function applyImportedNewsDraft(data) {
            resetNewsImportedDraftState();
            const titleEl = document.getElementById('newsTitle');
            const dateEl = document.getElementById('newsDate');
            const categoryEl = document.getElementById('newsCategory');
            const imageEl = document.getElementById('newsImage');
            const summaryEl = document.getElementById('newsSummary');
            if (titleEl) titleEl.value = String(data?.title || '').trim();
            if (dateEl && String(data?.date || '').trim()) dateEl.value = String(data.date).trim();
            if (categoryEl && String(data?.category || '').trim()) categoryEl.value = String(data.category).trim();
            if (imageEl) imageEl.value = String(data?.image_url || '').trim();
            if (summaryEl) summaryEl.value = String(data?.summary || '').trim();
            setNewsEditorHtml(String(data?.content_html || '').trim());
            switchNewsEditorMode('visual');
            updateNewsPreview();

            const importedCount = Number(data?.imported_image_count || 0);
            const failedCount = Number(data?.image_failed_count || 0);
            if (importedCount > 0 || failedCount > 0) {
                const tone = failedCount > 0 ? '#d97706' : '#28a745';
                setNewsImageProcessMessage(
                    failedCount > 0
                        ? `飞书正文图片已转存 ${importedCount} 张，另有 ${failedCount} 张未成功转存`
                        : `飞书正文图片已转存 ${importedCount} 张`,
                    tone
                );
            } else {
                setNewsImageProcessMessage('', '#666');
            }
        }

        async function importNewsFromFeishuUrl() {
            const input = document.getElementById('newsFeishuImportUrl');
            const button = document.getElementById('newsFeishuImportBtn');
            if (input?.disabled || button?.disabled) {
                setNewsFeishuImportMessage('功能尚不完善，持续开发中', '#888');
                return;
            }
            const rawUrl = String(input?.value || '').trim();
            if (!rawUrl) {
                setNewsFeishuImportMessage('请先粘贴飞书共享链接', '#dc3545');
                return;
            }

            const isEditing = !!editingNewsLink;
            if (isEditing || hasNewsDraftContent()) {
                const confirmMessage = isEditing
                    ? '当前正在编辑一条资讯。继续导入会退出编辑状态并覆盖当前表单内容，是否继续？'
                    : '继续导入会覆盖当前已填写的标题、摘要和正文内容，是否继续？';
                const ok = await showGlobalConfirm(confirmMessage, '确认导入飞书内容');
                if (!ok) return;
            }

            if (button) button.disabled = true;
            setNewsFeishuImportMessage('正在抓取飞书分享页并解析正文...', '#666');
            try {
                const res = await fetch('/api/news/import/feishu', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: rawUrl })
                });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '飞书内容导入失败');
                }

                applyImportedNewsDraft(data);
                if (input) input.value = '';

                const warnings = Array.isArray(data.warnings)
                    ? data.warnings.map((item) => String(item || '').trim()).filter(Boolean)
                    : [];
                let message = String(data.message || '飞书内容导入成功');
                if (warnings.length > 0) {
                    message += `；${warnings.slice(0, 2).join('；')}`;
                }
                const tone = Number(data.image_failed_count || 0) > 0 || warnings.length > 0 ? '#d97706' : '#28a745';
                setNewsFeishuImportMessage(message, tone);
            } catch (error) {
                setNewsFeishuImportMessage(error?.message || '飞书内容导入失败', '#dc3545');
            } finally {
                if (button) button.disabled = false;
            }
        }

        function decodeNewsJsonAttribute(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return null;
            const attempts = [value];
            try {
                attempts.push(decodeURIComponent(value));
            } catch (e) { }
            for (const candidate of attempts) {
                try {
                    return JSON.parse(candidate);
                } catch (e) { }
            }
            return null;
        }

        function decodeNewsBase64JsonAttribute(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return null;
            try {
                return JSON.parse(window.atob(value));
            } catch (e) {
                return null;
            }
        }

        function normalizeNewsCandidateUrl(rawValue) {
            const value = String(rawValue || '').trim();
            if (!value) return '';
            if (value.startsWith('//')) {
                return `${window.location.protocol}${value}`;
            }
            return value;
        }

        function isHttpNewsCandidateUrl(rawValue) {
            const value = normalizeNewsCandidateUrl(rawValue);
            if (!value) return false;
            try {
                const url = new URL(value, window.location.origin);
                return url.protocol === 'http:' || url.protocol === 'https:';
            } catch (e) {
                return false;
            }
        }

        function isLocalNewsImageUrl(rawValue) {
            const value = normalizeNewsCandidateUrl(rawValue);
            if (!value) return false;
            if (value.startsWith('blob:') || value.startsWith('data:')) return false;
            try {
                const url = new URL(value, window.location.origin);
                if (url.origin !== window.location.origin) return false;
                return url.pathname.startsWith('/cdn_assets/')
                    || url.pathname.startsWith('/media/')
                    || url.pathname.startsWith('/assets/')
                    || url.pathname.startsWith('/uploads/');
            } catch (e) {
                return value.startsWith('/cdn_assets/')
                    || value.startsWith('/media/')
                    || value.startsWith('/assets/')
                    || value.startsWith('/uploads/');
            }
        }

        function collectNewsImageCandidateUrls(img) {
            const values = [];
            const push = (rawValue) => {
                const value = normalizeNewsCandidateUrl(rawValue);
                if (!value) return;
                values.push(value);
            };

            push(img?.getAttribute?.('src'));
            push(img?.getAttribute?.('data-src'));

            const suiteData = decodeNewsBase64JsonAttribute(img?.getAttribute?.('data-suite'));
            if (suiteData && typeof suiteData === 'object') {
                push(suiteData.originSrc);
                push(suiteData.originalSrc);
                push(suiteData.src);
            }

            const galleryHost = img?.closest?.('[data-ace-gallery-json]');
            const galleryData = decodeNewsJsonAttribute(galleryHost?.getAttribute?.('data-ace-gallery-json'));
            if (galleryData && Array.isArray(galleryData.items)) {
                galleryData.items.forEach((item) => {
                    push(item?.src);
                    try {
                        push(decodeURIComponent(String(item?.src || '')));
                    } catch (e) { }
                });
            }

            return [...new Set(values)].filter((url) => {
                if (url.startsWith('blob:') || url.startsWith('data:')) return true;
                return isHttpNewsCandidateUrl(url) && !isLocalNewsImageUrl(url);
            });
        }

        function getNewsPendingImageNodes(root = newsEditorEl) {
            if (!root) return [];
            return Array.from(root.querySelectorAll('img')).filter((img) => {
                if (img.dataset.newsLocalized === '1' || img.dataset.newsImporting === '1') {
                    return false;
                }
                const src = normalizeNewsCandidateUrl(img.getAttribute('src'));
                if (src.startsWith('blob:') || src.startsWith('data:')) {
                    return true;
                }
                return collectNewsImageCandidateUrls(img).length > 0;
            });
        }

        async function uploadNewsBlobImage(blob, fileName = '') {
            const extByType = {
                'image/jpeg': 'jpg',
                'image/png': 'png',
                'image/gif': 'gif',
                'image/webp': 'webp',
                'image/svg+xml': 'svg'
            };
            const extension = extByType[String(blob?.type || '').toLowerCase()] || 'png';
            const finalName = fileName || `news-paste-${Date.now()}.${extension}`;
            const file = blob instanceof File ? blob : new File([blob], finalName, { type: blob?.type || 'image/png' });
            const formData = new FormData();
            formData.append('file', file, file.name);
            const res = await fetch('/api/news/image/upload', {
                method: 'POST',
                body: formData
            });
            const data = await parseJsonSafe(res);
            if (!res.ok || !data.success || !data.url) {
                throw new Error(data.message || '图片上传失败');
            }
            return data;
        }

        async function importNewsRemoteImageUrl(rawUrl) {
            const res = await fetch('/api/news/image/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: rawUrl })
            });
            const data = await parseJsonSafe(res);
            if (!res.ok || !data.success || !data.url) {
                throw new Error(data.message || '图片转换失败，请改用“上传图片文件”或“导入图片链接”');
            }
            return data;
        }

        function markNewsImageAsLocalized(img, url) {
            if (!img || !url) return;
            img.setAttribute('src', url);
            img.dataset.newsLocalized = '1';
            img.removeAttribute('data-src');
            img.removeAttribute('data-suite');
            img.removeAttribute('data-lark-image-uri');
            img.removeAttribute('data-lark-image-width');
            img.removeAttribute('data-lark-image-height');
            img.removeAttribute('data-width');
            img.removeAttribute('data-height');
            const galleryHost = img.closest?.('[data-ace-gallery-json]');
            if (galleryHost) {
                galleryHost.removeAttribute('data-ace-gallery-json');
            }
        }

        async function localizeSingleNewsImageNode(img, index, total) {
            if (!img) return { success: false, error: new Error('图片节点不存在') };
            img.dataset.newsImporting = '1';
            try {
                const candidates = collectNewsImageCandidateUrls(img);
                for (const candidate of candidates) {
                    try {
                        let localData;
                        if (candidate.startsWith('blob:') || candidate.startsWith('data:')) {
                            const response = await fetch(candidate);
                            if (!response.ok) throw new Error('读取粘贴图片失败');
                            const blob = await response.blob();
                            localData = await uploadNewsBlobImage(blob, `news-paste-${Date.now()}-${index}.png`);
                        } else {
                            localData = await importNewsRemoteImageUrl(candidate);
                        }
                        markNewsImageAsLocalized(img, localData.url);
                        return { success: true, url: localData.url };
                    } catch (candidateError) {
                        // Try the next candidate URL.
                    }
                }
                throw new Error('图片转换失败，请改用“上传图片文件”或“导入图片链接”');
            } catch (error) {
                return { success: false, error };
            } finally {
                delete img.dataset.newsImporting;
            }
        }

        async function processPendingNewsImages(options = {}) {
            const { announceNoop = false } = options;
            if (!newsEditorEl) return { imported: 0, failed: 0, total: 0 };
            setNewsImageProcessMessage('正在识别粘贴图片...', '#666');
            const nodes = getNewsPendingImageNodes();
            if (nodes.length === 0) {
                if (announceNoop) {
                    setNewsImageProcessMessage('未检测到需要转换的粘贴图片', '#666');
                } else {
                    setNewsImageProcessMessage('', '#666');
                }
                return { imported: 0, failed: 0, total: 0 };
            }

            let imported = 0;
            let failed = 0;
            for (let i = 0; i < nodes.length; i += 1) {
                setNewsImageProcessMessage(`正在转换第 ${i + 1} 张图，共 ${nodes.length} 张...`, '#666');
                const result = await localizeSingleNewsImageNode(nodes[i], i + 1, nodes.length);
                if (result.success) {
                    imported += 1;
                } else {
                    failed += 1;
                }
            }

            schedulePreview();
            if (failed > 0) {
                setNewsImageProcessMessage(
                    `图片转换完成：成功 ${imported} 张，失败 ${failed} 张。失败图片请改用“上传图片文件”或“导入图片链接”`,
                    '#d97706'
                );
            } else {
                setNewsImageProcessMessage(`图片转换成功，共 ${imported} 张`, '#28a745');
            }
            return { imported, failed, total: nodes.length };
        }

        function queueNewsImageProcessing(options = {}) {
            const run = async () => {
                await new Promise((resolve) => setTimeout(resolve, 80));
                return processPendingNewsImages(options);
            };
            newsImageProcessingPromise = Promise.resolve(newsImageProcessingPromise).catch(() => ({ imported: 0, failed: 0, total: 0 })).then(run, run);
            return newsImageProcessingPromise;
        }

        async function insertNewsClipboardImages(files) {
            if (!Array.isArray(files) || files.length === 0) return;
            let imported = 0;
            let failed = 0;
            for (let i = 0; i < files.length; i += 1) {
                setNewsImageProcessMessage(`正在转换第 ${i + 1} 张图，共 ${files.length} 张...`, '#666');
                try {
                    const data = await uploadNewsBlobImage(files[i], files[i]?.name || `news-paste-${Date.now()}-${i + 1}.png`);
                    const width = getNewsImageWidthSetting();
                    insertHtmlToNewsEditor(
                        `<p style="text-align:center;"><img src="${data.url}" alt="news-image" data-news-localized="1" style="width:${width};max-width:100%;height:auto;display:block;margin:0 auto;"></p>`
                    );
                    imported += 1;
                } catch (error) {
                    failed += 1;
                }
            }
            if (failed > 0) {
                setNewsImageProcessMessage(
                    `图片转换完成：成功 ${imported} 张，失败 ${failed} 张。失败图片请改用“上传图片文件”或“导入图片链接”`,
                    '#d97706'
                );
            } else {
                setNewsImageProcessMessage(`图片转换成功，共 ${imported} 张`, '#28a745');
            }
        }

        async function ensureNewsImagesReadyForSubmit() {
            await Promise.resolve(newsImageProcessingPromise).catch(() => ({ imported: 0, failed: 0, total: 0 }));
            let pending = getNewsPendingImageNodes();
            if (pending.length === 0) return true;
            setNewsImageProcessMessage('检测到正文里仍有未转存图片，正在重试转换...', '#d97706');
            await processPendingNewsImages({ announceNoop: false });
            pending = getNewsPendingImageNodes();
            if (pending.length > 0) {
                setNewsImageProcessMessage('仍有图片未转换成功，请改用“上传图片文件”或“导入图片链接”处理后再发布', '#dc3545');
                return false;
            }
            return true;
        }

        function switchNewsEditorMode(mode) {
            if (!newsEditorEl || !newsSourceEl) return;
            const visualBtn = document.getElementById('newsModeVisualBtn');
            const sourceBtn = document.getElementById('newsModeSourceBtn');
            if (mode === 'source') {
                newsSourceEl.value = newsEditorEl.innerHTML || '';
                newsEditorEl.style.display = 'none';
                newsSourceEl.style.display = 'block';
                newsEditorMode = 'source';
                if (visualBtn) visualBtn.classList.remove('active');
                if (sourceBtn) sourceBtn.classList.add('active');
            } else {
                newsEditorEl.innerHTML = newsSourceEl.value || '';
                newsSourceEl.style.display = 'none';
                newsEditorEl.style.display = 'block';
                newsEditorMode = 'visual';
                if (sourceBtn) sourceBtn.classList.remove('active');
                if (visualBtn) visualBtn.classList.add('active');
            }
            schedulePreview();
        }

        function applyNewsFormat(cmd, value = null) {
            if (!newsEditorEl || newsEditorMode !== 'visual') {
                switchNewsEditorMode('visual');
            }
            newsEditorEl.focus();
            restoreNewsEditorSelection();
            document.execCommand(cmd, false, value);
            saveNewsEditorSelection();
            schedulePreview();
        }

        function applyNewsFontSize(size) {
            if (!size) return;
            if (/^\d+(\.\d+)?$/.test(size)) size = `${size}px`;
            applyNewsFormat('styleWithCSS', true);
            applyNewsFormat('fontSize', '7');
            if (!newsEditorEl) return;
            const fonts = newsEditorEl.querySelectorAll('font[size="7"]');
            fonts.forEach(node => {
                node.removeAttribute('size');
                node.style.fontSize = size;
            });
            schedulePreview();
        }

        function applyNewsFontSizeCustom() {
            const input = document.getElementById('newsFontSizeCustom');
            if (!input) return;
            const val = parseFloat(input.value);
            if (!Number.isFinite(val) || val < 8 || val > 200) {
                alert('请输入 8 - 200 之间的字号');
                return;
            }
            applyNewsFontSize(`${val}px`);
        }

        function applyNewsFontColor(color) {
            if (!color) return;
            applyNewsFormat('styleWithCSS', true);
            applyNewsFormat('foreColor', color);
        }

        function setNewsColorPreset(color) {
            const colorInput = document.getElementById('newsFontColorInput');
            if (colorInput) colorInput.value = color;
            applyNewsFontColor(color);
        }

        function getNewsSelectionBlocks() {
            if (!newsEditorEl) return [];
            const sel = window.getSelection();
            if ((!sel || sel.rangeCount === 0) && newsEditorSavedRange) {
                const fakeSel = window.getSelection();
                if (fakeSel) {
                    fakeSel.removeAllRanges();
                    fakeSel.addRange(newsEditorSavedRange);
                }
            }
            if (!sel || sel.rangeCount === 0) return [];
            const range = sel.getRangeAt(0);
            if (!newsEditorEl.contains(range.commonAncestorContainer)) return [];
            const selector = 'p,div,li,h1,h2,h3,h4,h5,h6,blockquote';
            const blocks = Array.from(newsEditorEl.querySelectorAll(selector)).filter(el => {
                try {
                    return range.intersectsNode(el);
                } catch (e) {
                    return false;
                }
            });
            if (blocks.length) return blocks;

            let node = sel.anchorNode;
            if (node && node.nodeType === Node.TEXT_NODE) node = node.parentElement;
            while (node && node !== newsEditorEl) {
                if (node.matches && node.matches(selector)) return [node];
                node = node.parentElement;
            }
            return [];
        }

        function applyNewsBlockStyle(styleSetter) {
            if (!newsEditorEl) return;
            if (newsEditorMode !== 'visual') switchNewsEditorMode('visual');
            restoreNewsEditorSelection();
            const blocks = getNewsSelectionBlocks();
            if (blocks.length > 0) {
                blocks.forEach(styleSetter);
            } else {
                const allBlocks = Array.from(newsEditorEl.querySelectorAll('p,div,li,h1,h2,h3,h4,h5,h6,blockquote'));
                if (allBlocks.length > 0) allBlocks.forEach(styleSetter);
                else styleSetter(newsEditorEl);
            }
            saveNewsEditorSelection();
            schedulePreview();
        }

        function applyNewsLineHeight(value) {
            if (!value) return;
            applyNewsBlockStyle((el) => { el.style.lineHeight = value; });
        }

        function applyNewsLineHeightCustom() {
            const input = document.getElementById('newsLineHeightCustom');
            if (!input) return;
            const val = parseFloat(input.value);
            if (!Number.isFinite(val) || val < 0.8 || val > 5) {
                alert('请输入 0.8 - 5.0 之间的行间距');
                return;
            }
            applyNewsLineHeight(String(val));
        }

        function applyNewsFirstIndent(value) {
            if (typeof value === 'undefined' || value === '') return;
            applyNewsBlockStyle((el) => { el.style.textIndent = value; });
        }

        function applyNewsParagraphSpacing(type, value) {
            if (!value) return;
            applyNewsBlockStyle((el) => {
                if (type === 'before') el.style.marginTop = value;
                if (type === 'after') el.style.marginBottom = value;
            });
        }

        async function insertNewsLink() {
            const link = await showGlobalPrompt('请输入链接（http/https）', '', '插入链接', 'https://');
            if (!link) return;
            applyNewsFormat('createLink', link.trim());
        }

        function getNewsImageWidthSetting() {
            const preset = document.getElementById('newsImageSizePreset')?.value || '60%';
            const customRaw = (document.getElementById('newsImageSizeCustom')?.value || '').trim();
            const raw = customRaw || preset;
            if (!raw) return '60%';
            if (/^\d+(\.\d+)?%$/.test(raw)) return raw;
            if (/^\d+(\.\d+)?px$/i.test(raw)) return raw.toLowerCase();
            if (/^\d+(\.\d+)?$/.test(raw)) return `${raw}px`;
            return preset || '60%';
        }

        function insertHtmlToNewsEditor(html) {
            if (!newsEditorEl) return;
            if (newsEditorMode !== 'visual') {
                switchNewsEditorMode('visual');
            }
            newsEditorEl.focus();
            document.execCommand('insertHTML', false, html);
            schedulePreview();
        }

        function htmlFromRange(range) {
            const div = document.createElement('div');
            div.appendChild(range.cloneContents());
            return div.innerHTML;
        }

        function fragmentFromHtml(html) {
            const tpl = document.createElement('template');
            tpl.innerHTML = html || '';
            return tpl.content.cloneNode(true);
        }

        function getCurrentNewsBlock() {
            if (!newsEditorEl) return null;
            let node = null;
            const sel = window.getSelection();
            if (sel && sel.rangeCount > 0) {
                const range = sel.getRangeAt(0);
                node = range.commonAncestorContainer;
            } else if (newsEditorSavedRange) {
                node = newsEditorSavedRange.commonAncestorContainer;
            }
            if (!node) node = newsEditorEl;
            if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
            if (!node || node === newsEditorEl) return null;
            if (!newsEditorEl.contains(node)) return null;
            return node.closest ? node.closest('p,div,li,h1,h2,h3,h4,h5,h6,blockquote') : null;
        }

        function getAiPolishTarget() {
            if (!newsEditorEl || !newsSourceEl) return null;

            if (newsEditorMode === 'source') {
                const value = newsSourceEl.value || '';
                const start = Number.isFinite(newsSourceEl.selectionStart) ? newsSourceEl.selectionStart : 0;
                const end = Number.isFinite(newsSourceEl.selectionEnd) ? newsSourceEl.selectionEnd : start;
                if (end > start) {
                    return {
                        content: value.slice(start, end),
                        apply: (newHtml) => {
                            newsSourceEl.value = value.slice(0, start) + (newHtml || '') + value.slice(end);
                            switchNewsEditorMode('source');
                        }
                    };
                }
                return {
                    content: value,
                    apply: (newHtml) => {
                        newsSourceEl.value = newHtml || '';
                        switchNewsEditorMode('source');
                    }
                };
            }

            restoreNewsEditorSelection();
            const sel = window.getSelection();
            if (sel && sel.rangeCount > 0) {
                const range = sel.getRangeAt(0);
                if (newsEditorEl.contains(range.commonAncestorContainer) && !range.collapsed) {
                    const selectedText = (range.toString() || '').trim();
                    const selectedHtml = htmlFromRange(range).trim();
                    if (selectedText || selectedHtml) {
                        const savedRange = range.cloneRange();
                        return {
                            content: selectedHtml || selectedText,
                            apply: (newHtml) => {
                                const liveSel = window.getSelection();
                                if (!liveSel) return;
                                liveSel.removeAllRanges();
                                liveSel.addRange(savedRange);
                                const liveRange = liveSel.getRangeAt(0);
                                liveRange.deleteContents();
                                liveRange.insertNode(fragmentFromHtml(newHtml || ''));
                                liveSel.removeAllRanges();
                            }
                        };
                    }
                }
            }

            const block = getCurrentNewsBlock();
            if (block) {
                return {
                    content: block.innerHTML || block.textContent || '',
                    apply: (newHtml) => { block.innerHTML = newHtml || ''; }
                };
            }

            return {
                content: newsEditorEl.innerHTML || '',
                apply: (newHtml) => { newsEditorEl.innerHTML = newHtml || ''; }
            };
        }

        function triggerNewsImageUpload() {
            const input = document.getElementById('newsImageFileInput');
            if (input) input.click();
        }

        async function uploadNewsImageFile(inputEl) {
            const file = inputEl?.files?.[0];
            if (!file) return;
            setNewsImageProcessMessage('正在上传图片...', '#666');
            try {
                const data = await uploadNewsBlobImage(file, file.name || '');
                const width = getNewsImageWidthSetting();
                insertHtmlToNewsEditor(
                    `<p style="text-align:center;"><img src="${data.url}" alt="news-image" data-news-localized="1" style="width:${width};max-width:100%;height:auto;display:block;margin:0 auto;"></p>`
                );
                setNewsImageProcessMessage('图片上传并插入成功', '#28a745');
            } catch (e) {
                setNewsImageProcessMessage(e?.message || '图片上传失败', '#dc3545');
            } finally {
                if (inputEl) inputEl.value = '';
            }
        }

        async function insertNewsImageFromUrl() {
            const input = document.getElementById('newsInsertImageUrl');
            const rawUrl = (input?.value || '').trim();
            if (!rawUrl) {
                alert('请先粘贴图片链接');
                return;
            }
            setNewsImageProcessMessage('正在下载并导入图片...', '#666');
            try {
                const data = await importNewsRemoteImageUrl(rawUrl);
                const width = getNewsImageWidthSetting();
                insertHtmlToNewsEditor(
                    `<p style="text-align:center;"><img src="${data.url}" alt="news-image" data-news-localized="1" style="width:${width};max-width:100%;height:auto;display:block;margin:0 auto;"></p>`
                );
                if (input) input.value = '';
                setNewsImageProcessMessage('图片已导入', '#28a745');
            } catch (e) {
                setNewsImageProcessMessage(e?.message || '图片导入失败', '#dc3545');
            }
        }

        function getSelectedNewsImageElement() {
            if (!newsEditorEl) return null;
            const sel = window.getSelection();
            if (!sel || sel.rangeCount === 0) return null;
            let node = sel.anchorNode;
            if (!node) return null;
            if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
            if (!node) return null;
            if (node.tagName === 'IMG') return node;
            const inNode = node.querySelector ? node.querySelector('img') : null;
            if (inNode) return inNode;
            const closest = node.closest ? node.closest('img') : null;
            if (closest) return closest;
            return null;
        }

        function applySizeToSelectedNewsImage() {
            if (!newsEditorEl || newsEditorMode !== 'visual') switchNewsEditorMode('visual');
            restoreNewsEditorSelection();
            const img = getSelectedNewsImageElement();
            const width = getNewsImageWidthSetting();
            if (!img) {
                alert('请先把光标放到目标图片上再设置大小');
                return;
            }
            img.style.width = width;
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            img.style.display = 'block';
            img.style.margin = '0 auto';
            const parentP = img.closest('p');
            if (parentP) parentP.style.textAlign = 'center';
            schedulePreview();
        }

        const newsCreateForm = document.getElementById('newsCreateForm');
        if (newsCreateForm) {
            newsCreateForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const msg = document.getElementById('newsCreateMsg');
                const linkEl = document.getElementById('newsCreateLink');
                if (msg) msg.textContent = '';
                if (linkEl) linkEl.textContent = '';

                const payload = {
                    title: document.getElementById('newsTitle').value.trim(),
                    date: document.getElementById('newsDate').value,
                    category: document.getElementById('newsCategory').value,
                    division: document.getElementById('newsDivision').value.trim(),
                    image_url: document.getElementById('newsImage').value.trim(),
                    summary: document.getElementById('newsSummary').value.trim(),
                    content: getNewsEditorHtml(),
                    content_is_html: true
                };

                if (!payload.content) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '请填写正文内容';
                    }
                    return;
                }

                if (!await ensureNewsImagesReadyForSubmit()) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '请先等待正文图片转换完成';
                    }
                    return;
                }

                try {
                    const endpoint = editingNewsLink ? '/api/news/update' : '/api/news/create';
                    if (editingNewsLink) payload.link = editingNewsLink;
                    const res = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (data.success) {
                        if (msg) {
                            msg.style.color = '#28a745';
                            msg.textContent = editingNewsLink ? '✓ 修改成功' : '✓ 生成成功';
                        }
                        if (linkEl && data.link) {
                            const stamped = `${data.link}${data.link.includes('?') ? '&' : '?'}t=${Date.now()}`;
                            linkEl.innerHTML = `页面：<a href="${stamped}" target="_blank">${stamped}</a>`;
                        }
                        newsCreateForm.reset();
                        setNewsEditorHtml('');
                        switchNewsEditorMode('visual');
                        aiTypesetPending = false;
                        aiTypesetBeforeHtml = '';
                        updateAiTypesetActionVisibility();
                        cancelNewsEdit();
                        updateNewsPreview();
                        loadFeaturedNews();
                        loadNewsList();
                    } else {
                        if (msg) {
                            msg.style.color = '#dc3545';
                            msg.textContent = data.message || '生成失败';
                        }
                    }
                } catch (e) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '网络错误';
                    }
                }
            });
        }

        async function loadNewsList() {
            const listEl = document.getElementById('newsList');
            if (!listEl) return;
            listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#888;">加载中...</div>';
            try {
                const res = await fetch('/api/news/all');
                const data = await res.json();
                const items = data.items || [];
                if (items.length === 0) {
                    listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#888;">暂无资讯</div>';
                    return;
                }
                const categoryOptions = (selected) => `
                    <option value="enterprise" ${selected === 'enterprise' ? 'selected' : ''}>企业新闻</option>
                    <option value="industry" ${selected === 'industry' ? 'selected' : ''}>行业动态</option>
                    <option value="science" ${selected === 'science' ? 'selected' : ''}>科普知识</option>
                `;
                listEl.innerHTML = items.map((item, index) => `
                    <div class="file-item" style="align-items: flex-start; gap: 12px;">
                        <div style="display:flex; flex-direction:column; align-items:center; gap:6px; min-width:52px; padding-top:2px;">
                            <span style="font-size:12px; color:#64748b;">排序</span>
                            <button class="btn-sm" style="width:42px; padding:6px 0;" onclick="reorderNewsItem('${item.link}', 'up')" ${index === 0 ? 'disabled' : ''}>↑</button>
                            <button class="btn-sm" style="width:42px; padding:6px 0;" onclick="reorderNewsItem('${item.link}', 'down')" ${index === items.length - 1 ? 'disabled' : ''}>↓</button>
                            <span style="font-size:12px; color:#94a3b8;">#${item.order || (index + 1)}</span>
                        </div>
                        <div class="file-info" style="flex:1; min-width:0;">
                            <img src="${item.image || ''}" alt="news" style="width: 72px; height: 46px; object-fit: cover; border-radius: 6px;">
                            <div>
                                <div style="font-weight: 600;">${escapeHtml(item.title || '')}</div>
                                <div class="file-meta">${item.date || ''}</div>
                                <div class="file-meta" style="margin-top: 4px;">摘要：${escapeHtml(item.desc || '（无）')}</div>
                                <div class="file-meta">归属事业部：${escapeHtml(item.division || '（未设置）')}</div>
                                <div class="file-meta">${escapeHtml(item.link || '')}</div>
                                <div style="margin-top: 8px; display:flex; align-items:center; gap:8px;">
                                    <span style="font-size:12px; color:#666;">分类</span>
                                    <select class="form-control" style="width: 130px; padding: 6px 8px;"
                                        onchange="quickUpdateNewsCategory('${item.link}', this.value)">
                                        ${categoryOptions(item.category || 'enterprise')}
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="btn-sm" onclick="editNewsItem('${item.link}')">编辑</button>
                            <button class="btn-sm btn-danger" onclick="deleteNewsItem('${item.link}')">删除</button>
                            <button class="btn-sm" onclick="toggleNewsVisibility('${item.link}', ${item.hidden ? 'false' : 'true'})">
                                ${item.hidden ? '显示' : '隐藏'}
                            </button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#dc3545;">加载失败</div>';
            }
        }

        async function reorderNewsItem(link, direction) {
            if (!link) return;
            try {
                const res = await fetch('/api/news/reorder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ link, direction })
                });
                const data = await res.json();
                if (!data.success) {
                    alert(data.message || '排序失败');
                }
            } catch (e) {
                alert('网络错误');
            }
            loadNewsList();
        }

        async function quickUpdateNewsCategory(link, category) {
            try {
                const res = await fetch('/api/news/category', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ link, category })
                });
                const data = await res.json();
                if (!data.success) {
                    alert(data.message || '分类更新失败');
                    loadNewsList();
                    return;
                }
                loadFeaturedNews();
            } catch (e) {
                alert('网络错误');
                loadNewsList();
            }
        }

        async function editNewsItem(link) {
            if (!link) return;
            try {
                const resAll = await fetch('/api/news/all');
                const dataAll = await resAll.json();
                const item = (dataAll.items || []).find(n => n.link === link);
                if (!item) return;
                const resDetail = await fetch(`/api/news/detail?link=${encodeURIComponent(link)}`);
                const dataDetail = await resDetail.json();
                const detail = dataDetail.detail || {};
                editingNewsLink = link;
                document.getElementById('newsTitle').value = item.title || '';
                document.getElementById('newsDate').value = item.date || '';
                document.getElementById('newsCategory').value = item.category || 'enterprise';
                document.getElementById('newsDivision').value = item.division || '';
                document.getElementById('newsImage').value = detail.image_url || item.image || '';
                document.getElementById('newsSummary').value = item.desc || '';
                setNewsEditorHtml(detail.content_html || detail.content_text || '');
                switchNewsEditorMode('visual');
                aiTypesetPending = false;
                aiTypesetBeforeHtml = '';
                updateAiTypesetActionVisibility();
                document.getElementById('newsSubmitBtn').textContent = '保存修改';
                document.getElementById('newsCancelEdit').style.display = 'inline-flex';
                window.scrollTo({ top: 0, behavior: 'smooth' });
                updateNewsPreview();
            } catch (e) {
                console.error(e);
            }
        }

        function cancelNewsEdit() {
            editingNewsLink = '';
            const btn = document.getElementById('newsSubmitBtn');
            const cancelBtn = document.getElementById('newsCancelEdit');
            if (btn) btn.textContent = '生成资讯';
            if (cancelBtn) cancelBtn.style.display = 'none';
            aiTypesetPending = false;
            aiTypesetBeforeHtml = '';
            updateAiTypesetActionVisibility();
        }

        async function deleteNewsItem(link) {
            if (!await showGlobalConfirm('确定删除该资讯吗？此操作无法撤销。')) return;
            try {
                const res = await fetch('/api/news/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ link })
                });
                const data = await res.json();
                if (data.success) {
                    loadNewsList();
                    loadFeaturedNews();
                } else {
                    alert(data.message || '删除失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        async function toggleNewsVisibility(link, hidden) {
            try {
                const res = await fetch('/api/news/visibility', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ link, hidden })
                });
                const data = await res.json();
                if (data.success) {
                    loadNewsList();
                    loadFeaturedNews();
                } else {
                    alert(data.message || '更新失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        let previewTimer = null;
        function schedulePreview() {
            if (previewTimer) clearTimeout(previewTimer);
            previewTimer = setTimeout(updateNewsPreview, 200);
        }

        async function updateNewsPreview() {
            const title = document.getElementById('newsTitle')?.value.trim() || '标题预览';
            const date = document.getElementById('newsDate')?.value || '';
            const image = document.getElementById('newsImage')?.value.trim();
            const content = getNewsEditorHtml();
            const frameEl = document.getElementById('newsPreviewFrame');
            if (!frameEl) return;
            bindNewsPreviewBridge();
            frameEl.style.height = '640px';

            try {
                const res = await fetch('/api/news/preview-page', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title,
                        date,
                        image_url: image,
                        content,
                        content_is_html: true
                    })
                });
                const data = await res.json();
                if (data.success) {
                    frameEl.srcdoc = data.page_html || '';
                }
            } catch (e) {
                frameEl.srcdoc = '<!doctype html><html><body style="font-family:sans-serif;padding:24px;color:#666;">预览加载失败</body></html>';
            }
        }

        function bindNewsPreviewEvents() {
            ['newsTitle', 'newsDate', 'newsImage'].forEach(id => {
                const el = document.getElementById(id);
                if (!el) return;
                el.addEventListener('input', schedulePreview);
                el.addEventListener('change', schedulePreview);
            });
            if (newsEditorEl) {
                newsEditorEl.addEventListener('input', schedulePreview);
                newsEditorEl.addEventListener('keyup', schedulePreview);
                newsEditorEl.addEventListener('keyup', saveNewsEditorSelection);
                newsEditorEl.addEventListener('mouseup', saveNewsEditorSelection);
                newsEditorEl.addEventListener('focus', saveNewsEditorSelection);
                newsEditorEl.addEventListener('blur', saveNewsEditorSelection);
                newsEditorEl.addEventListener('paste', (event) => {
                    const clipboard = event.clipboardData;
                    const htmlSnippet = String(clipboard?.getData('text/html') || '');
                    const imageFiles = clipboard
                        ? Array.from(clipboard.items || [])
                            .filter((item) => item.kind === 'file' && String(item.type || '').startsWith('image/'))
                            .map((item) => item.getAsFile())
                            .filter(Boolean)
                        : [];
                    const hasRichText = !!(clipboard && (clipboard.getData('text/html') || clipboard.getData('text/plain')));
                    const likelyContainsImages = imageFiles.length > 0
                        || /<img[\s>]/i.test(htmlSnippet)
                        || /data-ace-gallery-json|data-lark-image-uri|feishu\.cn|larksuite\.com|larkoffice\.com/i.test(htmlSnippet);

                    if (imageFiles.length > 0 && !hasRichText) {
                        event.preventDefault();
                        insertNewsClipboardImages(imageFiles);
                        return;
                    }

                    if (!likelyContainsImages) {
                        return;
                    }

                    setNewsImageProcessMessage('正在识别粘贴图片...', '#666');
                    queueNewsImageProcessing({ announceNoop: true });
                });
            }
            if (newsSourceEl) {
                newsSourceEl.addEventListener('input', schedulePreview);
                newsSourceEl.addEventListener('change', schedulePreview);
            }
            const feishuImportInput = document.getElementById('newsFeishuImportUrl');
            if (feishuImportInput) {
                feishuImportInput.addEventListener('keydown', (event) => {
                    if (event.key !== 'Enter') return;
                    event.preventDefault();
                    importNewsFromFeishuUrl();
                });
            }
        }

        async function aiPolishNews() {
            const msg = document.getElementById('newsCreateMsg');
            const fullBeforeHtml = getNewsEditorHtml();
            const target = getAiPolishTarget();
            const content = (target?.content || '').trim();
            if (!content || !target) {
                alert('请输入正文内容');
                return;
            }
            if (msg) {
                msg.style.color = '#666';
                msg.textContent = '正在自动排版当前选中内容/段落...';
            }
            try {
                aiTypesetBeforeHtml = fullBeforeHtml;
                const res = await fetch('/api/news/ai-polish', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: document.getElementById('newsTitle')?.value.trim(),
                        summary: document.getElementById('newsSummary')?.value.trim(),
                        content,
                        content_is_html: true
                    })
                });
                const data = await res.json();
                if (!data.success) {
                    const blocked = String(data.message || '').includes('改动了正文字符');
                    if (blocked) {
                        setNewsEditorHtml(fullBeforeHtml);
                        switchNewsEditorMode(newsEditorMode === 'source' ? 'source' : 'visual');
                        const beforeExcerpt = String(data.before_excerpt || '').trim();
                        const afterExcerpt = String(data.after_excerpt || '').trim();
                        const diffIndex = Number.isFinite(data.diff_index) ? data.diff_index : '';
                        if (msg) {
                            msg.style.color = '#d97706';
                            const hint = (beforeExcerpt || afterExcerpt)
                                ? ` 差异片段：原文「${beforeExcerpt}」→ AI「${afterExcerpt}」`
                                : '';
                            msg.textContent = `AI 排版结果触发拦截，正文已保持不变。请缩小选区后重试。${hint}`;
                        }
                        if (beforeExcerpt || afterExcerpt) {
                            alert(
                                `AI 触发拦截（位置索引约 ${diffIndex}）\n原文片段：${beforeExcerpt}\nAI片段：${afterExcerpt}\n\n建议：缩小到单段再排版，或分段逐次排版。`
                            );
                        }
                        return;
                    }
                    throw new Error(data.message || 'AI 排版失败');
                }
                const polished = (data.content || '').trim();
                if (!polished) {
                    throw new Error('AI 返回内容为空，已保留原文');
                }
                target.apply(polished);
                const afterHtml = getNewsEditorHtml();
                if (!afterHtml.trim()) {
                    setNewsEditorHtml(fullBeforeHtml);
                    throw new Error('排版结果异常，已自动恢复原内容');
                }
                switchNewsEditorMode(newsEditorMode === 'source' ? 'source' : 'visual');
                updateNewsPreview();
                aiTypesetPending = true;
                updateAiTypesetActionVisibility();
                if (msg) {
                    if (data.warning) {
                        msg.style.color = '#d97706';
                        msg.textContent = `${data.warning}`;
                    } else {
                        msg.style.color = '#28a745';
                        msg.textContent = '✓ AI 排版已替换当前选区/段落，可点击“撤销替换”恢复';
                    }
                }
            } catch (e) {
                // 任意失败都恢复排版前内容，避免“正文消失”
                setNewsEditorHtml(fullBeforeHtml);
                switchNewsEditorMode(newsEditorMode === 'source' ? 'source' : 'visual');
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || 'AI 排版失败';
                }
            }
        }

        // --- Jobs Editor ---
        let jobEditorMode = 'visual';
        let jobEditorSavedRange = null;
        const jobEditorEl = document.getElementById('jobContentEditor');
        const jobSourceEl = document.getElementById('jobContent');

        function saveJobEditorSelection() {
            if (!jobEditorEl || jobEditorMode !== 'visual') return;
            const sel = window.getSelection();
            if (!sel || sel.rangeCount === 0) return;
            const range = sel.getRangeAt(0);
            if (!jobEditorEl.contains(range.commonAncestorContainer)) return;
            jobEditorSavedRange = range.cloneRange();
        }

        function restoreJobEditorSelection() {
            if (!jobEditorEl || jobEditorMode !== 'visual' || !jobEditorSavedRange) return;
            const sel = window.getSelection();
            if (!sel) return;
            sel.removeAllRanges();
            sel.addRange(jobEditorSavedRange);
        }

        function getJobEditorHtml() {
            if (!jobEditorEl || !jobSourceEl) return '';
            if (jobEditorMode === 'source') {
                return (jobSourceEl.value || '').trim();
            }
            jobSourceEl.value = (jobEditorEl.innerHTML || '').trim();
            return jobSourceEl.value;
        }

        function setJobEditorHtml(html) {
            if (!jobEditorEl || !jobSourceEl) return;
            const value = html || '';
            jobEditorEl.innerHTML = value;
            jobSourceEl.value = value;
        }

        function switchJobEditorMode(mode) {
            if (!jobEditorEl || !jobSourceEl) return;
            const visualBtn = document.getElementById('jobModeVisualBtn');
            const sourceBtn = document.getElementById('jobModeSourceBtn');
            if (mode === 'source') {
                jobSourceEl.value = jobEditorEl.innerHTML || '';
                jobEditorEl.style.display = 'none';
                jobSourceEl.style.display = 'block';
                jobEditorMode = 'source';
                if (visualBtn) visualBtn.classList.remove('active');
                if (sourceBtn) sourceBtn.classList.add('active');
            } else {
                jobEditorEl.innerHTML = jobSourceEl.value || '';
                jobSourceEl.style.display = 'none';
                jobEditorEl.style.display = 'block';
                jobEditorMode = 'visual';
                if (sourceBtn) sourceBtn.classList.remove('active');
                if (visualBtn) visualBtn.classList.add('active');
            }
        }

        function applyJobFormat(cmd, value = null) {
            if (!jobEditorEl || jobEditorMode !== 'visual') {
                switchJobEditorMode('visual');
            }
            jobEditorEl.focus();
            restoreJobEditorSelection();
            document.execCommand(cmd, false, value);
            saveJobEditorSelection();
        }

        function applyJobFontSize(size) {
            if (!size) return;
            if (/^\d+(\.\d+)?$/.test(size)) size = `${size}px`;
            applyJobFormat('styleWithCSS', true);
            applyJobFormat('fontSize', '7');
            if (!jobEditorEl) return;
            const fonts = jobEditorEl.querySelectorAll('font[size="7"]');
            fonts.forEach(node => {
                node.removeAttribute('size');
                node.style.fontSize = size;
            });
        }

        function applyJobFontSizeCustom() {
            const input = document.getElementById('jobFontSizeCustom');
            if (!input) return;
            const val = parseFloat(input.value);
            if (!Number.isFinite(val) || val < 8 || val > 200) {
                alert('请输入 8 - 200 之间的字号');
                return;
            }
            applyJobFontSize(`${val}px`);
        }

        function applyJobFontColor(color) {
            if (!color) return;
            applyJobFormat('styleWithCSS', true);
            applyJobFormat('foreColor', color);
        }

        function setJobColorPreset(color) {
            const colorInput = document.getElementById('jobFontColorInput');
            if (colorInput) colorInput.value = color;
            applyJobFontColor(color);
        }

        function getJobSelectionBlocks() {
            if (!jobEditorEl) return [];
            const sel = window.getSelection();
            if ((!sel || sel.rangeCount === 0) && jobEditorSavedRange) {
                const fakeSel = window.getSelection();
                if (fakeSel) {
                    fakeSel.removeAllRanges();
                    fakeSel.addRange(jobEditorSavedRange);
                }
            }
            if (!sel || sel.rangeCount === 0) return [];
            const range = sel.getRangeAt(0);
            if (!jobEditorEl.contains(range.commonAncestorContainer)) return [];
            const selector = 'p,div,li,h1,h2,h3,h4,h5,h6,blockquote';
            const blocks = Array.from(jobEditorEl.querySelectorAll(selector)).filter(el => {
                try {
                    return range.intersectsNode(el);
                } catch (e) {
                    return false;
                }
            });
            if (blocks.length) return blocks;

            let node = sel.anchorNode;
            if (node && node.nodeType === Node.TEXT_NODE) node = node.parentElement;
            while (node && node !== jobEditorEl) {
                if (node.matches && node.matches(selector)) return [node];
                node = node.parentElement;
            }
            return [];
        }

        function applyJobBlockStyle(styleSetter) {
            if (!jobEditorEl) return;
            if (jobEditorMode !== 'visual') switchJobEditorMode('visual');
            restoreJobEditorSelection();
            const blocks = getJobSelectionBlocks();
            if (blocks.length > 0) {
                blocks.forEach(styleSetter);
            } else {
                const allBlocks = Array.from(jobEditorEl.querySelectorAll('p,div,li,h1,h2,h3,h4,h5,h6,blockquote'));
                if (allBlocks.length > 0) allBlocks.forEach(styleSetter);
                else styleSetter(jobEditorEl);
            }
            saveJobEditorSelection();
        }

        function applyJobLineHeight(value) {
            if (!value) return;
            applyJobBlockStyle((el) => { el.style.lineHeight = value; });
        }

        function applyJobLineHeightCustom() {
            const input = document.getElementById('jobLineHeightCustom');
            if (!input) return;
            const val = parseFloat(input.value);
            if (!Number.isFinite(val) || val < 0.8 || val > 5) {
                alert('请输入 0.8 - 5.0 之间的行间距');
                return;
            }
            applyJobLineHeight(String(val));
        }

        function applyJobFirstIndent(value) {
            if (typeof value === 'undefined' || value === '') return;
            applyJobBlockStyle((el) => { el.style.textIndent = value; });
        }

        function applyJobParagraphSpacing(type, value) {
            if (!value) return;
            applyJobBlockStyle((el) => {
                if (type === 'before') el.style.marginTop = value;
                if (type === 'after') el.style.marginBottom = value;
            });
        }

        async function insertJobLink() {
            const link = await showGlobalPrompt('请输入链接（http/https）', '', '插入链接', 'https://');
            if (!link) return;
            applyJobFormat('createLink', link.trim());
        }

        function getJobImageWidthSetting() {
            const preset = document.getElementById('jobImageSizePreset')?.value || '60%';
            const customRaw = (document.getElementById('jobImageSizeCustom')?.value || '').trim();
            const raw = customRaw || preset;
            if (!raw) return '60%';
            if (/^\d+(\.\d+)?%$/.test(raw)) return raw;
            if (/^\d+(\.\d+)?px$/i.test(raw)) return raw.toLowerCase();
            if (/^\d+(\.\d+)?$/.test(raw)) return `${raw}px`;
            return preset || '60%';
        }

        function insertHtmlToJobEditor(html) {
            if (!jobEditorEl) return;
            if (jobEditorMode !== 'visual') {
                switchJobEditorMode('visual');
            }
            jobEditorEl.focus();
            document.execCommand('insertHTML', false, html);
        }

        function triggerJobImageUpload() {
            const input = document.getElementById('jobImageFileInput');
            if (input) input.click();
        }

        async function uploadJobImageFile(inputEl) {
            const msg = document.getElementById('jobMsg');
            const file = inputEl?.files?.[0];
            if (!file) return;
            if (msg) {
                msg.style.color = '#666';
                msg.textContent = '正在上传图片...';
            }
            try {
                const formData = new FormData();
                formData.append('file', file);
                const res = await fetch('/api/news/image/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (!data.success) throw new Error(data.message || '上传失败');
                const width = getJobImageWidthSetting();
                insertHtmlToJobEditor(
                    `<p style="text-align:center;"><img src="${data.url}" alt="job-image" style="width:${width};max-width:100%;height:auto;display:block;margin:0 auto;"></p>`
                );
                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = '✓ 图片上传并插入成功';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || '图片上传失败';
                }
            } finally {
                if (inputEl) inputEl.value = '';
            }
        }

        async function insertJobImageFromUrl() {
            const input = document.getElementById('jobInsertImageUrl');
            const msg = document.getElementById('jobMsg');
            const rawUrl = (input?.value || '').trim();
            if (!rawUrl) {
                alert('请先粘贴图片链接');
                return;
            }
            if (msg) {
                msg.style.color = '#666';
                msg.textContent = '正在下载并导入图片...';
            }
            try {
                const res = await fetch('/api/news/image/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: rawUrl })
                });
                const data = await res.json();
                if (!data.success) throw new Error(data.message || '导入失败');
                const width = getJobImageWidthSetting();
                insertHtmlToJobEditor(
                    `<p style="text-align:center;"><img src="${data.url}" alt="job-image" style="width:${width};max-width:100%;height:auto;display:block;margin:0 auto;"></p>`
                );
                if (input) input.value = '';
                if (msg) {
                    msg.style.color = '#28a745';
                    msg.textContent = '✓ 图片已导入';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = e?.message || '图片导入失败';
                }
            }
        }

        function getSelectedJobImageElement() {
            if (!jobEditorEl) return null;
            const sel = window.getSelection();
            if (!sel || sel.rangeCount === 0) return null;
            let node = sel.anchorNode;
            if (!node) return null;
            if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
            if (!node) return null;
            if (node.tagName === 'IMG') return node;
            const inNode = node.querySelector ? node.querySelector('img') : null;
            if (inNode) return inNode;
            const closest = node.closest ? node.closest('img') : null;
            if (closest) return closest;
            return null;
        }

        function applySizeToSelectedJobImage() {
            if (!jobEditorEl || jobEditorMode !== 'visual') switchJobEditorMode('visual');
            const img = getSelectedJobImageElement();
            if (!img) {
                alert('请先在编辑区点击要设置宽度的图片');
                return;
            }
            const width = getJobImageWidthSetting();
            img.style.width = width;
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            img.style.display = 'block';
            img.style.margin = '0 auto';
        }

        function bindJobEditorEvents() {
            if (!jobEditorEl) return;
            jobEditorEl.addEventListener('keyup', saveJobEditorSelection);
            jobEditorEl.addEventListener('mouseup', saveJobEditorSelection);
            jobEditorEl.addEventListener('focus', saveJobEditorSelection);
            jobEditorEl.addEventListener('blur', saveJobEditorSelection);
        }

        function cleanJobText(value) {
            if (value === null || value === undefined) return '';
            return String(value)
                .replace(/\u00a0/g, ' ')
                .replace(/&nbsp;?/gi, ' ')
                .replace(/\s+/g, ' ')
                .trim();
        }

        function normalizeJobDateForInput(value) {
            const text = cleanJobText(value);
            if (!text) return '';
            const match = text.match(/(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})/);
            if (!match) return '';
            const y = match[1];
            const m = String(parseInt(match[2], 10)).padStart(2, '0');
            const d = String(parseInt(match[3], 10)).padStart(2, '0');
            return `${y}-${m}-${d}`;
        }

        // --- Jobs Admin ---
        let editingJobId = '';
        let jobsCache = [];
        const jobForm = document.getElementById('jobForm');
        if (jobForm) {
            jobForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const msg = document.getElementById('jobMsg');
                if (msg) msg.textContent = '';

                const payload = {
                    id: editingJobId,
                    title: document.getElementById('jobTitle')?.value.trim(),
                    department: document.getElementById('jobDepartment')?.value.trim(),
                    location: document.getElementById('jobLocation')?.value.trim(),
                    date: document.getElementById('jobDate')?.value,
                    content_html: getJobEditorHtml(),
                    visible: document.getElementById('jobVisible')?.checked
                };

                try {
                    const res = await fetch('/api/jobs', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (data.success) {
                        if (msg) {
                            msg.style.color = '#28a745';
                            msg.textContent = '✓ 保存成功';
                        }
                        cancelJobEdit();
                        jobForm.reset();
                        setJobEditorHtml('');
                        switchJobEditorMode('visual');
                        loadJobsAdmin();
                    } else if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = data.message || '保存失败';
                    }
                } catch (e) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '网络错误';
                    }
                }
            });
        }

        async function loadJobsAdmin() {
            const listEl = document.getElementById('jobsListAdmin');
            if (!listEl) return;
            listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#888;">加载中...</div>';
            try {
                const res = await fetch('/api/jobs');
                const data = await res.json();
                jobsCache = data.items || [];
                if (jobsCache.length === 0) {
                    listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#888;">暂无招聘信息</div>';
                    return;
                }
                listEl.innerHTML = jobsCache.map(item => `
                    <div class="file-item" style="align-items: flex-start;">
                        <div class="file-info">
                            <div>
                                <div style="font-weight: 600;">${escapeHtml(cleanJobText(item.title || ''))}</div>
                                <div class="file-meta">${escapeHtml(cleanJobText(item.department || ''))} · ${escapeHtml(cleanJobText(item.location || ''))} · ${escapeHtml(cleanJobText(item.date || ''))}</div>
                                <div class="file-meta">ID: ${escapeHtml(item.id || '')}</div>
                            </div>
                        </div>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="btn-sm" onclick="editJobItem('${item.id}')">编辑</button>
                            <button class="btn-sm" onclick="toggleJobItem('${item.id}')">${item.visible ? '隐藏' : '显示'}</button>
                            <button class="btn-sm btn-danger" onclick="deleteJobItem('${item.id}')">删除</button>
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                listEl.innerHTML = '<div style="text-align:center; padding: 20px; color:#dc3545;">加载失败</div>';
            }
        }

        function editJobItem(jobId) {
            const item = jobsCache.find(j => j.id === jobId);
            if (!item) return;
            editingJobId = jobId;
            document.getElementById('jobTitle').value = cleanJobText(item.title || '');
            document.getElementById('jobDepartment').value = cleanJobText(item.department || '');
            document.getElementById('jobLocation').value = cleanJobText(item.location || '');
            document.getElementById('jobDate').value = normalizeJobDateForInput(item.date || '');
            setJobEditorHtml(item.content_html || '');
            switchJobEditorMode('visual');
            document.getElementById('jobVisible').checked = !!item.visible;
            document.getElementById('jobCancelEdit').style.display = 'inline-flex';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function cancelJobEdit() {
            editingJobId = '';
            const cancelBtn = document.getElementById('jobCancelEdit');
            if (cancelBtn) cancelBtn.style.display = 'none';
        }

        async function deleteJobItem(jobId) {
            if (!await showGlobalConfirm('确定删除该职位吗？此操作无法撤销。')) return;
            try {
                const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    loadJobsAdmin();
                } else {
                    alert(data.message || '删除失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        async function toggleJobItem(jobId) {
            try {
                const res = await fetch(`/api/jobs/${jobId}/toggle`, { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    loadJobsAdmin();
                } else {
                    alert(data.message || '更新失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        bindNewsPreviewEvents();
        bindJobEditorEvents();
        // --- Messages Logic ---
        let messageDetailMap = {};

        function closeMessageDetailModal() {
            const modal = document.getElementById('messageDetailModal');
            if (!modal) return;
            modal.hidden = true;
        }

        function formatMessageDetailValue(value) {
            const raw = String(value ?? '').trim();
            if (!raw) return '-';
            return escapeHtml(raw).replace(/\n/g, '<br>');
        }

        function buildMessageDetailItem(label, valueHtml) {
            return `
                <div class="msg-detail-label">${escapeHtml(label)}</div>
                <div class="msg-detail-value">${valueHtml}</div>
            `;
        }

        function viewMessageDetail(id) {
            const message = messageDetailMap[String(id || '')];
            if (!message) {
                alert('未找到该留言详情，请刷新后重试。');
                return;
            }

            const isJob = message.message_type === 'job_application';
            const timestamp = String(message.timestamp || '');
            const statusText = message.is_read ? '已读' : '未读';
            const title = String(message.title || message.txtTitle || '');
            const content = String(message.content || message.txtContent || '');
            const items = [];

            items.push(buildMessageDetailItem('提交时间', formatMessageDetailValue(timestamp)));
            items.push(buildMessageDetailItem('状态', formatMessageDetailValue(statusText)));
            items.push(buildMessageDetailItem('姓名', formatMessageDetailValue(message.name)));
            items.push(buildMessageDetailItem('联系电话', formatMessageDetailValue(message.phone)));
            items.push(buildMessageDetailItem('邮箱', formatMessageDetailValue(message.email)));
            items.push(buildMessageDetailItem('来源 IP', formatMessageDetailValue(message.ip)));
            items.push(buildMessageDetailItem('类型', formatMessageDetailValue(isJob ? '应聘信息' : '留言信息')));

            if (title) {
                items.push(buildMessageDetailItem('标题', formatMessageDetailValue(title)));
            }
            if (content) {
                items.push(buildMessageDetailItem('内容', formatMessageDetailValue(content)));
            }

            if (isJob) {
                items.push(buildMessageDetailItem('应聘岗位', formatMessageDetailValue(message.job_title || message.job_id)));
                items.push(buildMessageDetailItem('年龄', formatMessageDetailValue(message.age)));
                items.push(buildMessageDetailItem('民族', formatMessageDetailValue(message.ethnicity)));
                items.push(buildMessageDetailItem('性别', formatMessageDetailValue(message.gender)));
                items.push(buildMessageDetailItem('住址', formatMessageDetailValue(message.address)));
                items.push(buildMessageDetailItem('学历', formatMessageDetailValue(message.education)));
                items.push(buildMessageDetailItem('院校', formatMessageDetailValue(message.school)));
                items.push(buildMessageDetailItem('工作经历', formatMessageDetailValue(message.work_experience)));
                items.push(buildMessageDetailItem('项目经历', formatMessageDetailValue(message.project_experience)));
                items.push(buildMessageDetailItem('自我陈述', formatMessageDetailValue(message.self_statement)));
                if (message.resume_url) {
                    const resumeLink = `<a href="${escapeHtml(String(message.resume_url))}" target="_blank" rel="noopener">点击下载简历</a>`;
                    items.push(buildMessageDetailItem('简历文件', resumeLink));
                }
            }

            const contentEl = document.getElementById('messageDetailContent');
            const modal = document.getElementById('messageDetailModal');
            if (!contentEl || !modal) return;
            contentEl.innerHTML = items.join('');
            modal.hidden = false;
        }

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeMessageDetailModal();
                closeLoginFailModal();
            }
        });

        function formatDateInBeijing(dateObj) {
            if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return '-';
            const formatter = new Intl.DateTimeFormat('zh-CN', {
                timeZone: 'Asia/Shanghai',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
            const parts = formatter.formatToParts(dateObj);
            const map = {};
            parts.forEach(part => {
                if (part && part.type) map[part.type] = part.value;
            });
            return `${map.year || '0000'}-${map.month || '00'}-${map.day || '00'} ${map.hour || '00'}:${map.minute || '00'}:${map.second || '00'}`;
        }

        function formatAuditTimestamp(rawValue) {
            const raw = String(rawValue || '').trim();
            if (!raw) return '-';
            const normalized = raw.replace(' ', 'T');
            const hasTimezone = /[zZ]$|[+\-]\d{2}:?\d{2}$/.test(normalized);

            if (!hasTimezone && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$/.test(raw)) {
                const normalizedRaw = raw.replace('T', ' ');
                return normalizedRaw.length === 16 ? `${normalizedRaw}:00` : normalizedRaw.slice(0, 19);
            }

            const dt = new Date(normalized);
            if (Number.isNaN(dt.getTime())) return raw.replace('T', ' ');
            return formatDateInBeijing(dt);
        }

        function updateAdminLoginLogsPagination(payload, visibleCount = 0) {
            const total = Number(payload?.total ?? 0) || 0;
            const page = Math.max(1, Number(payload?.page ?? 1) || 1);
            const pageSize = Math.max(5, Number(payload?.page_size ?? adminLoginLogsPageSize) || adminLoginLogsPageSize);
            const totalPages = Math.max(1, Number(payload?.total_pages ?? 1) || 1);

            adminLoginLogsTotal = total;
            adminLoginLogsPage = page;
            adminLoginLogsPageSize = pageSize;
            adminLoginLogsTotalPages = totalPages;

            const infoEl = document.getElementById('adminLoginLogsPageInfo');
            const currentEl = document.getElementById('adminLoginLogsPageCurrent');
            const prevBtn = document.getElementById('adminLoginLogsPrevBtn');
            const nextBtn = document.getElementById('adminLoginLogsNextBtn');
            const pageSizeSelect = document.getElementById('adminLoginLogsPageSize');

            if (pageSizeSelect && pageSizeSelect.value !== String(pageSize)) {
                pageSizeSelect.value = String(pageSize);
            }

            const start = total > 0 ? ((page - 1) * pageSize + 1) : 0;
            const end = total > 0 ? Math.min((page - 1) * pageSize + visibleCount, total) : 0;
            if (infoEl) {
                infoEl.textContent = total > 0 ? `第 ${start}-${end} 条，共 ${total} 条` : '共 0 条';
            }
            if (currentEl) {
                currentEl.textContent = `${page} / ${totalPages}`;
            }
            if (prevBtn) prevBtn.disabled = page <= 1;
            if (nextBtn) nextBtn.disabled = page >= totalPages;
        }

        function changeAdminLoginLogsPage(delta) {
            const nextPage = adminLoginLogsPage + Number(delta || 0);
            if (nextPage < 1 || nextPage > adminLoginLogsTotalPages) return;
            loadAdminLoginLogs(nextPage);
        }

        function changeAdminLoginLogsPageSize(rawValue) {
            const nextSize = Number(rawValue || ADMIN_LOGIN_LOG_DEFAULT_PAGE_SIZE);
            if (!Number.isFinite(nextSize) || nextSize < 5 || nextSize > 200) return;
            adminLoginLogsPageSize = nextSize;
            adminLoginLogsPage = 1;
            loadAdminLoginLogs(1);
        }

        async function loadAdminLoginLogs(page = adminLoginLogsPage) {
            const tbody = document.getElementById('adminLoginLogsBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="6" class="no-data">加载中...</td></tr>';

            try {
                const targetPage = Math.max(1, Number(page) || 1);
                const pageSize = Math.max(5, Number(adminLoginLogsPageSize) || ADMIN_LOGIN_LOG_DEFAULT_PAGE_SIZE);
                const url = `/api/admin/login-logs?page=${targetPage}&page_size=${pageSize}`;
                const res = await fetch(url);
                const payload = await res.json();
                if (!res.ok) throw new Error(payload?.message || '加载失败');

                const items = Array.isArray(payload?.items) ? payload.items : [];
                updateAdminLoginLogsPagination(payload, items.length);
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="6" class="no-data">暂无历史登录日志</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map((item, index) => {
                    const success = item?.success === true;
                    const operation = escapeHtml(item?.operation || '-');
                    const username = escapeHtml(item?.username || '');
                    const detail = escapeHtml(item?.detail || '');
                    const operationExtra = [];
                    if (username) operationExtra.push(`<div style="font-size:12px; color:#64748b;">账号：${username}</div>`);
                    if (detail) operationExtra.push(`<div style="font-size:12px; color:#64748b;">说明：${detail}</div>`);
                    const seq = (adminLoginLogsPage - 1) * adminLoginLogsPageSize + index + 1;

                    return `
                        <tr>
                            <td>${seq}</td>
                            <td>${escapeHtml(item?.ip || '-')}</td>
                            <td>${escapeHtml(item?.location || '未知')}</td>
                            <td><span class="audit-status-badge ${success ? 'audit-status-ok' : 'audit-status-fail'}">${success ? '成功' : '失败'}</span></td>
                            <td>${escapeHtml(formatAuditTimestamp(item?.timestamp))}</td>
                            <td>
                                <div>${operation}</div>
                                ${operationExtra.join('')}
                            </td>
                        </tr>
                    `;
                }).join('');
            } catch (e) {
                const reason = (e && e.message) ? escapeHtml(String(e.message)) : '加载失败';
                tbody.innerHTML = `<tr><td colspan="6" class="no-data">${reason}</td></tr>`;
                updateAdminLoginLogsPagination({ total: adminLoginLogsTotal, page: adminLoginLogsPage, page_size: adminLoginLogsPageSize, total_pages: adminLoginLogsTotalPages }, 0);
            }
        }

        function updateChatbotHistoryPagination(payload, visibleCount = 0) {
            const total = Number(payload?.total ?? 0) || 0;
            const page = Math.max(1, Number(payload?.page ?? 1) || 1);
            const pageSize = Math.max(5, Number(payload?.page_size ?? chatbotHistoryPageSize) || chatbotHistoryPageSize);
            const totalPages = Math.max(1, Number(payload?.total_pages ?? 1) || 1);

            chatbotHistoryTotal = total;
            chatbotHistoryPage = page;
            chatbotHistoryPageSize = pageSize;
            chatbotHistoryTotalPages = totalPages;

            const infoEl = document.getElementById('chatbotHistoryPageInfo');
            const currentEl = document.getElementById('chatbotHistoryPageCurrent');
            const prevBtn = document.getElementById('chatbotHistoryPrevBtn');
            const nextBtn = document.getElementById('chatbotHistoryNextBtn');
            const pageSizeSelect = document.getElementById('chatbotHistoryPageSize');

            if (pageSizeSelect && pageSizeSelect.value !== String(pageSize)) {
                pageSizeSelect.value = String(pageSize);
            }

            const start = total > 0 ? ((page - 1) * pageSize + 1) : 0;
            const end = total > 0 ? Math.min((page - 1) * pageSize + visibleCount, total) : 0;
            if (infoEl) {
                infoEl.textContent = total > 0 ? `第 ${start}-${end} 条，共 ${total} 条` : '共 0 条';
            }
            if (currentEl) {
                currentEl.textContent = `${page} / ${totalPages}`;
            }
            if (prevBtn) prevBtn.disabled = page <= 1;
            if (nextBtn) nextBtn.disabled = page >= totalPages;
        }

        function changeChatbotHistoryPage(delta) {
            const nextPage = chatbotHistoryPage + Number(delta || 0);
            if (nextPage < 1 || nextPage > chatbotHistoryTotalPages) return;
            loadChatbotConversationLogs(nextPage);
        }

        function changeChatbotHistoryPageSize(rawValue) {
            const nextSize = Number(rawValue || CHATBOT_HISTORY_DEFAULT_PAGE_SIZE);
            if (!Number.isFinite(nextSize) || nextSize < 5 || nextSize > 200) return;
            chatbotHistoryPageSize = nextSize;
            chatbotHistoryPage = 1;
            loadChatbotConversationLogs(1);
        }

        function formatChatbotHistorySource(source) {
            const value = String(source || '').trim();
            if (value === 'ai' || value === 'ai_sync_fallback') {
                return '<span class="chatbot-history-source chatbot-history-source-ai">AI 回复</span>';
            }
            if (value === 'local_fallback') {
                return '<span class="chatbot-history-source chatbot-history-source-fallback">降级回复</span>';
            }
            if (value === 'partial_ai_plus_fallback') {
                return '<span class="chatbot-history-source chatbot-history-source-mixed">混合回复</span>';
            }
            return `<span class="chatbot-history-source chatbot-history-source-mixed">${escapeHtml(value || '未知来源')}</span>`;
        }

        function formatChatbotHistoryText(rawValue) {
            const text = String(rawValue || '').trim();
            if (!text) return '<span class="chatbot-history-empty">-</span>';

            const preview = text.length > 120 ? `${text.slice(0, 120)}...` : text;
            const previewHtml = escapeHtml(preview).replace(/\n/g, '<br>');
            const fullHtml = escapeHtml(text).replace(/\n/g, '<br>');
            const needsExpand = text.length > 120 || text.includes('\n');

            if (!needsExpand) {
                return `<div class="chatbot-history-preview">${fullHtml}</div>`;
            }

            return `
                <div class="chatbot-history-preview">${previewHtml}</div>
                <details class="chatbot-history-details">
                    <summary>展开全文</summary>
                    <div class="chatbot-history-full">${fullHtml}</div>
                </details>
            `;
        }

        async function loadChatbotConversationLogs(page = chatbotHistoryPage) {
            const tbody = document.getElementById('chatbotHistoryBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="7" class="no-data">加载中...</td></tr>';

            try {
                const targetPage = Math.max(1, Number(page) || 1);
                const pageSize = Math.max(5, Number(chatbotHistoryPageSize) || CHATBOT_HISTORY_DEFAULT_PAGE_SIZE);
                const url = `/api/chatbot/history?page=${targetPage}&page_size=${pageSize}`;
                const res = await fetch(url);
                const payload = await res.json();
                if (!res.ok) throw new Error(payload?.message || '加载失败');

                const items = Array.isArray(payload?.items) ? payload.items : [];
                updateChatbotHistoryPagination(payload, items.length);
                if (!items.length) {
                    tbody.innerHTML = '<tr><td colspan="7" class="no-data">暂无历史对话</td></tr>';
                    return;
                }

                tbody.innerHTML = items.map((item, index) => {
                    const seq = (chatbotHistoryPage - 1) * chatbotHistoryPageSize + index + 1;
                    const ip = escapeHtml(item?.ip || '-');
                    const location = escapeHtml(item?.location || '未知');
                    const sessionId = escapeHtml(item?.session_id || '-');
                    const pageTitle = escapeHtml(item?.page_title || '');
                    const pageUrl = escapeHtml(item?.page_url || '');
                    const pageText = pageTitle || pageUrl
                        ? `${pageTitle || pageUrl}${pageTitle && pageUrl ? ` · ${pageUrl}` : ''}`
                        : '未记录页面信息';

                    return `
                        <tr>
                            <td>${seq}</td>
                            <td>${escapeHtml(formatAuditTimestamp(item?.timestamp))}</td>
                            <td>${ip}</td>
                            <td>${location}</td>
                            <td>
                                <div class="chatbot-history-meta">
                                    <div class="chatbot-history-session-id">${sessionId}</div>
                                    <div class="chatbot-history-page">${pageText}</div>
                                    ${formatChatbotHistorySource(item?.response_source)}
                                </div>
                            </td>
                            <td>${formatChatbotHistoryText(item?.user_message)}</td>
                            <td>${formatChatbotHistoryText(item?.assistant_message)}</td>
                        </tr>
                    `;
                }).join('');
                queueResponsiveTableLabels();
            } catch (e) {
                const reason = (e && e.message) ? escapeHtml(String(e.message)) : '加载失败';
                tbody.innerHTML = `<tr><td colspan="7" class="no-data">${reason}</td></tr>`;
                updateChatbotHistoryPagination({ total: chatbotHistoryTotal, page: chatbotHistoryPage, page_size: chatbotHistoryPageSize, total_pages: chatbotHistoryTotalPages }, 0);
            }
        }

        async function loadMessages() {
            const feedbackTbody = document.getElementById('messagesTableBody');
            const jobTbody = document.getElementById('jobApplicationsTableBody');
            if (feedbackTbody) feedbackTbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px;">加载中...</td></tr>';
            if (jobTbody) jobTbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 20px;">加载中...</td></tr>';

            try {
                const res = await fetch('/api/messages');
                if (!res.ok) {
                    throw new Error(`加载消息失败 (${res.status})`);
                }
                const payload = await res.json();
                const { messages, stats } = normalizeMessagesPayload(payload);
                setMessageCenterData(messages, stats);

                const feedbackItems = [];
                const jobItems = [];
                messageDetailMap = {};

                messages.forEach(msg => {
                    if (msg && msg.id) messageDetailMap[String(msg.id)] = msg;
                    if (msg.message_type === 'job_application') jobItems.push(msg);
                    else feedbackItems.push(msg);
                });

                if (feedbackTbody) {
                    if (feedbackItems.length === 0) {
                        feedbackTbody.innerHTML = '<tr><td colspan="5" class="no-data">暂无留言数据</td></tr>';
                    } else {
                        feedbackTbody.innerHTML = feedbackItems.map(msg => {
                            const timestamp = String(msg.timestamp || '');
                            const dateStr = timestamp.split('T')[0] || '-';
                            const timeStr = timestamp.length >= 16 ? timestamp.substring(11, 16) : '-';
                            const isRead = !!msg.is_read;
                            return `
                                <tr>
                                    <td>
                                        <div style="font-weight:500;">${escapeHtml(dateStr)}</div>
                                        <div style="font-size:12px; color:#888;">${escapeHtml(timeStr)}</div>
                                    </td>
                                    <td>
                                        <div style="font-weight:600;">${escapeHtml(msg.name || '')}</div>
                                        <div style="font-size:12px; color:#888;">${escapeHtml(msg.ip || '')}</div>
                                        <div style="font-size:12px; color:${isRead ? '#16a34a' : '#d97706'};">${isRead ? '已读' : '未读'}</div>
                                    </td>
                                    <td>${escapeHtml(msg.phone || '')}</td>
                                    <td>
                                        <div title="${escapeHtml(msg.content || '')}" style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                                            ${escapeHtml(msg.content || '')}
                                        </div>
                                        ${msg.email ? `<div style="font-size:12px; color:#888; margin-top:2px;"><i class="far fa-envelope"></i> ${escapeHtml(msg.email)}</div>` : ''}
                                    </td>
                                    <td>
                                        <button class="btn-sm" onclick="viewMessageDetail('${msg.id}')">
                                            <i class="far fa-eye"></i> 查看
                                        </button>
                                        <button class="btn-sm" onclick="markMessageRead('${msg.id}')" ${isRead ? 'disabled' : ''}>
                                            ${isRead ? '已读' : '标记已读'}
                                        </button>
                                        <button class="btn-sm btn-danger" onclick="deleteMessage('${msg.id}')">
                                            <i class="fas fa-trash"></i> 删除
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('');
                    }
                }

                if (jobTbody) {
                    if (jobItems.length === 0) {
                        jobTbody.innerHTML = '<tr><td colspan="6" class="no-data">暂无应聘信息</td></tr>';
                    } else {
                        jobTbody.innerHTML = jobItems.map(msg => {
                            const timestamp = String(msg.timestamp || '');
                            const dateStr = timestamp.split('T')[0] || '-';
                            const timeStr = timestamp.length >= 16 ? timestamp.substring(11, 16) : '-';
                            const isRead = !!msg.is_read;
                            const resumeHtml = msg.resume_url
                                ? `<a href="${escapeHtml(msg.resume_url)}" target="_blank" rel="noopener">下载简历</a>`
                                : '未上传';
                            const detailsHtml = `
                                <div><strong>职位：</strong>${escapeHtml(msg.job_title || msg.job_id || '-')}</div>
                                <div><strong>年龄/民族/性别：</strong>${escapeHtml(msg.age || '-')} / ${escapeHtml(msg.ethnicity || '-')} / ${escapeHtml(msg.gender || '-')}</div>
                                <div><strong>住址：</strong>${escapeHtml(msg.address || '-')}</div>
                                <div><strong>学历/院校：</strong>${escapeHtml(msg.education || '-')} / ${escapeHtml(msg.school || '-')}</div>
                                <div><strong>工作经历：</strong>${escapeHtml(msg.work_experience || '-')}</div>
                                <div><strong>项目经历：</strong>${escapeHtml(msg.project_experience || '-')}</div>
                                <div><strong>自我陈述：</strong>${escapeHtml(msg.self_statement || '-')}</div>
                            `;
                            return `
                                <tr>
                                    <td>
                                        <div style="font-weight:500;">${escapeHtml(dateStr)}</div>
                                        <div style="font-size:12px; color:#888;">${escapeHtml(timeStr)}</div>
                                    </td>
                                    <td>
                                        <div style="font-weight:600;">${escapeHtml(msg.name || '')}</div>
                                        <div style="font-size:12px; color:#888;">IP: ${escapeHtml(msg.ip || '')}</div>
                                        <div style="font-size:12px; color:${isRead ? '#16a34a' : '#d97706'};">${isRead ? '已读' : '未读'}</div>
                                    </td>
                                    <td>
                                        <div>${escapeHtml(msg.phone || '-')}</div>
                                        <div style="font-size:12px; color:#888;">${escapeHtml(msg.email || '-')}</div>
                                    </td>
                                    <td style="max-width: 460px; line-height:1.7;">${detailsHtml}</td>
                                    <td>${resumeHtml}</td>
                                    <td>
                                        <button class="btn-sm" onclick="viewMessageDetail('${msg.id}')">
                                            <i class="far fa-eye"></i> 查看
                                        </button>
                                        <button class="btn-sm" onclick="markMessageRead('${msg.id}')" ${isRead ? 'disabled' : ''}>
                                            ${isRead ? '已读' : '标记已读'}
                                        </button>
                                        <button class="btn-sm btn-danger" onclick="deleteMessage('${msg.id}')">
                                            <i class="fas fa-trash"></i> 删除
                                        </button>
                                    </td>
                                </tr>
                            `;
                        }).join('');
                    }
                }

                document.getElementById('totalCount').textContent = Number(stats.total_count ?? messages.length) || 0;
                document.getElementById('jobCount').textContent = Number(stats.job_count ?? jobItems.length) || 0;
                document.getElementById('todayCount').textContent = Number(stats.today_count ?? 0) || 0;
                document.getElementById('readCount').textContent = Number(stats.read_count ?? 0) || 0;
                document.getElementById('deletedCount').textContent = Number(stats.deleted_count ?? 0) || 0;

            } catch (e) {
                if (feedbackTbody) feedbackTbody.innerHTML = '<tr><td colspan="5" class="no-data">加载失败</td></tr>';
                if (jobTbody) jobTbody.innerHTML = '<tr><td colspan="6" class="no-data">加载失败</td></tr>';
                document.getElementById('totalCount').textContent = '0';
                document.getElementById('jobCount').textContent = '0';
                document.getElementById('todayCount').textContent = '0';
                document.getElementById('readCount').textContent = '0';
                document.getElementById('deletedCount').textContent = '0';
            }
        }

        async function deleteMessage(id) {
            if (!await showGlobalConfirm('确定删除这条留言吗？此操作无法撤销。')) return;
            try {
                const res = await fetch(`/api/messages/${id}`, { method: 'DELETE' });
                if (res.ok) loadMessages();
                else alert('删除失败');
            } catch (e) {
                alert('网络错误');
            }
        }

        async function markMessageRead(id) {
            try {
                const res = await fetch(`/api/messages/${id}/read`, { method: 'POST' });
                const data = await res.json();
                if (res.ok && data.success) {
                    loadMessages();
                } else {
                    alert(data.message || '标记已读失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        function stopBindingTimer() {
            if (bindingTimer) {
                clearInterval(bindingTimer);
                bindingTimer = null;
            }
        }

        function startBindingTimer(seconds) {
            stopBindingTimer();
            bindingCountdown = Math.max(0, Number(seconds || 0));
            updateBindingActionState();
            if (bindingCountdown <= 0) return;
            bindingTimer = setInterval(() => {
                bindingCountdown = Math.max(0, bindingCountdown - 1);
                updateBindingActionState();
                if (bindingCountdown <= 0) stopBindingTimer();
            }, 1000);
        }

        function updateBindingActionState() {
            const sendBtn = document.getElementById('bindingSendCodeBtn');
            const verifyBtn = document.getElementById('bindingVerifyBtn');
            const banner = document.getElementById('bindingRequiredBanner');
            const codeWrap = document.getElementById('bindingCodeWrap');
            if (banner) banner.style.display = bindingRequiredState ? 'block' : 'none';
            if (codeWrap) codeWrap.style.display = bindingCountdown > 0 || bindingRequiredState ? 'block' : (document.getElementById('bindingCodeInput')?.value ? 'block' : 'none');
            if (sendBtn) sendBtn.textContent = bindingCountdown > 0 ? `重新发送（${bindingCountdown}s）` : '发送绑定验证码';
            if (sendBtn) sendBtn.disabled = bindingCountdown > 0;
            if (verifyBtn) verifyBtn.disabled = false;
        }

        async function loadEmailBindingStatus() {
            const statusEl = document.getElementById('bindingStatusText');
            const inputEl = document.getElementById('bindingEmailInput');
            const msgEl = document.getElementById('bindingMsg');
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#28a745';
            }
            try {
                const res = await fetch('/api/admin/account/email-binding', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    if (statusEl) statusEl.textContent = '邮箱状态加载失败';
                    return;
                }
                if (inputEl) inputEl.value = String(data.email || '');
                if (statusEl) {
                    statusEl.textContent = data.email_verified
                        ? `已绑定：${String(data.email_masked || data.email || '')}`
                        : '尚未绑定安全邮箱';
                }
                bindingRequiredState = data.binding_required === true || bindingRequiredState;
                updateBindingActionState();
            } catch (e) {
                if (statusEl) statusEl.textContent = '邮箱状态加载失败';
            }
        }

        async function sendBindingCode() {
            const msgEl = document.getElementById('bindingMsg');
            const email = String(document.getElementById('bindingEmailInput')?.value || '').trim();
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#dc3545';
            }
            if (!email) {
                if (msgEl) msgEl.textContent = '请先输入邮箱地址。';
                return;
            }
            try {
                const res = await fetch('/api/admin/account/email-binding/send-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    if (msgEl) msgEl.textContent = data.message || '验证码发送失败';
                    return;
                }
                if (msgEl) {
                    msgEl.style.color = '#28a745';
                    msgEl.textContent = data.message || '绑定验证码已发送。';
                }
                startBindingTimer(Number(data.resend_after || 60));
                const codeWrap = document.getElementById('bindingCodeWrap');
                if (codeWrap) codeWrap.style.display = 'block';
            } catch (e) {
                if (msgEl) msgEl.textContent = '网络错误，验证码发送失败';
            }
        }

        async function verifyBindingCode() {
            const msgEl = document.getElementById('bindingMsg');
            const email = String(document.getElementById('bindingEmailInput')?.value || '').trim();
            const code = String(document.getElementById('bindingCodeInput')?.value || '').trim();
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#dc3545';
            }
            if (!email || !code) {
                if (msgEl) msgEl.textContent = '请输入邮箱和验证码。';
                return;
            }
            try {
                const res = await fetch('/api/admin/account/email-binding/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, code })
                });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    if (msgEl) msgEl.textContent = data.message || '邮箱绑定失败';
                    return;
                }
                if (msgEl) {
                    msgEl.style.color = '#28a745';
                    msgEl.textContent = data.message || '邮箱绑定成功';
                }
                bindingRequiredState = false;
                stopBindingTimer();
                bindingCountdown = 0;
                if (document.getElementById('bindingCodeInput')) document.getElementById('bindingCodeInput').value = '';
                await checkLoginStatus();
                await loadEmailBindingStatus();
            } catch (e) {
                if (msgEl) msgEl.textContent = '网络错误，邮箱绑定失败';
            }
        }

        function renderSmtpExpiryStatus(config = {}) {
            const statusEl = document.getElementById('smtpExpiryStatus');
            if (!statusEl) return;
            const remaining = Number(config.smtp_password_remaining_days);
            const expiresAt = String(config.smtp_password_expires_at || '').trim();
            if (!config.smtp_configured) {
                statusEl.textContent = '当前 SMTP 配置不完整。';
                statusEl.style.color = '#b45309';
                return;
            }
            if (config.smtp_password_expired) {
                statusEl.textContent = `授权码已到期${expiresAt ? `（${expiresAt}）` : ''}，请立即更新。`;
                statusEl.style.color = '#b91c1c';
                return;
            }
            if (Number.isFinite(remaining)) {
                statusEl.textContent = `授权码预计剩余 ${remaining} 天${expiresAt ? `，到期时间：${expiresAt}` : ''}`;
                statusEl.style.color = remaining <= 7 ? '#b45309' : '#2e7d32';
                return;
            }
            statusEl.textContent = '已配置，但尚未记录授权码到期时间。';
            statusEl.style.color = '#666';
        }

        async function loadEmailAuthSettings() {
            const msgEl = document.getElementById('emailAuthSettingsMsg');
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#28a745';
            }
            try {
                const res = await fetch('/api/admin/email-auth/config', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                emailAuthAdminConfig = data && typeof data === 'object' ? data : { email_auth_enabled: false };
                const setValue = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.value = value || '';
                };
                const setChecked = (id, value) => {
                    const el = document.getElementById(id);
                    if (el) el.checked = value === true;
                };
                setChecked('emailAuthEnabled', data.email_auth_enabled === true);
                setValue('smtpHost', data.smtp_host || '');
                setValue('smtpPort', data.smtp_port || 465);
                setValue('smtpUsername', data.smtp_username || '');
                setValue('smtpFromName', data.smtp_from_name || '');
                setValue('smtpFromEmail', data.smtp_from_email || '');
                setValue('smtpNoticeEmail', data.smtp_notice_email || '');
                const smtpPwdEl = document.getElementById('smtpPassword');
                if (smtpPwdEl) {
                    smtpPwdEl.value = '';
                    smtpPwdEl.placeholder = data.smtp_password_masked ? `${data.smtp_password_masked}（留空不修改）` : '留空表示保持当前授权码不变';
                }
                setChecked('smtpUseSsl', data.smtp_use_ssl !== false);
                setChecked('smtpUseTls', data.smtp_use_tls === true);
                renderSmtpExpiryStatus(data);
                updateLoginActionState();
            } catch (e) {
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = 'SMTP 设置加载失败';
                }
            }
        }

        function getAdminLoginGeoDisplayNameObjects() {
            if (adminLoginGeoDisplayNames === null) {
                try {
                    adminLoginGeoDisplayNames = typeof Intl !== 'undefined' && Intl.DisplayNames
                        ? new Intl.DisplayNames(['zh-Hans-CN', 'zh-CN', 'en'], { type: 'region' })
                        : null;
                } catch (e) {
                    adminLoginGeoDisplayNames = null;
                }
            }
            if (adminLoginGeoDisplayNamesEn === null) {
                try {
                    adminLoginGeoDisplayNamesEn = typeof Intl !== 'undefined' && Intl.DisplayNames
                        ? new Intl.DisplayNames(['en'], { type: 'region' })
                        : null;
                } catch (e) {
                    adminLoginGeoDisplayNamesEn = null;
                }
            }
            return {
                zh: adminLoginGeoDisplayNames,
                en: adminLoginGeoDisplayNamesEn
            };
        }

        function getAdminLoginGeoCountryMeta(code) {
            const safeCode = String(code || '').trim().toUpperCase();
            if (!safeCode) {
                return { label: '', labelEn: '', searchText: '' };
            }
            if (adminLoginGeoCountryMetaCache.has(safeCode)) {
                return adminLoginGeoCountryMetaCache.get(safeCode);
            }
            const displayNames = getAdminLoginGeoDisplayNameObjects();
            let label = safeCode;
            let labelEn = safeCode;
            try {
                const zhName = displayNames.zh ? String(displayNames.zh.of(safeCode) || '').trim() : '';
                const enName = displayNames.en ? String(displayNames.en.of(safeCode) || '').trim() : '';
                if (zhName && zhName.toUpperCase() !== safeCode) label = zhName;
                if (enName && enName.toUpperCase() !== safeCode) labelEn = enName;
                if (label === safeCode && labelEn && labelEn !== safeCode) label = labelEn;
            } catch (e) {
                // Keep ISO code fallback.
            }
            const meta = {
                label,
                labelEn,
                searchText: `${label} ${labelEn} ${safeCode}`.toLowerCase()
            };
            adminLoginGeoCountryMetaCache.set(safeCode, meta);
            return meta;
        }

        function normalizeAdminLoginGeoCatalog(rawCatalog = {}) {
            const rawContinents = Array.isArray(rawCatalog.continents) ? rawCatalog.continents : [];
            return {
                continents: rawContinents.map((item) => ({
                    key: String(item?.key || '').trim(),
                    label: String(item?.label || item?.key || '').trim(),
                    countries: Array.isArray(item?.countries)
                        ? item.countries.map(code => String(code || '').trim().toUpperCase()).filter(Boolean)
                        : []
                })).filter(item => item.key)
            };
        }

        function normalizeAdminLoginGeoConfig(rawConfig = {}, catalog = adminLoginGeoCatalog) {
            const continents = {};
            (Array.isArray(catalog.continents) ? catalog.continents : []).forEach((continent) => {
                const rawValue = String(rawConfig?.continents?.[continent.key] || '').trim().toLowerCase();
                continents[continent.key] = rawValue === 'allow' ? 'allow' : 'deny';
            });
            const countries = {};
            const rawCountries = rawConfig && typeof rawConfig.countries === 'object' ? rawConfig.countries : {};
            Object.entries(rawCountries || {}).forEach(([rawCode, rawValue]) => {
                const code = String(rawCode || '').trim().toUpperCase();
                const value = String(rawValue || '').trim().toLowerCase();
                if (!code) return;
                if (value === 'allow' || value === 'deny') {
                    countries[code] = value;
                }
            });
            return {
                enabled: rawConfig?.enabled !== false,
                continents,
                countries
            };
        }

        function updateAdminLoginGeoStatusText() {
            const statusEl = document.getElementById('adminLoginGeoStatusText');
            if (!statusEl) return;
            if (!adminLoginGeoConfig.enabled) {
                statusEl.textContent = '当前状态：已关闭';
                statusEl.style.color = '#666';
                return;
            }
            const continentAllows = Object.values(adminLoginGeoConfig.continents || {}).filter(v => v === 'allow').length;
            const countryAllows = Object.values(adminLoginGeoConfig.countries || {}).filter(v => v === 'allow').length;
            const countryDenies = Object.values(adminLoginGeoConfig.countries || {}).filter(v => v === 'deny').length;
            statusEl.textContent = `当前状态：已启用；允许大洲 ${continentAllows} 个，国家单独允许 ${countryAllows} 个，单独禁止 ${countryDenies} 个`;
            statusEl.style.color = '#2e7d32';
        }

        function getAdminLoginGeoContinents() {
            return Array.isArray(adminLoginGeoCatalog.continents) ? adminLoginGeoCatalog.continents : [];
        }

        function getAdminLoginGeoContinentByKey(continentKey) {
            return getAdminLoginGeoContinents().find(item => item.key === continentKey) || null;
        }

        function getAdminLoginGeoCountriesForContinent(continentKey) {
            const continent = getAdminLoginGeoContinentByKey(continentKey);
            return continent && Array.isArray(continent.countries) ? [...continent.countries] : [];
        }

        function sortAdminLoginGeoCountryCodes(codes) {
            return [...codes].sort((a, b) => {
                const nameA = getAdminLoginGeoCountryMeta(a).label;
                const nameB = getAdminLoginGeoCountryMeta(b).label;
                return nameA.localeCompare(nameB, 'zh-CN');
            });
        }

        function ensureAdminLoginGeoSelections() {
            const continents = getAdminLoginGeoContinents();
            if (!continents.length) {
                adminLoginGeoSelectedContinentKey = '';
                adminLoginGeoSelectedCountryContinentKey = '';
                adminLoginGeoSelectedCountryCode = '';
                return;
            }
            const continentKeys = continents.map(item => item.key);
            if (!continentKeys.includes(adminLoginGeoSelectedContinentKey)) {
                adminLoginGeoSelectedContinentKey = continentKeys[0];
            }
            if (!continentKeys.includes(adminLoginGeoSelectedCountryContinentKey)) {
                adminLoginGeoSelectedCountryContinentKey = continentKeys[0];
            }
            const countryCodes = sortAdminLoginGeoCountryCodes(
                getAdminLoginGeoCountriesForContinent(adminLoginGeoSelectedCountryContinentKey)
            );
            if (!countryCodes.includes(adminLoginGeoSelectedCountryCode)) {
                adminLoginGeoSelectedCountryCode = countryCodes[0] || '';
            }
        }

        function renderAdminLoginGeoContinentControls() {
            const continentSelect = document.getElementById('adminLoginGeoContinentSelect');
            const policySelect = document.getElementById('adminLoginGeoContinentPolicy');
            const hintEl = document.getElementById('adminLoginGeoContinentHint');
            if (!continentSelect || !policySelect || !hintEl) return;
            const continents = getAdminLoginGeoContinents();
            continentSelect.innerHTML = continents.map((continent) => (
                `<option value="${escapeHtml(continent.key)}">${escapeHtml(continent.label)}</option>`
            )).join('');
            continentSelect.value = adminLoginGeoSelectedContinentKey;
            const continent = getAdminLoginGeoContinentByKey(adminLoginGeoSelectedContinentKey);
            const policy = adminLoginGeoConfig.continents?.[adminLoginGeoSelectedContinentKey] === 'allow' ? 'allow' : 'deny';
            policySelect.value = policy;
            hintEl.textContent = continent
                ? `${continent.label}共 ${Array.isArray(continent.countries) ? continent.countries.length : 0} 个国家或地区，当前默认规则：${policy === 'allow' ? '允许登录' : '禁止登录'}。`
                : '请选择一个大洲后设置默认规则。';
        }

        function renderAdminLoginGeoCountryControls() {
            const continentFilterSelect = document.getElementById('adminLoginGeoCountryContinentFilter');
            const countrySelect = document.getElementById('adminLoginGeoCountrySelect');
            const policySelect = document.getElementById('adminLoginGeoCountryPolicy');
            const hintEl = document.getElementById('adminLoginGeoCountryHint');
            if (!continentFilterSelect || !countrySelect || !policySelect || !hintEl) return;
            const continents = getAdminLoginGeoContinents();
            continentFilterSelect.innerHTML = continents.map((continent) => (
                `<option value="${escapeHtml(continent.key)}">${escapeHtml(continent.label)}</option>`
            )).join('');
            continentFilterSelect.value = adminLoginGeoSelectedCountryContinentKey;

            const countryCodes = sortAdminLoginGeoCountryCodes(
                getAdminLoginGeoCountriesForContinent(adminLoginGeoSelectedCountryContinentKey)
            );
            countrySelect.innerHTML = countryCodes.map((code) => {
                const meta = getAdminLoginGeoCountryMeta(code);
                const label = `${meta.label} (${code})`;
                return `<option value="${escapeHtml(code)}">${escapeHtml(label)}</option>`;
            }).join('');
            countrySelect.value = adminLoginGeoSelectedCountryCode;

            const continent = getAdminLoginGeoContinentByKey(adminLoginGeoSelectedCountryContinentKey);
            const countryMeta = getAdminLoginGeoCountryMeta(adminLoginGeoSelectedCountryCode);
            const continentPolicy = adminLoginGeoConfig.continents?.[adminLoginGeoSelectedCountryContinentKey] === 'allow' ? 'allow' : 'deny';
            const policy = adminLoginGeoConfig.countries?.[adminLoginGeoSelectedCountryCode] || 'inherit';
            policySelect.value = policy;

            const policyLabel = policy === 'allow'
                ? '允许登录'
                : (policy === 'deny' ? '禁止登录' : `跟随${continent ? continent.label : '所属大洲'}（${continentPolicy === 'allow' ? '允许登录' : '禁止登录'}）`);
            hintEl.textContent = adminLoginGeoSelectedCountryCode
                ? `${countryMeta.label} 当前规则：${policyLabel}。`
                : '请选择一个国家或地区后设置覆盖规则。';
        }

        function renderAdminLoginGeoSettings() {
            ensureAdminLoginGeoSelections();
            const enabledEl = document.getElementById('adminLoginGeoEnabled');
            if (enabledEl) enabledEl.checked = adminLoginGeoConfig.enabled !== false;
            renderAdminLoginGeoContinentControls();
            renderAdminLoginGeoCountryControls();
            updateAdminLoginGeoStatusText();
        }

        async function loadAdminLoginGeoSettings() {
            const msgEl = document.getElementById('adminLoginGeoSettingsMsg');
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#28a745';
            }
            try {
                const res = await fetch('/api/admin/security/login-geo', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '加载失败');
                }
                adminLoginGeoCatalog = normalizeAdminLoginGeoCatalog(data.catalog || {});
                adminLoginGeoConfig = normalizeAdminLoginGeoConfig(data.config || {}, adminLoginGeoCatalog);
                ensureAdminLoginGeoSelections();
                renderAdminLoginGeoSettings();
            } catch (e) {
                updateAdminLoginGeoStatusText();
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = '后台登录地域规则加载失败';
                }
            }
        }

        // --- Settings Logic ---
        function downloadFullBackup() {
            window.open('/api/backup/download', '_blank');
        }

        async function restoreFromBackup() {
            const fileInput = document.getElementById('backupRestoreFile');
            const msg = document.getElementById('backupMsg');
            const file = fileInput?.files?.[0];
            if (msg) {
                msg.style.color = '#dc3545';
                msg.textContent = '';
            }
            if (!file) {
                if (msg) msg.textContent = '请先选择备份 ZIP 文件';
                return;
            }
            if (!String(file.name || '').toLowerCase().endsWith('.zip')) {
                if (msg) msg.textContent = '仅支持 ZIP 备份文件';
                return;
            }
            if (!await showGlobalConfirm('恢复会覆盖当前数据，确认继续吗？')) return;

            const fd = new FormData();
            fd.append('file', file);
            if (msg) {
                msg.style.color = '#666';
                msg.textContent = '恢复中，请稍候...';
            }
            try {
                const res = await fetch('/api/backup/restore', {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    if (msg) {
                        msg.style.color = '#28a745';
                        const restoredFiles = Number(data.restored_files || 0);
                        const restoredEntries = Number(data.restored_entries || 0);
                        const extra = restoredFiles
                            ? `（已恢复 ${restoredFiles} 个文件，${restoredEntries} 个顶层条目）`
                            : '';
                        msg.textContent = (data.message || '恢复成功，请重启服务并刷新后台。') + extra;
                    }
                    if (fileInput) fileInput.value = '';
                } else if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = data.message || '恢复失败';
                }
            } catch (e) {
                if (msg) {
                    msg.style.color = '#dc3545';
                    msg.textContent = '网络错误，恢复失败';
                }
            }
        }

        function updateTurnstileStatusText(enabled, siteKey) {
            const statusEl = document.getElementById('turnstileStatusText');
            if (!statusEl) return;
            if (!enabled) {
                statusEl.textContent = '当前状态：已关闭';
                statusEl.style.color = '#666';
                return;
            }
            statusEl.textContent = siteKey ? '当前状态：已开启' : '当前状态：配置不完整';
            statusEl.style.color = siteKey ? '#2e7d32' : '#d97706';
        }

        async function loadTurnstileAdminConfig() {
            const enabledEl = document.getElementById('turnstileEnabled');
            const siteEl = document.getElementById('turnstileSiteKey');
            const secretEl = document.getElementById('turnstileSecretKey');
            const msgEl = document.getElementById('turnstileSettingsMsg');
            if (!enabledEl || !siteEl || !secretEl) return;

            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#28a745';
            }

            try {
                const res = await fetch('/api/admin/security/turnstile', { cache: 'no-store' });
                const data = await res.json();
                enabledEl.checked = data.enabled === true;
                siteEl.value = data.site_key || '';
                secretEl.value = '';
                secretEl.placeholder = data.secret_key ? `${data.secret_key}（留空不修改）` : '留空表示保持当前密钥不变';
                updateTurnstileStatusText(enabledEl.checked, siteEl.value.trim());
            } catch (e) {
                updateTurnstileStatusText(false, '');
                if (msgEl) {
                    msgEl.style.color = '#dc3545';
                    msgEl.textContent = '登录验证设置加载失败';
                }
            }
        }

        const adminLoginGeoContinentSelectEl = document.getElementById('adminLoginGeoContinentSelect');
        if (adminLoginGeoContinentSelectEl && adminLoginGeoContinentSelectEl.dataset.bound !== '1') {
            adminLoginGeoContinentSelectEl.dataset.bound = '1';
            adminLoginGeoContinentSelectEl.addEventListener('change', function () {
                adminLoginGeoSelectedContinentKey = String(this.value || '').trim();
                renderAdminLoginGeoContinentControls();
            });
        }

        const adminLoginGeoContinentPolicyEl = document.getElementById('adminLoginGeoContinentPolicy');
        if (adminLoginGeoContinentPolicyEl && adminLoginGeoContinentPolicyEl.dataset.bound !== '1') {
            adminLoginGeoContinentPolicyEl.dataset.bound = '1';
            adminLoginGeoContinentPolicyEl.addEventListener('change', function () {
                const continentKey = String(document.getElementById('adminLoginGeoContinentSelect')?.value || '').trim();
                if (!continentKey) return;
                adminLoginGeoConfig.continents = adminLoginGeoConfig.continents || {};
                adminLoginGeoConfig.continents[continentKey] = String(this.value || '').trim() === 'allow' ? 'allow' : 'deny';
                renderAdminLoginGeoContinentControls();
                renderAdminLoginGeoCountryControls();
                updateAdminLoginGeoStatusText();
            });
        }

        const adminLoginGeoCountryContinentFilterEl = document.getElementById('adminLoginGeoCountryContinentFilter');
        if (adminLoginGeoCountryContinentFilterEl && adminLoginGeoCountryContinentFilterEl.dataset.bound !== '1') {
            adminLoginGeoCountryContinentFilterEl.dataset.bound = '1';
            adminLoginGeoCountryContinentFilterEl.addEventListener('change', function () {
                adminLoginGeoSelectedCountryContinentKey = String(this.value || '').trim();
                ensureAdminLoginGeoSelections();
                renderAdminLoginGeoCountryControls();
            });
        }

        const adminLoginGeoCountrySelectEl = document.getElementById('adminLoginGeoCountrySelect');
        if (adminLoginGeoCountrySelectEl && adminLoginGeoCountrySelectEl.dataset.bound !== '1') {
            adminLoginGeoCountrySelectEl.dataset.bound = '1';
            adminLoginGeoCountrySelectEl.addEventListener('change', function () {
                adminLoginGeoSelectedCountryCode = String(this.value || '').trim().toUpperCase();
                renderAdminLoginGeoCountryControls();
            });
        }

        const adminLoginGeoCountryPolicyEl = document.getElementById('adminLoginGeoCountryPolicy');
        if (adminLoginGeoCountryPolicyEl && adminLoginGeoCountryPolicyEl.dataset.bound !== '1') {
            adminLoginGeoCountryPolicyEl.dataset.bound = '1';
            adminLoginGeoCountryPolicyEl.addEventListener('change', function () {
                const countryCode = String(document.getElementById('adminLoginGeoCountrySelect')?.value || '').trim().toUpperCase();
                if (!countryCode) return;
                const nextValue = String(this.value || '').trim().toLowerCase();
                adminLoginGeoConfig.countries = adminLoginGeoConfig.countries || {};
                if (nextValue === 'allow' || nextValue === 'deny') {
                    adminLoginGeoConfig.countries[countryCode] = nextValue;
                } else {
                    delete adminLoginGeoConfig.countries[countryCode];
                }
                renderAdminLoginGeoCountryControls();
                updateAdminLoginGeoStatusText();
            });
        }

        const adminLoginGeoEnabledEl = document.getElementById('adminLoginGeoEnabled');
        if (adminLoginGeoEnabledEl && adminLoginGeoEnabledEl.dataset.bound !== '1') {
            adminLoginGeoEnabledEl.dataset.bound = '1';
            adminLoginGeoEnabledEl.addEventListener('change', function () {
                adminLoginGeoConfig.enabled = this.checked === true;
                updateAdminLoginGeoStatusText();
            });
        }

        const adminLoginGeoSettingsForm = document.getElementById('adminLoginGeoSettingsForm');
        if (adminLoginGeoSettingsForm && adminLoginGeoSettingsForm.dataset.bound !== '1') {
            adminLoginGeoSettingsForm.dataset.bound = '1';
            adminLoginGeoSettingsForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const btn = e.target.querySelector('button[type="submit"]');
                const msg = document.getElementById('adminLoginGeoSettingsMsg');
                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#dc3545';
                }
                if (btn) btn.disabled = true;
                try {
                    const res = await fetch('/api/admin/security/login-geo', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            enabled: adminLoginGeoConfig.enabled !== false,
                            continents: adminLoginGeoConfig.continents || {},
                            countries: adminLoginGeoConfig.countries || {}
                        })
                    });
                    const data = await parseJsonSafe(res);
                    if (!res.ok || !data.success) {
                        if (msg) msg.textContent = data.message || '保存失败';
                        return;
                    }
                    adminLoginGeoCatalog = normalizeAdminLoginGeoCatalog(data.catalog || adminLoginGeoCatalog);
                    adminLoginGeoConfig = normalizeAdminLoginGeoConfig(data.config || adminLoginGeoConfig, adminLoginGeoCatalog);
                    renderAdminLoginGeoSettings();
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = data.message || '地域规则保存成功';
                    }
                } catch (e) {
                    if (msg) msg.textContent = '网络错误，保存失败';
                } finally {
                    if (btn) btn.disabled = false;
                }
            });
        }

        const turnstileEnabledEl = document.getElementById('turnstileEnabled');
        if (turnstileEnabledEl) {
            turnstileEnabledEl.addEventListener('change', function () {
                const site = document.getElementById('turnstileSiteKey')?.value.trim() || '';
                updateTurnstileStatusText(this.checked, site);
            });
        }
        const turnstileSiteKeyEl = document.getElementById('turnstileSiteKey');
        if (turnstileSiteKeyEl) {
            turnstileSiteKeyEl.addEventListener('input', function () {
                const enabled = !!document.getElementById('turnstileEnabled')?.checked;
                updateTurnstileStatusText(enabled, this.value.trim());
            });
        }

        const turnstileSettingsForm = document.getElementById('turnstileSettingsForm');
        if (turnstileSettingsForm) {
            turnstileSettingsForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const btn = e.target.querySelector('button[type="submit"]');
                const msg = document.getElementById('turnstileSettingsMsg');
                const enabled = !!document.getElementById('turnstileEnabled')?.checked;
                const siteKey = String(document.getElementById('turnstileSiteKey')?.value || '').trim();
                const secretKey = String(document.getElementById('turnstileSecretKey')?.value || '').trim();

                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#dc3545';
                }

                if (enabled && !siteKey) {
                    if (msg) msg.textContent = '启用登录验证时必须填写站点密钥';
                    return;
                }

                if (btn) btn.disabled = true;
                try {
                    const res = await fetch('/api/admin/security/turnstile', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            enabled: enabled,
                            site_key: siteKey,
                            secret_key: secretKey
                        })
                    });
                    const data = await res.json();
                    if (res.ok && data.success) {
                        if (msg) {
                            msg.style.color = '#28a745';
                            msg.textContent = '登录验证设置保存成功';
                        }
                        await loadTurnstileAdminConfig();
                        // Ensure login page uses latest security mode without refresh.
                        await initLoginSecurity();
                    } else if (msg) {
                        msg.textContent = data.message || '保存失败';
                    }
                } catch (e) {
                    if (msg) msg.textContent = '网络错误，保存失败';
                } finally {
                    if (btn) btn.disabled = false;
                }
            });
        }

        document.getElementById('settingsForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            const msg = document.getElementById('settingsMsg');

            btn.disabled = true;
            msg.textContent = '';
            msg.style.color = '#dc3545'; // default error color

            try {
                const res = await fetch('/admin/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        oldPassword: document.getElementById('oldPassword').value,
                        newUsername: document.getElementById('newUsername').value,
                        newPassword: document.getElementById('newPassword').value
                    })
                });
                const data = await res.json();

                if (data.success) {
                    msg.style.color = '#28a745';
                    msg.textContent = '修改成功！下次登录请使用新账号密码。';
                    e.target.reset();
                } else {
                    msg.textContent = data.message || '修改失败';
                }
            } catch (e) {
                msg.textContent = '网络错误';
            } finally {
                btn.disabled = false;
            }
        });

        const bindingSendCodeBtn = document.getElementById('bindingSendCodeBtn');
        if (bindingSendCodeBtn && bindingSendCodeBtn.dataset.bound !== '1') {
            bindingSendCodeBtn.dataset.bound = '1';
            bindingSendCodeBtn.addEventListener('click', async () => {
                await sendBindingCode();
            });
        }

        const bindingVerifyBtn = document.getElementById('bindingVerifyBtn');
        if (bindingVerifyBtn && bindingVerifyBtn.dataset.bound !== '1') {
            bindingVerifyBtn.dataset.bound = '1';
            bindingVerifyBtn.addEventListener('click', async () => {
                await verifyBindingCode();
            });
        }

        const emailAuthSettingsForm = document.getElementById('emailAuthSettingsForm');
        if (emailAuthSettingsForm && emailAuthSettingsForm.dataset.bound !== '1') {
            emailAuthSettingsForm.dataset.bound = '1';
            emailAuthSettingsForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const btn = e.target.querySelector('button[type="submit"]');
                const msg = document.getElementById('emailAuthSettingsMsg');
                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#dc3545';
                }
                if (btn) btn.disabled = true;
                try {
                    const res = await fetch('/api/admin/email-auth/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            email_auth_enabled: !!document.getElementById('emailAuthEnabled')?.checked,
                            smtp_host: document.getElementById('smtpHost')?.value || '',
                            smtp_port: document.getElementById('smtpPort')?.value || 465,
                            smtp_username: document.getElementById('smtpUsername')?.value || '',
                            smtp_password_or_app_code: document.getElementById('smtpPassword')?.value || '',
                            smtp_use_ssl: !!document.getElementById('smtpUseSsl')?.checked,
                            smtp_use_tls: !!document.getElementById('smtpUseTls')?.checked,
                            smtp_from_name: document.getElementById('smtpFromName')?.value || '',
                            smtp_from_email: document.getElementById('smtpFromEmail')?.value || '',
                            smtp_notice_email: document.getElementById('smtpNoticeEmail')?.value || ''
                        })
                    });
                    const data = await parseJsonSafe(res);
                    if (!res.ok || !data.success) {
                        if (msg) msg.textContent = data.message || '保存失败';
                        return;
                    }
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = data.message || 'SMTP 设置保存成功';
                    }
                    await loadEmailAuthSettings();
                    await initLoginSecurity();
                } catch (e) {
                    if (msg) msg.textContent = '网络错误，保存失败';
                } finally {
                    if (btn) btn.disabled = false;
                }
            });
        }

        const smtpTestBtn = document.getElementById('smtpTestBtn');
        if (smtpTestBtn && smtpTestBtn.dataset.bound !== '1') {
            smtpTestBtn.dataset.bound = '1';
            smtpTestBtn.addEventListener('click', async () => {
                const msg = document.getElementById('emailAuthSettingsMsg');
                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#666';
                    msg.textContent = '测试邮件发送中...';
                }
                smtpTestBtn.disabled = true;
                try {
                    const res = await fetch('/api/admin/email-auth/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            target_email: document.getElementById('smtpNoticeEmail')?.value || ''
                        })
                    });
                    const data = await parseJsonSafe(res);
                    if (msg) {
                        msg.style.color = res.ok && data.success ? '#28a745' : '#dc3545';
                        msg.textContent = data.message || (res.ok ? '测试邮件已发送' : '测试失败');
                    }
                } catch (e) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '网络错误，测试失败';
                    }
                } finally {
                    smtpTestBtn.disabled = false;
                }
            });
        }

        let subAccountsCache = [];

        function renderPermissionGrid(containerId, selectedPermissions = []) {
            const container = document.getElementById(containerId);
            if (!container) return;
            const selectedSet = new Set((selectedPermissions || []).map(v => String(v || '').trim()));
            const catalog = Array.isArray(permissionCatalog) && permissionCatalog.length
                ? permissionCatalog
                : DEFAULT_PERMISSION_CATALOG;
            container.innerHTML = catalog.map(item => {
                const key = String(item.key || '').trim();
                const label = String(item.label || key);
                const checked = selectedSet.has(key) ? 'checked' : '';
                return `
                    <label style="display:flex; align-items:center; gap:8px; background:#fff; border:1px solid #e5e7eb; border-radius:6px; padding:8px 10px;">
                        <input type="checkbox" data-permission-key="${escapeHtml(key)}" ${checked}>
                        <span>${escapeHtml(label)}</span>
                    </label>
                `;
            }).join('');
        }

        function readPermissionGrid(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return [];
            const output = [];
            container.querySelectorAll('input[type="checkbox"][data-permission-key]').forEach(el => {
                if (el.checked) {
                    const key = String(el.dataset.permissionKey || '').trim();
                    if (key) output.push(key);
                }
            });
            return output;
        }

        function getSelectedSubAccount() {
            const select = document.getElementById('subEditSelect');
            if (!select) return null;
            const name = String(select.value || '').trim();
            if (!name) return null;
            return subAccountsCache.find(item => String(item.username || '').trim() === name) || null;
        }

        function fillSubAccountEditForm(target) {
            const enabledEl = document.getElementById('subEditEnabled');
            const pwdEl = document.getElementById('subEditPassword');
            const notifyMessageEl = document.getElementById('subEditNotifyMessageEmail');
            const notifyJobEl = document.getElementById('subEditNotifyJobEmail');
            const msgEl = document.getElementById('subEditMsg');
            if (msgEl) {
                msgEl.textContent = '';
                msgEl.style.color = '#28a745';
            }
            if (!target) {
                if (enabledEl) enabledEl.checked = true;
                if (pwdEl) pwdEl.value = '';
                if (notifyMessageEl) notifyMessageEl.checked = false;
                if (notifyJobEl) notifyJobEl.checked = false;
                renderPermissionGrid('subEditPermissionsGrid', []);
                return;
            }
            if (enabledEl) enabledEl.checked = target.enabled !== false;
            if (pwdEl) pwdEl.value = '';
            if (notifyMessageEl) notifyMessageEl.checked = target.notify_message_email === true;
            if (notifyJobEl) notifyJobEl.checked = target.notify_job_email === true;
            renderPermissionGrid('subEditPermissionsGrid', Array.isArray(target.permissions) ? target.permissions : []);
        }

        function refreshSubAccountSelect() {
            const select = document.getElementById('subEditSelect');
            if (!select) return;
            const previous = String(select.value || '').trim();
            if (!subAccountsCache.length) {
                select.innerHTML = '<option value="">暂无子账号</option>';
                select.disabled = true;
                fillSubAccountEditForm(null);
                return;
            }
            select.disabled = false;
            select.innerHTML = subAccountsCache.map(item => {
                const name = String(item.username || '').trim();
                const status = item.enabled === false ? '（已禁用）' : '';
                return `<option value="${escapeHtml(name)}">${escapeHtml(name)}${escapeHtml(status)}</option>`;
            }).join('');
            const hasPrevious = subAccountsCache.some(item => String(item.username || '').trim() === previous);
            select.value = hasPrevious ? previous : String(subAccountsCache[0].username || '').trim();
            fillSubAccountEditForm(getSelectedSubAccount());
        }

        function permissionLabelMap() {
            const map = {};
            const catalog = Array.isArray(permissionCatalog) && permissionCatalog.length
                ? permissionCatalog
                : DEFAULT_PERMISSION_CATALOG;
            for (const item of catalog) {
                const key = String((item && item.key) || '').trim();
                if (!key) continue;
                map[key] = String((item && item.label) || key);
            }
            return map;
        }

        function renderSubAccountsTable() {
            const tbody = document.getElementById('subAccountsListBody');
            const countEl = document.getElementById('subAccountsListCount');
            if (!tbody) return;

            if (countEl) {
                countEl.textContent = String(subAccountsCache.length || 0);
            }
            if (!subAccountsCache.length) {
                tbody.innerHTML = '<tr><td colspan="8" class="no-data">暂无子账号</td></tr>';
                return;
            }

            const labelMap = permissionLabelMap();
            tbody.innerHTML = subAccountsCache.map((item) => {
                const username = String(item.username || '').trim();
                const enabled = item.enabled !== false;
                const permissions = Array.isArray(item.permissions)
                    ? item.permissions.map(v => String(v || '').trim()).filter(Boolean)
                    : [];
                const permissionNames = permissions.map(key => labelMap[key] || key);
                const permissionText = permissionNames.length ? permissionNames.join('、') : '无';
                const loginText = item.last_login_at ? (formatChangelogTime(item.last_login_at) || item.last_login_at) : '从未登录';
                const updateText = item.updated_at ? (formatChangelogTime(item.updated_at) || item.updated_at) : '-';
                const statusText = enabled ? '启用' : '禁用';
                const statusColor = enabled ? '#16a34a' : '#dc2626';
                const notifyMessageText = item.notify_message_email === true ? '接收' : '关闭';
                const notifyMessageColor = item.notify_message_email === true ? '#16a34a' : '#64748b';
                const notifyJobText = item.notify_job_email === true ? '接收' : '关闭';
                const notifyJobColor = item.notify_job_email === true ? '#16a34a' : '#64748b';

                return `
                    <tr>
                        <td>${escapeHtml(username)}</td>
                        <td><span style="font-weight:700; color:${statusColor};">${statusText}</span></td>
                        <td title="${escapeHtml(permissionText)}" style="max-width: 360px;">${escapeHtml(permissionText)}</td>
                        <td><span style="font-weight:700; color:${notifyMessageColor};">${notifyMessageText}</span></td>
                        <td><span style="font-weight:700; color:${notifyJobColor};">${notifyJobText}</span></td>
                        <td>${escapeHtml(loginText)}</td>
                        <td>${escapeHtml(updateText)}</td>
                        <td>
                            <button type="button" class="btn-sm sub-account-edit-btn" data-username="${escapeHtml(username)}">编辑</button>
                        </td>
                    </tr>
                `;
            }).join('');

            tbody.querySelectorAll('.sub-account-edit-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const username = String(btn.dataset.username || '').trim();
                    if (!username) return;
                    const select = document.getElementById('subEditSelect');
                    if (select) {
                        select.value = username;
                        select.dispatchEvent(new Event('change'));
                    }
                    document.getElementById('subAccountEditForm')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                });
            });
        }

        async function loadSubAccounts() {
            syncSubAccountManageVisibility();
            renderPermissionGrid('subCreatePermissionsGrid', ['messages']);
            if (!currentAdminAuth.is_super_admin) {
                subAccountsCache = [];
                refreshSubAccountSelect();
                renderSubAccountsTable();
                return;
            }

            const msgCreate = document.getElementById('subCreateMsg');
            const msgEdit = document.getElementById('subEditMsg');
            if (msgCreate) {
                msgCreate.textContent = '';
                msgCreate.style.color = '#28a745';
            }
            if (msgEdit) {
                msgEdit.textContent = '';
                msgEdit.style.color = '#28a745';
            }

            try {
                const res = await fetch('/api/admin/subaccounts', { cache: 'no-store' });
                const data = await parseJsonSafe(res);
                if (!res.ok || !data.success) {
                    throw new Error(data.message || '子账号列表加载失败');
                }
                if (Array.isArray(data.permission_catalog) && data.permission_catalog.length) {
                    permissionCatalog = data.permission_catalog
                        .map(item => ({
                            key: String((item && item.key) || '').trim(),
                            label: String((item && item.label) || '').trim()
                        }))
                        .filter(item => item.key);
                }
                subAccountsCache = Array.isArray(data.items) ? data.items : [];
                renderPermissionGrid('subCreatePermissionsGrid', ['messages']);
                refreshSubAccountSelect();
                renderSubAccountsTable();
            } catch (e) {
                if (msgEdit) {
                    msgEdit.style.color = '#dc3545';
                    msgEdit.textContent = String(e.message || '子账号列表加载失败');
                }
                subAccountsCache = [];
                refreshSubAccountSelect();
                renderSubAccountsTable();
            }
        }

        const subAccountCreateForm = document.getElementById('subAccountCreateForm');
        if (subAccountCreateForm) {
            subAccountCreateForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!currentAdminAuth.is_super_admin) return;
                const btn = e.target.querySelector('button[type="submit"]');
                const msg = document.getElementById('subCreateMsg');
                const username = String(document.getElementById('subCreateUsername')?.value || '').trim();
                const password = String(document.getElementById('subCreatePassword')?.value || '');
                const enabled = !!document.getElementById('subCreateEnabled')?.checked;
                const notifyMessageEmail = !!document.getElementById('subCreateNotifyMessageEmail')?.checked;
                const notifyJobEmail = !!document.getElementById('subCreateNotifyJobEmail')?.checked;
                const permissions = readPermissionGrid('subCreatePermissionsGrid');

                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#dc3545';
                }
                if (!username || !password) {
                    if (msg) msg.textContent = '用户名和密码不能为空';
                    return;
                }
                if (permissions.length === 0) {
                    if (msg) msg.textContent = '请至少选择 1 项权限';
                    return;
                }

                if (btn) btn.disabled = true;
                try {
                    const res = await fetch('/api/admin/subaccounts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            username,
                            password,
                            enabled,
                            permissions,
                            notify_message_email: notifyMessageEmail,
                            notify_job_email: notifyJobEmail
                        })
                    });
                    const data = await parseJsonSafe(res);
                    if (!res.ok || !data.success) {
                        throw new Error(data.message || '创建失败');
                    }
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '子账号创建成功';
                    }
                    e.target.reset();
                    renderPermissionGrid('subCreatePermissionsGrid', ['messages']);
                    await loadSubAccounts();
                } catch (err) {
                    if (msg) msg.textContent = String(err.message || '创建失败');
                } finally {
                    if (btn) btn.disabled = false;
                }
            });
        }

        const subEditSelectEl = document.getElementById('subEditSelect');
        if (subEditSelectEl) {
            subEditSelectEl.addEventListener('change', () => {
                fillSubAccountEditForm(getSelectedSubAccount());
            });
        }

        const subAccountEditForm = document.getElementById('subAccountEditForm');
        if (subAccountEditForm) {
            subAccountEditForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                if (!currentAdminAuth.is_super_admin) return;
                const target = getSelectedSubAccount();
                const msg = document.getElementById('subEditMsg');
                const btn = e.target.querySelector('button[type="submit"]');
                if (!target) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '请先选择子账号';
                    }
                    return;
                }

                const enabled = !!document.getElementById('subEditEnabled')?.checked;
                const password = String(document.getElementById('subEditPassword')?.value || '');
                const notifyMessageEmail = !!document.getElementById('subEditNotifyMessageEmail')?.checked;
                const notifyJobEmail = !!document.getElementById('subEditNotifyJobEmail')?.checked;
                const permissions = readPermissionGrid('subEditPermissionsGrid');
                if (permissions.length === 0) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '请至少选择 1 项权限';
                    }
                    return;
                }

                if (msg) {
                    msg.textContent = '';
                    msg.style.color = '#dc3545';
                }
                if (btn) btn.disabled = true;
                try {
                    const res = await fetch(`/api/admin/subaccounts/${encodeURIComponent(target.username)}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            enabled,
                            permissions,
                            password,
                            notify_message_email: notifyMessageEmail,
                            notify_job_email: notifyJobEmail
                        })
                    });
                    const data = await parseJsonSafe(res);
                    if (!res.ok || !data.success) {
                        throw new Error(data.message || '保存失败');
                    }
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '子账号更新成功';
                    }
                    await loadSubAccounts();
                } catch (err) {
                    if (msg) msg.textContent = String(err.message || '保存失败');
                } finally {
                    if (btn) btn.disabled = false;
                }
            });
        }

        const subDeleteBtn = document.getElementById('subDeleteBtn');
        if (subDeleteBtn) {
            subDeleteBtn.addEventListener('click', async () => {
                if (!currentAdminAuth.is_super_admin) return;
                const target = getSelectedSubAccount();
                const msg = document.getElementById('subEditMsg');
                if (!target) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = '请先选择子账号';
                    }
                    return;
                }
                const ok = await showGlobalConfirm(`确定删除子账号 "${target.username}" 吗？此操作无法撤销。`);
                if (!ok) return;
                try {
                    const res = await fetch(`/api/admin/subaccounts/${encodeURIComponent(target.username)}`, {
                        method: 'DELETE'
                    });
                    const data = await parseJsonSafe(res);
                    if (!res.ok || !data.success) {
                        throw new Error(data.message || '删除失败');
                    }
                    if (msg) {
                        msg.style.color = '#28a745';
                        msg.textContent = '子账号已删除';
                    }
                    await loadSubAccounts();
                } catch (err) {
                    if (msg) {
                        msg.style.color = '#dc3545';
                        msg.textContent = String(err.message || '删除失败');
                    }
                }
            });
        }

        const subRefreshBtn = document.getElementById('subRefreshBtn');
        if (subRefreshBtn) {
            subRefreshBtn.addEventListener('click', async () => {
                await loadSubAccounts();
            });
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // --- Chatbot Config Logic ---
        function switchChatbotTab(tabName, btn) {
            document.querySelectorAll('#view-chatbot .tab-btn').forEach(el => el.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('#view-chatbot .tab-content').forEach(el => el.classList.remove('active'));
            const tab = document.getElementById(`chatbot-tab-${tabName}`);
            if (tab) {
                tab.classList.add('active');
                renderTabGuide(tab);
            }

            if (tabName === 'knowledge') loadKnowledgeFiles();
            if (tabName === 'product-ai') loadProductPageAiConfig();
            if (tabName === 'history') loadChatbotConversationLogs();
        }

        async function loadChatbotConfig() {
            try {
                const res = await fetch('/api/chatbot/config');
                const config = await res.json();

                document.getElementById('chatbotEnabled').checked = config.enabled !== false;
                document.getElementById('chatbotApiKey').placeholder = config.api_key || 'sk-...';
                document.getElementById('chatbotApiBase').value = config.api_base || 'https://api.openai.com/v1';
                document.getElementById('chatbotModel').value = config.model || 'gpt-3.5-turbo';

                updateStatusIndicator(config.enabled !== false);
                loadProductPageAiConfig();

                // Also load knowledge files
                loadKnowledgeFiles();
                if (document.getElementById('chatbot-tab-history')?.classList.contains('active')) {
                    loadChatbotConversationLogs();
                }
            } catch (e) {
                console.error('Failed to load chatbot config:', e);
            }
        }

        function updateStatusIndicator(enabled) {
            const status = document.getElementById('chatbotStatus');
            if (enabled) {
                status.className = 'status-indicator enabled';
                status.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i><span>已启用</span>';
            } else {
                status.className = 'status-indicator disabled';
                status.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i><span>已禁用</span>';
            }
        }

        document.getElementById('chatbotEnabled').addEventListener('change', function () {
            updateStatusIndicator(this.checked);
        });

        function updateProductAiStatusIndicator(enabled) {
            const status = document.getElementById('productAiStatus');
            if (!status) return;
            if (enabled) {
                status.className = 'status-indicator enabled';
                status.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i><span>已启用</span>';
            } else {
                status.className = 'status-indicator disabled';
                status.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i><span>已禁用</span>';
            }
        }

        async function loadProductPageAiConfig() {
            try {
                const res = await fetch('/api/product-ai/config');
                const config = await res.json();
                const enabled = config.enabled === true;
                const id = (x) => document.getElementById(x);
                id('productAiEnabled').checked = enabled;
                id('productAiApiKey').placeholder = config.api_key || 'sk-...';
                id('productAiApiBase').value = config.api_base || 'https://api.openai.com/v1';
                id('productAiModel').value = config.model || 'gpt-4o-mini';
                updateProductAiStatusIndicator(enabled);
            } catch (e) {
                console.error('Failed to load product AI config:', e);
            }
        }

        document.getElementById('productAiEnabled').addEventListener('change', function () {
            updateProductAiStatusIndicator(this.checked);
        });

        document.getElementById('productAiConfigForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            const msg = document.getElementById('productAiConfigMsg');
            const apiKeyInput = document.getElementById('productAiApiKey');
            const apiKey = apiKeyInput.value.trim();

            btn.disabled = true;
            msg.textContent = '';
            msg.style.color = '#dc3545';

            try {
                const res = await fetch('/api/product-ai/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: document.getElementById('productAiEnabled').checked,
                        api_key: apiKey || undefined,
                        api_base: document.getElementById('productAiApiBase').value,
                        model: document.getElementById('productAiModel').value
                    })
                });
                const data = await res.json();
                if (data.success) {
                    msg.style.color = '#28a745';
                    msg.textContent = '产品页编程 AI 配置保存成功！';
                    apiKeyInput.value = '';
                    loadProductPageAiConfig();
                } else {
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e2) {
                msg.textContent = '网络错误';
            } finally {
                btn.disabled = false;
            }
        });

        document.getElementById('chatbotConfigForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = e.target.querySelector('button');
            const msg = document.getElementById('chatbotConfigMsg');

            btn.disabled = true;
            msg.textContent = '';
            msg.style.color = '#dc3545';

            const apiKeyInput = document.getElementById('chatbotApiKey');
            const apiKey = apiKeyInput.value.trim();

            try {
                const res = await fetch('/api/chatbot/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: document.getElementById('chatbotEnabled').checked,
                        api_key: apiKey || undefined,
                        api_base: document.getElementById('chatbotApiBase').value,
                        model: document.getElementById('chatbotModel').value
                    })
                });
                const data = await res.json();

                if (data.success) {
                    msg.style.color = '#28a745';
                    msg.textContent = '配置保存成功！';
                    apiKeyInput.value = '';
                    loadChatbotConfig();
                } else {
                    msg.textContent = data.message || '保存失败';
                }
            } catch (e) {
                msg.textContent = '网络错误';
            } finally {
                btn.disabled = false;
            }
        });

        // --- Knowledge Base Logic ---
        async function loadKnowledgeFiles() {
            const textInput = document.getElementById('knowledgeTextInput');
            const statusEl = document.getElementById('knowledgeTextStatus');
            const listEl = document.getElementById('knowledgeFileList');
            const pendingListEl = document.getElementById('knowledgePendingFileList');
            if (!textInput || !listEl) return;

            listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">加载中...</div>';
            if (pendingListEl && !pendingKnowledgeFiles.length) {
                pendingListEl.innerHTML = '';
            }

            try {
                const res = await fetch('/api/chatbot/knowledge');
                const data = await res.json();

                document.getElementById('pdfSupportWarning').style.display = data.pdf_support ? 'none' : 'block';
                textInput.value = data.text_content || '';

                if (statusEl) {
                    if (data.text_size > 0) {
                        const modifiedText = data.text_modified ? `，最后更新：${formatDateTime(data.text_modified)}` : '';
                        statusEl.textContent = `当前已保存文本知识库 ${formatFileSize(data.text_size)}${modifiedText}`;
                    } else {
                        statusEl.textContent = '当前未保存文本知识库内容';
                    }
                }

                if (!Array.isArray(data.files) || data.files.length === 0) {
                    listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">暂无知识库文件</div>';
                } else {
                    listEl.innerHTML = data.files.map(file => `
                        <div class="file-item">
                            <div class="file-info">
                                <i class="fas fa-file-pdf"></i>
                                <div>
                                    <div style="font-weight: 500;">${escapeHtml(file.name)}</div>
                                    <div class="file-meta">${formatFileSize(file.size)} · ${formatDateTime(file.modified)}</div>
                                </div>
                            </div>
                            <div style="display:flex; gap:8px; flex-wrap:wrap;">
                                <button type="button" class="btn-sm knowledge-download-btn" data-filename="${escapeAttr(file.name)}">
                                    <i class="fas fa-download"></i> 下载
                                </button>
                                <button type="button" class="btn-sm btn-danger knowledge-delete-btn" data-filename="${escapeAttr(file.name)}">
                                    <i class="fas fa-trash"></i> 删除
                                </button>
                            </div>
                        </div>
                    `).join('');

                    listEl.querySelectorAll('.knowledge-download-btn').forEach(btn => {
                        btn.addEventListener('click', () => downloadKnowledgeFile(btn.dataset.filename || ''));
                    });
                    listEl.querySelectorAll('.knowledge-delete-btn').forEach(btn => {
                        btn.addEventListener('click', () => deleteKnowledgeFile(btn.dataset.filename || ''));
                    });
                }

                renderPendingKnowledgeFiles();
            } catch (e) {
                listEl.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">加载失败</div>';
            }
        }

        function formatFileSize(bytes) {
            if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function formatDateTime(isoString) {
            if (!isoString) return '-';
            return String(isoString).replace('T', ' ').slice(0, 16);
        }

        async function deleteKnowledgeFile(filename) {
            if (!await showGlobalConfirm(`确定删除文件 "${filename}" 吗？此操作无法撤销。`)) return;

            try {
                const res = await fetch(`/api/chatbot/knowledge/${encodeURIComponent(filename)}`, { method: 'DELETE' });
                if (res.ok) {
                    loadKnowledgeFiles();
                } else {
                    alert('删除失败');
                }
            } catch (e) {
                alert('网络错误');
            }
        }

        function downloadKnowledgeFile(filename) {
            if (!filename) return;
            window.open(`/api/chatbot/knowledge/${encodeURIComponent(filename)}/download`, '_blank');
        }

        function setKnowledgeUploadMessage(message, type = 'success') {
            const msgEl = document.getElementById('knowledgeUploadMsg');
            if (!msgEl) return;
            msgEl.textContent = message || '';
            msgEl.style.color = type === 'error' ? '#dc3545' : (type === 'warning' ? '#c05621' : '#28a745');
        }

        function renderPendingKnowledgeFiles() {
            const pendingListEl = document.getElementById('knowledgePendingFileList');
            if (!pendingListEl) return;
            if (!pendingKnowledgeFiles.length) {
                pendingListEl.innerHTML = '';
                return;
            }

            pendingListEl.innerHTML = `
                <div style="margin-bottom: 10px; color: #666; font-size: 13px;">待保存 PDF 文件（${pendingKnowledgeFiles.length}）</div>
                ${pendingKnowledgeFiles.map((file, index) => `
                    <div class="file-item">
                        <div class="file-info">
                            <i class="fas fa-file-pdf"></i>
                            <div>
                                <div style="font-weight: 500;">${escapeHtml(file.name)}</div>
                                <div class="file-meta">${formatFileSize(file.size)}</div>
                            </div>
                        </div>
                        <div style="display:flex; gap:8px; flex-wrap:wrap;">
                            <button type="button" class="btn-sm btn-danger knowledge-pending-remove-btn" data-index="${index}">
                                <i class="fas fa-times"></i> 移除
                            </button>
                        </div>
                    </div>
                `).join('')}
            `;

            pendingListEl.querySelectorAll('.knowledge-pending-remove-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const index = Number(btn.dataset.index);
                    if (!Number.isInteger(index)) return;
                    pendingKnowledgeFiles.splice(index, 1);
                    renderPendingKnowledgeFiles();
                });
            });
        }

        function addPendingKnowledgeFiles(fileList) {
            const files = Array.from(fileList || []);
            if (!files.length) return;

            const added = [];
            const skipped = [];
            files.forEach(file => {
                if (!file || !file.name) return;
                if (!file.name.toLowerCase().endsWith('.pdf')) {
                    skipped.push(`${file.name} 不是 PDF 文件`);
                    return;
                }
                const exists = pendingKnowledgeFiles.some(item =>
                    item.name === file.name
                    && item.size === file.size
                    && item.lastModified === file.lastModified
                );
                if (exists) {
                    skipped.push(`${file.name} 已在待上传列表中`);
                    return;
                }
                added.push(file);
            });

            if (added.length) {
                pendingKnowledgeFiles = pendingKnowledgeFiles.concat(added);
                renderPendingKnowledgeFiles();
                setKnowledgeUploadMessage(`已加入 ${added.length} 个待保存 PDF 文件`, 'success');
            }
            if (skipped.length) {
                setKnowledgeUploadMessage(skipped.join('；'), added.length ? 'warning' : 'error');
            }
        }

        async function saveKnowledgeBase() {
            const textInput = document.getElementById('knowledgeTextInput');
            const fileInput = document.getElementById('knowledgeFileInput');
            const saveBtn = document.getElementById('knowledgeSaveBtn');
            const progress = document.getElementById('uploadProgress');
            const progressLabel = progress ? progress.querySelector('span') : null;
            if (!textInput || !saveBtn || !progress) return;

            setKnowledgeUploadMessage('');
            progress.style.display = 'block';
            saveBtn.disabled = true;
            if (progressLabel) {
                progressLabel.textContent = pendingKnowledgeFiles.length ? '正在保存文本与 PDF...' : '正在保存文本...';
            }

            try {
                const formData = new FormData();
                formData.append('knowledge_text', textInput.value || '');
                pendingKnowledgeFiles.forEach(file => formData.append('files', file));

                const res = await fetch('/api/chatbot/knowledge/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();

                if (!res.ok || !data.success) {
                    const details = Array.isArray(data.failed) && data.failed.length
                        ? `：${data.failed.map(item => `${item.filename || '文本'} ${item.message}`).join('；')}`
                        : '';
                    setKnowledgeUploadMessage(`${data.message || '保存失败'}${details}`, 'error');
                    return;
                }

                pendingKnowledgeFiles = [];
                await loadKnowledgeFiles();
                if (fileInput) fileInput.value = '';
                setKnowledgeUploadMessage(data.message || '知识库保存成功', data.partial_success ? 'warning' : 'success');
            } catch (e) {
                setKnowledgeUploadMessage('保存失败：网络错误', 'error');
            } finally {
                progress.style.display = 'none';
                if (progressLabel) {
                    progressLabel.textContent = '正在保存...';
                }
                saveBtn.disabled = false;
            }
        }

        // File upload handling
        const knowledgeUploadZone = document.getElementById('knowledgeUploadZone');
        const knowledgeFileInput = document.getElementById('knowledgeFileInput');
        const knowledgeSaveBtn = document.getElementById('knowledgeSaveBtn');

        if (knowledgeUploadZone && knowledgeFileInput) {
            knowledgeUploadZone.addEventListener('click', () => knowledgeFileInput.click());

            knowledgeUploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                knowledgeUploadZone.classList.add('dragover');
            });

            knowledgeUploadZone.addEventListener('dragleave', () => {
                knowledgeUploadZone.classList.remove('dragover');
            });

            knowledgeUploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                knowledgeUploadZone.classList.remove('dragover');
                addPendingKnowledgeFiles(e.dataTransfer.files);
            });

            knowledgeFileInput.addEventListener('change', () => {
                addPendingKnowledgeFiles(knowledgeFileInput.files);
                knowledgeFileInput.value = '';
            });
        }

        if (knowledgeSaveBtn) {
            knowledgeSaveBtn.addEventListener('click', saveKnowledgeBase);
        }
    
        function copyToClipboard(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
            }
        }

        // --- CDN Assets Functions ---
        let cdnAssetsData = [];
        let cdnSettings = { cdn_enabled: false, cdn_domain: '' };
        let cdnCurrentPath = '';

        function loadCdnAssets(path) {
            if (typeof path === 'string') cdnCurrentPath = path;
            const qs = cdnCurrentPath ? `?path=${encodeURIComponent(cdnCurrentPath)}` : '';
            fetch(`/api/cdn/assets/list${qs}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        cdnAssetsData = data.files || [];
                        cdnSettings = data.cdn_settings || { cdn_enabled: false, cdn_domain: '' };
                        cdnCurrentPath = data.current_path || '';
                        renderCdnBreadcrumb(data.breadcrumb || []);
                        renderCdnAssets();
                        updateCdnStatus();
                    } else {
                        showGlobalAlert('加载CDN素材失败: ' + (data.message || '未知错误'));
                    }
                })
                .catch(err => {
                    console.error('Load CDN assets error:', err);
                    showGlobalAlert('加载CDN素材失败');
                });
        }

        function renderCdnBreadcrumb(breadcrumb) {
            const el = document.getElementById('cdnBreadcrumb');
            if (!el) return;
            let html = `<span style="cursor:pointer;color:#60a5fa;font-weight:600;" onclick="loadCdnAssets('')"><i class="fas fa-home" style="margin-right:3px;"></i>cdn_assets</span>`;
            if (breadcrumb && breadcrumb.length) {
                breadcrumb.forEach((item, i) => {
                    html += `<span style="color:#666;margin:0 2px;">/</span>`;
                    if (i < breadcrumb.length - 1) {
                        html += `<span style="cursor:pointer;color:#60a5fa;" onclick="loadCdnAssets('${escapeHtml(item.path)}')">${escapeHtml(item.name)}</span>`;
                    } else {
                        html += `<span style="font-weight:600;">${escapeHtml(item.name)}</span>`;
                    }
                });
            }
            el.innerHTML = html;
        }

        function updateCdnStatus() {
            const badge = document.getElementById('cdnStatusBadge');
            const domainDisplay = document.getElementById('cdnDomainDisplay');
            if (!badge) return;

            if (cdnSettings.cdn_enabled && cdnSettings.cdn_domain) {
                badge.textContent = '已启用';
                badge.style.background = '#166534';
                badge.style.color = '#4ade80';
                domainDisplay.textContent = cdnSettings.cdn_domain;
            } else {
                badge.textContent = '未启用';
                badge.style.background = '#44403c';
                badge.style.color = '#a8a29e';
                domainDisplay.textContent = '(使用本地路径)';
            }
        }

        function renderCdnAssets() {
            const tbody = document.getElementById('cdnAssetsTableBody');
            const fileCountEl = document.getElementById('cdnFileCount');
            const totalSizeEl = document.getElementById('cdnTotalSize');

            if (!cdnAssetsData.length) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:30px;color:#888;">此目录为空</td></tr>';
                fileCountEl.textContent = '0';
                totalSizeEl.textContent = '0 KB';
                return;
            }

            let totalSize = 0;
            let html = '';

            cdnAssetsData.forEach(file => {
                if (file.type === 'file') totalSize += file.size;

                const itemPath = cdnCurrentPath ? `${cdnCurrentPath}/${file.name}` : file.name;
                const escapedPath = escapeHtml(itemPath);
                const escapedName = escapeHtml(file.name);

                html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">';

                // Name column
                if (file.type === 'folder') {
                    html += `<td style="padding:10px 12px;cursor:pointer;" onclick="loadCdnAssets('${escapedPath}')">
                        <i class="fas fa-folder" style="color:#facc15;margin-right:6px;"></i>
                        <span style="color:#60a5fa;text-decoration:underline;">${escapedName}</span>
                        <span style="color:#888;font-size:12px;margin-left:6px;">(${file.children || 0} 项)</span>
                    </td>`;
                } else {
                    const previewable = isCdnPreviewable(file.name);
                    if (previewable) {
                        html += `<td style="padding:10px 12px;cursor:pointer;" onclick="previewCdnFile('${escapedPath}', '${escapedName}')">
                            <i class="fas ${getCdnFileIcon(file.name)}" style="color:#94a3b8;margin-right:6px;"></i>
                            <span style="color:#60a5fa;">${escapedName}</span>
                        </td>`;
                    } else {
                        html += `<td style="padding:10px 12px;">
                            <i class="fas ${getCdnFileIcon(file.name)}" style="color:#94a3b8;margin-right:6px;"></i>
                            ${escapedName}
                        </td>`;
                    }
                }

                // Type column
                const typeLabel = file.type === 'folder' ? '文件夹' : getFileTypeLabel(file.name);
                html += `<td style="padding:10px 12px;"><span style="font-size:12px;padding:2px 8px;border-radius:4px;background:rgba(255,255,255,0.06);">${typeLabel}</span></td>`;

                // Size column
                html += `<td style="padding:10px 12px;">${file.type === 'folder' ? '-' : formatFileSize(file.size)}</td>`;

                // Modified column
                html += `<td style="padding:10px 12px;font-size:12px;color:#888;">${file.modified}</td>`;

                // Actions column
                html += '<td style="padding:10px 12px;text-align:center;white-space:nowrap;">';
                if (file.type === 'file') {
                    if (isCdnPreviewable(file.name)) {
                        html += `<button class="action-btn" onclick="previewCdnFile('${escapedPath}', '${escapedName}')" title="预览" style="padding:4px 8px;margin:0 2px;border:none;border-radius:4px;cursor:pointer;background:rgba(168,85,247,0.15);color:#a855f7;font-size:12px;"><i class="fas fa-eye"></i></button>`;
                    }
                    html += `<button class="action-btn primary" onclick="copyCdnUrl('${escapedPath}')" title="复制链接" style="padding:4px 8px;margin:0 2px;border:none;border-radius:4px;cursor:pointer;background:rgba(96,165,250,0.15);color:#60a5fa;font-size:12px;"><i class="fas fa-link"></i></button>`;
                    html += `<button class="action-btn primary" onclick="downloadCdnFile('${escapedPath}')" title="下载" style="padding:4px 8px;margin:0 2px;border:none;border-radius:4px;cursor:pointer;background:rgba(96,165,250,0.15);color:#60a5fa;font-size:12px;"><i class="fas fa-download"></i></button>`;
                }
                html += `<button class="action-btn secondary" onclick="renameCdnFile('${escapedPath}', '${escapedName}')" title="重命名" style="padding:4px 8px;margin:0 2px;border:none;border-radius:4px;cursor:pointer;background:rgba(255,255,255,0.08);color:#ccc;font-size:12px;"><i class="fas fa-edit"></i></button>`;
                html += `<button class="action-btn danger" onclick="deleteCdnFile('${escapedPath}', '${escapedName}')" title="删除" style="padding:4px 8px;margin:0 2px;border:none;border-radius:4px;cursor:pointer;background:rgba(239,68,68,0.15);color:#ef4444;font-size:12px;"><i class="fas fa-trash"></i></button>`;
                html += '</td></tr>';
            });

            tbody.innerHTML = html;
            fileCountEl.textContent = cdnAssetsData.length;
            totalSizeEl.textContent = formatFileSize(totalSize);
        }

        function getCdnFileIcon(filename) {
            const ext = (filename.split('.').pop() || '').toLowerCase();
            const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico'];
            const videoExts = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'];
            const docExts = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md'];
            if (imageExts.includes(ext)) return 'fa-file-image';
            if (videoExts.includes(ext)) return 'fa-file-video';
            if (docExts.includes(ext)) return 'fa-file-alt';
            return 'fa-file';
        }

        function getFileTypeLabel(filename) {
            return (filename.split('.').pop() || '').toUpperCase();
        }

        function formatFileSize(bytes) {
            if (!bytes || bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }

        function handleCdnFileUpload(input) {
            const files = input.files;
            if (!files.length) return;

            let uploaded = 0;
            let failed = 0;

            Array.from(files).forEach(file => {
                const formData = new FormData();
                formData.append('file', file);
                if (cdnCurrentPath) formData.append('path', cdnCurrentPath);

                fetch('/api/cdn/assets/upload', {
                    method: 'POST',
                    body: formData
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) uploaded++;
                    else failed++;
                    if (uploaded + failed === files.length) {
                        showGlobalAlert(failed === 0
                            ? `成功上传 ${uploaded} 个文件`
                            : `成功 ${uploaded} 个，失败 ${failed} 个`);
                        loadCdnAssets();
                        input.value = '';
                    }
                })
                .catch(() => {
                    failed++;
                    if (uploaded + failed === files.length) {
                        showGlobalAlert(`成功 ${uploaded} 个，失败 ${failed} 个`);
                        loadCdnAssets();
                        input.value = '';
                    }
                });
            });
        }

        function cdnCreateFolder() {
            const name = prompt('请输入文件夹名称：');
            if (!name || !name.trim()) return;

            fetch('/api/cdn/assets/mkdir', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: cdnCurrentPath, name: name.trim() })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showGlobalAlert('文件夹创建成功');
                    loadCdnAssets();
                } else {
                    showGlobalAlert('创建失败: ' + data.message);
                }
            })
            .catch(() => showGlobalAlert('创建失败'));
        }

        function copyCdnUrl(filePath) {
            fetch(`/api/cdn/assets/url?path=${encodeURIComponent(filePath)}`)
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        copyToClipboard(data.full_url);
                        showGlobalAlert('链接已复制：' + data.full_url);
                    } else {
                        showGlobalAlert('获取链接失败: ' + data.message);
                    }
                })
                .catch(() => showGlobalAlert('获取链接失败'));
        }

        function downloadCdnFile(filePath) {
            window.location.href = `/api/cdn/assets/download/${encodeURIComponent(filePath)}`;
        }

        function renameCdnFile(filePath, oldName) {
            const newName = prompt('请输入新名称：', oldName);
            if (!newName || newName === oldName) return;

            fetch('/api/cdn/assets/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ old_path: filePath, new_name: newName })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showGlobalAlert('重命名成功');
                    loadCdnAssets();
                } else {
                    showGlobalAlert('重命名失败: ' + data.message);
                }
            })
            .catch(() => showGlobalAlert('重命名失败'));
        }

        async function deleteCdnFile(filePath, name) {
            const ok = await showGlobalConfirm(`确定要删除 "${name}" 吗？此操作不可恢复。`);
            if (!ok) return;

            fetch('/api/cdn/assets/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showGlobalAlert('删除成功');
                    loadCdnAssets();
                } else {
                    showGlobalAlert('删除失败: ' + data.message);
                }
            })
            .catch(() => showGlobalAlert('删除失败'));
        }

        // --- CDN Preview ---
        let _cdnPreviewPath = '';

        const _cdnImageExts = ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico', 'avif'];
        const _cdnVideoExts = ['mp4', 'webm', 'mov', 'ogg'];
        const _cdnDocExts = ['pdf'];
        const _cdnTextExts = ['txt', 'md', 'json', 'csv', 'xml', 'html', 'css', 'js', 'py', 'sh', 'log', 'yml', 'yaml'];

        function isCdnPreviewable(filename) {
            const ext = (filename.split('.').pop() || '').toLowerCase();
            return _cdnImageExts.includes(ext) || _cdnVideoExts.includes(ext) || _cdnDocExts.includes(ext) || _cdnTextExts.includes(ext);
        }

        function _cdnFileCategory(filename) {
            const ext = (filename.split('.').pop() || '').toLowerCase();
            if (_cdnImageExts.includes(ext)) return 'image';
            if (_cdnVideoExts.includes(ext)) return 'video';
            if (_cdnDocExts.includes(ext)) return 'pdf';
            if (_cdnTextExts.includes(ext)) return 'text';
            return 'unknown';
        }

        function previewCdnFile(filePath, fileName) {
            _cdnPreviewPath = filePath;
            const overlay = document.getElementById('cdnPreviewOverlay');
            const content = document.getElementById('cdnPreviewContent');
            const nameEl = document.getElementById('cdnPreviewFileName');
            if (!overlay || !content) return;

            nameEl.textContent = fileName || filePath;
            const url = `/cdn_assets/${filePath}`;
            const category = _cdnFileCategory(fileName || filePath);

            let html = '';
            switch (category) {
                case 'image':
                    html = `<img src="${url}" alt="${escapeHtml(fileName)}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.4);user-select:none;" ondragstart="return false" />`;
                    break;
                case 'video':
                    html = `<video src="${url}" controls autoplay style="max-width:100%;max-height:100%;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,0.4);outline:none;"></video>`;
                    break;
                case 'pdf':
                    html = `<iframe src="${url}" style="width:100%;height:100%;border:none;border-radius:8px;background:#fff;"></iframe>`;
                    break;
                case 'text':
                    html = `<div id="cdnTextPreviewBox" style="width:100%;max-width:900px;max-height:100%;overflow:auto;background:#1e1e2e;color:#cdd6f4;padding:24px;border-radius:10px;font-family:'Fira Code',Consolas,Monaco,monospace;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-word;box-shadow:0 8px 32px rgba(0,0,0,0.4);"><span style="color:#888;">加载中...</span></div>`;
                    break;
                default:
                    html = `<div style="text-align:center;color:#888;"><i class="fas fa-file" style="font-size:48px;margin-bottom:16px;display:block;"></i>此文件类型不支持预览</div>`;
            }

            content.innerHTML = html;
            overlay.style.display = 'block';
            document.body.style.overflow = 'hidden';
            document.addEventListener('keydown', _cdnPreviewKeyHandler);

            // Load text content async
            if (category === 'text') {
                fetch(url)
                    .then(res => {
                        if (!res.ok) throw new Error('加载失败');
                        return res.text();
                    })
                    .then(text => {
                        const box = document.getElementById('cdnTextPreviewBox');
                        if (box) {
                            // Truncate very large files
                            const maxLen = 200000;
                            let displayText = text.length > maxLen ? text.substring(0, maxLen) + '\n\n... (文件过大，仅显示前 200KB)' : text;
                            box.textContent = displayText;
                        }
                    })
                    .catch(() => {
                        const box = document.getElementById('cdnTextPreviewBox');
                        if (box) box.innerHTML = '<span style="color:#f38ba8;">加载失败</span>';
                    });
            }
        }

        function closeCdnPreview(event) {
            if (event && event.target && event.target.id !== 'cdnPreviewOverlay') return;
            const overlay = document.getElementById('cdnPreviewOverlay');
            const content = document.getElementById('cdnPreviewContent');
            if (overlay) overlay.style.display = 'none';
            if (content) {
                // Stop any playing video
                const video = content.querySelector('video');
                if (video) { video.pause(); video.src = ''; }
                content.innerHTML = '';
            }
            document.body.style.overflow = '';
            document.removeEventListener('keydown', _cdnPreviewKeyHandler);
            _cdnPreviewPath = '';
        }

        function _cdnPreviewKeyHandler(e) {
            if (e.key === 'Escape') closeCdnPreview();
        }

        function cdnPreviewCopyUrl() {
            if (!_cdnPreviewPath) return;
            copyCdnUrl(_cdnPreviewPath);
        }

        function cdnPreviewDownload() {
            if (!_cdnPreviewPath) return;
            downloadCdnFile(_cdnPreviewPath);
        }
