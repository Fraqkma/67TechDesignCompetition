"""Integration tests for Flask routes and temporary JSON persistence."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app import create_app


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DATABASE = PROJECT_DIR / "data" / "database.json"


class ApiTests(unittest.TestCase):
    """Run the real API against a disposable copy of database.json."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "database.json"
        shutil.copy2(SOURCE_DATABASE, self.database_path)

        self.app = create_app(self.database_path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["graphValid"])

    def test_frontend_and_assets_are_served(self) -> None:
        """Flask must serve the page, CSS and JavaScript from one localhost."""

        page = self.client.get("/")
        css = self.client.get("/static/css/style.css")
        javascript = self.client.get("/static/js/app.js")
        self.addCleanup(page.close)
        self.addCleanup(css.close)
        self.addCleanup(javascript.close)

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Skill Map", page.data)
        self.assertEqual(css.status_code, 200)
        self.assertEqual(javascript.status_code, 200)

    def test_track_selection_and_roadmap_pages_are_served(self) -> None:
        """The two edited pages must render through their Flask routes."""

        select_track = self.client.get("/select-track")
        roadmap = self.client.get("/roadmap")
        self.addCleanup(select_track.close)
        self.addCleanup(roadmap.close)

        self.assertEqual(select_track.status_code, 200)
        self.assertIn(b'tracks-hero', select_track.data)
        self.assertEqual(roadmap.status_code, 200)
        self.assertIn(b'roadmap-page', roadmap.data)

    def test_roadmap_contract(self) -> None:
        response = self.client.get("/api/roadmap")
        roadmap = response.get_json()["data"]

        self.assertIn("nodes", roadmap)
        self.assertIn("edges", roadmap)
        self.assertIn("progress", roadmap)
        self.assertIn("recommendedSkillId", roadmap)
        self.assertEqual(roadmap["progress"]["career"], 0)

    def test_locked_skill_cannot_be_completed(self) -> None:
        response = self.client.post(
            "/api/progress",
            json={"skillId": "embedded_systems", "completed": True},
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.get_json()["ok"])

    def test_available_skill_can_be_completed_and_persists(self) -> None:
        update_response = self.client.post(
            "/api/progress",
            json={"skillId": "basic_algebra", "completed": True},
        )
        self.assertEqual(update_response.status_code, 200)

        roadmap_response = self.client.get("/api/roadmap")
        roadmap = roadmap_response.get_json()["data"]
        node = next(
            item for item in roadmap["nodes"] if item["id"] == "basic_algebra"
        )
        self.assertEqual(node["status"], "completed")

    def test_reset_clears_progress(self) -> None:
        self.client.post(
            "/api/progress",
            json={"skillId": "basic_algebra", "completed": True},
        )
        reset_response = self.client.post("/api/reset")
        roadmap = reset_response.get_json()["data"]

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(roadmap["completedSkillIds"], [])

    def test_ai_recommendation_uses_graph_fallback_without_key(self) -> None:
        with patch.dict(
            "os.environ", {"AI_API_KEY": "", "OPENAI_API_KEY": ""}
        ):
            response = self.client.post(
                "/api/ai/recommendation",
                json={"subject": "all"},
            )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("recommendation", payload["data"])
        self.assertIn("graphSummary", payload["data"])

    def test_ai_analyzer_returns_future_chatbot_contract(self) -> None:
        response = self.client.post(
            "/api/ai/analyze",
            json={"targetSkillId": "embedded_systems", "subject": "all"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        analysis = payload["data"]
        self.assertEqual(analysis["targetSkillId"], "embedded_systems")
        self.assertEqual(analysis["recommendedPath"][-1]["id"], "embedded_systems")
        self.assertEqual(analysis["analysisSource"], "graph_engine")
        self.assertIsNotNone(analysis["teachingPrompt"])

    def test_ai_analyzer_rejects_unknown_target(self) -> None:
        response = self.client.post(
            "/api/ai/analyze", json={"targetSkillId": "not_a_skill"}
        )

        self.assertEqual(response.status_code, 404)

    def test_ai_chat_requires_api_key(self) -> None:
        with patch.dict(
            "os.environ", {"AI_API_KEY": "", "OPENAI_API_KEY": ""}
        ):
            response = self.client.post(
                "/api/ai/chat",
                json={"message": "ช่วยอธิบาย roadmap ให้ผมฟัง"},
            )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("API key", payload["error"])

    @patch("app.AIService.ask_chat", return_value="อธิบายแบบย่อได้")
    def test_ai_chat_includes_recommended_skill_context(self, mocked_ask_chat) -> None:
        with patch.dict(
            "os.environ", {"AI_API_KEY": "test-key", "OPENAI_API_KEY": ""}
        ):
            response = self.client.post(
                "/api/ai/chat",
                json={"message": "ช่วยอธิบาย roadmap ให้ผมฟัง"},
            )

        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["answer"], "อธิบายแบบย่อได้")
        self.assertIn("recommendedSkill", payload["data"])
        self.assertTrue(payload["data"]["recommendedSkill"]["id"])
        self.assertTrue(mocked_ask_chat.called)

    def test_plan_preview_endpoint_returns_schedule(self) -> None:
        class FakeCursor:
            def __init__(self, rows):
                self.rows = rows
                self.last_query = ""

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, query, params=None):
                self.last_query = query

            def fetchall(self):
                if "SELECT skill_id FROM user_skill_progress" in self.last_query:
                    return self.rows
                return []

        class FakeConnection:
            def __init__(self, rows):
                self.rows = rows

            def cursor(self):
                return FakeCursor(self.rows)

            def commit(self):
                return None

            def rollback(self):
                return None

            def close(self):
                return None

        fake_connection = FakeConnection([("basic_algebra",)])

        with patch("app.get_db", return_value=fake_connection):
            with self.client.session_transaction() as session:
                session["user_id"] = 1

            response = self.client.post(
                "/api/plan/preview",
                json={
                    "targetSkillId": "functions_graphs",
                    "weeklyHours": 6,
                    "startDate": "2026-08-17",
                },
            )

        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        plan = payload["data"]
        self.assertEqual(plan["targetSkillId"], "functions_graphs")
        self.assertEqual(plan["totalHours"], 10)
        self.assertEqual([week["plannedHours"] for week in plan["weeks"]], [6, 4])
        self.assertEqual(plan["estimatedCompletionDate"], "2026-08-30")

    def test_analyzer_returns_teaching_context(self) -> None:
        response = self.client.post("/api/ai/analyze", json={"subject": "all"})
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload["data"]["nextSkill"])
        self.assertTrue(payload["data"]["teachingPrompt"])
        self.assertEqual(payload["data"]["analysisSource"], "graph_engine")

    @patch("app.TeachingAssistant.answer", return_value="นี่คือตัวอย่างคำอธิบาย")
    def test_teaching_chat_uses_server_analyzer_context(self, mocked_answer) -> None:
        response = self.client.post(
            "/api/chat",
            json={
                "message": "ช่วยยกตัวอย่างให้หน่อย",
                "history": [{"role": "assistant", "content": "เริ่มเรียนกัน"}],
            },
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["answer"], "นี่คือตัวอย่างคำอธิบาย")
        analysis = mocked_answer.call_args.args[1]
        self.assertEqual(analysis["analysisSource"], "graph_engine")
        self.assertTrue(analysis["teachingPrompt"])

    def test_teaching_chat_rejects_missing_message(self) -> None:
        response = self.client.post("/api/chat", json={"history": []})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    @patch("app.TeachingAssistant.answer", side_effect=RuntimeError("provider down"))
    def test_teaching_chat_handles_provider_failure(self, _mocked_answer) -> None:
        response = self.client.post("/api/chat", json={"message": "ช่วยสอนหน่อย"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "AI teaching request failed")


if __name__ == "__main__":
    unittest.main()
