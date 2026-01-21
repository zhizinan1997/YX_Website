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
├── tools/                  # 维护脚本
├── server.py               # Flask 后端服务器
├── Dockerfile              # Docker 构建文件
├── docker-compose.yml      # Docker Compose 配置
├── requirements.txt        # Python依赖
└── README.md               # 项目说明
```

## 🚀 Docker 部署

### 方式一：Docker Run (推荐)

```bash
# 先创建数据目录
mkdir -p /root/yxwebsite/data

# 然后运行容器
docker run -d \
  --name yx-website \
  --restart unless-stopped \
  --network bridge \
  -p 2026:8000 \
  -v /root/yxwebsite/data:/app/data \
  yx_website-website:latest
```

### 方式二：Docker Compose

项目根目录下已包含 `docker-compose.yml`，修改端口映射为 `2026:8000` 后：

```bash
docker-compose up -d
```

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
