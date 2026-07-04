(function () {
    const ADMIN_ACTIVITY_WINDOW_MS = 2 * 60 * 1000;
    const ADMIN_ACTIVITY_HEADER = 'X-Admin-User-Active';
    let lastAdminUserActivityAt = 0;

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
        if (!shouldAttachActivityHeader(url)) {
            return { input, init };
        }
        const headers = new Headers(input && input.headers ? input.headers : undefined);
        if (init && init.headers) {
            new Headers(init.headers).forEach((value, key) => headers.set(key, value));
        }
        headers.set(ADMIN_ACTIVITY_HEADER, '1');
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
            const isAdminRequest = isAdminRequestUrl(url);
            if (isAdminRequest && (response.status === 401 || response.redirected || isHtmlResponse(response))) {
                if (window.Admin2Auth && typeof window.Admin2Auth.forceRelogin === 'function') {
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
    };
})();
