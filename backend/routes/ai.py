"""Graph-grounded AI analysis, recommendation, and teaching routes."""

from __future__ import annotations

from typing import Any

import psycopg2
from flask import request

from backend.graph_engine import GraphValidationError
from backend.routes.responses import error, success


def _json_object() -> dict[str, Any] | None:
    """Return a JSON object, keeping route validation consistent."""

    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def register_ai_routes(
    app: Any,
    services: Any,
    ai_analyzer: Any,
    teaching_assistant: Any,
) -> None:
    """Register AI endpoints while keeping all graph decisions deterministic."""

    ai_service = services.ai_service

    @app.post("/api/ai/recommendation")
    def ai_recommendation():
        body = _json_object()
        if body is None:
            return error("Request body must be JSON")

        subject = body.get("subject", "all")
        supplied_key = body.get("apiKey")
        if supplied_key is not None and not isinstance(supplied_key, str):
            return error("apiKey must be a string")
        api_key = (supplied_key or ai_service.resolve_api_key()).strip()

        try:
            user_id = services.logged_in_user_id()
            conn, _, engine, completed = services.load_roadmap_data(
                body.get("careerId"),
                user_id,
            )
            conn.close()

            valid_subjects = {
                "all",
                *(item["id"] for item in engine.subjects),
            }
            if subject not in valid_subjects:
                return error("Unknown subject", 400, subject)

            payload = ai_service.build_recommendation_payload(
                engine,
                completed,
                subject,
            )
            payload["aiEnabled"] = bool(api_key)
            if api_key:
                try:
                    payload["aiExplanation"] = ai_service.ask_chat(
                        (
                            "อธิบายเหตุผลที่ควรเรียน Skill นี้ต่อจากสถานะปัจจุบัน "
                            "ของผู้เรียน และอธิบายว่ามันจะช่วยปลดล็อกอะไรบ้าง"
                        ),
                        engine,
                        completed,
                        api_key,
                    )
                except RuntimeError as exc:
                    payload["aiExplanation"] = payload["fallbackExplanation"]
                    payload["aiWarning"] = str(exc)
            else:
                payload["aiExplanation"] = payload["fallbackExplanation"]
                payload["aiWarning"] = (
                    "AI API key ยังไม่ถูกตั้งค่า "
                    "ระบบใช้งาน graph-only explanation แทน"
                )
            return success(payload, "AI recommendation generated")
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not build AI recommendation", 500, str(exc))

    @app.post("/api/ai/analyze")
    def ai_analyze():
        body = _json_object()
        if body is None:
            return error("Request body must be JSON")

        subject = body.get("subject", "all")
        target_skill_id = body.get("targetSkillId")
        if not isinstance(subject, str):
            return error("subject must be a string")
        if target_skill_id is not None and (
            not isinstance(target_skill_id, str) or not target_skill_id
        ):
            return error(
                "targetSkillId must be a non-empty string when provided"
            )

        try:
            user_id = services.logged_in_user_id()
            conn, _, engine, completed = services.load_roadmap_data(
                body.get("careerId"),
                user_id,
            )
            conn.close()

            valid_subjects = {
                "all",
                *(item["id"] for item in engine.subjects),
            }
            if subject not in valid_subjects:
                return error("Unknown subject", 400, subject)
            if target_skill_id is not None and target_skill_id not in engine.skill_by_id:
                return error("Target skill not found", 404, target_skill_id)

            analysis = ai_analyzer.analyze(
                engine,
                completed,
                preferred_subject=subject,
                target_skill_id=target_skill_id,
            )
            return success(analysis, "AI analysis generated")
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except (GraphValidationError, ValueError) as exc:
            return error("Could not analyze learning progress", 500, str(exc))

    @app.post("/api/ai/chat")
    def ai_chat():
        body = _json_object()
        if body is None:
            return error("Request body must be JSON")

        message = body.get("message")
        history = body.get("history", [])
        target_skill_id = body.get("targetSkillId")
        supplied_key = body.get("apiKey")
        if supplied_key is not None and not isinstance(supplied_key, str):
            return error("apiKey must be a string")
        api_key = (supplied_key or ai_service.resolve_api_key()).strip()

        if not isinstance(message, str) or not message.strip():
            return error("Message must be a non-empty string")
        if not isinstance(history, list):
            return error("history must be a list")
        if target_skill_id is not None and (
            not isinstance(target_skill_id, str) or not target_skill_id
        ):
            return error(
                "targetSkillId must be a non-empty string when provided"
            )
        if not api_key:
            return error(
                "AI API key is required. Add it in the page or set "
                "AI_API_KEY in the environment.",
                400,
            )

        try:
            user_id = services.logged_in_user_id()
            conn, _, engine, completed = services.load_roadmap_data(
                body.get("careerId"),
                user_id,
            )
            conn.close()

            if target_skill_id is not None and target_skill_id not in engine.skill_by_id:
                return error("Target skill not found", 404, target_skill_id)

            analysis = ai_analyzer.analyze(
                engine,
                completed,
                target_skill_id=target_skill_id,
            )
            focus = None
            if target_skill_id is not None:
                focus = {
                    "focusedSkill": ai_analyzer.focus_context(
                        engine,
                        completed,
                        target_skill_id,
                    ),
                    "reason": analysis["reason"],
                    "pathToSkill": [
                        {"id": step["id"], "name": step["name"]}
                        for step in analysis["recommendedPath"]
                    ],
                }

            answer = ai_service.ask_chat(
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
            return error(str(exc), 400)
        except RuntimeError as exc:
            return error("AI request failed", 502, str(exc))
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except GraphValidationError as exc:
            return error("Could not answer the chat question", 500, str(exc))

    @app.post("/api/chat")
    def teaching_chat():
        """Teach the next skill selected by the deterministic analyzer."""

        body = _json_object()
        if body is None:
            return error("Request body must be JSON")
        message = body.get("message")
        history = body.get("history", [])
        if not isinstance(message, str) or not message.strip():
            return error("message must be a non-empty string")

        try:
            user_id = services.logged_in_user_id()
            conn, _, engine, completed = services.load_roadmap_data(
                body.get("careerId"),
                user_id,
            )
            conn.close()
            analysis = ai_analyzer.analyze(engine, completed)
            answer = teaching_assistant.answer(message, analysis, history)
            return success(
                {
                    "answer": answer,
                    "recommendedSkill": analysis["nextSkill"],
                    "reason": analysis["reason"],
                },
                "Teaching response generated",
            )
        except ValueError as exc:
            return error(str(exc), 400)
        except RuntimeError as exc:
            return error("AI teaching request failed", 502, str(exc))
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Database connection failed", 500, str(exc))
        except GraphValidationError as exc:
            return error("Could not prepare teaching context", 500, str(exc))
