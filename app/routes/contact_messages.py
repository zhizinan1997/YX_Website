"""
公开表单与消息中心路由模块。

本模块提供用户反馈提交、招聘简历投递、Turnstile人机验证
以及后台消息管理等功能。

主要功能：
1. 公开表单提交
   - 联系表单（姓名、邮箱、电话、内容）
   - 招聘投递表单（简历上传）
   - Turnstile人机验证集成
   - IP限流保护（默认每小时5次）

2. 简历管理
   - 支持PDF、DOC、DOCX格式
   - 文件签名验证
   - 自动重命名避免冲突
   - 按时间戳归档

3. 消息处理
   - 消息元数据管理
   - 已读/未读状态跟踪
   - 分页查询支持

4. 限流机制
   - 基于IP地址的限流
   - 可配置的限流阈值
   - 自动清理过期记录

安全特性：
- Turnstile验证码防止机器人提交
- IP频率限制防止滥用
- 文件类型白名单验证
- 文件签名验证确保真实性
- 文本内容清理防止XSS

作者：元芯传感技术团队
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote, unquote

from flask import jsonify, request, send_file
from werkzeug.utils import secure_filename

from app.routes.admin import (
    _get_email_auth_settings,
    _load_admin_users,
    _normalize_email,
    _send_smtp_mail,
)

# 模块级依赖容器，在 configure/register 阶段一次性注入。
_DEPS = {}
_RATE_LIMIT_CLEANUP_INTERVAL = 300
_rate_limit_lock = threading.Lock()
_rate_limit_storage: dict[str, list[float]] = {}
_rate_limit_last_cleanup = 0.0



# 依赖注入配置入口。
def configure_contact_messages(
    *,
    get_config,
    get_turnstile_settings,
    verify_turnstile_token,
    get_client_ip,
    clean_job_text,
    now_beijing,
    messages_dir,
    messages_meta_file,
    resume_uploads_dir,
    allowed_resume_extensions,
    rate_limit_max,
    rate_limit_window,
):
    """配置公开表单与消息中心模块的共享依赖。"""
    _DEPS.clear()
    _DEPS.update({
        'get_config': get_config,
        'get_turnstile_settings': get_turnstile_settings,
        'verify_turnstile_token': verify_turnstile_token,
        'get_client_ip': get_client_ip,
        'clean_job_text': clean_job_text,
        'now_beijing': now_beijing,
        'messages_dir': Path(messages_dir),
        'messages_meta_file': Path(messages_meta_file),
        'resume_uploads_dir': Path(resume_uploads_dir),
        'allowed_resume_extensions': {str(item).lower() for item in (allowed_resume_extensions or set())},
        'rate_limit_max': max(1, int(rate_limit_max)),
        'rate_limit_window': max(1, int(rate_limit_window)),
    })


def _dep(name):
    value = _DEPS.get(name)
    if value is None and name not in _DEPS:
        raise RuntimeError(f'Contact/messages dependency not configured: {name}')
    return value


def _peek_upload_bytes(file_storage, max_bytes: int = 8192) -> bytes:
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return b''
    try:
        current_pos = stream.tell()
    except Exception:
        current_pos = None
    try:
        sample = stream.read(max_bytes)
    except Exception:
        sample = b''
    try:
        if current_pos is not None:
            stream.seek(current_pos)
        else:
            stream.seek(0)
    except Exception:
        pass
    return sample or b''


def validate_uploaded_resume(file_storage) -> bool:
    ext = Path((getattr(file_storage, 'filename', '') or '')).suffix.lower()
    sample = _peek_upload_bytes(file_storage)
    if ext == '.pdf':
        return sample.startswith(b'%PDF-')
    if ext == '.doc':
        return sample.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if ext == '.docx':
        return sample.startswith(b'PK\x03\x04')
    return False


def extract_resume_storage_name(message: dict) -> str:
    if not isinstance(message, dict):
        return ''
    stored_name = str(message.get('resume_stored_filename') or '').strip()
    if stored_name:
        safe_name = Path(unquote(stored_name)).name
        return safe_name if safe_name == unquote(stored_name) else ''
    resume_url = str(message.get('resume_url') or '').strip()
    if resume_url.startswith('/media/resumes/'):
        tail = unquote(resume_url.split('/media/resumes/', 1)[1]).strip()
        safe_name = Path(tail).name
        return safe_name if safe_name == tail else ''
    return ''


def build_resume_download_url(message: dict) -> str:
    message_id = str((message or {}).get('id') or '').strip()
    if not message_id:
        return ''
    if not extract_resume_storage_name(message):
        return ''
    return f'/api/messages/{quote(message_id)}/resume'


def _normalize_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _sanitize_download_filename_part(value: str, *, limit: int = 40) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ''
    text = re.sub(r'[\x00-\x1f\\/:*?"<>|]+', '_', text)
    text = text.strip(' .-_')
    if not text:
        return ''
    return text[:limit].rstrip(' .-_')


def _infer_resume_extension(message: dict, resume_name: str = '') -> str:
    allowed_extensions = {str(item).lower() for item in (_dep('allowed_resume_extensions') or set())}
    candidates = [
        resume_name,
        message.get('resume_filename'),
        message.get('resume_stored_filename'),
        message.get('resume_url'),
    ]
    for candidate in candidates:
        text = str(candidate or '').strip()
        if not text:
            continue
        ext = Path(text).suffix.lower()
        if ext in allowed_extensions:
            return ext
        normalized = text.lower().lstrip('.')
        if f'.{normalized}' in allowed_extensions:
            return f'.{normalized}'
        match = re.search(r'(pdf|docx|doc)$', normalized)
        if match:
            inferred = f".{match.group(1)}"
            if inferred in allowed_extensions:
                return inferred
    return ''


def build_resume_download_name(message: dict, resume_name: str = '') -> str:
    ext = _infer_resume_extension(message, resume_name)
    name = _sanitize_download_filename_part(message.get('name'))
    contact = _sanitize_download_filename_part(message.get('phone') or message.get('email'))
    job_title = _sanitize_download_filename_part(message.get('job_title') or message.get('job_id'))
    parts = [part for part in (name, contact, job_title) if part]
    if parts:
        base_name = '-'.join(parts)
    else:
        fallback = _sanitize_download_filename_part(message.get('id'), limit=24) or 'resume'
        base_name = f'candidate-{fallback}'
    return f'{base_name}{ext}'


def _summarize_text(value: str, limit: int = 120) -> str:
    normalized = _normalize_whitespace(value)
    if not normalized:
        return '未填写'
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(1, limit - 1)].rstrip() + '…'


def _clean_attribution_text(value, limit: int = 160) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ''
    text = re.sub(r'[\x00-\x1f<>]+', '', text).strip()
    return text[:limit]


def _clean_attribution_utm(raw) -> dict:
    data = raw if isinstance(raw, dict) else {}
    output = {}
    for source_key, out_key in (
        ('source', 'utm_source'),
        ('medium', 'utm_medium'),
        ('campaign', 'utm_campaign'),
        ('content', 'utm_content'),
        ('term', 'utm_term'),
        ('id', 'utm_id'),
    ):
        value = _clean_attribution_text(data.get(source_key) or data.get(out_key), limit=96)
        value = re.sub(r'[^A-Za-z0-9._:-]+', '-', value).strip('.:-_')
        output[out_key] = value[:96]
    return output


def _clean_attribution_touch(raw) -> dict:
    data = raw if isinstance(raw, dict) else {}
    utm = _clean_attribution_utm(data.get('utm') if isinstance(data.get('utm'), dict) else data)
    promotion_mark = _clean_attribution_text(data.get('promotion_mark') or utm.get('utm_id'), limit=96)
    promotion_mark = re.sub(r'[^A-Za-z0-9._:-]+', '-', promotion_mark).strip('.:-_')[:96]
    return {
        **utm,
        'promotion_mark': promotion_mark,
        'landing_page': _clean_attribution_text(data.get('landing_page'), limit=260),
        'referrer': _clean_attribution_text(data.get('referrer'), limit=300),
    }


def _extract_request_attribution(data=None) -> dict:
    raw = ''
    if data is not None:
        try:
            raw = data.get('attribution') or ''
        except Exception:
            raw = ''
    if not raw:
        raw = request.cookies.get('yx_site_attribution', '')
    parsed = {}
    if isinstance(raw, dict):
        parsed = raw
    elif raw:
        try:
            parsed = json.loads(unquote(str(raw)))
        except Exception:
            parsed = {}
    if not isinstance(parsed, dict):
        return {}
    first = _clean_attribution_touch(parsed.get('first_touch') or parsed.get('first'))
    last = _clean_attribution_touch(parsed.get('last_touch') or parsed.get('last'))
    if not any(first.values()) and not any(last.values()):
        return {}
    return {
        'first_touch': first,
        'last_touch': last,
    }


def _format_file_size(size_bytes) -> str:
    try:
        value = int(size_bytes or 0)
    except Exception:
        return ''
    if value <= 0:
        return ''
    units = ('字节', '千字节', '兆字节', '吉字节')
    size = float(value)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if size < 1024 or candidate == units[-1]:
            break
        size /= 1024
    if unit == '字节':
        return f'{int(size)}{unit}'
    return f'{size:.1f} {unit}'


def _build_notification_subject(message: dict) -> str:
    message_type = str((message or {}).get('message_type') or '').strip().lower()
    if message_type == 'job_application':
        job_title = _normalize_whitespace(message.get('job_title') or message.get('job_id') or '')
        applicant_name = _normalize_whitespace(message.get('name', ''))
        suffix = job_title or applicant_name or '新应聘'
        return f'官网新应聘通知｜{suffix}'
    title = _normalize_whitespace(message.get('title', ''))
    suffix = title or _normalize_whitespace(message.get('name', '')) or '新留言'
    return f'官网新留言通知｜{suffix}'


def _build_notification_rows(message: dict) -> list[tuple[str, str]]:
    message_type = str((message or {}).get('message_type') or '').strip().lower()
    common_rows = [
        ('消息编号', _normalize_whitespace(message.get('id', '')) or '未生成'),
        ('提交时间', _normalize_whitespace(message.get('timestamp', '')) or '未知'),
        ('姓名', _normalize_whitespace(message.get('name', '')) or '匿名'),
        ('电话', _normalize_whitespace(message.get('phone', '')) or '未填写'),
        ('邮箱', _normalize_whitespace(message.get('email', '')) or '未填写'),
    ]
    if message_type == 'job_application':
        resume_name = _normalize_whitespace(message.get('resume_filename', '')) or '未上传'
        resume_size = _format_file_size(message.get('resume_size_bytes'))
        if resume_size:
            resume_name = f'{resume_name}（{resume_size}）'
        return common_rows + [
            ('消息类型', '应聘投递'),
            ('岗位', _normalize_whitespace(message.get('job_title') or message.get('job_id') or '') or '未填写'),
            ('年龄', _normalize_whitespace(message.get('age', '')) or '未填写'),
            ('性别', _normalize_whitespace(message.get('gender', '')) or '未填写'),
            ('学历', _normalize_whitespace(message.get('education', '')) or '未填写'),
            ('毕业院校', _normalize_whitespace(message.get('school', '')) or '未填写'),
            ('住址', _normalize_whitespace(message.get('address', '')) or '未填写'),
            ('民族', _normalize_whitespace(message.get('ethnicity', '')) or '未填写'),
            ('简历文件', resume_name),
            ('工作经历摘要', _summarize_text(message.get('work_experience', ''), 140)),
            ('项目经历摘要', _summarize_text(message.get('project_experience', ''), 140)),
            ('自我陈述', _summarize_text(message.get('self_statement', ''), 140)),
        ]
    return common_rows + [
        ('消息类型', '在线留言或页面反馈'),
        ('标题', _normalize_whitespace(message.get('title', '')) or '无标题'),
        ('联系账号', _normalize_whitespace(message.get('qq', '')) or '未填写'),
        ('留言摘要', _summarize_text(message.get('content', ''), 180)),
    ]


def _render_summary_item(label: str, value: str) -> str:
    return (
        '<td style="width:50%;padding:6px;vertical-align:top;">'
        '<div style="padding:16px 18px;border-radius:18px;background:rgba(255,255,255,0.76);'
        'border:1px solid rgba(18,61,113,0.08);box-shadow:inset 0 1px 0 rgba(255,255,255,0.9);">'
        f'<div style="font-size:12px;letter-spacing:0.8px;color:#5d708b;">{html_escape(label)}</div>'
        f'<div style="margin-top:8px;font-size:18px;line-height:1.45;font-weight:800;color:#0d2d56;">{html_escape(value)}</div>'
        '</div></td>'
    )


def _render_detail_row(label: str, value: str) -> str:
    return (
        '<tr>'
        '<td style="padding:12px 14px;border-bottom:1px solid rgba(18,61,113,0.08);'
        'font-size:13px;line-height:1.7;color:#5d708b;width:126px;vertical-align:top;">'
        f'{html_escape(label)}</td>'
        '<td style="padding:12px 14px;border-bottom:1px solid rgba(18,61,113,0.08);'
        'font-size:14px;line-height:1.8;color:#10233d;vertical-align:top;">'
        f'{html_escape(value)}</td>'
        '</tr>'
    )


def _render_notification_brand_email(*, eyebrow: str, title: str, intro: str, highlight_html: str, note_lines):
    notes = ''.join(
        f'<li style="margin:0 0 8px;">{html_escape(str(line or ""))}</li>'
        for line in (note_lines or [])
        if str(line or '').strip()
    )
    return f"""
    <div style="margin:0;padding:0;background:linear-gradient(180deg,#edf4fb 0%,#e6eef9 100%);">
      <div style="width:100%;margin:0;font-family:'Microsoft YaHei',Arial,sans-serif;color:#10233d;background:
        radial-gradient(circle at top right, rgba(39,199,217,0.22) 0, rgba(39,199,217,0) 28%),
        radial-gradient(circle at left center, rgba(18,61,113,0.08) 0, rgba(18,61,113,0) 32%),
        linear-gradient(180deg,#edf4fb 0%,#e6eef9 100%);
      ">
        <div style="position:relative;overflow:hidden;background:
          radial-gradient(circle at 78% 26%, rgba(39,199,217,0.34) 0, rgba(39,199,217,0) 18%),
          radial-gradient(circle at 12% 18%, rgba(255,255,255,0.12) 0, rgba(255,255,255,0) 20%),
          linear-gradient(135deg,#08192d 0%,#123d71 55%,#1d6f99 76%,#27c7d9 100%);
          border-radius:0;padding:44px 44px 102px;color:#ffffff;box-shadow:inset 0 -1px 0 rgba(255,255,255,0.08);">
          <div style="position:absolute;right:-78px;top:-66px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,0.08);"></div>
          <div style="position:absolute;right:74px;bottom:28px;width:132px;height:132px;border-radius:50%;background:rgba(39,199,217,0.16);filter:blur(2px);"></div>
          <div style="position:relative;z-index:1;display:inline-block;padding:8px 16px;border-radius:999px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.24);font-size:12px;letter-spacing:1.4px;box-shadow:0 10px 24px rgba(8,25,45,0.18);">
            元芯传感后台
          </div>
          <div style="position:relative;z-index:1;margin-top:24px;font-size:14px;line-height:1.8;color:rgba(255,255,255,0.78);">{html_escape(eyebrow)}</div>
          <h1 style="position:relative;z-index:1;margin:12px 0 0;font-size:34px;line-height:1.18;font-weight:800;color:#ffffff;text-shadow:0 10px 28px rgba(8,25,45,0.25);">{html_escape(title)}</h1>
          <div style="position:relative;z-index:1;margin-top:16px;width:88px;height:4px;border-radius:999px;background:linear-gradient(90deg,rgba(255,255,255,0.92) 0%,rgba(39,199,217,0.92) 100%);"></div>
        </div>
        <div style="position:relative;z-index:2;margin-top:-54px;background:
          linear-gradient(180deg,rgba(255,255,255,0.96) 0%,#ffffff 100%);
          border-top-left-radius:34px;border-top-right-radius:34px;padding:40px 44px 34px;
          box-shadow:0 28px 90px rgba(8,25,45,0.14), inset 0 1px 0 rgba(255,255,255,0.85);">
          <p style="margin:0 0 20px;font-size:17px;line-height:1.9;color:#10233d;">{html_escape(intro)}</p>
          <div style="margin:24px 0;padding:30px 28px;border-radius:28px;background:
            radial-gradient(circle at top center, rgba(255,255,255,0.72) 0, rgba(255,255,255,0) 34%),
            linear-gradient(180deg,rgba(39,199,217,0.18) 0%,rgba(18,61,113,0.06) 100%);
            border:1px solid rgba(39,199,217,0.30);box-shadow:inset 0 1px 0 rgba(255,255,255,0.8), 0 16px 36px rgba(18,61,113,0.08);">
            {highlight_html}
          </div>
          <div style="padding:22px 24px;border-radius:24px;background:linear-gradient(180deg,#f9fcff 0%,#f1f7fd 100%);border:1px solid rgba(18,61,113,0.08);box-shadow:inset 0 1px 0 rgba(255,255,255,0.9);">
            <div style="margin:0 0 12px;font-size:14px;font-weight:700;letter-spacing:0.4px;color:#123d71;">处理提示</div>
            <ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.9;color:#5d708b;">
              {notes}
            </ul>
          </div>
        </div>
        <div style="padding:22px 24px 32px;text-align:center;font-size:12px;line-height:1.9;color:#5d708b;background:#ffffff;">
          <div style="font-weight:700;color:#123d71;">元芯传感官网</div>
          <div>本邮件由官网消息通知系统自动发送，请勿直接回复。</div>
        </div>
      </div>
    </div>
    """


def _build_notification_email(message: dict) -> tuple[str, str, str]:
    message_type = str((message or {}).get('message_type') or '').strip().lower()
    is_job_application = message_type == 'job_application'
    heading = '收到新的应聘投递' if is_job_application else '收到新的网站留言'
    eyebrow = '官网表单消息提醒'
    intro = (
        '官网招聘表单刚收到一份新的应聘资料，系统已保存到后台留言中心。以下是便于管理员快速判断的摘要信息。'
        if is_job_application
        else '官网留言或页面反馈表单刚收到一条新的用户提交，系统已保存到后台留言中心。以下是便于管理员快速判断的摘要信息。'
    )
    rows = _build_notification_rows(message)
    row_map = {label: value for label, value in rows}
    summary_cells = [
        _render_summary_item('提交类型', row_map.get('消息类型', '新消息')),
        _render_summary_item('提交人', row_map.get('姓名', '匿名')),
        _render_summary_item('联系电话', row_map.get('电话', '未填写')),
        _render_summary_item('提交时间', row_map.get('提交时间', '未知')),
    ]
    summary_rows = ''.join(
        f'<tr>{summary_cells[index]}{summary_cells[index + 1]}</tr>'
        for index in range(0, len(summary_cells), 2)
    )
    primary_label = '应聘摘要' if is_job_application else '留言摘要'
    primary_text = (
        row_map.get('自我陈述', '未填写')
        if is_job_application
        else row_map.get('留言摘要', '未填写')
    )
    detail_rows = ''.join(_render_detail_row(label, value) for label, value in rows)
    highlight_html = f'''
      <div style="font-size:12px;letter-spacing:1.2px;color:#5d708b;text-align:center;">消息快速概览</div>
      <table style="margin-top:12px;width:100%;border-collapse:separate;border-spacing:0;">{summary_rows}</table>
      <div style="margin:18px 0 0;padding:20px 22px;border-radius:22px;background:#ffffff;border:1px solid rgba(39,199,217,0.24);box-shadow:0 12px 28px rgba(18,61,113,0.07);">
        <div style="font-size:12px;letter-spacing:1px;color:#5d708b;">{html_escape(primary_label)}</div>
        <div style="margin-top:10px;font-size:16px;line-height:1.9;color:#10233d;">{html_escape(primary_text)}</div>
      </div>
      <div style="margin:18px 0 0;border-radius:22px;overflow:hidden;background:rgba(255,255,255,0.82);border:1px solid rgba(18,61,113,0.10);">
        <table style="width:100%;border-collapse:collapse;">
          {detail_rows}
        </table>
      </div>
    '''
    html_body = _render_notification_brand_email(
        eyebrow=eyebrow,
        title=heading,
        intro=intro,
        highlight_html=highlight_html,
        note_lines=[
            '完整留言、反馈或简历文件请登录后台留言系统查看。',
            '如果需要回访，请优先核对用户留下的电话和邮箱信息。',
            '本邮件只展示摘要信息，请不要在邮件中转发敏感简历内容。',
        ],
    )
    text_lines = ['官网公开表单收到新的提交，摘要如下：']
    text_lines.extend(f'{label}: {value}' for label, value in rows)
    text_lines.append('完整内容请登录后台留言系统查看。')
    return _build_notification_subject(message), html_body, '\n'.join(text_lines)


def _collect_admin_notification_recipients(message: dict) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()

    def _append(email_value: str):
        normalized = _normalize_email(email_value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        recipients.append(normalized)

    admin_users_file = _dep('messages_dir').parent / 'admin_users.json'
    users_data = _load_admin_users(admin_users_file)
    message_type = str((message or {}).get('message_type') or '').strip().lower()
    is_job_application = message_type == 'job_application'
    for user in users_data.get('users', []):
        if not isinstance(user, dict):
            continue
        if user.get('enabled', True) is False:
            continue
        if not bool(user.get('email_verified', False)):
            continue
        wants_notification = bool(user.get('notify_job_email', False)) if is_job_application else bool(user.get('notify_message_email', False))
        if not wants_notification:
            continue
        _append(user.get('email', ''))
    return recipients


def _notify_admins_about_message(message: dict, logger):
    try:
        config = _dep('get_config')() or {}
        smtp_settings = _get_email_auth_settings(config)
        recipients = _collect_admin_notification_recipients(message)
        if not recipients:
            logger.info('Skip admin message notification: no recipients configured')
            return
        if not smtp_settings.get('configured'):
            logger.info('Skip admin message notification: SMTP not configured')
            return
        if smtp_settings.get('expired'):
            logger.info('Skip admin message notification: SMTP password expired')
            return
        subject, html_body, text_body = _build_notification_email(message)
        for recipient in recipients:
            _send_smtp_mail(
                smtp_settings,
                to_email=recipient,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
    except Exception as exc:
        logger.warning('Failed to send admin message notification: %s', exc)


def _start_admin_notification(message: dict, logger):
    payload = dict(message or {})
    thread = threading.Thread(
        target=_notify_admins_about_message,
        args=(payload, logger),
        name='contact-message-admin-email',
        daemon=True,
    )
    thread.start()


def get_messages_meta():
    """加载已持久化的消息元数据。"""
    default_meta = {'deleted_count': 0}
    messages_meta_file = _dep('messages_meta_file')
    if messages_meta_file.exists():
        try:
            meta = json.loads(messages_meta_file.read_text(encoding='utf-8'))
            merged = {**default_meta, **(meta if isinstance(meta, dict) else {})}
            merged['deleted_count'] = max(0, int(merged.get('deleted_count', 0)))
            return merged
        except Exception:
            pass
    messages_meta_file.write_text(json.dumps(default_meta, indent=2, ensure_ascii=False), encoding='utf-8')
    return default_meta


def save_messages_meta(meta):
    """持久化保存消息元数据。"""
    safe_meta = {'deleted_count': max(0, int((meta or {}).get('deleted_count', 0)))}
    _dep('messages_meta_file').write_text(json.dumps(safe_meta, indent=2, ensure_ascii=False), encoding='utf-8')
    return safe_meta


def get_public_turnstile_config():
    return _dep('get_turnstile_settings')(_dep('get_config')() or {})


def extract_turnstile_token_from_request():
    form = request.form or {}
    for key in ('cf_turnstile_response', 'cf-turnstile-response', 'turnstileToken'):
        value = str(form.get(key, '') or '').strip()
        if value:
            return value

    data = request.get_json(silent=True) or {}
    if isinstance(data, dict):
        for key in ('cf_turnstile_response', 'cf-turnstile-response', 'turnstileToken'):
            value = str(data.get(key, '') or '').strip()
            if value:
                return value
    return ''


def require_public_turnstile_check(ip: str = ''):
    settings = get_public_turnstile_config()
    if not settings.get('enabled'):
        return None

    token = extract_turnstile_token_from_request()
    if not token:
        return jsonify({'success': False, 'message': '请先完成人机验证'}), 400

    ok, detail = _dep('verify_turnstile_token')(
        secret_key=settings.get('secret_key', ''),
        token=token,
        remote_ip=ip or _dep('get_client_ip')(),
        proxy_url=settings.get('proxy_url', ''),
        proxy_fallback_enabled=settings.get('proxy_fallback_enabled', False),
    )
    if ok:
        return None
    return jsonify({'success': False, 'message': detail or '验证码校验失败，请重试'}), 400


def check_rate_limit(ip: str) -> bool:
    """检查当前 IP 是否仍在限流阈值内，允许时返回 True。"""
    global _rate_limit_last_cleanup
    now = time.time()
    ip_key = str(ip or '').strip() or 'unknown'
    rate_limit_window = _dep('rate_limit_window')
    rate_limit_max = _dep('rate_limit_max')

    with _rate_limit_lock:
        if now - _rate_limit_last_cleanup > _RATE_LIMIT_CLEANUP_INTERVAL:
            keys_to_remove = [
                key for key, timestamps in _rate_limit_storage.items()
                if not any(now - ts < rate_limit_window for ts in timestamps)
            ]
            for key in keys_to_remove:
                del _rate_limit_storage[key]
            _rate_limit_last_cleanup = now

        entries = [ts for ts in _rate_limit_storage.get(ip_key, []) if now - ts < rate_limit_window]
        if len(entries) >= rate_limit_max:
            _rate_limit_storage[ip_key] = entries
            return False
        entries.append(now)
        _rate_limit_storage[ip_key] = entries
    return True



# 路由注册入口。
def register_contact_message_routes(
    app,
    *,
    login_required,
    get_config,
    get_turnstile_settings,
    verify_turnstile_token,
    get_client_ip,
    clean_job_text,
    now_beijing,
    messages_dir,
    messages_meta_file,
    resume_uploads_dir,
    allowed_resume_extensions,
    rate_limit_max,
    rate_limit_window,
):
    """注册公开反馈、招聘投递和后台消息中心相关路由。"""
    configure_contact_messages(
        get_config=get_config,
        get_turnstile_settings=get_turnstile_settings,
        verify_turnstile_token=verify_turnstile_token,
        get_client_ip=get_client_ip,
        clean_job_text=clean_job_text,
        now_beijing=now_beijing,
        messages_dir=messages_dir,
        messages_meta_file=messages_meta_file,
        resume_uploads_dir=resume_uploads_dir,
        allowed_resume_extensions=allowed_resume_extensions,
        rate_limit_max=rate_limit_max,
        rate_limit_window=rate_limit_window,
    )

    @app.route('/api/turnstile/public', methods=['GET'])
    def get_turnstile_public_api():
        """获取站点表单使用的 Turnstile 公开配置。"""
        settings = get_public_turnstile_config()
        return jsonify({
            'enabled': bool(settings.get('enabled')),
            'site_key': settings.get('site_key', ''),
        })

    @app.route('/api/feedback', methods=['POST'])
    def submit_feedback():
        """处理反馈表单提交。"""
        ip = _dep('get_client_ip')()

        turnstile_failed = require_public_turnstile_check(ip)
        if turnstile_failed:
            return turnstile_failed

        if not check_rate_limit(ip):
            return jsonify({
                'success': False,
                'message': '提交过于频繁，请稍后再试。每小时最多提交5条留言。',
            }), 429

        data = request.form if request.form else request.json or {}
        phone = data.get('txtUserTel', '').strip()
        content = data.get('txtContent', '').strip()

        if not phone:
            return jsonify({'success': False, 'message': '请填写联系电话'}), 400
        if not content:
            return jsonify({'success': False, 'message': '请填写留言内容'}), 400

        now_bj = _dep('now_beijing')()
        message = {
            'id': now_bj.strftime('%Y%m%d%H%M%S%f') + os.urandom(4).hex(),
            'name': (data.get('txtUserName', '').strip() or '匿名')[:100],
            'phone': phone[:30],
            'email': data.get('txtUserEmail', '').strip()[:200],
            'qq': data.get('txtUserQQ', '').strip()[:20],
            'title': (data.get('txtTitle', '').strip() or '无标题')[:200],
            'content': content[:5000],
            'is_read': False,
            'timestamp': now_bj.isoformat(),
            'ip': ip,
            'attribution': _extract_request_attribution(data),
        }

        filepath = _dep('messages_dir') / f"{message['id']}.json"
        filepath.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding='utf-8')
        _start_admin_notification(message, app.logger)
        return jsonify({
            'success': True,
            'message': '留言提交成功！我们会尽快回复您。',
        })

    @app.route('/api/messages', methods=['GET'])
    @login_required
    def get_messages():
        """获取后台消息中心的全部消息。"""
        messages = []
        today = _dep('now_beijing')().date().isoformat()
        today_count = 0
        read_count = 0
        job_count = 0

        for filepath in sorted(_dep('messages_dir').glob('*.json'), reverse=True):
            try:
                msg = json.loads(filepath.read_text(encoding='utf-8'))
                resume_download_url = build_resume_download_url(msg)
                if resume_download_url:
                    msg['resume_url'] = resume_download_url
                messages.append(msg)
                if str(msg.get('timestamp', '')).split('T')[0] == today:
                    today_count += 1
                if msg.get('is_read'):
                    read_count += 1
                if msg.get('message_type') == 'job_application':
                    job_count += 1
            except Exception:
                continue

        meta = get_messages_meta()
        stats = {
            'total_count': len(messages),
            'job_count': job_count,
            'today_count': today_count,
            'read_count': read_count,
            'deleted_count': int(meta.get('deleted_count', 0)),
        }
        return jsonify({'messages': messages, 'stats': stats})

    @app.route('/api/messages/<message_id>', methods=['DELETE'])
    @login_required
    def delete_message(message_id):
        """删除一条消息。"""
        if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
            return jsonify({'success': False, 'message': '无效的留言 ID'}), 400

        filepath = _dep('messages_dir') / f'{message_id}.json'
        if filepath.exists():
            try:
                msg = json.loads(filepath.read_text(encoding='utf-8'))
                resume_name = extract_resume_storage_name(msg)
                if resume_name:
                    resume_path = _dep('resume_uploads_dir') / resume_name
                    if resume_path.exists():
                        resume_path.unlink()
            except Exception:
                pass

            filepath.unlink()
            meta = get_messages_meta()
            meta['deleted_count'] = int(meta.get('deleted_count', 0)) + 1
            save_messages_meta(meta)
            return jsonify({'success': True})

        return jsonify({'success': False, 'message': '留言不存在'}), 404

    @app.route('/api/messages/<message_id>/read', methods=['POST'])
    @login_required
    def mark_message_read(message_id):
        """将单条消息标记为已读。"""
        if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
            return jsonify({'success': False, 'message': '无效的留言 ID'}), 400

        filepath = _dep('messages_dir') / f'{message_id}.json'
        if not filepath.exists():
            return jsonify({'success': False, 'message': '留言不存在'}), 404

        try:
            msg = json.loads(filepath.read_text(encoding='utf-8'))
            msg['is_read'] = True
            filepath.write_text(json.dumps(msg, ensure_ascii=False, indent=2), encoding='utf-8')
            return jsonify({'success': True})
        except Exception:
            return jsonify({'success': False, 'message': '更新失败'}), 500

    @app.route('/api/messages/<message_id>/resume', methods=['GET'])
    @login_required
    def download_message_resume(message_id):
        """通过鉴权后的后台接口下载求职者简历。"""
        if not re.fullmatch(r'[a-zA-Z0-9_\-]+', message_id):
            return jsonify({'success': False, 'message': '无效的留言 ID'}), 400

        filepath = _dep('messages_dir') / f'{message_id}.json'
        if not filepath.exists():
            return jsonify({'success': False, 'message': '留言不存在'}), 404

        try:
            msg = json.loads(filepath.read_text(encoding='utf-8'))
        except Exception:
            return jsonify({'success': False, 'message': '留言数据损坏'}), 500

        resume_name = extract_resume_storage_name(msg)
        if not resume_name:
            return jsonify({'success': False, 'message': '未找到简历文件'}), 404

        resume_path = _dep('resume_uploads_dir') / resume_name
        if not resume_path.exists() or not resume_path.is_file():
            return jsonify({'success': False, 'message': '简历文件不存在'}), 404

        download_name = build_resume_download_name(msg, resume_name) or resume_name
        response = send_file(
            resume_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetypes.guess_type(download_name)[0] or 'application/octet-stream',
            conditional=False,
        )
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/api/job-application', methods=['POST'])
    def submit_job_application():
        """处理招聘申请表单提交。"""
        ip = _dep('get_client_ip')()

        turnstile_failed = require_public_turnstile_check(ip)
        if turnstile_failed:
            return turnstile_failed

        if not check_rate_limit(ip):
            return jsonify({
                'success': False,
                'message': '提交过于频繁，请稍后再试。每小时最多提交5条。',
            }), 429

        data = request.form or {}
        required_fields = {
            'name': '姓名',
            'age': '年龄',
            'ethnicity': '民族',
            'gender': '性别',
            'address': '住址',
            'phone': '电话',
            'email': '邮箱',
            'education': '学历',
            'school': '毕业院校',
            'work_experience': '工作经历',
            'project_experience': '项目经历',
            'self_statement': '自我陈述',
        }

        cleaned = {}
        clean_job_text = _dep('clean_job_text')
        for key in required_fields:
            cleaned[key] = clean_job_text(data.get(key, ''))
            if not cleaned[key]:
                return jsonify({'success': False, 'message': f'请填写{required_fields[key]}'}), 400

        age_val = re.sub(r'\D+', '', cleaned['age'])
        if not age_val:
            return jsonify({'success': False, 'message': '年龄格式不正确'}), 400
        cleaned['age'] = age_val

        if len(cleaned['self_statement']) > 100:
            return jsonify({'success': False, 'message': '自我陈述请控制在100字以内'}), 400

        resume_file = request.files.get('resume_file')
        if not resume_file or not resume_file.filename:
            return jsonify({'success': False, 'message': '请上传简历文件（PDF或Word）'}), 400

        ext = Path(resume_file.filename).suffix.lower()
        if ext not in _dep('allowed_resume_extensions'):
            return jsonify({'success': False, 'message': '简历格式仅支持 PDF/DOC/DOCX'}), 400
        if not validate_uploaded_resume(resume_file):
            return jsonify({'success': False, 'message': '简历文件格式与扩展名不匹配'}), 400

        resume_file.stream.seek(0, os.SEEK_END)
        size = resume_file.stream.tell()
        resume_file.stream.seek(0)
        if size > 10 * 1024 * 1024:
            return jsonify({'success': False, 'message': '简历文件过大（最大10MB）'}), 400

        now = _dep('now_beijing')()
        message_id = now.strftime('%Y%m%d%H%M%S%f')
        safe_name = secure_filename(resume_file.filename) or f'resume{ext}'
        saved_name = f'{message_id}_{safe_name}'
        resume_path = _dep('resume_uploads_dir') / saved_name
        resume_file.save(resume_path)

        message = {
            'id': message_id,
            'message_type': 'job_application',
            'job_id': clean_job_text(data.get('job_id', '')),
            'job_title': clean_job_text(data.get('job_title', '')),
            'name': cleaned['name'],
            'age': cleaned['age'],
            'ethnicity': cleaned['ethnicity'],
            'gender': cleaned['gender'],
            'address': cleaned['address'],
            'phone': cleaned['phone'],
            'email': cleaned['email'],
            'education': cleaned['education'],
            'school': cleaned['school'],
            'work_experience': cleaned['work_experience'],
            'project_experience': cleaned['project_experience'],
            'self_statement': cleaned['self_statement'],
            'resume_filename': safe_name,
            'resume_stored_filename': saved_name,
            'resume_size_bytes': size,
            'resume_url': f'/api/messages/{message_id}/resume',
            'is_read': False,
            'timestamp': now.isoformat(),
            'ip': ip,
            'attribution': _extract_request_attribution(data),
        }

        filepath = _dep('messages_dir') / f'{message_id}.json'
        filepath.write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding='utf-8')
        _start_admin_notification(message, app.logger)
        return jsonify({
            'success': True,
            'message': '应聘信息提交成功，我们会尽快联系您。',
        })


__all__ = [
    'register_contact_message_routes',
]
