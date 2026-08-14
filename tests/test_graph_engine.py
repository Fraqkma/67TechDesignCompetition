"""Unit tests for graph rules using the DB-backed skill graph."""

from __future__ import annotations

import copy
import unittest

from app import get_db
from backend.db_store import load_database
from backend.graph_engine import GraphEngine, GraphValidationError


class GraphEngineTests(unittest.TestCase):
    """Check the rules most likely to break during roadmap editing."""

    @classmethod
    def setUpClass(cls) -> None:
        conn = get_db()
        try:
            cls.database = load_database(conn)
        finally:
            conn.close()
        cls.engine = GraphEngine(cls.database)

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
        root_ids = [
            skill["id"]
            for skill in self.database["skills"]
            if not self.engine.prerequisites[skill["id"]]
        ]
        self.assertTrue(root_ids)
        for skill_id in root_ids:
            self.assertEqual(statuses[skill_id], "available")

    def test_all_prerequisites_are_required(self) -> None:
        """A skill stays locked until every prerequisite is done."""

        skill = next(
            skill
            for skill in self.database["skills"]
            if len(self.engine.prerequisites[skill["id"]]) >= 2
        )
        path_ids = [
            step["skillId"]
            for step in self.engine.build_learning_path(skill["id"], set())
        ]
        prereq_ids = path_ids[:-1]
        self.assertTrue(prereq_ids)

        partial = self.engine.clean_completed(prereq_ids[:-1])
        self.assertEqual(
            self.engine.calculate_statuses(partial)[skill["id"]], "locked"
        )

        complete = self.engine.clean_completed(prereq_ids)
        self.assertEqual(
            self.engine.calculate_statuses(complete)[skill["id"]], "available"
        )

    def test_learning_path_respects_every_edge(self) -> None:
        """All prerequisites in the target subgraph must precede their child."""

        target = self.database["skills"][-1]["id"]
        path = self.engine.build_learning_path(target, set())
        path_ids = [step["skillId"] for step in path]
        positions = {skill_id: index for index, skill_id in enumerate(path_ids)}

        self.assertEqual(path_ids[-1], target)
        for edge in self.database["edges"]:
            if edge["source"] in positions and edge["target"] in positions:
                self.assertLess(
                    positions[edge["source"]], positions[edge["target"]]
                )

    def test_recommendation_is_always_available(self) -> None:
        """The recommendation algorithm must never suggest a locked skill."""

        completed = set()
        statuses = self.engine.calculate_statuses(completed)
        recommendation = self.engine.recommend_next(completed)

        self.assertIsNotNone(recommendation)
        self.assertEqual(statuses[recommendation["skillId"]], "available")

    def test_progress_uses_skill_weights(self) -> None:
        """Completing one skill contributes its weight to career progress."""

        skill = next(
            skill for skill in self.database["skills"] if skill.get("required", True)
        )
        progress = self.engine.calculate_progress({skill["id"]})
        expected = round(skill["weight"] / progress["totalWeight"] * 100)

        self.assertEqual(progress["completedWeight"], skill["weight"])
        self.assertEqual(progress["career"], expected)

    def test_uncomplete_cascades_to_invalid_dependents(self) -> None:
        """Removing a skill must also remove completed dependents."""

        all_completed = {
            skill["id"] for skill in self.database["skills"]
        }
        target = next(
            skill["id"]
            for skill in self.database["skills"]
            if self.engine.children[skill["id"]]
        )
        remaining, removed = self.engine.remove_skill_and_invalid_dependents(
            target, all_completed
        )

        self.assertNotIn(target, remaining)
        for skill_id in removed:
            self.assertNotIn(skill_id, remaining)

    def test_cycle_is_rejected(self) -> None:
        """A backward edge that creates a loop must fail validation."""

        # Follow one prerequisite chain to an ancestor, then add an edge from
        # the descendant back to that ancestor to force a cycle.
        descendant = self.database["skills"][-1]["id"]
        ancestor = descendant
        while self.engine.prerequisites[ancestor]:
            ancestor = sorted(self.engine.prerequisites[ancestor])[0]

        cyclic_database = copy.deepcopy(self.database)
        cyclic_database["edges"].append(
            {"source": descendant, "target": ancestor}
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
