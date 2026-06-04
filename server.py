"""  """"""
YX Website 的 Flask 入口文件与组合根。

当前文件只负责三件事：

1. 创建 Flask 应用实例。
2. 安装全局请求保护并注册全部路由。
3. 提供本地开发时的直接启动入口。

业务实现与路由细节已经拆分到 `app/` 下的各模块中。
"""

import os

from app.app_config import APP_ROOT, MESSAGES_DIR, create_app, ensure_required_runtime_config
from app.bootstrap import register_all_routes
from app.request_security import register_strict_anti_crawl_guard

# 兼容本地工具脚本：继续从 `server` 模块暴露新闻处理辅助函数。
from app.routes.news_content import (
    build_news_article_html,
    build_news_card_html,
    build_news_card_regex,
    dedupe_news_cards,
    derive_news_cover_and_summary,
    get_all_news_items,
    parse_news_article_html,
)


app = create_app()
register_strict_anti_crawl_guard(app)
ensure_required_runtime_config()
register_all_routes(app)


__all__ = [
    'app',
    'build_news_article_html',
    'build_news_card_html',
    'build_news_card_regex',
    'dedupe_news_cards',
    'derive_news_cover_and_summary',
    'get_all_news_items',
    'parse_news_article_html',
]


if __name__ == '__main__':
    # 首次本地启动时，先确保最基础的可写数据目录存在。
    data_dir = APP_ROOT / 'data'
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    # 直接运行 `python server.py` 时，输出常用访问入口，便于本地调试。
    print("=" * 50)
    print("YX Website Server")
    print("=" * 50)
    print("Local:   http://localhost:8000")
    print("Admin:   http://localhost:8000/admin")
    print(f"Data:    {MESSAGES_DIR.absolute()}")

    # 如果外部指定了日志文件路径，就优先使用；否则回落到项目默认日志。
    app_log_file = os.environ.get('FLASK_LOG_FILE', '').strip()
    if not app_log_file:
        app_log_file = str(APP_ROOT / 'data' / 'app.log')
    print(f"Logs:    {app_log_file}")

    app.logger.info("Flask application started successfully")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8000, debug=True)
