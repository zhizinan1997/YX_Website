(function () {
    function updateDocumentTitle(viewName) {
        if (!window.Admin2Views) return;
        const title = window.Admin2Views.getTitle(viewName);
        const suffix = (window.Admin2State && window.Admin2State.titleSuffix) || '管理后台';
        if (title) {
            document.title = `${title} - ${suffix}`;
        }
    }

    function wrapSwitchView() {
        if (window.__admin2SwitchWrapped || typeof window.switchView !== 'function') return;
        const originalSwitchView = window.switchView;
        window.switchView = function (viewName, options) {
            const result = originalSwitchView.call(this, viewName, options);
            if (!options || options.hash !== false) {
                window.Admin2Router && window.Admin2Router.writeHashView(viewName);
            }
            updateDocumentTitle(viewName);
            return result;
        };
        window.__admin2SwitchWrapped = true;
    }

    function wrapShowDashboard() {
        if (window.__admin2DashboardWrapped || typeof window.showDashboard !== 'function') return;
        const originalShowDashboard = window.showDashboard;
        window.showDashboard = function () {
            const result = originalShowDashboard.apply(this, arguments);
            if (window.Admin2Shell) window.Admin2Shell.mount();
            return result;
        };
        window.__admin2DashboardWrapped = true;
    }

    function boot() {
        if (window.Admin2Auth) window.Admin2Auth.decorateLogin();
        if (window.Admin2Api) window.Admin2Api.installGlobalFetchGuard();
        if (window.Admin2Router) window.Admin2Router.install();
        wrapSwitchView();
        wrapShowDashboard();
        if (document.getElementById('dashboard') && document.getElementById('dashboard').style.display !== 'none') {
            if (window.Admin2Shell) window.Admin2Shell.mount();
            const activeView = document.querySelector('.view-section.active');
            if (activeView && activeView.id) {
                updateDocumentTitle(activeView.id.replace(/^view-/, ''));
            }
        }
    }

    window.addEventListener('load', boot);
})();
