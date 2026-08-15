"""Unit tests for chat input and session-history validation."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from backend.teaching_assistant import TeachingAssistant
from backend.ai_service import AIService


ANALYSIS = {
    "nextSkill": {"id": "basic_algebra", "name": "Basic Algebra"},
    "teachingPrompt": "Teach Basic Algebra using the graph.",
}


class TeachingAssistantTests(unittest.TestCase):
    def test_history_is_limited_to_recent_valid_messages(self) -> None:
        history = [{"role": "user", "content": str(index)} for index in range(20)]
        cleaned = TeachingAssistant.clean_history(history)

        self.assertEqual(len(cleaned), TeachingAssistant.MAX_HISTORY_MESSAGES)
        self.assertEqual(cleaned[0]["content"], "8")

    def test_invalid_history_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TeachingAssistant.clean_history([{"role": "system", "content": "no"}])

    @patch("backend.teaching_assistant.AIService.ask_teaching", return_value="answer")
    def test_answer_passes_analyzer_context_to_existing_provider_service(self, mocked):
        answer = TeachingAssistant.answer("Explain variables", ANALYSIS, [])

        self.assertEqual(answer, "answer")
        self.assertEqual(mocked.call_args.args[1], ANALYSIS)

    @patch("backend.ai_service.AIService._request_completion", return_value="answer")
    def test_provider_request_contains_prompt_and_history(self, mocked):
        AIService.ask_teaching(
            "Give me an example",
            ANALYSIS,
            [{"role": "user", "content": "What is algebra?"}],
        )

        messages = mocked.call_args.args[0]
        self.assertIn(ANALYSIS["teachingPrompt"], messages[1]["content"])
        self.assertEqual(messages[2], {"role": "user", "content": "What is algebra?"})
        self.assertEqual(messages[-1], {"role": "user", "content": "Give me an example"})

    @patch("backend.ai_service.AIService._request_completion", return_value="answer")
    def test_ask_chat_includes_graph_context_and_history(self, mocked):
        engine = Mock()
        engine.career = {"name": "Software Engineer"}
        engine.subjects = []
        engine.skill_by_id = {}
        engine.topological_order = []
        engine.calculate_progress.return_value = {"percent": 0}
        engine.calculate_statuses.return_value = {}

        AIService.ask_chat(
            "แล้ว skill ถัดไปคืออะไร",
            engine,
            set(),
            "test-key",
            history=[{"role": "user", "content": "ช่วยอธิบาย roadmap หน่อย"}],
        )

        messages = mocked.call_args.args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Skill Tree context", messages[1]["content"])
        self.assertEqual(
            messages[2],
            {"role": "user", "content": "ช่วยอธิบาย roadmap หน่อย"},
        )
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "แล้ว skill ถัดไปคืออะไร")

    def test_ask_chat_rejects_non_list_history(self) -> None:
        engine = Mock()
        engine.career = {"name": "Software Engineer"}
        engine.subjects = []
        engine.skill_by_id = {}
        engine.topological_order = []
        engine.calculate_progress.return_value = {"percent": 0}
        engine.calculate_statuses.return_value = {}
        with self.assertRaises(ValueError):
            AIService.ask_chat(
                "สวัสดี",
                engine,
                set(),
                "test-key",
                history="not-a-list",
            )

    @patch("backend.ai_service.AIService._request_completion", return_value="answer")
    def test_ask_chat_includes_focus_context(self, mocked):
        engine = Mock()
        engine.career = {"name": "Software Engineer"}
        engine.subjects = []
        engine.skill_by_id = {}
        engine.topological_order = []
        engine.calculate_progress.return_value = {"percent": 0}
        engine.calculate_statuses.return_value = {}

        AIService.ask_chat(
            "ช่วยอธิบาย skill นี้",
            engine,
            set(),
            "test-key",
            focus={"focusedSkill": {"id": "sql", "name": "SQL"}},
        )

        messages = mocked.call_args.args[0]
        focus_message = next(
            message
            for message in messages
            if "Focused skill" in message["content"]
        )
        self.assertIn("SQL", focus_message["content"])

    @patch("backend.ai_service.request.urlopen")
    def test_provider_request_uses_bearer_authorization(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"choices": [{"message": {"content": "answer"}}]}'
        )

        with patch.dict("os.environ", {"AI_MODEL": "test-model"}):
            answer = AIService._request_completion(
                [{"role": "user", "content": "hello"}], "test-key"
            )

        self.assertEqual(answer, "answer")
        request_object = mocked_urlopen.call_args.args[0]
        self.assertEqual(request_object.get_header("Authorization"), "Bearer test-key")

    def test_profile_prompt_uses_onboarding_answers_and_achievements(self):
        prompt = AIService.build_profile_prompt(
            {
                "favoriteAnimal": "cat",
                "favoriteColor": "sky blue",
                "favoriteSeason": "rainy",
            },
            ["First Step", "Code Novice"],
        )

        self.assertIn("cat", prompt.lower())
        self.assertIn("sky blue", prompt.lower())
        self.assertIn("rainy", prompt.lower())
        self.assertIn("First Step", prompt)
        self.assertIn("Code Novice", prompt)

    def test_profile_fallback_image_is_svg_bytes(self):
        image_bytes = AIService.generate_profile_fallback_image(
            {
                "favoriteAnimal": "cat",
                "favoriteColor": "sky blue",
                "favoriteSeason": "rainy",
            },
            ["First Step"],
        )

        self.assertTrue(image_bytes.startswith(b"<svg"))
        self.assertIn(b"cat", image_bytes.lower())

    @patch("backend.ai_service.request.urlopen")
    def test_profile_image_generation_uses_openai_image_endpoint(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"data": [{"b64_json": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAF"}]}'
        )

        with patch.dict(
            "os.environ",
            {"AI_API_KEY": "test-key", "AI_IMAGE_MODEL": "gpt-image-1"},
            clear=False,
        ):
            image_bytes = AIService.generate_profile_image(
                {
                    "favoriteAnimal": "cat",
                    "favoriteColor": "sky blue",
                    "favoriteSeason": "rainy",
                },
                ["First Step"],
            )

        self.assertTrue(image_bytes.startswith(b"\x89PNG"))
        request_object = mocked_urlopen.call_args.args[0]
        self.assertIn("/images/generations", request_object.full_url)
        self.assertEqual(request_object.get_header("Authorization"), "Bearer test-key")


if __name__ == "__main__":
    unittest.main()
