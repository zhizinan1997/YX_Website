"""
AI聊天机器人与知识库路由模块。

本模块提供基于OpenAI的智能客服功能，支持：
1. 公开聊天接口
2. 知识库管理（PDF文档）
3. 对话日志记录
4. IP限流控制
5. 产品页AI能力

主要功能：
1. 公开聊天接口
   - 流式响应支持（SSE）
   - 多轮对话上下文
   - IP频率限制（3次/分钟，20次/天）
   - 自动清理过期对话

2. 知识库管理
   - PDF文档上传和解析
   - 文本内容缓存
   - 文件列表管理
   - 支持PDF和纯文本格式

3. 配置管理
   - OpenAI API配置
   - 模型选择
   - 费率限制配置
   - 知识库开关

4. 产品页AI
   - 根据产品资料生成页面
   - HTML代码输出
   - 模板参考支持

5. 对话日志
   - 完整对话记录（JSONL格式）
   - 用户IP记录
   - 时间戳记录
   - 自动归档

系统提示词：
- 客服助手提示词：亲切、专业、简洁
- 产品页AI提示词：生成可发布HTML代码

安全特性：
- IP频率限制
- 知识库路径穿越防护
- 本地API地址屏蔽
- 配置修改仅限超级管理员

作者：元芯传感技术团队
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Response,
    current_app,
    jsonify,
    request,
    send_from_directory,
    session,
    stream_with_context,
)

from app.request_security import validate_safe_remote_fetch_url

BEIJING_TZ = timezone(timedelta(hours=8))

def now_beijing():
    """返回北京时间对应的当前时间。"""
    return datetime.now(BEIJING_TZ)

# 模块级依赖容器，在 configure/register 阶段一次性注入。
_DEPS = {}
_knowledge_cache = {
    "content": "",
    "last_updated": 0,
    "files": [],
}
_knowledge_lock = threading.Lock()
_conversation_log_lock = threading.Lock()

MANUAL_KNOWLEDGE_FILENAME = "_manual_knowledge.txt"
KNOWLEDGE_TEXT_ENTRIES_FILENAME = "knowledge_text_entries.json"

_rate_limit_storage = defaultdict(list)
_rate_limit_lock = threading.Lock()
_turnstile_clearance_storage = {}
_turnstile_clearance_lock = threading.Lock()


def _default_turnstile_settings(_config=None):
    return {}


def _default_verify_turnstile_token(*_args, **_kwargs):
    return False, "人机验证未配置"

CHATBOT_RATE_LIMIT_CONFIG = {
    "requests_per_minute": 3,
    "requests_per_day": 20,
    "window_seconds": 60,
    "day_window_seconds": 86400,
}

CHATBOT_TURNSTILE_CLEARANCE_SECONDS = 10 * 60

_LOCAL_API_BASE_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
}
_LOCAL_API_BASE_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".lan",
    ".home",
)

CHATBOT_SYSTEM_PROMPT = """你是元芯传感的智能客服助手。你的职责是回答用户关于公司产品、技术和服务的问题。

公司信息：
- 公司名称：湖南元芯传感科技有限责任公司
- 主要业务：先进生物与化学传感技术解决方案
- 核心技术：碳基电子传感技术
- 主要产品：氢气传感器、生物传感器、气体检测模组

回答规则：
1. 每次回复都先用简短问候语开头，例如“您好”或“您好，感谢咨询”。
2. 回复语言要简洁、清晰、专业，但不能因为过于简短而遗漏关键信息。
3. 单次回复通常控制在 3 到 6 句；如果用户问题较复杂，可适当多补充 1 到 3 个关键点。
4. 优先直接回答用户问题，并尽量补充用户最关心的核心信息，例如适用场景、产品特点、是否支持定制、报价或联系路径。
5. 语气要亲切、自然，像真实人工客服，体现耐心和服务感，但不要过度夸张或过分口语化。
6. 可根据语境加入 1 到 2 个贴切的 emoji 来表达友好、感谢、关心等情绪，例如 🙂、😊、🙏，但不要堆砌，不要影响专业感。
7. 当用户咨询产品、方案、合作、价格、打样、售后等问题时，尽量给出更完整、可执行的答复，而不是只给一句概括。
8. 请用专业、友好的语气回答问题。如果遇到不确定的问题，请说明当前无法完全确认的部分，并引导用户联系我们的销售团队。
9. 不要编造官网页面“技术升级、维护中、暂时无法访问、没有页面”等状态；只有系统明确告知页面不可访问时才可这样说。
10. 每轮回答都要优先依据系统提供的“官网站内检索结果”；如果系统提供了站内检索结果或推荐页面，必须承认官网已有这些内容，并引导用户点击回答下方的推荐入口。
11. 如果系统说明没有检索到完全匹配页面，只能说“暂未在官网检索到完全匹配页面”，不要猜测官网页面状态。"""

PRODUCT_AI_SYSTEM_PROMPT = """你是“元芯传感产品页编程助手”，负责根据后台给定的产品资料生成可发布的页面内容。

你在“产品页编程 AI”场景下的硬性规则：
1) 你的输出目标是完整 HTML 页面代码。
2) 请直接开始写代码，代码写完后不要添加任何其他内容。
3) 禁止输出解释、注释说明、Markdown代码块（```）。
4) 输出尽量完整，包含 <!DOCTYPE html>、<html>、<head>、<body>。
5) 必须参考提供的模板结构与样式，不要无故删除关键布局和资源引用。
6) 文案专业、克制、可发布；禁止编造认证/资质/客户背书。
7) 图片或链接未知时可使用占位路径 /assets/images/logo.png 或保守留空。"""



# 依赖注入配置入口。
def configure_ai_chatbot(
    *,
    get_config,
    update_config,
    get_turnstile_settings=None,
    verify_turnstile_token=None,
    require_super_admin_api,
    get_client_ip,
    resolve_ip_location,
    sanitize_public_link_url,
    validate_uploaded_pdf,
    knowledge_dir,
    conversation_log_file,
    pdf_support,
    pypdf2_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
    get_gassensing_products_with_settings,
    get_biosensing_products_with_settings_data,
):
    """配置 AI 聊天机器人模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update(
        {
            "get_config": get_config,
            "update_config": update_config,
            "get_turnstile_settings": get_turnstile_settings
            or _default_turnstile_settings,
            "verify_turnstile_token": verify_turnstile_token
            or _default_verify_turnstile_token,
            "require_super_admin_api": require_super_admin_api,
            "get_client_ip": get_client_ip,
            "resolve_ip_location": resolve_ip_location,
            "sanitize_public_link_url": sanitize_public_link_url,
            "validate_uploaded_pdf": validate_uploaded_pdf,
            "knowledge_dir": Path(knowledge_dir),
            "conversation_log_file": Path(conversation_log_file),
            "pdf_support": bool(pdf_support),
            "pypdf2_module": pypdf2_module,
            "requests_support": bool(requests_support),
            "requests_module": requests_module,
            "httpx_support": bool(httpx_support),
            "httpx_module": httpx_module,
            "get_gassensing_products_with_settings": get_gassensing_products_with_settings,
            "get_biosensing_products_with_settings_data": get_biosensing_products_with_settings_data,
        }
    )


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f"AI chatbot dependency not configured: {name}")
    return value


def _current_admin_has_chatbot_access() -> bool:
    if not bool(session.get("admin_logged_in")):
        return False
    if bool(session.get("admin_is_super_admin", False)):
        return True

    raw_permissions = session.get("admin_permissions", [])
    if not isinstance(raw_permissions, (list, tuple, set)):
        return False

    for item in raw_permissions:
        if str(item or "").strip() == "chatbot":
            return True
    return False


def _require_chatbot_admin_api():
    if _current_admin_has_chatbot_access():
        return None
    return jsonify({"success": False, "message": "当前账号没有 AI 与知识库 权限"}), 403


def reset_knowledge_cache():
    with _knowledge_lock:
        _knowledge_cache["content"] = ""
        _knowledge_cache["last_updated"] = 0
        _knowledge_cache["files"] = []


def _manual_knowledge_path() -> Path:
    return _dep("knowledge_dir") / MANUAL_KNOWLEDGE_FILENAME


def _knowledge_text_entries_path() -> Path:
    return _dep("knowledge_dir") / KNOWLEDGE_TEXT_ENTRIES_FILENAME


def _read_legacy_manual_knowledge_text() -> str:
    path = _manual_knowledge_path()
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _knowledge_entry_timestamp() -> str:
    return now_beijing().replace(microsecond=0).isoformat()


def _derive_knowledge_text_title(content: str) -> str:
    for line in str(content or "").splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        if compact:
            return compact[:60] + ("..." if len(compact) > 60 else "")
    return "文本知识"


def _safe_knowledge_text_entry(row) -> dict | None:
    if not isinstance(row, dict):
        return None
    content = str(row.get("content") or "")
    if not content.strip():
        return None
    entry_id = str(row.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", entry_id):
        entry_id = uuid.uuid4().hex
    title = str(row.get("title") or "").strip() or _derive_knowledge_text_title(content)
    created_at = str(row.get("created_at") or "").strip() or _knowledge_entry_timestamp()
    modified_at = str(row.get("modified_at") or "").strip() or created_at
    return {
        "id": entry_id,
        "title": title[:120],
        "content": content,
        "created_at": created_at,
        "modified_at": modified_at,
        "size": len(content.encode("utf-8")),
    }


def _build_knowledge_text_entry(content: str, title: str = "") -> dict:
    text = str(content or "")
    now = _knowledge_entry_timestamp()
    return {
        "id": uuid.uuid4().hex,
        "title": (str(title or "").strip() or _derive_knowledge_text_title(text))[:120],
        "content": text,
        "created_at": now,
        "modified_at": now,
        "size": len(text.encode("utf-8")),
    }


def _write_knowledge_text_entries(entries: list[dict]) -> None:
    path = _knowledge_text_entries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_entries = []
    seen_ids = set()
    for row in entries:
        entry = _safe_knowledge_text_entry(row)
        if not entry or entry["id"] in seen_ids:
            continue
        seen_ids.add(entry["id"])
        clean_entries.append(entry)
    # 唯一临时文件名 + 原子替换：固定 .tmp 名在多 worker 并发写时会产生
    # 交错损坏的 JSON，损坏后读取会静默回退为空列表（条目“消失”）。
    tmp_path = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    tmp_path.write_text(
        json.dumps(clean_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _read_knowledge_text_entries() -> list[dict]:
    path = _knowledge_text_entries_path()
    if path.exists():
        try:
            raw_entries = json.loads(path.read_text(encoding="utf-8") or "[]")
        except Exception:
            raw_entries = []
        if not isinstance(raw_entries, list):
            raw_entries = []

        clean_entries = []
        seen_ids = set()
        for row in raw_entries:
            entry = _safe_knowledge_text_entry(row)
            if not entry or entry["id"] in seen_ids:
                continue
            seen_ids.add(entry["id"])
            clean_entries.append(entry)
        return clean_entries

    legacy_text = _read_legacy_manual_knowledge_text()
    migrated_entries = []
    if legacy_text.strip():
        migrated_entries.append(
            _build_knowledge_text_entry(legacy_text, title="手工录入知识库")
        )
    _write_knowledge_text_entries(migrated_entries)
    return migrated_entries


def _append_knowledge_text_entry(content: str, title: str = "") -> dict:
    text = str(content or "")
    if not text.strip():
        raise ValueError("文本内容不能为空")
    entries = _read_knowledge_text_entries()
    entry = _build_knowledge_text_entry(text, title=title)
    entries.append(entry)
    _write_knowledge_text_entries(entries)
    reset_knowledge_cache()
    return entry


def _find_knowledge_text_entry(entry_id: str) -> dict | None:
    safe_id = str(entry_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", safe_id):
        return None
    for entry in _read_knowledge_text_entries():
        if entry["id"] == safe_id:
            return entry
    return None


def _update_knowledge_text_entry(entry_id: str, *, title: str = "", content: str = "") -> dict | None:
    safe_id = str(entry_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", safe_id):
        return None
    text = str(content or "")
    if not text.strip():
        raise ValueError("文本内容不能为空")
    entries = _read_knowledge_text_entries()
    updated_entry = None
    for entry in entries:
        if entry["id"] != safe_id:
            continue
        entry["title"] = (str(title or "").strip() or _derive_knowledge_text_title(text))[:120]
        entry["content"] = text
        entry["modified_at"] = _knowledge_entry_timestamp()
        entry["size"] = len(text.encode("utf-8"))
        updated_entry = entry
        break
    if updated_entry is None:
        return None
    _write_knowledge_text_entries(entries)
    reset_knowledge_cache()
    return updated_entry


def _delete_knowledge_text_entry(entry_id: str) -> bool:
    safe_id = str(entry_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", safe_id):
        return False
    entries = _read_knowledge_text_entries()
    kept_entries = [entry for entry in entries if entry["id"] != safe_id]
    if len(kept_entries) == len(entries):
        return False
    _write_knowledge_text_entries(kept_entries)
    reset_knowledge_cache()
    return True


def _knowledge_text_entry_public(entry: dict, *, include_content: bool = True) -> dict:
    output = {
        "id": entry.get("id", ""),
        "title": entry.get("title", ""),
        "created_at": entry.get("created_at", ""),
        "modified_at": entry.get("modified_at", ""),
        "size": int(entry.get("size") or 0),
    }
    if include_content:
        output["content"] = entry.get("content", "")
    return output


def _safe_knowledge_pdf_filename(filename: str) -> str:
    raw_name = Path(str(filename or "")).name.strip()
    if not raw_name:
        return ""
    safe_name = re.sub(r"[^\w\u4e00-\u9fff\-_.]", "_", raw_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip()
    if not safe_name or safe_name in {".", ".."} or ".." in safe_name:
        return ""
    if not safe_name.lower().endswith(".pdf"):
        return ""
    if safe_name.lower() == ".pdf":
        safe_name = f"knowledge_{uuid.uuid4().hex[:8]}.pdf"
    if len(safe_name) > 180:
        stem = safe_name[:-4][:168].rstrip("._-") or "knowledge"
        safe_name = f"{stem}_{uuid.uuid4().hex[:8]}.pdf"
    return safe_name


def _unique_knowledge_pdf_filename(filename: str) -> str:
    safe_name = _safe_knowledge_pdf_filename(filename)
    if not safe_name:
        return ""
    knowledge_dir = _dep("knowledge_dir")
    target = knowledge_dir / safe_name
    if not target.exists():
        return safe_name
    stem = safe_name[:-4]
    suffix = ".pdf"
    for index in range(2, 1000):
        candidate = f"{stem}_{index}{suffix}"
        if not (knowledge_dir / candidate).exists():
            return candidate
    return f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def _safe_knowledge_pdf_path(filename: str) -> tuple[Path | None, str]:
    raw_name = str(filename or "").strip()
    safe_name = Path(raw_name).name
    if (
        not raw_name
        or safe_name != raw_name
        or ".." in raw_name
        or not raw_name.lower().endswith(".pdf")
        or _safe_knowledge_pdf_filename(raw_name) != raw_name
    ):
        return None, "文件名不合法"
    knowledge_dir = _dep("knowledge_dir")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    root = knowledge_dir.resolve()
    path = (root / safe_name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None, "文件名不合法"
    return path, ""


def load_manual_knowledge_text() -> str:
    entries = _read_knowledge_text_entries()
    return "\n\n".join(entry["content"] for entry in entries if entry.get("content"))


def save_manual_knowledge_text(text: str) -> dict:
    content = str(text or "")
    trimmed = content.strip()
    try:
        if trimmed:
            entry = _build_knowledge_text_entry(content, title="手工录入知识库")
            _write_knowledge_text_entries([entry])
            return {
                "saved": True,
                "cleared": False,
                "size": entry["size"],
                "modified": entry["modified_at"],
            }
        _write_knowledge_text_entries([])
        return {"saved": False, "cleared": True, "size": 0, "modified": ""}
    finally:
        reset_knowledge_cache()


def get_chatbot_system_prompt():
    return CHATBOT_SYSTEM_PROMPT


def get_product_page_ai_system_prompt():
    return PRODUCT_AI_SYSTEM_PROMPT


def _clean_rate_limit_storage():
    with _rate_limit_lock:
        current_time = time.time()
        keys_to_remove = []
        for key, timestamps in _rate_limit_storage.items():
            _rate_limit_storage[key] = [
                ts
                for ts in timestamps
                if current_time - ts < CHATBOT_RATE_LIMIT_CONFIG["day_window_seconds"]
            ]
            if not _rate_limit_storage[key]:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del _rate_limit_storage[key]


def _check_rate_limit(identifier, requests_limit, window_seconds):
    current_time = time.time()
    with _rate_limit_lock:
        timestamps = _rate_limit_storage[identifier]
        cutoff_time = current_time - window_seconds
        recent_requests = [ts for ts in timestamps if ts > cutoff_time]
        if len(recent_requests) >= requests_limit:
            oldest_in_window = min(recent_requests)
            retry_after = int(oldest_in_window + window_seconds - current_time) + 1
            return False, retry_after, len(recent_requests)
        recent_requests.append(current_time)
        _rate_limit_storage[identifier] = recent_requests
        return True, 0, len(recent_requests)


def _get_rate_limit_snapshot(identifier, window_seconds):
    current_time = time.time()
    with _rate_limit_lock:
        timestamps = _rate_limit_storage[identifier]
        cutoff_time = current_time - window_seconds
        recent_requests = [ts for ts in timestamps if ts > cutoff_time]
        _rate_limit_storage[identifier] = recent_requests
        if recent_requests:
            retry_after = int(min(recent_requests) + window_seconds - current_time) + 1
        else:
            retry_after = 0
        return len(recent_requests), max(0, retry_after)


def _clean_turnstile_clearance_storage():
    now_ts = time.time()
    with _turnstile_clearance_lock:
        expired = [
            key
            for key, expires_at in _turnstile_clearance_storage.items()
            if float(expires_at or 0) <= now_ts
        ]
        for key in expired:
            _turnstile_clearance_storage.pop(key, None)


def _chatbot_turnstile_settings():
    try:
        return _dep("get_turnstile_settings")(_dep("get_config")() or {}) or {}
    except Exception:
        return {}


def _chatbot_turnstile_enabled(settings):
    return bool(
        settings
        and settings.get("enabled")
        and settings.get("site_key")
        and settings.get("secret_key")
    )


def _chatbot_risk_threshold(limit, mode):
    try:
        value = int(limit)
    except Exception:
        value = 1
    value = max(1, value)
    if value <= 1:
        return 1
    if mode == "minute":
        return max(1, min(value - 1, (value * 2 + 2) // 3))
    return max(1, min(value - 1, value // 2))


def _chatbot_risk_triggered(minute_count, day_count, minute_limit, day_limit):
    minute_threshold = _chatbot_risk_threshold(minute_limit, "minute")
    day_threshold = _chatbot_risk_threshold(day_limit, "day")
    return minute_count >= minute_threshold or day_count >= day_threshold


def _chatbot_turnstile_clearance_key(client_ip, session_id):
    safe_ip = str(client_ip or "unknown").strip() or "unknown"
    safe_session = re.sub(r"[^A-Za-z0-9_.:-]", "", str(session_id or "").strip())[:80]
    return f"{safe_ip}:{safe_session or 'anonymous'}"


def _has_chatbot_turnstile_clearance(clearance_key):
    now_ts = time.time()
    with _turnstile_clearance_lock:
        expires_at = float(_turnstile_clearance_storage.get(clearance_key) or 0)
        if expires_at > now_ts:
            return True
        _turnstile_clearance_storage.pop(clearance_key, None)
    return False


def _grant_chatbot_turnstile_clearance(clearance_key):
    with _turnstile_clearance_lock:
        _turnstile_clearance_storage[clearance_key] = (
            time.time() + CHATBOT_TURNSTILE_CLEARANCE_SECONDS
        )


def _extract_chatbot_turnstile_token(payload):
    if not isinstance(payload, dict):
        return ""
    for key in ("turnstileToken", "cf_turnstile_response", "cf-turnstile-response"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _chatbot_turnstile_challenge_response(settings, message):
    return jsonify(
        {
            "success": False,
            "requires_turnstile": True,
            "message": message or "当前请求需要先完成人机验证。",
            "turnstile": {
                "enabled": True,
                "site_key": settings.get("site_key", ""),
            },
        }
    ), 403


def _require_chatbot_turnstile_if_needed(
    *,
    client_ip,
    session_id,
    payload,
    minute_count,
    day_count,
    minute_limit,
    day_limit,
):
    settings = _chatbot_turnstile_settings()
    if not _chatbot_turnstile_enabled(settings):
        return None
    if not _chatbot_risk_triggered(minute_count, day_count, minute_limit, day_limit):
        return None

    clearance_key = _chatbot_turnstile_clearance_key(client_ip, session_id)
    if _has_chatbot_turnstile_clearance(clearance_key):
        return None

    token = _extract_chatbot_turnstile_token(payload)
    if not token:
        return _chatbot_turnstile_challenge_response(
            settings,
            "智能客服请求较频繁，请先完成人机验证。",
        )

    try:
        ok, detail = _dep("verify_turnstile_token")(
            secret_key=settings.get("secret_key", ""),
            token=token,
            remote_ip=client_ip,
            proxy_url=settings.get("proxy_url", ""),
            proxy_fallback_enabled=settings.get("proxy_fallback_enabled", False),
        )
    except Exception as exc:
        LOGGER.warning("Turnstile verification error: %s", exc, exc_info=True)
        ok, detail = False, "人机验证服务暂时不可用，请稍后重试。"

    if ok:
        _grant_chatbot_turnstile_clearance(clearance_key)
        return None

    return _chatbot_turnstile_challenge_response(
        settings,
        detail or "人机验证未通过，请重新验证。",
    )


def rate_limit_chatbot(max_per_minute=10, max_per_day=100):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            _clean_rate_limit_storage()
            _clean_turnstile_clearance_storage()
            client_ip = "unknown"
            try:
                client_ip = str(_dep("get_client_ip")() or "").strip() or "unknown"
            except Exception:
                pass
            ip_key = f"ip:{client_ip}"
            minute_limit = CHATBOT_RATE_LIMIT_CONFIG.get(
                "requests_per_minute", max_per_minute
            )
            minute_window = CHATBOT_RATE_LIMIT_CONFIG.get("window_seconds", 60)
            day_limit = CHATBOT_RATE_LIMIT_CONFIG.get("requests_per_day", max_per_day)
            day_window = CHATBOT_RATE_LIMIT_CONFIG.get("day_window_seconds", 86400)
            payload = request.get_json(silent=True) or {}
            session_id = ""
            if isinstance(payload, dict):
                session_id = str(payload.get("session_id") or "").strip()

            minute_identifier = f"{ip_key}:minute"
            day_identifier = f"{ip_key}:day"
            minute_count, retry_after_ip_minute = _get_rate_limit_snapshot(
                minute_identifier,
                minute_window,
            )
            if minute_count >= int(minute_limit):
                return jsonify(
                    {
                        "success": False,
                        "message": f"请求过于频繁，请 {retry_after_ip_minute} 秒后再试",
                        "retry_after": retry_after_ip_minute,
                        "rate_limit": "ip_per_minute",
                    }
                ), 429

            day_count, retry_after_ip_day = _get_rate_limit_snapshot(
                day_identifier,
                day_window,
            )
            if day_count >= int(day_limit):
                return jsonify(
                    {
                        "success": False,
                        "message": "智能客服请求已达到今日上限，请稍后再试",
                        "retry_after": retry_after_ip_day,
                        "rate_limit": "ip_per_day",
                    }
                ), 429

            turnstile_response = _require_chatbot_turnstile_if_needed(
                client_ip=client_ip,
                session_id=session_id,
                payload=payload,
                minute_count=minute_count,
                day_count=day_count,
                minute_limit=minute_limit,
                day_limit=day_limit,
            )
            if turnstile_response is not None:
                # 进入/未通过人机验证的请求同样计入限流桶：否则带垃圾 token
                # 的请求可以无限循环触发对 siteverify 服务的出站校验调用。
                _check_rate_limit(minute_identifier, minute_limit, minute_window)
                _check_rate_limit(day_identifier, day_limit, day_window)
                return turnstile_response

            is_allowed_ip_minute, retry_after_ip_minute, count_ip_minute = (
                _check_rate_limit(
                    minute_identifier,
                    minute_limit,
                    minute_window,
                )
            )
            if not is_allowed_ip_minute:
                return jsonify(
                    {
                        "success": False,
                        "message": f"请求过于频繁，请 {retry_after_ip_minute} 秒后再试",
                        "retry_after": retry_after_ip_minute,
                        "rate_limit": "ip_per_minute",
                    }
                ), 429
            is_allowed_ip_day, retry_after_ip_day, count_ip_day = _check_rate_limit(
                day_identifier,
                day_limit,
                day_window,
            )
            if not is_allowed_ip_day:
                return jsonify(
                    {
                        "success": False,
                        "message": "客服机器人去超净室光刻了，请稍后再试",
                        "retry_after": retry_after_ip_day,
                        "rate_limit": "ip_per_day",
                    }
                ), 429
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def sanitize_ai_api_base_url(raw_url: str) -> str:
    """校验 AI API Base 地址，避免 DNS 解析导致代理假 IP 误判。"""
    value = str(raw_url or "").strip()
    if not value:
        return ""

    try:
        parsed = urlparse(value)
    except Exception:
        return ""

    scheme = (parsed.scheme or "").strip().lower()
    hostname = (parsed.hostname or "").strip().lower()
    if scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    if hostname in _LOCAL_API_BASE_BLOCKED_HOSTS or hostname.endswith(
        _LOCAL_API_BASE_BLOCKED_SUFFIXES
    ):
        return ""

    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            return ""
    elif "." not in hostname:
        return ""

    normalized = parsed._replace(fragment="").geturl().rstrip("/")
    ok, _, safe_url = validate_safe_remote_fetch_url(normalized)
    return safe_url.rstrip("/") if ok else ""


def get_chatbot_config():
    """从共享站点配置中读取聊天机器人配置。"""
    config = _dep("get_config")()
    return {
        "api_key": (os.environ.get("CHATBOT_API_KEY") or config.get("chatbot_api_key", "")),
        "api_base": (os.environ.get("CHATBOT_API_BASE") or config.get("chatbot_api_base", "https://api.openai.com/v1")),
        "model": (os.environ.get("CHATBOT_MODEL") or config.get("chatbot_model", "gpt-3.5-turbo")),
        "enabled": config.get("chatbot_enabled", True),
    }


def get_product_page_ai_config():
    """从共享站点配置中读取产品页编码 AI 配置。"""
    config = _dep("get_config")()
    return {
        "enabled": config.get("product_ai_enabled", False),
        "api_key": (os.environ.get("PRODUCT_AI_API_KEY") or config.get("product_ai_api_key", "")),
        "api_base": (os.environ.get("PRODUCT_AI_API_BASE") or config.get("product_ai_api_base", "https://api.openai.com/v1")),
        "model": (os.environ.get("PRODUCT_AI_MODEL") or config.get("product_ai_model", "gpt-4o-mini")),
    }


def load_knowledge_base():
    """从文本条目与 PDF 文件加载并缓存知识库内容。"""
    knowledge_dir = _dep("knowledge_dir")
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    pdf_support = _dep("pdf_support")
    pypdf2_module = _dep("pypdf2_module")
    text_entries = _read_knowledge_text_entries()
    entries_path = _knowledge_text_entries_path()

    with _knowledge_lock:
        pdf_files = sorted(knowledge_dir.glob("*.pdf"))
        tracked_files = []
        tracked_mtimes = []
        for pdf_file in pdf_files:
            try:
                tracked_mtimes.append(pdf_file.stat().st_mtime)
            except OSError:
                # glob 与 stat 之间文件可能被另一 worker 删除（管理端删除请求），
                # 跳过该文件而不是让公开聊天接口 500。
                continue
            tracked_files.append(pdf_file.name)
        if entries_path.exists() and entries_path.is_file():
            try:
                tracked_files.append(entries_path.name)
                tracked_mtimes.append(entries_path.stat().st_mtime)
            except OSError:
                pass
        current_files = sorted(tracked_files)
        current_mtime = max(tracked_mtimes) if tracked_mtimes else 0

        if (
            _knowledge_cache["files"] == current_files
            and _knowledge_cache["last_updated"] >= current_mtime
        ):
            return _knowledge_cache["content"]

        knowledge_text = []
        for entry in text_entries:
            content = str(entry.get("content") or "").strip()
            if not content:
                continue
            title = str(entry.get("title") or "").strip() or "文本知识"
            knowledge_text.append(f"\n--- 来自文本条目: {title} ---\n")
            knowledge_text.append(content)

        if not pdf_support or pypdf2_module is None:
            _knowledge_cache["content"] = "\n".join(knowledge_text)
            _knowledge_cache["last_updated"] = current_mtime
            _knowledge_cache["files"] = current_files
            return _knowledge_cache["content"]

        for pdf_path in pdf_files:
            try:
                with open(pdf_path, "rb") as fh:
                    reader = pypdf2_module.PdfReader(fh)
                    pdf_text = []
                    for page in reader.pages:
                        text = page.extract_text()
                        if text:
                            pdf_text.append(text)
                    if pdf_text:
                        knowledge_text.append(f"\n--- 来自文档: {pdf_path.name} ---\n")
                        knowledge_text.append("\n".join(pdf_text))
            except Exception as exc:
                print(f"Error reading PDF {pdf_path}: {exc}")
                continue

        _knowledge_cache["content"] = "\n".join(knowledge_text)
        _knowledge_cache["last_updated"] = current_mtime
        _knowledge_cache["files"] = current_files
        return _knowledge_cache["content"]


def load_chatbot_conversation_logs():
    """从按行 JSON 日志文件中加载聊天记录。"""
    log_file = _dep("conversation_log_file")
    if not log_file.exists():
        return []

    items = []
    try:
        with open(log_file, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    items.append(item)
    except Exception as exc:
        print(f"Error loading chatbot conversation logs: {exc}")
        return []

    return items


def append_chatbot_conversation_log(
    *,
    session_id,
    user_message,
    assistant_message,
    ip="",
    location="",
    page_url="",
    page_title="",
    response_source="ai",
    model="",
):
    """追加一条聊天机器人对话记录。"""
    user_text = str(user_message or "").strip()
    assistant_text = str(assistant_message or "").strip()
    if not user_text or not assistant_text:
        return

    safe_session_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(session_id or "").strip())[
        :80
    ]
    if not safe_session_id:
        safe_session_id = f"session_{now_beijing().strftime('%Y%m%d%H%M%S%f')}"

    record = {
        "timestamp": now_beijing().replace(microsecond=0).isoformat(),
        "session_id": safe_session_id,
        "ip": str(ip or "").strip()[:80],
        "location": str(location or "").strip()[:300],
        "page_url": str(page_url or "").strip()[:500],
        "page_title": str(page_title or "").strip()[:200],
        "response_source": str(response_source or "ai").strip()[:40],
        "model": str(model or "").strip()[:120],
        "user_message": user_text,
        "assistant_message": assistant_text,
    }

    log_file = _dep("conversation_log_file")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with _conversation_log_lock:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_openai_api(messages, stream=False):
    """以同步或流式模式调用兼容 OpenAI 的 API。"""
    if stream:
        return call_openai_api_stream(messages)
    return call_openai_api_sync(messages)


def call_openai_api_sync(messages):
    """调用兼容 OpenAI 的非流式 API。"""
    config = get_chatbot_config()
    if not config["api_key"]:
        return None, "AI客服未配置，请联系管理员"

    api_url = config["api_base"].rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": False,
    }

    requests_support = _dep("requests_support")
    requests_module = _dep("requests_module")
    httpx_support = _dep("httpx_support")
    httpx_module = _dep("httpx_module")

    try:
        if requests_support and requests_module is not None:
            response = requests_module.post(
                api_url, json=payload, headers=headers, timeout=60
            )
            if response.status_code != 200:
                return None, f"API错误: {response.status_code}"
            result = response.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"], None
            return None, "API返回格式错误"
        if httpx_support and httpx_module is not None:
            response = httpx_module.post(
                api_url, json=payload, headers=headers, timeout=60.0
            )
            if response.status_code != 200:
                return None, f"API错误: {response.status_code}"
            result = response.json()
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"], None
            return None, "API返回格式错误"
        return None, "缺少HTTP客户端库(requests或httpx)"
    except Exception as exc:
        print(f"OpenAI API error: {exc}")
        return None, f"API调用失败: {str(exc)}"


def _extract_chat_stream_text(chunk_obj):
    if not isinstance(chunk_obj, dict):
        return ""
    choices = chunk_obj.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def call_openai_api_stream(messages):
    """调用兼容大模型接口规范的流式接口。"""
    config = get_chatbot_config()
    if not config["api_key"]:
        return None, "AI客服未配置，请联系管理员"

    api_url = config["api_base"].rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": True,
    }

    requests_support = _dep("requests_support")
    requests_module = _dep("requests_module")
    httpx_support = _dep("httpx_support")
    httpx_module = _dep("httpx_module")
    connect_timeout = 20
    read_timeout = 300

    if requests_support and requests_module is not None:

        def gen_requests():
            response = None
            try:
                response = requests_module.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=(connect_timeout, read_timeout),
                    allow_redirects=False,
                )
                if response.status_code != 200:
                    detail = (response.text or "").strip()
                    if detail:
                        detail = detail[:500]
                    yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                    return
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8", errors="ignore")
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    text = _extract_chat_stream_text(chunk)
                    if text:
                        yield text, None
            except GeneratorExit:
                # 客户端断开时 Flask 向生成器抛 GeneratorExit（BaseException），
                # 必须显式关闭上游连接，否则会一直挂到 read_timeout。
                raise
            except Exception as exc:
                yield None, f"API调用失败: {str(exc)}"
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        return gen_requests()

    if httpx_support and httpx_module is not None:

        def gen_httpx():
            try:
                timeout_obj = httpx_module.Timeout(
                    connect=connect_timeout,
                    read=read_timeout,
                    write=60,
                    pool=60,
                )
                with httpx_module.Client(timeout=timeout_obj) as client:
                    with client.stream(
                        "POST", api_url, json=payload, headers=headers
                    ) as response:
                        if response.status_code != 200:
                            detail = (response.text or "").strip()
                            if detail:
                                detail = detail[:500]
                            yield None, f"API错误: {response.status_code}{(' - ' + detail) if detail else ''}"
                            return
                        for line in response.iter_lines():
                            if not line:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode("utf-8", errors="ignore")
                            if not line.startswith("data: "):
                                continue
                            data = line[6:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            text = _extract_chat_stream_text(chunk)
                            if text:
                                yield text, None
            except Exception as exc:
                yield None, f"API调用失败: {str(exc)}"

        return gen_httpx()

    return None, "缺少HTTP客户端库(requests或httpx)"


CHAT_RECOMMENDATION_KEYWORDS = {
    "product": ("产品", "型号", "参数", "选型", "检测", "传感器", "报警器", "模块", "检测仪", "量程", "推荐"),
    "solution": ("方案", "场景", "应用", "行业", "部署", "工况", "解决", "系统"),
    "custom": ("定制", "定制化", "开发", "特殊需求", "开发需求", "非标", "客制化", "微纳加工", "工艺定制", "芯片定制", "封装"),
    "contact": ("联系", "电话", "邮箱", "地址", "售后", "对接", "客服"),
    "quote": ("报价", "价格", "采购", "打样", "样机", "多少钱", "费用"),
}
RECOMMENDATION_CTA_LABELS = {
    "product": "查看产品",
    "solution": "查看方案",
    "custom": "查看定制服务",
    "contact": "联系咨询",
    "overview": "查看详情",
}
RECOMMENDATION_PAGE_TYPE_WEIGHT = {
    "product": 90,
    "solution": 70,
    "custom": 95,
    "contact": 55,
    "overview": 45,
    "other": 0,
}
CHAT_SEARCH_FALLBACK_QUERIES = {
    "product": "产品 传感器 模块 检测仪 报警器 参数 量程",
    "solution": "解决方案 行业 氢能 电力 环境 储能 检漏 定制化",
    "custom": "定制服务 定制化 特殊开发 微纳加工 芯片定制 封装测试",
    "contact": "联系 电话 邮箱 留言 售后",
    "quote": "报价 价格 采购 样机 打样 联系",
}
CHAT_SEARCH_BANNED_PAGE_TYPES = {"news", "career", "about", "other"}
CHAT_SPECIFIC_QUERY_STOP_PHRASES = (
    "你们", "我们", "官网", "网站", "这个", "那个", "有没有", "是否有", "有没有相关",
    "可以", "能不能", "能做吗", "发给我看看", "给我看看", "哪里", "在哪", "哪些",
    "什么", "怎么", "如何", "介绍", "一下", "相关", "页面", "界面", "入口", "服务",
    "产品", "型号", "参数", "选型", "检测", "传感器", "报警器", "模块", "检测仪",
    "量程", "推荐", "方案", "解决方案", "场景", "应用", "行业", "部署", "工况",
    "解决", "系统", "联系", "电话", "邮箱", "地址", "售后", "对接", "客服",
    "报价", "价格", "采购", "打样", "样机", "多少钱", "费用", "特殊", "需求",
    "的", "吗", "呢",
)
CHAT_VERIFIED_FALLBACK_PAGES = {
    "product": [
        {
            "title": "气体传感产品总览",
            "url": "/pages/gassensing/all-products.html",
            "type": "overview",
            "snippet": "查看气体传感器、检测模块、报警器与分析仪产品。",
            "_score": 210,
        },
        {
            "title": "生物传感",
            "url": "/pages/biosensing/",
            "type": "overview",
            "snippet": "查看碳基生物传感平台、检测芯片与相关产品。",
            "_score": 180,
        },
    ],
    "solution": [
        {
            "title": "解决方案",
            "url": "/pages/solutions/solutions-index.html",
            "type": "overview",
            "snippet": "元芯传感行业解决方案总览，覆盖氢能、电力、环境、储能、检漏与定制化传感场景。",
            "_score": 250,
        },
        {
            "title": "氢能源产业链解决方案",
            "url": "/pages/solutions/industry-hydrogen.html",
            "type": "solution",
            "snippet": "面向制氢、储氢、运氢、加氢与用氢环节的氢安全监测方案。",
            "_score": 220,
        },
        {
            "title": "智慧电力安全解决方案",
            "url": "/pages/solutions/industry-power-safety.html",
            "type": "solution",
            "snippet": "面向电力设备与变压器油中氢监测的安全预警方案。",
            "_score": 205,
        },
        {
            "title": "工业检漏监测解决方案",
            "url": "/pages/solutions/industry-leak-detection.html",
            "type": "solution",
            "snippet": "面向工业管线、设备密封性与示踪检漏的监测方案。",
            "_score": 195,
        },
        {
            "title": "环境气体监测解决方案",
            "url": "/pages/solutions/industry-environment.html",
            "type": "solution",
            "snippet": "面向环境气体连续监测、风险预警与数据化管理的解决方案。",
            "_score": 185,
        },
        {
            "title": "储能锂电池热失控预警解决方案",
            "url": "/pages/solutions/industry-energy-storage.html",
            "type": "solution",
            "snippet": "面向储能电站与锂电池安全的早期气体预警方案。",
            "_score": 175,
        },
        {
            "title": "定制化传感解决方案",
            "url": "/pages/solutions/custom-solutions.html",
            "type": "solution",
            "snippet": "针对特殊应用场景提供量身定制的生物与化学传感方案。",
            "_score": 165,
        },
    ],
    "custom": [
        {
            "title": "定制服务",
            "url": "/pages/customization/",
            "type": "custom",
            "snippet": "从传感器芯片到定制仪表的一站式解决方案，支持按应用需求定制开发。",
            "_score": 260,
        },
        {
            "title": "半导体器件与微纳工艺定制化服务",
            "url": "/pages/customization/semiconductor_device_customization.html",
            "type": "custom",
            "snippet": "覆盖气敏芯片设计、MEMS微热板加工、敏感薄膜沉积、封装测试等全链条定制服务。",
            "_score": 240,
        },
        {
            "title": "生物传感芯片定制服务",
            "url": "/pages/biosensing/custom_bio_sensor_chip.html",
            "type": "custom",
            "snippet": "基于碳基/氧化物半导体 MEMS 平台，提供芯片结构设计、表面修饰到封装测试的一站式定制。",
            "_score": 215,
        },
    ],
    "contact": [
        {
            "title": "联系我们",
            "url": "/pages/contact/contact.html",
            "type": "contact",
            "snippet": "获取产品咨询、报价、方案支持与售后服务。",
            "_score": 999,
        },
        {
            "title": "在线留言",
            "url": "/pages/contact/feedback.html",
            "type": "contact",
            "snippet": "提交需求、报价咨询、样机申请与售后问题。",
            "_score": 900,
        },
    ],
}


def _normalize_chat_text(value) -> str:
    return str(value or "").strip()


def _extract_ascii_tokens(text: str) -> list[str]:
    seen = set()
    output = []
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,}", str(text or "")):
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def _infer_page_context(page_url: str, page_title: str = "") -> str:
    combined = f"{page_url} {page_title}".lower()
    if "/pages/biosensing/" in combined:
        return "biosensing"
    if "/pages/gassensing/" in combined or "/pages/measurement/" in combined:
        return "gassensing"
    if "/pages/solutions/" in combined:
        return "solutions"
    return ""


def _sanitize_recommendation_url(url: str) -> str:
    return _dep("sanitize_public_link_url")(_normalize_chat_text(url), default="")


def _url_is_verified_public_page(url: str) -> bool:
    value = _sanitize_recommendation_url(url)
    if not value:
        return False
    if value.startswith(("http://", "https://", "//")):
        return False
    if value == "/":
        return True
    path = value.split("?", 1)[0].split("#", 1)[0]
    helpers = current_app.extensions.get("yx_public_site_search", {})
    resolve_page = helpers.get("resolve_page")
    if callable(resolve_page):
        try:
            return bool(resolve_page(path))
        except Exception:
            pass
    try:
        root = Path(current_app.root_path).resolve()
        # Flask root_path is pinned to the repo root in this app.
        normalized = path.strip("/")
        if not normalized:
            return True
        candidates = [root / normalized]
        if path.endswith("/"):
            candidates.append(root / normalized / "index.html")
        if not normalized.endswith(".html"):
            candidates.append(root / f"{normalized}.html")
            candidates.append(root / normalized / "index.html")
        for candidate in candidates:
            candidate = candidate.resolve()
            if root in candidate.parents or candidate == root:
                if candidate.is_file():
                    return True
    except Exception:
        pass
    return False


def _detect_recommendation_intent(user_message: str) -> dict:
    text = _normalize_chat_text(user_message)
    hits = {}
    for intent, keywords in CHAT_RECOMMENDATION_KEYWORDS.items():
        hits[intent] = [word for word in keywords if word in text]

    explicit_keywords = {
        "product": ["产品", "型号", "参数", "选型", "检测", "传感器", "报警器", "模块", "检测仪", "量程", "推荐", "芯片", "器件"],
        "solution": ["方案", "场景", "应用", "行业", "部署", "工况", "解决", "系统"],
        "custom": ["定制", "定制化", "开发", "特殊需求", "开发需求", "非标", "客制化", "微纳加工", "工艺定制", "芯片定制", "封装", "专门做", "能做吗"],
        "contact": ["联系", "电话", "邮箱", "地址", "售后", "对接", "客服"],
        "quote": ["报价", "价格", "采购", "打样", "样机", "多少钱", "费用"],
    }
    for intent, keywords in explicit_keywords.items():
        bucket = hits.setdefault(intent, [])
        for word in keywords:
            if word in text and word not in bucket:
                bucket.append(word)

    primary = ""
    for candidate in ("quote", "contact", "custom", "solution", "product"):
        if hits.get(candidate):
            primary = candidate
            break

    return {
        "primary": primary,
        "should_recommend": bool(primary),
        "hits": hits,
        "ascii_tokens": _extract_ascii_tokens(text),
    }


def _classify_recommendation_url(url: str) -> str:
    path = _normalize_chat_text(url).lower()
    if not path:
        return "other"
    if "/pages/contact/" in path:
        return "contact"
    if (
        "/pages/customization/" in path
        or path in {"/pages/solutions/custom-solutions.html", "/pages/biosensing/custom_bio_sensor_chip.html"}
        or "/pages/research/micro-nano.html" in path
        or "/pages/about/micro-nano.html" in path
    ):
        return "custom"
    if path in {
        "/pages/gassensing/all-products.html",
        "/pages/biosensing/",
        "/pages/biosensing/index.html",
        "/pages/solutions/solutions-index.html",
    }:
        return "overview"
    if "/pages/solutions/" in path or "/pages/gassensing/cases/" in path:
        return "solution"
    if "/pages/gassensing/" in path or "/pages/biosensing/" in path:
        return "product"
    return "other"


def _candidate_matches_context(url: str, page_context: str) -> bool:
    path = _normalize_chat_text(url).lower()
    if not page_context:
        return False
    if page_context == "gassensing":
        return "/pages/gassensing/" in path or "/pages/measurement/" in path or "/pages/solutions/" in path
    if page_context == "biosensing":
        return "/pages/biosensing/" in path or "/pages/customization/" in path or "custom-solutions" in path
    if page_context == "solutions":
        return "/pages/solutions/" in path
    return False


def _candidate_title(item: dict) -> str:
    return (
        _normalize_chat_text(item.get("title"))
        or _normalize_chat_text(item.get("cardTitle"))
        or _normalize_chat_text(item.get("displayName"))
        or _normalize_chat_text(item.get("shortName"))
        or _normalize_chat_text(item.get("name"))
        or _normalize_chat_text(item.get("id"))
    )


def _candidate_snippet(item: dict) -> str:
    return (
        _normalize_chat_text(item.get("snippet"))
        or _normalize_chat_text(item.get("cardSummary"))
        or _normalize_chat_text(item.get("description"))
    )[:180]


def _build_product_public_url(product: dict) -> str:
    product_id = _normalize_chat_text(product.get("id"))
    if not product_id or product_id in {"index", "all-products"}:
        return ""
    if product_id.startswith("../customization/"):
        slug = product_id.replace("../customization/", "").strip("/")
        return f"/pages/customization/{slug}.html"
    if product_id.startswith("../biosensing/"):
        slug = product_id.replace("../biosensing/", "").strip("/")
        return f"/pages/biosensing/{slug}.html"
    return f"/pages/gassensing/{product_id}.html"


def _score_structured_product(product: dict, user_message: str, intent: dict, page_context: str) -> int:
    title = _candidate_title(product)
    snippet = _candidate_snippet(product)
    categories = " ".join([str(item) for item in product.get("categories", []) if item])
    industry = " ".join([str(item) for item in product.get("industryCategories", []) if item])
    combined = f"{title} {snippet} {categories} {industry} {_normalize_chat_text(product.get('id'))}".lower()
    score = 0
    query = _normalize_chat_text(user_message).lower()
    if query and query in combined:
        score += 90
    for token in intent.get("ascii_tokens", []):
        if token in combined:
            score += 35
    for words in intent.get("hits", {}).values():
        for word in words:
            if word.lower() in combined:
                score += 18
    if intent.get("primary") == "product":
        score += 22
    if intent.get("primary") == "custom":
        if any(word in combined for word in ("定制", "custom", "微纳", "开发", "封装")):
            score += 55
        else:
            score += 12
    if intent.get("primary") in {"quote", "contact"}:
        score += 10
    if _candidate_matches_context(_build_product_public_url(product), page_context):
        score += 24
    if any(category in {"sensor", "module", "detector", "alarm", "system", "iot", "service"} for category in product.get("categories", [])):
        score += 8
    return score


def _build_contact_recommendation() -> dict:
    item = dict(CHAT_VERIFIED_FALLBACK_PAGES["contact"][0])
    item["cta_label"] = RECOMMENDATION_CTA_LABELS["contact"]
    return item


def _recommendation_intent_label(intent: dict) -> str:
    labels = {
        "product": "产品咨询",
        "solution": "方案咨询",
        "custom": "定制开发",
        "contact": "联系咨询",
        "quote": "报价采购",
    }
    return labels.get(intent.get("primary") or "", "通用咨询")


def _build_custom_recommendation_candidates(user_message: str, page_url: str, page_title: str, intent: dict) -> list[dict]:
    page_context = _infer_page_context(page_url, page_title)
    custom_pages = [dict(item) for item in CHAT_VERIFIED_FALLBACK_PAGES["custom"]]
    custom_pages.append(
        {
            "title": "定制化传感解决方案",
            "url": "/pages/solutions/custom-solutions.html",
            "type": "solution",
            "snippet": "面向特殊应用场景提供量身定制的生物与化学传感方案。",
            "_score": 225,
        }
    )
    custom_pages.append(
        {
            "title": "传感器微纳加工",
            "url": "/pages/research/micro-nano.html",
            "type": "custom",
            "snippet": "支持微纳图形、叉指电极、MEMS结构等高灵活性加工服务。",
            "_score": 190,
        }
    )
    query = _normalize_chat_text(user_message).lower()
    preferred = "bio" if page_context == "biosensing" or any(word in query for word in ("生物", "芯片", "微流控", "修饰")) else ""
    for item in custom_pages:
        text = f"{item['title']} {item['snippet']} {item['url']}".lower()
        for words in intent.get("hits", {}).values():
            for word in words:
                if word.lower() in text:
                    item["_score"] += 20
        if preferred == "bio" and "/pages/biosensing/" in item["url"]:
            item["_score"] += 45
        elif page_context == "gassensing" and "/pages/customization/" in item["url"]:
            item["_score"] += 35
        elif page_context == "solutions" and "/pages/solutions/" in item["url"]:
            item["_score"] += 35
        item["cta_label"] = RECOMMENDATION_CTA_LABELS.get(item["type"], RECOMMENDATION_CTA_LABELS["overview"])
    return custom_pages


def _build_solution_recommendation_candidates(user_message: str, page_url: str, page_title: str, intent: dict) -> list[dict]:
    page_context = _infer_page_context(page_url, page_title)
    query = _normalize_chat_text(user_message).lower()
    solution_pages = [dict(item) for item in CHAT_VERIFIED_FALLBACK_PAGES["solution"]]
    keyword_weights = (
        (("氢", "氢能", "加氢", "制氢"), "industry-hydrogen", 70),
        (("电力", "变压器", "油中氢"), "industry-power-safety", 70),
        (("检漏", "泄漏", "示踪"), "industry-leak-detection", 70),
        (("环境", "空气", "监测"), "industry-environment", 60),
        (("储能", "锂电", "电池", "热失控"), "industry-energy-storage", 70),
        (("定制", "特殊", "非标"), "custom-solutions", 55),
    )
    for item in solution_pages:
        url = item["url"]
        for words, marker, weight in keyword_weights:
            if marker in url and any(word in query for word in words):
                item["_score"] += weight
        if page_context == "solutions" and "/pages/solutions/" in url:
            item["_score"] += 35
        item["cta_label"] = RECOMMENDATION_CTA_LABELS.get(item["type"], RECOMMENDATION_CTA_LABELS["overview"])
    return solution_pages


def _load_public_search_results(query: str, limit: int = 12) -> list[dict]:
    try:
        helpers = current_app.extensions.get("yx_public_site_search", {})
        search_pages = helpers.get("search_pages")
        if callable(search_pages):
            return list(search_pages(query, limit)) if query else []
    except Exception:
        return []
    return []


def _build_search_first_query(user_message: str, page_title: str, intent: dict) -> str:
    text = _normalize_chat_text(user_message)
    terms = []
    for words in intent.get("hits", {}).values():
        for word in words:
            if word not in terms:
                terms.append(word)
    fallback = CHAT_SEARCH_FALLBACK_QUERIES.get(intent.get("primary") or "", "")
    parts = [text]
    if terms:
        parts.append(" ".join(terms[:6]))
    if fallback:
        parts.append(fallback)
    return " ".join([part for part in parts if part]).strip()


def _specific_query_terms(user_message: str, intent: dict) -> list[str]:
    text = _normalize_chat_text(user_message)
    cleaned = text
    for phrase in CHAT_SPECIFIC_QUERY_STOP_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    for words in intent.get("hits", {}).values():
        for word in words:
            cleaned = cleaned.replace(word, " ")
    tokens = []
    seen = set()
    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_.-]{1,}", cleaned):
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(key)
    return tokens[:6]


def _candidate_matches_specific_terms(item: dict, terms: list[str]) -> bool:
    if not terms:
        return True
    combined = " ".join([
        _normalize_chat_text(item.get("title")),
        _normalize_chat_text(item.get("snippet")),
        _normalize_chat_text(item.get("url")),
    ]).lower()
    return any(term.lower() in combined for term in terms)


def _search_result_to_recommendation(item: dict, *, intent: dict, page_context: str) -> dict:
    url = _sanitize_recommendation_url(item.get("url"))
    page_type = item.get("page_type") or _classify_recommendation_url(url)
    if page_type in CHAT_SEARCH_BANNED_PAGE_TYPES:
        return {}
    primary = intent.get("primary") or ""
    custom_hits = intent.get("hits", {}).get("custom") or []
    if primary == "solution" and page_type == "custom" and not custom_hits:
        return {}
    if primary == "product" and page_type in {"custom", "solution"}:
        return {}
    if not _url_is_verified_public_page(url):
        return {}
    score = int(item.get("score") or 0)
    score += RECOMMENDATION_PAGE_TYPE_WEIGHT.get(page_type, 0)
    if _candidate_matches_context(url, page_context):
        score += 28
    if primary == "product" and page_type == "product":
        score += 35
    elif primary == "solution" and page_type in {"solution", "overview"}:
        score += 35
    elif primary == "custom" and page_type in {"custom", "solution"}:
        score += 55 if page_type == "custom" else 24
    elif primary in {"contact", "quote"} and page_type == "contact":
        score += 45
    return {
        "title": _candidate_title(item),
        "url": url,
        "type": "custom" if page_type == "custom" else page_type,
        "snippet": _candidate_snippet(item),
        "cta_label": RECOMMENDATION_CTA_LABELS.get(page_type, RECOMMENDATION_CTA_LABELS["overview"]),
        "_score": score,
        "_source": "site_search",
        "_business_line": item.get("business_line", ""),
    }


def _build_search_first_recommendations(user_message: str, page_url: str, page_title: str, intent: dict) -> list[dict]:
    page_context = _infer_page_context(page_url, page_title)
    query = _build_search_first_query(user_message, page_title, intent)
    specific_terms = _specific_query_terms(user_message, intent)
    candidates = []
    for item in _load_public_search_results(query, limit=18):
        candidate = _search_result_to_recommendation(item, intent=intent, page_context=page_context)
        if candidate and _candidate_matches_specific_terms(candidate, specific_terms):
            candidates.append(candidate)
    return candidates


def _verified_fallback_candidates(primary: str) -> list[dict]:
    key = "contact" if primary == "quote" else primary
    candidates = []
    for item in CHAT_VERIFIED_FALLBACK_PAGES.get(key, []):
        candidate = dict(item)
        candidate["url"] = _sanitize_recommendation_url(candidate.get("url"))
        if not _url_is_verified_public_page(candidate.get("url")):
            continue
        candidate["cta_label"] = RECOMMENDATION_CTA_LABELS.get(candidate.get("type"), RECOMMENDATION_CTA_LABELS["overview"])
        candidates.append(candidate)
    return candidates


def _build_search_recommendations(user_message: str, page_url: str, page_title: str, intent: dict) -> list[dict]:
    page_context = _infer_page_context(page_url, page_title)
    query = _normalize_chat_text(user_message)
    search_query = query
    if intent.get("primary") == "custom":
        custom_terms = []
        for word in ("定制化", "定制服务", "特殊开发", "开发需求", "非标", "微纳加工", "芯片定制", "封装测试"):
            if word in query and word not in custom_terms:
                custom_terms.append(word)
        search_query = " ".join(custom_terms) or f"{query} 定制服务 微纳加工"
    results = []
    for item in _load_public_search_results(search_query, limit=12):
        url = _normalize_chat_text(item.get("url"))
        page_type = _classify_recommendation_url(url)
        if page_type in CHAT_SEARCH_BANNED_PAGE_TYPES:
            continue
        if intent.get("primary") == "solution" and page_type == "custom" and not (intent.get("hits", {}).get("custom") or []):
            continue
        if intent.get("primary") == "product" and page_type in {"custom", "solution"}:
            continue
        if not _url_is_verified_public_page(url):
            continue
        score = int(item.get("score") or 0)
        score += RECOMMENDATION_PAGE_TYPE_WEIGHT.get(page_type, 0)
        if _candidate_matches_context(url, page_context):
            score += 28
        if query and query.lower() in _normalize_chat_text(item.get("title")).lower():
            score += 16
        if intent.get("primary") == "product" and page_type == "product":
            score += 22
        if intent.get("primary") == "solution" and page_type == "solution":
            score += 22
        if intent.get("primary") == "custom" and page_type in {"custom", "solution"}:
            score += 55 if page_type == "custom" else 24
        if intent.get("primary") in {"contact", "quote"} and page_type == "contact":
            score += 40
        if intent.get("primary") == "solution" and page_type == "product":
            score += 8
        results.append(
            {
                "title": _candidate_title(item),
                "url": _sanitize_recommendation_url(url),
                "type": page_type,
                "snippet": _candidate_snippet(item),
                "cta_label": RECOMMENDATION_CTA_LABELS.get(page_type, RECOMMENDATION_CTA_LABELS["overview"]),
                "_score": score,
            }
        )
    return results


def _build_structured_product_recommendations(user_message: str, page_url: str, page_title: str, intent: dict) -> list[dict]:
    page_context = _infer_page_context(page_url, page_title)
    candidates = []
    product_sources = []
    try:
        product_sources.extend(_dep("get_gassensing_products_with_settings")() or [])
    except Exception:
        pass
    try:
        product_sources.extend(_dep("get_biosensing_products_with_settings_data")() or [])
    except Exception:
        pass

    for product in product_sources:
        if product.get("hidden"):
            continue
        url = _sanitize_recommendation_url(_build_product_public_url(product))
        if not url:
            continue
        if not _url_is_verified_public_page(url):
            continue
        score = _score_structured_product(product, user_message, intent, page_context)
        if score < 45:
            continue
        page_type = _classify_recommendation_url(url)
        candidates.append(
            {
                "title": _candidate_title(product),
                "url": url,
                "type": "custom" if page_type == "custom" else "product",
                "snippet": _candidate_snippet(product),
                "cta_label": RECOMMENDATION_CTA_LABELS["custom"] if page_type == "custom" else RECOMMENDATION_CTA_LABELS["product"],
                "_score": score,
            }
        )
    return candidates


def _merge_recommendation_candidates(
    intent: dict,
    search_candidates: list[dict],
    product_candidates: list[dict],
    custom_candidates: list[dict] | None = None,
    solution_candidates: list[dict] | None = None,
) -> list[dict]:
    primary = intent.get("primary") or ""
    merged = {}

    def remember(item: dict):
        url = _sanitize_recommendation_url(item.get("url"))
        if not url:
            return
        if not _url_is_verified_public_page(url):
            return
        item = dict(item)
        item["url"] = url
        existing = merged.get(url)
        if not existing or item.get("_score", 0) > existing.get("_score", 0):
            merged[url] = item

    for item in search_candidates:
        remember(item)
    for item in product_candidates:
        remember(item)
    if primary not in {"custom", "solution"}:
        for item in custom_candidates or []:
            remember(item)
    if primary == "custom":
        for item in custom_candidates or []:
            remember(item)
    if primary == "solution":
        for item in solution_candidates or []:
            remember(item)

    if primary in {"contact", "quote"}:
        remember(_build_contact_recommendation())

    items = list(merged.values())
    if not items:
        return []

    for item in items:
        item_type = item.get("type", "other")
        if primary == "product" and item_type == "product":
            item["_score"] += 35
        elif primary == "solution" and item_type == "solution":
            item["_score"] += 35
        elif primary == "solution" and item_type == "overview":
            item["_score"] += 30
        elif primary == "custom" and item_type == "custom":
            item["_score"] += 55
        elif primary == "custom" and item_type == "solution":
            item["_score"] += 24
        elif primary in {"contact", "quote"} and item_type == "contact":
            item["_score"] += 45
        elif primary == "solution" and item_type == "product":
            item["_score"] += 8
        elif primary == "product" and item_type == "solution":
            item["_score"] += 6

    items.sort(key=lambda entry: entry.get("_score", 0), reverse=True)

    output = []
    product_count = 0
    solution_count = 0
    for item in items:
        item_type = item.get("type", "other")
        if item_type == "product":
            if primary == "solution" and product_count >= 2:
                continue
            if primary != "solution" and product_count >= 3:
                continue
            product_count += 1
        elif item_type == "solution":
            if primary == "solution" and solution_count >= 2:
                continue
            solution_count += 1
        elif item_type == "overview":
            if primary not in {"solution", "contact", "quote"} and len(output) >= 2:
                continue
        if len(output) >= 3:
            break
        output.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "type": item_type,
                "snippet": item.get("snippet", ""),
                "cta_label": item.get("cta_label") or RECOMMENDATION_CTA_LABELS.get(item_type, RECOMMENDATION_CTA_LABELS["overview"]),
            }
        )
    return output


def build_chat_recommendation_context(user_message: str, page_url: str, page_title: str) -> dict:
    intent = _detect_recommendation_intent(user_message)
    search_first_candidates = _build_search_first_recommendations(user_message, page_url, page_title, intent)
    specific_terms = _specific_query_terms(user_message, intent)
    allow_intent_fallbacks = not specific_terms or bool(search_first_candidates)
    search_candidates = _build_search_recommendations(user_message, page_url, page_title, intent)
    if specific_terms:
        search_candidates = [
            item for item in search_candidates
            if _candidate_matches_specific_terms(item, specific_terms)
        ]
    product_candidates = _build_structured_product_recommendations(user_message, page_url, page_title, intent)
    if specific_terms:
        product_candidates = [
            item for item in product_candidates
            if _candidate_matches_specific_terms(item, specific_terms)
        ]
    custom_candidates = (
        _build_custom_recommendation_candidates(user_message, page_url, page_title, intent)
        if intent.get("primary") == "custom" and allow_intent_fallbacks
        else []
    )
    solution_candidates = (
        _build_solution_recommendation_candidates(user_message, page_url, page_title, intent)
        if intent.get("primary") == "solution" and allow_intent_fallbacks
        else []
    )
    fallback_candidates = _verified_fallback_candidates(intent.get("primary") or "")
    if not intent.get("primary") or not allow_intent_fallbacks:
        fallback_candidates = []
    recommendations = _merge_recommendation_candidates(
        intent,
        search_first_candidates + search_candidates,
        product_candidates,
        custom_candidates + fallback_candidates,
        solution_candidates,
    )
    if intent.get("primary") in {"contact", "quote"}:
        fallback = _build_contact_recommendation()
        if not recommendations:
            recommendations = [{
                "title": fallback["title"],
                "url": fallback["url"],
                "type": fallback["type"],
                "snippet": fallback["snippet"],
                "cta_label": fallback["cta_label"],
            }]
    return {
        "intent": intent,
        "query": _build_search_first_query(user_message, page_title, intent),
        "search_result_count": len(search_first_candidates),
        "site_candidates": search_first_candidates,
        "recommendations": recommendations,
    }


def build_chat_recommendations(user_message: str, page_url: str, page_title: str) -> list[dict]:
    return build_chat_recommendation_context(user_message, page_url, page_title).get("recommendations") or []


def build_agent_query_tokens(user_message: str, page_title: str, intent: dict | None = None) -> list[str]:
    intent = intent or _detect_recommendation_intent(user_message)
    keywords = []
    for words in intent.get("hits", {}).values():
        for word in words:
            if word not in keywords:
                keywords.append(word)
    if not keywords:
        primary = intent.get("primary") or ""
        fallback = CHAT_SEARCH_FALLBACK_QUERIES.get(primary, "")
        keywords = [word for word in fallback.split() if word][:3] or _extract_ascii_tokens(user_message)[:3]

    query_tokens = []
    if page_title:
        query_tokens.append(page_title[:18])
    query_tokens.extend(keywords[:3])
    if not query_tokens:
        query_tokens.append("站内知识")
    return query_tokens[:4]


def build_agent_runtime_context(user_message: str, page_url: str, page_title: str) -> dict:
    recommendation_context = build_chat_recommendation_context(
        user_message=user_message,
        page_url=page_url,
        page_title=page_title,
    )
    intent = recommendation_context.get("intent") or _detect_recommendation_intent(user_message)
    recommendations = recommendation_context.get("recommendations") or []
    return {
        "intent": intent,
        "query_tokens": build_agent_query_tokens(user_message, page_title, intent),
        "search_query": recommendation_context.get("query", ""),
        "search_result_count": recommendation_context.get("search_result_count", 0),
        "specific_terms": _specific_query_terms(user_message, intent),
        "site_candidates": recommendation_context.get("site_candidates", []),
        "recommendations": recommendations,
    }


def build_agent_status_updates(
    user_message: str,
    page_url: str,
    page_title: str,
    recommendations: list[dict],
    runtime_context: dict | None = None,
) -> list[dict]:
    runtime_context = runtime_context or {}
    intent = runtime_context.get("intent") or _detect_recommendation_intent(user_message)
    query_tokens = runtime_context.get("query_tokens") or build_agent_query_tokens(user_message, page_title, intent)
    found_count = runtime_context.get("search_result_count")
    if found_count is None:
        found_count = len(recommendations)

    updates = [
        {"label": "元芯AI正在分析您的问题", "detail": "结合当前页面与历史对话判断意图"},
        {"label": "已理解您的问题", "detail": f"识别意图：{_recommendation_intent_label(intent)}"},
        {"label": "检索关键词", "detail": " / ".join(query_tokens[:4])},
        {"label": "开始检索官网", "detail": f"找到 {found_count} 个页面，筛选出 {len(recommendations)} 个推荐入口"},
    ]
    if page_url:
        updates.insert(2, {"label": "结合当前页面上下文", "detail": page_url[:80]})
    return updates


def build_agent_completion_status(recommendations: list[dict]) -> dict:
    if recommendations:
        return {
            "label": "已完成答案整理",
            "detail": f"同步生成 {len(recommendations)} 个推荐入口",
        }
    return {
        "label": "已完成答案整理",
        "detail": "官网未命中完全匹配入口，正在输出保守回复",
    }


def build_site_search_prompt_context(runtime_context: dict) -> str:
    recommendations = runtime_context.get("recommendations") or []
    candidates = runtime_context.get("site_candidates") or []
    search_query = _normalize_chat_text(runtime_context.get("search_query"))
    result_count = int(runtime_context.get("search_result_count") or 0)
    items = [
        item for item in recommendations
        if _normalize_chat_text(item.get("title")) and _normalize_chat_text(item.get("url"))
    ][:3]
    source_items = [
        item for item in candidates
        if _normalize_chat_text(item.get("title")) and _normalize_chat_text(item.get("url"))
    ][:5]
    rows = []
    for idx, item in enumerate(source_items or items, 1):
        title = _normalize_chat_text(item.get("title"))
        url = _normalize_chat_text(item.get("url"))
        snippet = _normalize_chat_text(item.get("snippet"))
        item_type = _normalize_chat_text(item.get("type")) or "overview"
        row = f"{idx}. [{item_type}] {title} - {url}"
        if snippet:
            row += f"：{snippet}"
        rows.append(row)
    recommendation_rows = []
    for idx, item in enumerate(items, 1):
        recommendation_rows.append(f"{idx}. {item.get('title', '')} - {item.get('url', '')}")

    if rows:
        return (
            "本轮回答必须基于以下官网站内检索结果和知识库内容。"
            "这些 URL 均已由后端校验为真实官网页面，可作为用户入口；"
            "禁止声称官网页面维护中、技术升级、暂时无法访问、没有页面或无法打开。"
            "如果用户询问官网是否有相关界面/页面，必须明确回答“官网有相关页面”，并引导点击回答下方推荐入口。"
            "不要把完整链接堆进正文，前端会在回答下方单独展示推荐入口。\n"
            f"检索词：{search_query or '站内知识'}\n"
            f"检索命中：{result_count} 个页面\n"
            "官网检索结果：\n" + "\n".join(rows)
            + ("\n推荐入口：\n" + "\n".join(recommendation_rows) if recommendation_rows else "")
        )
    return (
        "本轮已执行官网站内检索，但没有找到完全匹配的官网页面。"
        "回答时必须说明“暂未在官网检索到完全匹配页面”，可以基于公司知识库给出保守建议并引导联系咨询；"
        "如果用户询问的是某个具体产品、具体场景或具体方案，不要把泛化产品/方案页面说成已经匹配该具体需求；"
        "禁止编造官网页面、URL、维护中、技术升级、暂时无法访问或没有页面等状态。"
        f"\n检索词：{search_query or '站内知识'}"
    )


def build_recommendation_prompt_context(recommendations: list[dict]) -> str:
    return build_site_search_prompt_context({
        "recommendations": recommendations,
        "site_candidates": recommendations,
        "search_result_count": len(recommendations or []),
    })



# 路由注册入口。
def register_ai_chatbot_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
    get_turnstile_settings=None,
    verify_turnstile_token=None,
    require_super_admin_api,
    get_client_ip,
    resolve_ip_location,
    sanitize_public_link_url,
    validate_uploaded_pdf,
    knowledge_dir,
    conversation_log_file,
    pdf_support,
    pypdf2_module,
    requests_support,
    requests_module,
    httpx_support,
    httpx_module,
    get_gassensing_products_with_settings,
    get_biosensing_products_with_settings_data,
):
    """注册聊天机器人、知识库与配置相关路由，并完成共享依赖注入。"""
    configure_ai_chatbot(
        get_config=get_config,
        update_config=update_config,
        get_turnstile_settings=get_turnstile_settings,
        verify_turnstile_token=verify_turnstile_token,
        require_super_admin_api=require_super_admin_api,
        get_client_ip=get_client_ip,
        resolve_ip_location=resolve_ip_location,
        sanitize_public_link_url=sanitize_public_link_url,
        validate_uploaded_pdf=validate_uploaded_pdf,
        knowledge_dir=knowledge_dir,
        conversation_log_file=conversation_log_file,
        pdf_support=pdf_support,
        pypdf2_module=pypdf2_module,
        requests_support=requests_support,
        requests_module=requests_module,
        httpx_support=httpx_support,
        httpx_module=httpx_module,
        get_gassensing_products_with_settings=get_gassensing_products_with_settings,
        get_biosensing_products_with_settings_data=get_biosensing_products_with_settings_data,
    )

    @app.route("/api/chatbot/chat", methods=["POST"])
    @rate_limit_chatbot()
    def chatbot_chat():
        config = get_chatbot_config()
        if not config["enabled"]:
            return jsonify({"success": False, "message": "智能客服暂时不可用"}), 503

        data = request.get_json(silent=True) or {}
        # 公开接口的输入长度硬上限：防止近 128MB 的 JSON 被整体转发给
        # LLM（巨额 token 成本）并原样写入对话日志（磁盘耗尽）。
        CHATBOT_MAX_MESSAGE_CHARS = 4000
        user_message = str(data.get("message") or "").strip()[:CHATBOT_MAX_MESSAGE_CHARS]
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []
        session_id = str(data.get("session_id") or "").strip()[:80]
        page_url = str(data.get("page_url") or "").strip()[:500]
        page_title = str(data.get("page_title") or "").strip()[:200]
        requester_ip = "未知"
        requester_location = "未知"
        try:
            requester_ip = str(_dep("get_client_ip")() or "").strip() or "未知"
        except Exception:
            requester_ip = "未知"
        try:
            requester_location = (
                str(_dep("resolve_ip_location")(requester_ip) or "").strip() or "未知"
            )
        except Exception:
            requester_location = "未知"
        if not user_message:
            return jsonify({"success": False, "message": "请输入您的问题"}), 400

        knowledge = load_knowledge_base()
        system_prompt = get_chatbot_system_prompt()
        if knowledge:
            system_prompt += f"\n\n以下是公司知识库的相关内容，请参考这些信息回答用户问题：\n{knowledge[:8000]}"

        messages = [{"role": "system", "content": system_prompt}]
        normalized_history = []
        for msg in history[-8:]:
            if not isinstance(msg, dict):
                continue
            role = (
                "assistant"
                if str(msg.get("role") or "").strip() == "assistant"
                else "user"
            )
            content = str(msg.get("content") or "").strip()[:CHATBOT_MAX_MESSAGE_CHARS]
            if not content:
                continue
            normalized_history.append({"role": role, "content": content})
        if (
            normalized_history
            and normalized_history[-1]["role"] == "user"
            and normalized_history[-1]["content"] == user_message
        ):
            normalized_history.pop()
        messages.extend(normalized_history)
        messages.append({"role": "user", "content": user_message})

        def record_chatbot_reply(reply_text, source="ai"):
            try:
                append_chatbot_conversation_log(
                    session_id=session_id,
                    user_message=user_message,
                    assistant_message=reply_text,
                    ip=requester_ip,
                    location=requester_location,
                    page_url=page_url,
                    page_title=page_title,
                    response_source=source,
                    model=config.get("model", ""),
                )
            except Exception as exc:
                app.logger.warning("failed to record chatbot conversation log: %s", exc)

        def emit_status_payload(status_item):
            return f"data: {json.dumps({'status': status_item}, ensure_ascii=False)}\n\n"

        def emit_recommendations_payload(recommendations):
            if not recommendations:
                return ""
            return f"data: {json.dumps({'recommendations': recommendations}, ensure_ascii=False)}\n\n"

        def build_local_fallback_reply(text):
            q = str(text or "").strip()
            q_l = q.lower()

            def has_any(*words):
                return any(w in q_l or w in q for w in words)

            if has_any("报价", "价格", "采购"):
                return "您可以通过在线留言提交需求，我们会安排技术与销售跟进：[在线留言](/pages/contact/feedback.html#feedbackForm)。"
            if has_any("联系", "电话", "留言"):
                return "您可以通过在线留言提交需求，我们会安排技术与销售跟进：[在线留言](/pages/contact/feedback.html#feedbackForm)。"
            if has_any("介绍", "公司", "元芯"):
                return "元芯传感专注于气体传感与检测技术，覆盖传感器、检测模组与行业应用方案。如果您告诉我应用场景，我可以继续给出更具体的产品建议。"
            if has_any("定制", "定制化", "特殊需求", "开发需求", "非标", "客制化", "微纳加工"):
                return "可以的，元芯传感支持传感器芯片、微纳工艺、封装测试与定制仪表开发。您可以先查看定制服务入口：[定制服务](/pages/customization/)，也可以进一步查看[半导体器件与微纳工艺定制化服务](/pages/customization/semiconductor_device_customization.html)。"
            if has_any("产品", "传感器", "氢气", "型号"):
                return "您可以先查看气体传感产品总览页，按场景筛选型号：[查看全部产品](/pages/gassensing/all-products.html)。"
            if has_any("方案", "行业", "应用", "解决"):
                return "行业方案可以从这里进入：[解决方案中心](/pages/solutions/solutions-index.html)。如果您告知工况（温湿度、量程、安装方式），我可以继续细化建议。"
            return "暂未在官网检索到完全匹配页面。建议您通过在线留言提交具体需求，我们会尽快人工回复：[在线留言](/pages/contact/feedback.html#feedbackForm)。"

        fallback_reply = build_local_fallback_reply(user_message)
        use_stream = httpx_support or (
            requests_support and config.get("use_stream", True)
        )

        if use_stream:

            def generate():
                sent_any_content = False
                reply_parts = []
                recommendations = []
                try:
                    yield emit_status_payload(
                        {"label": "元芯AI正在分析您的问题", "detail": "结合当前页面与历史对话判断意图"}
                    )
                    runtime_context = build_agent_runtime_context(
                        user_message=user_message,
                        page_url=page_url,
                        page_title=page_title,
                    )
                    recommendations = runtime_context.get("recommendations") or []
                    recommendation_context = build_site_search_prompt_context(runtime_context)
                    if recommendation_context:
                        messages.insert(-1, {"role": "system", "content": recommendation_context})
                    intent = runtime_context.get("intent") or {}
                    query_tokens = runtime_context.get("query_tokens") or ["站内知识"]
                    found_count = runtime_context.get("search_result_count", len(recommendations))
                    yield emit_status_payload(
                        {"label": "已理解您的问题", "detail": f"识别意图：{_recommendation_intent_label(intent)}"}
                    )
                    if page_url:
                        yield emit_status_payload(
                            {"label": "结合当前页面上下文", "detail": page_url[:80]}
                        )
                    yield emit_status_payload(
                        {"label": "检索关键词", "detail": " / ".join(query_tokens[:4])}
                    )
                    yield emit_status_payload(
                        {"label": "开始检索官网", "detail": f"找到 {found_count} 个页面，筛选出 {len(recommendations)} 个推荐入口"}
                    )
                    generation_detail = "基于官网检索结果组织回复" if recommendations else "未命中完全匹配页面，按保守策略回复"
                    yield emit_status_payload(
                        {"label": "正在生成回答", "detail": generation_detail}
                    )
                    stream = call_openai_api(messages, stream=True)
                    if isinstance(stream, tuple):
                        _, error = stream
                        app.logger.warning("chatbot stream init failed: %s", error)
                        yield emit_status_payload(
                            {"label": "流式通道暂不可用", "detail": "正在切换为备用回答通道"}
                        )
                        sync_response, sync_error = call_openai_api(
                            messages, stream=False
                        )
                        if not sync_error and sync_response:
                            record_chatbot_reply(sync_response, "ai_sync_fallback")
                            yield emit_status_payload(build_agent_completion_status(recommendations))
                            yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                            if recommendations:
                                yield emit_recommendations_payload(recommendations)
                            yield "data: [DONE]\n\n"
                            return
                        app.logger.warning(
                            "chatbot sync fallback after stream init failed: %s",
                            sync_error,
                        )
                        record_chatbot_reply(fallback_reply, "local_fallback")
                        yield emit_status_payload(
                            {"label": "已切换为本地兜底回复", "detail": "外部模型暂时不可用"}
                        )
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                        if recommendations:
                            yield emit_recommendations_payload(recommendations)
                        yield "data: [DONE]\n\n"
                        return
                    for chunk, err in stream:
                        if err:
                            app.logger.warning("chatbot stream chunk failed: %s", err)
                            if not sent_any_content:
                                yield emit_status_payload(
                                    {"label": "流式输出中断", "detail": "正在切换为备用回答通道"}
                                )
                                sync_response, sync_error = call_openai_api(
                                    messages, stream=False
                                )
                                if not sync_error and sync_response:
                                    record_chatbot_reply(
                                        sync_response, "ai_sync_fallback"
                                    )
                                    yield emit_status_payload(build_agent_completion_status(recommendations))
                                    yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                                    if recommendations:
                                        yield emit_recommendations_payload(recommendations)
                                    yield "data: [DONE]\n\n"
                                    return
                                app.logger.warning(
                                    "chatbot sync fallback after stream chunk failed: %s",
                                    sync_error,
                                )
                            fallback_content = (
                                "\n\n" + fallback_reply
                                if sent_any_content
                                else fallback_reply
                            )
                            full_reply = "".join(reply_parts) + fallback_content
                            record_chatbot_reply(
                                full_reply,
                                "partial_ai_plus_fallback"
                                if sent_any_content
                                else "local_fallback",
                            )
                            yield emit_status_payload(
                                {"label": "已补充兜底回复", "detail": "模型输出中断，已自动补齐答复"}
                            )
                            yield f"data: {json.dumps({'content': fallback_content}, ensure_ascii=False)}\n\n"
                            if recommendations:
                                yield emit_recommendations_payload(recommendations)
                            yield "data: [DONE]\n\n"
                            return
                        sent_any_content = True
                        reply_parts.append(chunk)
                        yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                    if not sent_any_content:
                        record_chatbot_reply(fallback_reply, "local_fallback")
                        yield emit_status_payload(
                            {"label": "已切换为本地兜底回复", "detail": "未收到模型有效输出"}
                        )
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    else:
                        record_chatbot_reply("".join(reply_parts), "ai")
                    yield emit_status_payload(build_agent_completion_status(recommendations))
                    if recommendations:
                        yield emit_recommendations_payload(recommendations)
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    app.logger.exception("chatbot stream exception: %s", exc)
                    yield emit_status_payload(
                        {"label": "回答过程出现波动", "detail": "正在尝试恢复并继续回答"}
                    )
                    sync_response, sync_error = call_openai_api(messages, stream=False)
                    if not sync_error and sync_response:
                        record_chatbot_reply(sync_response, "ai_sync_fallback")
                        yield emit_status_payload(build_agent_completion_status(recommendations))
                        yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                        if recommendations:
                            yield emit_recommendations_payload(recommendations)
                        yield "data: [DONE]\n\n"
                        return
                    app.logger.warning(
                        "chatbot sync fallback after stream exception failed: %s",
                        sync_error,
                    )
                    record_chatbot_reply(fallback_reply, "local_fallback")
                    yield emit_status_payload(
                        {"label": "已切换为本地兜底回复", "detail": "服务暂时异常，已自动改用兜底方案"}
                    )
                    yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    if recommendations:
                        yield emit_recommendations_payload(recommendations)
                    yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        runtime_context = build_agent_runtime_context(
            user_message=user_message,
            page_url=page_url,
            page_title=page_title,
        )
        recommendations = runtime_context.get("recommendations") or []
        recommendation_context = build_site_search_prompt_context(runtime_context)
        if recommendation_context:
            messages.insert(-1, {"role": "system", "content": recommendation_context})
        status_updates = build_agent_status_updates(
            user_message=user_message,
            page_url=page_url,
            page_title=page_title,
            recommendations=recommendations,
            runtime_context=runtime_context,
        )

        response, error = call_openai_api(messages, stream=False)
        if error:
            app.logger.warning("chatbot non-stream failed: %s", error)
            record_chatbot_reply(fallback_reply, "local_fallback")
            return jsonify(
                {
                    "success": True,
                    "response": fallback_reply,
                    "recommendations": recommendations,
                    "status_updates": status_updates + [
                        {"label": "已切换为本地兜底回复", "detail": "外部模型暂时不可用"}
                    ],
                }
            )
        record_chatbot_reply(response, "ai")
        return jsonify(
            {
                "success": True,
                "response": response,
                "recommendations": recommendations,
                "status_updates": status_updates + [build_agent_completion_status(recommendations)],
            }
        )

    @app.route("/api/chatbot/history", methods=["GET"])
    @login_required
    def chatbot_history():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        try:
            page = int(request.args.get("page") or "1")
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.args.get("page_size") or "20")
        except (TypeError, ValueError):
            page_size = 20

        page = max(1, page)
        page_size = max(5, min(page_size, 200))

        session_filter = re.sub(
            r"[^a-zA-Z0-9_.-]", "_", str(request.args.get("session_id") or "").strip()
        )[:80]

        with _conversation_log_lock:
            items = list(reversed(load_chatbot_conversation_logs()))

        if session_filter:
            items = [
                item
                for item in items
                if str(item.get("session_id") or "") == session_filter
            ]

        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        if page > total_pages:
            page = total_pages

        start = (page - 1) * page_size
        end = start + page_size
        output = items[start:end]

        return jsonify(
            {
                "items": output,
                "count": len(output),
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages,
                "session_id": session_filter,
            }
        )

    @app.route("/api/chatbot/knowledge", methods=["GET"])
    @login_required
    def list_knowledge_files():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        files = []
        for pdf_path in sorted(_dep("knowledge_dir").glob("*.pdf")):
            if _safe_knowledge_pdf_filename(pdf_path.name) != pdf_path.name:
                continue
            stat = pdf_path.stat()
            files.append(
                {
                    "name": pdf_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=BEIJING_TZ).isoformat(),
                }
            )
        text_entries = [
            _knowledge_text_entry_public(entry)
            for entry in _read_knowledge_text_entries()
        ]
        manual_text = "\n\n".join(
            entry.get("content", "") for entry in text_entries if entry.get("content")
        )
        manual_size = sum(int(entry.get("size") or 0) for entry in text_entries)
        manual_modified = max(
            (str(entry.get("modified_at") or "") for entry in text_entries),
            default="",
        )
        return jsonify(
            {
                "files": files,
                "text_entries": text_entries,
                "pdf_support": _dep("pdf_support"),
                "text_content": manual_text,
                "text_size": manual_size,
                "text_modified": manual_modified,
            }
        )

    @app.route("/api/chatbot/knowledge/upload", methods=["POST"])
    @login_required
    def upload_knowledge_file():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        text_present = "knowledge_text" in request.form
        manual_text = request.form.get("knowledge_text", "") if text_present else ""
        # 单条文本上限 1MB，防止超大文本整体写入知识库 JSON 并在每次
        # 缓存重建时被拼进内存。
        manual_text = manual_text[: 1024 * 1024]
        manual_title = request.form.get("knowledge_title", "")
        files = []
        if "file" in request.files:
            files.extend(request.files.getlist("file"))
        if "files" in request.files:
            files.extend(request.files.getlist("files"))

        files = [file for file in files if file and file.filename]
        has_text = bool(str(manual_text or "").strip())
        if not files and not has_text:
            return jsonify({"success": False, "message": "没有可保存的知识库内容"}), 400

        uploaded = []
        failed = []
        text_entry = None

        if has_text:
            try:
                text_entry = _append_knowledge_text_entry(manual_text, title=manual_title)
            except Exception as exc:
                failed.append(
                    {
                        "filename": "knowledge_text",
                        "message": f"知识库文本保存失败: {str(exc)}",
                    }
                )

        pdf_supported = _dep("pdf_support") and _dep("pypdf2_module") is not None
        if files and not pdf_supported:
            for file in files:
                failed.append(
                    {
                        "filename": file.filename or "",
                        "message": "服务器未安装 PyPDF2，暂不支持 PDF 上传",
                    }
                )
        else:
            for file in files:
                if not file.filename:
                    failed.append({"filename": "", "message": "文件名不能为空"})
                    continue
                if not file.filename.lower().endswith(".pdf"):
                    failed.append({"filename": file.filename, "message": "只支持 PDF 文件"})
                    continue
                if not _dep("validate_uploaded_pdf")(file):
                    failed.append(
                        {"filename": file.filename, "message": "PDF 文件格式无效"}
                    )
                    continue

                # 单文件大小上限：防止超大 PDF 落盘并在公开聊天的缓存重建
                # 中被 PyPDF2 全量解析。
                max_pdf_bytes = 20 * 1024 * 1024
                try:
                    file.stream.seek(0, os.SEEK_END)
                    pdf_size = int(file.stream.tell() or 0)
                    file.stream.seek(0)
                except Exception:
                    pdf_size = 0
                if pdf_size > max_pdf_bytes:
                    failed.append(
                        {"filename": file.filename, "message": "PDF 文件过大（最大 20MB）"}
                    )
                    continue

                filename = _unique_knowledge_pdf_filename(file.filename)
                if not filename:
                    failed.append({"filename": file.filename, "message": "文件名不合法"})
                    continue
                filepath = _dep("knowledge_dir") / filename
                try:
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    file.save(str(filepath))
                    uploaded.append(filename)
                except Exception as exc:
                    failed.append(
                        {"filename": file.filename, "message": f"上传失败: {str(exc)}"}
                    )

        if uploaded:
            reset_knowledge_cache()

        success_parts = []
        if text_entry is not None:
            success_parts.append("文本知识条目已新增")
        if uploaded:
            success_parts.append(f"已上传 {len(uploaded)} 个 PDF 文件")

        response = {
            "success": True,
            "filename": uploaded[0] if uploaded else "",
            "text_saved": text_entry is not None,
            "text_cleared": False,
            "text_entry": (
                _knowledge_text_entry_public(text_entry) if text_entry is not None else None
            ),
            "text_modified": (text_entry or {}).get("modified_at", ""),
            "text_size": (text_entry or {}).get("size", 0),
            "uploaded": uploaded,
            "failed": failed,
        }

        if not success_parts:
            response["success"] = False
            response["message"] = failed[0]["message"] if len(failed) == 1 else "知识库保存失败"
            response["uploaded"] = []
            return jsonify(response), 400

        response["message"] = "，".join(success_parts)
        if failed:
            response["partial_success"] = True
            response["message"] = f'{response["message"]}，{len(failed)} 个项目处理失败'

        return jsonify(response)

    @app.route("/api/chatbot/knowledge/text/<entry_id>", methods=["GET"])
    @login_required
    def get_knowledge_text_entry(entry_id):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        entry = _find_knowledge_text_entry(entry_id)
        if entry is None:
            return jsonify({"success": False, "message": "文本条目不存在"}), 404
        return jsonify({"success": True, "entry": _knowledge_text_entry_public(entry)})

    @app.route("/api/chatbot/knowledge/text/<entry_id>", methods=["PUT"])
    @login_required
    def update_knowledge_text_entry(entry_id):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = request.form.to_dict()
        try:
            entry = _update_knowledge_text_entry(
                entry_id,
                title=data.get("title", ""),
                content=data.get("content", ""),
            )
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        if entry is None:
            return jsonify({"success": False, "message": "文本条目不存在"}), 404
        return jsonify(
            {
                "success": True,
                "message": "文本条目已更新",
                "entry": _knowledge_text_entry_public(entry),
            }
        )

    @app.route("/api/chatbot/knowledge/text/<entry_id>", methods=["DELETE"])
    @login_required
    def delete_knowledge_text_entry(entry_id):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        if not _delete_knowledge_text_entry(entry_id):
            return jsonify({"success": False, "message": "文本条目不存在"}), 404
        return jsonify({"success": True, "message": "文本条目已删除"})

    @app.route("/api/chatbot/knowledge/<filename>/view", methods=["GET"])
    @login_required
    def view_knowledge_file(filename):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        filepath, error = _safe_knowledge_pdf_path(filename)
        if error:
            return jsonify({"success": False, "message": error}), 400
        if not filepath or not filepath.exists() or not filepath.is_file():
            return jsonify({"success": False, "message": "文件不存在"}), 404
        response = send_from_directory(
            str(_dep("knowledge_dir")),
            filepath.name,
            as_attachment=False,
            download_name=filepath.name,
            mimetype="application/pdf",
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route("/api/chatbot/knowledge/<filename>/download", methods=["GET"])
    @login_required
    def download_knowledge_file(filename):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        filepath, error = _safe_knowledge_pdf_path(filename)
        if error:
            return jsonify({"success": False, "message": error}), 400
        if not filepath or not filepath.exists() or not filepath.is_file():
            return jsonify({"success": False, "message": "文件不存在"}), 404
        response = send_from_directory(
            str(_dep("knowledge_dir")),
            filepath.name,
            as_attachment=True,
            download_name=filepath.name,
            mimetype="application/pdf",
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route("/api/chatbot/knowledge/<filename>", methods=["DELETE"])
    @login_required
    def delete_knowledge_file(filename):
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        filepath, error = _safe_knowledge_pdf_path(filename)
        if error:
            return jsonify({"success": False, "message": error}), 400
        if not filepath or not filepath.exists():
            return jsonify({"success": False, "message": "文件不存在"}), 404
        try:
            filepath.unlink()
            reset_knowledge_cache()
            return jsonify({"success": True, "message": "删除成功"})
        except Exception as exc:
            return jsonify({"success": False, "message": f"删除失败: {str(exc)}"}), 500

    @app.route("/api/chatbot/config", methods=["GET"])
    @login_required
    def get_chatbot_config_api():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        config = get_chatbot_config()
        if config["api_key"]:
            # 只返回掩码（尾 4 位）：该接口对持有 chatbot 权限的子管理员开放，
            # 泄露前 8 位会辅助对密钥的离线识别与碰撞。
            config["api_key"] = (
                "***" + config["api_key"][-4:]
                if len(config["api_key"]) > 12
                else "***"
            )
        return jsonify(config)

    @app.route("/api/chatbot/config", methods=["POST"])
    @login_required
    def update_chatbot_config():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        updates = {}
        if (
            "api_key" in data
            and data["api_key"]
            and not str(data["api_key"]).startswith("***")
            and str(data["api_key"]).strip()
        ):
            # strip 后判空再写入：仅提交空白字符时不应静默清空已有密钥。
            updates["chatbot_api_key"] = str(data["api_key"]).strip()
        if "api_base" in data:
            safe_api_base = sanitize_ai_api_base_url(data["api_base"])
            if not safe_api_base:
                return jsonify(
                    {
                        "success": False,
                        "message": "API Base 必须是有效的 http/https 地址，且不能使用 localhost 或内网 IP",
                    }
                ), 400
            updates["chatbot_api_base"] = safe_api_base
        if "model" in data:
            # 与 product-ai 分支一致：规范化为字符串并去除空白，
            # 防止 dict/list 等非法类型原样写入配置导致请求持续失败。
            updates["chatbot_model"] = str(data["model"] or "").strip()
        if "enabled" in data:
            updates["chatbot_enabled"] = bool(data["enabled"])
        if updates:
            _dep("update_config")(updates)
        return jsonify({"success": True, "message": "配置已更新"})

    @app.route("/api/chatbot/rate-limit/config", methods=["GET"])
    @login_required
    def get_rate_limit_config():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        return jsonify(
            {
                "success": True,
                "config": CHATBOT_RATE_LIMIT_CONFIG,
            }
        )

    @app.route("/api/chatbot/rate-limit/config", methods=["POST"])
    @login_required
    def update_rate_limit_config():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "配置数据无效"}), 400
        if "requests_per_minute" in data:
            try:
                val = int(data["requests_per_minute"])
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "每分钟请求数必须是数字"}), 400
            if val < 1 or val > 100:
                return jsonify(
                    {"success": False, "message": "每分钟请求数必须在1-100之间"}
                ), 400
            CHATBOT_RATE_LIMIT_CONFIG["requests_per_minute"] = val
        if "requests_per_day" in data:
            try:
                val = int(data["requests_per_day"])
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "每日请求数必须是数字"}), 400
            if val < 1 or val > 1000:
                return jsonify(
                    {"success": False, "message": "每日请求数必须在1-1000之间"}
                ), 400
            CHATBOT_RATE_LIMIT_CONFIG["requests_per_day"] = val
        _clean_rate_limit_storage()
        return jsonify(
            {
                "success": True,
                "message": "速率限制配置已更新",
                "config": CHATBOT_RATE_LIMIT_CONFIG,
            }
        )

    @app.route("/api/chatbot/rate-limit/stats", methods=["GET"])
    @login_required
    def get_rate_limit_stats():
        denied = _require_chatbot_admin_api()
        if denied:
            return denied
        _clean_rate_limit_storage()
        with _rate_limit_lock:
            total_keys = len(_rate_limit_storage)
            ip_keys = [k for k in _rate_limit_storage.keys() if k.startswith("ip:")]
            session_keys = [
                k for k in _rate_limit_storage.keys() if k.startswith("session:")
            ]
            total_requests = sum(len(v) for v in _rate_limit_storage.values())
        return jsonify(
            {
                "success": True,
                "stats": {
                    "total_unique_identifiers": total_keys,
                    "ip_identifiers": len(ip_keys),
                    "session_identifiers": len(session_keys),
                    "total_tracked_requests": total_requests,
                },
            }
        )

    @app.route("/api/product-ai/config", methods=["GET"])
    @login_required
    def get_product_ai_config_api():
        denied = _dep("require_super_admin_api")()
        if denied:
            return denied
        config = get_product_page_ai_config()
        if config["api_key"]:
            config["api_key"] = (
                config["api_key"][:8] + "..." + config["api_key"][-4:]
                if len(config["api_key"]) > 12
                else "***"
            )
        return jsonify(config)

    @app.route("/api/product-ai/config", methods=["POST"])
    @login_required
    def update_product_ai_config():
        denied = _dep("require_super_admin_api")()
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        updates = {}
        if (
            "api_key" in data
            and data["api_key"]
            and not str(data["api_key"]).startswith("***")
        ):
            updates["product_ai_api_key"] = str(data["api_key"]).strip()
        if "api_base" in data:
            safe_api_base = sanitize_ai_api_base_url(data["api_base"])
            if not safe_api_base:
                current_api_base = str(get_product_page_ai_config().get("api_base") or "").rstrip("/")
                submitted_api_base = str(data.get("api_base") or "").strip().rstrip("/")
                if submitted_api_base and submitted_api_base == current_api_base:
                    safe_api_base = current_api_base
            if not safe_api_base:
                return jsonify(
                    {
                        "success": False,
                        "message": "API Base 必须是有效的 http/https 地址，且不能使用 localhost 或内网 IP",
                    }
                ), 400
            updates["product_ai_api_base"] = safe_api_base
        if "model" in data:
            updates["product_ai_model"] = str(data["model"]).strip()
        if "enabled" in data:
            updates["product_ai_enabled"] = bool(data["enabled"])
        if updates:
            _dep("update_config")(updates)
        return jsonify({"success": True, "message": "产品页编程AI配置已更新"})
