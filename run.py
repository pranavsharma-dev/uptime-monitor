import os

from app import app

if __name__ == "__main__":
    # debug=True is avoided on purpose: Flask's reloader forks a second
    # process, which would start two copies of the background scheduler.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))