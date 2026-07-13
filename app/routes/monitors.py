"""/monitors endpoints."""

import secrets

from flask import Blueprint, jsonify, request

from app.db import get_connection
from app.middleware import require_api_key

monitors_bp = Blueprint("monitors", __name__)


@monitors_bp.route("/monitors", methods=["POST"])
def create_monitor():
    data = request.get_json(silent=True) or {}
    website_url = data.get("url")
    slack_webhook_url = data.get("slack_webhook_url")

    if not website_url or not slack_webhook_url:
        return jsonify({"error": "url and slack_webhook_url are required"}), 400

    api_key = secrets.token_hex(32)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO monitors (website_url, slack_webhook_url, api_key, monitor_status)
                VALUES (%s, %s, %s, TRUE)
                """,
                (website_url, slack_webhook_url, api_key),
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"api_key": api_key}), 201


@monitors_bp.route("/monitors", methods=["GET"])
@require_api_key
def list_monitors():
    api_key = request.headers.get("X-API-Key")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT monitor_id, website_url, slack_webhook_url, monitor_status
                FROM monitors
                WHERE api_key = %s
                """,
                (api_key,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    monitors = [
        {
            "monitor_id": row[0],
            "website_url": row[1],
            "slack_webhook_url": row[2],
            "monitor_status": row[3],
        }
        for row in rows
    ]
    return jsonify(monitors), 200
