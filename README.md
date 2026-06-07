# 元芯传感官网 (Metachip Website)

湖南元芯传感科技有限责任公司官方网站源码。

元芯传感是一家专注于**生物与化学传感技术**的高新技术企业，提供气体检测、露点监测、湿度传感等领域的创新解决方案。本项目是其官方网站的完整实现，采用现代化技术栈构建，支持容器化部署。

**主要功能**：

- 🏢 企业展示：产品中心、解决方案、新闻资讯、关于我们
- 💬 在线留言：访客可提交咨询，支持 IP 限流防刷
- 🛡️ 管理后台：查看留言、修改管理员密码
- 📈 独立监测站：`check.hnmetachip.cn` 实时监测主站关键页面、同域资源和访问延迟
- 🐳 一键部署：Docker 容器化，GitHub Actions 自动构建

## 🛠️ 技术栈

- **后端**: Python 3.11, Flask, Gunicorn
- **监测站**: Flask, Playwright, Chromium, SQLite
- **前端**: HTML5, CSS3, JavaScript (jQuery), ArtDialog
- **部署**: Docker, GitHub Actions
- **数据**: JSON 文件存储、SQLite 监测数据

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
├── check_app/              # check.hnmetachip.cn 独立监测站
├── pages/                  # 网站各页面
├── cdn_assets/             # 统一素材目录（图片/视频）
├── docs/                   # 项目和部署文档
├── tools/                  # 维护脚本
├── server.py               # Flask 后端服务器
├── Dockerfile              # Docker 构建文件
├── Dockerfile.check        # 监测站 Docker 构建文件
├── requirements.txt        # Python依赖
├── requirements.check.txt  # 监测站 Python 依赖
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

### 本地启动监测站

`check_app/` 是独立 Flask 服务，不并入主站进程。首次本地运行需要安装监测站依赖和浏览器：

```bash
pip3 install -r requirements.check.txt
python3 -m playwright install chromium
```

启动本地预览服务：

```bash
CHECK_SCHEDULER_ENABLED=false \
CHECK_DEV_LOGIN_ENABLED=true \
CHECK_DEV_LOGIN_EMAIL=local-admin@check.local \
CHECK_MAIN_DATA_DIR=./data \
CHECK_DATA_DIR=./check_data \
PORT=8058 \
python3 -m check_app.app
```

访问地址：

- **监测看板**: <http://localhost:8058>
- **监测后台**: <http://localhost:8058/admin>

本地没有主站发信配置和已验证管理员邮箱时，可使用后台登录页的“本地预览登录”。生产环境默认关闭本地预览登录，后台只允许主站已启用且已验证邮箱的管理员登录。

---

## 🚀 Docker 部署

### 版本发布镜像

创建 GitHub Release 时，`.github/workflows/docker-publish.yml` 会同时构建并推送两个镜像：

- **主站镜像**: `ghcr.io/zhizinan1997/yx_website:<版本号>` 与 `latest`
- **监测站镜像**: `ghcr.io/zhizinan1997/yx_website-check:<版本号>` 与 `latest`

监测站镜像使用 `Dockerfile.check` 构建，主站镜像使用 `Dockerfile` 构建。

### 首选：一键脚本部署 / 升级

这是当前**首要推荐**的 Docker 部署方式。

它不是单纯“升级脚本”，而是统一的部署入口：  
- 首次部署时，脚本会自动识别当前机器没有部署痕迹，然后按“全新初始化”方式导入镜像里的 `data/pages`，并要求你输入缺失的 `SECRET_KEY`、`PUBLIC_BASE_URL`、管理员初始密码。  
- 更新部署时，脚本会自动识别当前机器已有部署痕迹，并让你选择：
  - `智能合并更新`
    说明：尽量保留宿主机上客户已经修改过的 `data/pages`，但遇到冲突仍可能需要人工核对。
  - `全新部署重置`
    说明：会先备份宿主机旧内容，然后清空 `data/pages` 以及旧版遗留的 `cdn_assets/update_logs` 宿主机目录，再完整导入新镜像内容。
- 如果当前机器上还保留着旧的 `yx-website` 容器，脚本会优先复用其中的 `SECRET_KEY`、`PUBLIC_BASE_URL` 等环境变量。
- 如果这些关键变量不存在，脚本会直接在终端里提示你输入，而不是静默失败。
- 脚本会输出非常详细的中文日志，包括镜像拉取进度、目录状态、基线来源、每个文件的新增/更新/跳过/冲突处理结果，以及容器删除、启动、验证过程。

推荐执行命令：

```bash
echo "【1/4】开始下载最新升级脚本 (通过代理)..." && \
curl -fL -x 127.0.0.1:8090 --progress-bar -o /root/yxwebsite/dockerrun_upgrade.sh https://raw.githubusercontent.com/zhizinan1997/YX_Website/main/tools/dockerrun_upgrade.sh && \
echo "【2/4】升级脚本下载完成，开始赋予执行权限..." && \
chmod +x /root/yxwebsite/dockerrun_upgrade.sh && \
echo "【3/4】执行权限已设置，开始运行升级脚本..." && \
bash /root/yxwebsite/dockerrun_upgrade.sh && \
echo "【4/4】升级脚本执行结束。"

# 如需查看可选参数
bash /root/yxwebsite/dockerrun_upgrade.sh --help
```

- 推荐每次升级前都重新下载一次脚本，确保拿到最新同步逻辑。
- 更新时如果你选择“智能合并更新”，冲突文件会分别保存到：
  - `/root/yxwebsite/.data-merge-conflicts/`
  - `/root/yxwebsite/.pages-merge-conflicts/`
- 更新时如果你选择“全新部署重置”，脚本会先把旧内容备份到：
  - `/root/yxwebsite/backups/reset-时间戳/`
- 脚本默认会在重建完成后执行 `docker image prune -f`，自动清理升级过程中遗留的旧版悬空镜像；如需跳过，可用 `CLEAN_OLD_IMAGES=false bash /root/yxwebsite/dockerrun_upgrade.sh`。
- 如果你想跳过交互选择，也可以手动指定：
  - `DEPLOY_STRATEGY=smart bash /root/yxwebsite/dockerrun_upgrade.sh`
  - `DEPLOY_STRATEGY=reset bash /root/yxwebsite/dockerrun_upgrade.sh`

说明：

- `2026` 为主站入口，直接映射到 `yx-website:8000`。
- 域名绑定通过阿里云 ESA 与宿主机 Nginx/宝塔反向代理完成，主站域名指向 `http://127.0.0.1:2026`。
- `yx-website` 在生产环境必须提供 `SECRET_KEY` 和 `PUBLIC_BASE_URL`。
- 首次部署时还必须提供 `ADMIN_PASSWORD_HASH` 或一次性 `ADMIN_PASSWORD` 作为超级管理员初始化凭据；如果 `/app/data/admin_users.json` 中已经存在超级管理员，则后续重启可省略这两个变量。
- 如确需允许首次初始化时使用弱密码，可显式传入 `ALLOW_WEAK_ADMIN_PASSWORDS=true`；默认仍为 `false`。
- 你的部署拓扑是 `用户 -> 阿里云 ESA -> 宿主机 Nginx/宝塔 -> yx-website`，因此建议固定使用 `TRUST_PROXY_HEADERS=true`。
- HTTPS 域名场景建议固定设置 `SESSION_COOKIE_SECURE=true`。
- `pages` 目录也建议持久化挂载到宿主机；后台创建或编辑新闻、产品页时会直接写入该目录，不挂载会在重建容器后丢失。
- `data` 目录除了客户数据外，也承载后台改过的站点配置、导航配置、首页模块配置等；一旦挂载到宿主机，镜像内默认 `data` 文件会被遮蔽，所以首次部署和每次升级都建议使用上面的升级脚本来同步。
- `cdn_assets` 继续挂载到宿主机以兼容客户自定义素材与备份；访问路径保持 `/cdn_assets/...`，由 ESA 在主站域名下按路径缓存。
- `update_logs` 也不再需要宿主机挂载；后台默认读取镜像内自带的更新日志。
- `MAIN_DOMAIN/CDN_DOMAIN` 不是容器启动必填项；新版 ESA 单域名部署不再需要单独 CDN 域名。
- `website` 镜像仍然是 `cdn_assets` 与默认 `pages` 的来源；其中 `pages` 因为要给后台写入，所以保留宿主机挂载。
- 空目录挂载会覆盖镜像内文件并导致 `404`/内容缺失或默认配置缺失，因此首次切换前请先把 `data` 与 `pages` 从镜像同步到宿主机目录。
- 升级镜像时，建议始终使用上面的升级脚本；它会自动处理“镜像新增默认 data/pages 文件”和“宿主机已修改内容”的合并问题。

### 宝塔 Nginx 反代（ESA 单域名）

- 主站域名（如 `test.hnmetachip.cn`）反代到：`http://127.0.0.1:2026`
- 只需要配置一个站点域名，并保持 `Host` 透传（默认即可）。
- 建议让宝塔反代层不做缓存，把缓存策略统一放在阿里云 ESA。

可在宝塔反代 `location` 中加入：

```nginx
proxy_no_cache 1;
proxy_cache_bypass 1;
```

### Docker 部署

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
ALLOW_WEAK_ADMIN_PASSWORDS=false
MAIN_PORT=2026
```

说明：

- `SECRET_KEY`、`PUBLIC_BASE_URL` 是生产启动必填项。
- 首次部署时必须提供 `ADMIN_PASSWORD_HASH` 或 `ADMIN_PASSWORD`；已有持久化管理员数据后可移除。
- 如必须允许 `admin123` 这类弱密码初始化，可额外设置 `ALLOW_WEAK_ADMIN_PASSWORDS=true`。
- 部署脚本默认持久化 `data/`、`pages/` 与 `cdn_assets/`，以兼容客户后台编辑、上传素材和升级备份。
- 如果你也使用宿主机挂载 `data/`，请注意镜像内默认 `data` 文件同样会被遮蔽；升级时也需要采用和上面相同的同步思路，否则新增默认配置可能不会自动进入宿主机目录。
- Turnstile 等业务配置仍可在 Admin 界面内调整；旧版 CDN 域名配置仅保留兼容，不再触发 `/cdn_assets/` 跳转。

### 手动 Docker Run（高级用户 / 排障用）

手动 `docker run` 方式仍然保留，但现在不再是首选方案。  
推荐优先使用上面的脚本，因为脚本会自动处理首次导入、环境变量补齐、更新合并、重置备份等细节。

```bash
# 1) 准备目录与网络
mkdir -p /root/yxwebsite/data /root/yxwebsite/pages /root/yxwebsite/cdn_assets
docker network create yx-net || true

# 2) 拉取镜像
docker pull ghcr.io/zhizinan1997/yx_website:latest

# 3) 首次部署时，先把镜像内的 data/pages/cdn_assets 导出到宿主机
docker create --name yx-website-seed ghcr.io/zhizinan1997/yx_website:latest
docker cp yx-website-seed:/app/data/. /root/yxwebsite/data/
docker cp yx-website-seed:/app/pages/. /root/yxwebsite/pages/
docker cp yx-website-seed:/app/cdn_assets/. /root/yxwebsite/cdn_assets/
docker rm -f yx-website-seed

# 4) 启动网站容器；宿主机 Nginx/宝塔反代到 http://127.0.0.1:2026
docker run -d \
  --name yx-website \
  --restart unless-stopped \
  --network yx-net \
  --network-alias yx-website \
  -p 127.0.0.1:2026:8000 \
  -e APP_ENV=production \
  -e SECRET_KEY='replace-with-a-random-secret-key-at-least-32-chars' \
  -e PUBLIC_BASE_URL='https://your-domain.example.com' \
  -e TRUST_PROXY_HEADERS=true \
  -e SESSION_COOKIE_SECURE=true \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD='replace-with-a-strong-bootstrap-password' \
  -e ALLOW_WEAK_ADMIN_PASSWORDS=false \
  -e CDN_ENABLED=false \
  -v /root/yxwebsite/data:/app/data \
  -v /root/yxwebsite/pages:/app/pages \
  -v /root/yxwebsite/cdn_assets:/app/cdn_assets \
  ghcr.io/zhizinan1997/yx_website:latest
```

### check.hnmetachip.cn 独立监测站

监测站使用独立镜像和独立容器部署，不依赖主站容器存活。它只读挂载主站 `data/`，从主站配置中同步发信配置、人机验证配置和已验证管理员邮箱；自身监测数据写入 `check_data/`。

```bash
mkdir -p /root/yxwebsite/check_data
docker network create yx-net || true

docker pull ghcr.io/zhizinan1997/yx_website-check:latest

docker run -d \
  --name yx-check-site \
  --restart unless-stopped \
  --network yx-net \
  -p 127.0.0.1:2028:8000 \
  -e CHECK_SECRET_KEY='replace-with-a-random-secret-at-least-32-chars' \
  -e CHECK_MAIN_DATA_DIR=/app/main_data \
  -e CHECK_DATA_DIR=/app/check_data \
  -v /root/yxwebsite/data:/app/main_data:ro \
  -v /root/yxwebsite/check_data:/app/check_data \
  ghcr.io/zhizinan1997/yx_website-check:latest
```

宝塔或 Nginx 将 `check.hnmetachip.cn` 反代到：

```text
http://127.0.0.1:2028
```

监测站默认每小时使用真实浏览器访问关键页面；异常后 1 分钟复测，仍异常则 2 分钟后再次复测，第三次仍异常时通过主站发信配置向已验证管理员邮箱发送告警。完整部署说明见 [docs/check_site.md](docs/check_site.md)。

## 📡 ESA 缓存建议

- 阿里云 ESA 只接管主站一个域名即可，代码中的资源路径保持 `/cdn_assets/...`。
- `/cdn_assets/*`、`/assets/*`：建议长缓存；如果文件名带 hash，可设置更长 TTL。
- 图片、视频、字体、CSS、JS：建议长缓存。
- `/admin/*`、`/api/*`、登录相关接口：建议绕过缓存。
- HTML 页面：建议短缓存或遵循源站。
- 从旧双域名方案切换期间，不要缓存历史 `302`。

## 🔐 Admin 登录防机器人（Turnstile）

- 后台“站点设置”新增 Turnstile 配置：
  - `启用 Turnstile 登录保护`
  - `Site Key`（前端）
  - `Secret Key`（服务端）
- 登录页会在启用后自动展示人机验证。
- `check.hnmetachip.cn/admin` 会读取同一份主站配置，启用后同样要求完成人机验证。
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
