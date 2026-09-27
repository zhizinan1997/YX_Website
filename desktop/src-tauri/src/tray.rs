//! 托盘图标与未读角标。
//!
//! 未读数来自页面标题前缀：注入脚本把 `(N) ` 写进 `document.title`，
//! `on_document_title_changed` 回调把标题交给我们。这样不需要给远程页面开任何
//! IPC 权限，也不需要额外的 HTTP 轮询——远程站点在 capabilities 里没有 `remote`
//! 声明，它发起的 IPC 会被 Tauri 直接拒绝。
//!
//! 托盘常驻不能延长会话：后端的空闲超时靠 `X-Admin-User-Active` 请求头刷新，
//! 而该请求头只在页面可见且有键鼠输入时才由前端附加。窗口放到托盘 2 小时后
//! 会话照常过期，这是预期行为，不做规避。

use tauri::image::Image;
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::{TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Runtime};

use tauri_plugin_opener::OpenerExt;

use crate::config;

const TRAY_ID: &str = "yx-admin-tray";

const ICON_NORMAL: &[u8] = include_bytes!("../icons/tray.png");
const ICON_UNREAD: &[u8] = include_bytes!("../icons/tray-unread.png");

fn icon_image(unread: bool) -> Option<Image<'static>> {
    Image::from_bytes(if unread { ICON_UNREAD } else { ICON_NORMAL }).ok()
}

/// 显示并聚焦主窗口，同时把它从最小化状态恢复出来。
pub fn reveal_main_window<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = app.get_webview_window(config::MAIN_WINDOW_LABEL) else {
        return;
    };
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
}

/// 回到后台首页。
///
/// 外壳没有浏览器前进/后退按钮，一旦某次导航把窗口带离后台（例如某个接口返回
/// 了非附件响应），用户就没有退路了。托盘里的这个入口是保底逃生通道：只要当前
/// 地址不在 `/admin` 下就重新导航回去。
fn open_admin<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = app.get_webview_window(config::MAIN_WINDOW_LABEL) else {
        return;
    };
    let on_admin_page = window
        .url()
        .map(|url| url.path().starts_with("/admin"))
        .unwrap_or(false);
    if !on_admin_page {
        let _ = window.navigate(config::admin_url());
    }
    reveal_main_window(app);
}

fn toggle_main_window<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = app.get_webview_window(config::MAIN_WINDOW_LABEL) else {
        return;
    };
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        reveal_main_window(app);
    }
}

/// 从标题前缀解析未读数，返回 `(是否为 99+ 这类上限值, 数量)`。
fn parse_unread(title: &str) -> Option<(bool, u32)> {
    let rest = title.strip_prefix('(')?;
    let close = rest.find(')')?;
    let inner = &rest[..close];

    let (digits, capped) = match inner.strip_suffix('+') {
        Some(value) => (value, true),
        None => (inner, false),
    };
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    digits.parse::<u32>().ok().map(|count| (capped, count))
}

/// 页面标题变化时同步窗口标题并刷新托盘角标。
pub fn apply_unread_from_title<R: Runtime>(app: &AppHandle<R>, title: &str) {
    let Some((capped, count)) = parse_unread(title) else {
        return;
    };
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };

    let unread = count > 0;
    if let Some(image) = icon_image(unread) {
        let _ = tray.set_icon(Some(image));
    }

    let tooltip = if unread {
        let suffix = if capped { "+" } else { "" };
        format!("{} · {count}{suffix} 条未读站内消息", config::WINDOW_TITLE)
    } else {
        format!("{} · 无未读站内消息", config::WINDOW_TITLE)
    };
    let _ = tray.set_tooltip(Some(&tooltip));
}

pub fn build<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let menu = MenuBuilder::new(app)
        .item(&MenuItemBuilder::with_id("toggle", "显示 / 隐藏窗口").build(app)?)
        .item(&MenuItemBuilder::with_id("open_admin", "回到后台首页").build(app)?)
        .item(&MenuItemBuilder::with_id("open_export", "打开导出目录").build(app)?)
        .separator()
        .item(&MenuItemBuilder::with_id("quit", "退出").build(app)?)
        .build()?;

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(icon_image(false).expect("托盘图标必须能解码"))
        .tooltip(config::WINDOW_TITLE)
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "toggle" => toggle_main_window(app),
            "open_admin" => open_admin(app),
            "open_export" => {
                let dir = config::export_dir(app);
                let _ = std::fs::create_dir_all(&dir);
                let _ = app
                    .opener()
                    .open_path(dir.to_string_lossy().to_string(), None::<&str>);
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // 左键单击交给默认行为（弹菜单），双击才切换窗口，避免两者互相打架。
            if let TrayIconEvent::DoubleClick { .. } = event {
                toggle_main_window(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}
