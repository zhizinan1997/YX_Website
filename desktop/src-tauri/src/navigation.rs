//! 顶层导航分流。
//!
//! 后台有 6 处功能靠 `window.open` / `target="_blank"` 打开新窗口：备份下载、
//! 知识库 PDF、产品/生物产品代码下载、简历下载、CDN 素材预览、已发布页面链接。
//! wry 在没有 `on_new_window` 处理器时会对 `NewWindowRequested` 无条件
//! `SetHandled(true)`，也就是这些操作**静默无反应**——不是弹出系统浏览器。
//!
//! 所以注入脚本先把新窗口请求改写成同窗口导航，再由这里分流：
//! 站内后台与下载接口放行，其余全部交给系统默认浏览器。

use tauri::Url;
use tauri_plugin_opener::OpenerExt;

use crate::config;

/// 允许在客户端窗口内导航的路径前缀。
///
/// 只放行后台与接口：`/api/` 里既有 JSON 接口也有附件下载地址，附件响应不会
/// 真正导航（浏览器会转成下载），所以放行 `/api/` 是安全的。
const ALLOWED_PATH_PREFIXES: [&str; 2] = ["/admin", "/api/"];

/// 构造导航守卫。返回 `false` 会取消这次导航。
pub fn build_guard(app: tauri::AppHandle, base: Url) -> impl Fn(&Url) -> bool + Send + 'static {
    move |url: &Url| {
        if is_allowed(url, &base) {
            return true;
        }
        // 站外链接、以及同源的公开页面（/pages/*）与 CDN 素材预览，都交给系统
        // 浏览器：既能正常使用，又不会把后台页面挤掉。
        if is_handoff_scheme(url) {
            let _ = app.opener().open_url(url.as_str(), None::<&str>);
        }
        false
    }
}

fn is_allowed(url: &Url, base: &Url) -> bool {
    match url.scheme() {
        // 本地兜底页自身的地址。
        "tauri" | "asset" | "ipc" => true,
        // `<a download>` 配合 blob:/data: 的下载（AI 报告 PDF、推广二维码 PNG、
        // 网站数据趋势 SVG）必须放行，否则会被误判成站外链接丢给系统浏览器而失效。
        "blob" | "data" | "about" => true,
        "http" | "https" => {
            if is_local_page(url) {
                return true;
            }
            config::same_origin(url, base)
                && ALLOWED_PATH_PREFIXES
                    .iter()
                    .any(|prefix| url.path().starts_with(prefix))
        }
        _ => false,
    }
}

/// 判断是否是应用内置页面。
///
/// Tauri 在 Windows 上把内置资源挂在 `tauri.localhost` 下（scheme 仍是 http/https），
/// 所以只能按主机名判断，不能按协议判断。
pub fn is_local_page(url: &Url) -> bool {
    matches!(url.host_str(), Some("tauri.localhost"))
}

/// 可以交给操作系统默认程序打开的协议。其余协议（如 `file:`）直接拦掉。
fn is_handoff_scheme(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https" | "mailto" | "tel")
}
