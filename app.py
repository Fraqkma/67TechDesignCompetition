"""Flask entry point and API routes for the SkillGraph prototype."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import bcrypt
import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session

from backend import (
    AIAnalyzer,
    AIService,
    GraphEngine,
    GraphValidationError,
    JsonStore,
    TeachingAssistant,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "database.json"

# =========================================================
# Environment
# =========================================================

load_dotenv(BASE_DIR / ".env")


# =========================================================
# PostgreSQL Configuration
# =========================================================

DB_CONFIG = {
    "host": os.getenv("SERVER_IP") or os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB_NAME") or os.getenv("DB_NAME", "skilltree_db"),
    "user": os.getenv("POSTGRES_USER") or os.getenv("DB_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD", ""),
}


def get_db():
    """Create a PostgreSQL connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_user_tables(conn) -> None:
    """Create the small per-user tables needed by authentication and progress.

    The skill graph deliberately remains in ``data/database.json``.  Only a
    learner's completion state belongs in PostgreSQL, keyed by ``user_id``.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                uid TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                display_name TEXT,
                level INTEGER NOT NULL DEFAULT 1,
                current_exp INTEGER NOT NULL DEFAULT 0,
                current_career_id TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_skill_progress (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                skill_id TEXT NOT NULL,
                completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, skill_id)
            )
            """
        )


# =========================================================
# Create Flask App
# =========================================================

def create_app(database_path: str | Path | None = None) -> Flask:
    """Create the Flask application."""

    app = Flask(__name__)

    app.config["JSON_SORT_KEYS"] = False

    app.config["DATABASE_PATH"] = str(
        database_path or DEFAULT_DATABASE_PATH
    )

    # Flask session
    app.secret_key = os.getenv(
        "FLASK_SECRET_KEY",
        "dev-secret-change-this",
    )

    store = JsonStore(app.config["DATABASE_PATH"])

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
    # Graph / JSON Store Helpers
    # =====================================================

    def load_engine() -> tuple[
        dict[str, Any],
        GraphEngine,
        set[str],
    ]:
        database = store.read()

        engine = GraphEngine(database)

        completed = engine.clean_completed(
            database.get("progress", {})
            .get("completedSkillIds", [])
        )

        return database, engine, completed

    def logged_in_user_id() -> int | None:
        """Return the authenticated user id without trusting request data."""
        user_id = session.get("user_id")
        return user_id if isinstance(user_id, int) else None

    def load_completed_for_user(user_id: int, engine: GraphEngine) -> set[str]:
        """Read one learner's completed skills from PostgreSQL."""
        conn = get_db()
        try:
            ensure_user_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT skill_id FROM user_skill_progress WHERE user_id = %s",
                    (user_id,),
                )
                completed = {row[0] for row in cur.fetchall()}
            conn.commit()
            return engine.clean_completed(completed)
        finally:
            conn.close()

    def save_progress_for_user(user_id: int, skill_id: str, completed_value: bool):
        """Validate a graph transition, then persist only that user's state."""
        _, engine, _ = load_engine()
        if skill_id not in engine.skill_by_id:
            raise KeyError(skill_id)
        conn = get_db()
        try:
            ensure_user_tables(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT skill_id FROM user_skill_progress WHERE user_id = %s", (user_id,))
                current = engine.clean_completed({row[0] for row in cur.fetchall()})
                removed_ids: list[str] = []
                if completed_value:
                    if engine.calculate_statuses(current)[skill_id] == "locked":
                        missing = engine.missing_prerequisites(skill_id, current)
                        raise PermissionError("Complete prerequisite skills first: " + ", ".join(engine.skill_by_id[item]["name"] for item in missing))
                    cur.execute("INSERT INTO user_skill_progress (user_id, skill_id) VALUES (%s, %s) ON CONFLICT (user_id, skill_id) DO NOTHING", (user_id, skill_id))
                    current.add(skill_id)
                else:
                    current, removed_ids = engine.remove_skill_and_invalid_dependents(skill_id, current)
                    cur.execute("DELETE FROM user_skill_progress WHERE user_id = %s AND skill_id = ANY(%s)", (user_id, [skill_id, *removed_ids]))
            conn.commit()
            return {"roadmap": engine.build_roadmap_payload(current), "removedSkillIds": removed_ids}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
            ensure_user_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (uid, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, uid, email
                    """,
                    # Existing database schema stores a compact 12-character UID.
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
            session["user_id"] = user_id
            session["uid"] = uid
            session["email"] = user_email
            return success(
                {"id": user_id, "uid": uid, "email": user_email},
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
            session["user_id"] = user_id
            session["uid"] = uid
            session["email"] = user_email

            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": user_email,
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
                    p.current_career_id
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
            ) = user

            return success(
                {
                    "id": user_id,
                    "uid": uid,
                    "email": email,
                    "displayName": display_name,
                    "level": level,
                    "currentExp": current_exp,
                    "currentCareerId": current_career_id,
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
        if display_name is not None and (
            not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 80
        ):
            return error("displayName must be 1 to 80 characters")
        if current_career_id is not None and (
            not isinstance(current_career_id, str) or len(current_career_id) > 100
        ):
            return error("currentCareerId must be a string up to 100 characters")
        if display_name is None and current_career_id is None:
            return error("Provide displayName or currentCareerId")

        conn = None
        try:
            conn = get_db()
            ensure_user_tables(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name, current_career_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        display_name = COALESCE(EXCLUDED.display_name, user_profiles.display_name),
                        current_career_id = COALESCE(EXCLUDED.current_career_id, user_profiles.current_career_id),
                        updated_at = NOW()
                    RETURNING display_name, current_career_id
                    """,
                    (user_id, display_name.strip() if isinstance(display_name, str) else None, current_career_id),
                )
                name, career_id = cur.fetchone()
            conn.commit()
            return success({"displayName": name, "currentCareerId": career_id}, "Profile updated")
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        finally:
            if conn is not None:
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
            _, engine, _ = load_engine()
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

            return success(
                engine.build_roadmap_payload(
                    completed,
                    preferred_subject,
                )
            )

        except (
            KeyError,
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
            _, engine, _ = load_engine()
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

        except (
            KeyError,
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
            _, engine, _ = load_engine()
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

        except (
            KeyError,
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not build learning path",
                500,
                str(exc),
            )

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
            result = save_progress_for_user(user_id, skill_id, completed_value)
            message = "Skill progress updated" if completed_value else "Skill progress removed"
            return success(result, message)
        except KeyError:
            return error("Skill not found", 404, skill_id)
        except PermissionError as exc:
            return error(str(exc), 409)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not update progress", 500, str(exc))

        try:

            def mutate(database: dict[str, Any]):
                engine = GraphEngine(database)

                if skill_id not in engine.skill_by_id:
                    raise KeyError(skill_id)

                current = engine.clean_completed(
                    database.get("progress", {})
                    .get("completedSkillIds", [])
                )

                removed_ids: list[str] = []

                if completed_value:

                    status = engine.calculate_statuses(
                        current
                    )[skill_id]

                    if status == "locked":

                        missing = (
                            engine.missing_prerequisites(
                                skill_id,
                                current,
                            )
                        )

                        missing_names = [
                            engine.skill_by_id[item]["name"]
                            for item in missing
                        ]

                        raise PermissionError(
                            "ต้องเรียนพื้นฐานให้ครบก่อน: "
                            + ", ".join(missing_names)
                        )

                    current.add(skill_id)

                else:

                    (
                        current,
                        removed_ids,
                    ) = (
                        engine
                        .remove_skill_and_invalid_dependents(
                            skill_id,
                            current,
                        )
                    )

                database.setdefault(
                    "progress",
                    {},
                )["completedSkillIds"] = sorted(
                    current
                )

                database["progress"]["updatedAt"] = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                roadmap_data = (
                    engine.build_roadmap_payload(
                        current
                    )
                )

                return {
                    "roadmap": roadmap_data,
                    "removedSkillIds": removed_ids,
                }

            result = store.update(mutate)

            message = (
                "บันทึกว่าเรียน Skill นี้แล้ว"
                if completed_value
                else "ยกเลิก Skill และ Skill ที่พึ่งพากันแล้ว"
            )

            return success(
                result,
                message,
            )

        except KeyError:
            return error(
                "Skill not found",
                404,
                skill_id,
            )

        except PermissionError as exc:
            return error(
                str(exc),
                409,
            )

        except (
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not update progress",
                500,
                str(exc),
            )

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
            _, engine, _ = load_engine()
            conn = get_db()
            ensure_user_tables(conn)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_skill_progress WHERE user_id = %s", (user_id,))
            conn.commit()
            return success(engine.build_roadmap_payload(set()), "Progress reset")
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not reset progress", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()

        try:

            def mutate(database: dict[str, Any]):
                engine = GraphEngine(database)

                database["progress"] = {
                    "completedSkillIds": [],
                    "updatedAt": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

                return engine.build_roadmap_payload(
                    set()
                )

            roadmap_data = store.update(mutate)

            return success(
                roadmap_data,
                "รีเซ็ต Progress เรียบร้อยแล้ว",
            )

        except (
            KeyError,
            GraphValidationError,
            ValueError,
        ) as exc:
            return error(
                "Could not reset progress",
                500,
                str(exc),
            )

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
            _, engine, completed = load_engine()

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

        except (
            KeyError,
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

            _, engine, completed = load_engine()

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

        if not api_key:
            return error(
                "AI API key is required. "
                "Add it in the page or set "
                "AI_API_KEY in the environment.",
                400,
            )

        try:

            _, engine, completed = load_engine()

            answer = AIService.ask_chat(
                message,
                engine,
                completed,
                api_key,
            )

            return success(
                {
                    "answer": answer
                },
                "AI response generated",
            )

        except ValueError as exc:

            return error(
                "AI API key is required",
                400,
                str(exc),
            )

        except RuntimeError as exc:

            return error(
                "AI request failed",
                502,
                str(exc),
            )

        except (
            KeyError,
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

            _, engine, completed = load_engine()

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

        except (
            GraphValidationError,
            KeyError,
        ) as exc:

            return error(
                "Could not prepare teaching context",
                500,
                str(exc),
            )

    # =====================================================
    # Return App
    # =====================================================

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
