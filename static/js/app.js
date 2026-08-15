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
  careerId: new URLSearchParams(window.location.search).get("career") || null,
};

const DEFAULT_PLAN_WEEKLY_HOURS = 6;

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
  // Never let the loading screen spin forever: abort requests that the
  // server does not answer in time so the page shows a readable error
  // instead of hanging (e.g. when the database is unreachable).
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 15000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
      signal: options.signal || controller.signal,
    });

    const payload = await response.json().catch(() => ({
      ok: false,
      error: "Server did not return valid JSON",
    }));

    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Request failed: ${response.status}`);
    }

    return payload;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("เซิร์ฟเวอร์ไม่ตอบกลับภายใน 15 วินาที — เชื่อมต่อฐานข้อมูลไม่ได้?");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
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

/** Render career title, progress bars and avatar rank. */
function renderOverview() {
  const { career, progress } = state.roadmap;
  elements.careerIcon.textContent = career.icon;
  elements.careerTitle.textContent = `${career.name} Roadmap`;
  elements.careerDescription.textContent = career.description;
  document.querySelector("#career-progress-title").textContent =
    `เส้นทางสู่${career.thaiName || career.name}`;

  elements.careerProgressValue.textContent = `${progress.career}%`;
  elements.careerProgressBar.style.width = `${progress.career}%`;
  elements.careerProgressTrack.setAttribute("aria-valuenow", progress.career);
  elements.progressCount.textContent =
    `เรียนแล้ว ${progress.completedCount} จาก ${progress.totalCount} Skills ` +
    `(${progress.completedWeight}/${progress.totalWeight} คะแนน)`;

  // Rank is chosen server-side from the ranks table (database).
  const rank = state.roadmap.rank || { code: "01", name: "Starter", hint: "" };
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

/**
 * Orbit layout: three concentric rings by level (beginner/intermediate/
 * advanced), skills spread evenly around each ring. Positions are computed
 * here purely for rendering — the backend's position field (used by the
 * old grid layout) is no longer read; status/locking rules are unaffected
 * since those still come entirely from the server.
 */
const ORBIT_CENTER = 450;
const ORBIT_TIER_RADIUS = { beginner: 170, intermediate: 285, advanced: 395 };
const ORBIT_TIER_ORDER = ["beginner", "intermediate", "advanced"];

function computeOrbitPositions(nodes, edges) {
  const byTier = {};
  ORBIT_TIER_ORDER.forEach((tier) => (byTier[tier] = []));
  nodes.forEach((node) => {
    if (!byTier[node.level]) byTier[node.level] = [];
    byTier[node.level].push(node);
  });

  const positions = {};
  const angleOf = {};

  ORBIT_TIER_ORDER.forEach((tier, tierIndex) => {
    let list = byTier[tier];
    const radius = ORBIT_TIER_RADIUS[tier] || ORBIT_TIER_RADIUS.beginner;
    const rotationOffset = ((tierIndex * 18 - 90) * Math.PI) / 180;
    const count = list.length;

    // Barycenter ordering: place each node near the average angle of its
    // already-placed prerequisites (inner tiers), so edges stay short and
    // don't crisscross the center. Nodes with no placed prerequisite keep
    // their original order and fall after the ones that do.
    if (tierIndex > 0 && edges && edges.length && count) {
      const parentAngle = {};
      list.forEach((node) => {
        const parents = edges
          .filter((edge) => edge.target === node.id && angleOf[edge.source] !== undefined)
          .map((edge) => angleOf[edge.source]);
        parentAngle[node.id] = parents.length
          ? parents.reduce((sum, a) => sum + a, 0) / parents.length
          : null;
      });
      list = list
        .map((node, index) => ({ node, index, angle: parentAngle[node.id] }))
        .sort((a, b) => {
          if (a.angle === null && b.angle === null) return a.index - b.index;
          if (a.angle === null) return 1;
          if (b.angle === null) return -1;
          return a.angle - b.angle;
        })
        .map((entry) => entry.node);
    }

    list.forEach((node, index) => {
      const angle = count ? rotationOffset + (index / count) * Math.PI * 2 : 0;
      positions[node.id] = {
        x: ORBIT_CENTER + Math.cos(angle) * radius,
        y: ORBIT_CENTER + Math.sin(angle) * radius,
      };
      angleOf[node.id] = angle;
    });
  });
  return positions;
}

/** A gentle inward-bowed curve between two orbit positions. */
function orbitEdgePath(a, b) {
  const midX = (a.x + b.x) / 2;
  const midY = (a.y + b.y) / 2;
  const controlX = ORBIT_CENTER + (midX - ORBIT_CENTER) * 0.85;
  const controlY = ORBIT_CENTER + (midY - ORBIT_CENTER) * 0.85;
  return `M ${a.x} ${a.y} Q ${controlX} ${controlY} ${b.x} ${b.y}`;
}

/** Draw the tier rings, then edges, then let renderNodes draw the planets. */
function renderEdges() {
  const nodeIndex = Object.fromEntries(
    state.roadmap.nodes.map((node) => [node.id, node])
  );
  const positions = computeOrbitPositions(state.roadmap.nodes, state.roadmap.edges);
  state.orbitPositions = positions;

  const rings = ORBIT_TIER_ORDER.map(
    (tier) =>
      `<circle class="orbit-ring" cx="${ORBIT_CENTER}" cy="${ORBIT_CENTER}" r="${ORBIT_TIER_RADIUS[tier]}"></circle>`
  ).join("");

  const paths = state.roadmap.edges
    .map((edge) => {
      const source = nodeIndex[edge.source];
      const target = nodeIndex[edge.target];
      const a = positions[edge.source];
      const b = positions[edge.target];
      if (!source || !target || !a || !b) return "";

      const isDimmed =
        state.selectedSubject !== "all" &&
        source.subjectId !== state.selectedSubject &&
        target.subjectId !== state.selectedSubject;

      let edgeStatus = "e-locked";
      if (source.status === "completed" && target.status === "completed") {
        edgeStatus = "e-completed";
      } else if (source.status === "completed" && target.status === "available") {
        edgeStatus = "e-open";
      }

      return `<path class="orbit-edge ${edgeStatus} ${isDimmed ? "dimmed" : ""}"
                    d="${orbitEdgePath(a, b)}" />`;
    })
    .join("");

  elements.edgeLayer.innerHTML = rings + paths;
}

/** Render the clickable skill planets on their computed orbit positions. */
function renderNodes() {
  const positions = state.orbitPositions || computeOrbitPositions(state.roadmap.nodes, state.roadmap.edges);

  elements.nodeLayer.innerHTML = state.roadmap.nodes
    .map((skill) => {
      const pos = positions[skill.id];
      if (!pos) return "";
      const isDimmed =
        state.selectedSubject !== "all" &&
        skill.subjectId !== state.selectedSubject;

      const classes = [
        "planet",
        skill.status,
        skill.isRecommended ? "recommended" : "",
        skill.id === state.selectedSkillId ? "selected" : "",
        isDimmed ? "dimmed" : "",
      ]
        .filter(Boolean)
        .join(" ");

      const leftPct = ((pos.x / 900) * 100).toFixed(3);
      const topPct = ((pos.y / 900) * 100).toFixed(3);

      return `
        <button class="${classes}" type="button"
                data-skill-id="${escapeHtml(skill.id)}"
                style="left:${leftPct}%; top:${topPct}%"
                title="${escapeHtml(skill.name)}"
                aria-label="${escapeHtml(skill.name)}">
          <span class="planet-ring" aria-hidden="true"></span>
          <span class="planet-core" aria-hidden="true"></span>
          <span class="planet-label">${escapeHtml(skill.shortName)}</span>
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
  const achievements = state.roadmap.achievements || [];
  const unlockedCount = achievements.filter(
    (achievement) => achievement.unlocked
  ).length;
  elements.achievementCount.textContent = `${unlockedCount}/${achievements.length}`;

  elements.achievementGrid.innerHTML = achievements
    .map((achievement) => {
      // Keep the God badge visual available while an already-running server
      // still returns catalog data created before the icon URL was seeded.
      const iconUrl = achievement.iconUrl || (
        achievement.name === "God" ? "/pignopic/god.png" : ""
      );
      const icon = iconUrl
        ? `<img class="achievement-img" src="${escapeHtml(iconUrl)}" alt="" loading="lazy">`
        : `<span class="achievement-icon">🎖</span>`;
      return `
        <div class="achievement-item ${achievement.unlocked ? "unlocked" : ""}"
             title="${escapeHtml(achievement.description)}">
          ${icon}
          <strong>${escapeHtml(achievement.name)} <span class="achievement-target">${achievement.target}%</span></strong>
          <small>${escapeHtml(achievement.description)}</small>
        </div>`;
    })
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

function currentLocalDateIso() {
  const now = new Date();
  const offsetMinutes = now.getTimezoneOffset();
  return new Date(now.getTime() - offsetMinutes * 60_000)
    .toISOString()
    .slice(0, 10);
}

function renderPlanPreview(plan) {
  const weeks = plan.weeks || [];
  return `
    <div class="path-result plan-result">
      <h3>แผนเรียนรายสัปดาห์</h3>
      <p class="detail-description">
        ใช้ ${escapeHtml(plan.weeklyHours)} ชั่วโมง/สัปดาห์ เริ่ม ${escapeHtml(plan.startDate)}
        และคาดว่าจะจบประมาณ ${escapeHtml(plan.estimatedCompletionDate)}
      </p>
      <div class="detail-meta">
        <span class="meta-chip">รวม ${escapeHtml(plan.totalHours)} ชั่วโมง</span>
        <span class="meta-chip">เหลือ ${escapeHtml(plan.remainingSkillCount)} skill</span>
      </div>
      ${
        weeks.length
          ? `<ol class="path-list">${weeks
              .map(
                (week) => `<li>
                    Week ${escapeHtml(week.weekNumber)} · ${escapeHtml(week.plannedHours)}h
                    <small>(${escapeHtml(week.startDate)} - ${escapeHtml(week.endDate)})</small>
                    <ul>${week.assignments
                      .map(
                        (assignment) => `<li>${escapeHtml(assignment.name)} · ${escapeHtml(assignment.hours)}h</li>`
                      )
                      .join("")}</ul>
                  </li>`
              )
              .join("")}</ol>`
          : '<p class="detail-description">ยังไม่มีทักษะที่ต้องแบ่งเป็นหลายสัปดาห์</p>'
      }
    </div>`;
}

/** Open a skill and build its complete detail panel from roadmap JSON. */
function openSkill(skillId) {
  const skill = getSkill(skillId);
  if (!skill) return;

  state.selectedSkillId = skillId;
  window.dispatchEvent(
    new CustomEvent("ai:focus-skill", {
      detail: { skillId, name: skill.name, thaiName: skill.thaiName },
    })
  );
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
      body: JSON.stringify({ skillId, completed, careerId: state.careerId }),
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
    const careerQuery = state.careerId
      ? `&career=${encodeURIComponent(state.careerId)}`
      : "";
    const payload = await apiRequest(`/api/roadmap?subject=${subjectQuery}${careerQuery}`);
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
    const payload = await apiRequest("/api/reset", {
      method: "POST",
      body: JSON.stringify({ careerId: state.careerId }),
    });
    state.roadmap = payload.data;
    state.selectedSkillId = null;
    window.dispatchEvent(new CustomEvent("ai:clear-focus"));
    elements.skillDetail.classList.add("hidden");
    elements.emptyDetail.classList.remove("hidden");
    renderAll();
    showToast(payload.message);
  } catch (error) {
    showToast(error.message, "error");
  }
});

document.addEventListener("DOMContentLoaded", () => loadRoadmap(true));
