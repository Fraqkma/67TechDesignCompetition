"""Flask entry point and API routes for the SkillGraph prototype."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from backend import GraphEngine, GraphValidationError, JsonStore


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "database.json"


def create_app(database_path: str | Path | None = None) -> Flask:
    """Create the Flask app.

    Accepting a custom database path lets tests use a temporary JSON file and
    guarantees that test runs never change the real prototype progress.
    """

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["DATABASE_PATH"] = str(database_path or DEFAULT_DATABASE_PATH)
    store = JsonStore(app.config["DATABASE_PATH"])

    def success(data: Any = None, message: str | None = None, status: int = 200):
        payload: dict[str, Any] = {"ok": True}
        if message is not None:
            payload["message"] = message
        if data is not None:
            payload["data"] = data
        return jsonify(payload), status

    def error(message: str, status: int = 400, details: Any = None):
        payload: dict[str, Any] = {"ok": False, "error": message}
        if details is not None:
            payload["details"] = details
        return jsonify(payload), status

    def load_engine() -> tuple[dict[str, Any], GraphEngine, set[str]]:
        database = store.read()
        engine = GraphEngine(database)
        completed = engine.clean_completed(
            database.get("progress", {}).get("completedSkillIds", [])
        )
        return database, engine, completed

    @app.get("/")
    def index():
        """Serve the landing page (page one)."""

        return render_template("index.html")

    @app.get("/roadmap")
    def roadmap_page():
        """Serve the interactive Skill Map frontend (page two)."""

        return render_template("roadmap.html")

    @app.get("/select-track")
    def select_track_page():
        """Serve the career-track selection screen (page 1.5)."""

        return render_template("select-track.html")

    @app.get("/api/health")
    def health():
        """Small endpoint used to verify that Flask and graph data work."""

        try:
            _, engine, _ = load_engine()
            return success(
                {
                    "service": "SkillGraph API",
                    "graphValid": True,
                    "skillCount": len(engine.skills),
                }
            )
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Graph data is invalid", 500, str(exc))

    @app.get("/api/roadmap")
    def roadmap():
        """Return all nodes, statuses, progress and one recommendation."""

        preferred_subject = request.args.get("subject", "all")

        try:
            _, engine, completed = load_engine()
            valid_subjects = {"all", *(subject["id"] for subject in engine.subjects)}
            if preferred_subject not in valid_subjects:
                return error("Unknown subject", 400, preferred_subject)

            return success(
                engine.build_roadmap_payload(completed, preferred_subject)
            )
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not build roadmap", 500, str(exc))

    @app.get("/api/skills/<skill_id>")
    def skill_detail(skill_id: str):
        """Return one fully analyzed skill node."""

        try:
            _, engine, completed = load_engine()
            roadmap_data = engine.build_roadmap_payload(completed)
            skill = next(
                (node for node in roadmap_data["nodes"] if node["id"] == skill_id),
                None,
            )
            if skill is None:
                return error("Skill not found", 404, skill_id)
            return success(skill)
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not load skill", 500, str(exc))

    @app.get("/api/path/<skill_id>")
    def learning_path(skill_id: str):
        """Build the remaining prerequisite path to a chosen target."""

        try:
            _, engine, completed = load_engine()
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
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not build learning path", 500, str(exc))

    @app.post("/api/progress")
    def update_progress():
        """Complete or uncomplete a skill and return the refreshed roadmap."""

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return error("Request body must be JSON")

        skill_id = body.get("skillId")
        completed_value = body.get("completed")

        if not isinstance(skill_id, str) or not skill_id:
            return error("skillId must be a non-empty string")
        if not isinstance(completed_value, bool):
            return error("completed must be true or false")

        try:
            def mutate(database: dict[str, Any]):
                engine = GraphEngine(database)
                if skill_id not in engine.skill_by_id:
                    raise KeyError(skill_id)

                current = engine.clean_completed(
                    database.get("progress", {}).get("completedSkillIds", [])
                )
                removed_ids: list[str] = []

                if completed_value:
                    status = engine.calculate_statuses(current)[skill_id]
                    if status == "locked":
                        missing = engine.missing_prerequisites(skill_id, current)
                        missing_names = [
                            engine.skill_by_id[item]["name"] for item in missing
                        ]
                        raise PermissionError(
                            "ต้องเรียนพื้นฐานให้ครบก่อน: "
                            + ", ".join(missing_names)
                        )
                    current.add(skill_id)
                else:
                    current, removed_ids = (
                        engine.remove_skill_and_invalid_dependents(
                            skill_id, current
                        )
                    )

                database.setdefault("progress", {})["completedSkillIds"] = sorted(
                    current
                )
                database["progress"]["updatedAt"] = datetime.now(
                    timezone.utc
                ).isoformat()

                roadmap_data = engine.build_roadmap_payload(current)
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
            return success(result, message)

        except KeyError:
            return error("Skill not found", 404, skill_id)
        except PermissionError as exc:
            return error(str(exc), 409)
        except (GraphValidationError, ValueError) as exc:
            return error("Could not update progress", 500, str(exc))

    @app.post("/api/reset")
    def reset_progress():
        """Clear only user progress; static graph data remains untouched."""

        try:
            def mutate(database: dict[str, Any]):
                engine = GraphEngine(database)
                database["progress"] = {
                    "completedSkillIds": [],
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                }
                return engine.build_roadmap_payload(set())

            roadmap_data = store.update(mutate)
            return success(roadmap_data, "รีเซ็ต Progress เรียบร้อยแล้ว")
        except (KeyError, GraphValidationError, ValueError) as exc:
            return error("Could not reset progress", 500, str(exc))

    return app


app = create_app()


if __name__ == "__main__":
    # debug=True is convenient for localhost development because Flask reloads
    # automatically when Python, HTML, CSS or JavaScript files change.
    app.run(host="127.0.0.1", port=5000, debug=True)
