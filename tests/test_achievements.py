"""Unit tests for the DB-driven achievements system."""

from __future__ import annotations

import unittest

from app import get_db
from backend.db_store import (
    build_achievements_payload,
    ensure_schema,
    evaluate_achievement_condition,
    load_achievements,
)


class AchievementConditionTests(unittest.TestCase):
    """Unlock-condition logic must be pure and need no database."""

    def _stats(self, exp=0, friends=0, study_sessions=0) -> dict[str, int]:
        return {
            "exp": exp,
            "friends": friends,
            "studySessions": study_sessions,
        }

    def test_completed_skills_condition(self) -> None:
        condition = '{"type": "completed_skills", "target": 1}'
        self.assertTrue(
            evaluate_achievement_condition(condition, {"1"}, self._stats())
        )
        self.assertFalse(
            evaluate_achievement_condition(condition, set(), self._stats())
        )

    def test_exp_condition(self) -> None:
        condition = '{"type": "exp", "target": 500}'
        self.assertTrue(
            evaluate_achievement_condition(
                condition, set(), self._stats(exp=500)
            )
        )
        self.assertFalse(
            evaluate_achievement_condition(
                condition, set(), self._stats(exp=499)
            )
        )

    def test_friends_and_study_sessions_conditions(self) -> None:
        stats = self._stats(friends=3, study_sessions=1)
        self.assertTrue(
            evaluate_achievement_condition(
                '{"type": "friends", "target": 3}', set(), stats
            )
        )
        self.assertTrue(
            evaluate_achievement_condition(
                '{"type": "study_sessions", "target": 1}', set(), stats
            )
        )
        self.assertFalse(
            evaluate_achievement_condition(
                '{"type": "friends", "target": 4}', set(), stats
            )
        )

    def test_malformed_conditions_never_unlock(self) -> None:
        stats = self._stats(exp=9999, friends=99, study_sessions=99)
        self.assertFalse(evaluate_achievement_condition("", set(), stats))
        self.assertFalse(
            evaluate_achievement_condition("not json", set(), stats)
        )
        self.assertFalse(
            evaluate_achievement_condition(
                '{"type": "mystery_rule"}', set(), stats
            )
        )


class AchievementDatabaseTests(unittest.TestCase):
    """The catalog must come from the achievements table, not hardcoded code."""

    @classmethod
    def setUpClass(cls) -> None:
        conn = get_db()
        try:
            # Apply the schema (including the condition-column migration and
            # the idempotent seed) so the catalog is always readable.
            ensure_schema(conn)
            conn.commit()
            cls.achievements = load_achievements(conn)
        finally:
            conn.close()

    def test_catalog_is_loaded_from_database(self) -> None:
        self.assertEqual(len(self.achievements), 4)
        names = {achievement["name"] for achievement in self.achievements}
        self.assertIn("First Step", names)
        self.assertIn("Code Novice", names)
        self.assertIn("Social Butterfly", names)
        self.assertIn("Study Buddy Host", names)

    def test_catalog_has_icons_and_conditions(self) -> None:
        for achievement in self.achievements:
            self.assertTrue(
                achievement["iconUrl"].startswith("http"),
                achievement["name"],
            )
            self.assertTrue(achievement["condition"], achievement["name"])


if __name__ == "__main__":
    unittest.main()
