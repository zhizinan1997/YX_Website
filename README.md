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
mkdir -p /root/yxwebsite/data
docker network create yx-net || true

# 2) 拉取镜像
docker pull ghcr.io/zhizinan1997/yx_website:latest
docker pull ghcr.io/zhizinan1997/yx-gateway:latest

# 3) 启动网站应用容器（仅内网暴露 8000）
docker run -d \
  --name yx-website \
  --restart unless-stopped \
  --network yx-net \
  --network-alias yx-website \
  -p 127.0.0.1:2026:8000 \
  -v /root/yxwebsite/data:/app/data \
  ghcr.io/zhizinan1997/yx_website:latest

# 4) 启动网关容器（对外暴露双端口）
docker run -d \
  --name yx-gateway \
  --restart unless-stopped \
  --network yx-net \
  -p 127.0.0.1:2026:80 \
  -p 127.0.0.1:2027:81 \
  ghcr.io/zhizinan1997/yx-gateway:latest

```

说明：

- `2026` 为主站入口，`2027` 为 CDN 专用入口。
- 域名绑定通过 DNS/反向代理完成（主站域名指向 `2026`，CDN 域名指向 `2027`）。
- `yx-website` 默认只挂载 `data`，不要挂载 `/app/pages`，否则会用宿主机旧页面覆盖镜像内新代码。
- `MAIN_DOMAIN/CDN_DOMAIN` 不再是容器启动必填项。
- 两个镜像默认内置 `cdn_assets`，全新服务器可直接启动使用。
- 如需挂载外部 `cdn_assets` 目录，请确保目录已预先同步完整素材；空目录挂载会覆盖镜像内素材并导致 404。

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
docker-compose up -d
```

可选环境变量（`.env`）：

```bash
MAIN_PORT=8000
CDN_PORT=8001
```

说明：

- 安全相关参数（管理员账号密码、Turnstile 开关与密钥）统一在容器启动后通过 Admin 界面配置。

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
- **默认账号**: `admin`
- **默认密码**: `admin123`

_建议首次登录后立即在“账号设置”中修改默认密码。_

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
