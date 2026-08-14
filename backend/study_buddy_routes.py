"""Flask Blueprint for the additive Study Buddy and friend system."""

from __future__ import annotations

from typing import Any, Callable

import psycopg2
from flask import Blueprint, jsonify, redirect, render_template, request, session

from backend.json_store import JsonStore
from backend.graph_engine import GraphEngine, GraphValidationError
from backend import study_buddy_store as social_store
from backend.study_buddy_service import (
    build_buddy_match,
    build_path_snapshot,
    list_shareable_skills,
    require_shareable_skill,
)


def create_study_buddy_blueprint(
    get_db: Callable,
    database_path: str,
    ensure_user_tables: Callable,
) -> Blueprint:
    """Create the Blueprint while reusing the original app's DB connector."""

    blueprint = Blueprint("study_buddy", __name__)
    graph_store = JsonStore(database_path)

    def success(data: Any = None, message: str | None = None, status: int = 200):
        payload: dict[str, Any] = {"ok": True}
        if data is not None:
            payload["data"] = data
        if message is not None:
            payload["message"] = message
        return jsonify(payload), status

    def error(message: str, status: int = 400, details: Any = None):
        payload: dict[str, Any] = {"ok": False, "error": message}
        if details is not None:
            payload["details"] = details
        return jsonify(payload), status

    def current_user_id() -> int | None:
        user_id = session.get("user_id")
        return user_id if isinstance(user_id, int) else None

    def require_user_id() -> int:
        user_id = current_user_id()
        if user_id is None:
            raise PermissionError("Login required")
        return user_id

    def ensure_tables(conn) -> None:
        ensure_user_tables(conn)
        social_store.ensure_social_schema(conn)

    def load_completed(conn, user_id: int, engine: GraphEngine) -> set[str]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT skill_id FROM user_skill_progress WHERE user_id = %s",
                (user_id,),
            )
            return engine.clean_completed(row[0] for row in cur.fetchall())

    def load_user_graph(conn, user_id: int):
        database = graph_store.read()
        engine = GraphEngine(database)
        career_id = str(engine.career["id"])
        completed = load_completed(conn, user_id, engine)
        return career_id, engine, completed

    def enrich_group(group: dict[str, Any], engine: GraphEngine):
        group["careerName"] = engine.career["name"]
        focus = engine.skill_by_id.get(group["focusNodeId"])
        group["focusSkillName"] = (
            focus.get("thaiName") or focus["name"] if focus else ""
        )
        return group

    def parse_json_object() -> dict[str, Any]:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("Request body must be JSON")
        return body

    @blueprint.get("/study-buddy")
    def study_buddy_page():
        if current_user_id() is None:
            return redirect("/login")
        return render_template("study-buddy.html")

    @blueprint.get("/api/social/dashboard")
    def dashboard():
        try:
            user_id = require_user_id()
            conn = get_db()
            try:
                ensure_tables(conn)
                career_id, engine, completed = load_user_graph(conn, user_id)
                me = social_store.get_person(conn, user_id)
                friends = social_store.list_friends(conn, user_id)
                me["currentCareerId"] = career_id
                me["careerName"] = engine.career["name"]
                matches = []
                for friend in friends:
                    friend["currentCareerId"] = career_id
                    friend["careerName"] = engine.career["name"]
                    friend_completed = load_completed(conn, friend["id"], engine)
                    matches.append(
                        build_buddy_match(
                            engine, completed, friend_completed, friend
                        )
                    )
                matches.sort(
                    key=lambda item: (
                        -item["matchScore"], item["displayName"].lower()
                    )
                )
                groups = social_store.list_study_groups(conn, user_id)
                for group in groups:
                    enrich_group(group, engine)
                joinable_groups = social_store.list_joinable_study_groups(
                    conn, user_id
                )
                for group in joinable_groups:
                    enrich_group(group, engine)
                payload = {
                    "me": me,
                    "career": engine.career,
                    "friends": friends,
                    "incomingRequests": social_store.list_incoming_requests(
                        conn, user_id
                    ),
                    "matches": matches,
                    "shareableSkills": list_shareable_skills(
                        engine, completed
                    ),
                    "notifications": social_store.list_notifications(
                        conn, user_id
                    ),
                    "pathShares": social_store.list_received_path_shares(
                        conn, user_id
                    ),
                    "groups": groups,
                    "joinableGroups": joinable_groups,
                }
                conn.commit()
                return success(payload)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 401)
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not load Study Buddy dashboard", 500, str(exc))

    @blueprint.get("/api/social/people")
    def search_people():
        try:
            user_id = require_user_id()
            query = (request.args.get("q") or "").strip()
            if len(query) < 2:
                return error("Enter at least 2 characters")
            conn = get_db()
            try:
                ensure_tables(conn)
                people = social_store.search_people(conn, user_id, query)
                conn.commit()
                return success(people)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 401)
        except psycopg2.Error as exc:
            return error("Could not search learners", 500, str(exc))

    @blueprint.post("/api/social/friend-requests")
    def create_friend_request():
        try:
            user_id = require_user_id()
            body = parse_json_object()
            friend_uid = body.get("uid")
            if not isinstance(friend_uid, str) or not friend_uid.strip():
                return error("uid is required")
            conn = get_db()
            try:
                ensure_tables(conn)
                result = social_store.send_friend_request(
                    conn, user_id, friend_uid.strip()
                )
                actor = social_store.get_person(conn, user_id)
                social_store.create_notification(
                    conn,
                    result["friendUserId"],
                    user_id,
                    "friend_request",
                    "คำขอเป็นเพื่อนใหม่",
                    f"{actor['displayName']} อยากเป็นเพื่อนกับคุณ",
                    {"requestId": result["requestId"]},
                )
                conn.commit()
                return success(result, "ส่งคำขอเป็นเพื่อนแล้ว", 201)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except ValueError as exc:
            return error(str(exc), 409)
        except psycopg2.Error as exc:
            return error("Could not send friend request", 500, str(exc))

    @blueprint.post("/api/social/friend-requests/<int:request_id>/response")
    def respond_friend_request(request_id: int):
        try:
            user_id = require_user_id()
            body = parse_json_object()
            accept = body.get("accept")
            if not isinstance(accept, bool):
                return error("accept must be a boolean")
            conn = get_db()
            try:
                ensure_tables(conn)
                requester_id = social_store.respond_to_friend_request(
                    conn, user_id, request_id, accept
                )
                if accept:
                    actor = social_store.get_person(conn, user_id)
                    social_store.create_notification(
                        conn,
                        requester_id,
                        user_id,
                        "friend_accepted",
                        "คำขอเป็นเพื่อนได้รับการตอบรับ",
                        f"{actor['displayName']} เป็นเพื่อนกับคุณแล้ว",
                    )
                conn.commit()
                message = "รับคำขอเป็นเพื่อนแล้ว" if accept else "ปฏิเสธคำขอเป็นเพื่อนแล้ว"
                return success({"accepted": accept}, message)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except ValueError as exc:
            return error(str(exc))
        except psycopg2.Error as exc:
            return error("Could not update friend request", 500, str(exc))

    @blueprint.post("/api/social/activity")
    def share_activity():
        try:
            user_id = require_user_id()
            body = parse_json_object()
            skill_id = str(body.get("skillId") or "").strip()
            if not skill_id:
                return error("skillId is required")
            conn = get_db()
            try:
                ensure_tables(conn)
                career_id, engine, completed = load_user_graph(conn, user_id)
                skill = require_shareable_skill(
                    engine, completed, skill_id
                )
                actor = social_store.get_person(conn, user_id)
                recipients = social_store.accepted_friend_ids(conn, user_id)
                sent = social_store.notify_many(
                    conn,
                    recipients,
                    user_id,
                    "study_activity",
                    f"{actor['displayName']} กำลังเรียนอยู่",
                    f"กำลังเรียน {skill['thaiName']}",
                    {
                        "careerId": career_id,
                        "skillId": skill["id"],
                        "skillName": skill["name"],
                        "status": skill["status"],
                    },
                )
                conn.commit()
                return success(
                    {"recipientCount": sent, "skill": skill},
                    f"แชร์ให้เพื่อน {sent} คนแล้ว",
                )
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 409 if current_user_id() else 401)
        except KeyError:
            return error("Skill not found in your current career", 404)
        except ValueError as exc:
            return error(str(exc))
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not share study activity", 500, str(exc))

    @blueprint.post("/api/social/path-shares")
    def share_path():
        try:
            user_id = require_user_id()
            body = parse_json_object()
            try:
                friend_user_id = int(body.get("friendUserId"))
            except (TypeError, ValueError):
                return error("friendUserId must be an integer")
            message = body.get("message") or ""
            if not isinstance(message, str) or len(message) > 300:
                return error("message must contain at most 300 characters")
            conn = get_db()
            try:
                ensure_tables(conn)
                if friend_user_id not in social_store.accepted_friend_ids(
                    conn, user_id
                ):
                    raise PermissionError("Paths can be shared with friends only")
                career_id, engine, completed = load_user_graph(conn, user_id)
                snapshot = build_path_snapshot(engine, completed)
                share_id = social_store.create_path_share(
                    conn,
                    user_id,
                    friend_user_id,
                    career_id,
                    message.strip(),
                    snapshot,
                )
                actor = social_store.get_person(conn, user_id)
                social_store.create_notification(
                    conn,
                    friend_user_id,
                    user_id,
                    "path_shared",
                    "เพื่อนแชร์เส้นทางการเรียน",
                    f"{actor['displayName']} แชร์ Skill Tree กับคุณ",
                    {"shareId": share_id, "careerId": career_id},
                )
                conn.commit()
                return success(
                    {"shareId": share_id, "snapshotSource": "graph_engine"},
                    "แชร์เส้นทางการเรียนแล้ว",
                    201,
                )
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except ValueError as exc:
            return error(str(exc))
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not share learning path", 500, str(exc))

    @blueprint.post("/api/social/study-groups")
    def create_group():
        try:
            user_id = require_user_id()
            body = parse_json_object()
            name = body.get("name")
            skill_id = str(body.get("focusSkillId") or "").strip()
            member_ids = body.get("memberUserIds", [])
            if not isinstance(name, str) or not (3 <= len(name.strip()) <= 100):
                return error("name must contain 3-100 characters")
            if not skill_id:
                return error("focusSkillId is required")
            if not isinstance(member_ids, list):
                return error("memberUserIds must be an array")
            try:
                members = {int(item) for item in member_ids}
            except (TypeError, ValueError):
                return error("Every memberUserId must be an integer")
            if not members:
                return error("Select at least one friend for the study group")
            if len(members) > 10:
                return error("A study group can include at most 10 friends")

            conn = get_db()
            try:
                ensure_tables(conn)
                accepted = social_store.accepted_friend_ids(conn, user_id)
                if not members.issubset(accepted):
                    raise PermissionError(
                        "Study groups can include accepted friends only"
                    )
                career_id, engine, completed = load_user_graph(conn, user_id)
                skill = require_shareable_skill(
                    engine, completed, skill_id
                )
                group_id = social_store.create_study_group(
                    conn,
                    user_id,
                    name.strip(),
                    career_id,
                    skill_id,
                    members,
                )
                actor = social_store.get_person(conn, user_id)
                social_store.notify_many(
                    conn,
                    members,
                    user_id,
                    "group_invite",
                    "คุณถูกเพิ่มเข้ากลุ่มติว",
                    f"{actor['displayName']} ชวนเรียน {skill['thaiName']}",
                    {"groupId": group_id, "skillId": skill_id},
                )
                conn.commit()
                return success(
                    {"groupId": group_id, "focusSkill": skill},
                    "สร้างกลุ่มติวแล้ว",
                    201,
                )
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except KeyError:
            return error("Skill not found in your current career", 404)
        except ValueError as exc:
            return error(str(exc))
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not create study group", 500, str(exc))

    @blueprint.post("/api/social/study-groups/<int:group_id>/join")
    def join_group(group_id: int):
        try:
            user_id = require_user_id()
            conn = get_db()
            try:
                ensure_tables(conn)
                group = social_store.get_study_group(conn, group_id)
                if not group:
                    raise KeyError("Study group not found")
                if social_store.is_group_member(conn, group_id, user_id):
                    raise ValueError("You are already a member of this group")
                if group["ownerUserId"] not in social_store.accepted_friend_ids(
                    conn, user_id
                ):
                    raise PermissionError(
                        "You can join study groups owned by accepted friends only"
                    )

                career_id, engine, _ = load_user_graph(conn, user_id)
                if group["careerId"] and group["careerId"] != career_id:
                    raise PermissionError(
                        "This study group belongs to a different learning path"
                    )
                if not social_store.join_study_group(conn, group_id, user_id):
                    raise ValueError("You are already a member of this group")

                actor = social_store.get_person(conn, user_id)
                social_store.create_notification(
                    conn,
                    group["ownerUserId"],
                    user_id,
                    "group_joined",
                    "มีสมาชิกใหม่เข้ากลุ่มติว",
                    f"{actor['displayName']} เข้าร่วม {group['name']}",
                    {"groupId": group_id},
                )
                group["memberCount"] += 1
                enrich_group(group, engine)
                conn.commit()
                return success(group, "เข้าร่วมกลุ่มติวแล้ว")
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except ValueError as exc:
            return error(str(exc), 409)
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not join study group", 500, str(exc))

    @blueprint.post("/api/social/study-groups/<int:group_id>/leave")
    def leave_group(group_id: int):
        try:
            user_id = require_user_id()
            conn = get_db()
            try:
                ensure_tables(conn)
                group = social_store.get_study_group(conn, group_id)
                if not group:
                    raise KeyError("Study group not found")
                actor = social_store.get_person(conn, user_id)
                result = social_store.leave_study_group(
                    conn, group_id, user_id
                )

                new_owner_id = result["newOwnerUserId"]
                if new_owner_id is not None:
                    social_store.create_notification(
                        conn,
                        new_owner_id,
                        user_id,
                        "group_owner_transferred",
                        "คุณเป็นเจ้าของกลุ่มติวคนใหม่",
                        f"{actor['displayName']} โอน {group['name']} ให้คุณ",
                        {"groupId": group_id},
                    )
                elif (
                    not result["deletedGroup"]
                    and group["ownerUserId"] != user_id
                ):
                    social_store.create_notification(
                        conn,
                        group["ownerUserId"],
                        user_id,
                        "group_left",
                        "สมาชิกออกจากกลุ่มติว",
                        f"{actor['displayName']} ออกจาก {group['name']}",
                        {"groupId": group_id},
                    )
                conn.commit()
                message = (
                    "ออกจากกลุ่มและปิดกลุ่มที่ไม่มีสมาชิกแล้ว"
                    if result["deletedGroup"]
                    else "ออกจากกลุ่มติวแล้ว"
                )
                return success(result, message)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except psycopg2.Error as exc:
            return error("Could not leave study group", 500, str(exc))

    @blueprint.get("/api/social/study-groups/<int:group_id>/messages")
    def group_messages(group_id: int):
        try:
            user_id = require_user_id()
            conn = get_db()
            try:
                ensure_tables(conn)
                if not social_store.is_group_member(conn, group_id, user_id):
                    raise PermissionError(
                        "Only group members can read this chat"
                    )
                group = social_store.get_study_group(conn, group_id)
                if not group:
                    raise KeyError("Study group not found")
                _, engine, _ = load_user_graph(conn, user_id)
                enrich_group(group, engine)
                messages = social_store.list_group_messages(
                    conn, group_id
                )
                conn.commit()
                return success({"group": group, "messages": messages})
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except (psycopg2.Error, GraphValidationError) as exc:
            return error("Could not load group chat", 500, str(exc))

    @blueprint.post("/api/social/study-groups/<int:group_id>/messages")
    def send_group_message(group_id: int):
        try:
            user_id = require_user_id()
            body = parse_json_object()
            content = body.get("content")
            if not isinstance(content, str) or not content.strip():
                return error("content is required")
            content = content.strip()
            if len(content) > 1000:
                return error("content must contain at most 1000 characters")

            conn = get_db()
            try:
                ensure_tables(conn)
                if not social_store.is_group_member(conn, group_id, user_id):
                    raise PermissionError(
                        "Only group members can send messages"
                    )
                group = social_store.get_study_group(conn, group_id)
                if not group:
                    raise KeyError("Study group not found")
                message = social_store.create_group_message(
                    conn, group_id, user_id, content
                )
                actor = social_store.get_person(conn, user_id)
                message["sender"] = {
                    "id": user_id,
                    "uid": actor["uid"],
                    "displayName": actor["displayName"],
                }
                recipients = social_store.list_group_member_ids(
                    conn, group_id
                ) - {user_id}
                social_store.notify_many(
                    conn,
                    recipients,
                    user_id,
                    "group_message",
                    f"ข้อความใหม่ใน {group['name']}",
                    content[:120],
                    {"groupId": group_id, "messageId": message["id"]},
                )
                conn.commit()
                return success(message, "ส่งข้อความแล้ว", 201)
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 403 if current_user_id() else 401)
        except KeyError as exc:
            return error(str(exc), 404)
        except ValueError as exc:
            return error(str(exc))
        except psycopg2.Error as exc:
            return error("Could not send group message", 500, str(exc))

    @blueprint.post("/api/social/notifications/<int:notification_id>/read")
    def read_notification(notification_id: int):
        try:
            user_id = require_user_id()
            conn = get_db()
            try:
                ensure_tables(conn)
                updated = social_store.mark_notification_read(
                    conn, user_id, notification_id
                )
                if not updated:
                    conn.rollback()
                    return error("Notification not found", 404)
                conn.commit()
                return success({"notificationId": notification_id})
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except PermissionError as exc:
            return error(str(exc), 401)
        except psycopg2.Error as exc:
            return error("Could not update notification", 500, str(exc))

    return blueprint
