CREATE TABLE MONITORS(
    monitor_ID SERIAL PRIMARY KEY,
    slack_webhook_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    website_url TEXT NOT NULL,
    monitor_status BOOLEAN NOT NULL
);

CREATE TABLE CHECKS(
    check_ID SERIAL PRIMARY KEY,
    check_time TIMESTAMP NOT NULL,
    check_status BOOLEAN NOT NULL,
    response_time INTEGER NOT NULL,
    monitor_id INTEGER NOT NULL REFERENCES MONITORS
);

CREATE TABLE ALERTS(
    alert_ID SERIAL PRIMARY KEY,
    alert_time TIMESTAMP NOT NULL,
    check_id INTEGER NOT NULL REFERENCES CHECKS
);

    

  
    