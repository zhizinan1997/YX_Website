(function () {
    function isHtmlResponse(response) {
        const contentType = String(response.headers.get('content-type') || '').toLowerCase();
        return contentType.includes('text/html');
    }

    function installGlobalFetchGuard() {
        if (window.__admin2FetchGuardInstalled) return;
        const previousFetch = window.fetch.bind(window);
        window.fetch = async function (input, init) {
            const response = await previousFetch(input, init);
            const url = typeof input === 'string' ? input : String((input && input.url) || '');
            const isAdminRequest = url.startsWith('/admin/') || url.startsWith('/api/');
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
    };
})();
