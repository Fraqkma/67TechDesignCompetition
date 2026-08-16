"""Career, roadmap, path-planning, and learner-progress routes."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg2
from flask import request

from backend import db_store
from backend.graph_engine import GraphValidationError
from backend.routes.responses import error, success


def register_learning_routes(
    app: Any,
    services: Any,
    plan_service: Any,
) -> None:
    """Register graph-grounded learning endpoints on ``app``."""

    @app.get("/api/careers")
    def careers():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        conn = services.get_db()
        try:
            db_store.ensure_schema(conn)
            return success(db_store.list_careers(conn), "Careers loaded")
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        finally:
            conn.close()

    @app.get("/api/health")
    def health():
        """Verify that the database graph can be loaded and validated."""

        try:
            _, engine, _ = services.load_engine()
            return success(
                {
                    "service": "SkillGraph API",
                    "graphValid": True,
                    "skillCount": len(engine.skills),
                }
            )
        except RuntimeError as exc:
            # Most commonly raised when required DB environment values are
            # missing on a new contributor's machine.
            return error("Database is not configured", 503, str(exc))
        except psycopg2.Error as exc:
            return error("Database connection failed", 503, str(exc))
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Graph data is invalid", 500, str(exc))

    @app.get("/api/roadmap")
    def roadmap():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        preferred_subject = request.args.get("subject", "all")
        try:
            conn, _, engine, completed = services.load_roadmap_data(
                request.args.get("career"),
                user_id,
            )
            try:
                valid_subjects = {
                    "all",
                    *(subject["id"] for subject in engine.subjects),
                }
                if preferred_subject not in valid_subjects:
                    return error("Unknown subject", 400, preferred_subject)

                payload = engine.build_roadmap_payload(
                    completed,
                    preferred_subject,
                )
                services.attach_user_context(conn, user_id, completed, payload)
                conn.commit()
                return success(payload)
            finally:
                conn.close()
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not build roadmap", 500, str(exc))

    @app.get("/api/skills/<skill_id>")
    def skill_detail(skill_id: str):
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        try:
            conn, _, engine, completed = services.load_roadmap_data(
                request.args.get("career"),
                user_id,
            )
            try:
                roadmap_data = engine.build_roadmap_payload(completed)
                skill = next(
                    (
                        node
                        for node in roadmap_data["nodes"]
                        if node["id"] == skill_id
                    ),
                    None,
                )
                if skill is None:
                    return error("Skill not found", 404, skill_id)
                return success(skill)
            finally:
                conn.close()
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not load skill", 500, str(exc))

    @app.get("/api/path/<skill_id>")
    def learning_path(skill_id: str):
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        try:
            conn, _, engine, completed = services.load_roadmap_data(
                request.args.get("career"),
                user_id,
            )
            try:
                if skill_id not in engine.skill_by_id:
                    return error("Skill not found", 404, skill_id)
                path = engine.build_learning_path(skill_id, completed)
                return success(
                    {
                        "targetSkillId": skill_id,
                        "targetName": engine.skill_by_id[skill_id]["name"],
                        "steps": path,
                        "remainingCount": len(path),
                    }
                )
            finally:
                conn.close()
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not build learning path", 500, str(exc))

    @app.post("/api/plan/preview")
    def plan_preview():
        """Schedule a graph-defined path within weekly study capacity."""

        user_id = services.logged_in_user_id()
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
            conn, _, engine, completed = services.load_roadmap_data(
                body.get("careerId"),
                user_id,
            )
            try:
                preview = plan_service.build_preview(
                    engine,
                    completed,
                    target_skill_id,
                    weekly_hours,
                    plan_start_date,
                )
                return success(preview, "Learning plan generated")
            finally:
                conn.close()
        except KeyError:
            return error("Skill not found", 404, target_skill_id)
        except ValueError as exc:
            return error(str(exc))
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except GraphValidationError as exc:
            return error("Could not build learning plan", 500, str(exc))

    @app.post("/api/progress")
    def update_progress():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        skill_id = body.get("skillId")
        completed_value = body.get("completed")
        career_param = body.get("careerId")
        if not isinstance(skill_id, str) or not skill_id:
            return error("skillId must be a non-empty string")
        if not isinstance(completed_value, bool):
            return error("completed must be true or false")

        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)
        try:
            result = services.save_progress_for_user(
                user_id,
                skill_id,
                completed_value,
                career_param=career_param,
            )
            message = (
                "Skill progress updated"
                if completed_value
                else "Skill progress removed"
            )
            return success(result, message)
        except KeyError as exc:
            return error(str(exc), 404)
        except PermissionError as exc:
            return error(str(exc), 409)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not update progress", 500, str(exc))

    @app.post("/api/reset")
    def reset_progress():
        user_id = services.logged_in_user_id()
        if user_id is None:
            return error("Login is required", 401)

        conn = None
        try:
            body = request.get_json(silent=True) or {}
            career_param = body.get("careerId") or request.args.get("career")
            conn = services.get_db()
            db_store.ensure_schema(conn)
            career_id = services.resolve_career_id(
                career_param,
                user_id,
                conn,
            )
            _, engine, _ = services.load_engine(career_id, conn)
            db_store.reset_progress(conn, user_id, career_id)
            payload = engine.build_roadmap_payload(set())
            services.attach_user_context(conn, user_id, set(), payload)
            conn.commit()
            return success(payload, "Progress reset")
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            if conn is not None:
                conn.rollback()
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not reset progress", 500, str(exc))
        finally:
            if conn is not None:
                conn.close()
