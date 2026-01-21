# 元芯传感官网 (YX Website)

湖南元芯传感科技有限责任公司官方网站。基于 Flask 开发，支持 Docker 容器化部署。

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

如果你已从 GHCR 拉取了镜像，或本地构建了镜像。

```bash
docker run -d \
  --name yx-website \
  --restart unless-stopped \
  --network bridge \
  -p 2026:8000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key-production \
  ghcr.io/zhizinan1997/yx-website:latest
```

### 方式二：Docker Compose

项目根目录下已包含 `docker-compose.yml`，修改端口映射为 `2026:8000` 后：

```bash
docker-compose up -d
```

## ⚙️ 管理后台

- **访问地址**: `http://localhost:2026/admin`
- **默认账号**: `admin`
- **默认密码**: `metachip2024`

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
