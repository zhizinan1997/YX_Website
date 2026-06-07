from __future__ import annotations

import threading
import time
from pathlib import Path

from . import config, main_site, mailer, monitor, storage


class CheckRunner:
    def __init__(self, *, data_dir: Path | None = None, main_data_dir: Path | None = None):
        self.data_dir = data_dir or config.CHECK_DATA_DIR
        self.main_data_dir = main_data_dir or config.MAIN_DATA_DIR
        self._running: set[int] = set()
        self._lock = threading.RLock()

    def is_running(self, target_id: int) -> bool:
        with self._lock:
            return int(target_id) in self._running

    def run_async(self, target_id: int, *, trigger: str = "manual") -> bool:
        target_id = int(target_id)
        with self._lock:
            if target_id in self._running:
                return False
            self._running.add(target_id)
        thread = threading.Thread(target=self._run_guarded, args=(target_id, trigger), daemon=True)
        thread.start()
        return True

    def _run_guarded(self, target_id: int, trigger: str) -> None:
        try:
            self.run_with_retries(target_id, trigger=trigger)
        finally:
            with self._lock:
                self._running.discard(int(target_id))

    def run_with_retries(self, target_id: int, *, trigger: str) -> None:
        target = storage.get_target(target_id, self.data_dir)
        if not target or not target.get("enabled", 1):
            return

        last_run_id = None
        last_result = None
        last_incident_id = None
        delays = [0, *config.RETRY_DELAYS_SECONDS]
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)
            latest_target = storage.get_target(target_id, self.data_dir) or target
            result = monitor.check_url(latest_target["url"], timeout_ms=int(latest_target.get("timeout_ms") or config.DEFAULT_TARGET_TIMEOUT_MS))
            run_id, incident_id = storage.record_run(latest_target, result, attempt=attempt, trigger=trigger, data_dir=self.data_dir)
            last_run_id = run_id
            last_result = result
            last_incident_id = incident_id
            if result.get("status") == "ok":
                return

        if last_run_id and last_result:
            self._send_alert_if_needed(target_id, last_run_id, last_incident_id, last_result)

    def _send_alert_if_needed(self, target_id: int, run_id: int, incident_id: int | None, result: dict) -> None:
        incident = storage.get_open_incident(target_id, self.data_dir)
        if not incident:
            return
        if incident.get("alert_sent_at"):
            return
        target = storage.get_target(target_id, self.data_dir)
        run = storage.get_run(run_id, self.data_dir)
        if not target or not run:
            return

        recipients = main_site.get_verified_admin_emails(self.main_data_dir)
        subject = f"【元芯监测告警】{target.get('name') or '监测目标'} 仍不可用"
        if not recipients:
            storage.record_alert_event(
                incident_id=incident_id or incident.get("id"),
                target_id=target_id,
                recipients=[],
                subject=subject,
                status="skipped",
                error="主站 admin_users.json 中没有已验证邮箱的管理员",
                data_dir=self.data_dir,
            )
            return

        settings = main_site.get_smtp_settings(self.main_data_dir)
        payload = {
            "target_name": target.get("name"),
            "url": target.get("url"),
            "status": run.get("status"),
            "latency_ms": run.get("latency_ms"),
            "http_status": run.get("http_status"),
            "resource_failed": run.get("resource_failed"),
            "error_summary": run.get("error_summary"),
            "finished_at": run.get("finished_at"),
        }
        try:
            mailer.send_alert(settings, recipients, payload)
        except Exception as exc:
            storage.record_alert_event(
                incident_id=incident_id or incident.get("id"),
                target_id=target_id,
                recipients=recipients,
                subject=subject,
                status="failed",
                error=str(exc),
                data_dir=self.data_dir,
            )
            return

        storage.record_alert_event(
            incident_id=incident_id or incident.get("id"),
            target_id=target_id,
            recipients=recipients,
            subject=subject,
            status="sent",
            data_dir=self.data_dir,
        )
        storage.mark_run_alert_sent(run_id, self.data_dir)


class Scheduler:
    def __init__(self, runner: CheckRunner, *, data_dir: Path | None = None, poll_seconds: int = 20):
        self.runner = runner
        self.data_dir = data_dir or config.CHECK_DATA_DIR
        self.poll_seconds = int(poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="check-site-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                storage.prune_old_data(self.data_dir)
                for target in storage.due_targets(self.data_dir):
                    target_id = int(target["id"])
                    if self.runner.is_running(target_id):
                        continue
                    storage.reserve_next_check(target_id, self.data_dir)
                    self.runner.run_async(target_id, trigger="schedule")
            except Exception:
                pass
            self._stop.wait(self.poll_seconds)

