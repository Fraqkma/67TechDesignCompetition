"use strict";

const AIState = { history: [], analysis: null };

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

async function loadTeachingContext() {
  try {
    const payload = await apiRequest("/api/ai/analyze", { method: "POST", body: JSON.stringify({ subject: "all" }) });
    AIState.analysis = payload.data;
    const skill = payload.data.nextSkill;
    if (!skill) {
      showAiStatus("คุณเรียนครบทุก Skill ในแผนปัจจุบันแล้ว");
      return;
    }
    showAiStatus(`กำลังเรียน: ${skill.name} (${skill.thaiName}) — ${payload.data.reason}`);
  } catch (error) {
    showAiStatus(`ไม่สามารถเตรียมบทเรียนได้: ${error.message}`);
  }
}

async function askAi() {
  const input = document.querySelector("#ai-question");
  const button = document.querySelector("#ask-ai-button");
  const message = input?.value.trim();
  if (!message) return showAiStatus("กรุณาพิมพ์คำถามก่อนส่ง");
  if (!AIState.analysis?.nextSkill) return showAiStatus("ยังไม่มี Skill ที่ระบบแนะนำให้เรียน");

  appendAiMessage("user", message);
  AIState.history.push({ role: "user", content: message });
  input.value = "";
  button.disabled = true;
  showAiStatus("AI กำลังเตรียมคำอธิบาย...");
  try {
    const payload = await apiRequest("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, history: AIState.history.slice(0, -1) }),
    });
    const answer = payload.data.answer;
    AIState.history.push({ role: "assistant", content: answer });
    appendAiMessage("assistant", answer);
    showAiStatus(`กำลังเรียน: ${payload.data.recommendedSkill.name}`);
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
  loadTeachingContext();
});
