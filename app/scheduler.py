"""Background scheduling: periodic uptime checks for every enabled monitor."""

import time
from datetime import datetime, timezone

import requests
from apscheduler.schedulers.background import BackgroundScheduler

from app.alerts import send_alert
from app.db import get_connection

CHECK_INTERVAL_MINUTES = 15
HTTP_TIMEOUT_SECONDS = 10

# HTTP 5xx means the server itself is failing to handle the request, which is
# what "down" is meant to capture. 4xx responses (404, 401, ...) still prove
# the site is reachable and serving traffic, so they count as "up".
DOWN_STATUS_THRESHOLD = 500


def _perform_http_check(website_url: str) -> tuple[bool, int]:
    """Return (is_up, response_time_ms) for a single HTTP check."""
    start = time.monotonic()
    try:
        response = requests.get(website_url, timeout=HTTP_TIMEOUT_SECONDS)
        response_time_ms = int((time.monotonic() - start) * 1000)
        is_up = response.status_code < DOWN_STATUS_THRESHOLD
        return is_up, response_time_ms
    except requests.RequestException:
        response_time_ms = int((time.monotonic() - start) * 1000)
        return False, response_time_ms


def run_check(monitor_id: int, website_url: str, slack_webhook_url: str) -> None:
    """Run a single check for one monitor, recording it and alerting on state changes."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT check_status FROM checks
                WHERE monitor_id = %s
                ORDER BY check_time DESC
                LIMIT 1
                """,
                (monitor_id,),
            )
            previous_row = cur.fetchone()
        previous_status = previous_row[0] if previous_row else None

        is_up, response_time_ms = _perform_http_check(website_url)
        check_time = datetime.now(timezone.utc)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO checks (check_time, check_status, response_time, monitor_id)
                VALUES (%s, %s, %s, %s)
                RETURNING check_id
                """,
                (check_time, is_up, response_time_ms, monitor_id),
            )
            check_id = cur.fetchone()[0]
        conn.commit()

        is_first_check = previous_status is None
        state_changed = not is_first_check and previous_status != is_up
        if state_changed:
            alert_sent = send_alert(slack_webhook_url, website_url, is_up)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alerts (alert_time, alert_sent, check_id)
                    VALUES (%s, %s, %s)
                    """,
                    (datetime.now(timezone.utc), alert_sent, check_id),
                )
            conn.commit()
    finally:
        conn.close()


def check_all_monitors() -> None:
    """Fetch every enabled monitor and run a check for each one."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT monitor_id, website_url, slack_webhook_url
                FROM monitors
                WHERE monitor_status = TRUE
                """
            )
            monitors = cur.fetchall()
    finally:
        conn.close()

    for monitor_id, website_url, slack_webhook_url in monitors:
        run_check(monitor_id, website_url, slack_webhook_url)


def start_scheduler() -> BackgroundScheduler:
    """Start the background job that checks every monitor every 15 minutes."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_all_monitors,
        trigger="interval",
        minutes=CHECK_INTERVAL_MINUTES,
        id="check_all_monitors",
    )
    scheduler.start()
    return scheduler
