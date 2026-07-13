# Uptime Monitor

A backend uptime monitoring service built with Python, Flask, and PostgreSQL. It periodically checks whether registered websites are reachable, records every result, and posts a Slack notification the moment a site's status changes — one alert when it goes down, one alert when it recovers.

The service is designed around a clean separation between its two responsibilities: an HTTP API (used at registration time and for querying monitor state) and a background scheduler (used continuously to probe registered sites). Monitors are identified by a per-monitor API key issued at registration, so multiple independent users can share one deployment without their monitors interfering with each other.

The architecture is intentionally minimal. Flask handles the API, APScheduler runs checks in-process on a background thread, and PostgreSQL stores all state. There are no external queues, no Redis dependencies, and no separate worker processes — the full stack runs with a single `docker compose up` command.

---

## Features

- Register a website for monitoring with a Slack webhook URL; receive an API key scoped to that monitor
- Automatic HTTP health checks every 15 minutes via an in-process APScheduler background job
- Response time measured in milliseconds and stored with every check result
- HTTP 5xx responses and network exceptions classified as DOWN; 1xx–4xx classified as UP
- State-change alerting: Slack is notified once when a site goes down and once when it recovers — not on every failed check
- Alert delivery outcome (`alert_sent` boolean) persisted in the database, so failed webhook calls are auditable
- API key authentication enforced by a reusable `require_api_key` decorator
- All SQL uses parameterized queries; no string concatenation
- Database connection retry loop so the Flask container survives the Postgres startup race in Docker
- Fully Dockerized: `docker compose up --build` is the only command needed to run the service locally
- 14 automated tests covering the API, auth decorator, scheduler logic, and alert delivery, running against a real Postgres instance
- GitHub Actions CI pipeline that provisions a Postgres service container and runs the full test suite on every push

---

## Tech Stack

| Technology | Version | Role |
|---|---|---|
| Python | 3.11 | Runtime |
| Flask | 3.1.3 | HTTP API framework |
| PostgreSQL | 15 | Persistent storage |
| psycopg2-binary | 2.9.12 | PostgreSQL adapter |
| APScheduler | 3.11.2 | In-process background job scheduler |
| requests | 2.34.2 | Outbound HTTP checks and Slack webhook calls |
| Docker | — | Container runtime |
| docker-compose | — | Multi-container local orchestration |
| pytest | 9.0.3 | Test runner |
| pytest-cov | 7.1.0 | Coverage reporting |
| GitHub Actions | — | CI pipeline |
| Railway | — | Target deployment platform (compatible via standard Dockerfile) |

---

## Architecture

```
                          HTTP Clients
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Flask API       │
                    │─────────────────────│
                    │  POST /monitors     │  ← Register a new monitor
                    │  GET  /monitors     │  ← List monitors (auth required)
                    │  GET  /health       │  ← Health check
                    └──────────┬──────────┘
                               │ psycopg2
                               │ (fresh connection per request)
                               ▼
                    ┌─────────────────────┐
                    │     PostgreSQL      │
                    │─────────────────────│
                    │  monitors           │
                    │  checks             │
                    │  alerts             │
                    └──────────▲──────────┘
                               │ psycopg2
                               │ (fresh connection per check)
                    ┌──────────┴──────────┐
                    │   APScheduler       │
                    │  (BackgroundSched.) │
                    │─────────────────────│
                    │  every 15 minutes:  │
                    │  check_all_monitors │
                    │    └─ run_check()   │
                    └──────────┬──────────┘
                               │ requests.get(url, timeout=10)
                               ▼
                    ┌─────────────────────┐
                    │   Target Website    │
                    └──────────┬──────────┘
                               │ status changed?
                               ▼
                    ┌─────────────────────┐
                    │   send_alert()      │──► Slack Incoming Webhook
                    └─────────────────────┘
```

Both the Flask API layer and the scheduler access the database through the same `get_connection()` helper in `app/db.py`. Each unit of work — one HTTP request, one monitor check — opens its own connection and closes it when done.

---

## Project Structure

```
uptime-monitor/
│
├── app/
│   ├── __init__.py          # Flask app factory; starts the scheduler on import
│   ├── db.py                # get_connection() with startup retry logic
│   ├── middleware.py        # require_api_key decorator
│   ├── alerts.py            # send_alert() — posts to Slack
│   ├── scheduler.py         # check_all_monitors(), run_check(), start_scheduler()
│   └── routes/
│       ├── __init__.py
│       └── monitors.py      # POST /monitors and GET /monitors endpoints
│
├── tests/
│   ├── conftest.py          # Fixtures: schema creation, table teardown, test client
│   ├── test_monitors.py     # API endpoint and auth decorator tests
│   ├── test_scheduler.py    # run_check() state-change and alerting logic tests
│   └── test_alerts.py       # send_alert() unit tests
│
├── init.sql                 # Schema DDL — auto-executed by Postgres on first boot
├── run.py                   # Entrypoint: starts the Flask dev server
├── Dockerfile               # python:3.11-slim image definition
├── .dockerignore            # Excludes .env, venv/, tests/, etc. from the build context
├── docker-compose.yml       # `web` and `db` service definitions
├── requirements.txt         # Pinned dependencies
├── .env.example             # Template for required environment variables
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions: test on every push
```

---

## Database Schema

The schema is defined in [`init.sql`](init.sql) and is automatically applied by Postgres when the `db` container first starts (via the `docker-entrypoint-initdb.d` mount).

### `monitors`

Stores every registered website and its associated configuration.

| Column | Type | Description |
|---|---|---|
| `monitor_id` | `SERIAL` PK | Auto-incrementing primary key |
| `website_url` | `TEXT NOT NULL` | The URL that will be checked |
| `slack_webhook_url` | `TEXT NOT NULL` | Slack Incoming Webhook URL for alerts |
| `api_key` | `TEXT NOT NULL` | 64-character hex token issued at registration |
| `monitor_status` | `BOOLEAN NOT NULL DEFAULT TRUE` | Whether the monitor is enabled |

An index on `api_key` (`idx_monitors_api_key`) supports fast lookups in the auth decorator.

### `checks`

Records the result of every individual health check. One row per execution of `run_check()`.

| Column | Type | Description |
|---|---|---|
| `check_id` | `SERIAL` PK | Auto-incrementing primary key |
| `check_time` | `TIMESTAMP NOT NULL` | UTC timestamp of the check |
| `check_status` | `BOOLEAN NOT NULL` | `TRUE` = up, `FALSE` = down |
| `response_time` | `INTEGER NOT NULL` | Round-trip time in milliseconds |
| `monitor_id` | `INTEGER NOT NULL` FK → `monitors` | Which monitor this check belongs to |

A composite index on `(monitor_id, check_time DESC)` (`idx_checks_monitor_id_check_time`) supports the "fetch most recent check for this monitor" query that runs before every new check.

### `alerts`

Records every Slack notification attempt. One row is written whenever a state change is detected.

| Column | Type | Description |
|---|---|---|
| `alert_id` | `SERIAL` PK | Auto-incrementing primary key |
| `alert_time` | `TIMESTAMP NOT NULL` | UTC timestamp of the alert attempt |
| `alert_sent` | `BOOLEAN NOT NULL` | Whether Slack returned a success response |
| `check_id` | `INTEGER NOT NULL` FK → `checks` | The check that triggered this alert |

**Relationships:** `checks.monitor_id → monitors.monitor_id` and `alerts.check_id → checks.check_id`. Cascading is not configured; deleting a monitor requires removing its checks and alerts first.

---

## API Documentation

### `POST /monitors`

Registers a new website for monitoring. No authentication required. Returns an API key that controls access to this monitor going forward.

**Request**

| | |
|---|---|
| Method | `POST` |
| Path | `/monitors` |
| Content-Type | `application/json` |

**Body**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | The website URL to monitor |
| `slack_webhook_url` | string | Yes | Slack Incoming Webhook URL for alerts |

**Responses**

| Status | Condition | Body |
|---|---|---|
| `201 Created` | Monitor created successfully | `{"api_key": "<64-char hex string>"}` |
| `400 Bad Request` | `url` or `slack_webhook_url` is missing | `{"error": "url and slack_webhook_url are required"}` |

**Example**

```bash
curl -X POST http://localhost:5000/monitors \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "slack_webhook_url": "https://hooks.slack.com/services/T00/B00/xxx"
  }'
```

```json
{
  "api_key": "a3f2c1d4e5b6a7f8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
}
```

---

### `GET /monitors`

Returns all monitors associated with the provided API key. Requires authentication.

**Request**

| | |
|---|---|
| Method | `GET` |
| Path | `/monitors` |
| Headers | `X-API-Key: <your-api-key>` |

**Responses**

| Status | Condition | Body |
|---|---|---|
| `200 OK` | Key is valid | JSON array of monitor objects |
| `401 Unauthorized` | Header is absent | `{"error": "missing api key"}` |
| `401 Unauthorized` | Key not found in database | `{"error": "invalid api key"}` |

**Example**

```bash
curl http://localhost:5000/monitors \
  -H "X-API-Key: a3f2c1d4e5b6a7f8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
```

```json
[
  {
    "monitor_id": 1,
    "website_url": "https://example.com",
    "slack_webhook_url": "https://hooks.slack.com/services/T00/B00/xxx",
    "monitor_status": true
  }
]
```

---

### `GET /health`

Health check endpoint. No authentication required. Used by load balancers and container orchestrators to verify the service is running.

**Example**

```bash
curl http://localhost:5000/health
```

```json
{
  "status": "ok"
}
```

---

## Authentication

Authenticated endpoints require an `X-API-Key` header containing the 64-character hex token issued when the monitor was created.

The `require_api_key` decorator in [`app/middleware.py`](app/middleware.py) handles validation. It reads the header, opens a database connection, executes a parameterized `SELECT` against `monitors.api_key`, and either rejects the request with a `401` or stores the key in Flask's request-scoped `g` object and calls the wrapped view function.

```
Request → require_api_key decorator
              │
              ├── No X-API-Key header?   → 401 {"error": "missing api key"}
              │
              ├── Key not in monitors?   → 401 {"error": "invalid api key"}
              │
              └── Key found             → g.api_key = key → call view function
```

**Why API keys instead of JWT?**

Monitors are not user accounts. There is no login flow, no session, and no need to encode expiry claims or sign tokens. An opaque random token looked up against the database is simpler to implement, straightforward to revoke (delete the row or set `monitor_status = FALSE`), and carries no client-side state. JWT would add token verification, expiry handling, and a signing secret to manage — none of which provides a meaningful security benefit for this use case.

---

## Scheduler

The scheduler is started in [`app/__init__.py`](app/__init__.py) using APScheduler's `BackgroundScheduler`, which runs the job on a daemon thread inside the same process as Flask. The scheduler is shut down cleanly via `atexit` when the process exits.

`DISABLE_SCHEDULER=1` suppresses startup entirely (used by the test suite to avoid needing a live database connection at import time).

**Check frequency:** every 15 minutes (`CHECK_INTERVAL_MINUTES = 15` in [`app/scheduler.py`](app/scheduler.py)).

**Monitoring flow:**

```
check_all_monitors()
    │
    └── SELECT monitor_id, website_url, slack_webhook_url
        FROM monitors WHERE monitor_status = TRUE
            │
            └── for each monitor → run_check(monitor_id, website_url, slack_webhook_url)
                    │
                    ├── 1. Query most recent check_status for this monitor
                    │
                    ├── 2. requests.get(url, timeout=10)
                    │        ├── status_code < 500  → is_up = True
                    │        ├── status_code >= 500 → is_up = False
                    │        └── RequestException   → is_up = False
                    │
                    ├── 3. Measure elapsed time in milliseconds
                    │
                    ├── 4. INSERT into checks (check_time, check_status, response_time, monitor_id)
                    │
                    └── 5. State changed AND not the first check?
                              │
                              ├── send_alert(slack_webhook_url, website_url, is_up)
                              │
                              └── INSERT into alerts (alert_time, alert_sent, check_id)
```

**State change detection:** `run_check()` reads the most recent row from `checks` for that monitor before performing the HTTP request. If no prior row exists (first check), no alert is generated. If a prior row exists and its `check_status` differs from the new result, a Slack notification is sent and an `alerts` row is written.

**Status classification:** HTTP responses with status codes below 500 are classified as UP. Responses at 500 or above (5xx server errors) and any network-level exception (`requests.RequestException`) are classified as DOWN. A 404 or 401 still proves the server is reachable, so it counts as UP.

---

## Running Locally

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Git

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/pranavsharma-dev/uptime-monitor.git
cd uptime-monitor

# 2. Create your environment file
cp .env.example .env
# Edit .env and set a secure DB_PASSWORD before proceeding

# 3. Build images and start all services
docker compose up --build
```

The `db` service starts first. `init.sql` is mounted into `docker-entrypoint-initdb.d/` and executed automatically on the first boot, creating all three tables and their indexes. The `web` service starts immediately after and retries its database connection until Postgres is ready (up to 10 attempts with a 2-second delay between each).

The API is available at `http://localhost:5000` once both containers are running.

### Running Tests

Tests require a reachable Postgres instance. Start only the database container, then run pytest with the required environment variables:

```bash
# Start the database
docker compose up -d db

# Run the full test suite
DISABLE_SCHEDULER=1 \
DB_HOST=localhost \
DB_PORT=5432 \
DB_NAME=uptime \
DB_USER=<your-DB_USER> \
DB_PASSWORD=<your-DB_PASSWORD> \
pytest --cov=app
```

To stop all containers and remove volumes when done:

```bash
docker compose down -v
```

---

## Environment Variables

All credentials and tuning parameters are supplied via environment variables. Copy [`.env.example`](.env.example) to `.env` and fill in values before running.

| Variable | Default (example) | Required | Description |
|---|---|---|---|
| `DB_HOST` | `db` | Yes | Postgres hostname (`db` inside Docker, `localhost` for local testing) |
| `DB_PORT` | `5432` | No | Postgres port |
| `DB_NAME` | `uptime` | Yes | Database name |
| `DB_USER` | `pranav` | Yes | Database user |
| `DB_PASSWORD` | *(none)* | Yes | Database password — never hardcode this |
| `DB_MAX_RETRIES` | `10` | No | Max connection attempts before raising an error |
| `DB_RETRY_DELAY` | `2` | No | Seconds to wait between retry attempts |
| `DISABLE_SCHEDULER` | `0` | No | Set to `1` to skip starting the background scheduler (used in tests) |
| `PORT` | `5000` | No | Port Flask binds to |

In production (e.g. Railway), set these directly as service environment variables rather than using a `.env` file. The `.env` file is in `.gitignore` and must never be committed.

---

## Testing

Tests are written with [pytest](https://pytest.org) and live in the [`tests/`](tests/) directory.

**Test strategy:** tests run against a real Postgres database rather than mocked `psycopg2` objects. Mocking the database would require reproducing every cursor and connection interface in test code without ever verifying the SQL itself — a wrong column name or constraint violation would still produce a passing test. A real disposable database is simpler to set up, exercises the actual schema and parameterized queries, and reflects the same environment used in CI.

The `conftest.py` fixtures:
- Create the schema once per session (from `init.sql`)
- Truncate all tables with `RESTART IDENTITY CASCADE` before every individual test, so each test starts from a clean, empty database

**Test files:**

| File | Tests | What is covered |
|---|---|---|
| `test_monitors.py` | 5 | `POST /monitors` (valid, missing fields), `GET /monitors` (no key, invalid key, valid key) |
| `test_scheduler.py` | 5 | First check does not alert, state change triggers alert, no state change does not alert, 5xx counts as DOWN, 4xx counts as UP |
| `test_alerts.py` | 4 | DOWN message content, BACK UP message content, returns `False` on `RequestException`, returns `False` on non-OK response |

**Running tests:**

```bash
# With coverage report
pytest --cov=app

# Verbose output
pytest -v --cov=app

# Single file
pytest tests/test_monitors.py -v
```

The test suite produces **86% coverage** across the `app/` package (14 tests, 145 statements).

---

## CI/CD

The GitHub Actions workflow is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and triggers on every push to any branch.

**What happens on every push:**

1. GitHub spins up an `ubuntu-latest` runner
2. A Postgres 15 service container starts with a health check (`pg_isready`) ensuring the database is accepting connections before tests begin
3. Python 3.11 is configured
4. `pip install -r requirements.txt` installs all pinned dependencies
5. `pytest --cov=app` runs the full test suite against the live Postgres service container

**Credentials:** the Postgres service container uses fixed, non-sensitive credentials (`uptime_test` / `postgres` / `postgres`) scoped entirely to that ephemeral container, which exists only for the duration of the job and is discarded afterward. These are not application secrets — using GitHub repository secrets for a throwaway CI database would add configuration overhead (a step every fork would need to repeat) without protecting anything real, since the container never holds production data and isn't reachable outside the job. Real credentials (used by the deployed application) are always sourced from environment variables and are never present in the workflow file — see [Environment Variables](#environment-variables). `DISABLE_SCHEDULER=1` is set as a job-level environment variable so the background scheduler does not start during the test run.

Because the workflow requires no repository configuration, CI runs successfully on forks and on this repository without any manual setup.

---

## Design Decisions

### APScheduler vs Celery

**Alternatives considered:** Celery with a Redis or RabbitMQ broker; a simple `threading.Timer` loop.

**Decision:** APScheduler's `BackgroundScheduler` runs a single recurring job on a daemon thread inside the same process as Flask. It requires no external dependencies and no separate worker process.

Celery is the right tool when jobs need to run across multiple machines, when tasks are triggered by events rather than a schedule, or when a failed task needs to be retried independently of the web server. None of those requirements apply here: the job runs on a fixed interval, produces no result that Flask needs to consume, and can tolerate one missed run if the process restarts. APScheduler handles this with far less operational overhead.

The tradeoff is that the scheduler shares memory (and failure modes) with the web server. If the web process crashes, checks stop running until it restarts. At the scale this service targets, that is acceptable.

---

### API Keys vs JWT

**Alternatives considered:** JWT (JSON Web Tokens) with HMAC or RSA signing.

**Decision:** Each monitor is issued a `secrets.token_hex(32)` API key at registration. Every authenticated request validates the key against the database with a parameterized query.

Monitors are not user sessions. There is no login, no token refresh, no need to embed claims. JWTs add a signing key to manage, a token-verification step, expiry handling, and client-side state — all complexity that provides no practical security benefit when the authorisation model is "does this key exist in the database." API keys are also trivially revocable: set `monitor_status = FALSE` or delete the row.

---

### Parameterized SQL

Every database query in the codebase uses psycopg2's `%s` placeholders and passes values as a separate tuple argument to `cursor.execute()`. String formatting or f-strings are never used to build SQL.

This is the primary defence against SQL injection. psycopg2 sends the query and the values as separate protocol messages; the database driver handles quoting and escaping before the query reaches Postgres. There is no code path in which user-supplied data is concatenated into a SQL string.

---

### Per-Request Database Connections

**Alternatives considered:** A module-level singleton connection; `psycopg2.pool.ThreadedConnectionPool`.

**Decision:** `get_connection()` opens a brand-new psycopg2 connection on every call and the caller closes it in a `finally` block. No connection is shared between calls.

psycopg2 connections are not thread-safe for concurrent use. The Flask application handles HTTP requests on multiple threads while the APScheduler job runs on its own background thread. A shared connection would require external locking and could silently corrupt query results if two threads used it simultaneously. Per-unit-of-work connections eliminate that class of bug entirely.

The overhead of opening a connection per request is measurable but small relative to the cost of a network round-trip to a remote Postgres server. A `ThreadedConnectionPool` would be the correct next step if request throughput ever made connection setup a bottleneck — but that optimisation is straightforward to add without restructuring the rest of the code.

---

### Alert on Status Change vs Alert on Every Failure

**Decision:** `run_check()` compares the new `check_status` to the most recent row in `checks` for that monitor. An `alerts` row is written, and Slack is notified, only when those two values differ.

Alerting on every failed check would generate a Slack message every 15 minutes for the duration of any outage. That volume trains teams to ignore the channel. Alerting on state change means exactly two messages per outage: one when the site goes down, one when it recovers. The first check for a new monitor is treated as establishing baseline state and never triggers an alert, regardless of outcome.

---

### Dockerized Development

The `Dockerfile` uses `python:3.11-slim` as the base image. Dependencies are installed before the application code is copied, so Docker can cache the `pip install` layer and skip it on rebuilds that only change Python files.

`debug=True` is explicitly avoided in `run.py`. Flask's debug mode starts a subprocess reloader, which would import `app/__init__.py` a second time and launch a duplicate APScheduler instance — resulting in two background threads running checks concurrently and producing duplicate database rows.

---

### Retry Logic for Database Startup

`docker-compose`'s `depends_on` controls container start order, not container readiness. The `db` container reports "started" as soon as the Docker daemon starts the process — before Postgres has initialised its data directory, applied `init.sql`, and opened its listening socket. The `web` container starts immediately after and its first database connection attempt often arrives before Postgres is ready.

`get_connection()` in `app/db.py` catches `psycopg2.OperationalError` and retries up to `DB_MAX_RETRIES` times (default: 10) with `DB_RETRY_DELAY` seconds between attempts (default: 2 seconds). This gives Postgres up to 20 seconds to become ready without requiring a `wait-for-it.sh` script, an entrypoint wrapper, or a `healthcheck`-based `depends_on` condition in the Compose file.

---

## Security Considerations

**SQL injection:** All database queries use parameterized statements (`cursor.execute(sql, (values,))`). User input is never interpolated into query strings. This is enforced consistently across `app/middleware.py`, `app/routes/monitors.py`, and `app/scheduler.py`.

**Secret management:** Application database credentials are never hardcoded. They are read exclusively from environment variables at runtime. The `.env` file is listed in `.gitignore`, and `.dockerignore` prevents it from ever being copied into a built image. CI uses fixed, non-sensitive credentials scoped to a disposable, job-scoped Postgres container — not a stand-in for how the deployed application is configured.

**API key generation:** Keys are generated with `secrets.token_hex(32)`, which produces 32 bytes of cryptographically random data represented as a 64-character hex string. The `secrets` module uses the operating system's CSPRNG (`os.urandom`), making the keys resistant to prediction or brute-force enumeration.

**API key lookup:** The auth decorator performs a `SELECT` with a parameterized query and a `LIMIT 1` to confirm key existence, then compares the result as a boolean. The key value itself is not returned in any response beyond the initial registration.

**Connection handling:** Every connection is opened inside a `try` block with `conn.close()` in the `finally` clause, ensuring connections are returned to Postgres even when exceptions occur. Autocommit is never enabled; writes are committed explicitly after each logical operation.

**Attack surface:** `POST /monitors` is unauthenticated by design (anyone can register a monitor). Rate limiting is not implemented — see [Future Improvements](#future-improvements).

---

## Future Improvements

The following enhancements are not implemented but represent natural next steps for a production deployment.

**Reliability and performance**
- Replace Flask's built-in development server with a production WSGI server (Gunicorn or Waitress)
- Add a `psycopg2.pool.ThreadedConnectionPool` to amortise connection setup cost under load
- Implement retry/exponential backoff for failed Slack webhook calls
- Move check execution to a task queue (Celery + Redis) to support parallel checks at scale and decouple check frequency from web server availability
- Paginate `GET /monitors` and add endpoints to query check history and alert history

**Observability**
- Structured JSON logging with request IDs for correlation
- Prometheus metrics endpoint exposing check counts, alert counts, error rates, and connection pool utilisation
- Grafana dashboard for visualising uptime history and alert frequency
- Distributed tracing (OpenTelemetry)

**Features**
- Multiple alert channels: email, PagerDuty, Microsoft Teams, webhooks
- Per-monitor check interval configuration (currently fixed at 15 minutes)
- HTTP method configuration (HEAD requests are cheaper than GET for availability checks)
- Custom HTTP headers and expected status code configuration per monitor
- Monitor pause/resume endpoint
- Dashboard UI for viewing monitor status, check history, and alert log

**Security and operations**
- Rate limiting on `POST /monitors` to prevent abuse (Flask-Limiter)
- User accounts with password authentication, replacing the per-monitor key model
- HTTPS termination (nginx reverse proxy or TLS at the load balancer)
- Infrastructure-as-code for Railway or AWS deployment (Terraform)
- Kubernetes manifests for horizontal scaling
- Database migrations managed by Alembic rather than a raw `init.sql`

---

## Lessons Learned

This project demonstrates a set of backend engineering fundamentals that appear in most production services:

- **Separation of concerns** between the HTTP layer, persistence layer, scheduling layer, and alerting layer — each module has one job and a clear interface
- **Thread safety** as a concrete constraint: the choice to avoid shared connections is driven by psycopg2's threading model, not convention
- **Defensive I/O**: network calls (`requests.get`, the Slack webhook POST) are wrapped in `try/except` so a flaky external service can't bring down the monitoring loop
- **SQL security by default**: parameterized queries aren't opt-in hardening — they're the only query pattern used in the codebase
- **Testing against real infrastructure**: using a disposable Postgres database in tests catches schema mistakes, constraint violations, and query errors that mocks would silently pass
- **Operational realism in local dev**: the DB startup retry loop is a response to an actual docker-compose behaviour, not a theoretical concern
- **Alert design as a product decision**: choosing state-change alerting over per-failure alerting is an engineering choice with a direct impact on how usable the system is for the people receiving the alerts
