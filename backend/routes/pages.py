"""Server-rendered page routes and public achievement artwork."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import redirect, render_template, send_from_directory

from backend import db_store
from backend.routes.responses import error


def register_page_routes(app: Any, services: Any) -> None:
    """Register browser page endpoints on ``app``."""

    @app.get("/pignopic/<path:filename>")
    def achievement_image(filename: str):
        allowed = {"join.png", "noob.png", "pro.png", "hacker.png", "god.png"}
        if filename not in allowed:
            return error("Achievement image not found", 404)
        return send_from_directory(Path(app.root_path) / "pignopic", filename)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.get("/register")
    def register_page():
        if services.logged_in_user_id() is not None:
            return redirect("/roadmap")
        return render_template("register.html")

    @app.get("/roadmap")
    def roadmap_page():
        if services.logged_in_user_id() is None:
            return redirect("/login")
        return render_template("roadmap.html")

    @app.get("/select-track")
    def select_track_page():
        if services.logged_in_user_id() is None:
            return redirect("/login")
        return render_template("select-track.html")

    @app.get("/profile")
    def profile_page():
        if services.logged_in_user_id() is None:
            return redirect("/login")
        return render_template("profile.html")

    @app.get("/onboarding")
    def onboarding_page():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return redirect("/login")

        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT favorite_animal, favorite_color, gender
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                profile = cur.fetchone()
            if profile and all(value is not None for value in profile):
                return redirect("/profile")
            return render_template("onboarding.html")
        finally:
            conn.close()
