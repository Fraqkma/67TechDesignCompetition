"""Lazy, pooled PostgreSQL connections for the web application."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from psycopg2 import pool as psycopg2_pool

from backend.config import database_config


class PooledConnection:
    """Proxy a psycopg2 connection and return it to the pool on ``close``."""

    def __init__(self, connection: Any, connection_pool: Any) -> None:
        self._connection = connection
        self._pool = connection_pool

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def close(self) -> None:
        """Discard an open transaction, then safely return the connection."""

        if self._connection is None:
            return
        connection = self._connection
        self._connection = None
        connection.rollback()
        self._pool.putconn(connection)


class DatabasePool:
    """Create the PostgreSQL pool on first use instead of during import.

    The database may live on another host, so pooling avoids reconnecting for
    every request. Lazy creation also lets contributors import the app and run
    database-independent tests before they have local credentials.
    """

    def __init__(
        self,
        config_provider: Callable[[], dict[str, str]] = database_config,
        *,
        min_connections: int = 1,
        max_connections: int = 30,
        connect_timeout: int = 5,
    ) -> None:
        self._config_provider = config_provider
        self._min_connections = min_connections
        self._max_connections = max_connections
        self._connect_timeout = connect_timeout
        self._pool: Any | None = None
        self._lock = threading.Lock()

    def _get_pool(self):
        if self._pool is not None:
            return self._pool
        with self._lock:
            if self._pool is None:
                self._pool = psycopg2_pool.ThreadedConnectionPool(
                    self._min_connections,
                    self._max_connections,
                    connect_timeout=self._connect_timeout,
                    **self._config_provider(),
                )
        return self._pool

    def connect(self) -> PooledConnection:
        """Borrow one connection from the shared pool."""

        pool = self._get_pool()
        return PooledConnection(pool.getconn(), pool)


_database_pool = DatabasePool()


def get_db() -> PooledConnection:
    """Return a reusable PostgreSQL connection from the application pool."""

    return _database_pool.connect()
