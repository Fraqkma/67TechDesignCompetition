"""PostgreSQL-backed storage for the Skill Graph.

This module replaces ``data/database.json``.  The connected database described
in ``database_schema_description.txt`` is the single source of truth for:

- ``careers`` / ``nodes`` / ``career_nodes`` / ``node_prerequisites``
  (the skill graph structure)
- ``users`` / ``user_profiles`` / ``user_node_progress``
  (authentication and learner progress)

Only structured facts live in the database.  Display-only fields that the
roadmap UI needs (node position, subject grouping, level, difficulty) are
derived deterministically here so the frontend contract stays unchanged.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.graph_engine import GraphValidationError


# =========================================================
# Schema
# =========================================================

SCHEMA_STATEMENTS: list[str] = [
    # ---- Skill Tree & Career module ----
    """
    CREATE TABLE IF NOT EXISTS careers (
        id BIGSERIAL PRIMARY KEY,
        title VARCHAR(150) NOT NULL,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id BIGSERIAL PRIMARY KEY,
        title VARCHAR(150) NOT NULL,
        description TEXT,
        exp_reward INTEGER NOT NULL DEFAULT 100
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS career_nodes (
        career_id BIGINT NOT NULL REFERENCES careers(id) ON DELETE CASCADE,
        node_id BIGINT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        step_order INTEGER,
        is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (career_id, node_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS node_prerequisites (
        node_id BIGINT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        prerequisite_node_id BIGINT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        PRIMARY KEY (node_id, prerequisite_node_id)
    )
    """,
    # ---- User & Profile module ----
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        uid VARCHAR(12) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        display_name VARCHAR(100) NOT NULL,
        level INTEGER NOT NULL DEFAULT 1,
        current_exp INTEGER NOT NULL DEFAULT 0,
        current_career_id BIGINT REFERENCES careers(id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_node_progress (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        node_id BIGINT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        completed_at TIMESTAMPTZ,
        UNIQUE (user_id, node_id)
    )
    """,
]


def ensure_schema(conn) -> None:
    """Create every table used by the app (idempotent)."""
    with conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)


# =========================================================
# Careers (select-track page)
# =========================================================


def list_careers(conn) -> list[dict[str, Any]]:
    """Return every career with its available skill count."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id,
                c.title,
                c.description,
                COUNT(cn.node_id)::int AS node_count
            FROM careers c
            LEFT JOIN career_nodes cn ON cn.career_id = c.id
            GROUP BY c.id, c.title, c.description
            ORDER BY c.id
            """
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2] or "",
                "nodeCount": row[3],
                "available": row[3] > 0,
                "icon": _initials(row[1]),
            }
            for row in cur.fetchall()
        ]


def career_exists(conn, career_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM careers WHERE id = %s", (career_id,))
        return cur.fetchone() is not None


def first_career_id(conn) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM careers ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


def user_career_id(conn, user_id: int) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT current_career_id FROM user_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None


# =========================================================
# Graph loading (source of truth for GraphEngine)
# =========================================================


def load_database(conn, career_id: int | None = None) -> dict[str, Any]:
    """Build the GraphEngine structure for one career from the database."""
    with conn.cursor() as cur:
        if career_id is None:
            cur.execute(
                "SELECT id, title, description FROM careers ORDER BY id LIMIT 1"
            )
        else:
            cur.execute(
                "SELECT id, title, description FROM careers WHERE id = %s",
                (career_id,),
            )
        career_row = cur.fetchone()
        if career_row is None:
            raise GraphValidationError(
                f"Career not found: {career_id}"
            )

        cur.execute(
            """
            SELECT
                n.id,
                n.title,
                n.description,
                n.exp_reward,
                cn.step_order,
                cn.is_mandatory
            FROM career_nodes cn
            JOIN nodes n ON n.id = cn.node_id
            WHERE cn.career_id = %s
            ORDER BY cn.step_order, n.id
            """,
            (career_row[0],),
        )
        node_rows = cur.fetchall()
        if not node_rows:
            raise GraphValidationError(
                f"Career {career_row[1]} has no skills yet"
            )

        node_ids = [row[0] for row in node_rows]

        # Prerequisites are global; keep only edges inside this career.
        prereqs_map: dict[int, list[int]] = defaultdict(list)
        edges: list[dict[str, Any]] = []
        if node_ids:
            cur.execute(
                """
                SELECT node_id, prerequisite_node_id
                FROM node_prerequisites
                WHERE node_id = ANY(%s) AND prerequisite_node_id = ANY(%s)
                """,
                (node_ids, node_ids),
            )
            for node_id, prereq_id in cur.fetchall():
                edges.append(
                    {"source": str(prereq_id), "target": str(node_id)}
                )
                prereqs_map[node_id].append(prereq_id)

    positions, depths = _layout(node_rows, prereqs_map)

    skills = []
    for row in node_rows:
        node_id, title, description, exp_reward, _step, is_mandatory = row
        depth = depths[node_id]
        level = _level_for_depth(depth)
        skills.append(
            {
                "id": str(node_id),
                "name": title,
                "thaiName": title,
                "shortName": _short_name(title),
                "subjectId": "core",
                "level": level,
                "difficulty": min(5, depth + 1),
                "weight": {"beginner": 1, "intermediate": 2, "advanced": 3}[
                    level
                ],
                "required": True if is_mandatory is None else bool(is_mandatory),
                "careerRelevance": 3,
                "estimatedHours": max(1, (exp_reward or 100) // 10),
                "position": positions[node_id],
                "description": description or "",
                "techniques": [],
                "learningOutcomes": [],
                "realWorld": [],
            }
        )

    return {
        "schemaVersion": 2,
        "career": {
            "id": str(career_row[0]),
            "name": career_row[1],
            "thaiName": career_row[1],
            "description": career_row[2] or "",
            "icon": _initials(career_row[1]),
        },
        "subjects": [
            {
                "id": "core",
                "name": "Core Skills",
                "thaiName": "ทักษะหลัก",
                "color": "#73e5c1",
            }
        ],
        "skills": skills,
        "edges": edges,
        "progress": {"completedSkillIds": [], "updatedAt": None},
    }


# =========================================================
# Display-field derivation (not stored in the database)
# =========================================================

# X coordinates match the roadmap's fixed beginner/intermediate/advanced
# columns so the existing zone background stays aligned with the nodes.
X_COLUMNS = [110, 285, 470, 650, 825, 1010]


def _initials(title: str) -> str:
    words = [
        word
        for word in title.replace("/", " ").split()
        if word and word[0].isalnum()
    ]
    if not words:
        return "SM"
    first = words[0][0].upper()
    if len(words) > 1:
        second = words[1][0].upper()
    elif len(words[0]) > 1:
        second = words[0][1].upper()
    else:
        second = first
    return first + second


def _short_name(title: str) -> str:
    if len(title) <= 20:
        return title
    words = title.split()
    short = " ".join(words[:2])
    return short if short and len(short) <= 20 else title[:19] + "…"


def _level_for_depth(depth: int) -> str:
    if depth <= 1:
        return "beginner"
    if depth <= 3:
        return "intermediate"
    return "advanced"


def _layout(
    node_rows: list[tuple[Any, ...]],
    prereqs_map: dict[int, list[int]],
) -> tuple[dict[int, dict[str, int]], dict[int, int]]:
    """Compute DAG depth and node positions (x by depth, y by step order)."""
    depths: dict[int, int] = {}

    def depth_of(node_id: int) -> int:
        if node_id in depths:
            return depths[node_id]
        prereqs = prereqs_map.get(node_id, [])
        if not prereqs:
            depths[node_id] = 0
        else:
            depths[node_id] = 1 + max(depth_of(item) for item in prereqs)
        return depths[node_id]

    columns: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for row in node_rows:
        columns[depth_of(row[0])].append(row)

    positions: dict[int, dict[str, int]] = {}
    for column_depth in sorted(columns):
        rows = columns[column_depth]
        rows.sort(key=lambda row: (row[4] or 0, row[0]))  # step_order
        count = len(rows)
        spacing = min(120, 460 // max(count - 1, 1)) if count > 1 else 0
        x = X_COLUMNS[min(column_depth, len(X_COLUMNS) - 1)]
        for index, row in enumerate(rows):
            positions[row[0]] = {"x": x, "y": 105 + index * spacing}

    return positions, depths


# =========================================================
# Learner progress (user_node_progress per schema)
# =========================================================


def load_completed_node_ids(conn, user_id: int) -> set[str]:
    """Return node ids the user marked completed, as strings."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT node_id FROM user_node_progress
            WHERE user_id = %s AND status = 'completed'
            """,
            (user_id,),
        )
        return {str(row[0]) for row in cur.fetchall()}


def save_completed(
    conn, user_id: int, node_id: int, completed: bool
) -> None:
    """Mark a node completed, or remove the completion record."""
    with conn.cursor() as cur:
        if completed:
            cur.execute(
                """
                INSERT INTO user_node_progress (user_id, node_id, status, completed_at)
                VALUES (%s, %s, 'completed', NOW())
                ON CONFLICT (user_id, node_id)
                DO UPDATE SET status = 'completed', completed_at = NOW()
                """,
                (user_id, node_id),
            )
        else:
            cur.execute(
                """
                DELETE FROM user_node_progress
                WHERE user_id = %s AND node_id = %s
                """,
                (user_id, node_id),
            )


def delete_completed_many(conn, user_id: int, node_ids: list[int]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM user_node_progress
            WHERE user_id = %s AND node_id = ANY(%s)
            """,
            (user_id, node_ids),
        )


def reset_progress(conn, user_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_node_progress WHERE user_id = %s",
            (user_id,),
        )
