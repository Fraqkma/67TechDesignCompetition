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

    def _build_engine(self, database: dict) -> GraphEngine:
        return GraphEngine(database)

    def test_graph_is_valid_dag(self) -> None:
        """Every skill must appear once in the topological order."""

        order = self.engine.topological_order
        self.assertEqual(len(order), len(self.database["skills"]))
        self.assertEqual(len(order), len(set(order)))

    def test_database_uses_known_subjects_and_skills(self) -> None:
        """The checked-in graph data must stay internally consistent."""

        skill_ids = {skill["id"] for skill in self.database["skills"]}
        subject_ids = {subject["id"] for subject in self.database["subjects"]}

        self.assertEqual(len(skill_ids), len(self.database["skills"]))
        self.assertTrue(skill_ids)
        for skill in self.database["skills"]:
            self.assertIn(skill["subjectId"], subject_ids)
        for edge in self.database["edges"]:
            self.assertIn(edge["source"], skill_ids)
            self.assertIn(edge["target"], skill_ids)

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
            self._build_engine(cyclic_database)

    def test_duplicate_skill_ids_are_rejected(self) -> None:
        """Two skills with the same id would make the graph ambiguous."""

        duplicate_database = copy.deepcopy(self.database)
        duplicate_database["skills"].append(
            dict(duplicate_database["skills"][0])
        )

        with self.assertRaises(GraphValidationError):
            self._build_engine(duplicate_database)

    def test_unknown_subject_is_rejected(self) -> None:
        """Every skill must belong to one of the declared subjects."""

        invalid_database = copy.deepcopy(self.database)
        invalid_database["skills"][0]["subjectId"] = "not_a_subject"

        with self.assertRaises(GraphValidationError):
            self._build_engine(invalid_database)

    def test_unknown_edge_and_self_loop_are_rejected(self) -> None:
        """Edges must point to real skills and must not loop back to themselves."""

        unknown_edge_database = copy.deepcopy(self.database)
        unknown_edge_database["edges"].append(
            {"source": "basic_algebra", "target": "missing_skill"}
        )

        with self.assertRaises(GraphValidationError):
            self._build_engine(unknown_edge_database)

        self_loop_database = copy.deepcopy(self.database)
        self_loop_database["edges"].append(
            {"source": "basic_algebra", "target": "basic_algebra"}
        )

        with self.assertRaises(GraphValidationError):
            self._build_engine(self_loop_database)


if __name__ == "__main__":
    unittest.main()
