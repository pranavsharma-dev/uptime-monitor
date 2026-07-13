"""Tests for send_alert()."""

from unittest.mock import Mock, patch

import requests

from app.alerts import send_alert


@patch("app.alerts.requests.post")
def test_send_alert_down_message(mock_post):
    mock_post.return_value = Mock(ok=True)

    result = send_alert("https://hooks.slack.test/x", "https://example.com", is_up=False)

    assert result is True
    _, kwargs = mock_post.call_args
    assert "DOWN" in kwargs["json"]["text"]
    assert "example.com" in kwargs["json"]["text"]


@patch("app.alerts.requests.post")
def test_send_alert_up_message(mock_post):
    mock_post.return_value = Mock(ok=True)

    result = send_alert("https://hooks.slack.test/x", "https://example.com", is_up=True)

    assert result is True
    _, kwargs = mock_post.call_args
    assert "BACK UP" in kwargs["json"]["text"]


@patch("app.alerts.requests.post")
def test_send_alert_returns_false_on_exception(mock_post):
    mock_post.side_effect = requests.RequestException("network error")

    result = send_alert("https://hooks.slack.test/x", "https://example.com", is_up=False)

    assert result is False


@patch("app.alerts.requests.post")
def test_send_alert_returns_false_on_non_ok_response(mock_post):
    mock_post.return_value = Mock(ok=False)

    result = send_alert("https://hooks.slack.test/x", "https://example.com", is_up=False)

    assert result is False
