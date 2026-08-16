"""Application configuration loaded from environment variables.

This module only reads configuration; it never opens a database connection.
Keeping configuration side-effect free makes imports, test discovery, and CLI
tools work before a developer has configured PostgreSQL.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in minimal environments
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Local values may come from ``.env``; real environment variables still win.
load_dotenv(PROJECT_ROOT / ".env")

PROFILE_GENDER_CHOICES = frozenset(
    {"ชาย", "หญิง", "นอนไบนารี", "ไม่ต้องการระบุ"}
)

_DATABASE_ENV_ALIASES = {
    "host": ("SERVER_IP", "DB_HOST"),
    "port": ("POSTGRES_PORT", "DB_PORT"),
    "database": ("POSTGRES_DB_NAME", "DB_NAME"),
    "user": ("POSTGRES_USER", "DB_USER"),
    "password": ("POSTGRES_PASSWORD", "DB_PASSWORD"),
}


def database_config() -> dict[str, str]:
    """Return validated psycopg2 settings without exposing secret values."""

    config = {
        key: next(
            (value for name in names if (value := os.getenv(name))),
            "",
        )
        for key, names in _DATABASE_ENV_ALIASES.items()
    }
    missing = [key for key, value in config.items() if not value]
    if missing:
        expected = ["/".join(_DATABASE_ENV_ALIASES[key]) for key in missing]
        raise RuntimeError(
            "Database is not configured. Set these environment variables: "
            + ", ".join(expected)
        )
    return config


def configure_flask_app(app: Any) -> None:
    """Apply shared Flask defaults used by every application instance."""

    app.config.update(
        JSON_SORT_KEYS=False,
        # Force CSS/JS revalidation. ETag/Last-Modified still allow cheap 304s.
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )

    configured_secret = os.getenv("FLASK_SECRET_KEY", "").strip()
    if configured_secret:
        app.secret_key = configured_secret
    else:
        # A random development key is safer than a public hard-coded fallback.
        # Sessions intentionally expire when the process restarts until the
        # developer provides a stable FLASK_SECRET_KEY.
        app.secret_key = secrets.token_hex(32)
        app.logger.warning(
            "FLASK_SECRET_KEY is not set; using a temporary development key."
        )
