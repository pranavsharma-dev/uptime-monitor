"""Slack alerting."""

import requests

ALERT_TIMEOUT_SECONDS = 10


def send_alert(slack_webhook_url: str, website_url: str, is_up: bool) -> bool:
    """POST a status-change message to the monitor's Slack webhook.

    Returns True if Slack accepted the message, False otherwise. Never raises
    so a broken webhook can't take down a monitoring check.
    """
    if is_up:
        text = f":white_check_mark: {website_url} is BACK UP"
    else:
        text = f":rotating_light: {website_url} is DOWN"

    try:
        response = requests.post(
            slack_webhook_url, json={"text": text}, timeout=ALERT_TIMEOUT_SECONDS
        )
        return response.ok
    except requests.RequestException:
        return False
