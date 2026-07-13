"""Test fixtures.

We test against a real Postgres database rather than mocking psycopg2.
Mocking would mean hand-crafting fake cursor/connection objects for every
query shape in app/db.py, app/middleware.py, and app/routes/monitors.py --
that duplicates the SQL in the test suite without ever proving the SQL is
correct. A real (disposable) database is simpler to set up here, exercises
the actual parameterized queries and schema constraints, and is what CI
already provisions via the Postgres service container in
.github/workflows/ci.yml. The tradeoff is that tests require a reachable
Postgres instance (via `docker-compose up db` locally, or the CI service),
so they are not runnable fully offline.
"""

import os

os.environ.setdefault("DISABLE_SCHEDULER", "1")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "uptime_test")
os.environ.setdefault("DB_USER", "pranav")
os.environ.setdefault("DB_PASSWORD", "password")
os.environ.setdefault("DB_MAX_RETRIES", "5")
os.environ.setdefault("DB_RETRY_DELAY", "1")

import pytest

from app import app as flask_app
from app.db import get_connection

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "init.sql")


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Create the schema once per test session against the test database."""
    with open(SCHEMA_PATH, encoding="utf-8") as schema_file:
        schema_sql = schema_file.read()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all tables before every test so each one starts from empty."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE alerts, checks, monitors RESTART IDENTITY CASCADE")
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture
def app():
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_conn():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
