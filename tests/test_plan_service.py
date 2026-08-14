"""Tests for graph-derived Goal-to-Plan scheduling (DB-backed graph)."""

from __future__ import annotations

import unittest
from datetime import date

from app import get_db
from backend.db_store import load_database
from backend.graph_engine import GraphEngine
from backend.plan_service import PlanService


class PlanServiceTests(unittest.TestCase):
    """Schedule the real database graph; assert properties, not fixture numbers."""

    @classmethod
    def setUpClass(cls) -> None:
        conn = get_db()
        try:
            cls.database = load_database(conn)
        finally:
            conn.close()
        cls.engine = GraphEngine(cls.database)

    def test_preview_schedules_exactly_the_missing_path(self) -> None:
        target = self.database["skills"][-1]["id"]
        preview = PlanService.build_preview(
            self.engine, set(), target, 6, date(2026, 8, 17)
        )

        self.assertEqual(preview["planSource"], "graph_engine")
        self.assertEqual(preview["targetSkillId"], target)
        # Every scheduled step must be part of the remaining learning path.
        path_ids = [step["skillId"] for step in preview["path"]]
        self.assertEqual(preview["remainingSkillCount"], len(path_ids))
        self.assertEqual(path_ids[-1], target)

    def test_preview_uses_only_missing_graph_path_and_weekly_capacity(self) -> None:
        target = self.database["skills"][-1]["id"]
        preview = PlanService.build_preview(
            self.engine, set(), target, 6, date(2026, 8, 17)
        )

        # Planned hours across all weeks must equal the path's total hours.
        total_hours = sum(
            self.engine.skill_by_id[step["skillId"]]["estimatedHours"]
            for step in preview["path"]
        )
        self.assertEqual(preview["totalHours"], total_hours)
        self.assertEqual(
            sum(week["plannedHours"] for week in preview["weeks"]),
            total_hours,
        )
        # No week may exceed the learner's weekly capacity.
        self.assertTrue(
            all(
                week["plannedHours"] <= preview["weeklyHours"]
                for week in preview["weeks"]
            )
        )
        # The plan starts on the requested date.
        self.assertEqual(preview["weeks"][0]["startDate"], "2026-08-17")

    def test_preview_rejects_invalid_capacity(self) -> None:
        with self.assertRaises(ValueError):
            PlanService.build_preview(
                self.engine,
                set(),
                self.database["skills"][0]["id"],
                0,
                date.today(),
            )


if __name__ == "__main__":
    unittest.main()
