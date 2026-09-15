from __future__ import annotations

import unittest
from pathlib import Path

import requests
from flask import Flask, jsonify, session

from app.routes import news_content as nc


def _login_required(fn):
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return jsonify({"success": False, "message": "login required"}), 401
        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    return wrapper


def _build_client():
    app = Flask(__name__)
    app.secret_key = "feishu-import-test-secret"
    nc.register_news_content_routes(
        app,
        login_required=_login_required,
        pages_dir=Path("pages"),
        news_featured_file=Path("data/news_featured.json"),
        news_visibility_file=Path("data/news_visibility.json"),
        legacy_news_uploads_dir=Path("data/news_uploads"),
        news_uploads_dir=Path("data/news_uploads"),
        h2_home_file=Path("data/h2_home.json"),
        markdown_support=False,
        markdown_module=None,
        requests_support=True,
        requests_module=requests,
        httpx_support=False,
        httpx_module=None,
        allowed_news_image_extensions={".png", ".jpg", ".jpeg", ".webp"},
        news_safe_html_tags=set(),
        news_dropped_html_tags=set(),
        news_void_html_tags=set(),
        validate_uploaded_image_extension=lambda filename, allowed: True,
        validate_image_bytes=lambda *args, **kwargs: (True, ""),
        validate_safe_remote_fetch_url=lambda url: (True, "", url),
        sanitize_public_text=lambda value, **kwargs: str(value or ""),
        sanitize_public_date_text=lambda value, **kwargs: str(value or ""),
        sanitize_public_link_url=lambda value, **kwargs: str(value or ""),
        sanitize_public_media_url=lambda value, **kwargs: str(value or ""),
        get_h2_home_config=lambda: {},
        get_product_settings=lambda: {},
        normalize_related_news_links=lambda *args, **kwargs: None,
        get_chatbot_config=lambda: {},
        call_openai_api=lambda *args, **kwargs: None,
    )
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    return client


class _ConsumedStreamResponse:
    """模拟 requests 的流式响应：body 已被 iter_content 消费。"""

    encoding = "utf-8"

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def iter_content(self, chunk_size=1):
        yield from self._chunks

    @property
    def apparent_encoding(self):  # pragma: no cover - 仅在回归时触发
        raise RuntimeError("The content for this response was already consumed")


class FeishuImportRegressionTests(unittest.TestCase):
    def test_remote_fetch_failure_returns_json_instead_of_html_500(self):
        client = _build_client()
        original = nc.fetch_remote_url_content

        def failing_fetch(*args, **kwargs):
            raise nc.RemoteFetchError(
                "远程内容下载失败，请确认链接可公开访问",
                reason="download_failed",
                source_url="https://www.feishu.cn/docx/regression",
                safe_source_url="https://www.feishu.cn/docx/regression",
            )

        nc.fetch_remote_url_content = failing_fetch
        try:
            res = client.post(
                "/api/news/import/feishu",
                json={"url": "https://www.feishu.cn/docx/regression"},
            )
        finally:
            nc.fetch_remote_url_content = original

        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.is_json)
        self.assertFalse(res.data.startswith(b"<!doctype html"))
        self.assertFalse(res.get_json()["success"])

    def test_bounded_payload_ignores_consumed_stream_apparent_encoding(self):
        response = _ConsumedStreamResponse([b"<html>", "中文正文".encode("utf-8"), b"</html>"])

        payload = nc._bounded_response_payload(response, max_bytes=1024, prefer_text=True)

        self.assertEqual(payload["text"], "<html>中文正文</html>")
        self.assertEqual(payload["content_type"], "text/html")


if __name__ == "__main__":
    unittest.main()
