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
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Response, jsonify, request, send_from_directory, stream_with_context

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

_rate_limit_storage = defaultdict(list)
_rate_limit_lock = threading.Lock()

CHATBOT_RATE_LIMIT_CONFIG = {
    "requests_per_minute": 3,
    "requests_per_day": 20,
    "window_seconds": 60,
    "day_window_seconds": 86400,
}

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
8. 请用专业、友好的语气回答问题。如果遇到不确定的问题，请说明当前无法完全确认的部分，并引导用户联系我们的销售团队。"""

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
):
    """配置 AI 聊天机器人模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update(
        {
            "get_config": get_config,
            "update_config": update_config,
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
        }
    )


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f"AI chatbot dependency not configured: {name}")
    return value


def reset_knowledge_cache():
    with _knowledge_lock:
        _knowledge_cache["content"] = ""
        _knowledge_cache["last_updated"] = 0
        _knowledge_cache["files"] = []


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


def rate_limit_chatbot(max_per_minute=10, max_per_day=100):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            _clean_rate_limit_storage()
            client_ip = "unknown"
            try:
                client_ip = str(_dep("get_client_ip")() or "").strip() or "unknown"
            except Exception:
                pass
            ip_key = f"ip:{client_ip}"
            is_allowed_ip_minute, retry_after_ip_minute, count_ip_minute = (
                _check_rate_limit(
                    f"{ip_key}:minute",
                    CHATBOT_RATE_LIMIT_CONFIG.get(
                        "requests_per_minute", max_per_minute
                    ),
                    CHATBOT_RATE_LIMIT_CONFIG.get("window_seconds", 60),
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
                f"{ip_key}:day",
                CHATBOT_RATE_LIMIT_CONFIG.get("requests_per_day", max_per_day),
                CHATBOT_RATE_LIMIT_CONFIG.get("day_window_seconds", 86400),
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

    return parsed._replace(fragment="").geturl()


def get_chatbot_config():
    """从共享站点配置中读取聊天机器人配置。"""
    config = _dep("get_config")()
    return {
        "api_key": config.get("chatbot_api_key", ""),
        "api_base": config.get("chatbot_api_base", "https://api.openai.com/v1"),
        "model": config.get("chatbot_model", "gpt-3.5-turbo"),
        "enabled": config.get("chatbot_enabled", True),
    }


def get_product_page_ai_config():
    """从共享站点配置中读取产品页编码 AI 配置。"""
    config = _dep("get_config")()
    return {
        "enabled": config.get("product_ai_enabled", False),
        "api_key": config.get("product_ai_api_key", ""),
        "api_base": config.get("product_ai_api_base", "https://api.openai.com/v1"),
        "model": config.get("product_ai_model", "gpt-4o-mini"),
    }


def load_knowledge_base():
    """从 PDF 文件加载并缓存知识库内容。"""
    knowledge_dir = _dep("knowledge_dir")
    pdf_support = _dep("pdf_support")
    pypdf2_module = _dep("pypdf2_module")

    with _knowledge_lock:
        pdf_files = list(knowledge_dir.glob("*.pdf"))
        current_files = sorted([f.name for f in pdf_files])
        current_mtime = max([f.stat().st_mtime for f in pdf_files]) if pdf_files else 0

        if (
            _knowledge_cache["files"] == current_files
            and _knowledge_cache["last_updated"] >= current_mtime
            and _knowledge_cache["content"]
        ):
            return _knowledge_cache["content"]

        if not pdf_support or pypdf2_module is None:
            return ""

        knowledge_text = []
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


def call_openai_api_stream(messages):
    """调用兼容大模型接口规范的流式接口。"""
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
        "stream": True,
    }

    requests_support = _dep("requests_support")
    requests_module = _dep("requests_module")
    httpx_support = _dep("httpx_support")
    httpx_module = _dep("httpx_module")

    if httpx_support and httpx_module is not None:

        def gen_httpx():
            try:
                with httpx_module.Client(timeout=60.0) as client:
                    with client.stream(
                        "POST", api_url, json=payload, headers=headers
                    ) as response:
                        if response.status_code != 200:
                            yield None, f"API错误: {response.status_code}"
                            return
                        for line in response.iter_lines():
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    if "choices" in chunk and chunk["choices"]:
                                        delta = chunk["choices"][0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content, None
                                except json.JSONDecodeError:
                                    continue
            except Exception as exc:
                yield None, f"API调用失败: {str(exc)}"

        return gen_httpx()

    if requests_support and requests_module is not None:

        def gen_requests():
            try:
                response = requests_module.post(
                    api_url, json=payload, headers=headers, stream=True, timeout=60
                )
                if response.status_code != 200:
                    yield None, f"API错误: {response.status_code}"
                    return
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content, None
                            except json.JSONDecodeError:
                                continue
            except Exception as exc:
                yield None, f"API调用失败: {str(exc)}"

        return gen_requests()

    return None, "缺少HTTP客户端库(requests或httpx)"



# 路由注册入口。
def register_ai_chatbot_routes(
    app,
    *,
    login_required,
    get_config,
    update_config,
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
):
    """注册聊天机器人、知识库与配置相关路由，并完成共享依赖注入。"""
    configure_ai_chatbot(
        get_config=get_config,
        update_config=update_config,
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
    )

    @app.route("/api/chatbot/chat", methods=["POST"])
    @rate_limit_chatbot()
    def chatbot_chat():
        config = get_chatbot_config()
        if not config["enabled"]:
            return jsonify({"success": False, "message": "智能客服暂时不可用"}), 503

        data = request.json or {}
        user_message = str(data.get("message") or "").strip()
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []
        session_id = str(data.get("session_id") or "").strip()
        page_url = str(data.get("page_url") or "").strip()
        page_title = str(data.get("page_title") or "").strip()
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
            content = str(msg.get("content") or "").strip()
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
            if has_any("产品", "传感器", "氢气", "型号"):
                return "您可以先查看气体传感产品总览页，按场景筛选型号：[查看全部产品](/pages/gassensing/all-products.html)。"
            if has_any("方案", "行业", "应用", "解决"):
                return "行业方案可以从这里进入：[解决方案中心](/pages/solutions/solutions-index.html)。如果您告知工况（温湿度、量程、安装方式），我可以继续细化建议。"
            return "抱歉，智能对话服务当前连接不稳定。建议先在“在线留言”提交问题，我们会尽快人工回复：[在线留言](/pages/contact/feedback.html#feedbackForm)。"

        fallback_reply = build_local_fallback_reply(user_message)
        use_stream = httpx_support or (
            requests_support and config.get("use_stream", True)
        )

        if use_stream:

            def generate():
                sent_any_content = False
                reply_parts = []
                try:
                    stream = call_openai_api(messages, stream=True)
                    if isinstance(stream, tuple):
                        _, error = stream
                        app.logger.warning("chatbot stream init failed: %s", error)
                        sync_response, sync_error = call_openai_api(
                            messages, stream=False
                        )
                        if not sync_error and sync_response:
                            record_chatbot_reply(sync_response, "ai_sync_fallback")
                            yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        app.logger.warning(
                            "chatbot sync fallback after stream init failed: %s",
                            sync_error,
                        )
                        record_chatbot_reply(fallback_reply, "local_fallback")
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    for chunk, err in stream:
                        if err:
                            app.logger.warning("chatbot stream chunk failed: %s", err)
                            if not sent_any_content:
                                sync_response, sync_error = call_openai_api(
                                    messages, stream=False
                                )
                                if not sync_error and sync_response:
                                    record_chatbot_reply(
                                        sync_response, "ai_sync_fallback"
                                    )
                                    yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
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
                            yield f"data: {json.dumps({'content': fallback_content}, ensure_ascii=False)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        sent_any_content = True
                        reply_parts.append(chunk)
                        yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                    if not sent_any_content:
                        record_chatbot_reply(fallback_reply, "local_fallback")
                        yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    else:
                        record_chatbot_reply("".join(reply_parts), "ai")
                    yield "data: [DONE]\n\n"
                except Exception as exc:
                    app.logger.exception("chatbot stream exception: %s", exc)
                    sync_response, sync_error = call_openai_api(messages, stream=False)
                    if not sync_error and sync_response:
                        record_chatbot_reply(sync_response, "ai_sync_fallback")
                        yield f"data: {json.dumps({'content': sync_response}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    app.logger.warning(
                        "chatbot sync fallback after stream exception failed: %s",
                        sync_error,
                    )
                    record_chatbot_reply(fallback_reply, "local_fallback")
                    yield f"data: {json.dumps({'content': fallback_reply}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        response, error = call_openai_api(messages, stream=False)
        if error:
            app.logger.warning("chatbot non-stream failed: %s", error)
            record_chatbot_reply(fallback_reply, "local_fallback")
            return jsonify({"success": True, "response": fallback_reply})
        record_chatbot_reply(response, "ai")
        return jsonify({"success": True, "response": response})

    @app.route("/api/chatbot/history", methods=["GET"])
    @login_required
    def chatbot_history():
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
        files = []
        for pdf_path in sorted(_dep("knowledge_dir").glob("*.pdf")):
            stat = pdf_path.stat()
            files.append(
                {
                    "name": pdf_path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return jsonify({"files": files, "pdf_support": _dep("pdf_support")})

    @app.route("/api/chatbot/knowledge/upload", methods=["POST"])
    @login_required
    def upload_knowledge_file():
        files = []
        if "file" in request.files:
            files.extend(request.files.getlist("file"))
        if "files" in request.files:
            files.extend(request.files.getlist("files"))

        files = [file for file in files if file and file.filename]
        if not files:
            return jsonify({"success": False, "message": "没有上传文件"}), 400

        uploaded = []
        failed = []

        for file in files:
            if not file.filename:
                failed.append({"filename": "", "message": "文件名为空"})
                continue
            if not file.filename.lower().endswith(".pdf"):
                failed.append({"filename": file.filename, "message": "只支持PDF文件"})
                continue
            if not _dep("validate_uploaded_pdf")(file):
                failed.append(
                    {"filename": file.filename, "message": "PDF 文件格式无效"}
                )
                continue

            filename = re.sub(r"[^\w\u4e00-\u9fff\-_.]", "_", file.filename)
            filepath = _dep("knowledge_dir") / filename
            try:
                file.save(str(filepath))
                uploaded.append(filename)
            except Exception as exc:
                failed.append(
                    {"filename": file.filename, "message": f"上传失败: {str(exc)}"}
                )

        if uploaded:
            reset_knowledge_cache()

        if not uploaded:
            message = failed[0]["message"] if len(failed) == 1 else "上传失败"
            return jsonify(
                {
                    "success": False,
                    "message": message,
                    "uploaded": [],
                    "failed": failed,
                }
            ), 400

        if failed:
            return jsonify(
                {
                    "success": True,
                    "partial_success": True,
                    "message": f"成功上传 {len(uploaded)} 个文件，失败 {len(failed)} 个",
                    "filename": uploaded[0],
                    "uploaded": uploaded,
                    "failed": failed,
                }
            )

        if len(uploaded) == 1:
            return jsonify(
                {
                    "success": True,
                    "message": f"文件 {uploaded[0]} 上传成功",
                    "filename": uploaded[0],
                    "uploaded": uploaded,
                }
            )

        return jsonify(
            {
                "success": True,
                "message": f"成功上传 {len(uploaded)} 个文件",
                "filename": uploaded[0],
                "uploaded": uploaded,
            }
        )

    @app.route("/api/chatbot/knowledge/<filename>/download", methods=["GET"])
    @login_required
    def download_knowledge_file(filename):
        filepath = _dep("knowledge_dir") / filename
        if not filepath.exists() or not filepath.is_file():
            return jsonify({"success": False, "message": "文件不存在"}), 404
        response = send_from_directory(
            str(_dep("knowledge_dir")),
            filename,
            as_attachment=True,
            download_name=filename,
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route("/api/chatbot/knowledge/<filename>", methods=["DELETE"])
    @login_required
    def delete_knowledge_file(filename):
        safe_name = Path(filename).name
        if safe_name != filename or ".." in filename:
            return jsonify({"success": False, "message": "文件名不合法"}), 400
        filepath = _dep("knowledge_dir") / safe_name
        if not filepath.exists():
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
        config = get_chatbot_config()
        if config["api_key"]:
            config["api_key"] = (
                config["api_key"][:8] + "..." + config["api_key"][-4:]
                if len(config["api_key"]) > 12
                else "***"
            )
        return jsonify(config)

    @app.route("/api/chatbot/config", methods=["POST"])
    @login_required
    def update_chatbot_config():
        denied = _dep("require_super_admin_api")()
        if denied:
            return denied
        data = request.json or {}
        updates = {}
        if (
            "api_key" in data
            and data["api_key"]
            and not str(data["api_key"]).startswith("***")
        ):
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
            updates["chatbot_model"] = data["model"]
        if "enabled" in data:
            updates["chatbot_enabled"] = bool(data["enabled"])
        if updates:
            _dep("update_config")(updates)
        return jsonify({"success": True, "message": "配置已更新"})

    @app.route("/api/chatbot/rate-limit/config", methods=["GET"])
    @login_required
    def get_rate_limit_config():
        return jsonify(
            {
                "success": True,
                "config": CHATBOT_RATE_LIMIT_CONFIG,
            }
        )

    @app.route("/api/chatbot/rate-limit/config", methods=["POST"])
    @login_required
    def update_rate_limit_config():
        denied = _dep("require_super_admin_api")()
        if denied:
            return denied
        data = request.json or {}
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "配置数据无效"}), 400
        if "requests_per_minute" in data:
            val = int(data["requests_per_minute"])
            if val < 1 or val > 100:
                return jsonify(
                    {"success": False, "message": "每分钟请求数必须在1-100之间"}
                ), 400
            CHATBOT_RATE_LIMIT_CONFIG["requests_per_minute"] = val
        if "requests_per_day" in data:
            val = int(data["requests_per_day"])
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
        data = request.json or {}
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
