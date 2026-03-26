# 项目结构清理报告（标准强度）

- 执行时间: 2026-03-26 13:31:42 +0800
- 项目路径: `/Users/zhizinan/Desktop/YX_Website`

## 执行摘要

- 删除 `.venv`: `True`
- 删除 `pages/gassensing_test`: `True`
- 删除历史单文件: `particle_test.html, nav-table.txt`
- 删除 `scripts/*.py`: `7` 个
- 删除 `.DS_Store`: `14` 个
- 删除 `__pycache__`: `3` 个目录
- 删除空目录: `70` 个

## 删除清单

- 已删除脚本:
  - `scripts/beautify_products.py`
  - `scripts/convert_product_pages.py`
  - `scripts/localize_external_images.py`
  - `scripts/migrate_beautify_products.py`
  - `scripts/migrate_product_details.py`
  - `scripts/rename_product_files.py`
  - `scripts/update-products.py`

## 保留项（白名单）

- `update_logs/`（后台读取更新日志）
- `data/messages`、`data/knowledge`、`data/news_uploads`、`data/partners/uploads`、`data/product_cards/uploads`、`data/hero/uploads`、`data/h2_home_videos`、`data/resumes`
- `cdn_assets/images`、`cdn_assets/videos` 结构目录

## 验收结果

- 旧媒体路径引用扫描: `0`
- `/cdn_assets/...` 引用缺失: `0`
- 页面冒烟: `home/products/news/about/admin` 全部 `200`
- 后台 CDN 配置校验: `data/h2_home.json` 与 `data/hero/hero.json` 远程 URL 保持不变

## 清理后状态

- 当前空目录数: `14`
- 当前 `.DS_Store` 数: `0`
- 当前 `__pycache__` 目录数: `2`

## 风险说明

- 已按“无引用 + 非运行时必需”标准清理；若后续需要历史迁移脚本，可从 Git 历史恢复。
- `scripts/` 与 `pages/gassensing_test/` 已移除，不再作为运行依赖。
