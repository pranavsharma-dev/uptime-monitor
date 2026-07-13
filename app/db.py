"""Database connection helper.

Every call to get_connection() opens a brand new psycopg2 connection using
credentials from the environment. We deliberately avoid a module-level
connection / connection pool: monitor checks run on a background scheduler
thread while HTTP requests are handled on Flask's own threads, and sharing a
single psycopg2 connection across threads is not safe (psycopg2 connections
are not thread-safe for concurrent use). Opening a short-lived connection per
unit of work keeps the concurrency model simple and correct at the cost of
some connection overhead, which is acceptable at this scale.
"""

import os
import time

import psycopg2

# docker-compose starts the web container as soon as the db container starts,
# not once Postgres is actually ready to accept connections. Retrying with a
# short backoff lets the Flask container wait out Postgres's startup instead
# of crashing on the first failed connection attempt.
MAX_RETRIES = int(os.environ.get("DB_MAX_RETRIES", "10"))
RETRY_DELAY_SECONDS = float(os.environ.get("DB_RETRY_DELAY", "2"))


def get_connection():
    """Return a fresh psycopg2 connection, retrying while Postgres starts up."""
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return psycopg2.connect(
                host=os.environ["DB_HOST"],
                port=os.environ.get("DB_PORT", "5432"),
                dbname=os.environ["DB_NAME"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
            )
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    raise ConnectionError(
        f"Could not connect to the database after {MAX_RETRIES} attempts"
    ) from last_error
