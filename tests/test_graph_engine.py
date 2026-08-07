"""Unit tests for graph rules without starting a web server."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from backend.graph_engine import GraphEngine, GraphValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_DIR / "data" / "database.json"


class GraphEngineTests(unittest.TestCase):
    """Check the rules most likely to break during roadmap editing."""

    def setUp(self) -> None:
        with DATABASE_PATH.open("r", encoding="utf-8") as database_file:
            self.database = json.load(database_file)
        self.engine = GraphEngine(self.database)

    def test_graph_is_valid_dag(self) -> None:
        """Every skill must appear once in the topological order."""

        order = self.engine.topological_order
        self.assertEqual(len(order), len(self.database["skills"]))
        self.assertEqual(len(order), len(set(order)))

    def test_root_skills_are_available(self) -> None:
        """Nodes with no prerequisites must be immediately learnable."""

        statuses = self.engine.calculate_statuses(set())
        self.assertEqual(statuses["basic_algebra"], "available")
        self.assertEqual(statuses["basic_physics"], "available")
        self.assertEqual(statuses["programming_fundamentals"], "available")

    def test_all_prerequisites_are_required(self) -> None:
        """Electricity stays locked until both Algebra and Physics are done."""

        only_algebra = self.engine.calculate_statuses({"basic_algebra"})
        self.assertEqual(only_algebra["electricity"], "locked")

        both_foundations = self.engine.calculate_statuses(
            {"basic_algebra", "basic_physics"}
        )
        self.assertEqual(both_foundations["electricity"], "available")

    def test_learning_path_respects_every_edge(self) -> None:
        """All prerequisites in the target subgraph must precede their child."""

        path = self.engine.build_learning_path("embedded_systems", set())
        path_ids = [step["skillId"] for step in path]
        positions = {skill_id: index for index, skill_id in enumerate(path_ids)}

        self.assertEqual(path_ids[-1], "embedded_systems")
        for edge in self.database["edges"]:
            if edge["source"] in positions and edge["target"] in positions:
                self.assertLess(
                    positions[edge["source"]], positions[edge["target"]]
                )

    def test_recommendation_is_always_available(self) -> None:
        """The recommendation algorithm must never suggest a locked skill."""

        completed = {"basic_algebra"}
        statuses = self.engine.calculate_statuses(completed)
        recommendation = self.engine.recommend_next(completed)

        self.assertIsNotNone(recommendation)
        self.assertEqual(statuses[recommendation["skillId"]], "available")

    def test_progress_uses_skill_weights(self) -> None:
        """Completing one weight-1 node contributes 1/totalWeight."""

        progress = self.engine.calculate_progress({"basic_algebra"})
        expected = round(1 / progress["totalWeight"] * 100)

        self.assertEqual(progress["completedWeight"], 1)
        self.assertEqual(progress["career"], expected)

    def test_uncomplete_cascades_to_invalid_dependents(self) -> None:
        """Removing C must also remove completed skills that need C."""

        all_completed = {skill["id"] for skill in self.database["skills"]}
        remaining, removed = self.engine.remove_skill_and_invalid_dependents(
            "c_programming", all_completed
        )

        self.assertNotIn("c_programming", remaining)
        self.assertIn("data_structures", removed)
        self.assertIn("computer_architecture", removed)
        self.assertIn("embedded_systems", removed)

    def test_cycle_is_rejected(self) -> None:
        """A backward edge that creates a loop must fail validation."""

        cyclic_database = copy.deepcopy(self.database)
        cyclic_database["edges"].append(
            {"source": "embedded_systems", "target": "basic_algebra"}
        )

        with self.assertRaises(GraphValidationError):
            GraphEngine(cyclic_database)


if __name__ == "__main__":
    unittest.main()
