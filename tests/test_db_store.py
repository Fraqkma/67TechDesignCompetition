"""Tests that roadmap display data comes from the database, not hardcoded code."""

from __future__ import annotations

import unittest

from app import get_db
from backend.db_store import ensure_schema, load_database, load_rank


class DbStoreTests(unittest.TestCase):
    """Subjects, node display fields and ranks must be DB-driven."""

    @classmethod
    def setUpClass(cls) -> None:
        conn = get_db()
        try:
            ensure_schema(conn)
            conn.commit()
            cls.database = load_database(conn)
        finally:
            conn.close()

    def test_subjects_come_from_the_database(self) -> None:
        subject_ids = {subject["id"] for subject in self.database["subjects"]}
        self.assertTrue(subject_ids)
        for subject in self.database["subjects"]:
            self.assertTrue(subject["name"])
            self.assertTrue(subject["thaiName"])
            self.assertTrue(subject["color"])
        for skill in self.database["skills"]:
            self.assertIn(skill["subjectId"], subject_ids)

    def test_display_fields_come_from_the_database(self) -> None:
        for skill in self.database["skills"]:
            # Thai name is a stored column, not a copy of the English title.
            self.assertTrue(skill["thaiName"])
            self.assertIsInstance(skill["careerRelevance"], int)
            self.assertGreaterEqual(skill["careerRelevance"], 0)
            self.assertIsInstance(skill["techniques"], list)
            self.assertIsInstance(skill["learningOutcomes"], list)
            self.assertIsInstance(skill["realWorld"], list)
            self.assertTrue(skill["description"])

    def test_rank_comes_from_the_database(self) -> None:
        conn = get_db()
        try:
            self.assertEqual(load_rank(conn, 0)["code"], "01")
            self.assertEqual(load_rank(conn, 24)["code"], "01")
            self.assertEqual(load_rank(conn, 25)["code"], "02")
            self.assertEqual(load_rank(conn, 50)["code"], "03")
            self.assertEqual(load_rank(conn, 75)["code"], "04")
            self.assertEqual(load_rank(conn, 100)["code"], "05")
            for progress in (0, 25, 50, 75, 100):
                rank = load_rank(conn, progress)
                self.assertTrue(rank["name"])
                self.assertIsInstance(rank["hint"], str)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
