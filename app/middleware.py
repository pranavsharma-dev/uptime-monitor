"""Auth decorator for API-key protected routes."""

from functools import wraps

from flask import g, jsonify, request

from app.db import get_connection


def require_api_key(view_func):
    """Require a valid X-API-Key header, matched against monitors.api_key."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({"error": "missing api key"}), 401

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM monitors WHERE api_key = %s LIMIT 1",
                    (api_key,),
                )
                key_exists = cur.fetchone() is not None
        finally:
            conn.close()

        if not key_exists:
            return jsonify({"error": "invalid api key"}), 401

        g.api_key = api_key
        return view_func(*args, **kwargs)

    return wrapped
