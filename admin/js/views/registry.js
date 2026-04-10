(function () {
    const titles = (window.Admin2State && window.Admin2State.viewTitles) || {};

    function getTitle(viewName) {
        return titles[String(viewName || '').trim()] || String(viewName || '').trim();
    }

    function hasView(viewName) {
        const key = String(viewName || '').trim();
        return Object.prototype.hasOwnProperty.call(titles, key);
    }

    window.Admin2Views = {
        getTitle,
        hasView,
    };
})();
