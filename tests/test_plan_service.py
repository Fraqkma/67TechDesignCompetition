"""Tests for graph-derived Goal-to-Plan scheduling."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from backend.graph_engine import GraphEngine
from backend.plan_service import PlanService


class PlanServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        database_path = Path(__file__).resolve().parents[1] / "data" / "database.json"
        self.engine = GraphEngine(json.loads(database_path.read_text(encoding="utf-8")))

    def test_preview_uses_only_missing_graph_path_and_weekly_capacity(self) -> None:
        preview = PlanService.build_preview(
            self.engine, {"basic_algebra"}, "functions_graphs", 6, date(2026, 8, 17)
        )

        self.assertEqual(preview["planSource"], "graph_engine")
        self.assertEqual([item["skillId"] for item in preview["path"]], ["functions_graphs"])
        self.assertEqual(preview["totalHours"], 10)
        self.assertEqual([week["plannedHours"] for week in preview["weeks"]], [6, 4])
        self.assertEqual(preview["estimatedCompletionDate"], "2026-08-30")

    def test_preview_rejects_invalid_capacity(self) -> None:
        with self.assertRaises(ValueError):
            PlanService.build_preview(self.engine, set(), "basic_algebra", 0, date.today())


if __name__ == "__main__":
    unittest.main()
