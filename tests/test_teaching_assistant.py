"""Unit tests for chat input and session-history validation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
