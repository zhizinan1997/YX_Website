# 桌面客户端（desktop/）

`/admin` 的 Windows 客户端。用 [Tauri v2](https://v2.tauri.app/) 做一个原生外壳，
**窗口顶层导航到线上 `https://www.hnmetachip.cn/admin`，页面 origin 保持真实域名**，
不改后端、不重写后台前端。

好处是后台与客户端永远同一份代码，功能自动同步；代价是下面这些约束一条都不能违反。

---

## 为什么不能换一种做法

| 做法 | 结果 |
| --- | --- |
| 把 `/admin` 放进 iframe | `/admin` 响应带 `X-Frame-Options: DENY` 和 `frame-ancestors 'self'`，直接拒绝 |
| 用自定义协议（`app://`）或本地代理加载 | 写操作全部 403。后端用 `is_same_origin_request` 校验 `Origin`/`Referer`（`app/request_security.py`），origin 一变就过不去 |
| 把前端静态文件打包进客户端、API 指向线上 | Cookie 是 `SameSite=Lax`，跨源 fetch 不带 Cookie，登录态建立不起来 |
| 用原生控件重写一套管理界面 | `admin.py` 约 4800 行、`site_analytics.py` 约 6900 行，等于把后台重做一遍，还会长期与 Web 端漂移 |

所以客户端只能是一个"加载真实线上页面的外壳"，价值来自 Rust 侧的原生能力。

---

## 目录结构

```
desktop/
├── README.md                  本文件
├── tools/generate_icons.py    按品牌配色重新生成图标
├── ui/index.html              应用内置兜底页（离线 / 连接失败提示）
└── src-tauri/
    ├── Cargo.toml
    ├── tauri.conf.json
    ├── capabilities/default.json   权限集：故意不声明 remote
    ├── icons/                      应用图标与托盘图标
    └── src/
        ├── main.rs          窗口创建、单实例、启动探测
        ├── config.rs        站点基址、导出目录、连通性探测
        ├── navigation.rs    顶层导航分流（站内放行 / 站外交系统浏览器）
        ├── downloads.rs     下载落盘接管（固定导出目录 + 完成通知）
        ├── scripts.rs       注入脚本（标题通道 + window.open / target=_blank 归一化）
        └── tray.rs          托盘图标与未读角标
```

---

## 外壳解决了后台在 WebView 里的哪些问题

这几处不是"锦上添花"，是不做就会坏掉的：

1. **`window.open` / `target="_blank"` 会被静默吞掉。**
   wry 在没有新窗口处理器时对 `NewWindowRequested` 无条件 `SetHandled(true)`，
   结果不是"弹出系统浏览器"，而是**什么都没发生**。后台有 6 处功能走这条路：
   整站备份下载、知识库 PDF 预览与下载、产品/生物产品代码下载、简历下载、
   CDN 素材预览、已发布页面链接。
   处理方式：注入脚本把新窗口请求改写成同窗口导航，再由 `navigation.rs` 分流。

2. **普通下载的落盘位置不可控。**
   接管 `on_download` 后统一存到「文档\元芯后台导出」，同名文件自动加序号不覆盖。
   注册处理器会隐藏 WebView2 自带的下载提示，所以**完成通知是必须的**——
   否则"静默下载"在用户眼里等同"点了没反应"。

3. **三处 HTML5 拖拽上传会失效。**
   Tauri 默认替换 WebView2 的拖放处理器。已通过 `disable_drag_drop_handler()` 关闭，
   首页轮播、合作伙伴 Logo、知识库 PDF 三处拖拽区恢复正常。

4. **站点不可达时只会看到白屏网络错误页。**
   改为先加载应用内置兜底页，探测可达后再跳转到线上后台；不可达时给出可重试的提示。

---

## 会话与登录行为（重要）

登录页有「30 天内免登录」勾选框，**它决定关掉客户端之后要不要重登**：

| | 不勾选 | 勾选 |
|---|---|---|
| 关掉客户端再打开 | 需要重新登录 | 直接进后台 |
| 放到托盘空闲 | 满 2 小时会话过期 | 30 天内不过期 |
| Cookie 是否落盘 | 否（会话级 Cookie，进程退出即丢失） | 是（带 30 天 `Expires`，存在 WebView 数据目录里） |

**这条功能完全在后端和网页端实现，客户端一行代码都没改。** 客户端只是加载同一个
后台页面，勾选后后端下发持久 Cookie，WebView2 自动把它写进
`%LOCALAPPDATA%\cn.hnmetachip.admin.desktop\EBWebView`，下次启动 `location` 还是那个
后台地址，`/admin/check` 返回 `logged_in: true`，页面直接显示后台。

客户端**不做**登录态持久化，也**不做**伪造页面可见性来续期——那等于绕过服务端的
会话控制，会让整套后台的安全设计失效。免登录靠的是后端显式下发的长效 Cookie，
不是客户端在绕过校验。

未勾选时仍是老行为：服务端限制空闲 2 小时 / 绝对 24 小时，空闲计时靠
`X-Admin-User-Active` 请求头刷新，而该请求头只在页面可见且近期有键鼠输入时才附加
（`admin/js/api.js`），窗口放到托盘 2 小时后会话照常过期。

**收回登录态**：后台账号菜单里的「退出登录」只清当前这一份 Cookie，点它之后**客户端
仍保持登录**；要一次性踢掉所有设备用「退出所有设备」，或改密码。

重登需要重新过人机验证（生产当前配置为阿里云 ESA），若账号启用了邮箱验证码登录还需收码。

---

## 已知限制

- **Passkey / Windows Hello 大概率不可用。** WebView2 对平台认证器的支持在
  [WebView2Feedback#5663](https://github.com/MicrosoftEdge/WebView2Feedback/issues/5663)
  中仍是未修复状态。请在目标机器上实测 `PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()`；
  若返回 `false`，登录请使用密码 + 邮箱验证码。
- **知识库 PDF 的"预览"会变成下载。** wry 默认关闭了 WebView2 内置 PDF 预览器
  （`--disable-features=msPdfOOUI`），PDF 链接一律触发下载。
- **托盘菜单的「回到后台首页」是保底逃生入口。** 外壳没有浏览器前进/后退按钮，
  万一某次导航把窗口带离了后台，用它重新回到 `/admin`。
- **下载完成通知在开发模式下可能不出现。** Windows 的 Toast 通知要求应用有开始菜单
  快捷方式和 AppUserModelID，安装包安装后正常。托盘菜单的「打开导出目录」是永远可用的
  兜底入口。
- **不通外链自动走系统浏览器**：跨域链接、同源的公开页面（`/pages/*`）、CDN 素材预览
  都会用系统默认浏览器打开，不占用后台窗口。

---

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `YX_ADMIN_BASE_URL` | `https://www.hnmetachip.cn` | 站点基址。本地调试指向 `http://localhost:8000` |
| `YX_ADMIN_EXPORT_DIR` | `%USERPROFILE%\Documents\元芯后台导出` | 下载落盘目录 |

> 后端有 IP 地域围栏（GeoIP 解析失败即拒绝登录，fail-closed），且**同一 IP 连续 3 次
> 密码错误会封禁 12 小时**。调试登录流程时请优先用本地 `python server.py`
> （`http://localhost:8000`）环境，不要在生产环境反复试密码。

---

## 构建

### 前置

- **Rust stable**（`rustup` 默认的 `x86_64-pc-windows-msvc` 工具链）
- **MSVC 生成工具 + Windows SDK**（Visual Studio Build Tools，"使用 C++ 的桌面开发"工作负载）
- **tauri CLI**：`cargo tauri` 子命令不在 Rust 里，要单独装一次
  ```bash
  cargo install tauri-cli --version "^2" --locked
  ```
  不想等编译，也可以直接从 GitHub 下预编译的
  [cargo-tauri-x86_64-pc-windows-msvc.zip](https://github.com/tauri-apps/tauri/releases?q=tauri-cli-v2)，
  解出来丢进 `~/.cargo/bin/` 即可。
- **WebView2 运行时**：Windows 11 已预装；Windows 10 一般随 Edge 更新预装，
  NSIS 安装包也会在缺失时自动引导安装

> **没有管理员权限时**（MSVC 装不上）：本地编译验证可以退回 GNU 工具链，
> 先用 winget 装一份 MinGW-w64（`BrechtSanders.WinLibs.POSIX.UCRT`），然后
> ```bash
> export RUSTUP_TOOLCHAIN=stable-x86_64-pc-windows-gnu
> cargo build --release      # 或 cargo tauri build
> ```
> 这条路径会报一个良性的链接器警告
> `ld.exe: .rsrc merge failure: multiple non-default manifests`——exe 照常生成且能运行，
> CI 走 MSVC 不会出现，不用去修。GNU 产物**只适合本机验证**，对外分发以 CI 的 MSVC 产物为准。

### 本地开发

```bash
cd desktop/src-tauri
cargo tauri dev
```

配合本地后端调试：

```bash
# 仓库根目录，另开一个终端
python server.py            # 监听 8000
# 然后
YX_ADMIN_BASE_URL=http://localhost:8000 cargo tauri dev
```

> 本地 `http://localhost:8000` 可用：后端的同源校验会比对 `request.host_url`，
> 且私网/回环地址绕过 IP 地域围栏。

### 打包

```bash
cd desktop/src-tauri
cargo tauri build
# 产物：target/release/bundle/nsis/元芯传感官网后台_<version>_x64-setup.exe
```

安装后的名字都来自 `tauri.conf.json` 里的 `productName`（安装程序文件名、桌面与开始菜单
快捷方式名、安装目录、控制面板里"应用和功能"的显示名）。可执行文件名不跟着走——它取自
`src-tauri/Cargo.toml` 的包名 `yx-admin-desktop`，所以保持 ASCII，路径里不会出现中文。

> 改 `productName` 会让安装目录和卸载注册表项一起变，等于换了个应用：
> 装机用户要先卸载旧版再装新版，否则会并存两份。`identifier` 则**任何时候都不能改**，
> 它绑定 `%LOCALAPPDATA%\{identifier}` 这个 WebView2 数据目录，一改就等于丢掉
> cookie/localStorage 并强制所有人重新登录。

重新生成图标（改了品牌色之后）：

```bash
python desktop/tools/generate_icons.py
```

### 校验注入脚本

注入脚本要覆盖后台自己的标题写入、又要从后台渲染的未读徽标里读数字，出错的表现是
"托盘角标永远不动"这类静默失效。改完 `scripts.rs` 后跑一遍行为校验（零依赖，用 node）：

```bash
node desktop/tools/check_injection.js
```

---

## 发布流程

1. 确认 `desktop/src-tauri/Cargo.toml` 与 `tauri.conf.json` 的版本号（CI 会按标签覆盖，本地改动只为一致性）。
2. 发版方式二选一：
   - **随主站一起发（常规路径）**：正常发 `v<major>.<minor>.<patch>` 的 Release（例如
     `v4.10.0`），`docker-publish.yml` 构建镜像的同时，`desktop-build.yml` 会构建 exe
     安装包挂到同一个 Release，桌面端版本号跟随标签（`v4.10.0` → `4.10.0`）。
   - **桌面端单独发版**：仅外壳自身改动时，建 **`desktop-v<major>.<minor>.<patch>`**
     形式的标签并发 Release，例如 `desktop-v0.1.0`。
3. `.github/workflows/desktop-build.yml` 自动在 `windows-latest` 上构建 NSIS 安装包，
   并把 `-setup.exe` 挂到该 Release。

> **标签前缀仍然必须区分**：`v*` 标签触发镜像 + 桌面双构建，`desktop-v*` 标签只构建
> 桌面端。docker-publish.yml 只认 `v` 前缀，`desktop-v0.1.0` 不会把主站镜像打成桌面
> 版本号并覆盖 `latest`。
>
> 桌面端版本日志**不要**写进 `update_logs/`——那里是站点版本号的来源，
> 同时还是 Docker 健康检查探测的 `/api/changelog/latest` 的数据源。

---

## 上线前必须实测的清单

1. **下载矩阵**：整站备份 ZIP、简历、产品代码、知识库 PDF、CDN 下载、图片 SEO Excel、
   AI 报告 PDF（blob）、推广二维码 PNG（data URL）、网站数据趋势 SVG。
   逐个确认文件落到导出目录且有完成通知。
2. **上传矩阵**：产品图、生物产品图、首页 Hero（拖拽）、合作伙伴 Logo（拖拽）、
   知识库 PDF（拖拽）、首页视频、备份恢复 zip、资讯编辑器粘贴上传。
3. **人机验证**：确认 WebView 能加载 `o.alicdn.com` 的 ESA 脚本并完成验证。
4. **Passkey 探针**：见上文「已知限制」。
5. **托盘角标**：新留言到达后（后台每 60 秒刷新一次未读）托盘图标与 tooltip 是否更新。
6. **单实例**：重复启动只激活已有窗口，不新开进程。
