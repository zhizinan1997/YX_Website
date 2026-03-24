# 2026-03-24 更新日志（完整）

## 一、更新目标
- 优化首页轮播图与氢气首页视频的首屏加载与切换体验。
- 降低首次打开等待时间，提升首图/首视频可见速度。
- 修复后台首页轮播删除和 URL 添加时的体验问题。
- 提供可复现、可对比的性能基准脚本与报告。

## 二、前端页面改动

### 1) 首页轮播（`/index.html`）
- 轮播媒体改为按需挂载：新增 `ensureSlideMedia`，避免一次性创建全部节点造成阻塞。
- 增加下一张预热：`warmNextSlide` 仅提前准备下一张，减少切换时等待。
- 增加切换前就绪校验：`waitForSlideReady`（图片 `load` / 视频 `canplay`）未完成时不切换。
- 自动轮播改为异步受控：`goNext` 增加 `switching` 互斥，避免重入。
- 图片轮播项设置为 `img.loading='eager'`，避免离屏轮播项因 lazy 导致切换出现半张图。
- 先渲染 fallback 首帧，再异步拉取 `/api/hero` 替换真实配置，缩短首屏感知空窗。
- 预取策略调整：
  - 首页图片从“预取全部”改为“仅预热后续 2 张”。
  - 氢气视频从“预拉多段完整视频”改为“首段小范围 Range 预热”。

### 2) 氢气首页视频（`/pages/gassensing/index.html`）
- 将单 `<video>` 切源改为双视频缓冲（active/standby）机制。
- 切换逻辑改为“无切换特效硬切”：取消淡入淡出过渡，避免黑屏闪烁。
- 新增“必须可播才切”机制：
  - `waitForPlayable`：等待 `loadeddata/canplay`。
  - `waitForPlaybackStart`：等待 `playing/timeupdate/requestVideoFrameCallback`。
- 新增单一重试计时器 `retryTimer`，修复重试叠加导致的“跳过一段视频”问题。
- 切换时序调整为：新视频确认开始播放 -> 立即显示新视频 -> 隐藏并暂停旧视频。
- 视频容器增加 `visibility/pointer-events` 控制，减少视觉抖动。

## 三、后台与服务端改动

### 1) 后台界面（`/admin/index.html`）
- 新增侧边栏菜单“更新日志”页面（版本号、构建时间、更新项展示）。
- 新增 `loadChangelog`/`renderChangelog` 前端逻辑，支持从接口读取更新信息。
- 首页轮播配置读取改为 `no-store`，避免后台看到旧缓存数据。
- 首页轮播 URL 添加后即时 `renderHeroList()`，提升操作反馈速度。

### 2) 服务端接口与缓存（`/server.py`）
- 新增 JSON 条件缓存辅助：
  - `build_json_etag`
  - `cached_json_response`
- `/api/hero` 与 `/api/h2-home` 支持 ETag + `stale-while-revalidate`。
- 后台登录态访问 `/api/hero` 时强制 `Cache-Control: no-store`，确保管理端看最新数据。
- 媒体静态资源增加长期缓存头（immutable）：
  - `/media/hero/<filename>`
  - `/media/h2-home/<filename>`
  - 新增 `/media/hero-derived/<filename>`

### 3) Hero 响应式变体（`/server.py` + `data/hero/derived/`）
- 新增本地派生图能力（Pillow）：
  - AVIF / WebP
  - 多宽度（768 / 1280 / 1920 + 原图宽度）
- 新增 manifest：
  - `data/hero/derived/manifest.json`
- `/api/hero` 返回项支持 `sources + fallback + width/height`，前端可直接用 `<picture>`。
- 删除上传图片时同步清理派生图与 manifest 条目，防止垃圾文件累积。
- 上传图片成功后自动生成派生图（可用时）。

### 4) 删除接口幂等修复（`/server.py`）
- `DELETE /api/hero/items/<id>` 在目标已不存在时不再返回 404。
- 改为返回成功态 `alreadyDeleted: true`，避免重复点击产生“删除失败”误报。

### 5) 路由模块化重构（新增 `app/routes`）
- 新增：
  - `app/routes/admin.py`
  - `app/routes/backup.py`
- `server.py` 改为调用：
  - `register_admin_routes(...)`
  - `register_backup_routes(...)`
- 后台认证与备份恢复逻辑从主文件拆分，便于后续维护。

## 四、数据与内容配置变更

### 1) 首页轮播数据（`/data/hero/hero.json`）
- 轮播资源由本地上传文件切换为 HTTP 图片地址。
- 当前为 10 张 `http://121.40.30.236:1234/image/*.jpg`。
- 轮播间隔保持 `interval_seconds: 3`。

### 2) 氢气首页视频数据（`/data/h2_home.json`）
- 更新为 4 段 HTTP 视频地址：
  - `http://121.40.30.236:1234/1.mp4`
  - `http://121.40.30.236:1234/2.mp4`
  - `http://121.40.30.236:1234/3.mp4`
  - `http://121.40.30.236:1234/4.mp4`

### 3) 上传文件清理（`/data/hero/uploads/`）
- 删除了旧的 8 个上传图片文件（此前本地上传资源）。

### 4) 管理员日志（`/data/admin_login_logs.json`）
- 今日新增一次后台登录成功记录（`127.0.0.1`）。

## 五、工具与基准测试

### 1) 新增工具脚本
- `tools/build_hero_variants.py`
  - 离线生成 Hero 多格式多尺寸派生图并维护 manifest。
- `tools/benchmark_home_h2_compare.py`
  - 无浏览器依赖（去除 Playwright 依赖），基于 HTTP 请求模拟两种加载策略。
  - 强制 no-cache + cache-busting，支持“首媒体可用时间”和“全量下载时间”统计。

### 2) 产出报告
- `benchmark_home_h2_compare.json`
- `benchmark_home_h2_compare.md`

### 3) 你本机本次跑数结果（3 轮均值）
- 首页首媒体就绪：`4.829s -> 0.909s`（`-3.920s`）
- 首页策略内全部资源完成：`13.154s -> 5.891s`（`-7.263s`）
- 氢气首媒体就绪：`0.539s -> 0.504s`（`-0.036s`）
- 氢气策略内全部资源完成：`0.539s -> 0.831s`（`+0.292s`）
- 首页全量图片下载：`12.152s -> 12.128s`（`-0.024s`）
- 氢气全量视频下载：`2.738s -> 3.423s`（`+0.685s`）

## 六、已知现象与当前状态
- 首页“下一张未就绪不切换”已实现（防半图）。
- 氢气页已改为“无特效硬切 + 双缓冲 + 防跳段”，用于消除黑屏和误跳段。
- 最终视觉效果以浏览器强刷（禁用缓存）后的实测为准。

## 七、涉及文件清单（今日）
- `index.html`
- `pages/gassensing/index.html`
- `admin/index.html`
- `server.py`
- `app/__init__.py`
- `app/routes/__init__.py`
- `app/routes/admin.py`
- `app/routes/backup.py`
- `tools/build_hero_variants.py`
- `tools/benchmark_home_h2_compare.py`
- `benchmark_home_h2_compare.json`
- `benchmark_home_h2_compare.md`
- `data/hero/hero.json`
- `data/h2_home.json`
- `data/hero/derived/manifest.json`
- `data/admin_login_logs.json`

