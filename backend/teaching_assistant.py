"""Teaching-only chatbot orchestration built on Analyzer output."""

from __future__ import annotations

from typing import Any

from backend.ai_service import AIService


class TeachingAssistant:
    """Validate short-lived conversation history and call the configured provider."""

    MAX_HISTORY_MESSAGES = 12
    MAX_MESSAGE_LENGTH = 2_000

    @classmethod
    def clean_history(cls, history: Any) -> list[dict[str, str]]:
        if history is None:
            return []
        if not isinstance(history, list):
            raise ValueError("history must be a list")

        clean: list[dict[str, str]] = []
        for item in history[-cls.MAX_HISTORY_MESSAGES :]:
            if not isinstance(item, dict):
                raise ValueError("Each history item must be an object")
            role, content = item.get("role"), item.get("content")
            if role not in {"user", "assistant"}:
                raise ValueError("History roles must be user or assistant")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("History content must be a non-empty string")
            clean.append({"role": role, "content": content.strip()[: cls.MAX_MESSAGE_LENGTH]})
        return clean

    @classmethod
    def answer(
        cls,
        message: str,
        analysis: dict[str, Any],
        history: Any = None,
    ) -> str:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message must be a non-empty string")
        if len(message.strip()) > cls.MAX_MESSAGE_LENGTH:
            raise ValueError("Message is too long")
        if not analysis.get("nextSkill") or not analysis.get("teachingPrompt"):
            raise ValueError("There is no recommended skill available to teach")

        return AIService.ask_teaching(
            message.strip(),
            analysis,
            cls.clean_history(history),
        )
