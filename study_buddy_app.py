"""Compatibility launcher; Study Buddy now lives in the original app."""

from app import app


if __name__ == "__main__":
    # Production launcher — matches app.py: threaded waitress server so slow
    # requests (long AI calls) don't block other users.
    from waitress import serve

    serve(app, host="127.0.0.1", port=5000, threads=8)
