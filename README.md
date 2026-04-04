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
echo "【1/4】开始下载最新升级脚本..." && \
curl -fL --progress-bar -o /root/yxwebsite/dockerrun_upgrade.sh https://raw.githubusercontent.com/zhizinan1997/YX_Website/main/tools/dockerrun_upgrade.sh && \
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

- `2026` 为主站入口，`2027` 为 CDN 专用入口。
- 域名绑定通过 DNS/反向代理完成（主站域名指向 `2026`，CDN 域名指向 `2027`）。
- `yx-website` 不映射宿主机端口，仅通过 Docker 网络供 `yx-gateway` 反向代理访问。
- `yx-website` 在生产环境必须提供 `SECRET_KEY` 和 `PUBLIC_BASE_URL`。
- 首次部署时还必须提供 `ADMIN_PASSWORD_HASH` 或一次性 `ADMIN_PASSWORD` 作为超级管理员初始化凭据；如果 `/app/data/admin_users.json` 中已经存在超级管理员，则后续重启可省略这两个变量。
- 如确需允许首次初始化时使用弱密码，可显式传入 `ALLOW_WEAK_ADMIN_PASSWORDS=true`；默认仍为 `false`。
- 你的部署拓扑是 `宿主机 Nginx -> gateway -> website`，因此建议固定使用 `TRUST_PROXY_HEADERS=true`。
- HTTPS 域名场景建议固定设置 `SESSION_COOKIE_SECURE=true`。
- `pages` 目录也建议持久化挂载到宿主机；后台创建或编辑新闻、产品页时会直接写入该目录，不挂载会在重建容器后丢失。
- `data` 目录除了客户数据外，也承载后台改过的站点配置、导航配置、首页模块配置等；一旦挂载到宿主机，镜像内默认 `data` 文件会被遮蔽，所以首次部署和每次升级都建议使用上面的升级脚本来同步。
- `cdn_assets` 不再需要宿主机挂载：`website` 直接使用镜像内置素材，`gateway` 的主站入口与 CDN 入口都会转发到 `website` 统一处理。
- `update_logs` 也不再需要宿主机挂载；后台默认读取镜像内自带的更新日志。
- `MAIN_DOMAIN/CDN_DOMAIN` 不是容器启动必填项。
- `website` 镜像仍然是 `cdn_assets` 与默认 `pages` 的来源；其中 `pages` 因为要给后台写入，所以保留宿主机挂载。
- 空目录挂载会覆盖镜像内文件并导致 `404`/内容缺失或默认配置缺失，因此首次切换前请先把 `data` 与 `pages` 从镜像同步到宿主机目录。
- 升级镜像时，建议始终使用上面的升级脚本；它会自动处理“镜像新增默认 data/pages 文件”和“宿主机已修改内容”的合并问题。

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

### Docker Compose

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
ALLOW_WEAK_ADMIN_PASSWORDS=false
MAIN_PORT=8000
CDN_PORT=8001
```

说明：

- `SECRET_KEY`、`PUBLIC_BASE_URL` 是生产启动必填项。
- 首次部署时必须提供 `ADMIN_PASSWORD_HASH` 或 `ADMIN_PASSWORD`；已有持久化管理员数据后可移除。
- 如必须允许 `admin123` 这类弱密码初始化，可额外设置 `ALLOW_WEAK_ADMIN_PASSWORDS=true`。
- `docker-compose.yml` 默认只持久化 `data/` 与 `pages/`；`cdn_assets/` 和 `update_logs/` 会直接使用镜像内内容。
- 如果你也使用宿主机挂载 `data/`，请注意镜像内默认 `data` 文件同样会被遮蔽；升级时也需要采用和上面相同的同步思路，否则新增默认配置可能不会自动进入宿主机目录。
- Turnstile、CDN 等业务配置仍可在 Admin 界面内调整。

### 手动 Docker Run（高级用户 / 排障用）

手动 `docker run` 方式仍然保留，但现在不再是首选方案。  
推荐优先使用上面的脚本，因为脚本会自动处理首次导入、环境变量补齐、更新合并、重置备份等细节。

```bash
# 1) 准备目录与网络
mkdir -p /root/yxwebsite/data /root/yxwebsite/pages
docker network create yx-net || true

# 2) 拉取镜像
docker pull ghcr.io/zhizinan1997/yx_website:latest
docker pull ghcr.io/zhizinan1997/yx-gateway:latest

# 3) 首次部署时，先把镜像内的 data/pages 导出到宿主机
docker create --name yx-website-seed ghcr.io/zhizinan1997/yx_website:latest
docker cp yx-website-seed:/app/data/. /root/yxwebsite/data/
docker cp yx-website-seed:/app/pages/. /root/yxwebsite/pages/
docker rm -f yx-website-seed

# 4) 启动网站容器
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
  -e ALLOW_WEAK_ADMIN_PASSWORDS=false \
  -v /root/yxwebsite/data:/app/data \
  -v /root/yxwebsite/pages:/app/pages \
  ghcr.io/zhizinan1997/yx_website:latest

# 5) 启动网关容器
docker run -d \
  --name yx-gateway \
  --restart unless-stopped \
  --network yx-net \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  -p 127.0.0.1:2026:80 \
  -p 127.0.0.1:2027:81 \
  ghcr.io/zhizinan1997/yx-gateway:latest
```

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
