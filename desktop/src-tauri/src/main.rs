//! 元芯传感管理后台 Windows 桌面客户端。
//!
//! 这是 `/admin` 的原生外壳：窗口顶层导航到线上后台，页面 origin 保持真实域名，
//! 不修改后端、不重写前端。外壳的价值全部来自 Rust 侧原生能力与一段注入脚本。
//!
//! 四条不可动摇的设计约束（改动任何一条都会让客户端失效或失去意义）：
//!
//! 1. **必须顶层导航到线上 `/admin`**，不能用 iframe、本地代理或自定义协议。
//!    后端所有写操作都校验 `Origin` / `Referer`（`app/request_security.py` 的
//!    `is_same_origin_request`），origin 一变全部写接口返回 403；`/admin` 还带
//!    `X-Frame-Options: DENY`，iframe 直接被拒。
//! 2. **capabilities 不声明 `remote`**，远程页面无法调用任何 IPC：托盘、下载接管、
//!    导航分流全部在 Rust 侧完成，未读数通过 `document.title` 前缀回传。
//! 3. **必须关闭 Tauri 的拖放处理器**，否则后台三处 HTML5 拖拽上传区失效。
//! 4. **必须归一化 `window.open` / `target="_blank"`**，否则后台 6 处功能静默无反应。
//!
//! 会话策略：接受"关闭客户端或空闲 2 小时后重新登录"。WebView 数据目录是持久的，
//! 但后端下发的是会话级 Cookie（无 Expires），进程退出即丢失，因此不做登录态持久化。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod downloads;
mod navigation;
mod scripts;
mod tray;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

fn main() {
    tauri::Builder::default()
        // 单实例必须最先注册：后台是长驻工具，多开实例会各自持有一份会话，
        // 并且同时往同一个导出目录写文件。
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            tray::reveal_main_window(app);
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let base = config::site_base_url();

            WebviewWindowBuilder::new(
                app,
                config::MAIN_WINDOW_LABEL,
                // 先渲染应用内置的兜底页，由 on_page_load 探测可达性后再跳到线上后台。
                // 站点不可达时兜底页会给出可重试的提示，避免 WebView2 直接抛出网络错误白屏。
                WebviewUrl::App("index.html".into()),
            )
            .title(config::WINDOW_TITLE)
            .inner_size(1440.0, 900.0)
            .min_inner_size(1024.0, 700.0)
            .center()
            // 关闭 Tauri 的拖放处理器：它会替换 WebView2 的原生拖放，
            // 导致首页轮播、合作伙伴、知识库三处 HTML5 拖拽上传收不到 dataTransfer.files。
            .disable_drag_drop_handler()
            .initialization_script(scripts::init_script(&scripts::admin_base_url()))
            .on_navigation(navigation::build_guard(handle.clone(), base))
            .on_download(downloads::handle)
            // 主路径不依赖这个回调（注入脚本已把新窗口请求改写成同窗口导航，
            // 且 target="_blank" 触发 on_new_window 存在已知问题），
            // 这里只是兜底：任何漏网的新窗口一律拒绝。
            .on_new_window(|_url, _features| tauri::webview::NewWindowResponse::Deny)
            .on_document_title_changed(|window, title| {
                // Tauri 不会自动把 document.title 同步到窗口标题，需要显式设置；
                // 顺便从中解析注入脚本写入的未读数前缀，刷新托盘角标。
                let _ = window.set_title(&title);
                tray::apply_unread_from_title(window.app_handle(), &title);
            })
            .on_page_load(|window, payload| {
                if payload.event() != tauri::webview::PageLoadEvent::Finished {
                    return;
                }
                // 每次内置兜底页加载完成时探测一次站点可达性：可达就跳转到线上后台。
                // 「重试」按钮因此只需要 location.reload()，整条链路不需要任何 IPC 命令。
                let on_local_page = window
                    .url()
                    .map(|url| navigation::is_local_page(&url))
                    .unwrap_or(false);
                if !on_local_page {
                    return;
                }

                let base = config::site_base_url();
                let handle = window.app_handle().clone();
                tauri::async_runtime::spawn(async move {
                    let reachable =
                        tauri::async_runtime::spawn_blocking(move || config::probe_reachable(&base))
                            .await
                            .unwrap_or(false);
                    if !reachable {
                        return;
                    }
                    if let Some(window) = handle.get_webview_window(config::MAIN_WINDOW_LABEL) {
                        let _ = window.navigate(config::admin_url());
                    }
                });
            })
            .build()?;

            tray::build(&handle)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("启动元芯后台客户端失败");
}
