"""Graph-derived weekly learning-plan previews."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

from backend.graph_engine import GraphEngine


class PlanService:
    """Turn an existing graph path into a time-boxed study plan.

    This service never chooses or changes prerequisites.  It only schedules the
    graph-defined learning path returned by :class:`GraphEngine`.
    """

    MIN_WEEKLY_HOURS = 1
    MAX_WEEKLY_HOURS = 80

    @classmethod
    def build_preview(
        cls,
        engine: GraphEngine,
        completed_ids: Iterable[str],
        target_skill_id: str,
        weekly_hours: int,
        start_date: date,
    ) -> dict[str, Any]:
        if target_skill_id not in engine.skill_by_id:
            raise KeyError(target_skill_id)
        if not cls.MIN_WEEKLY_HOURS <= weekly_hours <= cls.MAX_WEEKLY_HOURS:
            raise ValueError(
                f"weeklyHours must be between {cls.MIN_WEEKLY_HOURS} and {cls.MAX_WEEKLY_HOURS}"
            )

        path = engine.build_learning_path(target_skill_id, completed_ids)
        total_hours = sum(
            engine.skill_by_id[step["skillId"]]["estimatedHours"] for step in path
        )
        weeks: list[dict[str, Any]] = []
        step_index = 0
        remaining_for_skill = (
            engine.skill_by_id[path[0]["skillId"]]["estimatedHours"] if path else 0
        )

        while step_index < len(path):
            hours_left_this_week = weekly_hours
            assignments: list[dict[str, Any]] = []
            while hours_left_this_week and step_index < len(path):
                step = path[step_index]
                allocated = min(hours_left_this_week, remaining_for_skill)
                assignments.append(
                    {
                        "skillId": step["skillId"],
                        "name": step["name"],
                        "hours": allocated,
                    }
                )
                hours_left_this_week -= allocated
                remaining_for_skill -= allocated
                if remaining_for_skill == 0:
                    step_index += 1
                    if step_index < len(path):
                        remaining_for_skill = engine.skill_by_id[
                            path[step_index]["skillId"]
                        ]["estimatedHours"]

            week_start = start_date + timedelta(days=7 * len(weeks))
            weeks.append(
                {
                    "weekNumber": len(weeks) + 1,
                    "startDate": week_start.isoformat(),
                    "endDate": (week_start + timedelta(days=6)).isoformat(),
                    "plannedHours": weekly_hours - hours_left_this_week,
                    "assignments": assignments,
                }
            )

        return {
            "targetSkillId": target_skill_id,
            "targetName": engine.skill_by_id[target_skill_id]["name"],
            "weeklyHours": weekly_hours,
            "startDate": start_date.isoformat(),
            "totalHours": total_hours,
            "remainingSkillCount": len(path),
            "estimatedCompletionDate": weeks[-1]["endDate"] if weeks else start_date.isoformat(),
            "path": path,
            "weeks": weeks,
            "planSource": "graph_engine",
        }
