"""Tests for the structured, graph-grounded AI Analyzer."""

from __future__ import annotations

import unittest

from app import get_db
from backend.ai_analyzer import AIAnalyzer
from backend.db_store import load_database
from backend.graph_engine import GraphEngine


class AIAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        conn = get_db()
        try:
            cls.database = load_database(conn)
        finally:
            conn.close()
        cls.engine = GraphEngine(cls.database)

    def test_analysis_only_recommends_graph_available_skill(self) -> None:
        analysis = AIAnalyzer.analyze(self.engine, set())
        next_skill_id = analysis["nextSkill"]["id"]

        self.assertEqual(
            self.engine.calculate_statuses(set())[next_skill_id],
            "available",
        )
        self.assertEqual(analysis["analysisSource"], "graph_engine")
        self.assertIn("teachingPrompt", analysis)

    def test_target_path_contains_only_missing_graph_path(self) -> None:
        target = self.database["skills"][-1]["id"]
        analysis = AIAnalyzer.analyze(
            self.engine, set(), target_skill_id=target
        )
        path_ids = [skill["id"] for skill in analysis["recommendedPath"]]

        self.assertEqual(path_ids[-1], target)
        self.assertEqual(
            [skill["id"] for skill in analysis["skillGap"]], path_ids
        )
        self.assertEqual(analysis["nextSkill"]["id"], path_ids[0])

    def test_blocked_skills_expose_only_graph_prerequisites(self) -> None:
        analysis = AIAnalyzer.analyze(self.engine, set())
        blocked = next(
            skill
            for skill in analysis["blockedSkills"]
            if skill["id"] in self.engine.prerequisites
            and self.engine.prerequisites[skill["id"]]
        )

        self.assertEqual(
            blocked["missingPrerequisiteIds"],
            sorted(self.engine.prerequisites[blocked["id"]]),
        )


if __name__ == "__main__":
    unittest.main()
