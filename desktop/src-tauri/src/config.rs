//! 运行期配置：站点基址、导出目录、连通性探测。
//!
//! 站点基址默认指向生产主站，可用 `YX_ADMIN_BASE_URL` 覆盖。本地调试时指向
//! `http://localhost:8000` 即可——后端的同源校验会比对 `request.host_url`，
//! 本地回环地址同样能通过校验并正常登录。

use std::env;
use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::time::Duration;

use tauri::{AppHandle, Manager, Runtime, Url};

/// 生产主站。裸域会 301 到 www（README 规定的唯一主域名），所以基址固定用 www。
pub const DEFAULT_BASE_URL: &str = "https://www.hnmetachip.cn";

/// 覆盖站点基址，用于本地调试或指向测试环境。
pub const BASE_URL_ENV: &str = "YX_ADMIN_BASE_URL";

/// 覆盖导出目录。
pub const EXPORT_DIR_ENV: &str = "YX_ADMIN_EXPORT_DIR";

/// 导出目录名。落盘位置固定，用户对"下载到哪了"有稳定预期。
pub const EXPORT_DIR_NAME: &str = "元芯后台导出";

pub const MAIN_WINDOW_LABEL: &str = "main";
pub const WINDOW_TITLE: &str = "元芯传感管理后台";

/// 连通性探测的超时。太长会让本地兜底页停留过久，太短会在弱网下误判。
const PROBE_TIMEOUT: Duration = Duration::from_secs(5);

/// 解析站点基址，只保留 origin。
///
/// 基址里带路径会让拼出来的后台地址跑偏（`https://host/foo` + `/admin`），
/// 所以这里统一裁掉路径、查询串和锚点。
pub fn site_base_url() -> Url {
    let raw = env::var(BASE_URL_ENV).unwrap_or_default();
    let raw = raw.trim();
    let fallback = || Url::parse(DEFAULT_BASE_URL).expect("内置站点地址必须可解析");

    let mut url = if raw.is_empty() {
        fallback()
    } else {
        Url::parse(raw).unwrap_or_else(|_| fallback())
    };

    url.set_path("/");
    url.set_query(None);
    url.set_fragment(None);
    url
}

/// 后台首页地址，同时是注入脚本与导航放行的基准。
pub fn admin_url() -> Url {
    let mut url = site_base_url();
    url.set_path("/admin");
    url
}

/// 两个 URL 是否同源（协议、主机、端口全部一致）。
pub fn same_origin(left: &Url, right: &Url) -> bool {
    left.scheme() == right.scheme()
        && left.host_str() == right.host_str()
        && left.port_or_known_default() == right.port_or_known_default()
}

/// TCP 层连通性探测。
///
/// 只判断 DNS 与端口可达，不做 HTTP 语义检查——目的是在站点不可达时给出一个
/// 可重试的本地页面，而不是让 WebView2 直接抛出白屏的网络错误页。
pub fn probe_reachable(base: &Url) -> bool {
    let host = match base.host_str() {
        Some(value) if !value.is_empty() => value.to_string(),
        _ => return false,
    };
    let port = base.port_or_known_default().unwrap_or(443);
    let addrs = match (host.as_str(), port).to_socket_addrs() {
        Ok(value) => value,
        Err(_) => return false,
    };
    addrs
        .into_iter()
        .any(|addr| TcpStream::connect_timeout(&addr, PROBE_TIMEOUT).is_ok())
}

/// 导出目录。默认落到「文档\元芯后台导出」。
pub fn export_dir<R: Runtime>(app: &AppHandle<R>) -> PathBuf {
    if let Ok(raw) = env::var(EXPORT_DIR_ENV) {
        let raw = raw.trim();
        if !raw.is_empty() {
            return PathBuf::from(raw);
        }
    }
    if let Ok(dir) = app.path().document_dir() {
        return dir.join(EXPORT_DIR_NAME);
    }
    app.path()
        .app_local_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(EXPORT_DIR_NAME)
}
