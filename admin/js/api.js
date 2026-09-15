(function () {
    const ADMIN_ACTIVITY_WINDOW_MS = 2 * 60 * 1000;
    const ADMIN_ACTIVITY_HEADER = 'X-Admin-User-Active';
    const CSRF_HEADER = 'X-CSRF-Token';
    let lastAdminUserActivityAt = 0;
    let adminCsrfToken = '';

    function isHtmlResponse(response) {
        const contentType = String(response.headers.get('content-type') || '').toLowerCase();
        return contentType.includes('text/html');
    }

    function markUserActivity() {
        lastAdminUserActivityAt = Date.now();
    }

    function installUserActivityTracker() {
        if (window.__admin2UserActivityTrackerInstalled) return;
        const passiveCapture = { capture: true, passive: true };
        document.addEventListener('pointerdown', markUserActivity, passiveCapture);
        document.addEventListener('touchstart', markUserActivity, passiveCapture);
        document.addEventListener('wheel', markUserActivity, passiveCapture);
        document.addEventListener('scroll', markUserActivity, passiveCapture);
        document.addEventListener('keydown', markUserActivity, { capture: true });
        window.__admin2UserActivityTrackerInstalled = true;
    }

    function getRequestUrl(input) {
        if (typeof input === 'string') return input;
        return String((input && input.url) || '');
    }

    function getRequestMethod(input, init) {
        return String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    }

    function rememberCsrfToken(response) {
        const contentType = String(response.headers.get('content-type') || '').toLowerCase();
        if (!contentType.includes('application/json')) return;
        response.clone().json().then((data) => {
            const token = String(data && data.csrf_token || '').trim();
            if (!token) return;
            adminCsrfToken = token;
            window.__adminCsrfToken = token;
        }).catch(() => {});
    }

    function setCsrfToken(token) {
        const value = String(token || '').trim();
        if (!value) return;
        adminCsrfToken = value;
        window.__adminCsrfToken = value;
    }

    function getSameOriginPath(url) {
        try {
            const parsed = new URL(url, window.location.origin);
            if (parsed.origin !== window.location.origin) return '';
            return parsed.pathname || '';
        } catch (_) {
            return '';
        }
    }

    function isAdminRequestUrl(url) {
        const path = getSameOriginPath(url);
        return path === '/admin' || path.startsWith('/admin/') || path.startsWith('/api/');
    }

    function shouldAttachActivityHeader(url) {
        if (!isAdminRequestUrl(url)) return false;
        if (getSameOriginPath(url) === '/admin/logout') return false;
        if (document.visibilityState === 'hidden') return false;
        return lastAdminUserActivityAt > 0 && Date.now() - lastAdminUserActivityAt <= ADMIN_ACTIVITY_WINDOW_MS;
    }

    function withActivityHeader(input, init, url) {
        const method = getRequestMethod(input, init);
        const path = getSameOriginPath(url);
        const shouldAttachCsrf = adminCsrfToken
            && method !== 'GET'
            && method !== 'HEAD'
            && method !== 'OPTIONS'
            && (path.startsWith('/admin/') || path.startsWith('/api/'));
        if (!shouldAttachActivityHeader(url) && !shouldAttachCsrf) {
            return { input, init };
        }
        const headers = new Headers(input && input.headers ? input.headers : undefined);
        if (init && init.headers) {
            new Headers(init.headers).forEach((value, key) => headers.set(key, value));
        }
        if (shouldAttachActivityHeader(url)) headers.set(ADMIN_ACTIVITY_HEADER, '1');
        if (shouldAttachCsrf) headers.set(CSRF_HEADER, adminCsrfToken);
        return {
            input,
            init: Object.assign({}, init || {}, { headers }),
        };
    }

    function installGlobalFetchGuard() {
        if (window.__admin2FetchGuardInstalled) return;
        installUserActivityTracker();
        const previousFetch = window.fetch.bind(window);
        window.fetch = async function (input, init) {
            const url = getRequestUrl(input);
            const requestOptions = withActivityHeader(input, init, url);
            const response = await previousFetch(requestOptions.input, requestOptions.init);
            rememberCsrfToken(response);
            const isAdminRequest = isAdminRequestUrl(url);
            if (isAdminRequest && (response.status === 401 || response.redirected || isHtmlResponse(response))) {
                // 登录页可见时不触发 forceRelogin：未登录状态下某些预查询
                // （如 email-binding 安全引导）返回 401 属预期行为，若触发
                // forceRelogin 会不断 resetLoginTurnstile，导致人机验证
                // “完成几秒后被重置重跑”的循环（2026-09-15 线上现象）。
                const loginPage = document.getElementById('loginPage');
                const loginPageVisible = !!loginPage && loginPage.style.display !== 'none';
                if (!loginPageVisible && window.Admin2Auth && typeof window.Admin2Auth.forceRelogin === 'function') {
                    window.Admin2Auth.forceRelogin('登录已过期，请重新登录。');
                }
            }
            return response;
        };
        window.__admin2FetchGuardInstalled = true;
    }

    window.Admin2Api = {
        installGlobalFetchGuard,
        installUserActivityTracker,
        markUserActivity,
        setCsrfToken,
    };
})();
