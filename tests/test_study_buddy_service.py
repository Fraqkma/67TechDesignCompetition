"""Unit tests for graph-backed Study Buddy domain logic."""

from __future__ import annotations

import unittest

from backend.graph_engine import GraphEngine
from backend.study_buddy_service import (
    build_buddy_match,
    build_path_snapshot,
    list_shareable_skills,
    require_shareable_skill,
)


def build_engine() -> GraphEngine:
    skills = []
    for skill_id, name, level in (
        ("1", "Foundation", "beginner"),
        ("2", "Python", "beginner"),
        ("3", "Git", "beginner"),
        ("4", "Backend API", "intermediate"),
    ):
        skills.append(
            {
                "id": skill_id,
                "name": name,
                "thaiName": name,
                "subjectId": "core",
                "level": level,
                "difficulty": 1 if level == "beginner" else 2,
                "weight": 1,
                "required": True,
                "careerRelevance": 3,
            }
        )
    return GraphEngine(
        {
            "career": {"id": "9", "name": "Software Engineer"},
            "subjects": [{"id": "core", "name": "Core"}],
            "skills": skills,
            "edges": [
                {"source": "1", "target": "2"},
                {"source": "1", "target": "3"},
                {"source": "2", "target": "4"},
            ],
        }
    )


class StudyBuddyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = build_engine()

    def test_snapshot_is_built_from_graph_statuses_and_edges(self) -> None:
        snapshot = build_path_snapshot(self.engine, {"1"})

        self.assertEqual(snapshot["source"], "graph_engine")
        self.assertEqual(snapshot["career"]["id"], "9")
        self.assertEqual(snapshot["progress"]["completedCount"], 1)
        self.assertEqual(
            {skill["id"] for skill in snapshot["availableSkills"]},
            {"2", "3"},
        )
        self.assertEqual(snapshot["edges"], self.engine.edges)
        self.assertEqual(len(snapshot["skills"]), 4)

    def test_invalid_completion_is_not_shared(self) -> None:
        snapshot = build_path_snapshot(self.engine, {"4"})

        self.assertEqual(snapshot["completedSkills"], [])
        self.assertEqual(
            [skill["id"] for skill in snapshot["availableSkills"]],
            ["1"],
        )

    def test_only_graph_unlocked_skills_can_be_shared(self) -> None:
        shareable = list_shareable_skills(self.engine, {"1"})

        self.assertEqual({skill["id"] for skill in shareable}, {"1", "2", "3"})
        with self.assertRaises(PermissionError):
            require_shareable_skill(self.engine, {"1"}, "4")

    def test_match_explains_shared_and_complementary_skills(self) -> None:
        match = build_buddy_match(
            self.engine,
            {"1"},
            {"1", "2"},
            {"id": 77, "displayName": "Buddy", "uid": "BUDDY77"},
        )

        self.assertEqual(match["matchSource"], "graph_engine")
        self.assertEqual(
            [skill["id"] for skill in match["sharedAvailableSkills"]],
            ["3"],
        )
        self.assertEqual(
            [skill["id"] for skill in match["buddyCanHelpWith"]],
            ["2"],
        )
        self.assertGreater(match["matchScore"], 40)


if __name__ == "__main__":
    unittest.main()
