//! 下载落盘接管。
//!
//! 注册 `on_download` 之后，wry 会对 WebView2 的 `DownloadStarting` 设置
//! `SetResultFilePath` + `SetHandled(true)`，即隐藏 WebView2 自带的下载提示、
//! 静默保存到我们指定的路径。因此「保存完成通知」不是可选项——没有通知的静默
//! 下载，在用户眼里等同于「点了没反应」。
//!
//! 注意回调是同步的、跑在 WebView2 的事件循环里，绝不能在这里弹「另存为」对话框，
//! 否则整个页面会卡死。所以这里只决定落盘路径，反馈交给系统通知 + 托盘菜单里的
//! 「打开导出目录」。

use std::ffi::{OsStr, OsString};
use std::fs;
use std::path::{Path, PathBuf};

use tauri::webview::{DownloadEvent, Webview};
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_notification::NotificationExt;

use crate::config;

/// 处理一次下载事件。返回 `false` 表示取消这次下载。
pub fn handle<R: Runtime>(webview: Webview<R>, event: DownloadEvent<'_>) -> bool {
    match event {
        DownloadEvent::Requested { destination, .. } => {
            let suggested = destination
                .file_name()
                .map(OsStr::to_os_string)
                .unwrap_or_else(|| OsString::from("download"));
            let app = webview.app_handle().clone();
            match resolve_destination(&app, &suggested) {
                Some(path) => {
                    *destination = path;
                    true
                }
                None => false,
            }
        }
        DownloadEvent::Finished { path, success, .. } => {
            let app = webview.app_handle().clone();
            notify_finished(&app, path.as_deref(), success);
            true
        }
        _ => true,
    }
}

fn resolve_destination<R: Runtime>(app: &AppHandle<R>, suggested: &OsStr) -> Option<PathBuf> {
    let dir = config::export_dir(app);
    fs::create_dir_all(&dir).ok()?;
    Some(unique_path(&dir, &sanitize_file_name(suggested)))
}

/// 同名文件不覆盖，追加 `(1)`、`(2)`… 序号。
///
/// 连续导出备份包这类操作文件名高度重复，静默覆盖会让用户丢掉上一次的导出。
fn unique_path(dir: &Path, file_name: &str) -> PathBuf {
    let candidate = dir.join(file_name);
    if !candidate.exists() {
        return candidate;
    }

    let path = Path::new(file_name);
    let stem = path
        .file_stem()
        .map(|value| value.to_string_lossy().to_string())
        .unwrap_or_else(|| "download".to_string());
    let extension = path.extension().map(|value| value.to_string_lossy().to_string());

    for index in 1..1000 {
        let name = match &extension {
            Some(extension) => format!("{stem} ({index}).{extension}"),
            None => format!("{stem} ({index})"),
        };
        let candidate = dir.join(name);
        if !candidate.exists() {
            return candidate;
        }
    }
    dir.join(file_name)
}

/// 过滤文件名里的非法字符，并规避 Windows 保留设备名。
fn sanitize_file_name(raw: &OsStr) -> String {
    let text = raw.to_string_lossy();
    let mut cleaned: String = text
        .chars()
        .map(|ch| match ch {
            '\\' | '/' | ':' | '*' | '?' | '"' | '<' | '>' | '|' => '_',
            ch if (ch as u32) < 0x20 => '_',
            ch => ch,
        })
        .collect();

    cleaned = cleaned.trim().trim_matches('.').to_string();
    if cleaned.is_empty() {
        return "download".to_string();
    }
    if is_reserved_device_name(&cleaned) {
        cleaned = format!("_{cleaned}");
    }
    // 给目录前缀留出余量，避免超出 Windows 路径长度上限导致写入失败。
    if cleaned.chars().count() > 180 {
        cleaned = cleaned.chars().take(180).collect();
    }
    cleaned
}

fn is_reserved_device_name(name: &str) -> bool {
    let stem = name.split('.').next().unwrap_or(name).to_ascii_uppercase();
    if matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL") {
        return true;
    }
    let bytes = stem.as_bytes();
    bytes.len() == 4
        && (stem.starts_with("COM") || stem.starts_with("LPT"))
        && (b'1'..=b'9').contains(&bytes[3])
}

fn notify_finished<R: Runtime>(app: &AppHandle<R>, path: Option<&Path>, success: bool) {
    let (title, body) = match (success, path) {
        (true, Some(path)) => ("导出完成", format!("已保存到 {}", path.display())),
        (true, None) => ("导出完成", format!("文件已保存到「{}」", config::EXPORT_DIR_NAME)),
        (false, _) => (
            "导出失败",
            "下载未完成，请重试；若反复失败可在浏览器中登录后台导出。".to_string(),
        ),
    };

    let _ = app
        .notification()
        .builder()
        .title(title)
        .body(body)
        .show();
}
