"""
路由注册模块集合。

本包包含所有功能模块的路由定义，按功能模块组织为独立文件。
每个模块负责注册特定功能域的API路由。

模块组织：
1. admin.py - 后台认证与账号管理
2. ai_chatbot.py - AI聊天机器人
3. backup.py - 备份与恢复
4. cdn_assets.py - CDN素材管理
5. contact_messages.py - 留言系统
6. home_content.py - 首页内容管理
7. jobs_content.py - 招聘信息管理
8. media_delivery.py - 媒体分发
9. navigation_content.py - 导航内容管理
10. news_content.py - 新闻资讯管理
11. product_catalog.py - 产品目录
12. product_editor.py - 产品编辑器
13. product_settings.py - 产品设置
14. public_site.py - 公开站点
15. showcase_content.py - 展示内容
16. site_analytics.py - 站点分析

每个模块都遵循统一的注册模式：
def register_xxx_routes(app, *, login_required, ...):
    '''向Flask应用注册xxx相关路由'''
    # 路由定义...

作者：元芯传感技术团队
"""

