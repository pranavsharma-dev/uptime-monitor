-- Uptime Monitor schema

CREATE TABLE IF NOT EXISTS monitors (
    monitor_id SERIAL PRIMARY KEY,
    website_url TEXT NOT NULL,
    slack_webhook_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    monitor_status BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS checks (
    check_id SERIAL PRIMARY KEY,
    check_time TIMESTAMP NOT NULL,
    check_status BOOLEAN NOT NULL,
    response_time INTEGER NOT NULL,
    monitor_id INTEGER NOT NULL REFERENCES monitors(monitor_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id SERIAL PRIMARY KEY,
    alert_time TIMESTAMP NOT NULL,
    alert_sent BOOLEAN NOT NULL,
    check_id INTEGER NOT NULL REFERENCES checks(check_id)
);

CREATE INDEX IF NOT EXISTS idx_checks_monitor_id_check_time ON checks(monitor_id, check_time DESC);
CREATE INDEX IF NOT EXISTS idx_monitors_api_key ON monitors(api_key);
