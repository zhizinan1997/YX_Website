# check.hnmetachip.cn 独立监测站部署说明

`check.hnmetachip.cn` 是独立 Python Flask + Playwright 服务，用于监测 `www.hnmetachip.cn` 关键页面和同域资源。

## 运行方式

构建镜像：

```bash
docker build -f Dockerfile.check -t yx-check-site:latest .
```

启动容器：

```bash
mkdir -p /root/yxwebsite/check_data

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
  yx-check-site:latest
```

宝塔或 Nginx 将 `check.hnmetachip.cn` 反代到：

```text
http://127.0.0.1:2028
```

## 数据和权限

- 公共看板：`https://check.hnmetachip.cn/`
- 后台：`https://check.hnmetachip.cn/admin`
- 后台登录使用主站 `data/admin_users.json` 中 `enabled=true` 且 `email_verified=true` 的管理员邮箱。
- 验证码和告警邮件使用主站 `data/config.json` 中的 SMTP 配置。
- 监测数据保存在 `/root/yxwebsite/check_data/check_site.sqlite3`，默认保留 90 天。

## 监测策略

- 默认每小时检测一次。
- 首次异常后 1 分钟复测，仍异常则 2 分钟后再次复测。
- 第三次仍异常时，向主站已验证管理员邮箱发送告警。
- 同域 CSS、JS、图片、视频、字体、XHR/fetch 失败会计入异常；外链只记录，不触发告警。

