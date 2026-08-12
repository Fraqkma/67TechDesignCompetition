"""Tests for the structured, graph-grounded AI Analyzer."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.ai_analyzer import AIAnalyzer
from backend.graph_engine import GraphEngine


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "database.json"


class AIAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        with DATABASE_PATH.open(encoding="utf-8") as database_file:
            self.engine = GraphEngine(json.load(database_file))

    def test_analysis_only_recommends_graph_available_skill(self) -> None:
        analysis = AIAnalyzer.analyze(self.engine, {"basic_algebra"})
        next_skill_id = analysis["nextSkill"]["id"]

        self.assertEqual(
            self.engine.calculate_statuses({"basic_algebra"})[next_skill_id],
            "available",
        )
        self.assertEqual(analysis["analysisSource"], "graph_engine")
        self.assertIn("teachingPrompt", analysis)

    def test_target_path_contains_only_missing_graph_path(self) -> None:
        analysis = AIAnalyzer.analyze(
            self.engine, set(), target_skill_id="embedded_systems"
        )
        path_ids = [skill["id"] for skill in analysis["recommendedPath"]]

        self.assertEqual(path_ids[-1], "embedded_systems")
        self.assertEqual(
            [skill["id"] for skill in analysis["skillGap"]], path_ids
        )
        self.assertEqual(analysis["nextSkill"]["id"], path_ids[0])

    def test_blocked_skills_expose_only_graph_prerequisites(self) -> None:
        analysis = AIAnalyzer.analyze(self.engine, set())
        electricity = next(
            skill for skill in analysis["blockedSkills"] if skill["id"] == "electricity"
        )

        self.assertEqual(
            electricity["missingPrerequisiteIds"],
            ["basic_algebra", "basic_physics"],
        )


if __name__ == "__main__":
    unittest.main()
