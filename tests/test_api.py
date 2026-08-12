"""Integration tests for Flask routes and temporary JSON persistence."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

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
        response = self.client.post(
            "/api/ai/recommendation",
            json={"subject": "all"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("recommendation", payload["data"])
        self.assertIn("graphSummary", payload["data"])

    def test_ai_chat_requires_api_key(self) -> None:
        response = self.client.post(
            "/api/ai/chat",
            json={"message": "ช่วยอธิบาย roadmap ให้ผมฟัง"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("API key", payload["error"])


if __name__ == "__main__":
    unittest.main()
