"use strict";

const AIState = { history: [], analysis: null, focusSkillId: null };

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({ ok: false, error: "Server did not return valid JSON" }));
  if (!response.ok || !payload.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function showAiStatus(message) {
  const summary = document.querySelector("#ai-summary");
  if (summary) summary.innerHTML = `<p>${escapeHtml(message)}</p>`;
}

function appendAiMessage(role, text) {
  const box = document.querySelector("#ai-chat-box");
  if (!box) return;
  const item = document.createElement("div");
  item.className = `ai-message ${role === "assistant" ? "bot" : "user"}`;
  item.innerHTML = `<strong>${role === "assistant" ? "AI" : "You"}:</strong><span>${escapeHtml(text)}</span>`;
  box.appendChild(item);
  box.scrollTop = box.scrollHeight;
}

function recommendedSkillLabel(skill) {
  if (!skill) return "ไม่มี Skill ที่แนะนำเพิ่ม — ถามเรื่องการเรียนอื่นได้เลย";
  return `Skill ที่แนะนำ: ${skill.name} (${skill.thaiName})`;
}

async function analyzeWith(targetSkillId) {
  const payload = await apiRequest("/api/ai/analyze", {
    method: "POST",
    body: JSON.stringify({ subject: "all", targetSkillId }),
  });
  return payload.data;
}

function clearChatBox() {
  const box = document.querySelector("#ai-chat-box");
  if (box) box.innerHTML = "";
}

async function loadTeachingContext() {
  try {
    const payload = await apiRequest("/api/ai/analyze", { method: "POST", body: JSON.stringify({ subject: "all" }) });
    AIState.analysis = payload.data;
    const skill = payload.data.nextSkill;
    showAiStatus(
      skill
        ? `${recommendedSkillLabel(skill)} — ${payload.data.reason} (ถามเรื่องอะไรก็ได้)`
        : "คุณเรียนครบทุก Skill ในแผนปัจจุบันแล้ว — ถามเรื่องการเรียนอะไรก็ได้"
    );
  } catch (error) {
    showAiStatus(`ไม่สามารถเตรียมข้อมูลได้: ${error.message}`);
  }
}

async function focusOnSkill(skillId, skillName) {
  if (skillId === AIState.focusSkillId) return;
  AIState.focusSkillId = skillId;
  AIState.history = [];
  clearChatBox();
  appendAiMessage("assistant", `ตอนนี้เราจะโฟกัสที่: ${skillName} — ถามเรื่อง Skill นี้ได้เลย`);
  showAiStatus(`กำลังโหลดข้อมูลของ ${skillName}...`);
  try {
    const data = await analyzeWith(skillId);
    AIState.analysis = data;
    const next = data.nextSkill;
    const focusLabel =
      next && next.id !== skillId ? `${skillName} (ขั้นแรก: ${next.name})` : skillName;
    showAiStatus(`${focusLabel} — ${data.reason}`);
  } catch (error) {
    showAiStatus(`โหลดข้อมูล Skill นี้ไม่สำเร็จ: ${error.message}`);
  }
}

function clearFocus() {
  AIState.focusSkillId = null;
  AIState.history = [];
  clearChatBox();
  loadTeachingContext();
}

async function askAi() {
  const input = document.querySelector("#ai-question");
  const button = document.querySelector("#ask-ai-button");
  const message = input?.value.trim();
  if (!message) return showAiStatus("กรุณาพิมพ์คำถามก่อนส่ง");

  appendAiMessage("user", message);
  AIState.history.push({ role: "user", content: message });
  input.value = "";
  button.disabled = true;
  showAiStatus("AI กำลังหาคำตอบ...");
  try {
    const payload = await apiRequest("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        history: AIState.history.slice(0, -1),
        targetSkillId: AIState.focusSkillId,
      }),
    });
    const answer = payload.data.answer;
    AIState.history.push({ role: "assistant", content: answer });
    appendAiMessage("assistant", answer);
    showAiStatus(
      payload.data.focusedSkill
        ? `โฟกัสที่: ${payload.data.focusedSkill.name} (${payload.data.focusedSkill.thaiName})`
        : recommendedSkillLabel(payload.data.recommendedSkill)
    );
  } catch (error) {
    appendAiMessage("assistant", `เกิดข้อผิดพลาด: ${error.message}`);
    showAiStatus(error.message);
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#ask-ai-button")?.addEventListener("click", askAi);
  document.querySelector("#ai-question")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) askAi();
  });
  window.addEventListener("ai:focus-skill", (event) => {
    const { skillId, name } = event.detail || {};
    if (skillId) focusOnSkill(skillId, name || skillId);
  });
  window.addEventListener("ai:clear-focus", clearFocus);
  loadTeachingContext();
});
