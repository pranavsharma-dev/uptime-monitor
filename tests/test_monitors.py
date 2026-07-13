"""Tests for the /monitors endpoints and the require_api_key decorator."""


def _create_monitor(client, url="https://example.com", slack="https://hooks.slack.test/x"):
    response = client.post("/monitors", json={"url": url, "slack_webhook_url": slack})
    assert response.status_code == 201
    return response.get_json()["api_key"]


def test_unauth_returns_401(client):
    response = client.get("/monitors")

    assert response.status_code == 401
    assert response.get_json() == {"error": "missing api key"}


def test_invalid_key_returns_401(client):
    response = client.get("/monitors", headers={"X-API-Key": "not-a-real-key"})

    assert response.status_code == 401
    assert response.get_json() == {"error": "invalid api key"}


def test_create_monitor_returns_api_key(client):
    response = client.post(
        "/monitors",
        json={"url": "https://example.com", "slack_webhook_url": "https://hooks.slack.test/x"},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert "api_key" in body
    assert isinstance(body["api_key"], str)
    assert len(body["api_key"]) == 64  # secrets.token_hex(32)


def test_missing_fields_returns_400(client):
    response = client.post("/monitors", json={"url": "https://example.com"})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_get_monitors_returns_list(client):
    api_key = _create_monitor(client, url="https://example.com")

    response = client.get("/monitors", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["website_url"] == "https://example.com"
    assert body[0]["monitor_status"] is True
