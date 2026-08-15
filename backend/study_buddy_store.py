"""PostgreSQL storage for friends, sharing, notifications, and study groups.

Schema (DDL) for these tables lives in ``backend/db_store.SCHEMA_STATEMENTS``
so ``ensure_schema()`` creates the full database in one place.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from backend import db_store


def _person(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "uid": row[1],
        "displayName": row[2] or row[3].split("@", 1)[0],
        "level": row[4] or 1,
        "currentCareerId": row[5],
        "careerName": "",
        "profileImage": db_store.profile_image_data_url(row[6]),
    }


def get_person(conn, user_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.uid, p.display_name, u.email, p.level,
                   p.current_career_id, p.profile_picture
            FROM users u
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE u.id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return _person(row) if row else None


def search_people(
    conn,
    user_id: int,
    query: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    pattern = f"%{query.lower()}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id, u.uid, p.display_name, u.email, p.level,
                   p.current_career_id, p.profile_picture
            FROM users u
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE u.id <> %s
              AND (
                  LOWER(u.uid) LIKE %s
                  OR LOWER(COALESCE(p.display_name, '')) LIKE %s
              )
            ORDER BY
                CASE WHEN LOWER(u.uid) = %s THEN 0 ELSE 1 END,
                COALESCE(p.display_name, u.email)
            LIMIT %s
            """,
            (user_id, pattern, pattern, query.lower(), limit),
        )
        people = [_person(row) for row in cur.fetchall()]

        for person in people:
            person["friendshipStatus"] = friendship_status(
                conn, user_id, person["id"]
            )
    return people


def friendship_status(conn, user_id: int, other_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, friend_id, status
            FROM friendships
            WHERE (user_id = %s AND friend_id = %s)
               OR (user_id = %s AND friend_id = %s)
            ORDER BY CASE WHEN status = 'accepted' THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (user_id, other_id, other_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        return "none"
    if row[2] == "accepted":
        return "accepted"
    if row[2] == "blocked":
        return "blocked"
    return "outgoing_pending" if row[0] == user_id else "incoming_pending"


def send_friend_request(conn, user_id: int, friend_uid: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE LOWER(uid) = LOWER(%s)",
            (friend_uid,),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError("User UID not found")
        friend_id = row[0]
        if friend_id == user_id:
            raise ValueError("You cannot add yourself")

    status = friendship_status(conn, user_id, friend_id)
    if status != "none":
        raise ValueError(f"Friendship already exists ({status})")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO friendships (user_id, friend_id, status)
            VALUES (%s, %s, 'pending')
            RETURNING id
            """,
            (user_id, friend_id),
        )
        request_id = cur.fetchone()[0]
    return {"requestId": request_id, "friendUserId": friend_id}


def list_incoming_requests(conn, user_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id, u.id, u.uid, p.display_name, u.email,
                   p.profile_picture, f.created_at
            FROM friendships f
            JOIN users u ON u.id = f.user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE f.friend_id = %s AND f.status = 'pending'
            ORDER BY f.created_at DESC
            """,
            (user_id,),
        )
        return [
            {
                "requestId": row[0],
                "userId": row[1],
                "uid": row[2],
                "displayName": row[3] or row[4].split("@", 1)[0],
                "profileImage": db_store.profile_image_data_url(row[5]),
                "createdAt": row[6].isoformat(),
            }
            for row in cur.fetchall()
        ]


def respond_to_friend_request(
    conn,
    user_id: int,
    request_id: int,
    accept: bool,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id FROM friendships
            WHERE id = %s AND friend_id = %s AND status = 'pending'
            FOR UPDATE
            """,
            (request_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError("Friend request not found")
        requester_id = row[0]
        if accept:
            cur.execute(
                "UPDATE friendships SET status = 'accepted' WHERE id = %s",
                (request_id,),
            )
        else:
            cur.execute("DELETE FROM friendships WHERE id = %s", (request_id,))
    return requester_id


def list_friends(conn, user_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (u.id)
                   u.id, u.uid, p.display_name, u.email, p.level,
                   p.current_career_id, p.profile_picture
            FROM friendships f
            JOIN users u
              ON u.id = CASE
                  WHEN f.user_id = %s THEN f.friend_id ELSE f.user_id
              END
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE f.status = 'accepted'
              AND (f.user_id = %s OR f.friend_id = %s)
            ORDER BY u.id, f.created_at DESC
            """,
            (user_id, user_id, user_id),
        )
        return [_person(row) for row in cur.fetchall()]


def accepted_friend_ids(conn, user_id: int) -> set[int]:
    return {friend["id"] for friend in list_friends(conn, user_id)}


def create_notification(
    conn,
    user_id: int,
    actor_user_id: int,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO buddy_notifications
                (user_id, actor_user_id, kind, title, body, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                user_id,
                actor_user_id,
                kind,
                title,
                body,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        return cur.fetchone()[0]


def notify_many(
    conn,
    user_ids: Iterable[int],
    actor_user_id: int,
    kind: str,
    title: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> int:
    count = 0
    for user_id in set(user_ids):
        if user_id == actor_user_id:
            continue
        create_notification(
            conn,
            user_id,
            actor_user_id,
            kind,
            title,
            body,
            payload,
        )
        count += 1
    return count


def list_notifications(
    conn,
    user_id: int,
    limit: int = 30,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id, n.kind, n.title, n.body, n.payload, n.read_at,
                   n.created_at, u.uid, p.display_name, u.email,
                   p.profile_picture
            FROM buddy_notifications n
            JOIN users u ON u.id = n.actor_user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE n.user_id = %s
            ORDER BY n.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [
            {
                "id": row[0],
                "kind": row[1],
                "title": row[2],
                "body": row[3],
                "payload": row[4] or {},
                "read": row[5] is not None,
                "createdAt": row[6].isoformat(),
                "actor": {
                    "uid": row[7],
                    "displayName": row[8] or row[9].split("@", 1)[0],
                    "profileImage": db_store.profile_image_data_url(row[10]),
                },
            }
            for row in cur.fetchall()
        ]


def mark_notification_read(conn, user_id: int, notification_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE buddy_notifications
            SET read_at = COALESCE(read_at, NOW())
            WHERE id = %s AND user_id = %s
            """,
            (notification_id, user_id),
        )
        return cur.rowcount == 1


def create_path_share(
    conn,
    sender_user_id: int,
    receiver_user_id: int,
    career_id: str,
    message: str,
    snapshot: dict[str, Any],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO study_path_shares
                (sender_user_id, receiver_user_id, graph_career_id, message, snapshot)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                sender_user_id,
                receiver_user_id,
                career_id,
                message,
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        return cur.fetchone()[0]


def list_received_path_shares(
    conn,
    user_id: int,
    limit: int = 12,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, s.message, s.snapshot, s.created_at,
                   u.uid, p.display_name, u.email, p.profile_picture
            FROM study_path_shares s
            JOIN users u ON u.id = s.sender_user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE s.receiver_user_id = %s
            ORDER BY s.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [
            {
                "id": row[0],
                "message": row[1] or "",
                "snapshot": row[2],
                "createdAt": row[3].isoformat(),
                "sender": {
                    "uid": row[4],
                    "displayName": row[5] or row[6].split("@", 1)[0],
                    "profileImage": db_store.profile_image_data_url(row[7]),
                },
            }
            for row in cur.fetchall()
        ]


def create_study_group(
    conn,
    owner_user_id: int,
    name: str,
    career_id: str,
    focus_node_id: str,
    member_user_ids: Iterable[int],
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO study_groups
                (name, owner_user_id, graph_career_id, graph_focus_skill_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (name, owner_user_id, career_id, focus_node_id),
        )
        group_id = cur.fetchone()[0]
        members = {owner_user_id, *member_user_ids}
        for member_id in members:
            cur.execute(
                """
                INSERT INTO study_group_members (group_id, user_id, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (group_id, user_id) DO NOTHING
                """,
                (
                    group_id,
                    member_id,
                    "owner" if member_id == owner_user_id else "member",
                ),
            )
    return group_id


def list_study_groups(conn, user_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id, g.name, g.owner_user_id, g.graph_career_id,
                   g.graph_focus_skill_id, g.created_at,
                   COUNT(gm2.user_id)::int
            FROM study_group_members mine
            JOIN study_groups g ON g.id = mine.group_id
            LEFT JOIN study_group_members gm2 ON gm2.group_id = g.id
            WHERE mine.user_id = %s
            GROUP BY g.id
            ORDER BY g.created_at DESC
            """,
            (user_id,),
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "ownerUserId": row[2],
                "careerId": row[3],
                "careerName": "",
                "focusNodeId": str(row[4]) if row[4] is not None else None,
                "focusSkillName": "",
                "createdAt": row[5].isoformat(),
                "memberCount": row[6],
            }
            for row in cur.fetchall()
        ]


def get_study_group(conn, group_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id, g.name, g.owner_user_id, g.graph_career_id,
                   g.graph_focus_skill_id, g.created_at,
                   COUNT(gm.user_id)::int,
                   u.uid, p.display_name, u.email, p.profile_picture
            FROM study_groups g
            JOIN users u ON u.id = g.owner_user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            LEFT JOIN study_group_members gm ON gm.group_id = g.id
            WHERE g.id = %s
            GROUP BY g.id, u.uid, p.display_name, u.email, p.profile_picture
            """,
            (group_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "ownerUserId": row[2],
        "careerId": row[3],
        "careerName": "",
        "focusNodeId": str(row[4]) if row[4] is not None else None,
        "focusSkillName": "",
        "createdAt": row[5].isoformat(),
        "memberCount": row[6],
        "owner": {
            "uid": row[7],
            "displayName": row[8] or row[9].split("@", 1)[0],
            "profileImage": db_store.profile_image_data_url(row[10]),
        },
    }


def list_group_member_ids(conn, group_id: int) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT user_id FROM study_group_members WHERE group_id = %s",
            (group_id,),
        )
        return {row[0] for row in cur.fetchall()}


def is_group_member(conn, group_id: int, user_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM study_group_members
            WHERE group_id = %s AND user_id = %s
            """,
            (group_id, user_id),
        )
        return cur.fetchone() is not None


def list_joinable_study_groups(
    conn,
    user_id: int,
) -> list[dict[str, Any]]:
    """List groups owned by accepted friends that the learner has not joined."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT g.id, g.name, g.owner_user_id, g.graph_career_id,
                   g.graph_focus_skill_id, g.created_at,
                   COUNT(gm.user_id)::int,
                   u.uid, p.display_name, u.email, p.profile_picture
            FROM study_groups g
            JOIN users u ON u.id = g.owner_user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            LEFT JOIN study_group_members gm ON gm.group_id = g.id
            WHERE NOT EXISTS (
                SELECT 1 FROM study_group_members mine
                WHERE mine.group_id = g.id AND mine.user_id = %s
            )
              AND EXISTS (
                SELECT 1 FROM friendships f
                WHERE f.status = 'accepted'
                  AND (
                    (f.user_id = %s AND f.friend_id = g.owner_user_id)
                    OR
                    (f.friend_id = %s AND f.user_id = g.owner_user_id)
                  )
              )
            GROUP BY g.id, u.uid, p.display_name, u.email, p.profile_picture
            ORDER BY g.created_at DESC
            LIMIT 20
            """,
            (user_id, user_id, user_id),
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "ownerUserId": row[2],
                "careerId": row[3],
                "careerName": "",
                "focusNodeId": str(row[4]) if row[4] is not None else None,
                "focusSkillName": "",
                "createdAt": row[5].isoformat(),
                "memberCount": row[6],
                "owner": {
                    "uid": row[7],
                    "displayName": row[8] or row[9].split("@", 1)[0],
                    "profileImage": db_store.profile_image_data_url(row[10]),
                },
            }
            for row in cur.fetchall()
        ]


def join_study_group(conn, group_id: int, user_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO study_group_members (group_id, user_id, role)
            VALUES (%s, %s, 'member')
            ON CONFLICT (group_id, user_id) DO NOTHING
            RETURNING user_id
            """,
            (group_id, user_id),
        )
        return cur.fetchone() is not None


def leave_study_group(
    conn,
    group_id: int,
    user_id: int,
) -> dict[str, Any]:
    """Leave a group, transferring ownership or deleting an empty group."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT owner_user_id FROM study_groups
            WHERE id = %s
            FOR UPDATE
            """,
            (group_id,),
        )
        group_row = cur.fetchone()
        if not group_row:
            raise KeyError("Study group not found")

        cur.execute(
            """
            SELECT role FROM study_group_members
            WHERE group_id = %s AND user_id = %s
            FOR UPDATE
            """,
            (group_id, user_id),
        )
        if not cur.fetchone():
            raise PermissionError("You are not a member of this study group")

        owner_user_id = group_row[0]
        if owner_user_id != user_id:
            cur.execute(
                """
                DELETE FROM study_group_members
                WHERE group_id = %s AND user_id = %s
                """,
                (group_id, user_id),
            )
            return {"deletedGroup": False, "newOwnerUserId": None}

        cur.execute(
            """
            SELECT user_id FROM study_group_members
            WHERE group_id = %s AND user_id <> %s
            ORDER BY joined_at, user_id
            LIMIT 1
            """,
            (group_id, user_id),
        )
        next_owner = cur.fetchone()
        if not next_owner:
            cur.execute("DELETE FROM study_groups WHERE id = %s", (group_id,))
            return {"deletedGroup": True, "newOwnerUserId": None}

        new_owner_user_id = next_owner[0]
        cur.execute(
            "UPDATE study_groups SET owner_user_id = %s WHERE id = %s",
            (new_owner_user_id, group_id),
        )
        cur.execute(
            """
            UPDATE study_group_members SET role = 'owner'
            WHERE group_id = %s AND user_id = %s
            """,
            (group_id, new_owner_user_id),
        )
        cur.execute(
            """
            DELETE FROM study_group_members
            WHERE group_id = %s AND user_id = %s
            """,
            (group_id, user_id),
        )
        return {
            "deletedGroup": False,
            "newOwnerUserId": new_owner_user_id,
        }


def list_group_messages(
    conn,
    group_id: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.content, m.created_at,
                   u.id, u.uid, p.display_name, u.email, p.profile_picture
            FROM study_group_messages m
            JOIN users u ON u.id = m.sender_user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE m.group_id = %s
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT %s
            """,
            (group_id, limit),
        )
        rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "content": row[1],
            "createdAt": row[2].isoformat(),
            "sender": {
                "id": row[3],
                "uid": row[4],
                "displayName": row[5] or row[6].split("@", 1)[0],
                "profileImage": db_store.profile_image_data_url(row[7]),
            },
        }
        for row in reversed(rows)
    ]


def create_group_message(
    conn,
    group_id: int,
    sender_user_id: int,
    content: str,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO study_group_messages (group_id, sender_user_id, content)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (group_id, sender_user_id, content),
        )
        message_id, created_at = cur.fetchone()
    return {
        "id": message_id,
        "content": content,
        "createdAt": created_at.isoformat(),
    }


def list_world_chat_messages(
    conn,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return recent global messages with their current profile identity."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.content, m.created_at,
                   u.id, u.uid, p.display_name, u.email, p.profile_picture
            FROM world_chat_messages m
            JOIN users u ON u.id = m.user_id
            LEFT JOIN user_profiles p ON p.user_id = u.id
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "content": row[1],
            "createdAt": row[2].isoformat(),
            "sender": {
                "id": row[3],
                "uid": row[4],
                "displayName": row[5] or row[6].split("@", 1)[0],
                "profileImage": db_store.profile_image_data_url(row[7]),
            },
        }
        for row in reversed(rows)
    ]


def create_world_chat_message(
    conn,
    user_id: int,
    content: str,
) -> dict[str, Any]:
    """Persist one text-only Global Chat message."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO world_chat_messages (user_id, content)
            VALUES (%s, %s)
            RETURNING id, created_at
            """,
            (user_id, content),
        )
        message_id, created_at = cur.fetchone()
    return {
        "id": message_id,
        "content": content,
        "createdAt": created_at.isoformat(),
    }
