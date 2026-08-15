"""PostgreSQL-backed storage for the Skill Graph.

The connected database described in ``database_schema_description.txt`` is the
single source of truth for:

- ``careers`` / ``nodes`` / ``career_nodes`` / ``node_prerequisites``
  (the skill graph structure)
- ``users`` / ``user_profiles`` / ``user_node_progress``
  (authentication and learner progress)
- Social module (friendships, study groups, notifications, path shares)
- World chat & meme modules (world_chat_messages, meme_questions,
  user_meme_answers, study_frequency_memes, subject_memes)

The catalog data (careers, nodes, subjects, prerequisites, achievements,
ranks) lives in the database.  Only purely presentational fields that the
roadmap UI needs (node position, level, difficulty, weight, estimated hours,
short label) are derived deterministically from stored data so the frontend
contract stays unchanged and the database stays the single source of truth.

All DDL is consolidated here in ``SCHEMA_STATEMENTS`` so ``ensure_schema()``
creates every table the app needs (including the social tables that used to
live in ``study_buddy_store.SOCIAL_SCHEMA_STATEMENTS``) on a fresh database.
"""

from __future__ import annotations

import json
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
        exp_reward INTEGER NOT NULL DEFAULT 100,
        subject_id BIGINT,
        thai_title VARCHAR(150),
        career_relevance INTEGER NOT NULL DEFAULT 3,
        techniques TEXT NOT NULL DEFAULT '[]',
        learning_outcomes TEXT NOT NULL DEFAULT '[]',
        real_world TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subjects (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        thai_name VARCHAR(150),
        color VARCHAR(20)
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
        favorite_animal VARCHAR(80),
        favorite_color VARCHAR(80),
        favorite_season VARCHAR(80),
        profile_prompt TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        profile_picture BYTEA
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
    """
    CREATE TABLE IF NOT EXISTS user_career_node_progress (
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        career_id BIGINT NOT NULL REFERENCES careers(id) ON DELETE CASCADE,
        node_id BIGINT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        completed_at TIMESTAMPTZ,
        PRIMARY KEY (user_id, career_id, node_id)
    )
    """,
    # ---- Achievements & Certificates module ----
    """
    CREATE TABLE IF NOT EXISTS achievements (
        id BIGSERIAL PRIMARY KEY,
        title VARCHAR(100) NOT NULL,
        description TEXT,
        icon_url VARCHAR(512),
        condition TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_achievements (
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        achievement_id BIGINT NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
        unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, achievement_id)
    )
    """,
    # ---- Social module (achievement conditions read these) ----
    """
    CREATE TABLE IF NOT EXISTS friendships (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        friend_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, friend_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS study_sessions (
        id BIGSERIAL PRIMARY KEY,
        host_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        node_id BIGINT REFERENCES nodes(id) ON DELETE SET NULL,
        title VARCHAR(150) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ranks (
        id BIGSERIAL PRIMARY KEY,
        code VARCHAR(10) NOT NULL,
        name VARCHAR(50) NOT NULL,
        hint VARCHAR(200),
        min_progress INTEGER NOT NULL DEFAULT 0
    )
    """,
    # ---- Social module (friends, study groups, notifications, path shares) ----
    """
    CREATE TABLE IF NOT EXISTS study_groups (
        id BIGSERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        career_id TEXT,
        focus_node_id TEXT,
        graph_career_id TEXT,
        graph_focus_skill_id TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS study_group_members (
        group_id BIGINT NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role VARCHAR(20) NOT NULL DEFAULT 'member',
        joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (group_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS study_group_messages (
        id BIGSERIAL PRIMARY KEY,
        group_id BIGINT NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
        sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS buddy_notifications (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind VARCHAR(40) NOT NULL,
        title VARCHAR(150) NOT NULL,
        body TEXT NOT NULL,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        read_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS study_path_shares (
        id BIGSERIAL PRIMARY KEY,
        sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        receiver_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        career_id TEXT,
        graph_career_id TEXT,
        message TEXT,
        snapshot JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # ---- World chat & meme modules (new) ----
    """
    CREATE TABLE IF NOT EXISTS world_chat_messages (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meme_questions (
        id BIGSERIAL PRIMARY KEY,
        question_text TEXT NOT NULL,
        question_order INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_meme_answers (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        question_id BIGINT NOT NULL REFERENCES meme_questions(id) ON DELETE CASCADE,
        answer TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS study_frequency_memes (
        id BIGSERIAL PRIMARY KEY,
        title VARCHAR(150),
        description TEXT,
        image BYTEA,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subject_memes (
        id BIGSERIAL PRIMARY KEY,
        title VARCHAR(150),
        description TEXT,
        image BYTEA,
        subject_id BIGINT REFERENCES subjects(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # Migrations for databases created before these columns existed.
    """
    ALTER TABLE achievements ADD COLUMN IF NOT EXISTS condition TEXT
    """,
    """
    ALTER TABLE achievements ADD COLUMN IF NOT EXISTS category VARCHAR(40)
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS subject_id BIGINT
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS thai_title VARCHAR(150)
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS career_relevance INTEGER NOT NULL DEFAULT 3
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS techniques TEXT NOT NULL DEFAULT '[]'
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS learning_outcomes TEXT NOT NULL DEFAULT '[]'
    """,
    """
    ALTER TABLE nodes ADD COLUMN IF NOT EXISTS real_world TEXT NOT NULL DEFAULT '[]'
    """,
    """
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS favorite_animal VARCHAR(80)
    """,
    """
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS favorite_color VARCHAR(80)
    """,
    """
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS favorite_season VARCHAR(80)
    """,
    """
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS profile_prompt TEXT
    """,
    """
    ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS profile_picture BYTEA
    """,
    """
    ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS graph_career_id TEXT
    """,
    """
    ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS graph_focus_skill_id TEXT
    """,
    """
    ALTER TABLE study_path_shares ADD COLUMN IF NOT EXISTS graph_career_id TEXT
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_buddy_notifications_user_created
    ON buddy_notifications (user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_study_path_shares_receiver_created
    ON study_path_shares (receiver_user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_study_group_messages_group_created
    ON study_group_messages (group_id, created_at DESC)
    """,
]


# =========================================================
# Achievements (catalog seed)
# =========================================================

# ``condition`` is a JSON rule evaluated against user data so the unlock
# logic stays machine-readable while the catalog itself lives in the DB.
# Unlock data sources: completed skill count (user_node_progress), EXP
# (user_profiles.current_exp), friends (friendships), study rooms
# (study_sessions).  Social features are not built yet, so those two
# achievements stay locked until the features exist.
ACHIEVEMENT_SEEDS: list[tuple[int, str, str, str, str]] = [
    (
        1,
        "First Step",
        "เรียนจบวิชาแรกบน Skill Tree",
        "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        '{"type": "completed_skills", "target": 1}',
    ),
    (
        2,
        "Code Novice",
        "สะสม EXP ครบ 500 แต้ม",
        "https://cdn-icons-png.flaticon.com/512/190/190411.png",
        '{"type": "exp", "target": 500}',
    ),
    (
        3,
        "Social Butterfly",
        "มีเพื่อนในระบบครบ 3 คน",
        "https://cdn-icons-png.flaticon.com/512/1256/1256650.png",
        '{"type": "friends", "target": 3}',
    ),
    (
        4,
        "Study Buddy Host",
        "สร้างห้องติวครั้งแรก",
        "https://cdn-icons-png.flaticon.com/512/3820/3820107.png",
        '{"type": "study_sessions", "target": 1}',
    ),
]

# One shared achievement catalog.  The progress is evaluated against the
# selected career only, so the same learner can be Noob in one track and
# Hacker in another without creating a separate catalog per career.
CAREER_ACHIEVEMENT_SEEDS: list[tuple[int, str, str, str, str]] = [
    (101, "Join", "Start this career path", "/pignopic/join.png", '{"type":"career_progress","target":0}'),
    (102, "Noob", "Reach 25% progress in this career", "/pignopic/noob.png", '{"type":"career_progress","target":25}'),
    (103, "Pro", "Reach 50% progress in this career", "/pignopic/pro.png", '{"type":"career_progress","target":50}'),
    (104, "Hacker", "Reach 75% progress in this career", "/pignopic/hacker.png", '{"type":"career_progress","target":75}'),
    (105, "God", "Complete 100% of this career", "", '{"type":"career_progress","target":100}'),
]


def seed_achievements(conn) -> None:
    """Insert the achievement catalog (idempotent).

    Existing rows keep their title/description/icon; only an empty
    ``condition`` is filled in so admin edits are not overwritten.
    """
    with conn.cursor() as cur:
        for achievement_id, title, description, icon_url, condition in ACHIEVEMENT_SEEDS:
            cur.execute(
                """
                INSERT INTO achievements (id, title, description, icon_url, condition)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    condition = COALESCE(achievements.condition, EXCLUDED.condition)
                """,
                (achievement_id, title, description, icon_url, condition),
            )
        for achievement_id, title, description, icon_url, condition in CAREER_ACHIEVEMENT_SEEDS:
            cur.execute(
                """
                INSERT INTO achievements (id, title, description, icon_url, condition, category)
                VALUES (%s, %s, %s, %s, %s, 'career_progress')
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title, description = EXCLUDED.description,
                    icon_url = EXCLUDED.icon_url, condition = EXCLUDED.condition,
                    category = EXCLUDED.category
                """,
                (achievement_id, title, description, icon_url, condition),
            )


# =========================================================
# Subjects & ranks (catalog seeds)
# =========================================================

# The first subject matches what the prototype used to hardcode as "core";
# every existing node is backfilled onto it so behavior stays unchanged.
SUBJECT_SEEDS: list[tuple[int, str, str, str]] = [
    (1, "Core Skills", "ทักษะหลัก", "#73e5c1"),
]

RANK_SEEDS: list[tuple[int, str, str, str, int]] = [
    (1, "01", "Starter", "เริ่มเรียน Skill แรกเพื่อพัฒนา Rank", 0),
    (2, "02", "Core Learner", "มีพื้นฐานและเริ่มเรียนวิชาหลัก", 25),
    (3, "03", "System Builder", "กำลังเชื่อมฮาร์ดแวร์และซอฟต์แวร์", 50),
    (4, "04", "Career Ready", "พร้อมต่อยอดสู่โปรเจกต์จริง", 75),
    (5, "05", "Career Master", "เรียนครบทุกวิชาในเส้นทาง", 100),
]


def seed_subjects_and_nodes(conn) -> None:
    """Insert the subject catalog and backfill nodes onto it (idempotent)."""
    with conn.cursor() as cur:
        for subject_id, name, thai_name, color in SUBJECT_SEEDS:
            cur.execute(
                """
                INSERT INTO subjects (id, name, thai_name, color)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (subject_id, name, thai_name, color),
            )
        # Backfill display fields so every existing node behaves like the
        # prototype default (subject "core", Thai name = English title).
        cur.execute(
            """
            UPDATE nodes
            SET subject_id = (
                SELECT id FROM subjects ORDER BY id LIMIT 1
            )
            WHERE subject_id IS NULL
            """
        )
        cur.execute("UPDATE nodes SET thai_title = title WHERE thai_title IS NULL")


def seed_ranks(conn) -> None:
    """Insert or refresh the rank catalog (idempotent)."""
    with conn.cursor() as cur:
        for rank_id, code, name, hint, min_progress in RANK_SEEDS:
            cur.execute(
                """
                INSERT INTO ranks (id, code, name, hint, min_progress)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    name = EXCLUDED.name,
                    hint = EXCLUDED.hint,
                    min_progress = EXCLUDED.min_progress
                """,
                (rank_id, code, name, hint, min_progress),
            )


# =========================================================
# Meme questions (catalog seed)
# =========================================================

MEME_QUESTION_SEEDS: list[tuple[int, str, int]] = [
    (1, "สัตว์ที่ชอบ", 1),
    (2, "สีที่ชอบ", 2),
    (3, "ฤดูที่ชอบ", 3),
]


def seed_meme_questions(conn) -> None:
    """Insert the meme question catalog (idempotent)."""
    with conn.cursor() as cur:
        for question_id, question_text, question_order in MEME_QUESTION_SEEDS:
            cur.execute(
                """
                INSERT INTO meme_questions (id, question_text, question_order)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    question_text = EXCLUDED.question_text,
                    question_order = EXCLUDED.question_order
                """,
                (question_id, question_text, question_order),
            )


def ensure_schema(conn) -> None:
    """Create every table used by the app (idempotent)."""
    with conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    seed_achievements(conn)
    with conn.cursor() as cur:
        # Legacy rows did not identify a career.  They can safely belong only
        # to the learner's current career, never to every career sharing a node.
        cur.execute(
            """
            INSERT INTO user_career_node_progress
                (user_id, career_id, node_id, status, completed_at)
            SELECT p.user_id, p.current_career_id, old.node_id, old.status, old.completed_at
            FROM user_node_progress old
            JOIN user_profiles p ON p.user_id = old.user_id
            WHERE p.current_career_id IS NOT NULL
            ON CONFLICT (user_id, career_id, node_id) DO NOTHING
            """
        )
        # The old table has no career dimension.  Leaving rows there would
        # re-import cleared progress on every request, so the migration is a
        # move, not a copy.
        cur.execute(
            """
            DELETE FROM user_node_progress old
            USING user_profiles p
            WHERE p.user_id = old.user_id AND p.current_career_id IS NOT NULL
            """
        )
    seed_subjects_and_nodes(conn)
    seed_ranks(conn)
    seed_meme_questions(conn)


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


def user_display_name(conn, user_id: int) -> str | None:
    """Return the learner-facing display name for the given user."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT display_name FROM user_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None


# =========================================================
# Graph loading (source of truth for GraphEngine)
# =========================================================


def _parse_json_list(value: Any) -> list[str]:
    """Parse a stored JSON array column into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


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
            "SELECT id, name, thai_name, color FROM subjects ORDER BY id"
        )
        subject_rows = cur.fetchall()
        if subject_rows:
            subjects = [
                {
                    "id": str(row[0]),
                    "name": row[1],
                    "thaiName": row[2] or row[1],
                    "color": row[3] or "#73e5c1",
                }
                for row in subject_rows
            ]
        else:
            # No subject rows (fresh database before seeding): fall back to
            # the same default the prototype used so the graph stays valid.
            subjects = [
                {
                    "id": "core",
                    "name": "Core Skills",
                    "thaiName": "ทักษะหลัก",
                    "color": "#73e5c1",
                }
            ]
        first_subject_id = subjects[0]["id"]

        cur.execute(
            """
            SELECT
                n.id,
                n.title,
                n.description,
                n.exp_reward,
                cn.step_order,
                cn.is_mandatory,
                n.subject_id,
                n.thai_title,
                n.career_relevance,
                n.techniques,
                n.learning_outcomes,
                n.real_world
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
        (
            node_id,
            title,
            description,
            exp_reward,
            _step,
            is_mandatory,
            subject_id,
            thai_title,
            career_relevance,
            techniques,
            learning_outcomes,
            real_world,
        ) = row
        depth = depths[node_id]
        level = _level_for_depth(depth)
        # Progress weight follows difficulty so harder skills move the
        # career bar more than easy ones (1 = beginner … 5 = expert).
        difficulty = min(5, depth + 1)
        skills.append(
            {
                "id": str(node_id),
                "name": title,
                "thaiName": thai_title or title,
                "shortName": _short_name(title),
                "subjectId": (
                    str(subject_id)
                    if subject_id is not None
                    else first_subject_id
                ),
                "level": level,
                "difficulty": difficulty,
                "weight": difficulty,
                "required": True if is_mandatory is None else bool(is_mandatory),
                "careerRelevance": (
                    career_relevance
                    if career_relevance is not None
                    else 3
                ),
                "estimatedHours": max(1, (exp_reward or 100) // 10),
                "expReward": exp_reward or 100,
                "position": positions[node_id],
                "description": description or "",
                "techniques": _parse_json_list(techniques),
                "learningOutcomes": _parse_json_list(learning_outcomes),
                "realWorld": _parse_json_list(real_world),
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
        "subjects": subjects,
        "skills": skills,
        "edges": edges,
        "progress": {"completedSkillIds": [], "updatedAt": None},
    }


# =========================================================
# Display-field derivation (computed, not stored in the database)
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


def load_completed_node_ids(conn, user_id: int, career_id: int) -> set[str]:
    """Return completed nodes for one learner in one career."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT node_id FROM user_career_node_progress
            WHERE user_id = %s AND career_id = %s AND status = 'completed'
            """,
            (user_id, career_id),
        )
        return {str(row[0]) for row in cur.fetchall()}


def save_completed(
    conn, user_id: int, career_id: int, node_id: int, completed: bool
) -> None:
    """Mark a node completed, or remove the completion record."""
    with conn.cursor() as cur:
        if completed:
            cur.execute(
                """
                INSERT INTO user_career_node_progress
                    (user_id, career_id, node_id, status, completed_at)
                VALUES (%s, %s, %s, 'completed', NOW())
                ON CONFLICT (user_id, career_id, node_id)
                DO UPDATE SET status = 'completed', completed_at = NOW()
                """,
                (user_id, career_id, node_id),
            )
        else:
            cur.execute(
                """
                DELETE FROM user_career_node_progress
                WHERE user_id = %s AND career_id = %s AND node_id = %s
                """,
                (user_id, career_id, node_id),
            )


def delete_completed_many(conn, user_id: int, career_id: int, node_ids: list[int]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM user_career_node_progress
            WHERE user_id = %s AND career_id = %s AND node_id = ANY(%s)
            """,
            (user_id, career_id, node_ids),
        )


def reset_progress(conn, user_id: int, career_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_career_node_progress WHERE user_id = %s AND career_id = %s",
            (user_id, career_id),
        )


# =========================================================
# Achievements (catalog + unlock state from the database)
# =========================================================


def load_achievements(conn) -> list[dict[str, Any]]:
    """Return the five shared, career-progress achievement definitions."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, description, icon_url, condition
            FROM achievements
            WHERE category = 'career_progress'
            ORDER BY id
            """
        )
        return [
            {
                "id": str(row[0]),
                "name": row[1],
                "description": row[2] or "",
                "iconUrl": row[3] or "",
                "condition": row[4],
            }
            for row in cur.fetchall()
        ]


def load_unlocked_achievement_ids(conn, user_id: int) -> set[int]:
    """Return achievement ids the user already unlocked."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT achievement_id FROM user_achievements WHERE user_id = %s",
            (user_id,),
        )
        return {row[0] for row in cur.fetchall()}


def save_unlocked_achievements(
    conn, user_id: int, achievement_ids: list[int]
) -> None:
    """Record newly unlocked achievements (never duplicated)."""
    with conn.cursor() as cur:
        for achievement_id in achievement_ids:
            cur.execute(
                """
                INSERT INTO user_achievements (user_id, achievement_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, achievement_id),
            )


def clear_user_achievements(conn, user_id: int) -> None:
    """Delete every unlocked record for a user (used on progress reset)."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM user_achievements WHERE user_id = %s",
            (user_id,),
        )


def load_user_stats(conn, user_id: int) -> dict[str, int]:
    """Load the user-global numbers achievement conditions are checked against.

    Friends and study-session features are not built yet, so both counts
    read 0 from the (documented) tables and those achievements stay locked
    until the social module lands.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(current_exp, 0) FROM user_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        exp = row[0] if row else 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM friendships
            WHERE status = 'accepted' AND (user_id = %s OR friend_id = %s)
            """,
            (user_id, user_id),
        )
        friends = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM study_sessions WHERE host_user_id = %s",
            (user_id,),
        )
        study_sessions = cur.fetchone()[0]

    return {"exp": exp, "friends": friends, "studySessions": study_sessions}


def evaluate_achievement_condition(
    condition_raw: str | None,
    completed_skill_ids: set[str],
    stats: dict[str, int],
) -> bool:
    """Decide whether one JSON condition is currently satisfied."""
    if not condition_raw:
        return False
    try:
        condition = json.loads(condition_raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(condition, dict):
        return False

    condition_type = condition.get("type")
    target = condition.get("target", 1)
    if not isinstance(target, int):
        return False

    if condition_type == "completed_skills":
        return len(completed_skill_ids) >= target
    if condition_type == "exp":
        return stats["exp"] >= target
    if condition_type == "friends":
        return stats["friends"] >= target
    if condition_type == "study_sessions":
        return stats["studySessions"] >= target
    return False


def build_achievements_payload(
    conn,
    user_id: int,
    completed_skill_ids: set[str],
    career_progress: int,
) -> list[dict[str, Any]]:
    """Build the shared five-level catalog for the selected career.

    Unlocks are intentionally not written to ``user_achievements``: this is
    a live view of career-scoped graph progress, not a user-global badge.
    """
    achievements = load_achievements(conn)
    payload: list[dict[str, Any]] = []
    for achievement in achievements:
        try:
            condition = json.loads(achievement["condition"] or "{}")
            target = int(condition["target"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            target = 101  # Invalid database data must never unlock a badge.
        unlocked = career_progress >= target
        payload.append(
            {
                "id": achievement["id"],
                "name": achievement["name"],
                "description": achievement["description"],
                "iconUrl": achievement["iconUrl"],
                "unlocked": unlocked,
                "target": target,
            }
        )
    return payload


# =========================================================
# EXP (user_profiles gamification)
# =========================================================


def add_exp(conn, user_id: int, amount: int) -> None:
    """Add (or subtract) EXP on the user's profile."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_profiles (user_id, display_name, current_exp)
            VALUES (%s, '', %s)
            ON CONFLICT (user_id) DO UPDATE SET
                current_exp = user_profiles.current_exp + EXCLUDED.current_exp,
                updated_at = NOW()
            """,
            (user_id, amount),
        )


# =========================================================
# Ranks (roadmap avatar, read from the database)
# =========================================================


def load_rank(conn, progress: int) -> dict[str, Any]:
    """Return the rank object whose threshold the progress percentage passes."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT code, name, hint
            FROM ranks
            WHERE min_progress <= %s
            ORDER BY min_progress DESC
            LIMIT 1
            """,
            (progress,),
        )
        row = cur.fetchone()
        if row is None:
            return {"code": "01", "name": "Starter", "hint": ""}
        return {"code": row[0], "name": row[1], "hint": row[2] or ""}
