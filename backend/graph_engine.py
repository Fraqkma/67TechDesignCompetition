"""Pure graph algorithms for SkillGraph.

The browser never decides whether a skill is locked. It only renders the
status calculated here, which keeps the learning rules consistent everywhere.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable


class GraphValidationError(ValueError):
    """Raised when skill or edge data cannot form a valid learning DAG."""


class GraphEngine:
    """Validate and analyze the Computer Engineering skill graph."""

    VALID_LEVELS = {"beginner", "intermediate", "advanced"}

    def __init__(self, database: dict[str, Any]) -> None:
        self.database = database
        self.career = database["career"]
        self.subjects = database["subjects"]
        self.skills = database["skills"]
        self.edges = database["edges"]

        self.skill_by_id = {skill["id"]: skill for skill in self.skills}
        self.subject_by_id = {
            subject["id"]: subject for subject in self.subjects
        }

        self.prerequisites: dict[str, set[str]] = defaultdict(set)
        self.children: dict[str, set[str]] = defaultdict(set)

        for edge in self.edges:
            source = edge["source"]
            target = edge["target"]
            self.prerequisites[target].add(source)
            self.children[source].add(target)

        self.topological_order = self.validate_graph()

    def validate_graph(self) -> list[str]:
        """Validate IDs and return a topological order using Kahn's algorithm.

        A topological order guarantees that every prerequisite appears before
        the skill that depends on it. If not every node can be processed, the
        graph contains a cycle and is unsuitable as a learning roadmap.
        """

        skill_ids = [skill["id"] for skill in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise GraphValidationError("Duplicate skill id found")

        known_skills = set(skill_ids)
        known_subjects = set(self.subject_by_id)

        for skill in self.skills:
            if skill.get("subjectId") not in known_subjects:
                raise GraphValidationError(
                    f"Unknown subject for skill: {skill['id']}"
                )
            if skill.get("level") not in self.VALID_LEVELS:
                raise GraphValidationError(
                    f"Invalid level for skill: {skill['id']}"
                )

        seen_edges: set[tuple[str, str]] = set()
        indegree = {skill_id: 0 for skill_id in skill_ids}

        for edge in self.edges:
            source = edge.get("source")
            target = edge.get("target")

            if source not in known_skills or target not in known_skills:
                raise GraphValidationError(
                    f"Edge refers to unknown skill: {source} -> {target}"
                )
            if source == target:
                raise GraphValidationError(f"Self-loop found at: {source}")
            if (source, target) in seen_edges:
                raise GraphValidationError(
                    f"Duplicate edge found: {source} -> {target}"
                )

            seen_edges.add((source, target))
            indegree[target] += 1

        queue = deque(
            skill_id for skill_id in skill_ids if indegree[skill_id] == 0
        )
        order: list[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)

            for child in sorted(self.children[current]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if len(order) != len(skill_ids):
            raise GraphValidationError(
                "The roadmap contains a cycle; prerequisites must not loop"
            )

        return order

    def clean_completed(self, completed_ids: Iterable[str]) -> set[str]:
        """Remove unknown and logically invalid completed skills.

        This also protects the prototype if someone manually edits the JSON
        progress section and marks an advanced skill complete without its
        prerequisites.
        """

        remaining = {
            skill_id
            for skill_id in completed_ids
            if skill_id in self.skill_by_id
        }

        changed = True
        while changed:
            changed = False
            for skill_id in list(remaining):
                if not self.prerequisites[skill_id].issubset(remaining):
                    remaining.remove(skill_id)
                    changed = True

        return remaining

    def calculate_statuses(
        self, completed_ids: Iterable[str]
    ) -> dict[str, str]:
        """Return ``completed``, ``available`` or ``locked`` for every skill."""

        completed = self.clean_completed(completed_ids)
        statuses: dict[str, str] = {}

        for skill_id in self.topological_order:
            if skill_id in completed:
                statuses[skill_id] = "completed"
            elif self.prerequisites[skill_id].issubset(completed):
                statuses[skill_id] = "available"
            else:
                statuses[skill_id] = "locked"

        return statuses

    def missing_prerequisites(
        self, skill_id: str, completed_ids: Iterable[str]
    ) -> list[str]:
        """List the direct prerequisites that are still incomplete."""

        completed = self.clean_completed(completed_ids)
        return sorted(self.prerequisites[skill_id] - completed)

    def remove_skill_and_invalid_dependents(
        self, skill_id: str, completed_ids: Iterable[str]
    ) -> tuple[set[str], list[str]]:
        """Uncomplete a skill and cascade to dependents that become invalid."""

        remaining = self.clean_completed(completed_ids)
        removed: list[str] = []

        if skill_id in remaining:
            remaining.remove(skill_id)
            removed.append(skill_id)

        changed = True
        while changed:
            changed = False
            for current in self.topological_order:
                if current in remaining and not self.prerequisites[
                    current
                ].issubset(remaining):
                    remaining.remove(current)
                    removed.append(current)
                    changed = True

        return remaining, removed

    def _newly_unlocked_count(
        self, candidate_id: str, completed: set[str]
    ) -> int:
        """Count locked skills that become available after one candidate."""

        before = self.calculate_statuses(completed)
        after = self.calculate_statuses(completed | {candidate_id})
        return sum(
            1
            for skill_id in self.skill_by_id
            if before[skill_id] == "locked" and after[skill_id] == "available"
        )

    def recommend_next(
        self,
        completed_ids: Iterable[str],
        preferred_subject: str | None = None,
    ) -> dict[str, Any] | None:
        """Score every available skill and return the best next step.

        Score = career relevance * 4 + unlock impact * 2 + subject bonus
                - excessive difficulty penalty
        """

        completed = self.clean_completed(completed_ids)
        statuses = self.calculate_statuses(completed)
        candidates: list[dict[str, Any]] = []

        for skill in self.skills:
            skill_id = skill["id"]
            if statuses[skill_id] != "available":
                continue

            relevance_score = int(skill.get("careerRelevance", 1)) * 4
            unlock_count = self._newly_unlocked_count(skill_id, completed)
            unlock_score = unlock_count * 2
            subject_bonus = (
                3
                if preferred_subject
                and preferred_subject != "all"
                and skill["subjectId"] == preferred_subject
                else 0
            )
            difficulty_penalty = max(0, int(skill.get("difficulty", 1)) - 3) * 2
            total_score = (
                relevance_score
                + unlock_score
                + subject_bonus
                - difficulty_penalty
            )

            candidates.append(
                {
                    "skillId": skill_id,
                    "score": total_score,
                    "reason": {
                        "careerRelevance": relevance_score,
                        "unlockImpact": unlock_score,
                        "newlyUnlockedSkills": unlock_count,
                        "subjectBonus": subject_bonus,
                        "difficultyPenalty": difficulty_penalty,
                    },
                }
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                -item["score"],
                self.skill_by_id[item["skillId"]]["difficulty"],
                self.skill_by_id[item["skillId"]]["name"],
            )
        )
        return candidates[0]

    def calculate_progress(
        self, completed_ids: Iterable[str]
    ) -> dict[str, Any]:
        """Calculate weighted career and subject progress percentages."""

        completed = self.clean_completed(completed_ids)
        total_weight = 0
        completed_weight = 0
        subject_totals = {subject["id"]: 0 for subject in self.subjects}
        subject_completed = {subject["id"]: 0 for subject in self.subjects}

        for skill in self.skills:
            if not skill.get("required", True):
                continue

            weight = int(skill.get("weight", 1))
            subject_id = skill["subjectId"]
            total_weight += weight
            subject_totals[subject_id] += weight

            if skill["id"] in completed:
                completed_weight += weight
                subject_completed[subject_id] += weight

        def percentage(done: int, total: int) -> int:
            return round((done / total) * 100) if total else 0

        return {
            "career": percentage(completed_weight, total_weight),
            "completedWeight": completed_weight,
            "totalWeight": total_weight,
            "completedCount": len(completed),
            "totalCount": len(self.skills),
            "subjects": {
                subject_id: percentage(
                    subject_completed[subject_id], subject_totals[subject_id]
                )
                for subject_id in subject_totals
            },
        }

    def build_learning_path(
        self, target_id: str, completed_ids: Iterable[str]
    ) -> list[dict[str, Any]]:
        """Return missing prerequisites and target in a valid learning order."""

        if target_id not in self.skill_by_id:
            raise KeyError(target_id)

        completed = self.clean_completed(completed_ids)
        required: set[str] = set()

        def collect_prerequisites(skill_id: str) -> None:
            for prerequisite_id in self.prerequisites[skill_id]:
                if prerequisite_id not in required:
                    required.add(prerequisite_id)
                    collect_prerequisites(prerequisite_id)

        collect_prerequisites(target_id)
        required.add(target_id)

        path_ids = [
            skill_id
            for skill_id in self.topological_order
            if skill_id in required and skill_id not in completed
        ]

        return [
            {
                "order": index + 1,
                "skillId": skill_id,
                "name": self.skill_by_id[skill_id]["name"],
                "subjectId": self.skill_by_id[skill_id]["subjectId"],
                "level": self.skill_by_id[skill_id]["level"],
            }
            for index, skill_id in enumerate(path_ids)
        ]

    def build_roadmap_payload(
        self,
        completed_ids: Iterable[str],
        preferred_subject: str | None = None,
    ) -> dict[str, Any]:
        """Build the complete JSON object consumed by the browser."""

        completed = self.clean_completed(completed_ids)
        statuses = self.calculate_statuses(completed)
        recommendation = self.recommend_next(completed, preferred_subject)
        recommended_id = recommendation["skillId"] if recommendation else None

        nodes = []
        for skill in self.skills:
            skill_payload = dict(skill)
            skill_payload["status"] = statuses[skill["id"]]
            skill_payload["isRecommended"] = skill["id"] == recommended_id
            skill_payload["prerequisiteIds"] = sorted(
                self.prerequisites[skill["id"]]
            )
            skill_payload["nextSkillIds"] = sorted(self.children[skill["id"]])
            skill_payload["missingPrerequisiteIds"] = self.missing_prerequisites(
                skill["id"], completed
            )
            nodes.append(skill_payload)

        return {
            "career": self.career,
            "subjects": self.subjects,
            "nodes": nodes,
            "edges": self.edges,
            "progress": self.calculate_progress(completed),
            "recommendation": recommendation,
            "recommendedSkillId": recommended_id,
            # Achievements are user-global data read from the database
            # (backend.db_store); the graph engine only computes graph facts.
            "achievements": [],
            "completedSkillIds": sorted(completed),
            "graph": {
                "isValidDAG": True,
                "topologicalOrder": self.topological_order,
            },
        }
