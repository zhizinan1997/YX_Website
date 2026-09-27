(function () {
    function decorateLogin() {
        return;
    }

    function forceRelogin(message) {
        const dashboard = document.getElementById('dashboard');
        const loginPage = document.getElementById('loginPage');
        const loginError = document.getElementById('loginError');
        if (dashboard) dashboard.style.display = 'none';
        if (loginPage) loginPage.style.display = 'flex';
        if (loginError) loginError.textContent = message || '登录已过期，请重新登录。';
        if (typeof window.closeAccountMenu === 'function') window.closeAccountMenu();
        if (typeof window.resetLoginTurnstile === 'function') window.resetLoginTurnstile();
        if (typeof window.resetRememberMeFlag === 'function') window.resetRememberMeFlag();
    }

    window.Admin2Auth = {
        decorateLogin,
        forceRelogin,
    };
})();
