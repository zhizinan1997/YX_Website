from __future__ import annotations

import os
import secrets
import time
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config, main_site, mailer, storage
from .time_utils import iso_now
from .workflow import CheckRunner, Scheduler


def _same_origin_request(req) -> bool:
    origin = req.headers.get("Origin") or ""
    referer = req.headers.get("Referer") or ""
    host_url = req.host_url.rstrip("/")
    for candidate in (origin, referer):
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate)
        except Exception:
            continue
        candidate_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if candidate_origin == host_url:
            return True
    return not origin and not referer


def _is_loopback_request(req) -> bool:
    host = str(req.remote_addr or "").strip()
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


def _request_ip(req) -> str:
    for header in ("CF-Connecting-IP", "X-Real-IP"):
        value = str(req.headers.get(header) or "").strip()
        if value:
            return value
    forwarded = str(req.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return str(req.remote_addr or "").strip()


def _verify_login_turnstile(data: dict):
    settings = main_site.get_turnstile_settings(config.MAIN_DATA_DIR)
    if not settings.enabled:
        return None
    token = str(
        data.get("turnstileToken")
        or data.get("cf_turnstile_response")
        or data.get("cf-turnstile-response")
        or ""
    ).strip()
    ok, detail = main_site.verify_turnstile_token(
        settings.secret_key,
        token,
        _request_ip(request),
        proxy_url=settings.proxy_url,
        proxy_fallback_enabled=settings.proxy_fallback_enabled,
    )
    if ok:
        return None
    return jsonify({"success": False, "message": detail or "人机验证失败，请重新验证"}), 403


def _current_session_user() -> dict | None:
    email = str(session.get("check_admin_email") or "").strip().lower()
    if not email:
        return None
    if session.get("check_dev_login") and config.DEV_LOGIN_ENABLED:
        return {
            "username": "local-dev",
            "role": "super_admin",
            "email": email,
            "permissions": ["local-preview"],
            "dev_login": True,
        }
    return main_site.find_verified_admin_by_email(email, config.MAIN_DATA_DIR)


def _login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        email = session.get("check_admin_email")
        login_at = int(session.get("check_login_at") or 0)
        if not email or not login_at or int(time.time()) - login_at > config.SESSION_MAX_AGE_SECONDS:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "登录已过期，请重新登录"}), 401
            return redirect("/admin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin_request(request):
            return jsonify({"success": False, "message": "请求来源校验失败，请刷新页面后重试"}), 403
        return view(*args, **kwargs)

    return wrapped


def _sanitize_target_payload() -> dict:
    data = request.get_json(silent=True) or {}
    return {
        "name": data.get("name"),
        "url": data.get("url"),
        "enabled": bool(data.get("enabled", True)),
        "interval_seconds": data.get("interval_seconds") or config.DEFAULT_CHECK_INTERVAL_SECONDS,
        "timeout_ms": data.get("timeout_ms") or config.DEFAULT_TARGET_TIMEOUT_MS,
    }


def _smtp_status_payload(*, run_check: bool = False) -> dict:
    smtp = main_site.get_smtp_settings(config.MAIN_DATA_DIR)
    payload = {
        "success": True,
        "configured": smtp.configured,
        "host": smtp.host,
        "port": smtp.port if smtp.host else None,
        "username": smtp.username,
        "from_email": smtp.from_email,
        "from_name": smtp.from_name,
        "use_ssl": smtp.use_ssl,
        "use_tls": smtp.use_tls,
        "password_configured": bool(smtp.password),
        "source": str(config.MAIN_DATA_DIR / "config.json"),
        "readonly": True,
        "checked": False,
        "checked_at": "",
        "check_status": "unchecked" if smtp.configured else "missing",
        "check_ok": False,
        "message": "读取主站 SMTP 配置，尚未执行连接检测" if smtp.configured else "主站 SMTP 配置不完整",
    }
    if run_check:
        result = mailer.check_smtp_connection(smtp)
        payload.update(
            {
                "checked": True,
                "checked_at": iso_now(),
                "check_status": result.get("status") or "error",
                "check_ok": bool(result.get("ok")),
                "message": result.get("message") or "SMTP 服务检测完成",
            }
        )
    return payload


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    if config.TRUST_PROXY_HEADERS:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.secret_key = config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
    app.config["CHECK_DATA_DIR"] = str(config.CHECK_DATA_DIR)
    app.config["CHECK_MAIN_DATA_DIR"] = str(config.MAIN_DATA_DIR)

    storage.init_db(config.CHECK_DATA_DIR)
    runner = CheckRunner(data_dir=config.CHECK_DATA_DIR, main_data_dir=config.MAIN_DATA_DIR)
    app.config["CHECK_RUNNER"] = runner
    if config.SCHEDULER_ENABLED and os.environ.get("WERKZEUG_RUN_MAIN") != "false":
        scheduler = Scheduler(runner, data_dir=config.CHECK_DATA_DIR)
        scheduler.start()
        app.config["CHECK_SCHEDULER"] = scheduler

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        no_store = request.path.startswith("/api/") or request.path.startswith("/admin")
        response.headers.setdefault("Cache-Control", "no-store" if no_store else "public, max-age=60")
        return response

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/admin")
    def admin():
        return render_template("admin.html")

    @app.route("/api/public/status")
    def public_status():
        try:
            window_hours = int(request.args.get("window") or config.PUBLIC_WINDOW_HOURS)
        except Exception:
            window_hours = config.PUBLIC_WINDOW_HOURS
        window_hours = max(1, min(168, window_hours))
        return jsonify(storage.get_public_status(config.CHECK_DATA_DIR, window_hours=window_hours))

    @app.route("/api/public/config-status")
    def public_config_status():
        smtp = main_site.get_smtp_settings(config.MAIN_DATA_DIR)
        admins = main_site.get_verified_admin_emails(config.MAIN_DATA_DIR)
        turnstile = main_site.get_turnstile_settings(config.MAIN_DATA_DIR)
        return jsonify(
            {
                "smtp_configured": smtp.configured,
                "verified_admin_count": len(admins),
                "main_data_dir": str(config.MAIN_DATA_DIR),
                "dev_login_enabled": bool(config.DEV_LOGIN_ENABLED and _is_loopback_request(request)),
                "turnstile_enabled": turnstile.enabled,
            }
        )

    @app.route("/api/auth/turnstile/public")
    def auth_turnstile_public():
        turnstile = main_site.get_turnstile_settings(config.MAIN_DATA_DIR)
        return jsonify(
            {
                "success": True,
                "enabled": turnstile.enabled,
                "site_key": turnstile.site_key if turnstile.enabled else "",
            }
        )

    @app.route("/api/auth/session")
    def auth_session():
        email = str(session.get("check_admin_email") or "")
        user = _current_session_user()
        return jsonify(
            {
                "success": True,
                "logged_in": bool(user),
                "email": email if user else "",
                "user": user or None,
            }
        )

    @app.route("/api/auth/send-code", methods=["POST"])
    def send_code():
        if not _same_origin_request(request):
            return jsonify({"success": False, "message": "请求来源校验失败，请刷新页面后重试"}), 403
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return jsonify({"success": False, "message": "请输入有效邮箱"}), 400
        turnstile_response = _verify_login_turnstile(data)
        if turnstile_response is not None:
            return turnstile_response
        user = main_site.find_verified_admin_by_email(email, config.MAIN_DATA_DIR)
        if not user:
            return jsonify({"success": False, "message": "该邮箱未绑定主站已验证管理员账号"}), 403
        cooldown = storage.auth_code_resend_seconds(email, config.CHECK_DATA_DIR)
        if cooldown > 0:
            return jsonify({"success": False, "message": f"请 {cooldown} 秒后再发送验证码", "resend_after": cooldown}), 429
        smtp = main_site.get_smtp_settings(config.MAIN_DATA_DIR)
        if not smtp.configured:
            return jsonify({"success": False, "message": "主站发信配置不完整，无法发送验证码"}), 503
        code = "".join(secrets.choice("0123456789") for _ in range(6))
        salt = secrets.token_hex(8)
        storage.store_auth_code(email, code, salt, config.CHECK_DATA_DIR)
        try:
            mailer.send_login_code(smtp, email, code)
        except Exception as exc:
            return jsonify({"success": False, "message": f"验证码发送失败：{exc}"}), 500
        return jsonify({"success": True, "message": "验证码已发送", "expires_in": config.AUTH_CODE_EXPIRES_SECONDS})

    @app.route("/api/auth/verify-code", methods=["POST"])
    def verify_code():
        if not _same_origin_request(request):
            return jsonify({"success": False, "message": "请求来源校验失败，请刷新页面后重试"}), 403
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()
        code = str(data.get("code") or "").strip()
        user = main_site.find_verified_admin_by_email(email, config.MAIN_DATA_DIR)
        if not user:
            return jsonify({"success": False, "message": "账号邮箱状态已变化，请重新发送验证码"}), 403
        if not storage.verify_auth_code(email, code, config.CHECK_DATA_DIR):
            return jsonify({"success": False, "message": "验证码错误或已过期"}), 400
        session.clear()
        session["check_admin_email"] = email
        session["check_admin_username"] = user.get("username") or ""
        session["check_login_at"] = int(time.time())
        return jsonify({"success": True, "message": "登录成功", "user": user})

    @app.route("/api/auth/dev-login", methods=["POST"])
    def dev_login():
        if not config.DEV_LOGIN_ENABLED:
            return jsonify({"success": False, "message": "本地开发登录未启用"}), 404
        if not _is_loopback_request(request):
            return jsonify({"success": False, "message": "本地开发登录仅允许本机访问"}), 403
        if not _same_origin_request(request):
            return jsonify({"success": False, "message": "请求来源校验失败，请刷新页面后重试"}), 403
        session.clear()
        session["check_admin_email"] = config.DEV_LOGIN_EMAIL
        session["check_admin_username"] = "local-dev"
        session["check_login_at"] = int(time.time())
        session["check_dev_login"] = True
        return jsonify(
            {
                "success": True,
                "message": "本地开发登录成功",
                "user": {
                    "username": "local-dev",
                    "role": "super_admin",
                    "email": config.DEV_LOGIN_EMAIL,
                    "dev_login": True,
                },
            }
        )

    @app.route("/api/auth/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"success": True})

    @app.route("/api/admin/targets")
    @_login_required
    def admin_targets():
        return jsonify({"success": True, "targets": storage.list_targets(config.CHECK_DATA_DIR)})

    @app.route("/api/admin/targets", methods=["POST"])
    @_login_required
    def admin_create_target():
        try:
            target = storage.create_target(_sanitize_target_payload(), config.CHECK_DATA_DIR)
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        return jsonify({"success": True, "target": target})

    @app.route("/api/admin/targets/<int:target_id>", methods=["PUT"])
    @_login_required
    def admin_update_target(target_id):
        try:
            target = storage.update_target(target_id, _sanitize_target_payload(), config.CHECK_DATA_DIR)
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        return jsonify({"success": True, "target": target})

    @app.route("/api/admin/targets/<int:target_id>", methods=["DELETE"])
    @_login_required
    def admin_delete_target(target_id):
        storage.delete_target(target_id, config.CHECK_DATA_DIR)
        return jsonify({"success": True})

    @app.route("/api/admin/check-now", methods=["POST"])
    @_login_required
    def admin_check_now():
        data = request.get_json(silent=True) or {}
        target_id = int(data.get("target_id") or 0)
        if not storage.get_target(target_id, config.CHECK_DATA_DIR):
            return jsonify({"success": False, "message": "监测目标不存在"}), 404
        runner: CheckRunner = app.config["CHECK_RUNNER"]
        accepted = runner.run_async(target_id, trigger="manual")
        return jsonify({"success": True, "accepted": accepted, "message": "已开始检测" if accepted else "该目标正在检测中"})

    @app.route("/api/admin/check-all", methods=["POST"])
    @_login_required
    def admin_check_all():
        targets = [target for target in storage.list_targets(config.CHECK_DATA_DIR) if target.get("enabled")]
        if not targets:
            return jsonify({"success": False, "message": "没有启用的监测目标"}), 400
        runner: CheckRunner = app.config["CHECK_RUNNER"]
        accepted_ids = []
        skipped_ids = []
        for target in targets:
            target_id = int(target.get("id") or 0)
            if runner.run_async(target_id, trigger="manual"):
                accepted_ids.append(target_id)
            else:
                skipped_ids.append(target_id)
        return jsonify(
            {
                "success": True,
                "accepted": len(accepted_ids),
                "skipped": len(skipped_ids),
                "target_count": len(targets),
                "accepted_ids": accepted_ids,
                "skipped_ids": skipped_ids,
                "message": f"已开始检测 {len(accepted_ids)} 个目标",
            }
        )

    @app.route("/api/admin/runs")
    @_login_required
    def admin_runs():
        return jsonify({"success": True, "runs": storage.get_recent_runs(config.CHECK_DATA_DIR, limit=80)})

    @app.route("/api/admin/incidents")
    @_login_required
    def admin_incidents():
        return jsonify({"success": True, "incidents": storage.get_recent_incidents(config.CHECK_DATA_DIR, limit=80)})

    @app.route("/api/admin/incidents", methods=["DELETE"])
    @_login_required
    def admin_clear_incidents():
        deleted = storage.clear_all_incidents(config.CHECK_DATA_DIR)
        return jsonify({"success": True, "deleted": deleted})

    @app.route("/api/admin/smtp")
    @_login_required
    def admin_smtp_status():
        return jsonify(_smtp_status_payload(run_check=False))

    @app.route("/api/admin/smtp-check", methods=["POST"])
    @_login_required
    def admin_smtp_check():
        return jsonify(_smtp_status_payload(run_check=True))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
