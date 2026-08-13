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

    def test_graph_is_valid_dag(self) -> None:
        """Every skill must appear once in the topological order."""

        order = self.engine.topological_order
        self.assertEqual(len(order), len(self.database["skills"]))
        self.assertEqual(len(order), len(set(order)))

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
            GraphEngine(cyclic_database)


if __name__ == "__main__":
    unittest.main()
