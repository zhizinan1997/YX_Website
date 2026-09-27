//! 注入脚本。
//!
//! 在页面脚本之前执行，且不受页面 CSP 限制，是唯一能在不修改后端的前提下改变
//! 远程页面行为的地方。脚本做三件事：
//!
//! 1. 拦截 `document.title`：后台的 `admin/js/app.js` 会在切换视图时主动重写标题，
//!    所以未读数不能直接赋值，必须用访问器包住原型上的 `title`，让任何赋值都自动
//!    带上 `(N) ` 前缀。Rust 侧靠 `on_document_title_changed` 拿到这个前缀。
//! 2. 归一化 `window.open`：Tauri 会静默丢弃新窗口请求，改写成同窗口导航，
//!    交给 `navigation.rs` 分流。
//! 3. 归一化 `target="_blank"` 链接，同上。
//!
//! 未读数本身来自后台已渲染的未读徽标（`legacy-admin.js` 的
//! `setMessagesUnreadIndicator` 每 60 秒刷新一次），这里只做读取，不重复请求接口。

use serde_json::json;

use crate::config;

/// 组合出最终注入的脚本：先把站点基址交给页面，再挂载行为补丁。
pub fn init_script(base_url: &str) -> String {
    format!(
        "window.__YX_DESKTOP_BASE_URL__ = {};\n{}",
        json!(base_url),
        BEHAVIOR_PATCH
    )
}

pub fn admin_base_url() -> String {
    config::site_base_url().to_string()
}

const BEHAVIOR_PATCH: &str = r##"(function () {
    if (window.__yxDesktopShellInstalled) { return; }
    window.__yxDesktopShellInstalled = true;

    /* ---------- 1) 标题通道：把未读数写进 document.title ---------- */

    var titleDescriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'title');
    var canDecorateTitle = !!(titleDescriptor && titleDescriptor.get && titleDescriptor.set);
    var unreadText = '';

    function stripUnreadPrefix(value) {
        return String(value == null ? '' : value).replace(/^\(\d+\+?\)\s*/, '');
    }

    function decorate(base) {
        return unreadText ? '(' + unreadText + ') ' + base : base;
    }

    // 基准标题始终从当前实时值里剥离前缀取得，不能缓存：
    // 本脚本在 document-start 执行时 <title> 还没解析出来，而且后台的 app.js
    // 会重写标题，缓存值迟早会过期。
    function currentTitle() {
        return titleDescriptor.get.call(document);
    }

    if (canDecorateTitle) {
        Object.defineProperty(document, 'title', {
            configurable: true,
            enumerable: true,
            get: function () {
                return currentTitle();
            },
            set: function (value) {
                titleDescriptor.set.call(document, decorate(stripUnreadPrefix(value)));
            }
        });
    }

    function publishUnread(value) {
        var next = String(value == null ? '' : value).trim();
        if (next === unreadText) { return; }
        unreadText = next;
        if (canDecorateTitle) {
            // 绕过自己的 setter 直接写原始属性，避免递归。
            titleDescriptor.set.call(document, decorate(stripUnreadPrefix(currentTitle())));
        }
    }

    /* ---------- 2) 未读徽标读取 ---------- */

    var BADGE_ID = 'messageCenterUnreadBadge';
    var LOGIN_PAGE_ID = 'loginPage';

    function readUnreadText() {
        // 登录页可见时后台尚未加载未读数据，角标数字是上一次的残留。
        var loginPage = document.getElementById(LOGIN_PAGE_ID);
        if (loginPage && loginPage.style.display !== 'none') { return ''; }

        var badge = document.getElementById(BADGE_ID);
        if (!badge || badge.hasAttribute('hidden')) { return ''; }

        var text = String(badge.textContent || '').trim();
        // 后台用 99+ 表示超过 99 条（formatMessageCenterBadgeCount）。
        return /^\d+\+?$/.test(text) ? text : '';
    }

    // 徽标由后台每 60 秒刷新，这里 2 秒读一次 DOM 只是为了尽快反映变化，
    // 两次 getElementById 加一次 textContent 的开销可以忽略。
    setInterval(function () { publishUnread(readUnreadText()); }, 2000);

    /* ---------- 3) window.open 归一化 ---------- */

    var nativeOpen = window.open;
    window.open = function (url) {
        if (url === undefined || url === null || url === '') { return null; }
        try {
            window.location.assign(String(url));
        } catch (error) {
            // 退回到原生实现，至少不要静默失败。
            try { nativeOpen.apply(window, arguments); } catch (ignored) { }
        }
        return null;
    };

    /* ---------- 4) target="_blank" 链接归一化 ---------- */

    document.addEventListener('click', function (event) {
        var node = event.target;
        if (!node || typeof node.closest !== 'function') { return; }

        var anchor = node.closest('a[target="_blank"]');
        if (!anchor) { return; }
        // 带 download 属性的走浏览器默认下载流程，不在这里改写。
        if (anchor.hasAttribute('download')) { return; }

        var href = anchor.href;
        if (!href) { return; }

        event.preventDefault();
        event.stopPropagation();
        try { window.location.assign(href); } catch (ignored) { }
    }, true);
})();"##;
