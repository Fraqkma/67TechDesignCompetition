"""Flask entry point and API routes for the SkillGraph prototype.

The skill graph and learner progress live in the connected PostgreSQL database
(see ``database_schema_description.txt``).  ``backend.db_store`` maps the
relational rows into the structure :class:`GraphEngine` expects, so the graph
engine stays the single source of truth for prerequisites.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments
    def load_dotenv(*_args, **_kwargs):
        return False
import bcrypt
import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session

from backend import (
    AIAnalyzer,
    AIService,
    GraphEngine,
    GraphValidationError,
    PlanService,
    TeachingAssistant,
    db_store,
)
from backend.study_buddy_routes import create_study_buddy_blueprint


# =========================================================
# Environment
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


# =========================================================
# PostgreSQL Configuration
# =========================================================

# Strictly follow .env — never fall back to hardcoded values, otherwise a
# missing key silently connects to the wrong database and the page hangs on
# the loading screen. SERVER_IP / POSTGRES_* are the primary keys used by
# this project; DB_HOST / DB_* are kept as legacy aliases.
DB_CONFIG = {
    "host": os.getenv("SERVER_IP") or os.getenv("DB_HOST"),
    "port": os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT"),
    "database": os.getenv("POSTGRES_DB_NAME") or os.getenv("DB_NAME"),
    "user": os.getenv("POSTGRES_USER") or os.getenv("DB_USER"),
    "password": os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD"),
}

_missing_db_keys = [
    key for key, value in DB_CONFIG.items() if value is None
]
if _missing_db_keys:
    raise RuntimeError(
        "Database is not configured. Add these keys to .env: "
        + ", ".join(_missing_db_keys)
    )


def get_db():
    """Create a PostgreSQL connection.

    ``connect_timeout`` keeps an unreachable host (for example a database on
    another network, which is the usual cause of the page hanging on the
    loading screen) from blocking requests for minutes: the connection now
    fails after a few seconds and returns a readable error.
    """
    return psycopg2.connect(connect_timeout=5, **DB_CONFIG)


# =========================================================
# Create Flask App
# =========================================================

def create_app(database_path: str | None = None) -> Flask:
    """Create the Flask application.

    ``database_path`` is accepted for backwards compatibility with the JSON
    prototype but is no longer used: the graph is loaded from PostgreSQL.
    """

    app = Flask(__name__)

    app.config["JSON_SORT_KEYS"] = False

    # Flask session
    app.secret_key = os.getenv(
        "FLASK_SECRET_KEY",
        "dev-secret-change-this",
    )

    # =====================================================
    # Response Helpers
    # =====================================================

    def success(
        data: Any = None,
        message: str | None = None,
        status: int = 200,
    ):
        payload: dict[str, Any] = {
            "ok": True
        }

        if message is not None:
            payload["message"] = message

        if data is not None:
            payload["data"] = data

        return jsonify(payload), status

    def error(
        message: str,
        status: int = 400,
        details: Any = None,
    ):
        payload: dict[str, Any] = {
            "ok": False,
            "error": message,
        }

        if details is not None:
            payload["details"] = details

        return jsonify(payload), status

    # =====================================================
    # Graph / DB Helpers
    # =====================================================

    def load_engine(
        career_id: int | None = None,
    ) -> tuple[dict[str, Any], GraphEngine, set[str]]:
        """Load one career's graph from PostgreSQL."""
        conn = get_db()
        try:
            # Ensure tables/columns exist (idempotent) so the graph loader
            # always sees the current schema, even on a fresh database.
            db_store.ensure_schema(conn)
            database = db_store.load_database(conn, career_id)
            engine = GraphEngine(database)
            return database, engine, set()
        finally:
            conn.close()

    def attach_user_context(
        conn,
        user_id: int,
        completed: set[str],
        roadmap_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Add DB-driven user context (achievements + rank) to a roadmap."""
        roadmap_payload["achievements"] = (
            db_store.build_achievements_payload(conn, user_id, completed)
        )
        roadmap_payload["rank"] = db_store.load_rank(
            conn, roadmap_payload["progress"]["career"]
        )
        return roadmap_payload

    def logged_in_user_id() -> int | None:
        """Return the authenticated user id without trusting request data."""
        user_id = session.get("user_id")
        if user_id is None:
            return None
        try:
            normalized_user_id = int(user_id)
            session["user_id"] = normalized_user_id
            return normalized_user_id
        except (TypeError, ValueError):
            return None

    def resolve_career_id(
        career_param: str | None,
        user_id: int | None,
    ) -> int:
        """Resolve which career's graph a route should load.

        Prefer an explicit ``?career=`` id, then the user's saved career,
        then the first career in the database.
        """
        conn = get_db()
        try:
            if career_param is not None:
                try:
                    career_id = int(career_param)
                except (TypeError, ValueError):
                    raise KeyError(f"Unknown career: {career_param}")
                if not db_store.career_exists(conn, career_id):
                    raise KeyError(f"Career not found: {career_param}")
                return career_id
            career_id = (
                db_store.user_career_id(conn, user_id)
                if user_id is not None
                else None
            )
            if career_id is None:
                career_id = db_store.first_career_id(conn)
            if career_id is None:
                raise GraphValidationError("No careers are configured")
            return career_id
        finally:
            conn.close()

    def load_completed_for_user(user_id: int, engine: GraphEngine) -> set[str]:
        """Read one learner's completed nodes from PostgreSQL."""
        conn = get_db()
        try:
            completed = db_store.load_completed_node_ids(conn, user_id)
            conn.commit()
            return engine.clean_completed(completed)
        finally:
            conn.close()

    def save_progress_for_user(
        user_id: int,
        skill_id: str,
        completed_value: bool,
        career_id: int | None = None,
    ):
        """Validate a graph transition, then persist only that user's state."""
        _, engine, _ = load_engine(career_id)
        if skill_id not in engine.skill_by_id:
            raise KeyError(skill_id)
        conn = get_db()
        try:
            current = engine.clean_completed(
                db_store.load_completed_node_ids(conn, user_id)
            )
            removed_ids: list[str] = []
            if completed_value:
                if engine.calculate_statuses(current)[skill_id] == "locked":
                    missing = engine.missing_prerequisites(skill_id, current)
                    raise PermissionError(
                        "Complete prerequisite skills first: "
                        + ", ".join(
                            engine.skill_by_id[item]["name"] for item in missing
                        )
                    )
                newly_completed = skill_id not in current
                db_store.save_completed(conn, user_id, int(skill_id), True)
                # Award the node's EXP reward only the first time it is
                # completed so the Code Novice achievement can unlock.
                if newly_completed:
                    db_store.add_exp(
                        conn,
                        user_id,
                        int(engine.skill_by_id[skill_id].get("expReward", 100)),
                    )
                current.add(skill_id)
            else:
                current, removed_ids = engine.remove_skill_and_invalid_dependents(
                    skill_id, current
                )
                # removed_ids already includes skill_id itself.
                node_ids = {int(item) for item in removed_ids}
                db_store.delete_completed_many(conn, user_id, sorted(node_ids))
                # Un-completing refunds the EXP of every affected skill so
                # toggling cannot farm points.
                exp_to_remove = sum(
                    int(engine.skill_by_id[item].get("expReward", 100))
                    for item in removed_ids
                )
                if exp_to_remove:
                    db_store.add_exp(conn, user_id, -exp_to_remove)
            roadmap_payload = engine.build_roadmap_payload(current)
            attach_user_context(conn, user_id, current, roadmap_payload)
            refresh_user_profile_portrait(user_id, conn)
            conn.commit()
            return {
                "roadmap": roadmap_payload,
                "removedSkillIds": removed_ids,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def refresh_user_profile_portrait(user_id: int, conn=None) -> bool:
        """Refresh the stored profile portrait whenever profile answers or achievements change."""
        owns_conn = conn is None
        conn = conn or get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT favorite_animal, favorite_color, favorite_season
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                profile = cur.fetchone()
                if profile is None or any(value is None for value in profile):
                    return False

                animal, color, season = profile
                cur.execute(
                    "SELECT a.title FROM user_achievements ua JOIN achievements a ON a.id = ua.achievement_id WHERE ua.user_id = %s ORDER BY ua.unlocked_at",
                    (user_id,),
                )
                achievements = [row[0] for row in cur.fetchall()]

                prompt = AIService.build_profile_prompt(
                    {
                        "favoriteAnimal": animal,
                        "favoriteColor": color,
                        "favoriteSeason": season,
                    },
                    achievements,
                )
                image_bytes = AIService.generate_profile_image(
                    {
                        "favoriteAnimal": animal,
                        "favoriteColor": color,
                        "favoriteSeason": season,
                    },
                    achievements,
                )
                cur.execute(
                    "UPDATE user_profiles SET profile_prompt = %s, profile_picture = %s, updated_at = NOW() WHERE user_id = %s",
                    (prompt, image_bytes, user_id),
                )
            return True
        finally:
            if owns_conn and conn is not None:
                conn.close()

    def validate_career_param(career_param: str | None) -> int | None:
        """Return a validated career id from the query string, if present."""
        if career_param is None:
            return None
        try:
            career_id = int(career_param)
        except (TypeError, ValueError):
            raise KeyError(f"Unknown career: {career_param}")
        conn = get_db()
        try:
            if not db_store.career_exists(conn, career_id):
                raise KeyError(f"Career not found: {career_param}")
        finally:
            conn.close()
        return career_id

    # =====================================================
    # Frontend Pages
    # =====================================================

    @app.get("/")
    def index():
        """Serve the landing page."""
        return render_template("index.html")

    @app.get("/login")
    def login_page():
        """Serve the login page."""
        return render_template("login.html")

    @app.get("/register")
    def register_page():
        """Serve the registration page."""
        if logged_in_user_id() is not None:
            return redirect("/roadmap")
        return render_template("register.html")

    @app.get("/roadmap")
    def roadmap_page():
        """Serve the interactive Skill Map frontend."""
        if logged_in_user_id() is None:
            return redirect("/login")
        return render_template("roadmap.html")

    @app.get("/select-track")
    def select_track_page():
        """Serve the career-track selection screen."""
        if logged_in_user_id() is None:
            return redirect("/login")
        return render_template("select-track.html")

    @app.get("/profile")
    def profile_page():
        """Serve the signed-in learner profile page."""
        if logged_in_user_id() is None:
            return redirect("/login")
        return render_template("profile.html")

    @app.get("/onboarding")
    def onboarding_page():
        """Serve a first-login onboarding form."""
        user_id = logged_in_user_id()
        if user_id is None:
            return redirect("/login")
        conn = get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT favorite_animal, favorite_color, favorite_season FROM user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                profile = cur.fetchone()
            if profile and all(value is not None for value in profile):
                return redirect("/profile")
            return render_template("onboarding.html")
        finally:
            conn.close()

    # =====================================================
    # Authentication
    # =====================================================

    @app.post("/api/register")
    def register():
        """Create an account, profile, and authenticated browser session."""
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        email = body.get("email")
        password = body.get("password")
        if not isinstance(email, str) or not re.fullmatch(
            r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()
        ):
            return error("Enter a valid email address")
        if not isinstance(password, str) or len(password) < 8:
            return error("Password must contain at least 8 characters")

        normalized_email = email.strip().lower()
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        conn = None
        try:
            conn = get_db()
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (uid, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, uid, email
                    """,
                    (uuid4().hex[:12], normalized_email, password_hash),
                )
                user_id, uid, user_email = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id, user_email.split("@", 1)[0]),
                )
            conn.commit()
            session.clear()
            session["user_id"] = int(user_id)
            session["uid"] = uid
            session["email"] = user_email
            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": user_email,
                    "redirect": "/onboarding",
                },
                "Account created",
                201,
            )
        except psycopg2.IntegrityError:
            if conn is not None:
                conn.rollback()
            return error("This email is already registered", 409)
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.post("/api/login")
    def login():
        """Login using PostgreSQL users table."""

        body = request.get_json(silent=True)

        if not isinstance(body, dict):
            return error(
                "Request body must be JSON"
            )

        email = body.get("email")
        password = body.get("password")

        if not isinstance(email, str) or not email.strip():
            return error(
                "Email must be a non-empty string"
            )

        if not isinstance(password, str) or not password:
            return error(
                "Password must be a non-empty string"
            )

        conn = None
        cur = None

        try:
            conn = get_db()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    id,
                    email,
                    password_hash,
                    uid
                FROM users
                WHERE email = %s
                """,
                (email.strip(),),
            )

            user = cur.fetchone()

            if user is None:
                return error(
                    "Email หรือ Password ไม่ถูกต้อง",
                    401,
                )

            user_id = user[0]
            user_email = user[1]
            password_hash = user[2]
            uid = user[3]

            # Check password using bcrypt
            password_correct = bcrypt.checkpw(
                password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )

            if not password_correct:
                return error(
                    "Email หรือ Password ไม่ถูกต้อง",
                    401,
                )

            # Save login session
            session["user_id"] = int(user_id)
            session["uid"] = uid
            session["email"] = user_email

            conn = get_db()
            try:
                db_store.ensure_schema(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT favorite_animal, favorite_color, favorite_season FROM user_profiles WHERE user_id = %s",
                        (user_id,),
                    )
                    profile = cur.fetchone()
                if not profile or any(value is None for value in profile):
                    redirect_path = "/onboarding"
                else:
                    redirect_path = "/roadmap"
            finally:
                conn.close()

            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": user_email,
                    "redirect": redirect_path,
                },
                "Login สำเร็จ",
            )

        except psycopg2.Error as exc:
            return error(
                "Database connection failed",
                500,
                str(exc),
            )

        finally:
            if cur is not None:
                cur.close()

            if conn is not None:
                conn.close()

    # =====================================================
    # Current User
    # =====================================================

    @app.get("/api/me")
    def current_user():
        """Return currently logged-in user and profile."""

        user_id = session.get("user_id")
        if user_id is not None:
            try:
                user_id = int(user_id)
                session["user_id"] = user_id
            except (TypeError, ValueError):
                session.clear()
                return error("ยังไม่ได้ Login", 401)

        if user_id is None:
            return error(
                "ยังไม่ได้ Login",
                401,
            )

        conn = None
        cur = None

        try:
            conn = get_db()
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    u.id,
                    u.uid,
                    u.email,
                    p.display_name,
                    p.level,
                    p.current_exp,
                    p.current_career_id,
                    p.favorite_animal,
                    p.favorite_color,
                    p.favorite_season,
                    p.profile_picture,
                    p.profile_prompt
                FROM users u
                LEFT JOIN user_profiles p
                    ON p.user_id = u.id
                WHERE u.id = %s
                """,
                (user_id,),
            )

            user = cur.fetchone()

            if user is None:
                session.clear()

                return error(
                    "User not found",
                    404,
                )

            (
                user_id,
                uid,
                email,
                display_name,
                level,
                current_exp,
                current_career_id,
                favorite_animal,
                favorite_color,
                favorite_season,
                profile_picture,
                profile_prompt,
            ) = user

            profile_image = None
            if profile_picture:
                import base64
                image_bytes = bytes(profile_picture)
                image_prefix = "data:image/png;base64,"
                if image_bytes.startswith(b"<svg"):
                    image_prefix = "data:image/svg+xml;base64,"
                profile_image = (
                    f"{image_prefix}{base64.b64encode(image_bytes).decode('ascii')}"
                )

            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": email,
                    "displayName": display_name,
                    "level": level,
                    "currentExp": current_exp,
                    "currentCareerId": current_career_id,
                    "favoriteAnimal": favorite_animal,
                    "favoriteColor": favorite_color,
                    "favoriteSeason": favorite_season,
                    "profileImage": profile_image,
                    "profilePrompt": profile_prompt,
                }
            )

        except psycopg2.Error as exc:
            return error(
                "Database connection failed",
                500,
                str(exc),
            )

        finally:
            if cur is not None:
                cur.close()

            if conn is not None:
                conn.close()

    @app.put("/api/profile")
    def update_profile():
        """Update the signed-in learner's editable profile fields."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        display_name = body.get("displayName")
        current_career_id = body.get("currentCareerId")
        favorite_animal = body.get("favoriteAnimal")
        favorite_color = body.get("favoriteColor")
        favorite_season = body.get("favoriteSeason")
        if display_name is not None and (
            not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 80
        ):
            return error("displayName must be 1 to 80 characters")
        for field_name, value in {
            "favoriteAnimal": favorite_animal,
            "favoriteColor": favorite_color,
            "favoriteSeason": favorite_season,
        }.items():
            if value is not None and (not isinstance(value, str) or not value.strip()):
                return error(f"{field_name} must be a non-empty string")

        if current_career_id is not None:
            if isinstance(current_career_id, str) and current_career_id.isdigit():
                current_career_id = int(current_career_id)
            if not isinstance(current_career_id, int) or current_career_id <= 0:
                return error("currentCareerId must be a valid career id")
            conn = get_db()
            try:
                if not db_store.career_exists(conn, current_career_id):
                    return error("Career not found", 404, current_career_id)
            finally:
                conn.close()

        if display_name is None and current_career_id is None and favorite_animal is None and favorite_color is None and favorite_season is None:
            return error("Provide displayName, currentCareerId, or onboarding answers")

        conn = None
        try:
            conn = get_db()
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                profile_answers = {
                    "favorite_animal": favorite_animal.strip() if isinstance(favorite_animal, str) else None,
                    "favorite_color": favorite_color.strip() if isinstance(favorite_color, str) else None,
                    "favorite_season": favorite_season.strip() if isinstance(favorite_season, str) else None,
                }
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name, current_career_id, favorite_animal, favorite_color, favorite_season)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, user_profiles.display_name),
                        current_career_id = COALESCE(EXCLUDED.current_career_id, user_profiles.current_career_id),
                        favorite_animal = COALESCE(EXCLUDED.favorite_animal, user_profiles.favorite_animal),
                        favorite_color = COALESCE(EXCLUDED.favorite_color, user_profiles.favorite_color),
                        favorite_season = COALESCE(EXCLUDED.favorite_season, user_profiles.favorite_season),
                        updated_at = NOW()
                    RETURNING display_name, current_career_id, favorite_animal, favorite_color, favorite_season
                    """,
                    (
                        user_id,
                        display_name.strip() if isinstance(display_name, str) else None,
                        current_career_id,
                        profile_answers["favorite_animal"],
                        profile_answers["favorite_color"],
                        profile_answers["favorite_season"],
                    ),
                )
                name, career_id, animal, color, season = cur.fetchone()

                achievement_names = []
                cur.execute(
                    "SELECT a.title FROM user_achievements ua JOIN achievements a ON a.id = ua.achievement_id WHERE ua.user_id = %s ORDER BY ua.unlocked_at",
                    (user_id,),
                )
                for row in cur.fetchall():
                    achievement_names.append(row[0])

                profile_payload = {
                    "favoriteAnimal": animal,
                    "favoriteColor": color,
                    "favoriteSeason": season,
                }
                prompt = AIService.build_profile_prompt(profile_payload, achievement_names)
                image_bytes = AIService.generate_profile_image(profile_payload, achievement_names)
                cur.execute(
                    "UPDATE user_profiles SET profile_prompt = %s, profile_picture = %s, updated_at = NOW() WHERE user_id = %s",
                    (prompt, image_bytes, user_id),
                )
            conn.commit()
            return success({"displayName": name, "currentCareerId": career_id, "favoriteAnimal": animal, "favoriteColor": color, "favoriteSeason": season}, "Profile updated")
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    @app.get("/api/profile/onboarding")
    def onboarding_status():
        """Return whether the current user still needs the first-login onboarding form."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT favorite_animal, favorite_color, favorite_season, profile_picture IS NOT NULL FROM user_profiles WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            if row is None:
                return success({"required": True})
            return success({"required": row[0] is None or row[1] is None or row[2] is None or row[3] is False})
        finally:
            conn.close()

    @app.post("/api/profile/onboarding")
    def onboarding_submit():
        """Persist first-login personality answers and generate the profile portrait."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")
        answers = {
            "favoriteAnimal": body.get("favoriteAnimal"),
            "favoriteColor": body.get("favoriteColor"),
            "favoriteSeason": body.get("favoriteSeason"),
        }
        for key, value in answers.items():
            if not isinstance(value, str) or not value.strip():
                return error(f"{key} must be a non-empty string")
        conn = get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT a.title FROM user_achievements ua JOIN achievements a ON a.id = ua.achievement_id WHERE ua.user_id = %s ORDER BY ua.unlocked_at",
                    (user_id,),
                )
                achievements = [row[0] for row in cur.fetchall()]
            prompt = AIService.build_profile_prompt(answers, achievements)
            image_bytes = AIService.generate_profile_image(answers, achievements)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name, favorite_animal, favorite_color, favorite_season, profile_prompt, profile_picture)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        favorite_animal = EXCLUDED.favorite_animal,
                        favorite_color = EXCLUDED.favorite_color,
                        favorite_season = EXCLUDED.favorite_season,
                        profile_prompt = EXCLUDED.profile_prompt,
                        profile_picture = EXCLUDED.profile_picture,
                        updated_at = NOW()
                    RETURNING favorite_animal, favorite_color, favorite_season
                    """,
                    (
                        user_id,
                        (db_store.user_display_name(conn, user_id) or "Learner"),
                        answers["favoriteAnimal"].strip(),
                        answers["favoriteColor"].strip(),
                        answers["favoriteSeason"].strip(),
                        prompt,
                        image_bytes,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return success({"favoriteAnimal": row[0], "favoriteColor": row[1], "favoriteSeason": row[2], "profilePrompt": prompt}, "Onboarding completed")
        except psycopg2.Error as exc:
            conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    @app.post("/api/profile/refresh")
    def refresh_profile_portrait():
        """Refresh the stored portrait using the current onboarding answers and achievements."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = get_db()
        try:
            db_store.ensure_schema(conn)
            refreshed = refresh_user_profile_portrait(user_id, conn)
            conn.commit()
            if not refreshed:
                return error("Profile onboarding answers are not set yet", 400)
            return success({"refreshed": True}, "Profile portrait refreshed")
        except psycopg2.Error as exc:
            conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    # =====================================================
    # Logout
    # =====================================================

    @app.post("/api/logout")
    def logout():
        """Logout current user."""

        session.clear()

        return success(
            message="Logout สำเร็จ"
        )

    # =====================================================
    # Careers (select-track page)
    # =====================================================

    @app.get("/api/careers")
    def careers():
        """Return every career tracked in the database."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = get_db()
        try:
            db_store.ensure_schema(conn)
            return success(db_store.list_careers(conn), "Careers loaded")
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    # =====================================================
    # Health
    # =====================================================

    @app.get("/api/health")
    def health():
        """Verify that Flask and graph data work."""

        try:
            _, engine, _ = load_engine()

            return success(
                {
                    "service": "SkillGraph API",
                    "graphValid": True,
                    "skillCount": len(engine.skills),
                }
            )

        except (
            KeyError,
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Graph data is invalid",
                500,
                str(exc),
            )

    # =====================================================
    # Roadmap
    # =====================================================

    @app.get("/api/roadmap")
    def roadmap():
        """Return all nodes, statuses, progress and recommendation."""

        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        preferred_subject = request.args.get(
            "subject",
            "all",
        )

        try:
            career_id = resolve_career_id(request.args.get("career"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = load_completed_for_user(user_id, engine)

            valid_subjects = {
                "all",
                *(
                    subject["id"]
                    for subject in engine.subjects
                ),
            }

            if preferred_subject not in valid_subjects:
                return error(
                    "Unknown subject",
                    400,
                    preferred_subject,
                )

            roadmap_payload = engine.build_roadmap_payload(
                completed,
                preferred_subject,
            )
            conn = get_db()
            try:
                attach_user_context(conn, user_id, completed, roadmap_payload)
                conn.commit()
            finally:
                conn.close()
            return success(roadmap_payload)

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except psycopg2.Error as exc:
            return error(
                "Database connection failed",
                500,
                str(exc),
            )
        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not build roadmap",
                500,
                str(exc),
            )

    # =====================================================
    # Skill Detail
    # =====================================================

    @app.get("/api/skills/<skill_id>")
    def skill_detail(skill_id: str):
        """Return one fully analyzed skill node."""

        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        try:
            career_id = resolve_career_id(request.args.get("career"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = load_completed_for_user(user_id, engine)

            roadmap_data = engine.build_roadmap_payload(
                completed
            )

            skill = next(
                (
                    node
                    for node in roadmap_data["nodes"]
                    if node["id"] == skill_id
                ),
                None,
            )

            if skill is None:
                return error(
                    "Skill not found",
                    404,
                    skill_id,
                )

            return success(skill)

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except psycopg2.Error as exc:
            return error(
                "Database connection failed",
                500,
                str(exc),
            )
        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not load skill",
                500,
                str(exc),
            )

    # =====================================================
    # Learning Path
    # =====================================================

    @app.get("/api/path/<skill_id>")
    def learning_path(skill_id: str):
        """Build remaining prerequisite path."""

        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        try:
            career_id = resolve_career_id(request.args.get("career"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = load_completed_for_user(user_id, engine)

            if skill_id not in engine.skill_by_id:
                return error(
                    "Skill not found",
                    404,
                    skill_id,
                )

            path = engine.build_learning_path(
                skill_id,
                completed,
            )

            return success(
                {
                    "targetSkillId": skill_id,
                    "targetName": engine.skill_by_id[
                        skill_id
                    ]["name"],
                    "steps": path,
                    "remainingCount": len(path),
                }
            )

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except psycopg2.Error as exc:
            return error(
                "Database connection failed",
                500,
                str(exc),
            )
        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not build learning path",
                500,
                str(exc),
            )

    # =====================================================
    # Goal-to-Plan
    # =====================================================

    @app.post("/api/plan/preview")
    def plan_preview():
        """Schedule a graph-defined path using the learner's weekly capacity."""
        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        target_skill_id = body.get("targetSkillId")
        weekly_hours = body.get("weeklyHours")
        start_date_value = body.get("startDate")
        if not isinstance(target_skill_id, str) or not target_skill_id:
            return error("targetSkillId must be a non-empty string")
        if isinstance(weekly_hours, bool) or not isinstance(weekly_hours, int):
            return error("weeklyHours must be an integer")
        if start_date_value is None:
            plan_start_date = date.today()
        elif isinstance(start_date_value, str):
            try:
                plan_start_date = date.fromisoformat(start_date_value)
            except ValueError:
                return error("startDate must use YYYY-MM-DD")
        else:
            return error("startDate must use YYYY-MM-DD")

        try:
            _, engine, _ = load_engine()
            completed = load_completed_for_user(user_id, engine)
            return success(
                PlanService.build_preview(
                    engine,
                    completed,
                    target_skill_id,
                    weekly_hours,
                    plan_start_date,
                ),
                "Learning plan generated",
            )
        except KeyError:
            return error("Skill not found", 404, target_skill_id)
        except ValueError as exc:
            return error(str(exc))
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except GraphValidationError as exc:
            return error("Could not build learning plan", 500, str(exc))

    # =====================================================
    # Progress
    # =====================================================

    @app.post("/api/progress")
    def update_progress():
        """Complete or uncomplete a skill."""

        body = request.get_json(silent=True)

        if not isinstance(body, dict):
            return error(
                "Request body must be JSON"
            )

        skill_id = body.get("skillId")
        completed_value = body.get("completed")
        career_param = body.get("careerId")

        if not isinstance(skill_id, str) or not skill_id:
            return error(
                "skillId must be a non-empty string"
            )

        if not isinstance(completed_value, bool):
            return error(
                "completed must be true or false"
            )

        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        try:
            career_id = (
                validate_career_param(str(career_param))
                if career_param is not None
                else None
            )
            result = save_progress_for_user(
                user_id,
                skill_id,
                completed_value,
                career_id=career_id,
            )
            message = "Skill progress updated" if completed_value else "Skill progress removed"
            return success(result, message)
        except KeyError as exc:
            return error(str(exc), 404)
        except PermissionError as exc:
            return error(str(exc), 409)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not update progress", 500, str(exc))

    # =====================================================
    # Reset Progress
    # =====================================================

    @app.post("/api/reset")
    def reset_progress():
        """Clear user progress."""

        user_id = logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = None
        try:
            body = request.get_json(silent=True) or {}
            career_param = body.get("careerId") or request.args.get("career")
            career_id = resolve_career_id(
                str(career_param) if career_param is not None else None,
                user_id,
            )
            _, engine, _ = load_engine(career_id)
            conn = get_db()
            db_store.ensure_schema(conn)
            db_store.reset_progress(conn, user_id)
            # Achievements derive from progress, so clear unlocked records
            # too and let them re-evaluate from the reset state.
            db_store.clear_user_achievements(conn, user_id)
            roadmap_payload = engine.build_roadmap_payload(set())
            attach_user_context(conn, user_id, set(), roadmap_payload)
            conn.commit()
            return success(roadmap_payload, "Progress reset")
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not reset progress", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

    # =====================================================
    # AI Recommendation
    # =====================================================

    @app.post("/api/ai/recommendation")
    def ai_recommendation():
        """Create graph-aware recommendation."""

        body = request.get_json(
            silent=True
        ) or {}

        subject = body.get(
            "subject",
            "all",
        )

        api_key = (
            body.get("apiKey")
            or AIService.resolve_api_key()
        ).strip()

        try:
            career_id = resolve_career_id(
                body.get("careerId"), logged_in_user_id()
            )
            _, engine, _ = load_engine(career_id)
            user_id = logged_in_user_id()
            completed = (
                load_completed_for_user(user_id, engine)
                if user_id is not None
                else set()
            )

            valid_subjects = {
                "all",
                *(
                    subject_id["id"]
                    for subject_id in engine.subjects
                ),
            }

            if subject not in valid_subjects:
                return error(
                    "Unknown subject",
                    400,
                    subject,
                )

            payload = (
                AIService
                .build_recommendation_payload(
                    engine,
                    completed,
                    subject,
                )
            )

            payload["aiEnabled"] = bool(api_key)

            if api_key:

                try:

                    payload["aiExplanation"] = (
                        AIService.ask_chat(
                            (
                                "อธิบายเหตุผลที่ควรเรียน "
                                "Skill นี้ต่อจากสถานะปัจจุบัน "
                                "ของผู้เรียน และอธิบายว่า "
                                "มันจะช่วยปลดล็อกอะไรบ้าง"
                            ),
                            engine,
                            completed,
                            api_key,
                        )
                    )

                except RuntimeError as exc:

                    payload["aiExplanation"] = (
                        payload["fallbackExplanation"]
                    )

                    payload["aiWarning"] = str(exc)

            else:

                payload["aiExplanation"] = (
                    payload["fallbackExplanation"]
                )

                payload["aiWarning"] = (
                    "AI API key ยังไม่ถูกตั้งค่า "
                    "ระบบใช้งาน graph-only explanation แทน"
                )

            return success(
                payload,
                "AI recommendation generated",
            )

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not build AI recommendation",
                500,
                str(exc),
            )

    # =====================================================
    # AI Analyze
    # =====================================================

    @app.post("/api/ai/analyze")
    def ai_analyze():
        """Return graph-grounded analysis."""

        body = request.get_json(
            silent=True
        ) or {}

        subject = body.get(
            "subject",
            "all",
        )

        target_skill_id = body.get(
            "targetSkillId"
        )

        if not isinstance(subject, str):
            return error(
                "subject must be a string"
            )

        if target_skill_id is not None and (
            not isinstance(
                target_skill_id,
                str,
            )
            or not target_skill_id
        ):
            return error(
                "targetSkillId must be a non-empty string when provided"
            )

        try:
            user_id = logged_in_user_id()
            career_id = resolve_career_id(body.get("careerId"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = (
                load_completed_for_user(user_id, engine)
                if user_id is not None
                else set()
            )

            valid_subjects = {
                "all",
                *(
                    item["id"]
                    for item in engine.subjects
                ),
            }

            if subject not in valid_subjects:
                return error(
                    "Unknown subject",
                    400,
                    subject,
                )

            if (
                target_skill_id is not None
                and target_skill_id
                not in engine.skill_by_id
            ):
                return error(
                    "Target skill not found",
                    404,
                    target_skill_id,
                )

            analysis = AIAnalyzer.analyze(
                engine,
                completed,
                preferred_subject=subject,
                target_skill_id=target_skill_id,
            )

            return success(
                analysis,
                "AI analysis generated",
            )

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not analyze learning progress",
                500,
                str(exc),
            )

    # =====================================================
    # AI Chat
    # =====================================================

    @app.post("/api/ai/chat")
    def ai_chat():
        """Question-answer endpoint for AI assistant."""

        body = request.get_json(
            silent=True
        ) or {}

        message = body.get("message")

        history = body.get(
            "history",
            [],
        )

        target_skill_id = body.get(
            "targetSkillId"
        )

        api_key = (
            body.get("apiKey")
            or AIService.resolve_api_key()
        ).strip()

        if (
            not isinstance(
                message,
                str,
            )
            or not message.strip()
        ):
            return error(
                "Message must be a non-empty string"
            )

        if not isinstance(history, list):
            return error(
                "history must be a list"
            )

        if target_skill_id is not None and (
            not isinstance(
                target_skill_id,
                str,
            )
            or not target_skill_id
        ):
            return error(
                "targetSkillId must be a non-empty string when provided"
            )

        if not api_key:
            return error(
                "AI API key is required. "
                "Add it in the page or set "
                "AI_API_KEY in the environment.",
                400,
            )

        try:
            user_id = logged_in_user_id()
            career_id = resolve_career_id(body.get("careerId"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = (
                load_completed_for_user(user_id, engine)
                if user_id is not None
                else set()
            )
            if (
                target_skill_id is not None
                and target_skill_id
                not in engine.skill_by_id
            ):
                return error(
                    "Target skill not found",
                    404,
                    target_skill_id,
                )

            analysis = AIAnalyzer.analyze(
                engine,
                completed,
                target_skill_id=target_skill_id,
            )

            focus = None
            if target_skill_id is not None:
                focus = {
                    "focusedSkill": AIAnalyzer.focus_context(
                        engine,
                        completed,
                        target_skill_id,
                    ),
                    "reason": analysis["reason"],
                    "pathToSkill": [
                        {
                            "id": step["id"],
                            "name": step["name"],
                        }
                        for step in analysis["recommendedPath"]
                    ],
                }

            answer = AIService.ask_chat(
                message,
                engine,
                completed,
                api_key,
                history=history,
                focus=focus,
            )

            return success(
                {
                    "answer": answer,
                    "recommendedSkill": analysis["nextSkill"],
                    "reason": analysis["reason"],
                    "focusedSkill": focus["focusedSkill"] if focus else None,
                },
                "AI response generated",
            )

        except ValueError as exc:

            return error(
                str(exc),
                400,
            )

        except RuntimeError as exc:

            return error(
                "AI request failed",
                502,
                str(exc),
            )

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except (
            GraphValidationError,
        ) as exc:

            return error(
                "Could not answer the chat question",
                500,
                str(exc),
            )

    # =====================================================
    # Teaching Assistant
    # =====================================================

    @app.post("/api/chat")
    def teaching_chat():
        """Teach the Analyzer-selected skill."""

        body = request.get_json(
            silent=True
        )

        if not isinstance(body, dict):
            return error(
                "Request body must be JSON"
            )

        message = body.get("message")

        history = body.get(
            "history",
            [],
        )

        if (
            not isinstance(
                message,
                str,
            )
            or not message.strip()
        ):
            return error(
                "message must be a non-empty string"
            )

        try:
            user_id = logged_in_user_id()
            career_id = resolve_career_id(body.get("careerId"), user_id)
            _, engine, _ = load_engine(career_id)
            completed = (
                load_completed_for_user(user_id, engine)
                if user_id is not None
                else set()
            )

            analysis = AIAnalyzer.analyze(
                engine,
                completed,
            )

            answer = TeachingAssistant.answer(
                message,
                analysis,
                history,
            )

            return success(
                {
                    "answer": answer,
                    "recommendedSkill": analysis[
                        "nextSkill"
                    ],
                    "reason": analysis[
                        "reason"
                    ],
                },
                "Teaching response generated",
            )

        except ValueError as exc:

            return error(
                str(exc),
                400,
            )

        except RuntimeError as exc:

            return error(
                "AI teaching request failed",
                502,
                str(exc),
            )

        except KeyError as exc:
            return error(
                str(exc),
                404,
            )
        except (
            GraphValidationError,
        ) as exc:

            return error(
                "Could not prepare teaching context",
                500,
                str(exc),
            )

    # =====================================================
    # Return App
    # =====================================================

    app.register_blueprint(
        create_study_buddy_blueprint(get_db)
    )

    return app


# =========================================================
# Run
# =========================================================

app = create_app()


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        # Keep one server process so its database network permission is retained.
        use_reloader=False,
    )
