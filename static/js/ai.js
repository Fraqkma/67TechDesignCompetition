"use strict";

const AIState = {
  apiKey: localStorage.getItem("skillmap-ai-key") || "",
};

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

  const payload = await response.json().catch(() => ({
    ok: false,
    error: "Server did not return valid JSON",
  }));

  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }

  return payload;
}

function setAiKey() {
  const input = document.querySelector("#ai-api-key");
  if (!input) return;

  const key = input.value.trim();
  AIState.apiKey = key;
  localStorage.setItem("skillmap-ai-key", key);

  if (!key) {
    window.alert("กรุณาใส่ API key ก่อนใช้งาน AI Assistant");
    return;
  }

  showAiStatus("บันทึก API key แล้วพร้อมใช้งาน AI Assistant");
}

function showAiStatus(message) {
  const summary = document.querySelector("#ai-summary");
  if (!summary) return;
  summary.innerHTML = `<p>${escapeHtml(message)}</p>`;
}

function appendAiMessage(role, text) {
  const box = document.querySelector("#ai-chat-box");
  if (!box) return;

  const message = document.createElement("div");
  message.className = `ai-message ${role}`;
  message.innerHTML = `<strong>${role === "bot" ? "AI" : "You"}:</strong><span>${escapeHtml(text)}</span>`;
  box.appendChild(message);
  box.scrollTop = box.scrollHeight;
}

async function askAi() {
  const question = document.querySelector("#ai-question");
  if (!question) return;

  const text = question.value.trim();
  if (!text) {
    showAiStatus("กรุณาพิมพ์คำถามก่อนส่ง");
    return;
  }

  if (!AIState.apiKey) {
    showAiStatus("ยังไม่มี API key กรุณาใส่ก่อนใช้ AI Assistant");
    return;
  }

  appendAiMessage("user", text);
  question.value = "";

  showAiStatus("กำลังวิเคราะห์ roadmap และตอบคำถามของคุณ...");

  try {
    const payload = await apiRequest("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({
        message: text,
        apiKey: AIState.apiKey,
      }),
    });

    appendAiMessage("bot", payload.data.answer);
    showAiStatus("AI ได้ตอบคำถามตามข้อมูล graph ของโปรเจกต์แล้ว");
  } catch (error) {
    appendAiMessage("bot", `เกิดข้อผิดพลาด: ${error.message}`);
    showAiStatus(error.message);
  }
}

async function refreshAiRecommendation() {
  const summary = document.querySelector("#ai-summary");
  if (!summary) return;

  try {
    const payload = await apiRequest("/api/ai/recommendation", {
      method: "POST",
      body: JSON.stringify({
        subject: "all",
        apiKey: AIState.apiKey,
      }),
    });

    const recommendation = payload.data.recommendation;
    const graphSummary = payload.data.graphSummary;
    const text = payload.data.aiExplanation || payload.data.fallbackExplanation;

    const recommendationName = recommendation
      ? payload.data.recommendationName
      : "ไม่มี Skill ที่พร้อมเรียน";

    summary.innerHTML = `
      <p><strong>Recommendation:</strong> ${escapeHtml(recommendationName)}</p>
      <p>${escapeHtml(text)}</p>
      <p><strong>Progress:</strong> ${graphSummary.progress.career}% · ${graphSummary.completedCount}/${graphSummary.totalCount} skills</p>
    `;
  } catch (error) {
    showAiStatus(error.message);
  }
}

function initializeAiAssistant() {
  const apiKeyInput = document.querySelector("#ai-api-key");
  const saveButton = document.querySelector("#save-ai-key");
  const askButton = document.querySelector("#ask-ai-button");

  if (apiKeyInput) {
    apiKeyInput.value = AIState.apiKey;
  }

  if (saveButton) {
    saveButton.addEventListener("click", setAiKey);
  }

  if (askButton) {
    askButton.addEventListener("click", askAi);
  }

  if (apiKeyInput) {
    apiKeyInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        askAi();
      }
    });
  }

  refreshAiRecommendation();
}

document.addEventListener("DOMContentLoaded", initializeAiAssistant);
