"""Database-independent tests for the modular application infrastructure."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import app as app_module
from backend import db_store
from backend.database import DatabasePool


class ApplicationFactoryTests(unittest.TestCase):
    def test_factory_registers_every_route_group_without_connecting(self) -> None:
        with patch.object(DatabasePool, "_get_pool") as get_pool:
            application = app_module.create_app()

        get_pool.assert_not_called()
        rules = {rule.rule for rule in application.url_map.iter_rules()}
        self.assertIn("/api/login", rules)
        self.assertIn("/api/roadmap", rules)
        self.assertIn("/api/ai/chat", rules)
        self.assertIn("/api/social/dashboard", rules)

    def test_app_module_keeps_legacy_ai_patch_points(self) -> None:
        application = app_module.create_app()
        services = application.extensions["enlightenment_compass"]
        self.assertIs(services.ai_service, app_module.AIService)

    def test_session_string_user_id_is_normalized(self) -> None:
        application = app_module.create_app()
        services = application.extensions["enlightenment_compass"]
        with application.test_request_context("/"):
            from flask import session

            session["user_id"] = "42"
            self.assertEqual(services.logged_in_user_id(), 42)
            self.assertEqual(session["user_id"], 42)

    @patch("backend.routes.account.db_store.ensure_schema")
    @patch("backend.routes.account.bcrypt.checkpw", return_value=True)
    def test_login_reuses_one_database_connection(
        self,
        _check_password,
        _ensure_schema,
    ) -> None:
        application = app_module.create_app()
        services = application.extensions["enlightenment_compass"]
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.fetchone.side_effect = [
            (7, "learner@example.com", "stored-hash", "user-uid"),
            ("cat", "blue", "ไม่ต้องการระบุ"),
        ]
        conn = Mock()
        conn.cursor.return_value = cursor
        services.get_db = Mock(return_value=conn)

        response = application.test_client().post(
            "/api/login",
            json={"email": "learner@example.com", "password": "password"},
        )

        self.assertEqual(response.status_code, 200)
        services.get_db.assert_called_once_with()
        conn.close.assert_called_once_with()


class DatabasePoolTests(unittest.TestCase):
    @patch("backend.database.psycopg2_pool.ThreadedConnectionPool")
    def test_pool_is_created_lazily_and_close_returns_connection(self, pool_cls) -> None:
        config_provider = Mock(
            return_value={
                "host": "db",
                "port": "5432",
                "database": "test",
                "user": "test",
                "password": "secret",
            }
        )
        raw_connection = Mock()
        pool = pool_cls.return_value
        pool.getconn.return_value = raw_connection
        database = DatabasePool(config_provider)

        config_provider.assert_not_called()
        connection = database.connect()
        config_provider.assert_called_once_with()
        self.assertIs(connection.cursor, raw_connection.cursor)

        connection.close()
        connection.close()  # Closing a proxy twice is intentionally harmless.
        raw_connection.rollback.assert_called_once_with()
        pool.putconn.assert_called_once_with(raw_connection)


class SchemaBootstrapTests(unittest.TestCase):
    def test_achievement_seed_preserves_all_canonical_ids(self) -> None:
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        conn = Mock()
        conn.cursor.return_value = cursor

        db_store.seed_achievements(conn)

        delete_parameters = cursor.execute.call_args_list[0].args[1]
        expected_ids = tuple(
            item[0]
            for item in (
                db_store.ACHIEVEMENT_SEEDS
                + db_store.CAREER_ACHIEVEMENT_SEEDS
            )
        )
        self.assertEqual(delete_parameters, expected_ids)

    def test_schema_is_committed_before_process_cache_is_set(self) -> None:
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        conn = Mock()
        conn.cursor.return_value = cursor

        with (
            patch.object(db_store, "_schema_initialized", False),
            patch.object(db_store, "SCHEMA_STATEMENTS", []),
            patch.object(db_store, "seed_achievements"),
            patch.object(db_store, "seed_subjects_and_nodes"),
            patch.object(db_store, "seed_ranks"),
            patch.object(db_store, "seed_meme_questions"),
        ):
            db_store.ensure_schema(conn)
            self.assertTrue(db_store._schema_initialized)

        conn.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
