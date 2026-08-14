"""Integration tests for Flask routes backed by the connected PostgreSQL DB."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

import bcrypt

from app import create_app, get_db


class ApiTests(unittest.TestCase):
    """Run the real API against the connected PostgreSQL database."""

    def setUp(self) -> None:
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

        # Create a throwaway user so progress writes satisfy the FK constraint.
        self.test_email = f"test-{uuid4().hex[:8]}@example.com"
        self.test_password = "test-pass-1234"
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (uid, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (
                        uuid4().hex[:12],
                        self.test_email,
                        bcrypt.hashpw(
                            self.test_password.encode("utf-8"),
                            bcrypt.gensalt(),
                        ).decode("utf-8"),
                    ),
                )
                self.user_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (self.user_id, "API Test User"),
                )
            conn.commit()
        finally:
            conn.close()

        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

        # Pick a career and data-driven nodes from the real database.
        response = self.client.get("/api/careers")
        self.careers = response.get_json()["data"]
        available_careers = [c for c in self.careers if c["available"]]
        self.career_id = available_careers[0]["id"] if available_careers else None

        roadmap_response = self.client.get(f"/api/roadmap?career={self.career_id}")
        self.roadmap = roadmap_response.get_json()["data"]
        self.available_node = next(
            node["id"] for node in self.roadmap["nodes"] if node["status"] == "available"
        )
        self.locked_node = next(
            node["id"] for node in self.roadmap["nodes"] if node["status"] == "locked"
        )

    def tearDown(self) -> None:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (self.user_id,))
            conn.commit()
        finally:
            conn.close()

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["graphValid"])
        self.assertGreater(payload["data"]["skillCount"], 0)

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
        self.assertIn(b"tracks-hero", select_track.data)
        self.assertEqual(roadmap.status_code, 200)
        self.assertIn(b"roadmap-page", roadmap.data)

    def test_careers_come_from_the_database(self) -> None:
        response = self.client.get("/api/careers")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(len(payload["data"]), 1)
        for career in payload["data"]:
            self.assertIn("id", career)
            self.assertIn("title", career)
            self.assertIn("description", career)
            self.assertIn("available", career)
        self.assertTrue(any(career["available"] for career in payload["data"]))

    def test_roadmap_contract(self) -> None:
        response = self.client.get(f"/api/roadmap?career={self.career_id}")
        roadmap = response.get_json()["data"]

        self.assertIn("nodes", roadmap)
        self.assertIn("edges", roadmap)
        self.assertIn("progress", roadmap)
        self.assertIn("recommendedSkillId", roadmap)
        self.assertEqual(roadmap["progress"]["career"], 0)
        self.assertEqual(roadmap["career"]["id"], str(self.career_id))

    def test_locked_skill_cannot_be_completed(self) -> None:
        response = self.client.post(
            "/api/progress",
            json={
                "skillId": self.locked_node,
                "completed": True,
                "careerId": self.career_id,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.get_json()["ok"])

    def test_available_skill_can_be_completed_and_persists(self) -> None:
        update_response = self.client.post(
            "/api/progress",
            json={
                "skillId": self.available_node,
                "completed": True,
                "careerId": self.career_id,
            },
        )
        self.assertEqual(update_response.status_code, 200)

        roadmap_response = self.client.get(f"/api/roadmap?career={self.career_id}")
        roadmap = roadmap_response.get_json()["data"]
        node = next(
            item for item in roadmap["nodes"] if item["id"] == self.available_node
        )
        self.assertEqual(node["status"], "completed")

    def test_reset_clears_progress(self) -> None:
        self.client.post(
            "/api/progress",
            json={
                "skillId": self.available_node,
                "completed": True,
                "careerId": self.career_id,
            },
        )
        reset_response = self.client.post(
            "/api/reset",
            json={"careerId": self.career_id},
        )
        roadmap = reset_response.get_json()["data"]

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(roadmap["completedSkillIds"], [])

    def test_ai_recommendation_uses_graph_fallback_without_key(self) -> None:
        with patch.dict(
            "os.environ", {"AI_API_KEY": "", "OPENAI_API_KEY": ""}
        ):
            response = self.client.post(
                "/api/ai/recommendation",
                json={"subject": "all", "careerId": self.career_id},
            )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("recommendation", payload["data"])
        self.assertIn("graphSummary", payload["data"])

    def test_ai_analyzer_returns_future_chatbot_contract(self) -> None:
        response = self.client.post(
            "/api/ai/analyze",
            json={
                "targetSkillId": self.locked_node,
                "subject": "all",
                "careerId": self.career_id,
            },
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        analysis = payload["data"]
        self.assertEqual(analysis["targetSkillId"], self.locked_node)
        self.assertEqual(analysis["recommendedPath"][-1]["id"], self.locked_node)
        self.assertEqual(analysis["analysisSource"], "graph_engine")
        self.assertIsNotNone(analysis["teachingPrompt"])

    def test_ai_analyzer_rejects_unknown_target(self) -> None:
        response = self.client.post(
            "/api/ai/analyze",
            json={"targetSkillId": "not_a_skill", "careerId": self.career_id},
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
        """Schedule the DB graph for the signed-in user (no fixtures)."""

        response = self.client.post(
            "/api/plan/preview",
            json={
                "targetSkillId": self.locked_node,
                "weeklyHours": 6,
                "startDate": "2026-08-17",
            },
        )

        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        plan = payload["data"]
        self.assertEqual(plan["planSource"], "graph_engine")
        self.assertEqual(plan["targetSkillId"], self.locked_node)
        self.assertEqual(plan["weeklyHours"], 6)
        self.assertEqual(plan["startDate"], "2026-08-17")
        self.assertEqual(plan["remainingSkillCount"], len(plan["path"]))
        self.assertEqual(plan["path"][-1]["skillId"], self.locked_node)
        # Every planned hour must fit inside a week at the learner's capacity.
        planned_total = sum(
            step["hours"]
            for week in plan["weeks"]
            for step in week["assignments"]
        )
        self.assertEqual(plan["totalHours"], planned_total)
        self.assertTrue(
            all(
                week["plannedHours"] <= plan["weeklyHours"]
                for week in plan["weeks"]
            )
        )

    def test_analyzer_returns_teaching_context(self) -> None:
        response = self.client.post(
            "/api/ai/analyze", json={"subject": "all", "careerId": self.career_id}
        )
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
                "careerId": self.career_id,
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
        response = self.client.post(
            "/api/chat", json={"message": "ช่วยสอนหน่อย", "careerId": self.career_id}
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "AI teaching request failed")


if __name__ == "__main__":
    unittest.main()
