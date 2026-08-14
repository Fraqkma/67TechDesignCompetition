(() => {
  "use strict";

  const panel = document.querySelector("#study-buddy-panel");
  if (!panel) return;

  const elements = {
    tabs: document.querySelector("#buddy-subject-tabs"),
    content: document.querySelector("#buddy-subject-content"),
    count: document.querySelector("#buddy-match-count"),
    status: document.querySelector("#buddy-panel-status"),
  };

  const panelState = {
    subjects: [],
    matches: [],
    friends: [],
    activeSubjectId: null,
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function initials(name) {
    return (
      String(name || "?")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((word) => word[0]?.toUpperCase() || "")
        .join("") || "?"
    );
  }

  function safeColor(value) {
    return /^#[0-9a-f]{3,8}$/i.test(String(value || ""))
      ? value
      : "#73e5c1";
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("Login required");
    }
    if (!response.ok || !body.ok) {
      throw new Error(body.error || "Could not load Study Buddy");
    }
    return body;
  }

  function matchSkillsForSubject(match, subjectId) {
    const groups = [
      {
        items: match.sharedAvailableSkills || [],
        label: "พร้อมเรียนด้วยกัน",
      },
      {
        items: match.buddyCanHelpWith || [],
        label: "เพื่อนช่วยได้",
      },
      {
        items: match.youCanHelpWith || [],
        label: "คุณช่วยเพื่อนได้",
      },
    ];

    const reasons = [];
    for (const group of groups) {
      for (const skill of group.items) {
        if (skill.subjectId === subjectId) {
          reasons.push({ ...skill, reasonLabel: group.label });
        }
      }
    }
    return reasons;
  }

  function subjectMatches(subjectId) {
    return panelState.matches
      .map((match) => ({
        match,
        reasons: matchSkillsForSubject(match, subjectId),
      }))
      .filter((item) => item.reasons.length)
      .sort(
        (left, right) =>
          right.match.matchScore - left.match.matchScore ||
          left.match.displayName.localeCompare(right.match.displayName)
      );
  }

  function renderTabs() {
    elements.tabs.innerHTML = panelState.subjects
      .map((subject) => {
        const active = subject.id === panelState.activeSubjectId;
        const name = subject.thaiName || subject.name;
        return `
          <button
            class="buddy-subject-tab"
            type="button"
            role="tab"
            aria-selected="${active}"
            data-buddy-subject="${escapeHtml(subject.id)}"
            style="--buddy-subject-color:${escapeHtml(safeColor(subject.color))}"
            title="${escapeHtml(name)}"
          >${escapeHtml(name)}</button>`;
      })
      .join("");
  }

  function renderSubject() {
    const subject = panelState.subjects.find(
      (item) => item.id === panelState.activeSubjectId
    );
    if (!subject) {
      elements.count.textContent = "0 คน";
      elements.content.innerHTML =
        '<div class="buddy-panel-empty">ยังไม่มี Subject ใน Roadmap</div>';
      return;
    }

    const matches = subjectMatches(subject.id);
    elements.count.textContent = `${matches.length} คน`;

    if (!panelState.friends.length) {
      elements.content.innerHTML = `
        <div class="buddy-panel-empty">
          เพิ่มเพื่อนก่อน แล้วระบบจะจับคู่ตาม Skill ของ ${escapeHtml(
            subject.thaiName || subject.name
          )}
          <br><a class="buddy-empty-link" href="/study-buddy#friends">＋ เพิ่มเพื่อนคนแรก</a>
        </div>`;
      return;
    }

    if (!matches.length) {
      elements.content.innerHTML = `
        <div class="buddy-panel-empty">
          เพื่อนของคุณยังไม่มี Skill Gap ที่ตรงกับ ${escapeHtml(
            subject.thaiName || subject.name
          )} ในตอนนี้
          <br><a class="buddy-empty-link" href="/study-buddy">ดูเพื่อนทั้งหมด</a>
        </div>`;
      return;
    }

    elements.content.innerHTML = matches
      .slice(0, 3)
      .map(({ match, reasons }) => {
        const reason = reasons[0];
        return `
          <article class="buddy-match-row">
            <span class="buddy-match-avatar" aria-hidden="true">${escapeHtml(
              initials(match.displayName)
            )}</span>
            <div class="buddy-match-copy">
              <strong>${escapeHtml(match.displayName)}</strong>
              <small>ตรงกัน ${escapeHtml(match.matchScore)}% · #${escapeHtml(
                match.uid
              )}</small>
              <small class="buddy-skill-reason">${escapeHtml(
                reason.reasonLabel
              )}: ${escapeHtml(reason.thaiName || reason.name)}</small>
            </div>
            <button
              class="buddy-share-path"
              type="button"
              data-buddy-share="${escapeHtml(match.id)}"
              data-subject-name="${escapeHtml(subject.thaiName || subject.name)}"
            >แชร์เส้นทาง</button>
          </article>`;
      })
      .join("");
  }

  function selectSubject(subjectId) {
    if (!panelState.subjects.some((subject) => subject.id === subjectId)) return;
    panelState.activeSubjectId = subjectId;
    elements.status.textContent = "";
    renderTabs();
    renderSubject();
  }

  async function loadPanel() {
    try {
      const [roadmap, social] = await Promise.all([
        requestJson("/api/roadmap"),
        requestJson("/api/social/dashboard"),
      ]);
      panelState.subjects = roadmap.data.subjects || [];
      panelState.matches = social.data.matches || [];
      panelState.friends = social.data.friends || [];
      panelState.activeSubjectId =
        panelState.activeSubjectId || panelState.subjects[0]?.id || null;
      renderTabs();
      renderSubject();
    } catch (error) {
      elements.count.textContent = "ออฟไลน์";
      elements.tabs.innerHTML = "";
      elements.content.innerHTML = `<div class="buddy-panel-error">${escapeHtml(
        error.message
      )}<br><a class="buddy-empty-link" href="/study-buddy">เปิด Friend Hub</a></div>`;
    }
  }

  elements.tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-buddy-subject]");
    if (button) selectSubject(button.dataset.buddySubject);
  });

  elements.content.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-buddy-share]");
    if (!button) return;
    button.disabled = true;
    elements.status.textContent = "กำลังแชร์เส้นทาง...";
    try {
      const payload = await requestJson("/api/social/path-shares", {
        method: "POST",
        body: JSON.stringify({
          friendUserId: Number(button.dataset.buddyShare),
          message: `มาเรียน ${button.dataset.subjectName} ด้วยกันนะ`,
        }),
      });
      elements.status.textContent = payload.message || "แชร์เส้นทางแล้ว";
      button.textContent = "แชร์แล้ว ✓";
    } catch (error) {
      elements.status.textContent = error.message;
      button.disabled = false;
    }
  });

  document.addEventListener("DOMContentLoaded", loadPanel);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) loadPanel();
  });
})();
