"""Graph-backed domain logic for Study Buddy features.

This module deliberately contains no prerequisite rules of its own.  Every
status, recommendation, and shared path is derived from ``GraphEngine`` so the
social feature cannot accidentally become a second source of truth.
"""

from __future__ import annotations

from typing import Any, Iterable

from backend.graph_engine import GraphEngine


def _skill_summary(
    engine: GraphEngine,
    skill_id: str,
    status: str | None = None,
) -> dict[str, Any]:
    skill = engine.skill_by_id[skill_id]
    result = {
        "id": skill_id,
        "name": skill["name"],
        "thaiName": skill.get("thaiName") or skill["name"],
        "subjectId": skill["subjectId"],
        "level": skill["level"],
    }
    if status is not None:
        result["status"] = status
    return result


def build_path_snapshot(
    engine: GraphEngine,
    completed_ids: Iterable[str],
) -> dict[str, Any]:
    """Create a safe, server-built snapshot for sharing with one friend."""

    completed = engine.clean_completed(completed_ids)
    statuses = engine.calculate_statuses(completed)
    recommendation = engine.recommend_next(completed)

    return {
        "source": "graph_engine",
        "schemaVersion": 1,
        "career": {
            "id": engine.career["id"],
            "name": engine.career["name"],
        },
        "progress": engine.calculate_progress(completed),
        "skills": [
            _skill_summary(engine, skill_id, statuses[skill_id])
            for skill_id in engine.topological_order
        ],
        "edges": [
            {"source": edge["source"], "target": edge["target"]}
            for edge in engine.edges
        ],
        "completedSkills": [
            _skill_summary(engine, skill_id, "completed")
            for skill_id in engine.topological_order
            if statuses[skill_id] == "completed"
        ],
        "availableSkills": [
            _skill_summary(engine, skill_id, "available")
            for skill_id in engine.topological_order
            if statuses[skill_id] == "available"
        ],
        "recommendedSkill": (
            _skill_summary(engine, recommendation["skillId"], "available")
            if recommendation
            else None
        ),
    }


def build_buddy_match(
    engine: GraphEngine,
    my_completed_ids: Iterable[str],
    buddy_completed_ids: Iterable[str],
    buddy: dict[str, Any],
) -> dict[str, Any]:
    """Compare two learners on the same DB-backed career graph.

    A useful buddy either studies the same currently available skill or has
    already completed something the learner can study next.  The score is a
    transparent heuristic; it never changes graph relationships.
    """

    mine = engine.clean_completed(my_completed_ids)
    theirs = engine.clean_completed(buddy_completed_ids)
    my_statuses = engine.calculate_statuses(mine)
    buddy_statuses = engine.calculate_statuses(theirs)

    shared_available = [
        skill_id
        for skill_id in engine.topological_order
        if my_statuses[skill_id] == "available"
        and buddy_statuses[skill_id] == "available"
    ]
    buddy_can_help = [
        skill_id
        for skill_id in engine.topological_order
        if my_statuses[skill_id] == "available" and skill_id in theirs
    ]
    learner_can_help = [
        skill_id
        for skill_id in engine.topological_order
        if buddy_statuses[skill_id] == "available" and skill_id in mine
    ]

    score = min(
        100,
        40
        + min(30, len(shared_available) * 10)
        + min(20, len(buddy_can_help) * 7)
        + min(10, len(learner_can_help) * 5),
    )

    return {
        **buddy,
        "matchScore": score,
        "matchSource": "graph_engine",
        "sharedAvailableSkills": [
            _skill_summary(engine, skill_id, "available")
            for skill_id in shared_available[:4]
        ],
        "buddyCanHelpWith": [
            _skill_summary(engine, skill_id, "completed")
            for skill_id in buddy_can_help[:4]
        ],
        "youCanHelpWith": [
            _skill_summary(engine, skill_id, "completed")
            for skill_id in learner_can_help[:4]
        ],
    }


def list_shareable_skills(
    engine: GraphEngine,
    completed_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Return only skills that GraphEngine marks available or completed."""

    statuses = engine.calculate_statuses(completed_ids)
    return [
        _skill_summary(engine, skill_id, statuses[skill_id])
        for skill_id in engine.topological_order
        if statuses[skill_id] != "locked"
    ]


def require_shareable_skill(
    engine: GraphEngine,
    completed_ids: Iterable[str],
    skill_id: str,
) -> dict[str, Any]:
    """Validate an activity/group focus against the authoritative graph."""

    if skill_id not in engine.skill_by_id:
        raise KeyError(skill_id)
    status = engine.calculate_statuses(completed_ids)[skill_id]
    if status == "locked":
        missing = engine.missing_prerequisites(skill_id, completed_ids)
        names = [engine.skill_by_id[item]["name"] for item in missing]
        raise PermissionError(
            "Complete prerequisite skills first: " + ", ".join(names)
        )
    return _skill_summary(engine, skill_id, status)
