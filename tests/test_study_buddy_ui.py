"""Integration checks for Study Buddy inside the original Roadmap UI."""

from __future__ import annotations

import unittest
from pathlib import Path

from app import create_app


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "database.json"


class StudyBuddyUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(DATABASE_PATH)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1

    def test_original_app_registers_social_routes(self) -> None:
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}

        self.assertIn("/study-buddy", rules)
        self.assertIn("/api/social/dashboard", rules)
        self.assertIn("/api/social/friend-requests", rules)
        self.assertIn(
            "/api/social/study-groups/<int:group_id>/join", rules
        )
        self.assertIn(
            "/api/social/study-groups/<int:group_id>/leave", rules
        )
        self.assertIn(
            "/api/social/study-groups/<int:group_id>/messages", rules
        )

    def test_roadmap_contains_integrated_friend_controls(self) -> None:
        response = self.client.get("/roadmap")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"buddy-nav-button", response.data)
        self.assertIn(b"study-buddy-panel", response.data)
        self.assertIn(b"buddy-subject-tabs", response.data)
        self.assertIn(b"js/study-buddy-panel.js", response.data)

    def test_integrated_assets_and_friend_hub_are_served(self) -> None:
        css = self.client.get("/static/css/study-buddy-panel.css")
        javascript = self.client.get("/static/js/study-buddy-panel.js")
        hub = self.client.get("/study-buddy")
        self.addCleanup(css.close)
        self.addCleanup(javascript.close)
        self.addCleanup(hub.close)

        self.assertEqual(css.status_code, 200)
        self.assertEqual(javascript.status_code, 200)
        self.assertEqual(hub.status_code, 200)
        self.assertIn(b'id="friends"', hub.data)
        self.assertIn(b'id="joinable-group-list"', hub.data)
        self.assertIn(b'id="group-chat-dialog"', hub.data)
        self.assertIn(b'id="group-chat-messages"', hub.data)


if __name__ == "__main__":
    unittest.main()
