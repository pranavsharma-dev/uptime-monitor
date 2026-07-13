"""Flask application entry point."""

import atexit
import os

from flask import Flask

from app.routes.monitors import monitors_bp
from app.scheduler import start_scheduler

app = Flask(__name__)
app.register_blueprint(monitors_bp)


@app.route("/health")
def health():
    return {"status": "ok"}, 200


# The test suite and some tooling import this module without wanting a real
# background scheduler (and the DB connection it requires) running.
if os.environ.get("DISABLE_SCHEDULER") != "1":
    _scheduler = start_scheduler()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
