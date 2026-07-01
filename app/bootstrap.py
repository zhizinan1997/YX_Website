"""
应用启动接线模块，集中注册全站路由与共享依赖。

本模块负责在Flask应用启动时，按特定顺序注册所有功能路由和共享依赖项。
采用依赖注入模式，将各功能模块需要的配置和工具函数统一传入，实现模块间的解耦。

注册顺序设计原则：
1. 先注册基础设施相关路由（备份、CDN资产、媒体分发），避免被后续广义路由抢占
2. 再注册公开表单与统计接口（留言、站点分析），支持内容管理功能
3. 后台认证与内容管理接口放在中间位置
4. 最后注册公开站点路由，避免抢占更具体的API和后台路径

主要功能模块注册顺序：
1. 备份恢复模块（register_backup_routes）：数据备份和恢复功能
2. CDN资产管理（register_cdn_assets_routes）：静态资源分发
3. 媒体分发（register_media_delivery_routes）：图片、视频等媒体资源处理
4. 留言系统（register_contact_message_routes）：用户留言和简历投递
5. 站点分析（register_site_analytics_routes）：访问统计和数据分析
6. 后台管理（register_admin_routes）：管理员认证和权限控制
7. 首页内容（register_home_content_routes）：首页Banner、合作伙伴等
8. 产品目录（register_product_catalog_routes）：产品列表和分类
9. 产品设置（register_product_settings_routes）：产品详情和配置
10. 展示内容（register_showcase_content_routes）：案例和解决方案展示
11. 导航内容（register_navigation_content_routes）：网站导航配置
12. 招聘信息（register_jobs_content_routes）：职位发布和管理
13. 产品编辑器（register_product_editor_routes）：产品内容编辑
14. AI聊天机器人（register_ai_chatbot_routes）：智能客服功能
15. 新闻内容（register_news_content_routes）：资讯发布和管理
16. 公开站点（register_public_site_routes）：面向用户的前台页面

作者：元芯传感技术团队
"""

from __future__ import annotations

from app.app_config import (
    ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES,
    ALLOWED_H2_HOME_VIDEO_EXTENSIONS,
    ALLOWED_HERO_EXTENSIONS,
    ALLOWED_NEWS_IMAGE_EXTENSIONS,
    ALLOWED_PARTNER_EXTENSIONS,
    ALLOWED_PRODUCT_CARD_EXTENSIONS,
    ALLOWED_RESUME_EXTENSIONS,
    APP_ROOT,
    BACKUP_EXCLUDED_DIR_NAMES,
    BACKUP_EXCLUDED_FILE_NAMES,
    BACKUP_EXCLUDED_SUFFIXES,
    BACKUP_META_FILES,
    BEIJING_TZ,
    CDN_ASSETS_DIR,
    CHATBOT_CONVERSATION_LOG_FILE,
    CHEM_SUBSCRIPT_SCRIPT_SRC,
    DATA_DIR,
    HERO_CONFIG_FILE,
    HERO_DERIVED_DIR,
    HERO_DERIVED_FORMATS,
    HERO_DERIVED_MANIFEST_FILE,
    HERO_DERIVED_WIDTHS,
    HERO_SOURCE_IMAGE_EXTENSIONS,
    HERO_UPLOADS_DIR,
    H2_HOME_FILE,
    H2_HOME_VIDEO_UPLOADS_DIR,
    HOME_SECTION_VISIBILITY_FILE,
    HYDROGEN_SOLUTIONS_CONFIG_FILE,
    JOBS_FILE,
    KNOWLEDGE_DIR,
    LEGACY_NEWS_UPLOADS_DIR,
    MEDIA_IMMUTABLE_CACHE_CONTROL,
    MESSAGES_DIR,
    MESSAGES_META_FILE,
    NEWS_DROPPED_HTML_TAGS,
    NEWS_FEATURED_FILE,
    NEWS_SAFE_HTML_TAGS,
    NEWS_UPLOADS_DIR,
    NEWS_VISIBILITY_FILE,
    NEWS_VOID_HTML_TAGS,
    PARTNERS_CONFIG_FILE,
    PARTNERS_UPLOADS_DIR,
    PRIVATE_STATIC_PREFIXES,
    PRODUCT_CARD_UPLOADS_DIR,
    PRODUCT_FEATURED_FILE,
    PUBLIC_STATIC_EXACT_FILES,
    PUBLIC_STATIC_ROOT_DIRS,
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    RESUME_UPLOADS_DIR,
    SEO_BREADCRUMB_LABELS,
    SEO_BREADCRUMB_TARGETS,
    SEO_DEFAULT_ROBOTS,
    SEO_SECTION_DESCRIPTIONS,
    SITE_ANALYTICS_SCRIPT_SRC,
    SITE_BRAND_NAME,
    SITE_COMPANY_NAME,
    SITE_DEFAULT_DESCRIPTION,
    SITE_DISPLAY_NAME,
    SITE_FAVICON_RELATIVE_PATH,
    SITE_LOGO_PATH,
    SOLUTIONS_FEATURED_FILE,
    cached_json_response,
    get_config,
    now_beijing,
    update_config,
)
from app.admin_audit import (
    ADMIN_LOGIN_LOG_LOCK,
    append_admin_login_log,
    configure_admin_audit,
    load_admin_login_logs,
    resolve_ip_country_code,
    resolve_ip_location,
)
from app.auth_guards import login_required, require_super_admin_api
from app.optional_deps import (
    HTTPX_SUPPORT,
    MARKDOWN_SUPPORT,
    PDF_SUPPORT,
    PIL_FEATURES,
    PIL_SUPPORT,
    REQUESTS_SUPPORT,
    Image,
    ImageOps,
    PyPDF2,
    httpx,
    md,
    requests,
)
from app.public_content import (
    sanitize_public_date_text,
    sanitize_public_link_url,
    sanitize_public_media_url,
    sanitize_public_product_settings,
    sanitize_public_text,
)
from app.request_security import (
    PUBLIC_HTML_CONTENT_SECURITY_POLICY,
    PUBLIC_REFERRER_POLICY,
    STRICT_ANTI_CRAWL_HEADERS,
    first_forwarded_value,
    get_client_ip,
    get_public_base_url,
    is_anti_crawl_strict_private_path,
    is_same_origin_request,
    validate_safe_remote_fetch_url,
)
from app.routes.admin import (
    get_turnstile_settings,
    register_admin_routes,
    verify_turnstile_token,
)
from app.routes.ai_chatbot import (
    call_openai_api,
    get_chatbot_config,
    get_product_page_ai_config,
    get_product_page_ai_system_prompt,
    register_ai_chatbot_routes,
)
from app.routes.backup import register_backup_routes
from app.routes.cdn_assets import register_cdn_assets_routes
from app.routes.contact_messages import register_contact_message_routes
from app.routes.home_content import get_hero_config, register_home_content_routes
from app.routes.jobs_content import clean_job_text, register_jobs_content_routes
from app.routes.media_delivery import register_media_delivery_routes
from app.routes.navigation_content import register_navigation_content_routes
from app.routes.news_content import (
    register_news_content_routes,
    render_markdown,
    sanitize_news_html_fragment,
)
from app.routes.product_catalog import (
    DEFAULT_PRODUCT_CATEGORIES,
    EXCLUDED_PRODUCT_FILES,
    extract_case_meta_from_html,
    extract_solution_meta_from_html,
    get_all_case_items,
    get_biosensing_products_with_settings_data,
    get_gassensing_products_with_settings,
    get_products_with_settings_data,
    normalize_scanned_image_path,
    register_product_catalog_routes,
)
from app.routes.product_editor import (
    extract_product_meta_from_html,
    register_product_editor_routes,
)
from app.routes.product_settings import (
    _normalize_related_news_links,
    get_bio_product_settings,
    get_product_settings,
    infer_default_bio_industry_categories,
    infer_default_industry_categories,
    register_product_settings_routes,
    save_product_settings,
)
from app.routes.promotion_links import register_promotion_link_routes
from app.routes.public_site import register_public_site_routes
from app.routes.showcase_content import (
    get_h2_home_config,
    get_hydrogen_solution_products_config,
    register_showcase_content_routes,
    save_hydrogen_solution_products_config,
)
from app.routes.site_analytics import register_site_analytics_routes
from app.upload_utils import (
    infer_ai_product_image_extension_from_mime,
    normalize_ai_product_image_extension,
    validate_image_bytes,
    validate_uploaded_image_extension,
    validate_uploaded_pdf,
    validate_uploaded_video_extension,
)


def register_all_routes(app):
    """按既定顺序向应用注册全站路由，并补齐共享依赖。"""
    pages_dir = APP_ROOT / 'pages'

    # 共享审计模块不依附于某一个蓝图，需要在整体接线阶段统一配置。
    configure_admin_audit(
        data_dir=DATA_DIR,
        beijing_tz=BEIJING_TZ,
        requests_support=REQUESTS_SUPPORT,
        requests_module=requests if REQUESTS_SUPPORT else None,
        httpx_support=HTTPX_SUPPORT,
        httpx_module=httpx if HTTPX_SUPPORT else None,
        get_client_ip=get_client_ip,
    )

    # 基础设施与媒体分发相关路由先注册，避免后续广义公开路由抢占路径。
    register_backup_routes(
        app,
        login_required=login_required,
        project_root=APP_ROOT,
        backup_meta_files=BACKUP_META_FILES,
        backup_excluded_dir_names=BACKUP_EXCLUDED_DIR_NAMES,
        backup_excluded_file_names=BACKUP_EXCLUDED_FILE_NAMES,
        backup_excluded_suffixes=BACKUP_EXCLUDED_SUFFIXES,
    )

    register_cdn_assets_routes(
        app,
        cdn_assets_dir=CDN_ASSETS_DIR,
        site_config_file=DATA_DIR / 'site_config.json',
    )

    register_media_delivery_routes(
        app,
        login_required=login_required,
        get_config=get_config,
        update_config=update_config,
        is_same_origin_request=is_same_origin_request,
        validate_safe_remote_fetch_url=validate_safe_remote_fetch_url,
        first_forwarded_value=first_forwarded_value,
        get_h2_home_config=get_h2_home_config,
        get_hero_config=get_hero_config,
        hero_config_file=HERO_CONFIG_FILE,
        sanitize_public_media_url=sanitize_public_media_url,
        cdn_assets_dir=CDN_ASSETS_DIR,
        media_immutable_cache_control=MEDIA_IMMUTABLE_CACHE_CONTROL,
        requests_support=REQUESTS_SUPPORT,
        requests_module=requests if REQUESTS_SUPPORT else None,
        httpx_support=HTTPX_SUPPORT,
        httpx_module=httpx if HTTPX_SUPPORT else None,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_biosensing_products_with_settings_data=get_biosensing_products_with_settings_data,
    )

    # 公开表单与统计接口依赖公开站点，放在 API 注册靠前位置。
    register_contact_message_routes(
        app,
        login_required=login_required,
        get_config=get_config,
        get_turnstile_settings=get_turnstile_settings,
        verify_turnstile_token=verify_turnstile_token,
        get_client_ip=get_client_ip,
        clean_job_text=clean_job_text,
        now_beijing=now_beijing,
        messages_dir=MESSAGES_DIR,
        messages_meta_file=MESSAGES_META_FILE,
        resume_uploads_dir=RESUME_UPLOADS_DIR,
        allowed_resume_extensions=ALLOWED_RESUME_EXTENSIONS,
        rate_limit_max=RATE_LIMIT_MAX,
        rate_limit_window=RATE_LIMIT_WINDOW,
    )

    register_site_analytics_routes(
        app,
        login_required=login_required,
        data_dir=DATA_DIR,
        get_client_ip=get_client_ip,
        resolve_ip_location=resolve_ip_location,
        beijing_tz=BEIJING_TZ,
        get_config=get_config,
        update_config=update_config,
        requests_support=REQUESTS_SUPPORT,
        requests_module=requests if REQUESTS_SUPPORT else None,
        httpx_support=HTTPX_SUPPORT,
        httpx_module=httpx if HTTPX_SUPPORT else None,
    )

    register_promotion_link_routes(
        app,
        login_required=login_required,
        data_dir=DATA_DIR,
        get_public_base_url=get_public_base_url,
    )

    # 后台认证与内容管理相关接口。
    register_admin_routes(
        app,
        login_required=login_required,
        get_config=get_config,
        update_config=update_config,
        append_admin_login_log=append_admin_login_log,
        load_admin_login_logs=load_admin_login_logs,
        admin_login_log_lock=ADMIN_LOGIN_LOG_LOCK,
        project_root=APP_ROOT,
        resolve_ip_location=resolve_ip_location,
        resolve_ip_country_code=resolve_ip_country_code,
    )

    register_home_content_routes(
        app,
        login_required=login_required,
        cached_json_response=cached_json_response,
        sanitize_public_media_url=sanitize_public_media_url,
        validate_uploaded_video_extension=validate_uploaded_video_extension,
        validate_uploaded_image_extension=validate_uploaded_image_extension,
        allowed_partner_extensions=ALLOWED_PARTNER_EXTENSIONS,
        hero_config_file=HERO_CONFIG_FILE,
        hero_uploads_dir=HERO_UPLOADS_DIR,
        hero_derived_dir=HERO_DERIVED_DIR,
        hero_derived_manifest_file=HERO_DERIVED_MANIFEST_FILE,
        hero_source_image_extensions=HERO_SOURCE_IMAGE_EXTENSIONS,
        hero_derived_widths=HERO_DERIVED_WIDTHS,
        hero_derived_formats=HERO_DERIVED_FORMATS,
        h2_home_video_uploads_dir=H2_HOME_VIDEO_UPLOADS_DIR,
        partners_config_file=PARTNERS_CONFIG_FILE,
        partners_uploads_dir=PARTNERS_UPLOADS_DIR,
        home_section_visibility_file=HOME_SECTION_VISIBILITY_FILE,
        allowed_hero_extensions=ALLOWED_HERO_EXTENSIONS,
        media_immutable_cache_control=MEDIA_IMMUTABLE_CACHE_CONTROL,
        pil_support=PIL_SUPPORT,
        image_module=Image,
        image_ops_module=ImageOps,
        pil_features=PIL_FEATURES,
    )

    register_product_catalog_routes(
        app,
        app_root=APP_ROOT,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_link_url=sanitize_public_link_url,
        extract_product_meta_from_html=extract_product_meta_from_html,
        get_product_settings=get_product_settings,
        get_bio_product_settings=get_bio_product_settings,
        infer_default_industry_categories=infer_default_industry_categories,
        infer_default_bio_industry_categories=infer_default_bio_industry_categories,
        normalize_related_news_links=_normalize_related_news_links,
    )

    register_product_settings_routes(
        app,
        login_required=login_required,
        data_dir=DATA_DIR,
        sanitize_public_product_settings=sanitize_public_product_settings,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_link_url=sanitize_public_link_url,
        get_products_with_settings_data=get_products_with_settings_data,
        get_biosensing_products_with_settings_data=get_biosensing_products_with_settings_data,
        product_card_uploads_dir=PRODUCT_CARD_UPLOADS_DIR,
        allowed_product_card_extensions=ALLOWED_PRODUCT_CARD_EXTENSIONS,
        validate_uploaded_image_extension=validate_uploaded_image_extension,
    )

    register_showcase_content_routes(
        app,
        login_required=login_required,
        pages_dir=pages_dir,
        cached_json_response=cached_json_response,
        sanitize_public_media_url=sanitize_public_media_url,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_video_extension=validate_uploaded_video_extension,
        product_featured_file=PRODUCT_FEATURED_FILE,
        solutions_featured_file=SOLUTIONS_FEATURED_FILE,
        hydrogen_solutions_config_file=HYDROGEN_SOLUTIONS_CONFIG_FILE,
        h2_home_file=H2_HOME_FILE,
        h2_home_video_uploads_dir=H2_HOME_VIDEO_UPLOADS_DIR,
        allowed_h2_home_video_extensions=ALLOWED_H2_HOME_VIDEO_EXTENSIONS,
        get_products_with_settings_data=get_products_with_settings_data,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_all_case_items=get_all_case_items,
        extract_solution_meta_from_html=extract_solution_meta_from_html,
    )

    register_navigation_content_routes(
        app,
        login_required=login_required,
        app_root=APP_ROOT,
        data_dir=DATA_DIR,
        normalize_scanned_image_path=normalize_scanned_image_path,
        extract_solution_meta_from_html=extract_solution_meta_from_html,
        extract_case_meta_from_html=extract_case_meta_from_html,
        extract_product_meta_from_html=extract_product_meta_from_html,
    )

    register_jobs_content_routes(
        app,
        login_required=login_required,
        jobs_file=JOBS_FILE,
        pages_dir=pages_dir,
        sanitize_news_html_fragment=sanitize_news_html_fragment,
    )

    register_product_editor_routes(
        app,
        login_required=login_required,
        app_root=APP_ROOT,
        require_super_admin_api=require_super_admin_api,
        render_markdown=render_markdown,
        get_product_page_ai_config=get_product_page_ai_config,
        get_product_page_ai_system_prompt=get_product_page_ai_system_prompt,
        get_product_settings=get_product_settings,
        save_product_settings=save_product_settings,
        product_featured_file=PRODUCT_FEATURED_FILE,
        excluded_product_files=EXCLUDED_PRODUCT_FILES,
        hydrogen_solutions_config_file=HYDROGEN_SOLUTIONS_CONFIG_FILE,
        get_hydrogen_solution_products_config=get_hydrogen_solution_products_config,
        save_hydrogen_solution_products_config=save_hydrogen_solution_products_config,
        default_product_categories=DEFAULT_PRODUCT_CATEGORIES,
        normalize_ai_product_image_extension=normalize_ai_product_image_extension,
        infer_ai_product_image_extension_from_mime=infer_ai_product_image_extension_from_mime,
        allowed_ai_product_image_mime_types=ALLOWED_AI_PRODUCT_IMAGE_MIME_TYPES,
    )

    register_ai_chatbot_routes(
        app,
        login_required=login_required,
        get_config=get_config,
        update_config=update_config,
        require_super_admin_api=require_super_admin_api,
        get_client_ip=get_client_ip,
        resolve_ip_location=resolve_ip_location,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_pdf=validate_uploaded_pdf,
        knowledge_dir=KNOWLEDGE_DIR,
        conversation_log_file=CHATBOT_CONVERSATION_LOG_FILE,
        pdf_support=PDF_SUPPORT,
        pypdf2_module=PyPDF2 if PDF_SUPPORT else None,
        requests_support=REQUESTS_SUPPORT,
        requests_module=requests if REQUESTS_SUPPORT else None,
        httpx_support=HTTPX_SUPPORT,
        httpx_module=httpx if HTTPX_SUPPORT else None,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_biosensing_products_with_settings_data=get_biosensing_products_with_settings_data,
    )

    register_news_content_routes(
        app,
        login_required=login_required,
        pages_dir=pages_dir,
        news_featured_file=NEWS_FEATURED_FILE,
        news_visibility_file=NEWS_VISIBILITY_FILE,
        legacy_news_uploads_dir=LEGACY_NEWS_UPLOADS_DIR,
        news_uploads_dir=NEWS_UPLOADS_DIR,
        h2_home_file=H2_HOME_FILE,
        markdown_support=MARKDOWN_SUPPORT,
        markdown_module=md if MARKDOWN_SUPPORT else None,
        requests_support=REQUESTS_SUPPORT,
        requests_module=requests if REQUESTS_SUPPORT else None,
        httpx_support=HTTPX_SUPPORT,
        httpx_module=httpx if HTTPX_SUPPORT else None,
        allowed_news_image_extensions=ALLOWED_NEWS_IMAGE_EXTENSIONS,
        news_safe_html_tags=NEWS_SAFE_HTML_TAGS,
        news_dropped_html_tags=NEWS_DROPPED_HTML_TAGS,
        news_void_html_tags=NEWS_VOID_HTML_TAGS,
        validate_uploaded_image_extension=validate_uploaded_image_extension,
        validate_image_bytes=validate_image_bytes,
        validate_safe_remote_fetch_url=validate_safe_remote_fetch_url,
        sanitize_public_text=sanitize_public_text,
        sanitize_public_date_text=sanitize_public_date_text,
        sanitize_public_link_url=sanitize_public_link_url,
        sanitize_public_media_url=sanitize_public_media_url,
        get_h2_home_config=get_h2_home_config,
        get_product_settings=get_product_settings,
        normalize_related_news_links=_normalize_related_news_links,
        get_chatbot_config=get_chatbot_config,
        call_openai_api=call_openai_api,
    )

    # 公开站点路由覆盖面最大，放在最后，避免抢占更具体的 API 和后台路径。
    register_public_site_routes(
        app,
        login_required=login_required,
        app_root=APP_ROOT,
        cdn_assets_dir=CDN_ASSETS_DIR,
        site_favicon_relative_path=SITE_FAVICON_RELATIVE_PATH,
        public_static_exact_files=PUBLIC_STATIC_EXACT_FILES,
        public_static_root_dirs=PUBLIC_STATIC_ROOT_DIRS,
        private_static_prefixes=PRIVATE_STATIC_PREFIXES,
        get_public_base_url=get_public_base_url,
        first_forwarded_value=first_forwarded_value,
        is_anti_crawl_strict_private_path=is_anti_crawl_strict_private_path,
        strict_anti_crawl_headers=STRICT_ANTI_CRAWL_HEADERS,
        public_html_content_security_policy=PUBLIC_HTML_CONTENT_SECURITY_POLICY,
        public_referrer_policy=PUBLIC_REFERRER_POLICY,
        chem_subscript_script_src=CHEM_SUBSCRIPT_SCRIPT_SRC,
        site_analytics_script_src=SITE_ANALYTICS_SCRIPT_SRC,
        site_brand_name=SITE_BRAND_NAME,
        site_company_name=SITE_COMPANY_NAME,
        site_display_name=SITE_DISPLAY_NAME,
        site_default_description=SITE_DEFAULT_DESCRIPTION,
        site_logo_path=SITE_LOGO_PATH,
        seo_default_robots=SEO_DEFAULT_ROBOTS,
        seo_section_descriptions=SEO_SECTION_DESCRIPTIONS,
        seo_breadcrumb_labels=SEO_BREADCRUMB_LABELS,
        seo_breadcrumb_targets=SEO_BREADCRUMB_TARGETS,
    )

    return app
