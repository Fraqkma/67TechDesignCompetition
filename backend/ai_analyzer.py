"""Structured, graph-grounded recommendation context for AI features."""

from __future__ import annotations

from typing import Any, Iterable

from backend.graph_engine import GraphEngine


class AIAnalyzer:
    """Prepare facts that a teaching assistant may use but never override."""

    @staticmethod
    def _summary(skill: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": skill["id"],
            "name": skill["name"],
            "thaiName": skill.get("thaiName", skill["name"]),
            "subjectId": skill["subjectId"],
            "level": skill["level"],
        }

    @classmethod
    def analyze(
        cls,
        engine: GraphEngine,
        completed_ids: Iterable[str],
        preferred_subject: str | None = None,
    ) -> dict[str, Any]:
        """Return a portable teaching context derived solely from GraphEngine."""

        completed = engine.clean_completed(completed_ids)
        statuses = engine.calculate_statuses(completed)
        recommendation = engine.recommend_next(completed, preferred_subject)
        available = [
            cls._summary(engine.skill_by_id[skill_id])
            for skill_id in engine.topological_order
            if statuses[skill_id] == "available"
        ]

        if recommendation is None:
            return {
                "nextSkill": None,
                "reason": "All skills in the current graph are complete.",
                "teachingPrompt": None,
                "skillContext": None,
                "learnerProfile": {
                    "completedSkillIds": sorted(completed),
                    "progress": engine.calculate_progress(completed),
                },
                "availableSkills": available,
                "analysisSource": "graph_engine",
            }

        skill = engine.skill_by_id[recommendation["skillId"]]
        prerequisites = [
            engine.skill_by_id[skill_id]["name"]
            for skill_id in sorted(engine.prerequisites[skill["id"]])
        ]
        outcomes = "; ".join(skill.get("learningOutcomes", []))
        techniques = "; ".join(skill.get("techniques", []))
        teaching_prompt = (
            f"Teach {skill['name']} ({skill.get('thaiName', skill['name'])}) "
            "at a beginner-friendly pace. Use the Skill Tree as the source of "
            "truth and never invent or alter prerequisites. "
            f"Graph prerequisites: {', '.join(prerequisites) or 'none'}. "
            f"Focus on outcomes: {outcomes}. Use these approaches: {techniques}. "
            "Explain clearly, give a short example, and check understanding."
        )
        return {
            "nextSkill": cls._summary(skill),
            "reason": (
                f"{skill['name']} is available in the current graph and has the "
                f"highest recommendation score ({recommendation['score']})."
            ),
            "teachingPrompt": teaching_prompt,
            "skillContext": {
                **cls._summary(skill),
                "description": skill.get("description", ""),
                "techniques": skill.get("techniques", []),
                "learningOutcomes": skill.get("learningOutcomes", []),
                "realWorld": skill.get("realWorld", []),
                "estimatedHours": skill.get("estimatedHours"),
            },
            "learnerProfile": {
                "completedSkillIds": sorted(completed),
                "progress": engine.calculate_progress(completed),
                "preferredSubject": preferred_subject or "all",
            },
            "availableSkills": available,
            "graphEvidence": {
                "recommendationScore": recommendation["score"],
                "scoreBreakdown": recommendation["reason"],
                "directPrerequisiteIds": sorted(engine.prerequisites[skill["id"]]),
            },
            "analysisSource": "graph_engine",
        }
