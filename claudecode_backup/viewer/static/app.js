"use strict";

const $ = (sel) => document.querySelector(sel);
const projectButton = $("#project-button");
const projectButtonLabel = $("#project-button-label");
const projectMenu = $("#project-menu");
const sessionList = $("#session-list");
const chat = $("#chat");
const chatTitle = $("#chat-title");
const chatMeta = $("#chat-meta");
const imageJump = $("#image-jump");
const imageJumpLabel = $("#image-jump-label");
const fontSmaller = $("#font-smaller");
const fontLarger = $("#font-larger");
const fontSizeLabel = $("#font-size-label");
const projectsDirPath = $("#projects-dir-path");
const projectsDirChange = $("#projects-dir-change");

let currentProject = null;
let currentSessionId = null;
let projectsCache = [];
// Indices into the chat container of every image-bearing .msg element.
let imageMsgIndex = -1;

// ---------- chat font size ----------
const FONT_KEY = "claudecode-backup.chat-font-size";
const FONT_MIN = 11, FONT_MAX = 22, FONT_DEFAULT = 14;
function applyChatFontSize(px) {
  const clamped = Math.max(FONT_MIN, Math.min(FONT_MAX, px));
  document.documentElement.style.setProperty("--chat-font-size", `${clamped}px`);
  fontSizeLabel.textContent = `${clamped}px`;
  try { localStorage.setItem(FONT_KEY, String(clamped)); } catch (_) {}
}
function loadChatFontSize() {
  let v = FONT_DEFAULT;
  try {
    const stored = parseInt(localStorage.getItem(FONT_KEY) || "", 10);
    if (!Number.isNaN(stored)) v = stored;
  } catch (_) {}
  applyChatFontSize(v);
}
fontSmaller.addEventListener("click", () => {
  const cur = parseInt(getComputedStyle(document.documentElement)
    .getPropertyValue("--chat-font-size"), 10) || FONT_DEFAULT;
  applyChatFontSize(cur - 1);
});
fontLarger.addEventListener("click", () => {
  const cur = parseInt(getComputedStyle(document.documentElement)
    .getPropertyValue("--chat-font-size"), 10) || FONT_DEFAULT;
  applyChatFontSize(cur + 1);
});

// ---------- markdown / code highlighting ----------
marked.setOptions({
  gfm: true,
  breaks: false,
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value; }
      catch (_) {}
    }
    return hljs.highlightAuto(code).value;
  },
});

function renderMarkdown(text) {
  return marked.parse(text || "");
}

// ---------- helpers ----------
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function formatTimestamp(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function jsonPretty(v) {
  try { return JSON.stringify(v, null, 2); }
  catch (_) { return String(v); }
}

// ---------- block renderers ----------
function renderBlock(block) {
  switch (block.type) {
    case "text":
      return `<div class="text">${renderMarkdown(block.text)}</div>`;

    case "tool_use": {
      const argsPreview = jsonPretty(block.input);
      return `
        <details class="block tool_use">
          <summary>
            <span class="tag">tool_use</span>
            <span class="name">${escapeHtml(block.name || "tool")}</span>
          </summary>
          <div class="content"><pre>${escapeHtml(argsPreview)}</pre></div>
        </details>`;
    }

    case "tool_result": {
      const errClass = block.is_error ? " error" : "";
      const tagText = block.is_error ? "tool_result · error" : "tool_result";
      return `
        <details class="block tool_result${errClass}">
          <summary>
            <span class="tag">${escapeHtml(tagText)}</span>
          </summary>
          <div class="content"><pre>${escapeHtml(block.text || "")}</pre></div>
        </details>`;
    }

    case "thinking":
      return `
        <details class="block thinking">
          <summary><span class="tag">thinking</span></summary>
          <div class="content"><pre>${escapeHtml(block.text || "")}</pre></div>
        </details>`;

    case "image": {
      const mt = block.media_type || "image/png";
      const isUrl = block.text === "url";
      const src = isUrl ? block.data : `data:${mt};base64,${block.data}`;
      return `<div class="block image"><img src="${escapeHtml(src)}" alt="image" loading="lazy"></div>`;
    }

    default:
      return `<pre class="raw">${escapeHtml(block.text || "")}</pre>`;
  }
}

function renderMessage(msg) {
  const blocks = msg.blocks.map(renderBlock).join("\n");
  return `
    <div class="msg ${msg.role}">
      <div class="turn-meta">
        <span class="role-tag">${msg.role}</span>
        <span class="ts">${escapeHtml(formatTimestamp(msg.timestamp))}</span>
      </div>
      <div class="body">${blocks}</div>
    </div>`;
}

// ---------- API ----------
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ---------- bootstrap ----------
function renderProjectMenu() {
  projectMenu.innerHTML = projectsCache.map(
    (p) => `
      <div class="picker-item${p.name === currentProject ? " active" : ""}"
           data-name="${escapeHtml(p.name)}">
        <span class="cwd">${escapeHtml(p.cwd || p.name)}</span>
        <span class="count">${p.session_count} 个会话</span>
      </div>`
  ).join("");
  projectMenu.querySelectorAll(".picker-item").forEach((el) => {
    el.addEventListener("click", () => {
      closeProjectMenu();
      const name = el.dataset.name;
      if (name && name !== currentProject) {
        loadSessions(name);
        const p = projectsCache.find((x) => x.name === name);
        if (p) projectButtonLabel.textContent = p.cwd || p.name;
      }
    });
  });
}

function openProjectMenu() {
  projectMenu.hidden = false;
  // re-render to refresh `.active` highlight
  renderProjectMenu();
  // close on next outside-click
  setTimeout(() => document.addEventListener("click", outsideClickHandler), 0);
}
function closeProjectMenu() {
  projectMenu.hidden = true;
  document.removeEventListener("click", outsideClickHandler);
}
function outsideClickHandler(e) {
  if (!projectMenu.contains(e.target) && e.target !== projectButton) {
    closeProjectMenu();
  }
}

projectButton.addEventListener("click", () => {
  if (projectMenu.hidden) openProjectMenu();
  else closeProjectMenu();
});

// Cycle through every <img> in the chat. Each click advances to the next one
// (wraps around) and scrolls it into view with a brief highlight.
imageJump.addEventListener("click", () => {
  const imgs = chat.querySelectorAll(".block.image");
  if (imgs.length === 0) return;
  imageMsgIndex = (imageMsgIndex + 1) % imgs.length;
  const target = imgs[imageMsgIndex];
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.remove("flash");
  // re-trigger animation
  void target.offsetWidth;
  target.classList.add("flash");
  imageJumpLabel.textContent = `${imageMsgIndex + 1} / ${imgs.length}`;
});

async function loadProjectsDir() {
  try {
    const cfg = await api("/api/projects-dir");
    if (cfg && cfg.path) {
      projectsDirPath.textContent = cfg.path;
      projectsDirPath.title = cfg.path;
    }
  } catch (_) {}
}

projectsDirChange.addEventListener("click", async () => {
  projectsDirChange.disabled = true;
  projectsDirChange.textContent = "选择中…";
  try {
    const r = await fetch("/api/projects-dir", { method: "POST" });
    if (!r.ok) {
      const err = await r.text().catch(() => "");
      alert(`切换失败: ${err || r.status}`);
      return;
    }
    const data = await r.json();
    if (!data.path) return;  // user cancelled
    projectsDirPath.textContent = data.path;
    projectsDirPath.title = data.path;
    // Reload projects with the new dir
    closeProjectMenu();
    chat.innerHTML = "";
    chat.classList.add("empty");
    chatTitle.textContent = "选择左侧的会话";
    chatMeta.textContent = "";
    imageJump.hidden = true;
    sessionList.innerHTML = "";
    await loadProjects();
  } finally {
    projectsDirChange.disabled = false;
    projectsDirChange.textContent = "更换";
  }
});

async function loadProjects() {
  const projects = await api("/api/projects");
  projectsCache = projects;
  if (projects.length === 0) {
    chatTitle.textContent = "没有可用的项目";
    projectButtonLabel.textContent = "(无项目)";
    return;
  }
  projectButtonLabel.textContent = projects[0].cwd || projects[0].name;
  renderProjectMenu();
  await loadSessions(projects[0].name);
}

async function loadSessions(projectName) {
  currentProject = projectName;
  currentSessionId = null;
  const sessions = await api(`/api/projects/${encodeURIComponent(projectName)}/sessions`);
  sessionList.innerHTML = sessions.map(
    (s) => `
      <div class="session-item" data-sid="${escapeHtml(s.session_id)}">
        <div class="title">${escapeHtml(s.title)}</div>
        <div class="meta">
          <span>${s.message_count} 条</span>
          <span>${escapeHtml(formatTimestamp(s.last_modified))}</span>
        </div>
      </div>`
  ).join("");
  sessionList.querySelectorAll(".session-item").forEach((el) => {
    el.addEventListener("click", () => loadSession(el.dataset.sid));
  });
  if (sessions.length > 0) loadSession(sessions[0].session_id);
  else {
    chat.innerHTML = "";
    chat.classList.add("empty");
    chatTitle.textContent = "(该项目下没有会话)";
    chatMeta.textContent = "";
  }
}

async function loadSession(sid) {
  currentSessionId = sid;
  sessionList.querySelectorAll(".session-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.sid === sid);
  });
  chat.classList.remove("empty");
  chat.innerHTML = `<div class="msg"><div class="body">加载中…</div></div>`;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(currentProject)}`
      + `/sessions/${encodeURIComponent(sid)}`
    );
    chatTitle.textContent = data.cwd
      ? `${data.cwd}  ·  ${data.session_id}`
      : data.session_id;
    const imgCount = data.messages.reduce(
      (n, m) => n + m.blocks.filter((b) => b.type === "image").length,
      0,
    );
    chatMeta.textContent = `${data.messages.length} 条消息`;
    chat.innerHTML = data.messages.map(renderMessage).join("\n");
    chat.querySelectorAll("pre code").forEach((el) => {
      try { hljs.highlightElement(el); } catch (_) {}
    });
    chat.scrollTop = 0;
    // Setup image navigation
    imageMsgIndex = -1;
    if (imgCount > 0) {
      imageJump.hidden = false;
      imageJumpLabel.textContent = `${imgCount} 张图`;
    } else {
      imageJump.hidden = true;
    }
  } catch (e) {
    chat.innerHTML =
      `<div class="msg"><div class="body">加载失败: ${escapeHtml(e.message)}</div></div>`;
  }
}

// ---------- heartbeat (only used by the Edge --app backend) ----------
async function setupHeartbeat() {
  let cfg;
  try { cfg = await api("/api/config"); }
  catch (_) { return; }
  if (!cfg.heartbeat) return;
  const beat = () => fetch("/api/heartbeat", { method: "POST", keepalive: true }).catch(() => {});
  beat();
  setInterval(beat, 3000);
  const shutdown = () => {
    try { navigator.sendBeacon("/api/shutdown", new Blob([""])); }
    catch (_) { fetch("/api/shutdown", { method: "POST", keepalive: true }).catch(() => {}); }
  };
  window.addEventListener("pagehide", shutdown);
  window.addEventListener("beforeunload", shutdown);
}

loadChatFontSize();
loadProjectsDir();
loadProjects().catch((e) => {
  chatTitle.textContent = `初始化失败: ${e.message}`;
});
setupHeartbeat();
