"""Thread-safe JSON storage used in place of a database server.

This module intentionally keeps persistence small and visible for a prototype.
The public methods return deep copies so callers cannot accidentally modify the
in-memory value without going through ``update``.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar


T = TypeVar("T")


class JsonStore:
    """Read and atomically update one JSON file.

    ``threading.RLock`` prevents two Flask requests in the same process from
    writing at the same time. ``os.replace`` makes the final write atomic: the
    old database is replaced only after the temporary JSON file is complete.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self._lock = threading.RLock()

        if not self.path.exists():
            raise FileNotFoundError(f"JSON database not found: {self.path}")

    def _read_unlocked(self) -> dict[str, Any]:
        """Read the database while the caller already holds the lock."""

        with self.path.open("r", encoding="utf-8") as database_file:
            return json.load(database_file)

    def read(self) -> dict[str, Any]:
        """Return a safe copy of the current database."""

        with self._lock:
            return copy.deepcopy(self._read_unlocked())

    def update(self, mutator: Callable[[dict[str, Any]], T]) -> T:
        """Modify the database through ``mutator`` and save it atomically.

        The callback receives the whole decoded JSON object. It may modify that
        object and return any result needed by the API route.
        """

        with self._lock:
            database = self._read_unlocked()
            result = mutator(database)

            temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
            with temporary_path.open("w", encoding="utf-8") as temp_file:
                json.dump(database, temp_file, ensure_ascii=False, indent=2)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temporary_path, self.path)
            return result
