"""Tests for run_check's state-change / alerting behaviour."""

from unittest.mock import Mock, patch

import requests

from app.scheduler import run_check


def _insert_monitor(db_conn, website_url="https://example.com", slack="https://hooks.slack.test/x"):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO monitors (website_url, slack_webhook_url, api_key, monitor_status)
            VALUES (%s, %s, %s, TRUE)
            RETURNING monitor_id
            """,
            (website_url, slack, "test-key"),
        )
        monitor_id = cur.fetchone()[0]
    db_conn.commit()
    return monitor_id


def _fetch_checks(db_conn, monitor_id):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT check_status FROM checks WHERE monitor_id = %s ORDER BY check_time",
            (monitor_id,),
        )
        return [row[0] for row in cur.fetchall()]


def _fetch_alert_count(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM alerts")
        return cur.fetchone()[0]


@patch("app.scheduler.requests.get")
def test_first_check_does_not_alert(mock_get, db_conn):
    mock_get.return_value = Mock(status_code=200)
    monitor_id = _insert_monitor(db_conn)

    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    assert _fetch_checks(db_conn, monitor_id) == [True]
    assert _fetch_alert_count(db_conn) == 0


@patch("app.scheduler.send_alert")
@patch("app.scheduler.requests.get")
def test_state_change_triggers_alert(mock_get, mock_send_alert, db_conn):
    mock_send_alert.return_value = True
    monitor_id = _insert_monitor(db_conn)

    mock_get.return_value = Mock(status_code=200)
    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    mock_get.side_effect = requests.exceptions.ConnectionError("boom")
    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    assert _fetch_checks(db_conn, monitor_id) == [True, False]
    assert _fetch_alert_count(db_conn) == 1
    mock_send_alert.assert_called_once_with("https://hooks.slack.test/x", "https://example.com", False)


@patch("app.scheduler.requests.get")
def test_no_state_change_does_not_alert(mock_get, db_conn):
    mock_get.return_value = Mock(status_code=200)
    monitor_id = _insert_monitor(db_conn)

    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")
    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    assert _fetch_checks(db_conn, monitor_id) == [True, True]
    assert _fetch_alert_count(db_conn) == 0


@patch("app.scheduler.requests.get")
def test_5xx_response_counts_as_down(mock_get, db_conn):
    mock_get.return_value = Mock(status_code=503)
    monitor_id = _insert_monitor(db_conn)

    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    assert _fetch_checks(db_conn, monitor_id) == [False]


@patch("app.scheduler.requests.get")
def test_4xx_response_counts_as_up(mock_get, db_conn):
    mock_get.return_value = Mock(status_code=404)
    monitor_id = _insert_monitor(db_conn)

    run_check(monitor_id, "https://example.com", "https://hooks.slack.test/x")

    assert _fetch_checks(db_conn, monitor_id) == [True]
