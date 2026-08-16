"""Shared application operations used by multiple route modules.

Routes should translate HTTP input/output. This class owns the cross-cutting
graph, progress, achievement, and profile operations that used to be nested in
``create_app``. The graph engine remains the sole authority for prerequisite
validation and learning-path decisions.
"""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Callable
from typing import Any

from flask import session

from backend import db_store
from backend.graph_engine import GraphEngine, GraphValidationError


class ApplicationServices:
    """Coordinate database access with graph-grounded domain services."""

    ENGINE_CACHE_TTL_SECONDS = 30

    def __init__(self, get_db: Callable[[], Any], ai_service: Any) -> None:
        self.get_db = get_db
        self.ai_service = ai_service
        self._engine_cache: dict[
            int | None,
            tuple[float, tuple[dict[str, Any], GraphEngine]],
        ] = {}
        self._engine_cache_lock = threading.Lock()

    def profile_image_data_url(
        self,
        image_bytes: bytes | bytearray | memoryview | None,
    ) -> tuple[str | None, bool]:
        """Serialize image bytes and identify real AI raster portraits."""

        if not image_bytes:
            return None, False
        stored_bytes = bytes(image_bytes)
        mime_type = self.ai_service.profile_image_mime_type(stored_bytes)
        if mime_type is None:
            return None, False
        encoded = base64.b64encode(stored_bytes).decode("ascii")
        return f"data:{mime_type};base64,{encoded}", mime_type != "image/svg+xml"

    def load_engine(
        self,
        career_id: int | None = None,
        conn: Any = None,
    ) -> tuple[dict[str, Any], GraphEngine, set[str]]:
        """Load and briefly cache one career's immutable graph engine."""

        cached = self._engine_cache.get(career_id)
        if cached is not None:
            loaded_at, (database, engine) = cached
            if time.monotonic() - loaded_at < self.ENGINE_CACHE_TTL_SECONDS:
                return database, engine, set()

        owns_connection = conn is None
        conn = conn or self.get_db()
        try:
            db_store.ensure_schema(conn)
            database = db_store.load_database(conn, career_id)
            engine = GraphEngine(database)
            with self._engine_cache_lock:
                self._engine_cache[career_id] = (
                    time.monotonic(),
                    (database, engine),
                )
            return database, engine, set()
        finally:
            if owns_connection:
                conn.close()

    def attach_user_context(
        self,
        conn: Any,
        user_id: int,
        completed: set[str],
        roadmap_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Add database-backed achievements and rank to a roadmap payload."""

        career_progress = roadmap_payload["progress"]["career"]
        roadmap_payload["achievements"] = db_store.build_achievements_payload(
            conn,
            user_id,
            completed,
            career_progress,
        )
        roadmap_payload["rank"] = db_store.load_rank(conn, career_progress)
        return roadmap_payload

    def highest_career_achievement_for_user(
        self,
        conn: Any,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Return the learner's highest graph-derived tier across careers."""

        current_career_id = db_store.user_career_id(conn, user_id)
        best: dict[str, Any] | None = None
        best_key: tuple[int, int, int, int] | None = None

        for career in db_store.list_careers(conn):
            if not career["available"]:
                continue

            career_id = int(career["id"])
            engine = GraphEngine(db_store.load_database(conn, career_id))
            completed = engine.clean_completed(
                db_store.load_completed_node_ids(conn, user_id, career_id)
            )
            progress = int(engine.calculate_progress(completed)["career"])
            unlocked = [
                achievement
                for achievement in db_store.build_achievements_payload(
                    conn,
                    user_id,
                    completed,
                    progress,
                )
                if achievement["unlocked"]
            ]
            if not unlocked:
                continue

            achievement = max(unlocked, key=lambda item: int(item["target"]))
            target = int(achievement["target"])
            candidate_key = (
                target,
                progress,
                1 if career_id == current_career_id else 0,
                -career_id,
            )
            if best_key is not None and candidate_key <= best_key:
                continue

            best_key = candidate_key
            best = {
                "achievement": {
                    "id": achievement["id"],
                    "name": achievement["name"],
                    "description": achievement["description"],
                    "iconUrl": achievement["iconUrl"],
                    "target": target,
                },
                "career": {
                    "id": career_id,
                    "title": career["title"],
                    "icon": career["icon"],
                },
                "progress": progress,
            }

        return best

    @staticmethod
    def logged_in_user_id() -> int | None:
        """Return a normalized session user id without trusting request data."""

        user_id = session.get("user_id")
        if isinstance(user_id, bool):
            return None
        if isinstance(user_id, int):
            normalized = user_id
        elif isinstance(user_id, str) and user_id.isdigit():
            normalized = int(user_id)
        else:
            return None
        if normalized <= 0:
            return None
        session["user_id"] = normalized
        return normalized

    def resolve_career_id(
        self,
        career_param: str | int | None,
        user_id: int | None,
        conn: Any = None,
    ) -> int:
        """Resolve an explicit, saved, or fallback career id."""

        owns_connection = conn is None
        conn = conn or self.get_db()
        try:
            if career_param is not None:
                try:
                    career_id = int(career_param)
                except (TypeError, ValueError) as exc:
                    raise KeyError(f"Unknown career: {career_param}") from exc
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
            if owns_connection:
                conn.close()

    def load_completed_for_user(
        self,
        user_id: int,
        career_id: int,
        engine: GraphEngine,
        conn: Any = None,
    ) -> set[str]:
        """Read and graph-validate one learner's completed nodes."""

        owns_connection = conn is None
        conn = conn or self.get_db()
        try:
            completed = db_store.load_completed_node_ids(conn, user_id, career_id)
            conn.commit()
            return engine.clean_completed(completed)
        finally:
            if owns_connection:
                conn.close()

    def load_roadmap_data(
        self,
        career_param: str | int | None,
        user_id: int | None,
    ) -> tuple[Any, int, GraphEngine, set[str]]:
        """Load career, graph, and progress over one shared connection."""

        conn = self.get_db()
        try:
            db_store.ensure_schema(conn)
            career_id = self.resolve_career_id(career_param, user_id, conn)
            _, engine, _ = self.load_engine(career_id, conn)
            completed = (
                self.load_completed_for_user(user_id, career_id, engine, conn)
                if user_id is not None
                else set()
            )
            return conn, career_id, engine, completed
        except Exception:
            conn.close()
            raise

    def save_progress_for_user(
        self,
        user_id: int,
        skill_id: str,
        completed_value: bool,
        career_param: str | int | None = None,
    ) -> dict[str, Any]:
        """Validate a graph transition, then persist that learner's state."""

        conn = self.get_db()
        try:
            db_store.ensure_schema(conn)
            career_id = self.resolve_career_id(career_param, user_id, conn)
            _, engine, _ = self.load_engine(career_id, conn)
            if skill_id not in engine.skill_by_id:
                raise KeyError(skill_id)

            current = engine.clean_completed(
                db_store.load_completed_node_ids(conn, user_id, career_id)
            )
            removed_ids: list[str] = []
            if completed_value:
                if engine.calculate_statuses(current)[skill_id] == "locked":
                    missing = engine.missing_prerequisites(skill_id, current)
                    names = [engine.skill_by_id[item]["name"] for item in missing]
                    raise PermissionError(
                        "Complete prerequisite skills first: " + ", ".join(names)
                    )

                newly_completed = skill_id not in current
                db_store.save_completed(
                    conn,
                    user_id,
                    career_id,
                    int(skill_id),
                    True,
                )
                if newly_completed:
                    reward = int(
                        engine.skill_by_id[skill_id].get("expReward", 100)
                    )
                    db_store.add_exp(conn, user_id, reward)
                current.add(skill_id)
            else:
                current, removed_ids = engine.remove_skill_and_invalid_dependents(
                    skill_id,
                    current,
                )
                node_ids = sorted(int(item) for item in removed_ids)
                db_store.delete_completed_many(conn, user_id, career_id, node_ids)
                exp_to_remove = sum(
                    int(engine.skill_by_id[item].get("expReward", 100))
                    for item in removed_ids
                )
                if exp_to_remove:
                    db_store.add_exp(conn, user_id, -exp_to_remove)

            roadmap_payload = engine.build_roadmap_payload(current)
            self.attach_user_context(conn, user_id, current, roadmap_payload)
            self.refresh_user_profile_portrait(user_id, conn)
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

    def refresh_user_profile_portrait(
        self,
        user_id: int,
        conn: Any = None,
        *,
        require_generated: bool = False,
    ) -> bool:
        """Generate a portrait only when the account has no real portrait."""

        owns_connection = conn is None
        conn = conn or self.get_db()
        try:
            db_store.ensure_schema(conn)
            with conn.cursor() as cur:
                # The advisory lock prevents simultaneous provider requests for
                # the same user from generating more than one portrait.
                cur.execute("SELECT pg_advisory_xact_lock(67341, %s)", (user_id,))
                cur.execute(
                    """
                    SELECT favorite_animal, favorite_color, gender, profile_picture
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                profile = cur.fetchone()
                if profile is None or any(value is None for value in profile[:3]):
                    return False

                animal, color, gender, existing_picture = profile
                _, portrait_generated = self.profile_image_data_url(existing_picture)
                if portrait_generated:
                    return False

                cur.execute(
                    """
                    SELECT a.title
                    FROM user_achievements ua
                    JOIN achievements a ON a.id = ua.achievement_id
                    WHERE ua.user_id = %s
                    ORDER BY ua.unlocked_at
                    """,
                    (user_id,),
                )
                achievements = [row[0] for row in cur.fetchall()]

                profile_payload = {
                    "favoriteAnimal": animal,
                    "favoriteColor": color,
                    "gender": gender,
                }
                prompt = self.ai_service.build_profile_prompt(
                    profile_payload,
                    achievements,
                )
                try:
                    image_bytes = self.ai_service.generate_profile_image(
                        profile_payload,
                        achievements,
                        prompt=prompt,
                        allow_fallback=False,
                    )
                except self.ai_service.ProfileImageGenerationError:
                    if require_generated:
                        raise
                    # Progress must still save when the provider is unavailable.
                    return False

                cur.execute(
                    """
                    UPDATE user_profiles
                    SET profile_prompt = %s, profile_picture = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (prompt, image_bytes, user_id),
                )
            return True
        finally:
            if owns_connection:
                conn.close()
