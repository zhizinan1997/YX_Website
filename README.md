# 元芯传感官网 (Metachip Website)

湖南元芯传感科技有限责任公司官方网站源码。

元芯传感是一家专注于**生物与化学传感技术**的高新技术企业，提供气体检测、露点监测、湿度传感等领域的创新解决方案。本项目是其官方网站的完整实现，采用现代化技术栈构建，支持容器化部署。

**主要功能**：

- 🏢 企业展示：产品中心、解决方案、新闻资讯、关于我们
- 💬 在线留言：访客可提交咨询，支持 IP 限流防刷
- 🛡️ 管理后台：查看留言、修改管理员密码
- 🐳 一键部署：Docker 容器化，GitHub Actions 自动构建

## 🛠️ 技术栈

- **后端**: Python 3.11, Flask, Gunicorn
- **前端**: HTML5, CSS3, JavaScript (jQuery), ArtDialog
- **部署**: Docker, GitHub Actions
- **数据**: JSON 文件存储 (本地)

## 📂 目录结构

```
.
├── admin/                  # 管理后台静态文件
│   └── index.html         # 后台单页应用
├── assets/                 # 静态资源 (图片、CSS、JS)
├── data/                   # 数据存储目录 (需持久化)
│   ├── messages/          # 留言数据 (JSON)
│   ├── config.json        # 管理员账号配置
│   └── rate_limits.json   # IP限流记录
├── pages/                  # 网站各页面
├── cdn_assets/             # 统一素材目录（图片/视频）
├── gateway/                # Nginx 网关（主站/CDN 双域名分流）
├── tools/                  # 维护脚本
├── server.py               # Flask 后端服务器
├── Dockerfile              # Docker 构建文件
├── docker-compose.yml      # Docker Compose 配置
├── requirements.txt        # Python依赖
└── README.md               # 项目说明
```

## 💻 本地开发

### 环境要求

- Python 3.11+
- pip

### 启动步骤

1. **安装依赖**

```bash
cd /path/to/YX_Website
pip3 install -r requirements.txt
```

> **提示**: 如果遇到 SSL 证书错误，可以使用以下命令：
>
> ```bash
> pip3 install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
> ```

1. **启动开发服务器**

```bash
python3 server.py
```

1. **访问网站**

   - **前台首页**: <http://localhost:8000>
   - **管理后台**: <http://localhost:8000/admin>

开发服务器默认运行在 **8000** 端口，支持热重载（debug 模式）。

---

## 🚀 Docker 部署

### 方式一：Docker Run（双容器手动部署）

```bash
# 1) 准备目录与网络
mkdir -p /root/yxwebsite/data /root/yxwebsite/pages /root/yxwebsite/update_logs /root/yxwebsite/cdn_assets
docker network create yx-net || true

# 2) 拉取镜像
docker pull ghcr.io/zhizinan1997/yx_website:latest
docker pull ghcr.io/zhizinan1997/yx-gateway:latest

# 2.1) 首次部署时，先把网站镜像内的 pages 与 cdn_assets 导出到宿主机
# 仅在宿主机目录为空时执行一次即可
# docker create --name yx-website-assets ghcr.io/zhizinan1997/yx_website:latest
# docker cp yx-website-assets:/app/pages/. /root/yxwebsite/pages/
# docker cp yx-website-assets:/app/cdn_assets/. /root/yxwebsite/cdn_assets/
# docker rm -f yx-website-assets

# 2.2) 升级部署时（镜像已更新），同步镜像内最新 cdn_assets 到宿主机共享目录
# 注意：由于挂载了 /root/yxwebsite/cdn_assets:/app/cdn_assets，重建容器不会自动覆盖宿主机旧文件
# docker create --name yx-website-assets-new ghcr.io/zhizinan1997/yx_website:latest
# mkdir -p /root/yxwebsite/.tmp-cdn-assets
# rm -rf /root/yxwebsite/.tmp-cdn-assets/*
# docker cp yx-website-assets-new:/app/cdn_assets/. /root/yxwebsite/.tmp-cdn-assets/
# rsync -a --delete /root/yxwebsite/.tmp-cdn-assets/ /root/yxwebsite/cdn_assets/
# docker rm -f yx-website-assets-new
# rm -rf /root/yxwebsite/.tmp-cdn-assets

# 3) 启动网站应用容器（仅容器内 8000，不对宿主机开放）
docker run -d \
  --name yx-website \
  --restart unless-stopped \
  --network yx-net \
  --network-alias yx-website \
  -e APP_ENV=production \
  -e SECRET_KEY='replace-with-a-random-secret-key-at-least-32-chars' \
  -e PUBLIC_BASE_URL='https://your-domain.example.com' \
  -e TRUST_PROXY_HEADERS=true \
  -e SESSION_COOKIE_SECURE=true \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='replace-with-a-strong-bootstrap-password' \
  -v /root/yxwebsite/data:/app/data \
  -v /root/yxwebsite/pages:/app/pages \
  -v /root/yxwebsite/cdn_assets:/app/cdn_assets \
  -v /root/yxwebsite/update_logs:/app/update_logs \
  ghcr.io/zhizinan1997/yx_website:latest

# 4) 启动网关容器（对外暴露双端口）
docker run -d \
  --name yx-gateway \
  --restart unless-stopped \
  --network yx-net \
  -p 127.0.0.1:2026:80 \
  -p 127.0.0.1:2027:81 \
  -v /root/yxwebsite/cdn_assets:/app/cdn_assets:ro \
  ghcr.io/zhizinan1997/yx-gateway:latest

```

一键升级脚本（自动拉镜像、同步 `cdn_assets`、重建容器）：

```bash
# 在仓库目录执行
bash tools/dockerrun_upgrade.sh

# 如需查看可选参数
bash tools/dockerrun_upgrade.sh --help
```

- 脚本会优先复用现有 `yx-website` 容器中的环境变量（如 `SECRET_KEY`、`PUBLIC_BASE_URL`）。
- 如果当前机器上没有旧容器，请先通过环境变量提供至少 `SECRET_KEY` 与 `PUBLIC_BASE_URL` 后再执行脚本。

说明：

- `2026` 为主站入口，`2027` 为 CDN 专用入口。
- 域名绑定通过 DNS/反向代理完成（主站域名指向 `2026`，CDN 域名指向 `2027`）。
- `yx-website` 不映射宿主机端口，仅通过 Docker 网络供 `yx-gateway` 反向代理访问。
- `yx-website` 在生产环境必须提供 `SECRET_KEY` 和 `PUBLIC_BASE_URL`。
- 首次部署时还必须提供 `ADMIN_PASSWORD_HASH` 或一次性 `ADMIN_PASSWORD` 作为超级管理员初始化凭据；如果 `/app/data/admin_users.json` 中已经存在超级管理员，则后续重启可省略这两个变量。
- 你的部署拓扑是 `宿主机 Nginx -> gateway -> website`，因此建议固定使用 `TRUST_PROXY_HEADERS=true`。
- HTTPS 域名场景建议固定设置 `SESSION_COOKIE_SECURE=true`。
- `website` 与 `gateway` 必须共享同一份宿主机 `cdn_assets`；否则会出现“主站能引用、CDN/网关入口缺文件”的分叉问题。
- 推荐将 `cdn_assets` 挂载到宿主机共享目录，并同时挂给 `website` 与 `gateway`：这样主站入口与 CDN 专用入口始终读取同一份素材，后续更新不会出现两个容器内容分叉。
- `pages` 目录也建议持久化挂载到宿主机；后台创建或编辑新闻、产品页时会直接写入该目录，不挂载会在重建容器后丢失。
- `website` 建议以读写方式挂载 `/root/yxwebsite/cdn_assets:/app/cdn_assets`；`gateway` 建议以只读方式挂载 `/root/yxwebsite/cdn_assets:/app/cdn_assets:ro`。
- 推荐同时挂载 `/root/yxwebsite/pages:/app/pages` 与 `/root/yxwebsite/update_logs:/app/update_logs`，以保持页面内容与更新日志持久化。
- `MAIN_DOMAIN/CDN_DOMAIN` 不是容器启动必填项。
- `website` 镜像仍可作为初始化素材来源；`gateway` 镜像不再内置 `cdn_assets`，以减少镜像体积并统一依赖宿主机共享挂载。
- 空目录挂载会覆盖镜像内文件并导致 `404`/内容缺失，因此首次切换前请先把 `pages` 与 `cdn_assets` 同步到宿主机目录。
- 升级镜像时，`/root/yxwebsite/cdn_assets` 不会被自动覆盖；请在重建容器前执行上面的 `2.2` 同步步骤（建议每次发版都执行）。

### 宝塔 Nginx 反代（适配双域名）

- 主站域名（如 `test.hnmetachip.cn`）反代到：`http://127.0.0.1:2026`
- CDN 域名（如 `cdn.hnmetachip.cn`）反代到：`http://127.0.0.1:2027`
- 两个站点都要保持 `Host` 透传（默认即可）。
- 建议关闭宝塔“反向代理缓存”，至少对 `/cdn_assets/` 关闭，避免历史 `404/302` 被宿主机缓存导致误判。

可在对应站点反代 `location` 中加入：

```nginx
proxy_no_cache 1;
proxy_cache_bypass 1;
```

### 方式二：Docker Compose

项目根目录下已包含 `docker-compose.yml`，默认会启动两个服务：

- `website`：Flask 应用（仅容器内暴露 `8000`）
- `gateway`：统一入口网关（主站与 CDN 分流）

默认端口映射：

- 主站入口：`${MAIN_PORT:-8000} -> gateway:80`
- CDN 入口：`${CDN_PORT:-8001} -> gateway:81`

启动：

```bash
docker compose up -d
```

建议在 `.env` 中至少提供这些变量：

```bash
SECRET_KEY=replace-with-a-random-secret-key-at-least-32-chars
PUBLIC_BASE_URL=https://your-domain.example.com
TRUST_PROXY_HEADERS=true
SESSION_COOKIE_SECURE=true
ADMIN_USERNAME=admin
# 二选一：推荐直接提供哈希；或首次启动时临时提供明文密码
ADMIN_PASSWORD_HASH=
ADMIN_PASSWORD=
MAIN_PORT=8000
CDN_PORT=8001
```

说明：

- `SECRET_KEY`、`PUBLIC_BASE_URL` 是生产启动必填项。
- 首次部署时必须提供 `ADMIN_PASSWORD_HASH` 或 `ADMIN_PASSWORD`；已有持久化管理员数据后可移除。
- Turnstile、CDN 等业务配置仍可在 Admin 界面内调整。

## 📡 CDN 加速开关

- 后台“站点设置”中新增 `CDN 加速设置`：
  - `cdn_enabled`：是否开启
  - `cdn_domain`：如 `https://cdn.example.com`
- 代码中的资源路径仍保持 `/cdn_assets/...`，无需批量改源码。
- 开启后主站 `/cdn_assets/*` 会返回 `302` 到 `cdn_domain`，客户端将直接从 CDN 域名拉取资源（主站只承担轻量重定向流量）。
- 关闭后主站 `/cdn_assets/*` 恢复本地直出。

## 🔐 Admin 登录防机器人（Turnstile）

- 后台“站点设置”新增 Turnstile 配置：
  - `启用 Turnstile 登录保护`
  - `Site Key`（前端）
  - `Secret Key`（服务端）
- 登录页会在启用后自动展示人机验证。
- 无需修改阿里云域名解析；仅需服务器可访问 Cloudflare 验签接口。

## ⚙️ 管理后台

- **访问地址**: `http://localhost:2026/admin`
- **初始化方式**: 首次部署没有默认密码，需通过 `ADMIN_PASSWORD_HASH` 或一次性 `ADMIN_PASSWORD` 初始化超级管理员。
- **默认账号名**: 若未显式设置 `ADMIN_USERNAME`，默认仍为 `admin`

## ✨ 功能特性

1. **在线留言系统**
   - 包含姓名、电话(必填)、邮箱、QQ、标题、内容(必填)
   - 自动 IP 限流（每小时 5 条）
   - 无需验证码

2. **管理后台**
   - 查看所有留言（包含 IP 和时间）
   - 删除留言
   - 统计今日新增和总留言数
   - 修改管理员账号密码
