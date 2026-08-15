"use strict";

const state = {
  dashboard: null,
  searchResults: [],
  activeGroupId: null,
  chatPollTimer: null,
  worldChatPollTimer: null,
};

const elements = {
  loading: document.querySelector("#loading"),
  feedback: document.querySelector("#feedback"),
  myAvatar: document.querySelector("#my-avatar"),
  myName: document.querySelector("#my-name"),
  myUid: document.querySelector("#my-uid"),
  copyUid: document.querySelector("#copy-uid"),
  careerName: document.querySelector("#career-name"),
  friendCount: document.querySelector("#friend-count"),
  matchCount: document.querySelector("#match-count"),
  groupCount: document.querySelector("#group-count"),
  unreadCount: document.querySelector("#unread-count"),
  activitySkill: document.querySelector("#activity-skill"),
  shareActivity: document.querySelector("#share-activity"),
  matchList: document.querySelector("#match-list"),
  notificationList: document.querySelector("#notification-list"),
  pathShareList: document.querySelector("#path-share-list"),
  groupForm: document.querySelector("#group-form"),
  groupName: document.querySelector("#group-name"),
  groupSkill: document.querySelector("#group-skill"),
  groupFriends: document.querySelector("#group-friends"),
  groupList: document.querySelector("#group-list"),
  joinableGroupList: document.querySelector("#joinable-group-list"),
  groupChatDialog: document.querySelector("#group-chat-dialog"),
  groupChatTitle: document.querySelector("#group-chat-title"),
  groupChatMeta: document.querySelector("#group-chat-meta"),
  groupChatMessages: document.querySelector("#group-chat-messages"),
  groupChatForm: document.querySelector("#group-chat-form"),
  groupChatInput: document.querySelector("#group-chat-input"),
  groupChatSend: document.querySelector("#group-chat-send"),
  groupChatClose: document.querySelector("#group-chat-close"),
  groupChatStatus: document.querySelector("#group-chat-status"),
  leaveGroup: document.querySelector("#leave-group"),
  requestList: document.querySelector("#request-list"),
  peopleSearch: document.querySelector("#people-search"),
  searchQuery: document.querySelector("#search-query"),
  searchResults: document.querySelector("#search-results"),
  friendList: document.querySelector("#friend-list"),
  worldChatMessages: document.querySelector("#world-chat-messages"),
  worldChatForm: document.querySelector("#world-chat-form"),
  worldChatInput: document.querySelector("#world-chat-input"),
  worldChatSend: document.querySelector("#world-chat-send"),
  worldChatStatus: document.querySelector("#world-chat-status"),
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
  return String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() || "")
    .join("") || "?";
}

function avatarContent(person) {
  if (person?.profileImage) {
    return `<img class="profile-avatar" src="${escapeHtml(person.profileImage)}" alt="" />`;
  }
  return escapeHtml(initials(person?.displayName));
}

function relativeTime(value) {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return "";
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  if (minutes < 1) return "เมื่อสักครู่";
  if (minutes < 60) return `${minutes} นาทีที่แล้ว`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ชั่วโมงที่แล้ว`;
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium" }).format(
    new Date(value)
  );
}

function showFeedback(message, isError = false) {
  elements.feedback.textContent = message;
  elements.feedback.classList.remove("hidden");
  elements.feedback.classList.toggle("error", isError);
  window.clearTimeout(showFeedback.timer);
  showFeedback.timer = window.setTimeout(
    () => elements.feedback.classList.add("hidden"),
    4200
  );
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Login required");
  }
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function empty(message) {
  return `<p class="empty">${escapeHtml(message)}</p>`;
}

function renderIdentity(data) {
  elements.myName.textContent = data.me.displayName;
  elements.myUid.textContent = data.me.uid;
  elements.myAvatar.innerHTML = avatarContent(data.me);
  elements.careerName.textContent = data.career.name;
  elements.friendCount.textContent = data.friends.length;
  elements.matchCount.textContent = data.matches.length;
  elements.groupCount.textContent = data.groups.length;
  elements.unreadCount.textContent = data.notifications.filter(
    (item) => !item.read
  ).length;
}

function renderSkillSelectors(data) {
  const statusLabel = {
    available: "พร้อมเรียน",
    completed: "เรียนแล้ว",
  };
  const options = data.shareableSkills
    .map(
      (skill) =>
        `<option value="${escapeHtml(skill.id)}">${escapeHtml(
          skill.thaiName
        )} · ${escapeHtml(statusLabel[skill.status] || skill.status)}</option>`
    )
    .join("");
  const fallback = '<option value="">ยังไม่มี Skill ที่พร้อมเรียน</option>';
  elements.activitySkill.innerHTML = options || fallback;
  elements.groupSkill.innerHTML = options || fallback;
  elements.shareActivity.disabled = !options || data.friends.length === 0;
}

function renderMatches(matches) {
  if (!matches.length) {
    elements.matchList.innerHTML = empty(
      "ยังไม่มีเพื่อนในเส้นทางเดียวกัน เพิ่มเพื่อนเพื่อเริ่มจับคู่จาก Skill Gap"
    );
    return;
  }
  elements.matchList.innerHTML = matches
    .map((match) => {
      const shared = match.sharedAvailableSkills.map(
        (skill) => `<span class="skill-chip">เรียนพร้อมกัน: ${escapeHtml(skill.thaiName)}</span>`
      );
      const help = match.buddyCanHelpWith.map(
        (skill) => `<span class="skill-chip help">ขอคำแนะนำ: ${escapeHtml(skill.thaiName)}</span>`
      );
      const reasons = [...shared, ...help].slice(0, 5).join("");
      return `
        <article class="match-card">
          <div class="mini-avatar">${avatarContent(match)}</div>
          <div>
            <h3 class="match-name">${escapeHtml(match.displayName)}</h3>
            <div class="match-meta">#${escapeHtml(match.uid)} · ระดับ ${escapeHtml(match.level)}</div>
          </div>
          <span class="score">ตรงกัน ${escapeHtml(match.matchScore)}%</span>
          <div class="match-reasons">${reasons || '<span class="skill-chip">เส้นทางเดียวกัน</span>'}</div>
        </article>`;
    })
    .join("");
}

function renderNotifications(notifications) {
  if (!notifications.length) {
    elements.notificationList.innerHTML = empty(
      "กิจกรรมของเพื่อนและคำเชิญกลุ่มติวจะแสดงที่นี่"
    );
    return;
  }
  elements.notificationList.innerHTML = notifications
    .map(
      (item) => `
        <article class="notification ${item.read ? "" : "unread"}">
          <div class="notification-owner">
            <span class="chat-avatar">${avatarContent(item.actor)}</span>
            <strong>${escapeHtml(item.title)}</strong>
          </div>
          <p>${escapeHtml(item.body)}</p>
          <footer>
            <span>${escapeHtml(relativeTime(item.createdAt))}</span>
            ${
              item.read
                ? ""
                : `<button type="button" data-read-notification="${escapeHtml(item.id)}">อ่านแล้ว</button>`
            }
          </footer>
        </article>`
    )
    .join("");
}

function renderPathShares(shares) {
  if (!shares.length) {
    elements.pathShareList.innerHTML = empty(
      "เมื่อเพื่อนแชร์ Skill Tree ให้คุณ เส้นทางจะปรากฏตรงนี้"
    );
    return;
  }
  elements.pathShareList.innerHTML = shares
    .map((share) => {
      const snapshot = share.snapshot || {};
      const progress = snapshot.progress?.career || 0;
      const next = snapshot.recommendedSkill?.thaiName || "จบเส้นทางแล้ว";
      return `
        <article class="path-share">
          <header>
            <span class="chat-avatar">${avatarContent(share.sender)}</span>
            <strong>${escapeHtml(share.sender.displayName)}</strong>
            <small>${escapeHtml(relativeTime(share.createdAt))}</small>
          </header>
          <p>${escapeHtml(share.message || snapshot.career?.name || "แชร์เส้นทางการเรียน")}</p>
          <div class="progress-mini" aria-label="ความคืบหน้า ${escapeHtml(progress)} เปอร์เซ็นต์">
            <span style="width:${Math.max(0, Math.min(100, Number(progress) || 0))}%"></span>
          </div>
          <div class="path-next">ถัดไป: ${escapeHtml(next)} · ${escapeHtml(progress)}%</div>
        </article>`;
    })
    .join("");
}

function renderGroupForm(data) {
  if (!data.friends.length) {
    elements.groupFriends.innerHTML = '<span class="muted">เพิ่มเพื่อนก่อนสร้างกลุ่มติว</span>';
  } else {
    elements.groupFriends.innerHTML = data.friends
      .map(
        (friend) => `
          <label>
            <input type="checkbox" name="group-friend" value="${escapeHtml(friend.id)}" />
            ${escapeHtml(friend.displayName)}
          </label>`
      )
      .join("");
  }
  const submit = elements.groupForm.querySelector('button[type="submit"]');
  submit.disabled = !data.friends.length || !data.shareableSkills.length;
}

function renderGroups(groups, myId) {
  if (!groups.length) {
    elements.groupList.innerHTML = empty("ยังไม่มีกลุ่มติว ลองชวนเพื่อนที่เรียน Skill เดียวกัน");
    return;
  }
  elements.groupList.innerHTML = groups
    .map(
      (group) => `
        <article class="group-row">
          <div>
            <strong>${escapeHtml(group.name)}</strong>
            <small>${escapeHtml(group.focusSkillName)} · ${group.ownerUserId === myId ? "คุณเป็นเจ้าของ" : "สมาชิก"}</small>
          </div>
          <div class="group-row-actions">
            <span class="member-count">${escapeHtml(group.memberCount)} คน</span>
            <button class="button ghost" type="button" data-open-group-chat="${escapeHtml(group.id)}">
              เปิดแชต
            </button>
          </div>
        </article>`
    )
    .join("");
}

function renderJoinableGroups(groups) {
  if (!groups.length) {
    elements.joinableGroupList.innerHTML = empty(
      "ยังไม่มีกลุ่มของเพื่อนที่เปิดให้คุณเข้าร่วม"
    );
    return;
  }
  elements.joinableGroupList.innerHTML = groups
    .map(
      (group) => `
        <article class="group-row joinable-group-row">
          <div>
            <strong>${escapeHtml(group.name)}</strong>
            <small>${escapeHtml(group.focusSkillName)} · โดย ${escapeHtml(
              group.owner?.displayName || "เพื่อน"
            )}</small>
          </div>
          <div class="group-row-actions">
            <span class="member-count">${escapeHtml(group.memberCount)} คน</span>
            <button class="button primary" type="button" data-join-group="${escapeHtml(group.id)}">
              เข้าร่วม
            </button>
          </div>
        </article>`
    )
    .join("");
}

function renderGroupMessages(messages) {
  if (!messages.length) {
    elements.groupChatMessages.innerHTML = empty(
      "ยังไม่มีข้อความ เริ่มชวนเพื่อนวางแผนการเรียนได้เลย"
    );
    return;
  }
  const myId = state.dashboard.me.id;
  elements.groupChatMessages.innerHTML = messages
    .map(
      (message) => `
        <article class="group-message ${message.sender.id === myId ? "mine" : ""}">
          <div class="group-message-meta">
            <span class="message-owner">
              <span class="chat-avatar">${avatarContent(message.sender)}</span>
              <strong>${escapeHtml(
                message.sender.id === myId ? "คุณ" : message.sender.displayName
              )}</strong>
            </span>
            <time datetime="${escapeHtml(message.createdAt)}">${escapeHtml(
              relativeTime(message.createdAt)
            )}</time>
          </div>
          <p>${escapeHtml(message.content)}</p>
        </article>`
    )
    .join("");
  elements.groupChatMessages.scrollTop = elements.groupChatMessages.scrollHeight;
}

function renderWorldChatMessages(messages) {
  if (!messages.length) {
    elements.worldChatMessages.innerHTML = empty(
      "ยังไม่มีข้อความ เป็นคนแรกที่ทักทายผู้เรียนทุกคนได้เลย"
    );
    return;
  }
  const myId = state.dashboard?.me?.id;
  const shouldStickToBottom =
    elements.worldChatMessages.scrollHeight -
      elements.worldChatMessages.scrollTop -
      elements.worldChatMessages.clientHeight <
    80;
  elements.worldChatMessages.innerHTML = messages
    .map(
      (message) => `
        <article class="world-chat-message ${message.sender.id === myId ? "mine" : ""}">
          <span class="chat-avatar">${avatarContent(message.sender)}</span>
          <div class="world-chat-bubble">
            <div class="world-chat-meta">
              <strong>${escapeHtml(
                message.sender.id === myId ? "คุณ" : message.sender.displayName
              )}</strong>
              <small>#${escapeHtml(message.sender.uid)}</small>
              <time datetime="${escapeHtml(message.createdAt)}">${escapeHtml(
                relativeTime(message.createdAt)
              )}</time>
            </div>
            <p>${escapeHtml(message.content)}</p>
          </div>
        </article>`
    )
    .join("");
  if (shouldStickToBottom) {
    elements.worldChatMessages.scrollTop = elements.worldChatMessages.scrollHeight;
  }
}

async function loadWorldChat(showLoading = false) {
  if (showLoading) {
    elements.worldChatMessages.innerHTML =
      '<div class="empty">กำลังโหลด Global Chat...</div>';
  }
  try {
    const payload = await apiRequest("/api/social/world-chat/messages");
    renderWorldChatMessages(payload.data.messages || []);
    elements.worldChatStatus.textContent = "";
  } catch (error) {
    elements.worldChatStatus.textContent = error.message;
  }
}

function startWorldChatPolling() {
  window.clearInterval(state.worldChatPollTimer);
  state.worldChatPollTimer = window.setInterval(
    () => loadWorldChat(false),
    5000
  );
}

async function loadGroupMessages(showLoading = false) {
  const groupId = state.activeGroupId;
  if (!groupId) return;
  if (showLoading) {
    elements.groupChatMessages.innerHTML =
      '<div class="empty">กำลังโหลดข้อความ...</div>';
  }
  try {
    const payload = await apiRequest(
      `/api/social/study-groups/${encodeURIComponent(groupId)}/messages`
    );
    if (state.activeGroupId !== groupId) return;
    const { group, messages } = payload.data;
    elements.groupChatTitle.textContent = group.name;
    elements.groupChatMeta.textContent = `${group.focusSkillName} · ${group.memberCount} คน`;
    renderGroupMessages(messages);
  } catch (error) {
    if (state.activeGroupId === groupId) {
      elements.groupChatStatus.textContent = error.message;
    }
  }
}

function stopChatPolling() {
  window.clearInterval(state.chatPollTimer);
  state.chatPollTimer = null;
}

function closeGroupChat() {
  stopChatPolling();
  state.activeGroupId = null;
  elements.groupChatStatus.textContent = "";
  elements.groupChatInput.value = "";
  if (typeof elements.groupChatDialog.close === "function") {
    elements.groupChatDialog.close();
  } else {
    elements.groupChatDialog.removeAttribute("open");
  }
}

async function openGroupChat(groupId) {
  const group = state.dashboard.groups.find(
    (item) => String(item.id) === String(groupId)
  );
  if (!group) return;
  state.activeGroupId = group.id;
  elements.groupChatTitle.textContent = group.name;
  elements.groupChatMeta.textContent = `${group.focusSkillName} · ${group.memberCount} คน`;
  elements.groupChatStatus.textContent = "";
  if (typeof elements.groupChatDialog.showModal === "function") {
    elements.groupChatDialog.showModal();
  } else {
    elements.groupChatDialog.setAttribute("open", "");
  }
  await loadGroupMessages(true);
  stopChatPolling();
  state.chatPollTimer = window.setInterval(() => loadGroupMessages(false), 5000);
}

function renderRequests(requests) {
  if (!requests.length) {
    elements.requestList.innerHTML = "";
    return;
  }
  elements.requestList.innerHTML = requests
    .map(
      (item) => `
        <article class="request-card">
          <div class="mini-avatar">${avatarContent(item)}</div>
          <div><strong>${escapeHtml(item.displayName)}</strong><small>#${escapeHtml(item.uid)}</small></div>
          <div class="request-actions">
            <button class="button ghost" type="button" data-request-id="${escapeHtml(item.requestId)}" data-accept="true">รับ</button>
            <button class="button ghost danger" type="button" data-request-id="${escapeHtml(item.requestId)}" data-accept="false">ปฏิเสธ</button>
          </div>
        </article>`
    )
    .join("");
}

function renderFriends(friends) {
  if (!friends.length) {
    elements.friendList.innerHTML = empty(
      "ยังไม่มีเพื่อน ค้นหาด้วย Buddy ID ที่แสดงบนการ์ดของแต่ละคน"
    );
    return;
  }
  elements.friendList.innerHTML = friends
    .map(
      (friend) => `
        <article class="friend-card">
          <div class="mini-avatar">${avatarContent(friend)}</div>
          <div>
            <strong>${escapeHtml(friend.displayName)}</strong>
            <small>#${escapeHtml(friend.uid)} · ${escapeHtml(friend.careerName)}</small>
          </div>
          <footer>
            <button class="button ghost" type="button" data-share-path="${escapeHtml(friend.id)}">แชร์เส้นทาง</button>
          </footer>
        </article>`
    )
    .join("");
}

function renderSearchResults(results) {
  elements.searchResults.classList.remove("hidden");
  if (!results.length) {
    elements.searchResults.innerHTML = empty("ไม่พบผู้เรียนที่ตรงกับการค้นหา");
    return;
  }
  const statusLabel = {
    accepted: "เป็นเพื่อนแล้ว",
    outgoing_pending: "ส่งคำขอแล้ว",
    incoming_pending: "มีคำขอรอตอบรับ",
    blocked: "ไม่สามารถเพิ่มได้",
  };
  elements.searchResults.innerHTML = results
    .map((person) => {
      const canAdd = person.friendshipStatus === "none";
      return `
        <article class="person-row">
          <div class="mini-avatar">${avatarContent(person)}</div>
          <div>
            <strong>${escapeHtml(person.displayName)}</strong>
            <small>#${escapeHtml(person.uid)} · ${escapeHtml(person.careerName)}</small>
          </div>
          ${
            canAdd
              ? `<button class="button ghost" type="button" data-add-uid="${escapeHtml(person.uid)}">เพิ่มเพื่อน</button>`
              : `<small>${escapeHtml(statusLabel[person.friendshipStatus] || person.friendshipStatus)}</small>`
          }
        </article>`;
    })
    .join("");
}

function renderDashboard() {
  const data = state.dashboard;
  renderIdentity(data);
  renderSkillSelectors(data);
  renderMatches(data.matches);
  renderNotifications(data.notifications);
  renderPathShares(data.pathShares);
  renderGroupForm(data);
  renderGroups(data.groups, data.me.id);
  renderJoinableGroups(data.joinableGroups || []);
  renderRequests(data.incomingRequests);
  renderFriends(data.friends);
}

async function loadDashboard(showLoading = false) {
  if (showLoading) elements.loading.classList.remove("hidden");
  try {
    state.dashboard = (await apiRequest("/api/social/dashboard")).data;
    renderDashboard();
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    elements.loading.classList.add("hidden");
  }
}

elements.copyUid.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.dashboard.me.uid);
    showFeedback("คัดลอก Buddy ID แล้ว");
  } catch (_) {
    showFeedback(`Buddy ID: ${state.dashboard.me.uid}`);
  }
});

elements.shareActivity.addEventListener("click", async () => {
  elements.shareActivity.disabled = true;
  try {
    const payload = await apiRequest("/api/social/activity", {
      method: "POST",
      body: JSON.stringify({ skillId: elements.activitySkill.value }),
    });
    showFeedback(payload.message);
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    elements.shareActivity.disabled = false;
  }
});

elements.groupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const memberUserIds = [...document.querySelectorAll('[name="group-friend"]:checked')]
    .map((input) => Number(input.value));
  if (!memberUserIds.length) {
    showFeedback("เลือกเพื่อนอย่างน้อย 1 คนเพื่อสร้างกลุ่มติว", true);
    return;
  }
  const submit = elements.groupForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const payload = await apiRequest("/api/social/study-groups", {
      method: "POST",
      body: JSON.stringify({
        name: elements.groupName.value.trim(),
        focusSkillId: elements.groupSkill.value,
        memberUserIds,
      }),
    });
    elements.groupForm.reset();
    showFeedback(payload.message);
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

elements.groupList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-group-chat]");
  if (button) openGroupChat(button.dataset.openGroupChat);
});

elements.joinableGroupList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-join-group]");
  if (!button) return;
  button.disabled = true;
  try {
    const payload = await apiRequest(
      `/api/social/study-groups/${encodeURIComponent(button.dataset.joinGroup)}/join`,
      { method: "POST", body: "{}" }
    );
    showFeedback(payload.message);
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
    button.disabled = false;
  }
});

elements.groupChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeGroupId) return;
  const content = elements.groupChatInput.value.trim();
  if (!content) return;
  elements.groupChatSend.disabled = true;
  elements.groupChatStatus.textContent = "กำลังส่ง...";
  try {
    await apiRequest(
      `/api/social/study-groups/${encodeURIComponent(state.activeGroupId)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ content }),
      }
    );
    elements.groupChatInput.value = "";
    elements.groupChatStatus.textContent = "";
    await loadGroupMessages(false);
  } catch (error) {
    elements.groupChatStatus.textContent = error.message;
  } finally {
    elements.groupChatSend.disabled = false;
    elements.groupChatInput.focus();
  }
});

elements.worldChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = elements.worldChatInput.value.trim();
  if (!content) return;
  elements.worldChatSend.disabled = true;
  elements.worldChatStatus.textContent = "กำลังส่ง...";
  try {
    await apiRequest("/api/social/world-chat/messages", {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    elements.worldChatInput.value = "";
    await loadWorldChat(false);
  } catch (error) {
    elements.worldChatStatus.textContent = error.message;
  } finally {
    elements.worldChatSend.disabled = false;
    elements.worldChatInput.focus();
  }
});

elements.leaveGroup.addEventListener("click", async () => {
  if (!state.activeGroupId) return;
  const group = state.dashboard.groups.find(
    (item) => String(item.id) === String(state.activeGroupId)
  );
  const ownerNote =
    group?.ownerUserId === state.dashboard.me.id
      ? " ระบบจะโอนเจ้าของให้สมาชิกคนถัดไป หรือปิดกลุ่มหากไม่มีสมาชิกเหลือ"
      : "";
  if (!window.confirm(`ต้องการออกจาก ${group?.name || "กลุ่มนี้"} หรือไม่?${ownerNote}`)) {
    return;
  }
  elements.leaveGroup.disabled = true;
  try {
    const payload = await apiRequest(
      `/api/social/study-groups/${encodeURIComponent(state.activeGroupId)}/leave`,
      { method: "POST", body: "{}" }
    );
    closeGroupChat();
    showFeedback(payload.message);
    await loadDashboard();
  } catch (error) {
    elements.groupChatStatus.textContent = error.message;
  } finally {
    elements.leaveGroup.disabled = false;
  }
});

elements.groupChatClose.addEventListener("click", closeGroupChat);
elements.groupChatDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeGroupChat();
});

elements.peopleSearch.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const query = encodeURIComponent(elements.searchQuery.value.trim());
    state.searchResults = (await apiRequest(`/api/social/people?q=${query}`)).data;
    renderSearchResults(state.searchResults);
  } catch (error) {
    showFeedback(error.message, true);
  }
});

elements.searchResults.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-add-uid]");
  if (!button) return;
  button.disabled = true;
  try {
    const payload = await apiRequest("/api/social/friend-requests", {
      method: "POST",
      body: JSON.stringify({ uid: button.dataset.addUid }),
    });
    showFeedback(payload.message);
    elements.searchResults.classList.add("hidden");
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
    button.disabled = false;
  }
});

elements.requestList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-request-id]");
  if (!button) return;
  button.disabled = true;
  try {
    const payload = await apiRequest(
      `/api/social/friend-requests/${encodeURIComponent(button.dataset.requestId)}/response`,
      {
        method: "POST",
        body: JSON.stringify({ accept: button.dataset.accept === "true" }),
      }
    );
    showFeedback(payload.message);
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
    button.disabled = false;
  }
});

elements.friendList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-share-path]");
  if (!button) return;
  const message = window.prompt("เขียนข้อความสั้น ๆ ให้เพื่อน (เว้นว่างได้)", "มาเรียนเส้นทางนี้ด้วยกันนะ") ?? null;
  if (message === null) return;
  button.disabled = true;
  try {
    const payload = await apiRequest("/api/social/path-shares", {
      method: "POST",
      body: JSON.stringify({
        friendUserId: Number(button.dataset.sharePath),
        message: message.trim(),
      }),
    });
    showFeedback(payload.message);
  } catch (error) {
    showFeedback(error.message, true);
  } finally {
    button.disabled = false;
  }
});

elements.notificationList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-read-notification]");
  if (!button) return;
  try {
    await apiRequest(
      `/api/social/notifications/${encodeURIComponent(button.dataset.readNotification)}/read`,
      { method: "POST", body: "{}" }
    );
    await loadDashboard();
  } catch (error) {
    showFeedback(error.message, true);
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([loadDashboard(true), loadWorldChat(true)]);
  startWorldChatPolling();
});

window.addEventListener("beforeunload", () => {
  stopChatPolling();
  window.clearInterval(state.worldChatPollTimer);
});
