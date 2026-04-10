(function () {
    function readHashView() {
        const raw = String(window.location.hash || '').trim();
        if (!raw) return '';
        return raw.replace(/^#\/?/, '').trim();
    }

    function writeHashView(viewName) {
        const key = String(viewName || '').trim();
        if (!key) return;
        const nextHash = `#/${key}`;
        if (window.location.hash !== nextHash) {
            history.replaceState(null, '', nextHash);
        }
    }

    function install() {
        if (window.__admin2RouterInstalled) return;
        window.addEventListener('hashchange', () => {
            const viewName = readHashView();
            if (!viewName || !window.Admin2Views || !window.Admin2Views.hasView(viewName)) return;
            if (!document.getElementById(`view-${viewName}`)) return;
            if (typeof window.hasViewPermission === 'function' && !window.hasViewPermission(viewName)) return;
            if (typeof window.switchView === 'function') {
                window.switchView(viewName, { persist: false, hash: false });
            }
        });
        window.__admin2RouterInstalled = true;
    }

    window.Admin2Router = {
        install,
        readHashView,
        writeHashView,
    };
})();
