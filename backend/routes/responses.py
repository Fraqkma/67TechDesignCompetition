"""Shared HTTP response helpers and middleware."""

from __future__ import annotations

import gzip
from typing import Any

from flask import jsonify, request


def success(data: Any = None, message: str | None = None, status: int = 200):
    """Build the API's consistent successful JSON envelope."""

    payload: dict[str, Any] = {"ok": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def error(message: str, status: int = 400, details: Any = None):
    """Build the API's consistent error JSON envelope."""

    payload: dict[str, Any] = {"ok": False, "error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status


def register_response_compression(app: Any) -> None:
    """Compress sizeable text responses when the client accepts gzip."""

    @app.after_request
    def compress_response(response):
        if "gzip" not in request.headers.get("Accept-Encoding", ""):
            return response
        if not 200 <= response.status_code < 300 or response.direct_passthrough:
            return response

        content_type = response.content_type or ""
        compressible = (
            content_type.startswith("application/json")
            or content_type.startswith("text/")
            or content_type.startswith("application/javascript")
            or content_type.endswith("+json")
        )
        if not compressible:
            return response

        data = response.get_data()
        if len(data) < 1024:
            return response

        compressed = gzip.compress(data, compresslevel=4)
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Content-Length"] = str(len(compressed))
        # The original ETag describes the uncompressed body.
        response.headers.pop("ETag", None)
        return response
