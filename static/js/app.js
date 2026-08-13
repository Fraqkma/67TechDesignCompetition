"use strict";

/**
 * Skill Map frontend controller.
 *
 * Important boundary: this file only displays the status returned by Flask.
 * It never decides whether a node should be locked or recommended. Those rules
 * belong to backend/graph_engine.py so the project has one source of truth.
 */

const state = {
  roadmap: null,
  selectedSkillId: null,
  selectedSubject: "all",
  toastTimer: null,
};

const elements = {
  loading: document.querySelector("#loading-overlay"),
  apiStatus: document.querySelector("#api-status"),
  careerIcon: document.querySelector("#career-icon"),
  careerTitle: document.querySelector("#career-title"),
  careerDescription: document.querySelector("#career-description"),
  rankAvatar: document.querySelector("#rank-avatar"),
  rankName: document.querySelector("#rank-name"),
  rankHint: document.querySelector("#rank-hint"),
  careerProgressValue: document.querySelector("#career-progress-value"),
  careerProgressBar: document.querySelector("#career-progress-bar"),
  careerProgressTrack: document.querySelector(".progress-track.large"),
  progressCount: document.querySelector("#progress-count"),
  subjectProgressList: document.querySelector("#subject-progress-list"),
  subjectFilters: document.querySelector("#subject-filters"),
  edgeLayer: document.querySelector("#edge-layer"),
  nodeLayer: document.querySelector("#node-layer"),
  recommendationName: document.querySelector("#recommendation-name"),
  recommendationText: document.querySelector("#recommendation-text"),
  openRecommendation: document.querySelector("#open-recommendation"),
  emptyDetail: document.querySelector("#empty-detail"),
  skillDetail: document.querySelector("#skill-detail"),
  achievementCount: document.querySelector("#achievement-count"),
  achievementGrid: document.querySelector("#achievement-grid"),
  resetButton: document.querySelector("#reset-button"),
  toast: document.querySelector("#toast"),
};

/** Escape text before placing it inside HTML created from JSON content. */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/** Call a JSON API and turn non-2xx responses into readable errors. */
async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  const payload = await response.json().catch(() => ({
    ok: false,
    error: "Server did not return valid JSON",
  }));

  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }

  return payload;
}

/** Show a small non-blocking message at the bottom-right of the screen. */
function showToast(message, type = "success") {
  window.clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", type === "error");
  elements.toast.classList.add("show");

  state.toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 3300);
}

function setLoading(isLoading) {
  elements.loading.classList.toggle("hidden", !isLoading);
}

function getSkill(skillId) {
  return state.roadmap?.nodes.find((skill) => skill.id === skillId) || null;
}

function getSubject(subjectId) {
  return (
    state.roadmap?.subjects.find((subject) => subject.id === subjectId) || null
  );
}

/** Determine the simple avatar rank from weighted career progress. */
function getRank(progress) {
  if (progress >= 90) {
    return { code: "04", name: "Career Ready", hint: "พร้อมต่อยอดสู่โปรเจกต์จริง" };
  }
  if (progress >= 60) {
    return { code: "03", name: "System Builder", hint: "กำลังเชื่อมฮาร์ดแวร์และซอฟต์แวร์" };
  }
  if (progress >= 30) {
    return { code: "02", name: "Core Learner", hint: "มีพื้นฐานและเริ่มเรียนวิชาหลัก" };
  }
  return { code: "01", name: "Starter", hint: "เริ่มเรียน Skill แรกเพื่อพัฒนา Rank" };
}

/** Render career title, progress bars and avatar rank. */
function renderOverview() {
  const { career, progress } = state.roadmap;
  elements.careerIcon.textContent = career.icon;
  elements.careerTitle.textContent = `${career.name} Roadmap`;
  elements.careerDescription.textContent = career.description;

  elements.careerProgressValue.textContent = `${progress.career}%`;
  elements.careerProgressBar.style.width = `${progress.career}%`;
  elements.careerProgressTrack.setAttribute("aria-valuenow", progress.career);
  elements.progressCount.textContent =
    `เรียนแล้ว ${progress.completedCount} จาก ${progress.totalCount} Skills ` +
    `(${progress.completedWeight}/${progress.totalWeight} คะแนน)`;

  const rank = getRank(progress.career);
  elements.rankAvatar.textContent = rank.code;
  elements.rankName.textContent = rank.name;
  elements.rankHint.textContent = rank.hint;

  elements.subjectProgressList.innerHTML = state.roadmap.subjects
    .map((subject) => {
      const value = progress.subjects[subject.id] ?? 0;
      return `
        <div class="subject-progress-row">
          <span class="subject-name">
            <i class="subject-swatch" style="background:${escapeHtml(subject.color)}"></i>
            ${escapeHtml(subject.name)}
          </span>
          <div class="progress-track" role="progressbar" aria-valuemin="0"
               aria-valuemax="100" aria-valuenow="${value}"
               aria-label="${escapeHtml(subject.name)} progress">
            <span style="width:${value}%; background:${escapeHtml(subject.color)}"></span>
          </div>
          <span class="subject-percent">${value}%</span>
        </div>`;
    })
    .join("");
}

/** Render buttons that dim unrelated subjects without removing graph context. */
function renderSubjectFilters() {
  const filters = [
    { id: "all", name: "ทุกวิชา", color: "#73e5c1" },
    ...state.roadmap.subjects.map((subject) => ({
      id: subject.id,
      name: subject.name,
      color: subject.color,
    })),
  ];

  elements.subjectFilters.innerHTML = filters
    .map(
      (filter) => `
        <button class="filter-button ${filter.id === state.selectedSubject ? "active" : ""}"
                type="button" data-subject-id="${escapeHtml(filter.id)}"
                style="--filter-color:${escapeHtml(filter.color)}">
          ${escapeHtml(filter.name)}
        </button>`
    )
    .join("");

  elements.subjectFilters.querySelectorAll("[data-subject-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedSubject = button.dataset.subjectId;
      await loadRoadmap(false);
    });
  });
}

/** Build an SVG curve between the fixed center positions of two nodes. */
function edgePath(source, target) {
  // The stored coordinates are node centers. Moving each endpoint 72px keeps
  // the arrow visible at the border instead of hiding it under the node card.
  const sourceX = Number(source.position.x) + 72;
  const sourceY = Number(source.position.y);
  const targetX = Number(target.position.x) - 72;
  const targetY = Number(target.position.y);
  const middleX = sourceX + (targetX - sourceX) / 2;

  return `M ${sourceX} ${sourceY} C ${middleX} ${sourceY}, ${middleX} ${targetY}, ${targetX} ${targetY}`;
}

/** Draw graph edges first so every node stays clickable above them. */
function renderEdges() {
  const nodeIndex = Object.fromEntries(
    state.roadmap.nodes.map((node) => [node.id, node])
  );

  const paths = state.roadmap.edges
    .map((edge) => {
      const source = nodeIndex[edge.source];
      const target = nodeIndex[edge.target];
      if (!source || !target) return "";

      const isDimmed =
        state.selectedSubject !== "all" &&
        source.subjectId !== state.selectedSubject &&
        target.subjectId !== state.selectedSubject;

      let edgeStatus = "locked";
      if (source.status === "completed" && target.status === "completed") {
        edgeStatus = "completed";
      } else if (source.status === "completed" && target.status === "available") {
        edgeStatus = "available";
      }

      return `<path class="graph-edge ${edgeStatus} ${isDimmed ? "dimmed" : ""}"
                    marker-end="url(#edge-arrow-${edgeStatus})"
                    d="${edgePath(source, target)}" />`;
    })
    .join("");

  elements.edgeLayer.innerHTML = `
    <defs>
      <marker id="edge-arrow-locked" markerWidth="7" markerHeight="7"
              refX="6" refY="3.5" orient="auto">
        <path d="M 0 0 L 7 3.5 L 0 7 Z" fill="#526573"></path>
      </marker>
      <marker id="edge-arrow-available" markerWidth="7" markerHeight="7"
              refX="6" refY="3.5" orient="auto">
        <path d="M 0 0 L 7 3.5 L 0 7 Z" fill="#f8c35a"></path>
      </marker>
      <marker id="edge-arrow-completed" markerWidth="7" markerHeight="7"
              refX="6" refY="3.5" orient="auto">
        <path d="M 0 0 L 7 3.5 L 0 7 Z" fill="#55d79b"></path>
      </marker>
    </defs>
    ${paths}`;
}

function statusIcon(status) {
  if (status === "completed") return "✓";
  if (status === "available") return "→";
  return "×";
}

/** Render the clickable skill nodes using coordinates stored in database.json. */
function renderNodes() {
  elements.nodeLayer.innerHTML = state.roadmap.nodes
    .map((skill) => {
      const subject = getSubject(skill.subjectId);
      const isDimmed =
        state.selectedSubject !== "all" &&
        skill.subjectId !== state.selectedSubject;

      const classes = [
        "skill-node",
        skill.status,
        skill.isRecommended ? "recommended" : "",
        skill.id === state.selectedSkillId ? "selected" : "",
        isDimmed ? "dimmed" : "",
      ]
        .filter(Boolean)
        .join(" ");

      return `
        <button class="${classes}" type="button"
                data-skill-id="${escapeHtml(skill.id)}"
                style="left:${skill.position.x}px; top:${skill.position.y}px;
                       --subject-color:${escapeHtml(subject?.color || "#91a8b5")}">
          <span class="node-state-icon">${statusIcon(skill.status)}</span>
          <span class="node-copy">
            <strong title="${escapeHtml(skill.name)}">${escapeHtml(skill.shortName)}</strong>
            <small>${escapeHtml(skill.level)} · ${skill.estimatedHours}h</small>
          </span>
        </button>`;
    })
    .join("");

  elements.nodeLayer.querySelectorAll("[data-skill-id]").forEach((node) => {
    node.addEventListener("click", () => openSkill(node.dataset.skillId));
  });
}

/** Render the recommendation returned by the backend scoring algorithm. */
function renderRecommendation() {
  const recommendation = state.roadmap.recommendation;

  if (!recommendation) {
    elements.recommendationName.textContent = "Roadmap สำเร็จแล้ว";
    elements.recommendationText.textContent =
      "ไม่มี Skill ที่ต้องเรียนต่อใน Prototype นี้";
    elements.openRecommendation.disabled = true;
    return;
  }

  const skill = getSkill(recommendation.skillId);
  elements.recommendationName.textContent = skill.name;
  elements.recommendationText.textContent =
    `คะแนนแนะนำ ${recommendation.score} · ` +
    `เรียนแล้วช่วยปลดล็อก ${recommendation.reason.newlyUnlockedSkills} Skill`;
  elements.openRecommendation.disabled = false;
  elements.openRecommendation.onclick = () => openSkill(recommendation.skillId);
}

function renderAchievements() {
  const unlockedCount = state.roadmap.achievements.filter(
    (achievement) => achievement.unlocked
  ).length;
  elements.achievementCount.textContent = `${unlockedCount}/${state.roadmap.achievements.length}`;

  elements.achievementGrid.innerHTML = state.roadmap.achievements
    .map(
      (achievement) => `
        <div class="achievement-item ${achievement.unlocked ? "unlocked" : ""}"
             title="${escapeHtml(achievement.description)}">
          <span class="achievement-icon">${escapeHtml(achievement.icon)}</span>
          <strong>${escapeHtml(achievement.name)}</strong>
          <small>${escapeHtml(achievement.description)}</small>
        </div>`
    )
    .join("");
}

function statusLabel(status) {
  return {
    locked: "Locked",
    available: "Available",
    completed: "Completed",
  }[status];
}

function renderBulletList(items) {
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

/** Open a skill and build its complete detail panel from roadmap JSON. */
function openSkill(skillId) {
  const skill = getSkill(skillId);
  if (!skill) return;

  state.selectedSkillId = skillId;
  renderNodes();

  const subject = getSubject(skill.subjectId);
  const prerequisites = skill.prerequisiteIds.map((prerequisiteId) => {
    const prerequisite = getSkill(prerequisiteId);
    return {
      name: prerequisite?.name || prerequisiteId,
      completed: prerequisite?.status === "completed",
    };
  });

  const missingNames = skill.missingPrerequisiteIds
    .map((missingId) => getSkill(missingId)?.name || missingId)
    .join(", ");

  let actionLabel = "บันทึกว่าเรียนแล้ว";
  let actionClass = "primary";
  let actionDisabled = false;

  if (skill.status === "completed") {
    actionLabel = "ยกเลิกว่าเรียนแล้ว";
    actionClass = "secondary";
  } else if (skill.status === "locked") {
    actionLabel = "ยังไม่สามารถเรียนได้";
    actionClass = "secondary";
    actionDisabled = true;
  }

  elements.emptyDetail.classList.add("hidden");
  elements.skillDetail.classList.remove("hidden");
  elements.skillDetail.innerHTML = `
    <div class="detail-header">
      <div>
        <span class="eyebrow" style="color:${escapeHtml(subject?.color || "#73e5c1")}">
          ${escapeHtml(subject?.name || skill.subjectId)}
        </span>
        <h2>${escapeHtml(skill.name)}</h2>
        <p>${escapeHtml(skill.thaiName)}</p>
      </div>
      <span class="status-badge ${escapeHtml(skill.status)}">${statusLabel(skill.status)}</span>
    </div>

    <p class="detail-description">${escapeHtml(skill.description)}</p>

    <div class="detail-meta">
      <span class="meta-chip">ระดับ ${escapeHtml(skill.level)}</span>
      <span class="meta-chip">ความยาก ${skill.difficulty}/5</span>
      <span class="meta-chip">ประมาณ ${skill.estimatedHours} ชั่วโมง</span>
      <span class="meta-chip">น้ำหนัก ${skill.weight}</span>
    </div>

    <section class="detail-section">
      <h3>พื้นฐานที่ต้องเรียนก่อน</h3>
      <div class="chip-list">
        ${
          prerequisites.length
            ? prerequisites
                .map(
                  (item) => `<span class="prerequisite-chip ${item.completed ? "done" : ""}">
                    ${item.completed ? "✓" : "○"} ${escapeHtml(item.name)}
                  </span>`
                )
                .join("")
            : '<span class="prerequisite-chip done">เริ่มเรียนได้ทันที</span>'
        }
      </div>
    </section>

    <section class="detail-section">
      <h3>เทคนิคสำคัญ</h3>
      ${renderBulletList(skill.techniques)}
    </section>

    <section class="detail-section">
      <h3>เมื่อเรียนจบจะทำอะไรได้</h3>
      ${renderBulletList(skill.learningOutcomes)}
    </section>

    <section class="detail-section">
      <h3>นำไปใช้จริง</h3>
      ${renderBulletList(skill.realWorld)}
    </section>

    ${
      skill.status === "locked"
        ? `<p class="locked-message">ต้องเรียนให้ครบก่อน: ${escapeHtml(missingNames)}</p>`
        : ""
    }

    <div class="detail-actions">
      <button class="button ${actionClass} full" id="toggle-skill-button"
              type="button" ${actionDisabled ? "disabled" : ""}>
        ${actionLabel}
      </button>
      <button class="button ghost full" id="build-path-button" type="button">
        สร้างแผนไปยัง Skill นี้
      </button>
    </div>
    <div id="path-result"></div>`;

  const toggleButton = document.querySelector("#toggle-skill-button");
  if (!actionDisabled) {
    toggleButton.addEventListener("click", () => {
      toggleSkill(skill.id, skill.status !== "completed");
    });
  }

  document.querySelector("#build-path-button").addEventListener("click", () => {
    buildPath(skill.id);
  });
}

/** POST a progress change; backend validates unlock rules and cascades removals. */
async function toggleSkill(skillId, completed) {
  if (!completed) {
    const confirmed = window.confirm(
      "หากยกเลิก Skill นี้ ระบบจะยกเลิก Skill ที่ต้องพึ่งพามันด้วย ต้องการดำเนินการต่อหรือไม่?"
    );
    if (!confirmed) return;
  }

  try {
    const payload = await apiRequest("/api/progress", {
      method: "POST",
      body: JSON.stringify({ skillId, completed }),
    });

    state.roadmap = payload.data.roadmap;
    renderAll();
    openSkill(skillId);

    const removedCount = payload.data.removedSkillIds?.length || 0;
    const suffix = removedCount > 1 ? ` (${removedCount} Skills ถูกปรับตาม)` : "";
    showToast(`${payload.message}${suffix}`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

/** Ask the DFS/topological algorithm for the remaining path to one target. */
async function buildPath(skillId) {
  const resultContainer = document.querySelector("#path-result");
  if (!resultContainer) return;

  resultContainer.innerHTML = '<div class="path-result">กำลังสร้างเส้นทาง...</div>';

  try {
    const payload = await apiRequest(`/api/path/${encodeURIComponent(skillId)}`);
    const { steps, targetName } = payload.data;

    resultContainer.innerHTML = `
      <div class="path-result">
        <h3>เส้นทางที่เหลือไปยัง ${escapeHtml(targetName)}</h3>
        ${
          steps.length
            ? `<ol class="path-list">${steps
                .map(
                  (step) => `<li>${escapeHtml(step.name)} <small>(${escapeHtml(step.level)})</small></li>`
                )
                .join("")}</ol>`
            : "<p class=\"detail-description\">เรียนเส้นทางนี้ครบแล้ว</p>"
        }
      </div>`;
  } catch (error) {
    resultContainer.innerHTML = "";
    showToast(error.message, "error");
  }
}

function renderAll() {
  renderOverview();
  renderSubjectFilters();
  renderEdges();
  renderNodes();
  renderRecommendation();
  renderAchievements();
}

/** Load one complete roadmap payload. The subject only affects recommendation. */
async function loadRoadmap(showFullLoading = true) {
  if (showFullLoading) setLoading(true);

  try {
    const subjectQuery = encodeURIComponent(state.selectedSubject);
    const payload = await apiRequest(`/api/roadmap?subject=${subjectQuery}`);
    state.roadmap = payload.data;
    renderAll();

    if (state.selectedSkillId && getSkill(state.selectedSkillId)) {
      openSkill(state.selectedSkillId);
    }

    elements.apiStatus.classList.remove("offline");
  } catch (error) {
    elements.apiStatus.textContent = "API offline";
    showToast(`โหลด Roadmap ไม่สำเร็จ: ${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

elements.resetButton.addEventListener("click", async () => {
  const confirmed = window.confirm(
    "ต้องการล้าง Progress ทั้งหมดหรือไม่? ข้อมูล Skill Map จะไม่ถูกลบ"
  );
  if (!confirmed) return;

  try {
    const payload = await apiRequest("/api/reset", { method: "POST" });
    state.roadmap = payload.data;
    state.selectedSkillId = null;
    elements.skillDetail.classList.add("hidden");
    elements.emptyDetail.classList.remove("hidden");
    renderAll();
    showToast(payload.message);
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.addEventListener("DOMContentLoaded", () => loadRoadmap(true));
