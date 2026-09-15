"""回归测试：后台登录日志锁的自死锁防护。

2026-09-15 线上事故：bootstrap 将 admin_audit.ADMIN_LOGIN_LOG_LOCK（threading.Lock，
不可重入）作为 admin_login_log_lock 注入路由层；后台"系统日志"接口
/api/admin/login-logs 在 `with admin_login_log_lock:` 内调用
load_admin_login_logs()，后者再次 acquire 同一把锁 → 同线程重入自死锁，
持锁线程永不释放 → 登录收尾 append_admin_login_log 全部阻塞 →
gunicorn worker 全部请求线程卡死，站点约一半请求随机挂起
（首页区块超时、/admin/check 挂起导致前端误判下线、反复登录触发延迟保护）。

修复：
1. ADMIN_LOGIN_LOG_LOCK 改为 RLock（可重入，与 ADMIN_USERS_LOCK 等对齐）；
2. 移除路由层冗余外层加锁。

本测试通过子进程按生产方式接线（注入 admin_audit 的真实锁对象）复现
历史调用形态：旧代码会在子进程中死锁挂起（测试失败），新代码必须正常返回。
子进程隔离确保即使回归也不会拖死测试套件中的其他用例。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

CHILD_FLAG = "--as-deadlock-probe-child"


def _run_child_probe() -> int:
    """按生产接线复现历史死锁调用形态；成功返回 0，死锁时由父进程杀死。"""
    from flask import Flask

    from app.admin_audit import (
        ADMIN_LOGIN_LOG_LOCK,
        append_admin_login_log,
        configure_admin_audit,
        load_admin_login_logs,
    )
    from app.routes.admin import register_admin_routes

    tmp = tempfile.mkdtemp(prefix="yx-audit-probe-")
    root = Path(tmp)
    (root / "data").mkdir(exist_ok=True)
    configure_admin_audit(data_dir=root / "data")

    config: dict = {}
    app = Flask(__name__)
    app.secret_key = "deadlock-probe-secret"
    register_admin_routes(
        app,
        login_required=lambda func: func,
        get_config=lambda: dict(config),
        update_config=lambda updates: config.update(updates or {}) or dict(config),
        append_admin_login_log=append_admin_login_log,
        load_admin_login_logs=load_admin_login_logs,
        # 生产接线：注入的就是 admin_audit 内部那把锁（bootstrap.py 同款）。
        admin_login_log_lock=ADMIN_LOGIN_LOG_LOCK,
        project_root=root,
        resolve_ip_location=lambda _ip: "未知",
        resolve_ip_country_code=lambda _ip: "CN",
        get_public_base_url=lambda: "",
    )
    client = app.test_client()

    # 1) 历史 2026-09-15 死锁现场：后台系统日志分页接口（旧代码在此自死锁）。
    resp = client.get("/api/admin/login-logs?page=1&page_size=20")
    assert resp.status_code == 200, f"login-logs page failed: {resp.status_code}"
    assert resp.get_json()["count"] == 0

    # 2) 另一个分支：limit 模式（admin.py 旧 4503 行同款包裹）。
    resp = client.get("/api/admin/login-logs?limit=10")
    assert resp.status_code == 200, f"login-logs limit failed: {resp.status_code}"

    # 3) 历史调用形态本身：外层持锁 + 内部 load 再次加锁（旧代码自死锁点）。
    with ADMIN_LOGIN_LOG_LOCK:
        items = load_admin_login_logs()
    assert items == []

    # 4) 写入路径：append 后能读回。
    append_admin_login_log(operation="admin_login", success=True, username="probe")
    with ADMIN_LOGIN_LOG_LOCK:
        items = load_admin_login_logs()
    assert len(items) == 1 and items[0]["username"] == "probe"

    return 0


class AdminLoginLogsDeadlockTests(unittest.TestCase):
    def test_production_wiring_does_not_deadlock(self):
        """生产式接线 + 历史调用形态必须在限定时间内完成（旧代码会死锁挂起）。"""
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), CHILD_FLAG],
            cwd=str(REPO_ROOT),
            timeout=45,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"child probe failed\nstdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}",
        )
        self.assertIn("PROBE-OK", result.stdout)

    def test_concurrent_load_and_append_complete(self):
        """多线程并发读写登录日志必须全部完成，不得互锁/挂起。"""
        from app.admin_audit import (
            ADMIN_LOGIN_LOG_FILE,
            append_admin_login_log,
            load_admin_login_logs,
        )

        original_file = ADMIN_LOGIN_LOG_FILE
        tmp = tempfile.TemporaryDirectory()
        data_dir = Path(tmp.name)
        data_dir.mkdir(exist_ok=True)
        try:
            import app.admin_audit as audit

            audit.ADMIN_LOGIN_LOG_FILE = data_dir / "admin_login_logs.json"

            errors: list[str] = []
            readers_done = []
            writers_done = []

            def reader():
                try:
                    for _ in range(30):
                        load_admin_login_logs()
                    readers_done.append(True)
                except Exception as exc:  # pragma: no cover - 失败路径
                    errors.append(f"reader: {exc!r}")

            def writer():
                try:
                    for i in range(30):
                        append_admin_login_log(
                            operation="admin_login",
                            success=bool(i % 2),
                            username=f"concurrent-{i}",
                            detail=json.dumps({"i": i}),
                        )
                    writers_done.append(True)
                except Exception as exc:  # pragma: no cover - 失败路径
                    errors.append(f"writer: {exc!r}")

            threads = [threading.Thread(target=reader) for _ in range(4)]
            threads += [threading.Thread(target=writer) for _ in range(4)]
            for t in threads:
                t.start()
            deadline = time.monotonic() + 20
            for t in threads:
                t.join(max(0.1, deadline - time.monotonic()))
            hung = [t for t in threads if t.is_alive()]
            self.assertFalse(errors, f"线程内出现异常: {errors}")
            self.assertEqual(
                len(hung), 0,
                "存在仍挂起的线程——疑似登录日志锁死锁回归",
            )
            self.assertEqual(len(readers_done), 4)
            self.assertEqual(len(writers_done), 4)

            items = load_admin_login_logs()
            self.assertEqual(len(items), 4 * 30)
        finally:
            import app.admin_audit as audit

            audit.ADMIN_LOGIN_LOG_FILE = original_file
            tmp.cleanup()


if __name__ == "__main__":
    if CHILD_FLAG in sys.argv:
        code = _run_child_probe()
        print("PROBE-OK")
        sys.exit(code)
    unittest.main()
