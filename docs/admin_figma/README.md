# `/admin` Figma Handoff

## Current Status

- 新版后台已经切换为 `/admin` 入口。
- Verified routes:
  - `/admin`
  - `/admin/index.html`
- Captured screenshots:
  - [admin-login.png](/Users/zhizinan/Desktop/YX_Website/docs/admin_figma/admin-login.png)
  - [admin-direct.png](/Users/zhizinan/Desktop/YX_Website/docs/admin_figma/admin-direct.png)

## Why It Was Not Written Directly Into Figma

- The connected Figma account in this session is on a `View` seat.
- This session exposes Figma read/generation helpers, but not the canvas write toolchain needed to push a real design file from code.
- Because of that, the safe fallback is a Figma-ready handoff package instead of a direct sync.

## Code Sources

- Main entry: [admin/index.html](/Users/zhizinan/Desktop/YX_Website/admin/index.html)
- Visual tokens: [admin/styles/tokens.css](/Users/zhizinan/Desktop/YX_Website/admin/styles/tokens.css)
- Shell/layout: [admin/styles/layout.css](/Users/zhizinan/Desktop/YX_Website/admin/styles/layout.css)
- Components: [admin/styles/components.css](/Users/zhizinan/Desktop/YX_Website/admin/styles/components.css)
- Navigation grouping: [admin/js/state.js](/Users/zhizinan/Desktop/YX_Website/admin/js/state.js)

## Recommended Figma Pages

1. `00 Cover`
2. `01 Foundations`
3. `02 Admin Shell`
4. `03 Views`
5. `04 Components`

## Foundations To Rebuild In Figma

### Color tokens

- `--admin2-bg`: `#eef3f9`
- `--admin2-bg-accent`: `#e4edf8`
- `--admin2-surface`: translucent white surface
- `--admin2-text`: `#10233d`
- `--admin2-text-muted`: `#5d708b`
- `--admin2-nav`: `#08192d`
- `--admin2-nav-elevated`: `#102845`
- `--admin2-primary`: `#123d71`
- `--admin2-primary-strong`: `#0d2d56`
- `--admin2-accent`: `#27c7d9`
- `--admin2-success`: `#17935f`
- `--admin2-danger`: `#c84658`
- `--admin2-warning`: `#d18a18`

### Shape language

- Large content cards: `20px` radius
- Form controls and small buttons: `12px` radius
- Tabs and pills: `14px` to `18px` radius
- Sidebar items: rounded capsules, no left border accent

### Surface model

- Page background is not flat white; use soft radial atmosphere plus cool light base.
- Sidebar is dark, layered, and slightly glossy.
- Main work area uses semi-translucent white cards with soft border and elevated shadow.

## Shell Structure

### Login screen

- Product name: `元芯传感后台 2.0`
- Subtitle: `全新控制台入口，仅授权管理员可访问，请使用账号密码登录。`
- Keep the existing dark-tech login mood, but brand it as `2.0`.

### Sidebar groups

- `Overview`
  - 网站数据
  - 留言系统
- `Content Ops`
  - 首页设置
  - 添加资讯
  - 招聘信息
  - 站点设置
- `Catalog & Solutions`
  - 气体相关组
  - 生物相关组
- `AI & Knowledge`
  - AI 与知识库
- `System`
  - 账号设置
  - 备份恢复
  - CDN 素材
  - 更新日志
  - 后端日志
  - 退出登录

## Views To Design First

Priority order for Figma reconstruction:

1. Login
2. Dashboard shell
3. Site reports
4. Products
5. Chatbot
6. Settings
7. CDN assets

## Suggested Figma Frames

Under `03 Views`, create these desktop frames first:

1. `Admin / Login`
2. `Admin / Shell / Overview`
3. `Admin / Site Reports`
4. `Admin / Products`
5. `Admin / Chatbot`
6. `Admin / Settings`
7. `Admin / CDN Assets`

## Components To Extract

Under `04 Components`, rebuild:

- Sidebar section label
- Sidebar item
- Sidebar group toggle
- Top bar
- KPI stat card
- Primary button
- Secondary button
- Form input
- Tab bar
- Table container
- Status indicator
- Account menu
- Empty state

## Next Step When Figma Edit Access Is Available

- Create a new design file called `Admin Console`.
- Rebuild the shell first, then the login frame, then the `Site Reports` and `Products` views.
- Once a writable Figma session is available, this package can be used as the source-of-truth for a direct sync pass.
