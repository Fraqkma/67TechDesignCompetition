"""Graph-grounded learner analysis for AI and teaching experiences.

This module deliberately produces facts from :class:`GraphEngine` before any
external AI is involved.  Its output is therefore safe for a future chatbot to
use as context without allowing that chatbot to change learning dependencies.
"""

from __future__ import annotations

from typing import Any, Iterable

from backend.graph_engine import GraphEngine


class AIAnalyzer:
    """Build a reusable, structured learning recommendation from graph data."""

    @staticmethod
    def _skill_summary(skill: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": skill["id"],
            "name": skill["name"],
            "thaiName": skill.get("thaiName", skill["name"]),
            "subjectId": skill["subjectId"],
            "level": skill["level"],
        }

    @staticmethod
    def _skill_context(skill: dict[str, Any]) -> dict[str, Any]:
        """Return only teaching-relevant data for a future assistant."""

        return {
            **AIAnalyzer._skill_summary(skill),
            "description": skill.get("description", ""),
            "techniques": skill.get("techniques", []),
            "learningOutcomes": skill.get("learningOutcomes", []),
            "realWorld": skill.get("realWorld", []),
            "estimatedHours": skill.get("estimatedHours"),
            "difficulty": skill.get("difficulty"),
        }

    @staticmethod
    def _teaching_prompt(
        skill: dict[str, Any],
        direct_prerequisites: list[dict[str, Any]],
    ) -> str:
        outcomes = "; ".join(skill.get("learningOutcomes", [])) or "the listed learning outcomes"
        techniques = "; ".join(skill.get("techniques", [])) or "clear, practical examples"
        prerequisite_names = ", ".join(
            prerequisite["name"] for prerequisite in direct_prerequisites
        ) or "no graph prerequisites"

        return (
            f"Teach {skill['name']} ({skill.get('thaiName', skill['name'])}) "
            "to this learner at a beginner-friendly pace. Use the supplied Skill "
            "Tree as the source of truth: do not introduce or alter prerequisites. "
            f"The graph lists these direct prerequisites: {prerequisite_names}. "
            f"Focus on these outcomes: {outcomes}. Use these learning approaches: "
            f"{techniques}. Check understanding with a short exercise and adapt "
            "the explanation to the learner's answers."
        )

    @classmethod
    def analyze(
        cls,
        engine: GraphEngine,
        completed_ids: Iterable[str],
        preferred_subject: str | None = None,
        target_skill_id: str | None = None,
    ) -> dict[str, Any]:
        """Return graph-derived analysis without calling or trusting an AI model."""

        completed = engine.clean_completed(completed_ids)
        statuses = engine.calculate_statuses(completed)
        recommendation = engine.recommend_next(completed, preferred_subject)

        if target_skill_id is not None and target_skill_id not in engine.skill_by_id:
            raise KeyError(target_skill_id)

        available = [
            cls._skill_summary(engine.skill_by_id[skill_id])
            for skill_id in engine.topological_order
            if statuses[skill_id] == "available"
        ]
        blocked = [
            {
                **cls._skill_summary(engine.skill_by_id[skill_id]),
                "missingPrerequisiteIds": engine.missing_prerequisites(
                    skill_id, completed
                ),
            }
            for skill_id in engine.topological_order
            if statuses[skill_id] == "locked"
        ]

        next_skill = None
        recommended_path: list[dict[str, Any]] = []
        skill_gap: list[dict[str, Any]] = []
        graph_evidence: dict[str, Any] = {}
        reason = "All skills in the current graph are complete."
        priority = "none"
        teaching_prompt = None
        skill_context = None

        path_steps = (
            engine.build_learning_path(target_skill_id, completed)
            if target_skill_id is not None
            else []
        )
        next_skill_id = (
            next(
                (
                    step["skillId"]
                    for step in path_steps
                    if statuses[step["skillId"]] == "available"
                ),
                None,
            )
            if target_skill_id is not None
            else (recommendation["skillId"] if recommendation is not None else None)
        )

        if next_skill_id is not None:
            skill = engine.skill_by_id[next_skill_id]
            next_skill = cls._skill_summary(skill)
            direct_prerequisites = [
                cls._skill_summary(engine.skill_by_id[skill_id])
                for skill_id in sorted(engine.prerequisites[next_skill_id])
            ]
            before = statuses
            after = engine.calculate_statuses(completed | {next_skill_id})
            newly_unlocked = [
                skill_id
                for skill_id in engine.topological_order
                if before[skill_id] == "locked" and after[skill_id] == "available"
            ]

            if not path_steps:
                path_steps = engine.build_learning_path(next_skill_id, completed)
            recommended_path = [
                cls._skill_summary(engine.skill_by_id[step["skillId"]])
                for step in path_steps
            ]
            skill_gap = list(recommended_path)
            if target_skill_id is None:
                skill_gap = [next_skill]

            unlock_count = len(newly_unlocked)
            if target_skill_id is not None:
                reason = (
                    f"{skill['name']} is the first available missing step on the "
                    f"graph-defined path to {engine.skill_by_id[target_skill_id]['name']}. "
                    f"Completing it unlocks {unlock_count} additional skill(s)."
                )
            else:
                reason = (
                    f"{skill['name']} is available because every prerequisite recorded "
                    "in the current graph is complete. "
                    f"Its graph score is {recommendation['score']} and completing it "
                    f"unlocks {unlock_count} additional skill(s)."
                )
            priority = "high" if unlock_count else "medium"
            teaching_prompt = cls._teaching_prompt(skill, direct_prerequisites)
            skill_context = cls._skill_context(skill)
            graph_evidence = {
                "recommendationScore": (
                    recommendation["score"]
                    if target_skill_id is None and recommendation is not None
                    else None
                ),
                "scoreBreakdown": (
                    recommendation["reason"]
                    if target_skill_id is None and recommendation is not None
                    else None
                ),
                "directPrerequisiteIds": sorted(engine.prerequisites[next_skill_id]),
                "newlyUnlockedSkillIds": newly_unlocked,
            }

        return {
            "nextSkill": next_skill,
            "targetSkillId": target_skill_id,
            "learnerProfile": {
                "career": engine.career,
                "preferredSubject": preferred_subject or "all",
                "completedSkillIds": sorted(completed),
                "progress": engine.calculate_progress(completed),
            },
            "availableSkills": available,
            "blockedSkills": blocked,
            "skillGap": skill_gap,
            "recommendedPath": recommended_path,
            "reason": reason,
            "priority": priority,
            "skillContext": skill_context,
            "teachingPrompt": teaching_prompt,
            "graphEvidence": graph_evidence,
            "analysisSource": "graph_engine",
        }
