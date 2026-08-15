"""AI assistant utilities for roadmap reasoning and chat support.

This module intentionally keeps the graph as the single source of truth. The AI
helper can read the roadmap, explain it, and answer questions, but it never
modifies the prerequisite graph itself.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from backend.graph_engine import GraphEngine


class AIService:
    """Small OpenAI-compatible helper for graph-aware AI features."""

    MAX_HISTORY_MESSAGES = 12
    MAX_MESSAGE_LENGTH = 2_000

    @staticmethod
    def _clean_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        """Keep only the most recent valid user/assistant turns."""
        if history is None:
            return []
        if not isinstance(history, list):
            raise ValueError("history must be a list")

        clean: list[dict[str, str]] = []
        for item in history[-AIService.MAX_HISTORY_MESSAGES:]:
            if not isinstance(item, dict):
                raise ValueError("Each history item must be an object")
            role, content = item.get("role"), item.get("content")
            if role not in {"user", "assistant"}:
                raise ValueError("History roles must be user or assistant")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("History content must be a non-empty string")
            clean.append(
                {
                    "role": role,
                    "content": content.strip()[: AIService.MAX_MESSAGE_LENGTH],
                }
            )
        return clean

    @staticmethod
    def _resolve_model() -> str:
        model = os.getenv("AI_MODEL", "").strip()
        if not model:
            return "gpt-4o-mini"
        return model

    @staticmethod
    def _resolve_base_url() -> str:
        return os.getenv("AI_BASE_URL", "https://api.openai.com/v1")

    @staticmethod
    def resolve_api_key() -> str:
        """Read the server-side API key, preferring the standard OpenAI name."""

        return (
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("AI_API_KEY", "").strip()
        )

    @staticmethod
    def build_profile_prompt(
        answers: dict[str, str], achievements: list[str] | None = None
    ) -> str:
        """Create a prompt for a custom profile portrait based on onboarding answers."""
        favorite_animal = (answers.get("favoriteAnimal") or "animal of choice").strip()
        favorite_color = (answers.get("favoriteColor") or "favorite color").strip()
        favorite_season = (answers.get("favoriteSeason") or "favorite season").strip()
        achievement_text = ", ".join(achievements or []) or "new learner"

        return (
            "Create a warm, polished profile portrait for a learner with a joyful science-tech style. "
            "Use a friendly character illustration with a modern educational vibe. "
            f"The learner loves {favorite_animal}, likes {favorite_color}, and prefers {favorite_season}. "
            "Include subtle visual motifs for learning, skill growth, and discovery. "
            "The portrait should feel confident, creative, and student-friendly, with a clean premium social-app aesthetic. "
            f"Current achievement badges: {achievement_text}. "
            "Return a clean SVG illustration only, with readable shapes and bright but balanced colors."
        )

    @staticmethod
    def generate_profile_image(
        answers: dict[str, str], achievements: list[str] | None = None
    ) -> bytes:
        """Generate a profile portrait using the OpenAI-compatible image API when configured."""
        api_key = AIService.resolve_api_key()
        if not api_key:
            return AIService.generate_profile_fallback_image(answers, achievements)

        prompt = AIService.build_profile_prompt(answers, achievements)
        model = os.getenv("AI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1"
        endpoint = f"{AIService._resolve_base_url().rstrip('/')}/images/generations"

        payload = {
            "model": model,
            "prompt": prompt,
            "size": "1024x1024",
        }

        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except Exception:
            return AIService.generate_profile_fallback_image(answers, achievements)

        data_items = response_body.get("data") or []
        if not data_items:
            return AIService.generate_profile_fallback_image(answers, achievements)

        image_data = data_items[0].get("b64_json")
        if not isinstance(image_data, str) or not image_data:
            return AIService.generate_profile_fallback_image(answers, achievements)

        try:
            return bytes.fromhex(image_data) if image_data.startswith("0x") else __import__("base64").b64decode(image_data)
        except Exception:
            return AIService.generate_profile_fallback_image(answers, achievements)

    @staticmethod
    def generate_profile_fallback_image(
        answers: dict[str, str], achievements: list[str] | None = None
    ) -> bytes:
        """Generate a deterministic SVG portrait when AI image generation is unavailable."""
        favorite_animal = (answers.get("favoriteAnimal") or "animal").strip()
        favorite_color = (answers.get("favoriteColor") or "blue").strip()
        favorite_season = (answers.get("favoriteSeason") or "spring").strip()
        badge_text = ", ".join(achievements or []) or "new learner"
        safe_color = favorite_color.lower().replace(" ", "-")
        short_animal = favorite_animal.lower().replace(" ", "-")
        short_season = favorite_season.lower().replace(" ", "-")

        svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1024\" height=\"1024\" viewBox=\"0 0 1024 1024\">
  <defs>
    <linearGradient id=\"bg\" x1=\"0%\" x2=\"100%\" y1=\"0%\" y2=\"100%\">
      <stop offset=\"0%\" stop-color=\"#0d1b2a\"/>
      <stop offset=\"100%\" stop-color=\"#1d3557\"/>
    </linearGradient>
    <linearGradient id=\"accent\" x1=\"0%\" x2=\"100%\" y1=\"0%\" y2=\"100%\">
      <stop offset=\"0%\" stop-color=\"{safe_color}\"/>
      <stop offset=\"100%\" stop-color=\"#7bdff2\"/>
    </linearGradient>
  </defs>
  <rect width=\"1024\" height=\"1024\" fill=\"url(#bg)\"/>
  <circle cx=\"512\" cy=\"450\" r=\"220\" fill=\"url(#accent)\" opacity=\"0.18\"/>
  <circle cx=\"512\" cy=\"360\" r=\"140\" fill=\"#f3f7ff\"/>
  <path d=\"M390 388c25-118 224-118 249 0v90c-13 64-60 96-124 96-65 0-117-31-125-96z\" fill=\"#f6d7b0\"/>
  <circle cx=\"450\" cy=\"355\" r=\"12\" fill=\"#1b263b\"/>
  <circle cx=\"574\" cy=\"355\" r=\"12\" fill=\"#1b263b\"/>
  <path d=\"M470 430c30 24 80 24 110 0\" stroke=\"#1b263b\" stroke-width=\"10\" stroke-linecap=\"round\" fill=\"none\"/>
  <rect x=\"332\" y=\"600\" width=\"360\" height=\"180\" rx=\"32\" fill=\"rgba(255,255,255,0.09)\"/>
  <text x=\"512\" y=\"650\" text-anchor=\"middle\" font-size=\"42\" fill=\"#eaf6ff\" font-family=\"Arial, sans-serif\">{favorite_animal}</text>
  <text x=\"512\" y=\"700\" text-anchor=\"middle\" font-size=\"34\" fill=\"#dfeeff\" font-family=\"Arial, sans-serif\">{favorite_color}</text>
  <text x=\"512\" y=\"748\" text-anchor=\"middle\" font-size=\"30\" fill=\"#b6ddff\" font-family=\"Arial, sans-serif\">{favorite_season}</text>
  <text x=\"512\" y=\"830\" text-anchor=\"middle\" font-size=\"22\" fill=\"#9ae6ff\" font-family=\"Arial, sans-serif\">{badge_text}</text>
  <circle cx=\"820\" cy=\"220\" r=\"56\" fill=\"#ffd166\" opacity=\"0.8\"/>
  <circle cx=\"180\" cy=\"220\" r=\"36\" fill=\"#80ed99\" opacity=\"0.7\"/>
  <text x=\"512\" y=\"118\" text-anchor=\"middle\" font-size=\"42\" fill=\"#d7ecff\" font-family=\"Arial, sans-serif\">{short_animal}</text>
  <text x=\"512\" y=\"930\" text-anchor=\"middle\" font-size=\"24\" fill=\"#d7ecff\" font-family=\"Arial, sans-serif\">learning profile</text>
</svg>"""
        return svg.encode("utf-8")

    @staticmethod
    def _request_completion(messages: list[dict[str, str]], api_key: str) -> str:
        if not api_key or not api_key.strip():
            raise ValueError("AI API key is required")

        payload = {
            "model": AIService._resolve_model(),
            "messages": messages,
            "temperature": 0.3,
        }

        endpoint = f"{AIService._resolve_base_url().rstrip('/')}/chat/completions"
        request_data = json.dumps(payload).encode("utf-8")

        req = request.Request(
            endpoint,
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                response_body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"AI provider rejected the request: {details}") from exc
        except Exception as exc:  # pragma: no cover - network failure path
            raise RuntimeError(f"AI request failed: {exc}") from exc

        choices = response_body.get("choices", [])
        if not choices:
            raise RuntimeError("AI provider returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("AI provider returned an empty answer")

        return content.strip()

    @staticmethod
    def ask_teaching(
        message: str,
        analysis: dict[str, Any],
        history: list[dict[str, str]],
    ) -> str:
        """Teach only the skill selected by Analyzer, retaining session context."""

        skill = analysis["nextSkill"]
        teaching_prompt = analysis["teachingPrompt"]
        context = json.dumps(
            {
                "recommendedSkill": skill,
                "reason": analysis.get("reason"),
                "skillContext": analysis.get("skillContext"),
                "graphEvidence": analysis.get("graphEvidence"),
            },
            ensure_ascii=False,
        )
        return AIService._request_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Thai teaching assistant. Teach only the skill "
                        "chosen by the Analyzer. Do not decide a learning path, "
                        "invent skills, or invent/modify prerequisites. If the user "
                        "asks outside the recommended skill, politely connect it back "
                        "to the current lesson. Keep explanations practical and concise."
                    ),
                },
                {
                    "role": "system",
                    "content": (
                        "Teaching instruction:\n"
                        f"{teaching_prompt}\n\nTrusted context:\n{context}"
                    ),
                },
                *history,
                {"role": "user", "content": message},
            ],
            AIService.resolve_api_key(),
        )

    @staticmethod
    def _build_graph_context(
        engine: GraphEngine,
        completed_ids: set[str],
        preferred_subject: str | None = None,
    ) -> dict[str, Any]:
        progress = engine.calculate_progress(completed_ids)
        recommendation = engine.recommend_next(completed_ids, preferred_subject)
        recommended_skill = (
            engine.skill_by_id[recommendation["skillId"]]
            if recommendation is not None
            else None
        )

        available_skills = [
            {
                "id": skill_id,
                "name": engine.skill_by_id[skill_id]["name"],
                "subjectId": engine.skill_by_id[skill_id]["subjectId"],
            }
            for skill_id, status in engine.calculate_statuses(completed_ids).items()
            if status == "available"
        ]

        return {
            "career": engine.career,
            "completedCount": len(completed_ids),
            "totalCount": len(engine.skills),
            "progress": progress,
            "preferredSubject": preferred_subject,
            "recommendedSkill": {
                "id": recommended_skill["id"],
                "name": recommended_skill["name"],
                "subjectId": recommended_skill["subjectId"],
                "score": recommendation["score"],
                "reason": recommendation["reason"],
            }
            if recommended_skill is not None and recommendation is not None
            else None,
            "availableSkills": available_skills[:6],
            "subjects": [subject["id"] for subject in engine.subjects],
        }

    @staticmethod
    def generate_local_recommendation_text(
        engine: GraphEngine,
        completed_ids: set[str],
        preferred_subject: str | None = None,
    ) -> str:
        recommendation = engine.recommend_next(completed_ids, preferred_subject)
        if recommendation is None:
            return "โปรเจกต์นี้มี Skill ที่พร้อมเรียนไม่เหลือแล้ว คุณสามารถกลับไปทบทวนหรือเริ่มสร้างเส้นทางใหม่ได้"

        skill = engine.skill_by_id[recommendation["skillId"]]
        reason = recommendation["reason"]
        return (
            f"แนะนำให้เริ่มด้วย {skill['name']} ({skill['thaiName']}) "
            f"เพราะเป็น Skill ที่พร้อมเรียนและมีความสำคัญต่ออาชีพสูง "
            f"โดยมี score {recommendation['score']} และช่วยปลดล็อกประมาณ "
            f"{reason['newlyUnlockedSkills']} Skill. "
            f"ค่าน้ำหนักความสัมพันธ์ต่ออาชีพคือ {reason['careerRelevance']} "
            f"และมี subject bonus {reason['subjectBonus']}"
        )

    @staticmethod
    def build_recommendation_payload(
        engine: GraphEngine,
        completed_ids: set[str],
        preferred_subject: str | None = None,
    ) -> dict[str, Any]:
        recommendation = engine.recommend_next(completed_ids, preferred_subject)
        graph_summary = AIService._build_graph_context(
            engine, completed_ids, preferred_subject
        )

        payload = {
            "recommendation": recommendation,
            "graphSummary": graph_summary,
            "fallbackExplanation": AIService.generate_local_recommendation_text(
                engine, completed_ids, preferred_subject
            ),
        }

        if recommendation is not None:
            payload["recommendationName"] = engine.skill_by_id[
                recommendation["skillId"]
            ]["name"]
            payload["recommendationThaiName"] = engine.skill_by_id[
                recommendation["skillId"]
            ]["thaiName"]
        return payload

    @staticmethod
    def _build_graph_context_text(
        engine: GraphEngine,
        completed_ids: set[str],
    ) -> str:
        """Render the skill graph as JSON for the general chat prompt."""
        return json.dumps(
            {
                "career": engine.career,
                "progress": engine.calculate_progress(completed_ids),
                "subjects": engine.subjects,
                "availableSkills": [
                    {
                        "id": skill_id,
                        "name": engine.skill_by_id[skill_id]["name"],
                        "thaiName": engine.skill_by_id[skill_id]["thaiName"],
                        "subjectId": engine.skill_by_id[skill_id]["subjectId"],
                    }
                    for skill_id, status in engine.calculate_statuses(completed_ids).items()
                    if status == "available"
                ],
                "completedSkills": sorted(completed_ids),
                "topologicalOrder": engine.topological_order,
            },
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def ask_chat(
        message: str,
        engine: GraphEngine,
        completed_ids: set[str],
        api_key: str,
        history: list[dict[str, str]] | None = None,
        focus: dict[str, Any] | None = None,
    ) -> str:
        """Answer any learning question, grounded in the graph as source of truth.

        When ``focus`` is provided (the learner clicked a skill node), the model
        anchors its answer on that skill while still treating the graph as the
        source of truth for prerequisites.
        """

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "คุณเป็น AI ที่ช่วยวิเคราะห์ Learning Skill Tree และตอบคำถามที่เกี่ยวกับ "
                    "การเรียนรู้ของผู้ใช้ การเลือก skill และแผนการเรียนต่อไป "
                    "อย่าคิดค้นหรือเพิ่ม prerequisite ที่ไม่ได้อยู่ใน graph"
                ),
            },
            {
                "role": "system",
                "content": (
                    "Skill Tree context (source of truth):\n"
                    f"{AIService._build_graph_context_text(engine, completed_ids)}"
                ),
            },
        ]
        if focus:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "The learner selected a skill to focus on. Anchor your "
                        "answer on this skill and its data below; still treat the "
                        "skill graph as the source of truth for prerequisites.\n"
                        "Focused skill:\n"
                        f"{json.dumps(focus, ensure_ascii=False, indent=2)}"
                    ),
                }
            )
        messages.extend(AIService._clean_history(history))
        messages.append({"role": "user", "content": message})
        return AIService._request_completion(messages, api_key)
