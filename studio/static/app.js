const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/** @type {(key: string, params?: Record<string, string | number>) => string} */
const t = (key, params) =>
  typeof window.t === "function" ? window.t(key, params) : key;

let skillsReturnTarget = null;
let skillsBrowserActiveId = null;
let skillsDetailTab = "skill";
/** @type {Record<string, unknown> | null} */
let skillsDetailCache = null;
let skillsActiveFilePath = null;
let skillsFileState = {
  path: null,
  savedContent: "",
  dirty: false,
  loading: false,
  editable: true,
};
let skillsMdState = {
  savedContent: "",
  dirty: false,
  loading: false,
};
let skillsCache = [];
let skillsOriginFilter = "system";
let skillAuthorMode = false;
let skillAuthorSessionId = null;
let toolLabelsCache = {};
const CHAT_HISTORY_MAX = 60;

/** @type {{ conversationId: string | null, dbAlias: string | null, title: string, history: Array<{role: string, content: string}> }} */
let chatState = {
  conversationId: null,
  dbAlias: null,
  title: t("chat.newTitle"),
  history: [],
};
let chatViewMode = "chat";
let chatBusy = false;
/** @type {AbortController | null} */
let chatAbortController = null;
let convHistoryRenderSeq = 0;
/** @type {{ frontends: Array<Record<string, unknown>>, defaultFrontend: string | null, backends: Array<Record<string, unknown>> }} */
let systemPreviewCache = { frontends: [], defaultFrontend: null, backends: [] };

/** @type {Array<Record<string, unknown>>} */
let pendingRuntimeErrors = [];
const acknowledgedRuntimeErrorIds = new Set();
const runtimeErrorBaselineIds = new Set();
let runtimeErrorBaselineReady = false;
let lastLogByteSize = 0;
let runtimeErrorPollTimer = null;
let runtimeErrorPollProject = null;
let lastErrorWatchProject = null;
let previewIframeSettling = false;
let previewIframeSettleTimer = null;

/** @type {{ currentPath: string | null, savedContent: string, dirty: boolean, loading: boolean, hasFrontmatter: boolean, frontmatterFields: Record<string, string> | null, frontmatterOrder: string[], editorTab: string, previewProject: string | null, previewRelPath: string | null, previewAvailable: boolean }} */
let artifactsState = {
  currentPath: null,
  savedContent: "",
  dirty: false,
  loading: false,
  hasFrontmatter: false,
  frontmatterFields: null,
  frontmatterOrder: [],
  editorTab: "edit",
  previewProject: null,
  previewRelPath: null,
  previewAvailable: false,
  treeCollapsed: new Set(),
};

function getArtifactFmLabels() {
  return {
    db_alias: t("artifacts.fm.db_alias"),
    project_name: t("artifacts.fm.project_name"),
    generated_at: t("artifacts.fm.generated_at"),
    page_type: t("artifacts.fm.page_type"),
    scope: t("artifacts.fm.scope"),
    business_goal: t("artifacts.fm.business_goal"),
  };
}
const ARTIFACT_FM_READONLY = new Set(["db_alias"]);
const ARTIFACT_FM_MULTILINE = new Set(["scope", "business_goal"]);
const ARTIFACT_FM_DEFAULT_ORDER = [
  "db_alias",
  "project_name",
  "generated_at",
  "page_type",
  "scope",
  "business_goal",
];
const ARTIFACTS_FM_COLLAPSED_KEY = "studio_artifacts_fm_collapsed";
const ARTIFACTS_TREE_COLLAPSED_KEY = "studio_artifacts_tree_collapsed";

function loadTreeCollapsedSet() {
  try {
    const raw = localStorage.getItem(ARTIFACTS_TREE_COLLAPSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveTreeCollapsedSet(set) {
  try {
    localStorage.setItem(ARTIFACTS_TREE_COLLAPSED_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

artifactsState.treeCollapsed = loadTreeCollapsedSet();

function loadArtifactsFmCollapsed() {
  try {
    return localStorage.getItem(ARTIFACTS_FM_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function setArtifactsFmCollapsed(collapsed) {
  const panel = $("#artifacts-frontmatter");
  const btn = $("#artifacts-fm-toggle");
  if (!panel) return;
  panel.classList.toggle("collapsed", collapsed);
  if (btn) {
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.title = collapsed ? t("artifacts.metadataExpand") : t("artifacts.metadataCollapse");
  }
  try {
    localStorage.setItem(ARTIFACTS_FM_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function toggleArtifactsFmCollapsed() {
  const panel = $("#artifacts-frontmatter");
  if (!panel || panel.classList.contains("hidden")) return;
  setArtifactsFmCollapsed(panel.classList.contains("collapsed") ? false : true);
}

function getActiveSkillsForChat() {
  if (skillAuthorMode) return ["skill_author"];
  return skillsCache.filter((s) => s.studio_visible !== false).map((s) => s.id).filter(Boolean);
}
let editingDbAlias = null;
let editingProjectHasGemini = false;
/** @type {Array<Record<string, unknown>>} */
let projectsCache = [];
/** @type {Record<string, unknown> | null} */
let lastMainStatus = null;

function syncLlmProviderPanels() {
  const form = $("#setup-form");
  const provider = form?.llm_provider?.value || "deepseek";
  $("#deepseek-llm-fieldset")?.classList.toggle("hidden", provider !== "deepseek");
  $("#gemini-llm-fieldset")?.classList.toggle("hidden", provider !== "gemini");
}

function formatLlmStatusParams(status) {
  const provider = status?.llm_provider || "deepseek";
  const providerLabel =
    provider === "gemini" ? t("main.llmProviderGemini") : t("main.llmProviderDeepseek");
  const llm = status?.llm_ready ? t("main.llmOk") : t("main.llmMissing");
  return { llm, provider: providerLabel };
}

function formatApiError(detail) {
  if (detail == null || detail === "") return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object") {
          const loc = Array.isArray(item.loc) ? item.loc.filter((x) => x !== "body").join(".") : "";
          const msg = item.msg || item.message || "";
          if (msg === "Field required" && loc === "skill") {
            return t("chat.legacyRequest");
          }
          if (msg === "Field required" && loc === "skills") {
            return t("chat.skillsRequired");
          }
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .filter(Boolean)
      .join("；");
  }
  if (typeof detail === "object") {
    return detail.msg || detail.message || detail.error || JSON.stringify(detail);
  }
  return String(detail);
}

function networkErrorHint(err) {
  if (err && err.message === "Failed to fetch") {
    return t("chat.networkError");
  }
  const msg = err?.message;
  if (msg && msg !== "[object Object]") return msg;
  return formatApiError(err) || t("common.unknownError");
}

function createSourceDbRow(value = "") {
  const row = document.createElement("div");
  row.className = "source-db-row";
  row.innerHTML = `
    <input type="text" class="source-db-input" data-i18n-placeholder="setup.sourceDbPlaceholder" value="${value.replace(/"/g, "&quot;")}" />
    <button type="button" class="btn btn-icon remove-source-db" data-i18n-title="setup.removeRow" data-i18n-aria-label="common.delete" aria-label="Delete">×</button>
  `;
  row.querySelector(".remove-source-db").addEventListener("click", () => {
    row.remove();
  });
  window.StudioI18n?.applyI18n?.(row);
  return row;
}

function initSourceDbList(names = []) {
  const list = $("#source-db-list");
  list.innerHTML = "";
  names.forEach((name) => list.appendChild(createSourceDbRow(name)));
}

function setupNeedsMysql(form) {
  const target = (form.target_database?.value || "").trim();
  const sources = collectSourceDatabases();
  return sources.length > 0 || Boolean(target);
}

function formatStorageSummary(statusOrProject) {
  if (statusOrProject.storage_mode === "local") {
    const rel = statusOrProject.local_sqlite_path || "data/app.db";
    return t("main.storageLocal", { path: escapeHtml(rel) });
  }
  const target = statusOrProject.target_database || "—";
  return t("main.storageTarget", { target: escapeHtml(target) });
}

function formatSetupSuccessMessage(data) {
  const sources = (data.source_databases || []).join(", ") || t("common.none");
  const files = (data.source_files || []).length;
  const filePart = files ? t("setup.sourceFilesCount", { count: files }) : "";
  if (data.storage_mode === "local") {
    return t("setup.successLocal", { alias: data.db_alias, sources, files: filePart });
  }
  return t("setup.successMysql", { alias: data.db_alias, sources, files: filePart, target: data.target_database || "—" });
}

$("#add-source-db").addEventListener("click", () => {
  $("#source-db-list").appendChild(createSourceDbRow());
});

let pendingSourceFiles = [];
/** @type {Array<Record<string, unknown>>} */
let setupSourceFiles = [];
let sourceFileUploadBusy = false;

function getSetupDbAlias() {
  return (editingDbAlias || ($("#setup-form")?.db_alias?.value || "")).trim();
}

function formatFileSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function renderSourceFileList() {
  const listEl = $("#source-file-list");
  const emptyEl = $("#source-file-empty");
  if (!listEl) return;
  listEl.innerHTML = "";
  const rows = [];

  setupSourceFiles.forEach((file) => {
    rows.push({
      kind: "saved",
      name: file.name || file.path,
      meta: `${String(file.type || "").toUpperCase()} · ${formatFileSize(file.size)}`,
      path: file.path,
    });
  });
  pendingSourceFiles.forEach((file, index) => {
    rows.push({
      kind: sourceFileUploadBusy ? "uploading" : "pending",
      name: file.name,
      meta: sourceFileUploadBusy
        ? `${formatFileSize(file.size)} · ${t("common.uploading")}`
        : `${formatFileSize(file.size)} · ${editingDbAlias ? t("common.waitUpload") : t("common.uploadAfterSave")}`,
      index,
    });
  });

  if (!rows.length) {
    emptyEl?.classList.remove("hidden");
    return;
  }
  emptyEl?.classList.add("hidden");

  rows.forEach((row) => {
    const el = document.createElement("div");
    el.className = "source-file-row";
    el.innerHTML = `
      <span class="source-file-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
      ${row.kind === "pending" ? `<span class="source-file-badge">${t("common.pendingSave")}</span>` : ""}
      ${row.kind === "uploading" ? `<span class="source-file-badge">${t("common.uploading")}</span>` : ""}
      <span class="source-file-meta">${escapeHtml(row.meta)}</span>
      <button type="button" class="btn btn-text small source-file-remove" data-i18n-title="common.remove" title="Remove">×</button>
    `;
    el.querySelector(".source-file-remove").addEventListener("click", () => {
      if (row.kind === "pending") {
        pendingSourceFiles.splice(row.index, 1);
        renderSourceFileList();
        return;
      }
      removeSetupSourceFile(row.path, row.name);
    });
    listEl.appendChild(el);
  });
}

function initSourceFileList(files = []) {
  setupSourceFiles = Array.isArray(files) ? [...files] : [];
  pendingSourceFiles = [];
  renderSourceFileList();
}

async function uploadPendingSourceFiles(dbAlias) {
  if (!pendingSourceFiles.length) return [];
  sourceFileUploadBusy = true;
  renderSourceFileList();
  try {
    const fd = new FormData();
    pendingSourceFiles.forEach((file) => fd.append("files", file, file.name));
    const res = await fetch(`/api/projects/${encodeURIComponent(dbAlias)}/source-files`, {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("sourceFile.uploadFailed"));
    pendingSourceFiles = [];
    setupSourceFiles = data.source_files || [];
    return data.uploaded || [];
  } finally {
    sourceFileUploadBusy = false;
    renderSourceFileList();
  }
}

async function flushPendingSourceFilesIfReady() {
  const alias = getSetupDbAlias();
  if (!alias || !pendingSourceFiles.length || sourceFileUploadBusy) return;
  if (!editingDbAlias) return;
  try {
    await uploadPendingSourceFiles(alias);
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function removeSetupSourceFile(path, label) {
  const alias = editingDbAlias || ($("#setup-form")?.db_alias?.value || "").trim();
  if (!alias) {
    alert(t("sourceFile.saveFirst"));
    return;
  }
  if (!confirm(t("sourceFile.removeConfirm", { name: label }))) return;
  try {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(alias)}/source-files?path=${encodeURIComponent(path)}`,
      { method: "DELETE" }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.deleteFailed"));
    setupSourceFiles = data.source_files || [];
    renderSourceFileList();
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

$("#source-file-input")?.addEventListener("change", async (e) => {
  const input = e.target;
  const picked = [...(input.files || [])];
  input.value = "";
  let rejected = false;
  picked.forEach((file) => {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!["csv", "xlsx"].includes(ext)) {
      rejected = true;
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      alert(t("sourceFile.tooLarge", { name: file.name }));
      return;
    }
    pendingSourceFiles.push(file);
  });
  if (rejected) alert(t("sourceFile.typeRejected"));
  renderSourceFileList();
  await flushPendingSourceFilesIfReady();
});

function collectSourceDatabases() {
  return [...$$(".source-db-input")]
    .map((el) => el.value.trim())
    .filter(Boolean);
}

function hideAllPanels() {
  $("#project-panel").classList.add("hidden");
  $("#setup-panel").classList.add("hidden");
  $("#main-panel").classList.add("hidden");
}

async function fetchStatus() {
  const res = await fetch("/api/status");
  return res.json();
}

async function fetchProjects() {
  const res = await fetch("/api/projects");
  const data = await res.json();
  return data.projects || [];
}

async function deleteProject(dbAlias) {
  const name = String(dbAlias || "").trim();
  if (!name) return;
  const ok = confirm(
    t("project.deleteConfirm", { name })
  );
  if (!ok) return;

  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.deleteFailed"));

    if (data.was_active) {
      chatState = {
        conversationId: null,
        dbAlias: null,
        title: t("chat.newTitle"),
        history: [],
      };
      hideAllPanels();
      const status = data.status || (await fetchStatus());
      const projects = status.projects || (await fetchProjects());
      if (projects.length > 0) {
        await showProjectPicker();
      } else {
        showSetupForm(null);
        $("#back-to-projects-btn").classList.add("hidden");
      }
      return;
    }

    await showProjectPicker();
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function fetchSkills({ bustCache = false } = {}) {
  const url = bustCache ? `/api/skills?_=${Date.now()}` : "/api/skills";
  const res = await fetch(url, { cache: "no-store" });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("skills.loadListFailed"));
  return data.skills || [];
}

function upsertSkillInCache(skill) {
  if (!skill?.id) return;
  const idx = skillsCache.findIndex((s) => s.id === skill.id);
  if (idx >= 0) skillsCache[idx] = { ...skillsCache[idx], ...skill };
  else skillsCache.push(skill);
  skillsCache.sort((a, b) => String(a.id).localeCompare(String(b.id)));
}

async function fetchToolLabels() {
  try {
    const res = await fetch("/api/tool-labels");
    const data = await res.json();
    if (!res.ok) return;
    toolLabelsCache = data.labels || {};
  } catch {
    toolLabelsCache = {};
  }
}

function formatToolCallLabel(name) {
  const key = String(name || "").trim();
  if (!key) return t("chat.toolCall");
  return toolLabelsCache[key] || key;
}

function formatToolCallLine(nameOrLine) {
  const raw = String(nameOrLine || "").trim();
  if (!raw) return t("chat.toolCall");
  if (
    raw === t("chat.callingTools") ||
    raw === t("chat.maxToolRounds") ||
    raw.startsWith(t("skills.toolCallDsmlPrefix"))
  ) {
    return raw;
  }
  const prefixed = raw.match(/^调用工具[：:]\s*(.+)$/);
  const name = (prefixed ? prefixed[1] : raw).trim();
  return t("skills.toolCallPrefix", { name: formatToolCallLabel(name) });
}

function loadSkillsCache(skills) {
  skillsCache = Array.isArray(skills) ? skills : [];
}

function trimLocalHistory(history) {
  const cleaned = history.filter(
    (m) => m && (m.role === "user" || m.role === "assistant") && String(m.content || "").trim()
  );
  if (cleaned.length <= CHAT_HISTORY_MAX) return cleaned;
  return cleaned.slice(-CHAT_HISTORY_MAX);
}

function formatConvTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(window.StudioI18n?.getLang?.() === "zh" ? "zh-CN" : "en-US", { hour12: false });
  } catch {
    return iso;
  }
}

function updateChatTitle(titleOverride) {
  const el = $("#chat-conv-title");
  if (!el) return;
  if (titleOverride) {
    chatState.title = titleOverride;
  }
  const title = chatState.title || t("chat.newTitle");
  const n = chatState.history.length;
  if (n === 0) {
    el.textContent = title;
    return;
  }
  const turns = Math.ceil(n / 2);
  el.textContent = `${title} (${turns} ${t("common.turns")})`;
}

let markdownConfigured = false;

function configureMarkdownRenderer() {
  if (markdownConfigured) return;
  if (typeof marked === "undefined") return;
  const renderer = {
    link(href, title, text) {
      const safeHref = escapeHtml(String(href || "#"));
      const titleAttr = title ? ` title="${escapeHtml(String(title))}"` : "";
      return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
    },
  };
  if (typeof marked.use === "function") {
    marked.use({ renderer, breaks: true, gfm: true });
  } else if (typeof marked.setOptions === "function") {
    marked.setOptions({ renderer, breaks: true, gfm: true });
  }
  markdownConfigured = true;
}

function renderMarkdownHtml(text) {
  const raw = String(text ?? "");
  if (!raw.trim()) return "";
  configureMarkdownRenderer();
  if (typeof marked === "undefined") {
    return escapeHtml(raw).replace(/\n/g, "<br>");
  }
  let html = "";
  try {
    html = typeof marked.parse === "function" ? marked.parse(raw) : marked(raw);
  } catch {
    return escapeHtml(raw).replace(/\n/g, "<br>");
  }
  if (typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  }
  return html;
}

function setMarkdownContent(el, text) {
  if (!el) return;
  const html = renderMarkdownHtml(text);
  if (html) {
    el.innerHTML = html;
    el.classList.add("markdown-body");
  } else {
    el.textContent = "";
    el.classList.remove("markdown-body");
  }
}

function splitAssistantContent(raw) {
  let work = String(raw || "");
  const tools = [];

  const dsmlBlockRe =
    /<[｜|]+DSML[｜|]+tool_calls>[\s\S]*?<\/[｜|]+DSML[｜|]+tool_calls>/gi;
  work = work.replace(dsmlBlockRe, (block) => {
    const nameMatch = block.match(/invoke\s+name="([^"]+)"/i);
    tools.push(nameMatch ? formatToolCallLine(nameMatch[1]) : t("chat.toolCallDsml"));
    return "\n";
  });

  const dsmlOpenRe = /<[｜|]+DSML[｜|]+tool_calls>[\s\S]*$/i;
  if (dsmlOpenRe.test(work)) {
    tools.push(t("chat.callingTools"));
    work = work.replace(dsmlOpenRe, "\n");
  }

  work = work.replace(/\[调用工具\s+([^\]]+)\]\s*/g, (_, name) => {
    tools.push(formatToolCallLine(name.trim()));
    return "\n";
  });

  work = work.replace(/\[已达最大工具调用轮数\]\s*/g, () => {
    tools.push(t("chat.maxToolRounds"));
    return "\n";
  });

  const answer = work
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\n+/, "")
    .trim();
  return { tools, answer };
}

function setChatBusy(busy) {
  chatBusy = busy;
  const input = $("#chat-message");
  const sendBtn = $("#chat-btn");
  const stopBtn = $("#chat-stop-btn");
  const form = $("#chat-form");
  if (input) {
    input.disabled = busy;
    input.placeholder = busy
      ? t("chat.placeholderBusy")
      : t("chat.placeholder");
  }
  if (sendBtn) {
    sendBtn.disabled = busy;
    sendBtn.classList.toggle("hidden", busy);
    sendBtn.textContent = t("common.send");
  }
  stopBtn?.classList.toggle("hidden", !busy);
  form?.classList.toggle("is-busy", busy);
}

function stopChatGeneration() {
  if (!chatBusy || !chatAbortController) return;
  chatAbortController.abort();
}

function appendAssistantShell() {
  const log = $("#chat-log");
  const div = document.createElement("div");
  div.className = "msg assistant is-streaming";
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  renderAssistantMessage(div, "", { streaming: true, collapseTools: false });
  return div;
}

function renderAssistantMessage(el, raw, { streaming = false, collapseTools = false } = {}) {
  if (!el) return;
  const { tools, answer } = splitAssistantContent(raw);

  el.replaceChildren();
  el.className = "msg assistant";
  if (streaming) el.classList.add("is-streaming");
  if (tools.length) el.classList.add("has-tool-trace");

  if (streaming) {
    const statusEl = document.createElement("div");
    statusEl.className = "assistant-status";
    if (tools.length && !answer) {
      statusEl.textContent = t("chat.callingTools");
    } else if (answer) {
      statusEl.textContent = t("chat.streaming");
    } else {
      statusEl.textContent = t("chat.thinking");
    }
    el.appendChild(statusEl);
  }

  if (tools.length) {
    const traceEl = document.createElement("details");
    traceEl.className = "tool-trace";
    traceEl.open = !collapseTools;
    const summaryEl = document.createElement("summary");
    summaryEl.className = "tool-trace-summary";
    summaryEl.textContent = t("chat.toolTrace", { count: tools.length });
    const traceBody = document.createElement("pre");
    traceBody.className = "tool-trace-body";
    traceBody.textContent = tools.join("\n");
    traceEl.append(summaryEl, traceBody);
    el.appendChild(traceEl);
  }

  if (answer || !streaming) {
    const answerText =
      answer ||
      (tools.length
        ? t("chat.toolTraceEmpty")
        : "");
    if (answerText) {
      const answerEl = document.createElement("div");
      answerEl.className = "assistant-answer markdown-body";
      setMarkdownContent(answerEl, answerText);
      el.appendChild(answerEl);
    }
  }
}

function renderChatLog() {
  const log = $("#chat-log");
  if (!log) return;
  log.innerHTML = "";
  for (const m of chatState.history) {
    if (m.role === "assistant") {
      const div = document.createElement("div");
      renderAssistantMessage(div, m.content, { streaming: false, collapseTools: true });
      log.appendChild(div);
    } else if (m.role === "user") {
      const div = document.createElement("div");
      div.className = "msg user";
      const body = document.createElement("div");
      body.className = "msg-body markdown-body";
      setMarkdownContent(body, m.content);
      div.appendChild(body);
      log.appendChild(div);
    } else {
      const div = document.createElement("div");
      div.className = `msg ${m.role}`;
      div.textContent = m.content;
      log.appendChild(div);
    }
  }
  log.scrollTop = log.scrollHeight;
}

function applyConversation(conv) {
  chatState.conversationId = conv.id;
  chatState.title = conv.title || t("chat.newTitle");
  chatState.history = trimLocalHistory(conv.messages || []);
  renderChatLog();
  updateChatTitle();
  void renderConversationHistory();
}

async function fetchConversations() {
  const res = await fetch("/api/conversations");
  const data = await res.json();
  if (res.status === 404) {
    throw new Error(t("chat.convApiUnavailable"));
  }
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("chat.loadListFailed"));
  return data.conversations || [];
}

async function apiCreateConversation() {
  const res = await fetch("/api/conversations", { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("chat.createFailed"));
  return data.conversation;
}

async function apiLoadConversation(conversationId) {
  const res = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("chat.loadFailed"));
  return data.conversation;
}

async function apiDeleteConversation(conversationId) {
  const res = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("chat.deleteFailed"));
  return data;
}

async function initChatForProject(dbAlias, status = null) {
  chatState.dbAlias = dbAlias;
  chatState.history = [];
  chatState.conversationId = null;
  chatState.title = t("chat.newTitle");
  try {
    const st = status || (await fetchStatus());
    if (st.conversation_id) {
      try {
        applyConversation(await apiLoadConversation(st.conversation_id));
        return;
      } catch {
        /* 文件已删则继续 */
      }
    }
    const list = await fetchConversations();
    if (list.length) {
      applyConversation(await apiLoadConversation(list[0].id));
      return;
    }
    applyConversation(await apiCreateConversation());
  } catch {
    renderChatLog();
    updateChatTitle();
  } finally {
    await renderConversationHistory();
  }
}

function setPanelHeadActions({ artifacts = true, systemPreview = true, skills = true, back = false } = {}) {
  $("#system-preview-btn")?.classList.toggle("hidden", !systemPreview);
  $("#artifacts-btn")?.classList.toggle("hidden", !artifacts);
  $("#skills-btn")?.classList.toggle("hidden", !skills);
  $("#back-to-chat-btn")?.classList.toggle("hidden", !back);
  updateBackToChatBadge();
}

function stableErrorId(err) {
  if (!err) return "";
  const title = String(err.title || "");
  const httpM = title.match(
    /^(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+(\S+)\s+→\s+(\d+)/
  );
  if (httpM) {
    return hashRuntimeErrorKey(
      `http:${httpM[1]}:${httpM[2]}:${httpM[3]}`
    );
  }
  if (err.kind === "preview-fetch") {
    const url = String(err.excerpt || "").split("\n")[0] || title;
    const sm = title.match(/HTTP\s+(\d+)/i);
    const status = sm ? sm[1] : "0";
    return hashRuntimeErrorKey(`fetch:${url}:${status}`);
  }
  return err.id || "";
}

function isErrorAcknowledged(err) {
  if (!err?.id) return false;
  if (acknowledgedRuntimeErrorIds.has(err.id)) return true;
  const stable = stableErrorId(err);
  return stable ? acknowledgedRuntimeErrorIds.has(stable) : false;
}

function acknowledgeRuntimeErrors(errors) {
  for (const e of errors || []) {
    if (e?.id) acknowledgedRuntimeErrorIds.add(e.id);
    const stable = stableErrorId(e);
    if (stable) acknowledgedRuntimeErrorIds.add(stable);
  }
  pendingRuntimeErrors = pendingRuntimeErrors.filter((e) => !isErrorAcknowledged(e));
  updateRuntimeErrorUi();
}

function runtimeErrorDedupeKey(err) {
  const stable = stableErrorId(err);
  return stable || err?.id || "";
}

function mergeRuntimeErrors(errors, ctx = {}) {
  const list = Array.isArray(errors) ? errors : [];
  for (const e of list) {
    if (!e?.id || isErrorAcknowledged(e)) continue;
    const key = runtimeErrorDedupeKey(e);
    if (
      key &&
      pendingRuntimeErrors.some((p) => runtimeErrorDedupeKey(p) === key)
    ) {
      continue;
    }
    pendingRuntimeErrors.push({
      ...e,
      frontend_project: ctx.frontend_project || null,
      backend_project: ctx.backend_project || null,
      detected_at: Date.now(),
    });
  }
  updateRuntimeErrorUi();
}

function updateRuntimeErrorUi() {
  updateBackToChatBadge();
  updateSystemPreviewErrorBanner();
}

function updateSystemPreviewErrorBanner() {
  const banner = $("#system-preview-error-banner");
  const text = $("#system-preview-error-banner-text");
  if (!banner || !text) return;
  const n = pendingRuntimeErrors.length;
  const show = chatViewMode === "system-preview" && n > 0;
  banner.classList.toggle("hidden", !show);
  if (show) {
    const latest = pendingRuntimeErrors[pendingRuntimeErrors.length - 1];
    const hint = latest?.title ? t("preview.latest", { title: latest.title }) : "";
    text.textContent =
      n === 1
        ? t("preview.runtimeErrorOne", { hint })
        : t("preview.runtimeErrors", { count: n, hint });
  }
}

function updateBackToChatBadge() {
  const btn = $("#back-to-chat-btn");
  if (!btn) return;
  const show =
    chatViewMode === "system-preview" &&
    pendingRuntimeErrors.length > 0 &&
    !btn.classList.contains("hidden");
  btn.classList.toggle("has-runtime-alert", show);
  if (show) {
    const n = pendingRuntimeErrors.length;
    btn.title = t("chat.backBtnErrors", { count: n });
  } else {
    btn.title = t("chat.backBtnTitle");
  }
}

function hashRuntimeErrorKey(text) {
  let h = 0;
  const s = String(text);
  for (let i = 0; i < s.length; i += 1) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return `r${Math.abs(h).toString(16)}`;
}

function processRuntimeLogPoll(data, ctx) {
  const all = Array.isArray(data?.runtime_errors) ? data.runtime_errors : [];
  const fresh = Array.isArray(data?.new_runtime_errors) ? data.new_runtime_errors : [];
  const logSize = Number(data?.log_byte_size) || 0;

  if (!runtimeErrorBaselineReady) {
    for (const e of [...all, ...fresh]) {
      if (e?.id) runtimeErrorBaselineIds.add(e.id);
    }
    runtimeErrorBaselineReady = true;
    lastLogByteSize = logSize;
    return;
  }

  const toAdd = [];
  for (const e of fresh) {
    if (!e?.id || runtimeErrorBaselineIds.has(e.id)) continue;
    if (isErrorAcknowledged(e)) {
      runtimeErrorBaselineIds.add(e.id);
      continue;
    }
    runtimeErrorBaselineIds.add(e.id);
    toAdd.push(e);
  }

  if (!toAdd.length && logSize > lastLogByteSize) {
    for (const e of all) {
      if (!e?.id || runtimeErrorBaselineIds.has(e.id)) continue;
      if (isErrorAcknowledged(e)) {
        runtimeErrorBaselineIds.add(e.id);
        continue;
      }
      runtimeErrorBaselineIds.add(e.id);
      toAdd.push(e);
    }
  }

  lastLogByteSize = logSize;
  if (toAdd.length) mergeRuntimeErrors(toAdd, ctx);
}

function handlePreviewHttpErrorMessage(payload) {
  if (chatViewMode !== "system-preview") return;
  const status = Number(payload?.status) || 0;
  // 4xx/5xx 由后端日志轮询检测；避免 iframe 每次加载重复弹窗
  if (status >= 400) return;

  const project =
    $("#system-preview-project-select")?.value || runtimeErrorPollProject;
  const url = String(payload?.url || "");
  const id = hashRuntimeErrorKey(`fetch:${url}:${status}`);
  const err = {
    id,
    kind: "preview-fetch",
    title: status
      ? t("preview.httpFailed", { status })
      : t("preview.networkFailed"),
    excerpt: `${url}\n${String(payload?.detail || "").trim()}`.trim(),
  };
  const ctx = { frontend_project: project, backend_project: null };
  if (
    previewIframeSettling ||
    !runtimeErrorBaselineReady
  ) {
    runtimeErrorBaselineIds.add(id);
    return;
  }
  if (isErrorAcknowledged(err)) return;
  mergeRuntimeErrors([err], ctx);
}

function beginPreviewIframeSettling() {
  previewIframeSettling = true;
  if (previewIframeSettleTimer) clearTimeout(previewIframeSettleTimer);
  previewIframeSettleTimer = setTimeout(() => {
    previewIframeSettling = false;
    previewIframeSettleTimer = null;
  }, 2500);
}

function resetRuntimeErrorWatchForProject(projectName, { hard = false } = {}) {
  runtimeErrorPollProject = projectName || null;
  pendingRuntimeErrors = [];
  if (hard) {
    runtimeErrorBaselineReady = false;
    runtimeErrorBaselineIds.clear();
    lastLogByteSize = 0;
  }
  beginPreviewIframeSettling();
  updateRuntimeErrorUi();
}

function stopRuntimeErrorPoll() {
  if (runtimeErrorPollTimer) {
    clearInterval(runtimeErrorPollTimer);
    runtimeErrorPollTimer = null;
  }
}

function startRuntimeErrorPoll(projectName, { resetWatch = false } = {}) {
  stopRuntimeErrorPoll();
  if (!projectName) return;
  runtimeErrorPollProject = projectName;
  const tick = () => {
    void pollRuntimeErrors({ resetWatch: false });
  };
  runtimeErrorPollTimer = setInterval(tick, 1500);
  void pollRuntimeErrors({ resetWatch });
}

async function pollRuntimeErrors({ resetWatch = false } = {}) {
  if (chatViewMode !== "system-preview") return;
  const project =
    $("#system-preview-project-select")?.value || runtimeErrorPollProject;
  if (!project) return;
  await refreshBackendLog({
    scroll: false,
    updatePanel: false,
    resetWatch,
    frontendProject: project,
  });
}

function buildRuntimeErrorFixMessage(errors) {
  const fe = errors[0]?.frontend_project || "—";
  const be = errors[0]?.backend_project || "—";
  const parts = errors.map(
    (e, i) => `${t("preview.errorItem", { n: i + 1, title: e.title || t("common.unknown") })}\n\`\`\`\n${e.excerpt || ""}\n\`\`\``
  );
  return (
    t("preview.errorFixIntro", { fe, be }) + parts.join("\n\n")
  );
}

function dedupeRuntimeErrorsForDisplay(errors) {
  const list = Array.isArray(errors) ? errors : [];
  const seen = new Set();
  const out = [];
  for (const e of list) {
    const key = runtimeErrorDedupeKey(e);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(e);
  }
  return out;
}

function showRuntimeErrorPromptInChat(errors) {
  const log = $("#chat-log");
  const batch = dedupeRuntimeErrorsForDisplay(errors);
  if (!log || !batch.length) return;

  const div = document.createElement("div");
  div.className = "msg assistant runtime-error-notice";
  const body = document.createElement("div");
  body.className = "msg-body markdown-body";
  let md =
    t("preview.errorNoticeIntro");
  batch.forEach((e, i) => {
    const title = e.title || t("preview.runtimeError");
    const excerpt = (e.excerpt || "").trim();
    md += `**${i + 1}. ${title}**\n\n`;
    if (excerpt) {
      md += "```\n" + excerpt + "\n```\n\n";
    }
  });
  md +=
    t("preview.errorPrompt");
  setMarkdownContent(body, md);
  div.appendChild(body);

  const actions = document.createElement("div");
  actions.className = "runtime-error-actions";
  const okBtn = document.createElement("button");
  okBtn.type = "button";
  okBtn.className = "btn primary btn-sm";
  okBtn.textContent = t("preview.fixOk");
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "btn ghost btn-sm";
  cancelBtn.textContent = t("common.ignore");
  okBtn.addEventListener("click", () => {
    okBtn.disabled = true;
    cancelBtn.disabled = true;
    acknowledgeRuntimeErrors(batch);
    const msg = buildRuntimeErrorFixMessage(batch);
    void sendChatMessage(msg, { showUserMessage: true });
  });
  cancelBtn.addEventListener("click", () => {
    acknowledgeRuntimeErrors(batch);
    div.remove();
    appendMessage("system", t("preview.ignored"));
  });
  actions.append(okBtn, cancelBtn);
  div.appendChild(actions);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function syncConvHistorySidebar() {
  const onChat = chatViewMode === "chat" && !skillAuthorMode;
  $(".conv-history-sidebar")?.classList.toggle("hidden", !onChat);
  $(".main-grid")?.classList.toggle("main-grid--no-sidebar", !onChat);
}

function skillOriginLabel(origin) {
  return origin === "custom" ? t("skills.originCustomLabel") : t("skills.originSystemLabel");
}

function skillOriginBadgeHtml(origin) {
  const cls = origin === "custom" ? "custom" : "system";
  return `<span class="skills-origin-badge ${cls}">${skillOriginLabel(origin)}</span>`;
}

function getFilteredSkillsCache() {
  return skillsCache.filter((sk) => {
    const origin = sk.origin || "system";
    if (skillsOriginFilter === "custom") return origin === "custom";
    return origin === "system";
  });
}

function updateSkillsOriginFilterUi() {
  $("#skills-origin-filter")?.querySelectorAll(".skills-origin-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.origin === skillsOriginFilter);
  });
  $("#skills-list-actions")?.classList.toggle("hidden", skillsOriginFilter !== "custom");
}

function setSkillsOriginFilter(origin) {
  const next = origin === "custom" ? "custom" : "system";
  if (next === skillsOriginFilter) return;
  if (skillsMdState.dirty && !window.confirm(t("skills.unsavedSwitchFilter"))) return;
  skillsOriginFilter = next;
  updateSkillsOriginFilterUi();
  const filtered = getFilteredSkillsCache();
  if (!filtered.some((sk) => sk.id === skillsBrowserActiveId)) {
    skillsBrowserActiveId = filtered[0]?.id || null;
    skillsDetailCache = null;
    resetSkillFileEditor();
    skillsMdState = { savedContent: "", dirty: false, loading: false };
  }
  renderSkillsBrowserList(filtered);
  if (skillsBrowserActiveId) {
    void fetchSkillDetail(skillsBrowserActiveId)
      .then((detail) => renderSkillDetail(detail, { resetTab: true }))
      .catch(() => {
        const previewEl = $("#skills-skill-preview-wrap");
        if (previewEl) previewEl.innerHTML = `<p class="hint">${t("common.loadFailed")}</p>`;
      });
  } else {
    clearSkillDetailPanel();
  }
}

function clearSkillDetailPanel() {
  $("#skills-detail-title").textContent = t("skills.select");
  $("#skills-detail-meta").textContent = "";
  $("#skills-readonly-hint")?.classList.add("hidden");
  $("#skills-detail-toolbar")?.classList.add("hidden");
  $("#skills-delete-custom-btn")?.classList.add("hidden");
  $("#skills-detail-tabs")?.classList.add("hidden");
  skillsMdState = { savedContent: "", dirty: false, loading: false };
  const previewEl = $("#skills-skill-preview-wrap");
  const editorWrap = $("#skills-skill-editor-wrap");
  previewEl?.classList.remove("hidden");
  editorWrap?.classList.add("hidden");
  if (previewEl) {
    previewEl.innerHTML = `<p class="hint">${skillsOriginFilter === "custom" ? t("skills.selectCustomEmpty") : t("skills.selectSystem")}</p>`;
  }
  const editor = $("#skills-skill-editor");
  if (editor) editor.value = "";
  $("#skills-tab-tools")?.classList.add("hidden");
  $("#skills-tab-files")?.classList.add("hidden");
  $("#skills-tab-skill")?.classList.remove("hidden");
}

async function refreshSkillsCache() {
  const skills = await fetchSkills({ bustCache: true });
  loadSkillsCache(skills);
  return skills;
}

async function ensureSkillAuthorSession() {
  if (skillAuthorSessionId) return skillAuthorSessionId;
  const res = await fetch("/api/skill-author/session", { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("skills.sessionFailed"));
  skillAuthorSessionId = data.session_id;
  return skillAuthorSessionId;
}

async function renderSkillAuthorFileList() {
  const listEl = $("#skill-author-file-list");
  if (!listEl) return;
  listEl.innerHTML = "";
  if (!skillAuthorSessionId) return;
  try {
    const res = await fetch(
      `/api/skill-author/uploads?session_id=${encodeURIComponent(skillAuthorSessionId)}`
    );
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("skills.attachFailed"));
    (data.files || []).forEach((f) => {
      const li = document.createElement("li");
      li.textContent = f.filename || f.name || "file";
      listEl.appendChild(li);
    });
  } catch {
    /* ignore */
  }
}

async function uploadSkillAuthorFiles(fileList) {
  if (!fileList?.length) return;
  const sessionId = await ensureSkillAuthorSession();
  const fd = new FormData();
  for (const file of fileList) fd.append("files", file);
  const res = await fetch(
    `/api/skill-author/uploads?session_id=${encodeURIComponent(sessionId)}`,
    { method: "POST", body: fd }
  );
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.uploadFailed"));
  await renderSkillAuthorFileList();
  return data;
}

function leaveSkillAuthorMode() {
  skillAuthorMode = false;
  skillAuthorSessionId = null;
  $("#skill-author-bar")?.classList.add("hidden");
  $("#skill-author-file-input").value = "";
  const listEl = $("#skill-author-file-list");
  if (listEl) listEl.innerHTML = "";
}

async function openSkillAuthorChat() {
  skillsReturnTarget = "skills";
  try {
    await ensureSkillAuthorSession();
  } catch (err) {
    alert(networkErrorHint(err));
    return;
  }
  skillAuthorMode = true;
  hideAllPanels();
  $("#main-panel")?.classList.remove("hidden");
  await startNewConversation({ announce: false });
  showChatView();
  await renderSkillAuthorFileList();
  renderChatLog();
  appendMessage(
    "system",
    t("skillAuthor.ready")
  );
}

async function uploadCustomSkillZip(file) {
  if (!file) throw new Error(t("skills.noZip"));
  if (!/\.zip$/i.test(file.name || "")) {
    throw new Error(t("skills.zipRequired"));
  }
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/custom-skills/upload", { method: "POST", body: fd });
  let data;
  try {
    data = await res.json();
  } catch {
    throw new Error(
      res.status === 404
        ? t("skills.uploadApiUnavailable")
        : t("skills.serverError", { status: res.status })
    );
  }
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.uploadFailed"));
  return data;
}

async function finishCustomSkillUpload(data) {
  const sid = data.skill_id;
  skillsOriginFilter = "custom";
  updateSkillsOriginFilterUi();
  skillsMdState = { savedContent: "", dirty: false, loading: false };
  if (data.skill) upsertSkillInCache(data.skill);
  await refreshSkillsCache();
  if (sid) skillsBrowserActiveId = sid;
  renderSkillsBrowserList(getFilteredSkillsCache());
  if (sid) {
    const detail = await fetchSkillDetail(sid);
    renderSkillDetail(detail, { resetTab: true });
  }
  return data;
}

async function handleCustomSkillZipUpload(file) {
  const label = $("#skills-upload-label");
  const prevLabel = label?.textContent;
  if (label) {
    label.classList.add("is-busy");
    label.textContent = t("common.uploading");
  }
  try {
    const data = await uploadCustomSkillZip(file);
    await finishCustomSkillUpload(data);
  } catch (err) {
    alert(networkErrorHint(err));
  } finally {
    if (label) {
      label.classList.remove("is-busy");
      label.textContent = prevLabel || t("skills.upload");
    }
  }
}

async function deleteCustomSkill(skillId) {
  if (!window.confirm(t("skills.deleteConfirm", { id: skillId }))) return;
  const res = await fetch(`/api/custom-skills/${encodeURIComponent(skillId)}`, {
    method: "DELETE",
  });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.deleteFailed"));
  skillsBrowserActiveId = null;
  skillsDetailCache = null;
  await refreshSkillsCache();
  renderSkillsBrowser();
}

function showChatView() {
  chatViewMode = "chat";
  if (!skillAuthorMode) {
    skillsReturnTarget = null;
    $("#skill-author-bar")?.classList.add("hidden");
  }
  $("#chat-view")?.classList.remove("hidden");
  $("#system-preview-view")?.classList.add("hidden");
  $("#artifacts-view")?.classList.add("hidden");
  $("#skills-view")?.classList.add("hidden");
  closeBackendLogPanel();
  stopRuntimeErrorPoll();
  pendingRuntimeErrors = [];
  updateRuntimeErrorUi();
  if (skillAuthorMode) {
    const titleEl = $("#chat-conv-title");
    if (titleEl) titleEl.textContent = t("skillAuthor.title");
    $("#skill-author-bar")?.classList.remove("hidden");
    setPanelHeadActions({ artifacts: false, systemPreview: false, skills: true, back: true });
  } else {
    setPanelHeadActions({ artifacts: true, systemPreview: true, skills: true, back: false });
  }
  syncConvHistorySidebar();
  updateChatTitle();
}

async function fetchSkillDetail(skillId) {
  const res = await fetch(`/api/skills/${encodeURIComponent(skillId)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("skills.loadFailed"));
  return data.skill;
}

function renderSkillsBrowserList(skills) {
  const listEl = $("#skills-browser-list");
  const emptyEl = $("#skills-browser-empty");
  if (!listEl) return;
  const filtered = skills || getFilteredSkillsCache();
  listEl.innerHTML = "";
  if (!filtered.length) {
    emptyEl?.classList.remove("hidden");
    if (emptyEl) {
      emptyEl.textContent =
        skillsOriginFilter === "custom"
          ? t("skills.selectCustomEmpty")
          : t("skills.empty");
    }
    return;
  }
  emptyEl?.classList.add("hidden");
  filtered.forEach((sk) => {
    const li = document.createElement("li");
    li.className = "skills-browser-item";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "skills-browser-btn" + (sk.id === skillsBrowserActiveId ? " active" : "");
    btn.innerHTML = `
      <span class="skills-browser-name">${escapeHtml(sk.name || sk.id)}</span>
      <span class="skills-browser-id">${escapeHtml(sk.id)}</span>
      <span class="skills-browser-meta">${t("skills.toolMeta", { count: sk.tool_count || 0, extra: `${sk.studio_visible === false ? t("skills.notEnabledShort") : ""}${sk.read_only ? t("skills.readonlyShort") : ""}` })}</span>
    `;
    btn.addEventListener("click", () => selectSkillInBrowser(sk.id));
    li.appendChild(btn);
    listEl.appendChild(li);
  });
}

function setSkillsDetailTab(tab) {
  if (tab !== skillsDetailTab && skillsMdState.dirty && skillsDetailTab === "skill") {
    if (!window.confirm(t("skills.unsavedSwitchTab"))) return false;
  }
  skillsDetailTab = tab;
  const tabsEl = $("#skills-detail-tabs");
  tabsEl?.querySelectorAll(".skills-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  $("#skills-tab-skill")?.classList.toggle("hidden", tab !== "skill");
  $("#skills-tab-tools")?.classList.toggle("hidden", tab !== "tools");
  $("#skills-tab-files")?.classList.toggle("hidden", tab !== "files");
  return true;
}

function updateSkillsDetailTabs(detail) {
  const tabsEl = $("#skills-detail-tabs");
  if (!tabsEl) return;
  const tools = detail?.tools || [];
  const files = detail?.files || [];
  tabsEl.classList.remove("hidden");
  const toolsBtn = tabsEl.querySelector('[data-tab="tools"]');
  const filesBtn = tabsEl.querySelector('[data-tab="files"]');
  if (toolsBtn) {
    toolsBtn.textContent = tools.length ? t("skills.toolsCount", { count: tools.length }) : t("skills.tabTools");
    toolsBtn.disabled = !tools.length;
  }
  if (filesBtn) {
    filesBtn.textContent = files.length ? t("skills.filesCount", { count: files.length }) : t("skills.tabFiles");
    filesBtn.disabled = !files.length;
  }
  if (skillsDetailTab === "tools" && !tools.length) skillsDetailTab = "skill";
  if (skillsDetailTab === "files" && !files.length) skillsDetailTab = "skill";
  setSkillsDetailTab(skillsDetailTab);
}

function renderSkillToolsPane(detail) {
  const pane = $("#skills-tab-tools");
  if (!pane) return;
  const tools = detail?.tools || [];
  if (!tools.length) {
    pane.innerHTML = `<p class="hint">${t('skills.noTools')}</p>`;
    return;
  }
  pane.innerHTML = `
    <div class="skills-tool-list">
      ${tools
        .map((t) => {
          const aliases = (t.aliases || []).filter(Boolean);
          return `
            <article class="skills-tool-card">
              <div class="skills-tool-card-head">
                <span class="skills-tool-card-name">${escapeHtml(t.name)}</span>
                ${t.label && t.label !== t.name ? `<span class="skills-tool-card-label">${escapeHtml(t.label)}</span>` : ""}
              </div>
              <p class="skills-tool-card-desc">${escapeHtml(t.description || t("common.noDescription"))}</p>
              ${aliases.length ? `<p class="skills-tool-card-aliases">${t("common.alias", { list: aliases.map((a) => escapeHtml(a)).join(", ") })}</p>` : ""}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

const SKILLS_TREE_COLLAPSED_KEY = "studio_skills_tree_collapsed";

function loadSkillsTreeCollapsedSet() {
  try {
    const raw = localStorage.getItem(SKILLS_TREE_COLLAPSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveSkillsTreeCollapsedSet(set) {
  try {
    localStorage.setItem(SKILLS_TREE_COLLAPSED_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore */
  }
}

let skillsFilesTreeCollapsed = loadSkillsTreeCollapsedSet();

function isSkillDirCollapsed(path) {
  return skillsFilesTreeCollapsed.has(path);
}

function toggleSkillDirCollapsed(path) {
  if (skillsFilesTreeCollapsed.has(path)) {
    skillsFilesTreeCollapsed.delete(path);
  } else {
    skillsFilesTreeCollapsed.add(path);
  }
  saveSkillsTreeCollapsedSet(skillsFilesTreeCollapsed);
}

function buildSkillFilesTree(files) {
  const root = { type: "dir", name: "", path: "", children: [] };
  const normalized = (files || []).map((item) => {
    if (typeof item === "string") return { path: item, editable: true };
    return { path: item.path, editable: item.editable !== false };
  });
  for (const file of normalized) {
    const parts = String(file.path || "").split("/").filter(Boolean);
    if (!parts.length) continue;
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      if (isFile) {
        current.children.push({
          type: "file",
          name: part,
          path: file.path,
          editable: file.editable,
        });
      } else {
        const dirPath = parts.slice(0, i + 1).join("/");
        let dir = current.children.find((c) => c.type === "dir" && c.name === part);
        if (!dir) {
          dir = { type: "dir", name: part, path: dirPath, children: [] };
          current.children.push(dir);
        }
        current = dir;
      }
    }
  }
  const sortNodes = (nodes) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
    nodes.forEach((n) => {
      if (n.type === "dir") sortNodes(n.children);
    });
  };
  sortNodes(root.children);
  return root.children;
}

function renderSkillFilesTreeNode(node) {
  const readOnly = Boolean(skillsDetailCache?.read_only);
  if (node.type === "file") {
    const li = document.createElement("li");
    li.className = "artifacts-tree-item";
    const row = document.createElement("div");
    row.className =
      "artifacts-tree-file-row" + (node.path === skillsActiveFilePath ? " active" : "");

    const spacer = document.createElement("span");
    spacer.className = "artifacts-tree-chevron placeholder";
    spacer.setAttribute("aria-hidden", "true");

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "artifacts-tree-file" + (node.editable === false ? " not-editable" : "");
    btn.title = node.editable === false ? t("artifacts.notEditable", { path: node.path }) : node.path;
    btn.textContent = node.name;
    btn.addEventListener("click", () => openSkillFile(node.path, node.editable !== false));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "artifacts-tree-action artifacts-tree-delete";
    delBtn.title = node.editable === false ? t("skills.deleteFileReadonly") : t("skills.deleteFileBtn");
    delBtn.setAttribute("aria-label", t("skills.deleteAria", { name: node.name }));
    delBtn.textContent = "×";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSkillPath(node.path, node.name);
    });

    row.appendChild(spacer);
    row.appendChild(btn);
    if (!readOnly) row.appendChild(delBtn);
    li.appendChild(row);
    return li;
  }

  const collapsed = isSkillDirCollapsed(node.path);
  const li = document.createElement("li");
  li.className = "artifacts-tree-item";

  const row = document.createElement("div");
  row.className = "artifacts-tree-dir-row";

  const chevron = createTreeChevron(collapsed);
  const nameBtn = document.createElement("button");
  nameBtn.type = "button";
  nameBtn.className = "artifacts-tree-dir";
  nameBtn.title = node.path;
  nameBtn.textContent = node.name;

  const newBtn = document.createElement("button");
  newBtn.type = "button";
  newBtn.className = "artifacts-tree-action";
  newBtn.title = t("artifacts.newInDirBtn");
  newBtn.setAttribute("aria-label", t("skills.newInDirAria", { name: node.name }));
  newBtn.textContent = "+";
  newBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    promptNewSkillFile(node.path);
  });

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "artifacts-tree-action artifacts-tree-delete";
  delBtn.title = t("skills.deleteFolderTitle");
  delBtn.setAttribute("aria-label", t("skills.deleteFolderAria", { name: node.name }));
  delBtn.textContent = "×";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteSkillPath(node.path, node.name, { isDir: true });
  });

  const childrenUl = document.createElement("ul");
  childrenUl.className = "artifacts-tree-children" + (collapsed ? " hidden" : "");
  (node.children || []).forEach((child) => childrenUl.appendChild(renderSkillFilesTreeNode(child)));

  const applyCollapsed = () => {
    const isCollapsed = isSkillDirCollapsed(node.path);
    childrenUl.classList.toggle("hidden", isCollapsed);
    chevron.classList.toggle("collapsed", isCollapsed);
    chevron.setAttribute("aria-label", isCollapsed ? t("common.expand") : t("common.collapse"));
  };

  const toggle = () => {
    toggleSkillDirCollapsed(node.path);
    applyCollapsed();
  };
  chevron.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  nameBtn.addEventListener("click", toggle);

  row.appendChild(chevron);
  row.appendChild(nameBtn);
  if (!readOnly) {
    row.appendChild(newBtn);
    row.appendChild(delBtn);
  }
  li.appendChild(row);
  li.appendChild(childrenUl);
  return li;
}

function renderSkillFilesPane(detail) {
  const treeEl = $("#skills-files-tree");
  const emptyEl = $("#skills-files-tree-empty");
  if (!treeEl) return;
  const files = detail?.files || [];
  treeEl.innerHTML = "";
  const roots = buildSkillFilesTree(files);
  if (!roots.length) {
    emptyEl?.classList.remove("hidden");
    return;
  }
  const hasFiles = (nodes) => {
    for (const n of nodes || []) {
      if (n.type === "file") return true;
      if (n.children?.length && hasFiles(n.children)) return true;
    }
    return false;
  };
  if (!hasFiles(roots)) {
    emptyEl?.classList.remove("hidden");
  } else {
    emptyEl?.classList.add("hidden");
  }
  const ul = document.createElement("ul");
  roots.forEach((root) => ul.appendChild(renderSkillFilesTreeNode(root)));
  treeEl.appendChild(ul);
}

function setSkillFileStatus(text, kind = "") {
  const el = $("#skills-file-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("dirty", "saved", "error");
  if (kind) el.classList.add(kind);
}

function resetSkillFileEditor() {
  skillsActiveFilePath = null;
  skillsFileState = {
    path: null,
    savedContent: "",
    dirty: false,
    loading: false,
    editable: true,
  };
  const editor = $("#skills-file-editor");
  if (editor) {
    editor.value = "";
    editor.disabled = true;
  }
  updateSkillFileEditorUi();
}

async function confirmDiscardSkillFileChanges() {
  if (!skillsFileState.dirty) return true;
  return window.confirm(t("artifacts.unsavedDiscard"));
}

function updateSkillFileEditorUi() {
  const editor = $("#skills-file-editor");
  const saveBtn = $("#skills-file-save-btn");
  const label = $("#skills-file-label");
  if (!editor || !saveBtn || !label) return;
  const hasFile = Boolean(skillsFileState.path);
  label.textContent = hasFile ? skillsFileState.path : t("common.noFileSelected");
  const canEdit = hasFile && skillsFileState.editable && !skillsFileState.loading;
  editor.disabled = !canEdit;
  saveBtn.disabled = !canEdit || !skillsFileState.dirty;
  if (skillsFileState.loading) {
    setSkillFileStatus(t("common.loading"));
  } else if (skillsFileState.dirty) {
    setSkillFileStatus(t("common.unsavedChanges"), "dirty");
  } else if (hasFile) {
    setSkillFileStatus(skillsFileState.editable ? t("common.loaded") : t("skills.notEditable"), "saved");
  } else {
    setSkillFileStatus("");
  }
}

function normalizeSkillFilePath(input, parentDir) {
  let p = String(input || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  if (!p) throw new Error(t("skills.pathRequired"));
  if (parentDir) {
    const parent = parentDir.replace(/\/+$/, "");
    if (!p.includes("/")) {
      p = `${parent}/${p}`;
    }
  }
  if (p.split("/").includes("..")) throw new Error(t("skills.pathInvalid"));
  return p;
}

async function promptNewSkillFile(parentDir) {
  if (!skillsBrowserActiveId || skillsDetailCache?.read_only) return;
  const hint = parentDir
    ? t("skills.newFileInDir", { dir: parentDir })
    : t("skills.newFileExamples");
  const raw = window.prompt(hint, "");
  if (raw == null || !String(raw).trim()) return;
  try {
    const path = normalizeSkillFilePath(raw, parentDir || undefined);
    await createSkillFile(path, "");
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function createSkillFile(path, content = "") {
  if (!skillsBrowserActiveId) return;
  if (!(await confirmDiscardSkillFileChanges())) return;
  const res = await fetch(`/api/skills/${encodeURIComponent(skillsBrowserActiveId)}/file`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.createFailed"));
  const detail = await fetchSkillDetail(skillsBrowserActiveId);
  skillsDetailCache = detail;
  renderSkillFilesPane(detail);
  await openSkillFile(path, true);
}

function isCurrentSkillFileUnder(deletedPath) {
  const cur = skillsFileState.path;
  if (!cur) return false;
  return cur === deletedPath || cur.startsWith(`${deletedPath}/`);
}

async function deleteSkillPath(path, name, { isDir = false } = {}) {
  if (!skillsBrowserActiveId || skillsDetailCache?.read_only) return;
  let msg = isDir
    ? t("skills.deleteFolder", { name })
    : t("skills.deleteFile", { name });
  if (!window.confirm(msg)) return;
  if (
    isCurrentSkillFileUnder(path) &&
    skillsFileState.dirty &&
    !window.confirm(t("skills.deleteUnsaved"))
  ) {
    return;
  }
  try {
    const res = await fetch(
      `/api/skills/${encodeURIComponent(skillsBrowserActiveId)}/file?path=${encodeURIComponent(path)}`,
      { method: "DELETE" }
    );
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.deleteFailed"));
    if (isCurrentSkillFileUnder(path)) {
      resetSkillFileEditor();
    }
    const detail = await fetchSkillDetail(skillsBrowserActiveId);
    skillsDetailCache = detail;
    renderSkillFilesPane(detail);
    const bodyEl = $("#skills-tab-skill");
    if (bodyEl) {
      bodyEl.innerHTML = "";
      setMarkdownContent(bodyEl, detail.instructions || "");
    }
    updateSkillFileEditorUi();
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function openSkillFile(relPath, editable = true) {
  if (!skillsBrowserActiveId) return;
  if (relPath === skillsActiveFilePath) return;
  if (!(await confirmDiscardSkillFileChanges())) return;

  skillsActiveFilePath = relPath;
  skillsFileState = {
    path: relPath,
    savedContent: "",
    dirty: false,
    loading: true,
    editable,
  };
  updateSkillFileEditorUi();
  const editor = $("#skills-file-editor");
  if (editor) {
    editor.value = t("common.loading");
    editor.disabled = true;
  }
  renderSkillFilesPane(skillsDetailCache);

  try {
    if (!editable) {
      throw new Error(t("skills.notEditable"));
    }
    const res = await fetch(
      `/api/skills/${encodeURIComponent(skillsBrowserActiveId)}/file?path=${encodeURIComponent(relPath)}`
    );
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.openFailed"));
    const parts = relPath.split("/").filter(Boolean);
    for (let i = 1; i < parts.length; i++) {
      skillsFilesTreeCollapsed.delete(parts.slice(0, i).join("/"));
    }
    saveSkillsTreeCollapsedSet(skillsFilesTreeCollapsed);
    skillsFileState = {
      path: relPath,
      savedContent: data.content || "",
      dirty: false,
      loading: false,
      editable: Boolean(data.editable),
    };
    if (editor) {
      editor.value = data.editable ? data.content : t("skills.notTextPreview");
      editor.disabled = !data.editable;
    }
    setSkillFileStatus(t("common.loaded"), "saved");
  } catch (err) {
    skillsActiveFilePath = null;
    skillsFileState = {
      path: null,
      savedContent: "",
      dirty: false,
      loading: false,
      editable: true,
    };
    if (editor) {
      editor.value = "";
      editor.disabled = true;
    }
    setSkillFileStatus(networkErrorHint(err), "error");
  } finally {
    renderSkillFilesPane(skillsDetailCache);
    updateSkillFileEditorUi();
  }
}

async function saveSkillFileContent() {
  if (!skillsBrowserActiveId || !skillsFileState.path || !skillsFileState.editable) return;
  const editor = $("#skills-file-editor");
  const content = editor?.value ?? "";
  const saveBtn = $("#skills-file-save-btn");
  if (saveBtn) saveBtn.disabled = true;
  try {
    const res = await fetch(`/api/skills/${encodeURIComponent(skillsBrowserActiveId)}/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: skillsFileState.path, content }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.saveFailed"));
    skillsFileState.savedContent = content;
    skillsFileState.dirty = false;
    setSkillFileStatus(t("common.saved"), "saved");

    if (skillsFileState.path === "SKILL.md") {
      const detail = await fetchSkillDetail(skillsBrowserActiveId);
      skillsDetailCache = detail;
      const bodyEl = $("#skills-tab-skill");
      if (bodyEl) {
        bodyEl.innerHTML = "";
        setMarkdownContent(bodyEl, detail.instructions || "");
      }
    }
  } catch (err) {
    setSkillFileStatus(networkErrorHint(err), "error");
  }
  updateSkillFileEditorUi();
}

function setSkillsSkillMdStatus(text, kind = "") {
  const el = $("#skills-skill-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("dirty", "saved", "error");
  if (kind) el.classList.add(kind);
}

function updateSkillsSkillMdUi() {
  const editor = $("#skills-skill-editor");
  const saveBtn = $("#skills-skill-save-btn");
  if (!editor || !saveBtn) return;
  const canEdit = !skillsMdState.loading && Boolean(skillsBrowserActiveId);
  editor.disabled = !canEdit;
  saveBtn.disabled = !canEdit || !skillsMdState.dirty;
  if (skillsMdState.loading) {
    setSkillsSkillMdStatus(t("common.loading"));
  } else if (skillsMdState.dirty) {
    setSkillsSkillMdStatus(t("common.unsavedChanges"), "dirty");
  } else if (canEdit) {
    setSkillsSkillMdStatus(t("common.loaded"), "saved");
  } else {
    setSkillsSkillMdStatus("");
  }
}

async function loadSkillMdEditor(skillId) {
  const previewWrap = $("#skills-skill-preview-wrap");
  const editorWrap = $("#skills-skill-editor-wrap");
  const editor = $("#skills-skill-editor");
  if (!previewWrap || !editorWrap || !editor) return;

  skillsMdState = { savedContent: "", dirty: false, loading: true };
  updateSkillsSkillMdUi();
  editor.value = t("common.loading");
  editor.disabled = true;
  previewWrap.classList.add("hidden");
  editorWrap.classList.remove("hidden");

  try {
    const res = await fetch(
      `/api/skills/${encodeURIComponent(skillId)}/file?path=${encodeURIComponent("SKILL.md")}`
    );
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("skills.loadSkillMdFailed"));
    skillsMdState = {
      savedContent: data.content || "",
      dirty: false,
      loading: false,
    };
    editor.value = data.content || "";
  } catch (err) {
    skillsMdState.loading = false;
    editor.value = "";
    setSkillsSkillMdStatus(networkErrorHint(err), "error");
  }
  updateSkillsSkillMdUi();
}

async function saveSkillMdContent() {
  if (!skillsBrowserActiveId || skillsMdState.loading) return;
  const editor = $("#skills-skill-editor");
  const content = editor?.value ?? "";
  const saveBtn = $("#skills-skill-save-btn");
  if (saveBtn) saveBtn.disabled = true;
  try {
    const res = await fetch(`/api/skills/${encodeURIComponent(skillsBrowserActiveId)}/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "SKILL.md", content }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.saveFailed"));
    skillsMdState.savedContent = content;
    skillsMdState.dirty = false;
    setSkillsSkillMdStatus(t("common.saved"), "saved");
    const detail = await fetchSkillDetail(skillsBrowserActiveId);
    skillsDetailCache = detail;
    renderSkillToolsPane(detail);
    renderSkillFilesPane(detail);
    updateSkillsDetailTabs(detail);
    const previewEl = $("#skills-skill-preview-wrap");
    if (previewEl) {
      previewEl.innerHTML = "";
      setMarkdownContent(previewEl, detail.instructions || "");
    }
  } catch (err) {
    setSkillsSkillMdStatus(networkErrorHint(err), "error");
  }
  updateSkillsSkillMdUi();
}

function renderSkillSkillMdPane(detail) {
  const previewWrap = $("#skills-skill-preview-wrap");
  const editorWrap = $("#skills-skill-editor-wrap");
  if (!previewWrap || !editorWrap) return;

  skillsMdState = { savedContent: "", dirty: false, loading: false };

  if (detail.read_only) {
    previewWrap.classList.remove("hidden");
    editorWrap.classList.add("hidden");
    previewWrap.innerHTML = "";
    setMarkdownContent(previewWrap, detail.instructions || t("skills.noSkillBody"));
    return;
  }

  void loadSkillMdEditor(detail.id);
}

function renderSkillDetail(detail, { resetTab = false } = {}) {
  skillsDetailCache = detail;
  const titleEl = $("#skills-detail-title");
  const metaEl = $("#skills-detail-meta");
  if (!titleEl || !metaEl) return;

  if (resetTab) skillsDetailTab = "skill";

  titleEl.textContent = detail.name || detail.id;
  const metaParts = [
    skillOriginLabel(detail.origin || "system"),
    detail.version ? `v${detail.version}` : "",
    detail.studio_visible === false ? t("skills.notAutoEnabled") : "",
  ].filter(Boolean);
  metaEl.textContent = [detail.id, ...metaParts].join(" · ");
  metaEl.title = detail.path || "";

  $("#skills-readonly-hint")?.classList.toggle("hidden", !detail.read_only);
  const toolbar = $("#skills-detail-toolbar");
  const isCustom = detail.origin === "custom";
  toolbar?.classList.toggle("hidden", !isCustom);
  const newBtn = $("#skills-new-file-btn");
  if (newBtn) {
    newBtn.disabled = Boolean(detail.read_only);
    newBtn.classList.toggle("hidden", Boolean(detail.read_only));
  }
  const delCustomBtn = $("#skills-delete-custom-btn");
  if (delCustomBtn) {
    delCustomBtn.classList.toggle("hidden", !isCustom);
    delCustomBtn.onclick = isCustom ? () => deleteCustomSkill(detail.id) : null;
  }

  renderSkillToolsPane(detail);
  renderSkillFilesPane(detail);
  updateSkillsDetailTabs(detail);
  renderSkillSkillMdPane(detail);
}

async function selectSkillInBrowser(skillId) {
  if (skillsMdState.dirty) {
    if (!window.confirm(t("skills.unsavedSwitchSkill"))) return;
  }
  skillsBrowserActiveId = skillId;
  resetSkillFileEditor();
  skillsMdState = { savedContent: "", dirty: false, loading: false };
  renderSkillsBrowserList(getFilteredSkillsCache());
  const previewEl = $("#skills-skill-preview-wrap");
  const editorWrap = $("#skills-skill-editor-wrap");
  $("#skills-detail-tabs")?.classList.add("hidden");
  previewEl?.classList.remove("hidden");
  editorWrap?.classList.add("hidden");
  if (previewEl) previewEl.innerHTML = `<p class="hint">${t("common.loading")}</p>`;
  try {
    const detail = await fetchSkillDetail(skillId);
    renderSkillDetail(detail, { resetTab: true });
  } catch (err) {
    skillsDetailCache = null;
    if (previewEl) previewEl.textContent = networkErrorHint(err);
  }
}

async function renderSkillsBrowser() {
  const skills = await fetchSkills({ bustCache: true });
  loadSkillsCache(skills);
  updateSkillsOriginFilterUi();
  const filtered = getFilteredSkillsCache();
  renderSkillsBrowserList(filtered);
  if (filtered.length && !skillsBrowserActiveId) {
    await selectSkillInBrowser(filtered[0].id);
  } else if (skillsBrowserActiveId && filtered.some((sk) => sk.id === skillsBrowserActiveId)) {
    try {
      renderSkillDetail(await fetchSkillDetail(skillsBrowserActiveId));
    } catch {
      /* ignore refresh errors */
    }
  } else if (!filtered.length) {
    skillsBrowserActiveId = null;
    clearSkillDetailPanel();
  } else {
    await selectSkillInBrowser(filtered[0].id);
  }
}

function openSkillsLibrary(from = "chat") {
  if (!skillsReturnTarget) skillsReturnTarget = from;
  hideAllPanels();
  $("#main-panel").classList.remove("hidden");
  showSkillsView();
}

function showSkillsView() {
  if (skillAuthorMode) leaveSkillAuthorMode();
  chatViewMode = "skills";
  const titleEl = $("#chat-conv-title");
  if (titleEl) titleEl.textContent = t("skills.titleLibrary");
  $("#chat-view")?.classList.add("hidden");
  $("#system-preview-view")?.classList.add("hidden");
  $("#artifacts-view")?.classList.add("hidden");
  $("#skills-view")?.classList.remove("hidden");
  stopRuntimeErrorPoll();
  setPanelHeadActions({ artifacts: false, systemPreview: false, skills: false, back: true });
  syncConvHistorySidebar();
  renderSkillsBrowser();
}

function leaveSkillsView() {
  const target = skillsReturnTarget || "chat";
  skillsReturnTarget = null;
  if (target === "projects") {
    showProjectPicker();
    return;
  }
  if (skillAuthorMode) leaveSkillAuthorMode();
  showChatView();
}

function showArtifactsView() {
  chatViewMode = "artifacts";
  skillsReturnTarget = null;
  const titleEl = $("#chat-conv-title");
  if (titleEl) titleEl.textContent = t("artifacts.title");
  $("#chat-view")?.classList.add("hidden");
  $("#system-preview-view")?.classList.add("hidden");
  $("#skills-view")?.classList.add("hidden");
  $("#artifacts-view")?.classList.remove("hidden");
  stopRuntimeErrorPoll();
  setPanelHeadActions({ artifacts: false, systemPreview: false, skills: false, back: true });
  syncConvHistorySidebar();
}

function showSystemPreviewView() {
  chatViewMode = "system-preview";
  skillsReturnTarget = null;
  const titleEl = $("#chat-conv-title");
  if (titleEl) titleEl.textContent = t("preview.title");
  $("#chat-view")?.classList.add("hidden");
  $("#artifacts-view")?.classList.add("hidden");
  $("#skills-view")?.classList.add("hidden");
  $("#system-preview-view")?.classList.remove("hidden");
  setPanelHeadActions({ artifacts: true, systemPreview: false, skills: true, back: true });
  syncConvHistorySidebar();
}

function buildSystemPreviewUrl(projectName, apiBase) {
  const info = systemPreviewCache.frontends.find((f) => f.project_name === projectName);
  if (!info?.has_preview) return null;
  const entry = info.preview_entry || "preview.html";
  const base = apiBase || info.runtime_api_base || info.api_base_url || "";
  let url = `/api/frontend-preview/${encodeURIComponent(projectName)}/${encodeURIComponent(entry)}`;
  if (base) {
    url += `?studio_api_base=${encodeURIComponent(base)}`;
  }
  return url;
}

function updateSystemPreviewOpenTabButton(enabled) {
  const btn = $("#system-preview-open-tab-btn");
  if (!btn) return;
  btn.disabled = !enabled;
}

function openSystemPreviewInNewTab() {
  const project = $("#system-preview-project-select")?.value;
  if (!project) return;
  const info = systemPreviewCache.frontends.find((f) => f.project_name === project);
  const apiBase = info?.runtime_api_base || info?.api_base_url || "";
  const rel = buildSystemPreviewUrl(project, apiBase);
  if (!rel) return;
  const href = new URL(rel, window.location.origin).href;
  const opened = window.open(href, "_blank", "noopener,noreferrer");
  if (!opened) {
    window.alert(t("preview.popupBlocked"));
  }
}

function reloadSystemPreviewFrame(projectName, apiBase) {
  const frame = $("#system-preview-frame");
  const empty = $("#system-preview-empty");
  const info = systemPreviewCache.frontends.find((f) => f.project_name === projectName);
  if (!frame || !empty) return;
  if (!info?.has_preview) {
    frame.classList.add("hidden");
    empty.classList.remove("hidden");
    frame.removeAttribute("src");
    updateSystemPreviewOpenTabButton(false);
    return;
  }
  frame.classList.remove("hidden");
  empty.classList.add("hidden");
  beginPreviewIframeSettling();
  const rel = buildSystemPreviewUrl(projectName, apiBase);
  const bust = rel.includes("?") ? "&" : "?";
  frame.src = `${rel}${bust}t=${Date.now()}`;
  updateSystemPreviewOpenTabButton(true);
  if (!frame.dataset.runtimeErrorLoadBound) {
    frame.dataset.runtimeErrorLoadBound = "1";
    frame.addEventListener("load", () => beginPreviewIframeSettling());
  }
}

let backendLogPollTimer = null;
let systemPreviewRestartBusy = false;

function stopBackendLogPoll() {
  if (backendLogPollTimer) {
    clearInterval(backendLogPollTimer);
    backendLogPollTimer = null;
  }
}

function isBackendLogAutoRefreshOn() {
  const btn = $("#system-preview-log-autorefresh-btn");
  return btn?.classList.contains("is-active") || btn?.getAttribute("aria-pressed") === "true";
}

function setBackendLogAutoRefresh(on) {
  const btn = $("#system-preview-log-autorefresh-btn");
  if (!btn) return;
  btn.classList.toggle("is-active", on);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  if (on) startBackendLogPoll();
  else stopBackendLogPoll();
}

function startBackendLogPoll() {
  stopBackendLogPoll();
  if (!isBackendLogAutoRefreshOn()) return;
  if ($("#system-preview-log-panel")?.classList.contains("hidden")) return;
  backendLogPollTimer = setInterval(() => {
    refreshBackendLog({ scroll: false });
  }, 3000);
}

function closeBackendLogPanel() {
  $("#system-preview-log-panel")?.classList.add("hidden");
  $("#system-preview-log-btn")?.classList.remove("is-active");
  stopBackendLogPoll();
}

function updateSystemPreviewLogButton(projectName) {
  const btn = $("#system-preview-log-btn");
  if (!btn) return;
  const info = systemPreviewCache.frontends?.find((f) => f.project_name === projectName);
  const linked = info?.linked_backend;
  btn.disabled = !linked;
  btn.title = linked
    ? t("preview.logView", { name: linked })
    : t("preview.noLinkedBackend");
}

function updateSystemPreviewRestartButton(projectName) {
  const btn = $("#system-preview-restart-btn");
  if (!btn || systemPreviewRestartBusy) return;
  const info = systemPreviewCache.frontends?.find((f) => f.project_name === projectName);
  const linked = info?.linked_backend;
  btn.disabled = !linked;
  btn.title = linked
    ? t("preview.restartLinked", { name: linked })
    : t("preview.noLinkedBackend");
}

async function restartSystemPreviewBackend() {
  if (systemPreviewRestartBusy) return;
  const project = $("#system-preview-project-select")?.value;
  if (!project) return;
  const info = systemPreviewCache.frontends.find((f) => f.project_name === project);
  if (!info?.linked_backend) return;

  const btn = $("#system-preview-restart-btn");
  const hint = $("#system-preview-backend-hint");
  systemPreviewRestartBusy = true;
  if (btn) {
    btn.disabled = true;
    btn.textContent = t("preview.restarting");
  }
  if (hint) {
    hint.textContent = t("preview.restartingBackend", { name: info.linked_backend });
    hint.classList.remove("hidden");
  }
  try {
    const res = await fetch("/api/system-preview/restart", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frontend_project: project }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("preview.restartFailed"));
    info.runtime_api_base = data.api_base_url;
    info.backend_port = data.port;
    info.backend_started = true;
    if (hint && data.message) {
      hint.textContent = data.message;
      hint.classList.remove("hidden");
    }
    reloadSystemPreviewFrame(project, data.api_base_url);
    renderSystemPreviewMeta(project);
    void pollRuntimeErrors({ resetWatch: true });
    if (!$("#system-preview-log-panel")?.classList.contains("hidden")) {
      await refreshBackendLog({ resetWatch: true });
    }
  } catch (err) {
    if (hint) {
      hint.textContent = networkErrorHint(err);
      hint.classList.remove("hidden");
    }
  } finally {
    systemPreviewRestartBusy = false;
    if (btn) btn.textContent = t("preview.restart");
    updateSystemPreviewRestartButton(project);
  }
}

async function refreshBackendLog({
  scroll = true,
  updatePanel = true,
  resetWatch = false,
  frontendProject = null,
} = {}) {
  const project = frontendProject || $("#system-preview-project-select")?.value;
  const pre = $("#system-preview-log-content");
  const title = $("#system-preview-log-title");
  if (!project) {
    if (updatePanel && pre) pre.textContent = t("preview.selectFrontend");
    return null;
  }
  try {
    const params = new URLSearchParams({
      frontend_project: project,
      tail_lines: "400",
    });
    if (resetWatch) params.set("reset_watch", "true");
    const res = await fetch(`/api/system-preview/backend-log?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("preview.logFailed"));
    processRuntimeLogPoll(data, {
      frontend_project: project,
      backend_project: data.backend_project,
    });
    if (updatePanel) {
      if (title) {
        let label = data.log_path || "backend/…/.studio_uvicorn.log";
        if (data.runtime?.port) label += t("preview.runningPort", { port: data.runtime.port });
        else if (data.exists) label += t("preview.stopped");
        if (data.truncated) label += t("preview.truncated");
        const errN = pendingRuntimeErrors.length || (data.runtime_errors || []).length;
        if (errN) label += t("preview.pendingErrors", { count: errN });
        title.textContent = label;
      }
      if (pre) {
        pre.textContent = data.content || "";
        if (scroll) pre.scrollTop = pre.scrollHeight;
      }
    }
    return data;
  } catch (err) {
    if (updatePanel && pre) pre.textContent = t("preview.readLogFailed", { error: err.message || err });
    return null;
  }
}

function openBackendLogPanel() {
  const panel = $("#system-preview-log-panel");
  if (!panel) return;
  panel.classList.remove("hidden");
  $("#system-preview-log-btn")?.classList.add("is-active");
  refreshBackendLog();
  startBackendLogPoll();
}

async function ensureSystemPreviewBackend(frontendProject) {
  const info = systemPreviewCache.frontends.find(
    (f) => f.project_name === frontendProject
  );
  if (!info?.linked_backend) {
    return null;
  }
  const res = await fetch("/api/system-preview/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ frontend_project: frontendProject }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(formatApiError(data.detail) || t("preview.startFailed"));
  }
  info.runtime_api_base = data.api_base_url;
  info.backend_port = data.port;
  info.backend_started = data.started;
  if (data.message && $("#system-preview-backend-hint")) {
    $("#system-preview-backend-hint").textContent = data.message;
    $("#system-preview-backend-hint").classList.remove("hidden");
  }
  return data;
}

function renderSystemPreviewMeta(projectName) {
  const meta = $("#system-preview-meta");
  const backendHint = $("#system-preview-backend-hint");
  const info = systemPreviewCache.frontends.find((f) => f.project_name === projectName);
  if (!meta) return;
  if (!info) {
    meta.textContent = "";
    backendHint?.classList.add("hidden");
    return;
  }
  const parts = [];
  if (info.preview_entry) parts.push(t("preview.previewFile", { file: info.preview_entry }));
  if (info.has_ui_knowledge) parts.push(t("preview.hasUiKnowledge"));
  meta.textContent = parts.join(" · ") || "—";
    if (backendHint) {
    if (info.runtime_api_base) {
      backendHint.textContent = t("preview.backendRunning", { name: info.linked_backend, api: info.runtime_api_base, port: info.backend_port || "—" });
      backendHint.classList.remove("hidden");
    } else if (info.linked_backend && info.api_base_url) {
      backendHint.textContent = t("preview.backendLinked", { name: info.linked_backend, api: info.api_base_url });
      backendHint.classList.remove("hidden");
    } else if (systemPreviewCache.backends?.length) {
      backendHint.textContent =
        t("preview.unlinkHint");
      backendHint.classList.remove("hidden");
    } else {
      backendHint.classList.add("hidden");
      backendHint.textContent = "";
    }
  }
}

async function fillSystemPreviewProjectSelect(selected) {
  const sel = $("#system-preview-project-select");
  const backendHint = $("#system-preview-backend-hint");
  if (!sel) return;
  sel.innerHTML = "";
  const list = systemPreviewCache.frontends;
  if (!list.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = t("preview.noFrontend");
    sel.appendChild(opt);
    sel.disabled = true;
    updateSystemPreviewOpenTabButton(false);
    updateSystemPreviewRestartButton(null);
    return;
  }
  sel.disabled = false;
  list.forEach((f) => {
    const opt = document.createElement("option");
    opt.value = f.project_name;
    const label = f.has_preview ? f.project_name : t("preview.noPreviewPage", { name: f.project_name });
    opt.textContent = label;
    sel.appendChild(opt);
  });
  const pick =
    selected && list.some((f) => f.project_name === selected)
      ? selected
      : systemPreviewCache.defaultFrontend || list[0].project_name;
  sel.value = pick;
  const info = list.find((f) => f.project_name === pick);
  let apiBase = info?.api_base_url || "";
  if (info?.linked_backend) {
    if (backendHint) {
      backendHint.textContent = t("preview.startingBackend", { name: info.linked_backend });
      backendHint.classList.remove("hidden");
    }
    try {
      const rt = await ensureSystemPreviewBackend(pick);
      apiBase = rt?.api_base_url || apiBase;
    } catch (err) {
      if (backendHint) {
        backendHint.textContent = networkErrorHint(err);
        backendHint.classList.remove("hidden");
      }
    }
  }
  const projectChanged =
    lastErrorWatchProject !== null && lastErrorWatchProject !== pick;
  lastErrorWatchProject = pick;
  resetRuntimeErrorWatchForProject(pick, { hard: projectChanged });
  reloadSystemPreviewFrame(pick, apiBase);
  renderSystemPreviewMeta(pick);
  updateSystemPreviewLogButton(pick);
  updateSystemPreviewRestartButton(pick);
  startRuntimeErrorPoll(pick, { resetWatch: projectChanged });
}

async function openSystemPreviewPage() {
  if (!(await confirmDiscardArtifactsChanges())) return;
  showSystemPreviewView();
  const empty = $("#system-preview-empty");
  const frame = $("#system-preview-frame");
  try {
    const res = await fetch("/api/system-preview");
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("preview.loadFailed"));
    systemPreviewCache = {
      frontends: data.frontends || [],
      defaultFrontend: data.default_frontend || null,
      backends: data.backends || [],
    };
    if (!data.has_any_preview && empty) {
      const p = empty.querySelector("p");
      if (p && data.frontends?.length) {
        p.textContent = t("preview.missingPreview");
      }
    }
    await fillSystemPreviewProjectSelect(data.default_frontend);
  } catch (err) {
    systemPreviewCache = { frontends: [], defaultFrontend: null, backends: [] };
    await fillSystemPreviewProjectSelect(null);
    if (empty) {
      empty.classList.remove("hidden");
      const msg = empty.querySelector("p");
      if (msg) msg.textContent = networkErrorHint(err);
    }
    frame?.classList.add("hidden");
  }
}

function unquoteYamlValue(raw) {
  const val = String(raw).trim();
  if (val.length >= 2 && val[0] === val[val.length - 1] && (val[0] === '"' || val[0] === "'")) {
    return val.slice(1, -1);
  }
  return val;
}

function parseMarkdownFrontmatter(content) {
  const m = String(content).match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n)?/);
  if (!m) {
    return { hasFrontmatter: false, fields: {}, order: [], body: content };
  }
  const fields = {};
  const order = [];
  m[1].split("\n").forEach((line) => {
    const hit = line.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$/);
    if (!hit) return;
    fields[hit[1]] = unquoteYamlValue(hit[2]);
    order.push(hit[1]);
  });
  return { hasFrontmatter: true, fields, order, body: content.slice(m[0].length) };
}

function serializeMarkdownFrontmatter(fields, order) {
  const keys = [];
  (order || []).forEach((k) => {
    if (k in fields && !keys.includes(k)) keys.push(k);
  });
  Object.keys(fields).forEach((k) => {
    if (!keys.includes(k)) keys.push(k);
  });
  const lines = ["---"];
  keys.forEach((key) => {
    const val = String(fields[key] ?? "");
    const quoted = /[:#\n",]/.test(val);
    lines.push(quoted ? `${key}: "${val.replace(/"/g, '\\"')}"` : `${key}: ${val}`);
  });
  lines.push("---");
  return `${lines.join("\n")}\n\n`;
}

function resetArtifactsFrontmatter() {
  artifactsState.hasFrontmatter = false;
  artifactsState.frontmatterFields = null;
  artifactsState.frontmatterOrder = [];
  $("#artifacts-frontmatter")?.classList.add("hidden");
  const list = $("#artifacts-fm-fields");
  if (list) list.innerHTML = "";
  renderArtifactsAliasChip("");
}

function collectFrontmatterFromDom() {
  const fields = { ...(artifactsState.frontmatterFields || {}) };
  $$("#artifacts-fm-fields [data-fm-key]").forEach((el) => {
    const key = el.dataset.fmKey;
    if (!key || ARTIFACT_FM_READONLY.has(key)) return;
    fields[key] = el.value;
  });
  return fields;
}

function getArtifactEditorContent() {
  const editor = $("#artifacts-editor");
  if (!editor) return "";
  if (!artifactsState.hasFrontmatter) return editor.value;
  const fields = collectFrontmatterFromDom();
  return serializeMarkdownFrontmatter(fields, artifactsState.frontmatterOrder) + editor.value;
}

function markArtifactsDirty() {
  if (!artifactsState.currentPath || artifactsState.loading) return;
  artifactsState.dirty = getArtifactEditorContent() !== artifactsState.savedContent;
  updateArtifactsEditorUi();
}

function renderArtifactsAliasChip(value) {
  const chip = $("#artifacts-fm-alias");
  if (!chip) return;
  if (!value) {
    chip.classList.add("hidden");
    chip.innerHTML = "";
    return;
  }
  chip.classList.remove("hidden");
  chip.innerHTML = `
    <span class="artifacts-fm-alias-label">${t("artifacts.workspaceLabel")}</span>
    <span class="artifacts-fm-alias-value">${escapeHtml(value)}</span>
    <svg class="artifacts-fm-alias-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <rect x="5" y="11" width="14" height="10" rx="2"/>
      <path d="M8 11V8a4 4 0 0 1 8 0v3"/>
    </svg>
  `;
}

function renderArtifactsFrontmatter(fields, order) {
  const panel = $("#artifacts-frontmatter");
  const list = $("#artifacts-fm-fields");
  if (!panel || !list) return;
  const keys = [];
  (order || []).forEach((k) => {
    if (k in fields && !keys.includes(k)) keys.push(k);
  });
  ARTIFACT_FM_DEFAULT_ORDER.forEach((k) => {
    if (k in fields && !keys.includes(k)) keys.push(k);
  });
  Object.keys(fields).forEach((k) => {
    if (!keys.includes(k)) keys.push(k);
  });
  artifactsState.frontmatterOrder = keys;
  artifactsState.frontmatterFields = { ...fields };

  renderArtifactsAliasChip(fields.db_alias ?? "");

  list.innerHTML = "";
  keys.forEach((key) => {
    if (ARTIFACT_FM_READONLY.has(key)) return;

    const isMultiline = ARTIFACT_FM_MULTILINE.has(key);
    const row = document.createElement("div");
    row.className = "artifacts-fm-row" + (isMultiline ? " block" : "");

    const meta = document.createElement("div");
    meta.className = "artifacts-fm-row-meta";
    const name = document.createElement("span");
    name.className = "artifacts-fm-name";
    name.textContent = getArtifactFmLabels()[key] || key;
    const keyEl = document.createElement("span");
    keyEl.className = "artifacts-fm-key";
    keyEl.textContent = key;
    meta.appendChild(name);
    meta.appendChild(keyEl);

    const control = document.createElement("div");
    control.className = "artifacts-fm-row-control";
    const value = fields[key] ?? "";

    if (isMultiline) {
      const ta = document.createElement("textarea");
      ta.className = "artifacts-fm-textarea";
      ta.id = `artifacts-fm-${key}`;
      ta.dataset.fmKey = key;
      ta.value = value;
      ta.rows = key === "business_goal" ? 2 : 3;
      ta.addEventListener("input", markArtifactsDirty);
      control.appendChild(ta);
    } else {
      const input = document.createElement("input");
      input.className = "artifacts-fm-input";
      input.id = `artifacts-fm-${key}`;
      input.dataset.fmKey = key;
      input.type = key === "generated_at" ? "date" : "text";
      input.value = value;
      input.addEventListener("input", markArtifactsDirty);
      control.appendChild(input);
    }

    row.appendChild(meta);
    row.appendChild(control);
    list.appendChild(row);
  });
  panel.classList.remove("hidden");
  setArtifactsFmCollapsed(loadArtifactsFmCollapsed());
}

function parseFrontendArtifactPath(path) {
  const p = String(path || "");
  if (!p.startsWith("frontend/")) return null;
  const rest = p.slice("frontend/".length);
  const slash = rest.indexOf("/");
  if (slash < 0) return null;
  return { project: rest.slice(0, slash), relPath: rest.slice(slash + 1) };
}

function isArtifactHtmlFile(path) {
  const p = String(path || "").toLowerCase();
  return p.endsWith(".html") || p.endsWith(".htm");
}

function isArtifactMarkdownWithFrontmatter(path) {
  const p = String(path || "").toLowerCase();
  if (!p.endsWith(".md")) return false;
  return (
    p.startsWith("dataset/") ||
    /\/ui_knowledge\.md$/.test(p) ||
    /\/api_knowledge\.md$/.test(p)
  );
}

function reloadArtifactsPreviewFrame() {
  const frame = $("#artifacts-preview-frame");
  const proj = artifactsState.previewProject;
  const rel = artifactsState.previewRelPath;
  if (!frame || !proj || !rel) return;
  const url = `/api/frontend-preview/${encodeURIComponent(proj)}/${encodeURIComponent(rel)}?t=${Date.now()}`;
  frame.src = url;
}

function updateArtifactsViewTabs() {
  const tabs = $("#artifacts-view-tabs");
  const show = artifactsState.previewAvailable;
  tabs?.classList.toggle("hidden", !show);
  if (!show) {
    if (artifactsState.editorTab === "preview") {
      artifactsState.editorTab = "edit";
    }
    return;
  }
  $$(".artifacts-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === artifactsState.editorTab);
    btn.disabled = btn.dataset.tab === "preview" && !artifactsState.previewAvailable;
  });
}

function setArtifactsEditorTab(tab) {
  if (tab === "preview" && !artifactsState.previewAvailable) {
    tab = "edit";
  }
  artifactsState.editorTab = tab;
  const isPreview = tab === "preview";
  const fm = $("#artifacts-frontmatter");
  if (isPreview || !artifactsState.hasFrontmatter) {
    fm?.classList.add("hidden");
  } else {
    fm?.classList.remove("hidden");
  }
  $("#artifacts-editor")?.classList.toggle("hidden", isPreview);
  $("#artifacts-preview-wrap")?.classList.toggle("hidden", !isPreview);
  $("#artifacts-preview-empty")?.classList.toggle(
    "hidden",
    !isPreview || artifactsState.previewAvailable
  );
  $("#artifacts-save-btn")?.classList.toggle("hidden", isPreview);
  updateArtifactsViewTabs();
  if (isPreview && artifactsState.previewProject) {
    reloadArtifactsPreviewFrame();
  }
}

async function syncArtifactsPreviewContext(path) {
  const parsed = parseFrontendArtifactPath(path);
  artifactsState.previewProject = parsed?.project ?? null;
  artifactsState.previewRelPath = parsed?.relPath ?? null;
  artifactsState.previewAvailable = Boolean(parsed && isArtifactHtmlFile(path));
  artifactsState.editorTab = artifactsState.previewAvailable ? "preview" : "edit";
  setArtifactsEditorTab(artifactsState.editorTab);
}

function applyArtifactFileContent(rawContent, path) {
  const editor = $("#artifacts-editor");
  if (!editor) return;
  resetArtifactsFrontmatter();
  if (isArtifactMarkdownWithFrontmatter(path)) {
    const parsed = parseMarkdownFrontmatter(rawContent);
    if (parsed.hasFrontmatter && Object.keys(parsed.fields).length) {
      if (chatState.dbAlias) {
        parsed.fields.db_alias = chatState.dbAlias;
      }
      artifactsState.hasFrontmatter = true;
      renderArtifactsFrontmatter(parsed.fields, parsed.order);
      editor.value = parsed.body;
      return;
    }
  }
  editor.value = rawContent;
}

function setArtifactsStatus(text, kind = "") {
  const el = $("#artifacts-editor-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("dirty", "saved", "error");
  if (kind) el.classList.add(kind);
}

function updateArtifactsEditorUi() {
  const editor = $("#artifacts-editor");
  const saveBtn = $("#artifacts-save-btn");
  const label = $("#artifacts-file-label");
  if (!editor || !saveBtn || !label) return;
  const hasFile = Boolean(artifactsState.currentPath);
  label.textContent = hasFile ? artifactsState.currentPath : t("common.noFileSelected");
  const canEdit = hasFile && !artifactsState.loading;
  editor.disabled = !canEdit;
  saveBtn.disabled = !canEdit || !artifactsState.dirty;
  if (artifactsState.dirty) {
    setArtifactsStatus(t("artifacts.unsaved"), "dirty");
  } else if (hasFile && !artifactsState.loading) {
    setArtifactsStatus(t("artifacts.loaded"), "saved");
  }
}

async function confirmDiscardArtifactsChanges() {
  if (!artifactsState.dirty) return true;
  return window.confirm(t("artifacts.unsavedDiscard"));
}

function isDirCollapsed(path) {
  return artifactsState.treeCollapsed.has(path);
}

function toggleDirCollapsed(path) {
  if (artifactsState.treeCollapsed.has(path)) {
    artifactsState.treeCollapsed.delete(path);
  } else {
    artifactsState.treeCollapsed.add(path);
  }
  saveTreeCollapsedSet(artifactsState.treeCollapsed);
}

function createTreeChevron(collapsed) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "artifacts-tree-chevron" + (collapsed ? " collapsed" : "");
  btn.setAttribute("aria-label", collapsed ? t("common.expand") : t("common.collapse"));
  btn.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  return btn;
}

function normalizeArtifactPath(input, parentDir) {
  let p = String(input || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\/+/, "");
  if (!p) throw new Error(t("skills.pathRequired"));
  if (parentDir) {
    const parent = parentDir.replace(/\/+$/, "");
    if (
      !p.startsWith("dataset/") &&
      !p.startsWith("frontend/") &&
      !p.startsWith("backend/")
    ) {
      p = `${parent}/${p}`;
    }
  }
  if (
    !p.startsWith("dataset/") &&
    !p.startsWith("frontend/") &&
    !p.startsWith("backend/")
  ) {
    throw new Error(t("artifacts.pathPrefix"));
  }
  if (p.split("/").includes("..")) throw new Error(t("skills.pathInvalid"));
  return p;
}

async function promptNewArtifact(parentDir) {
  const hint = parentDir
    ? t("artifacts.newInDir", { dir: parentDir })
    : t("artifacts.newExamples");
  const raw = window.prompt(hint, "");
  if (raw == null || !String(raw).trim()) return;
  try {
    const path = normalizeArtifactPath(raw, parentDir || undefined);
    await createArtifactFile(path, "");
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function createArtifactFile(path, content = "") {
  if (!(await confirmDiscardArtifactsChanges())) return;
  const res = await fetch("/api/artifacts/file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.createFailed"));
  await renderArtifactsTreePanel();
  await openArtifactFile(path, true);
}

function isArtifactRootDir(path) {
  return path === "dataset" || path === "frontend" || path === "backend";
}

function isCurrentArtifactUnder(deletedPath) {
  const cur = artifactsState.currentPath;
  if (!cur) return false;
  return cur === deletedPath || cur.startsWith(`${deletedPath}/`);
}

async function deleteArtifactFile(path, label, { isDir = false } = {}) {
  const name = label || path;
  let msg = isDir
    ? t("skills.deleteFolder", { name })
    : t("skills.deleteFile", { name });
  if (isArtifactRootDir(path)) {
    msg = t("artifacts.deleteRoot", { name });
  }
  if (!window.confirm(msg)) return;
  if (
    isCurrentArtifactUnder(path) &&
    artifactsState.dirty &&
    !window.confirm(t("skills.deleteUnsaved"))
  ) {
    return;
  }
  try {
    const res = await fetch(`/api/artifacts/file?path=${encodeURIComponent(path)}`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.deleteFailed"));
    if (isCurrentArtifactUnder(path)) {
      artifactsState.currentPath = null;
      artifactsState.savedContent = "";
      artifactsState.dirty = false;
      artifactsState.previewProject = null;
      artifactsState.previewRelPath = null;
      artifactsState.previewAvailable = false;
      resetArtifactsFrontmatter();
      const editor = $("#artifacts-editor");
      if (editor) {
        editor.value = "";
        editor.disabled = true;
      }
      setArtifactsEditorTab("edit");
      updateArtifactsViewTabs();
    }
    await renderArtifactsTreePanel();
    updateArtifactsEditorUi();
    if (isArtifactRootDir(path)) {
      setArtifactsStatus(
        t("artifacts.deletedRoot", { path }),
        "saved"
      );
    }
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

function renderArtifactsTreeNode(node) {
  if (node.type === "file") {
    const li = document.createElement("li");
    li.className = "artifacts-tree-item";
    const row = document.createElement("div");
    row.className =
      "artifacts-tree-file-row" + (node.path === artifactsState.currentPath ? " active" : "");

    const spacer = document.createElement("span");
    spacer.className = "artifacts-tree-chevron placeholder";
    spacer.setAttribute("aria-hidden", "true");

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "artifacts-tree-file" + (node.editable === false ? " not-editable" : "");
    btn.title = node.editable === false ? t("artifacts.notEditable", { path: node.path }) : node.path;
    btn.textContent = node.name;
    btn.addEventListener("click", () => openArtifactFile(node.path, node.editable !== false));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "artifacts-tree-action artifacts-tree-delete";
    delBtn.title = node.editable === false ? t("skills.deleteFileReadonly") : t("skills.deleteFileBtn");
    delBtn.setAttribute("aria-label", t("skills.deleteAria", { name: node.name }));
    delBtn.textContent = "×";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteArtifactFile(node.path, node.name);
    });

    row.appendChild(spacer);
    row.appendChild(btn);
    row.appendChild(delBtn);
    li.appendChild(row);
    return li;
  }

  const collapsed = isDirCollapsed(node.path);
  const li = document.createElement("li");
  li.className = "artifacts-tree-item";

  const row = document.createElement("div");
  row.className = "artifacts-tree-dir-row";

  const chevron = createTreeChevron(collapsed);
  const nameBtn = document.createElement("button");
  nameBtn.type = "button";
  nameBtn.className = "artifacts-tree-dir";
  nameBtn.title = node.path;
  nameBtn.textContent = node.name;

  const newBtn = document.createElement("button");
  newBtn.type = "button";
  newBtn.className = "artifacts-tree-action";
  newBtn.title = t("artifacts.newInDirBtn");
  newBtn.setAttribute("aria-label", t("skills.newInDirAria", { name: node.name }));
  newBtn.textContent = "+";
  newBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    promptNewArtifact(node.path);
  });

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "artifacts-tree-action artifacts-tree-delete";
  delBtn.title = isArtifactRootDir(node.path)
    ? t("artifacts.deleteRootBtn", { name: node.name })
    : t("artifacts.deleteFolderBtn");
  delBtn.setAttribute("aria-label", t("skills.deleteFolderAria", { name: node.name }));
  delBtn.textContent = "×";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteArtifactFile(node.path, node.name, { isDir: true });
  });

  const childrenUl = document.createElement("ul");
  childrenUl.className = "artifacts-tree-children" + (collapsed ? " hidden" : "");
  (node.children || []).forEach((child) => childrenUl.appendChild(renderArtifactsTreeNode(child)));

  const applyCollapsed = () => {
    const isCollapsed = isDirCollapsed(node.path);
    childrenUl.classList.toggle("hidden", isCollapsed);
    chevron.classList.toggle("collapsed", isCollapsed);
    chevron.setAttribute("aria-label", isCollapsed ? t("common.expand") : t("common.collapse"));
  };

  const toggle = () => {
    toggleDirCollapsed(node.path);
    applyCollapsed();
  };
  chevron.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });
  nameBtn.addEventListener("click", toggle);

  row.appendChild(chevron);
  row.appendChild(nameBtn);
  row.appendChild(newBtn);
  if (delBtn) row.appendChild(delBtn);
  li.appendChild(row);
  li.appendChild(childrenUl);
  return li;
}

function renderArtifactsTree(roots) {
  const treeEl = $("#artifacts-tree");
  const emptyEl = $("#artifacts-tree-empty");
  if (!treeEl) return;
  treeEl.innerHTML = "";
  if (!roots?.length) {
    emptyEl?.classList.remove("hidden");
    return;
  }
  const hasFiles = (nodes) => {
    for (const n of nodes || []) {
      if (n.type === "file") return true;
      if (n.children?.length && hasFiles(n.children)) return true;
    }
    return false;
  };
  if (!hasFiles(roots)) {
    emptyEl?.classList.remove("hidden");
  } else {
    emptyEl?.classList.add("hidden");
  }
  const ul = document.createElement("ul");
  roots.forEach((root) => ul.appendChild(renderArtifactsTreeNode(root)));
  treeEl.appendChild(ul);
}

async function fetchArtifactsTree() {
  const res = await fetch("/api/artifacts");
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("artifacts.loadTreeFailed"));
  return data;
}

async function fetchArtifactFile(path) {
  const res = await fetch(`/api/artifacts/file?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("artifacts.readFailed"));
  return data.file;
}

async function saveArtifactFile(path, content) {
  const res = await fetch("/api/artifacts/file", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.saveFailed"));
  return data.file;
}

async function openArtifactFile(path, editable = true) {
  if (path === artifactsState.currentPath) return;
  if (!(await confirmDiscardArtifactsChanges())) return;
  artifactsState.loading = true;
  artifactsState.currentPath = path;
  artifactsState.dirty = false;
  resetArtifactsFrontmatter();
  updateArtifactsEditorUi();
  const editor = $("#artifacts-editor");
  if (editor) {
    editor.value = t("common.loading");
    editor.disabled = true;
  }
  $("#artifacts-save-btn")?.setAttribute("disabled", "true");
  setArtifactsStatus("");
  try {
    if (!editable) {
      throw new Error(t("skills.notEditable"));
    }
    const file = await fetchArtifactFile(path);
    const raw = file.content ?? "";
    artifactsState.savedContent = raw;
    applyArtifactFileContent(raw, path);
    artifactsState.dirty = false;
    await syncArtifactsPreviewContext(path);
    setArtifactsStatus(t("artifacts.loaded"), "saved");
  } catch (err) {
    artifactsState.currentPath = null;
    artifactsState.savedContent = "";
    artifactsState.previewProject = null;
    artifactsState.previewRelPath = null;
    artifactsState.previewAvailable = false;
    resetArtifactsFrontmatter();
    if (editor) {
      editor.value = "";
      editor.disabled = true;
    }
    setArtifactsStatus(networkErrorHint(err), "error");
  } finally {
    artifactsState.loading = false;
    renderArtifactsTreePanel();
    updateArtifactsEditorUi();
  }
}

async function renderArtifactsTreePanel() {
  try {
    const data = await fetchArtifactsTree();
    renderArtifactsTree(data.roots || []);
  } catch (err) {
    $("#artifacts-tree-empty")?.classList.remove("hidden");
    const emptyEl = $("#artifacts-tree-empty");
    if (emptyEl) emptyEl.textContent = networkErrorHint(err);
  }
}

async function openArtifactsPage() {
  if (!(await confirmDiscardArtifactsChanges())) return;
  showArtifactsView();
  await renderArtifactsTreePanel();
  updateArtifactsEditorUi();
}

async function saveCurrentArtifact() {
  const path = artifactsState.currentPath;
  const editor = $("#artifacts-editor");
  if (!path || !editor || artifactsState.loading) return;
  const saveBtn = $("#artifacts-save-btn");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = t("common.saving");
  }
  try {
    const content = getArtifactEditorContent();
    await saveArtifactFile(path, content);
    applyArtifactFileContent(content, path);
    artifactsState.savedContent = getArtifactEditorContent();
    artifactsState.dirty = false;
    setArtifactsStatus(t("artifacts.saved"), "saved");
    if (artifactsState.previewAvailable) reloadArtifactsPreviewFrame();
  } catch (err) {
    setArtifactsStatus(networkErrorHint(err), "error");
  } finally {
    if (saveBtn) saveBtn.textContent = t("common.save");
    updateArtifactsEditorUi();
  }
}

async function startNewConversation({ announce = true } = {}) {
  if (!chatState.dbAlias) return;
  try {
    applyConversation(await apiCreateConversation());
    showChatView();
    if (announce) {
      appendMessage("system", t("chat.newStartedSaved"));
    }
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function openConversation(conversationId) {
  try {
    applyConversation(await apiLoadConversation(conversationId));
    showChatView();
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function renderConversationHistory() {
  const seq = ++convHistoryRenderSeq;
  const listEl = $("#conv-history-list");
  const emptyEl = $("#conv-history-empty");
  if (!listEl) return;
  listEl.innerHTML = "";
  try {
    const items = await fetchConversations();
    if (seq !== convHistoryRenderSeq) return;
    const seen = new Set();
    const unique = [];
    for (const c of items) {
      const id = c?.id;
      if (!id || seen.has(id)) continue;
      seen.add(id);
      unique.push(c);
    }
    if (!unique.length) {
      emptyEl?.classList.remove("hidden");
      emptyEl.textContent = t("chat.emptyHistory");
      return;
    }
    emptyEl?.classList.add("hidden");
    unique.forEach((c) => {
      const li = document.createElement("li");
      li.className = "conv-history-row";

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "conv-history-item" + (c.id === chatState.conversationId ? " active" : "");
      btn.innerHTML = `
        <div class="conv-history-item-title">${escapeHtml(c.title || c.id)}</div>
        <div class="conv-history-item-meta">${formatConvTime(c.updated_at)} · ${c.message_count || 0} ${t("common.messages")}</div>
      `;
      btn.addEventListener("click", () => openConversation(c.id));

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "conv-history-delete";
      delBtn.title = t("chat.deleteConv");
      delBtn.setAttribute("aria-label", t("chat.deleteConvAria", { title: c.title || c.id }));
      delBtn.textContent = "×";
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        removeConversation(c.id, c.title || c.id);
      });

      li.appendChild(btn);
      li.appendChild(delBtn);
      listEl.appendChild(li);
    });
  } catch (err) {
    if (seq !== convHistoryRenderSeq) return;
    emptyEl?.classList.remove("hidden");
    emptyEl.textContent = networkErrorHint(err);
  }
}

async function removeConversation(conversationId, label) {
  const name = label || conversationId;
  if (!window.confirm(t("chat.deleteConfirm", { name }))) return;
  try {
    const result = await apiDeleteConversation(conversationId);
    const wasActive =
      result.was_active || chatState.conversationId === conversationId;
    await renderConversationHistory();
    if (wasActive) {
      const remaining = await fetchConversations();
      if (remaining.length) {
        applyConversation(await apiLoadConversation(remaining[0].id));
      } else {
        applyConversation(await apiCreateConversation());
      }
      if (chatViewMode === "chat") {
        renderChatLog();
        updateChatTitle();
      }
    }
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function showMain(status, { skipChatReload = false } = {}) {
  hideAllPanels();
  $("#main-panel").classList.remove("hidden");
  showChatView();
  lastMainStatus = status;
  const sources = (status.source_databases || []).join(", ") || t("common.none");
  const storageHtml = formatStorageSummary(status);
  $("#status-bar-text").innerHTML = t("main.statusBar", {
    alias: status.db_alias,
    sources,
    storage: storageHtml,
    ...formatLlmStatusParams(status),
  });
  if (chatState.dbAlias !== status.db_alias) {
    await initChatForProject(status.db_alias, status);
  } else if (!skipChatReload) {
    renderChatLog();
    updateChatTitle();
  }
  const skills = status.skills?.length ? status.skills : await fetchSkills();
  loadSkillsCache(skills);
  await fetchToolLabels();
  if (chatViewMode === "chat") renderChatLog();
  await renderConversationHistory();
}

async function renderProjectList(projects) {
  projectsCache = projects;
  const listEl = $("#project-list");
  const emptyEl = $("#project-list-empty");
  listEl.innerHTML = "";

  if (!projects.length) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  const sorted = [...projects].sort((a, b) => {
    if (Boolean(a.is_active) !== Boolean(b.is_active)) {
      return a.is_active ? -1 : 1;
    }
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });

  sorted.forEach((p) => {
    const card = document.createElement("div");
    card.className = "project-card" + (p.is_active ? " active" : "");
    const sources = (p.source_databases || []).join(", ") || t("common.none");
    const fileCount = p.source_file_count || (p.source_files || []).length || 0;
    const storageMeta =
      p.storage_mode === "local"
        ? t("project.storageLocal")
        : `${t("project.storageTarget")}：${escapeHtml(p.target_database || "—")}`;
    card.innerHTML = `
      <div class="project-card-head">
        <span class="project-name">${escapeHtml(p.db_alias)}</span>
        ${p.is_active ? `<span class="project-badge">${t("project.current")}</span>` : ""}
      </div>
      <div class="project-meta">${escapeHtml(p.host || "")}:${p.port || 3306}</div>
      <div class="project-meta">${t("project.sources")}：${escapeHtml(sources)} · ${t("project.sourceFiles")} ${fileCount}</div>
      <div class="project-meta">${storageMeta}</div>
      <div class="project-meta project-stats">${t("project.stats", { dataset: p.dataset_count || 0, frontend: p.frontend_count || 0, backend: p.backend_count || 0 })}</div>
      <div class="project-card-actions">
        <button type="button" class="btn primary small btn-enter">${t("project.enter")}</button>
        <button type="button" class="btn btn-text small btn-edit">${t("project.edit")}</button>
        <button type="button" class="btn btn-text small btn-delete">${t("project.delete")}</button>
      </div>
    `;

    card.querySelector(".btn-enter").addEventListener("click", (e) => {
      e.stopPropagation();
      enterProject(p.db_alias);
    });
    card.querySelector(".btn-edit").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openEditForm(p);
    });
    card.querySelector(".btn-delete").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      deleteProject(p.db_alias);
    });
    card.addEventListener("click", (e) => {
      if (e.target.closest(".project-card-actions")) return;
      enterProject(p.db_alias);
    });

    listEl.appendChild(card);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

async function showProjectPicker() {
  hideAllPanels();
  $("#project-panel").classList.remove("hidden");
  const projects = await fetchProjects();
  await renderProjectList(projects);
}

async function enterProject(dbAlias) {
  try {
    const res = await fetch("/api/projects/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ db_alias: dbAlias }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("project.switchFailed"));
    await showMain(data.status);
    appendMessage("system", t("project.entered", { alias: dbAlias }));
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

async function openEditForm(projectOrAlias) {
  const alias =
    typeof projectOrAlias === "string" ? projectOrAlias : projectOrAlias?.db_alias;
  if (!alias) return;

  const cached =
    typeof projectOrAlias === "object" && projectOrAlias?.user !== undefined
      ? projectOrAlias
      : projectsCache.find((p) => p.db_alias === alias);

  if (cached && cached.user !== undefined) {
    showSetupForm(cached);
    return;
  }

  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(alias)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.loadFailed"));
    showSetupForm(data.project);
  } catch (err) {
    alert(networkErrorHint(err));
  }
}

function showSetupForm(project = null) {
  hideAllPanels();
  $("#setup-panel").classList.remove("hidden");
  $("#setup-error").classList.add("hidden");
  editingDbAlias = project ? project.db_alias : null;
  editingProjectHasGemini = Boolean(project?.has_gemini_api_key);

  const form = $("#setup-form");
  if (project) {
    $("#setup-title").textContent = t("setup.editTitle", { alias: project.db_alias });
    $("#setup-hint").innerHTML = t("setup.hintEditHtml");
    $("#setup-btn").textContent = t("setup.saveChanges");
    form.db_alias.value = project.db_alias;
    form.db_alias.readOnly = true;
    form.host.value = project.host || "";
    form.port.value = project.port || 3306;
    form.user.value = project.user || "";
    form.password.value = "";
    form.password.placeholder = project.has_password ? t("setup.passwordEditEmpty") : t("setup.passwordEditRequired");
    form.target_database.value = project.target_database || "";
    form.target_user.value = project.target_user || "";
    form.target_password.value = "";
    form.target_password.placeholder = project.has_target_password ? t("setup.passwordEditEmpty") : "";
    initSourceDbList(project.source_databases || []);
    initSourceFileList(project.source_files || []);
    form.password.required = setupNeedsMysql(form) && !project.has_password;
    if (form.llm_provider) form.llm_provider.value = project.llm_provider || "deepseek";
    if (form.gemini_model) form.gemini_model.value = project.gemini_model || "gemini-2.0-flash";
    if (form.gemini_api_key) {
      form.gemini_api_key.value = "";
      form.gemini_api_key.placeholder = project.has_gemini_api_key
        ? t("setup.geminiApiKeyPlaceholder")
        : t("setup.geminiApiKeyPlaceholder");
    }
  } else {
    $("#setup-title").textContent = t("setup.newTitle");
    $("#setup-hint").innerHTML = t("setup.hintNewHtml");
    $("#setup-btn").textContent = t("setup.saveEnter");
    form.reset();
    form.db_alias.readOnly = false;
    form.host.value = "127.0.0.1";
    form.port.value = 3306;
    form.password.required = false;
    form.password.placeholder = t("setup.passwordPlaceholder");
    initSourceDbList();
    initSourceFileList();
    if (form.llm_provider) form.llm_provider.value = "deepseek";
    if (form.gemini_model) form.gemini_model.value = "gemini-2.0-flash";
  }

  syncLlmProviderPanels();

  $("#back-to-projects-btn").classList.toggle(
    "hidden",
    !(editingDbAlias || (document.querySelectorAll(".project-card").length > 0))
  );
}

function appendMessage(role, text) {
  const log = $("#chat-log");
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") {
    renderAssistantMessage(div, text, { streaming: false, collapseTools: true });
  } else if (role === "user") {
    const body = document.createElement("div");
    body.className = "msg-body markdown-body";
    setMarkdownContent(body, text);
    div.appendChild(body);
  } else {
    div.textContent = text;
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function init() {
  configureMarkdownRenderer();
  const status = await fetchStatus();
  if (status.ready) {
    showMain(status);
    return;
  }
  const projects = status.projects || (await fetchProjects());
  if (projects.length > 0) {
    await showProjectPicker();
  } else {
    showSetupForm(null);
    $("#back-to-projects-btn").classList.add("hidden");
  }
}

$("#llm-provider-select")?.addEventListener("change", syncLlmProviderPanels);

$("#setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("#setup-error");
  errEl.classList.add("hidden");
  const btn = $("#setup-btn");
  btn.disabled = true;
  const btnLabel = btn.textContent;
  btn.textContent = t("common.saving");

  const fd = new FormData(e.target);
  const source_databases = collectSourceDatabases();
  const target = (fd.get("target_database") || "").trim();
  const needsMysql = source_databases.length > 0 || Boolean(target);

  if (target && source_databases.includes(target)) {
    errEl.textContent = t("setup.targetSameAsSource");
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = btnLabel;
    return;
  }

  const password = (fd.get("password") || "").trim();
  if (needsMysql && !editingDbAlias && !password) {
    errEl.textContent = t("setup.passwordRequired");
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = btnLabel;
    return;
  }

  const provider = (fd.get("llm_provider") || "deepseek").trim();
  const deepseekKey = (fd.get("deepseek_api_key") || "").trim();
  const geminiKey = (fd.get("gemini_api_key") || "").trim();
  const status = await fetchStatus();
  if (provider === "gemini") {
    if (!geminiKey && !editingProjectHasGemini) {
      errEl.textContent = t("setup.geminiApiKeyRequired");
      errEl.classList.remove("hidden");
      btn.disabled = false;
      btn.textContent = btnLabel;
      return;
    }
  } else if (!status.has_deepseek && !deepseekKey) {
    errEl.textContent = t("setup.apiKeyRequired");
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = btnLabel;
    return;
  }

  const body = {
    db_alias: fd.get("db_alias"),
    host: fd.get("host"),
    port: Number(fd.get("port")),
    user: fd.get("user"),
    password: password,
    source_databases,
    target_database: target,
    target_user: (fd.get("target_user") || "").trim() || null,
    target_password: (fd.get("target_password") || "").trim() || null,
    deepseek_api_key: deepseekKey || null,
    deepseek_base_url: fd.get("deepseek_base_url") || "https://api.deepseek.com",
    deepseek_model: fd.get("deepseek_model") || "deepseek-chat",
    llm_provider: provider,
    gemini_api_key: geminiKey || null,
    gemini_model: (fd.get("gemini_model") || "gemini-2.0-flash").trim(),
    test_connection: fd.get("test_connection") === "on",
  };

  try {
    const res = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || t("common.saveFailed"));
    if (pendingSourceFiles.length) {
      btn.textContent = t("setup.uploadingSources");
      await uploadPendingSourceFiles(data.db_alias);
    }
    const status = await fetchStatus();
    await showMain(status);
    appendMessage("system", formatSetupSuccessMessage(data));
  } catch (err) {
    errEl.textContent = networkErrorHint(err);
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = btnLabel;
  }
});

$("#reconfigure-btn").addEventListener("click", async () => {
  await showProjectPicker();
});

$("#back-to-projects-btn").addEventListener("click", async () => {
  await showProjectPicker();
});

$("#new-project-btn").addEventListener("click", () => {
  showSetupForm(null);
});

$("#new-chat-btn").addEventListener("click", () => {
  startNewConversation({ announce: true });
});

$("#back-to-chat-btn").addEventListener("click", async () => {
  if (skillAuthorMode) {
    leaveSkillAuthorMode();
    void refreshSkillsCache().then(() => showSkillsView());
    return;
  }
  if (chatViewMode === "artifacts" && !(await confirmDiscardArtifactsChanges())) return;
  if (chatViewMode === "skills") {
    leaveSkillsView();
    return;
  }
  const fromPreview = chatViewMode === "system-preview";
  const errorBatch = fromPreview && pendingRuntimeErrors.length
    ? [...pendingRuntimeErrors]
    : [];
  if (errorBatch.length) {
    pendingRuntimeErrors = [];
    updateRuntimeErrorUi();
  }
  showChatView();
  if (errorBatch.length) {
    showRuntimeErrorPromptInChat(errorBatch);
  }
});

$("#skills-btn")?.addEventListener("click", () => {
  skillsReturnTarget = "chat";
  showSkillsView();
});

$("#skills-detail-tabs")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".skills-tab");
  if (!btn || btn.disabled) return;
  const tab = btn.dataset.tab;
  if (!tab || tab === skillsDetailTab) return;
  setSkillsDetailTab(tab);
});

$("#skills-file-editor")?.addEventListener("input", (e) => {
  if (!skillsFileState.path || skillsFileState.loading) return;
  skillsFileState.dirty = e.target.value !== skillsFileState.savedContent;
  updateSkillFileEditorUi();
});

$("#skills-skill-editor")?.addEventListener("input", (e) => {
  if (skillsMdState.loading) return;
  skillsMdState.dirty = e.target.value !== skillsMdState.savedContent;
  updateSkillsSkillMdUi();
});

$("#skills-skill-save-btn")?.addEventListener("click", () => {
  saveSkillMdContent();
});

$("#skills-origin-filter")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".skills-origin-tab");
  if (!btn?.dataset.origin) return;
  setSkillsOriginFilter(btn.dataset.origin);
});

$("#skills-create-chat-btn")?.addEventListener("click", () => {
  openSkillAuthorChat();
});

$("#skills-upload-input")?.addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  e.target.value = "";
  if (!file) return;
  await handleCustomSkillZipUpload(file);
});

$("#skill-author-upload-btn")?.addEventListener("click", () => {
  $("#skill-author-file-input")?.click();
});

$("#skill-author-file-input")?.addEventListener("change", async (e) => {
  const files = [...(e.target.files || [])];
  e.target.value = "";
  if (!files.length) return;
  try {
    await uploadSkillAuthorFiles(files);
  } catch (err) {
    alert(networkErrorHint(err));
  }
});

$("#skill-author-exit-btn")?.addEventListener("click", () => {
  leaveSkillAuthorMode();
  showSkillsView();
});

$("#skills-new-file-btn")?.addEventListener("click", () => {
  promptNewSkillFile("");
});

$("#skills-file-save-btn")?.addEventListener("click", () => {
  saveSkillFileContent();
});

$("#open-skills-from-projects")?.addEventListener("click", () => {
  skillsReturnTarget = "projects";
  openSkillsLibrary("projects");
});

$("#system-preview-btn")?.addEventListener("click", () => {
  openSystemPreviewPage();
});

$("#system-preview-open-tab-btn")?.addEventListener("click", () => {
  openSystemPreviewInNewTab();
});

$("#system-preview-restart-btn")?.addEventListener("click", () => {
  restartSystemPreviewBackend();
});

$("#system-preview-error-banner-ignore-btn")?.addEventListener("click", () => {
  if (!pendingRuntimeErrors.length) return;
  acknowledgeRuntimeErrors(pendingRuntimeErrors);
});

$("#system-preview-error-banner-btn")?.addEventListener("click", () => {
  $("#back-to-chat-btn")?.click();
});

$("#system-preview-project-select")?.addEventListener("change", async (e) => {
  const name = e.target.value;
  if (!name) return;
  lastErrorWatchProject = name;
  resetRuntimeErrorWatchForProject(name, { hard: true });
  startRuntimeErrorPoll(name, { resetWatch: true });
  const info = systemPreviewCache.frontends.find((f) => f.project_name === name);
  let apiBase = info?.api_base_url || "";
  if (info?.linked_backend) {
    const hint = $("#system-preview-backend-hint");
    if (hint) {
      hint.textContent = t("preview.startingBackend", { name: info.linked_backend });
      hint.classList.remove("hidden");
    }
    try {
      const rt = await ensureSystemPreviewBackend(name);
      apiBase = rt?.api_base_url || apiBase;
    } catch (err) {
      if (hint) hint.textContent = networkErrorHint(err);
    }
  }
  reloadSystemPreviewFrame(name, apiBase);
  renderSystemPreviewMeta(name);
  updateSystemPreviewLogButton(name);
  updateSystemPreviewRestartButton(name);
});

$("#system-preview-log-btn")?.addEventListener("click", () => {
  const panel = $("#system-preview-log-panel");
  if (panel?.classList.contains("hidden")) openBackendLogPanel();
  else closeBackendLogPanel();
});

$("#system-preview-log-close-btn")?.addEventListener("click", () => {
  closeBackendLogPanel();
});

$("#system-preview-log-refresh-btn")?.addEventListener("click", () => {
  refreshBackendLog();
});

$("#system-preview-log-autorefresh-btn")?.addEventListener("click", () => {
  setBackendLogAutoRefresh(!isBackendLogAutoRefreshOn());
});

$("#artifacts-btn").addEventListener("click", () => {
  openArtifactsPage();
});

$("#artifacts-new-file-btn")?.addEventListener("click", () => {
  promptNewArtifact("");
});

$("#artifacts-save-btn")?.addEventListener("click", () => {
  saveCurrentArtifact();
});

$("#artifacts-editor")?.addEventListener("input", () => {
  markArtifactsDirty();
});

$("#artifacts-fm-toggle")?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleArtifactsFmCollapsed();
});

$("#artifacts-fm-head")?.addEventListener("click", (e) => {
  if (e.target.closest("#artifacts-fm-toggle")) return;
  if (e.target.closest(".artifacts-fm-alias")) return;
  toggleArtifactsFmCollapsed();
});

$$(".artifacts-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    setArtifactsEditorTab(btn.dataset.tab || "preview");
  });
});

async function sendChatMessage(message, { showUserMessage = true } = {}) {
  const text = (message || "").trim();
  if (!text || chatBusy) return;

  if (pendingRuntimeErrors.length) {
    acknowledgeRuntimeErrors(pendingRuntimeErrors);
  }

  const skills = getActiveSkillsForChat();
  if (!skills.length) {
    appendMessage(
      "system",
      t("chat.noSkills")
    );
    return;
  }

  const historyForApi = chatState.history.map((m) => ({
    role: m.role,
    content: m.content,
  }));

  if (showUserMessage) {
    appendMessage("user", text);
  }
  chatState.history.push({ role: "user", content: text });
  chatState.history = trimLocalHistory(chatState.history);
  updateChatTitle();

  const assistantEl = appendAssistantShell();
  let assistantRaw = "";
  let aborted = false;
  chatAbortController = new AbortController();
  setChatBusy(true);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: chatAbortController.signal,
      body: JSON.stringify({
        skills: skills,
        message: text,
        history: historyForApi,
        conversation_id: chatState.conversationId,
        mode: skillAuthorMode ? "skill_author" : "normal",
        skill_author_session: skillAuthorMode ? skillAuthorSessionId : null,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(formatApiError(err.detail) || t("chat.requestFailed"));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") continue;
        let obj;
        try {
          obj = JSON.parse(payload);
        } catch {
          continue;
        }
        if (obj.error != null && obj.error !== "") {
          throw new Error(formatApiError(obj.error) || t("chat.chatError"));
        }
        if (obj.conversation_id) {
          chatState.conversationId = obj.conversation_id;
          if (obj.title) {
            updateChatTitle(obj.title);
            void renderConversationHistory();
          }
          continue;
        }
        if (obj.text) {
          assistantRaw += obj.text;
          renderAssistantMessage(assistantEl, assistantRaw, {
            streaming: true,
            collapseTools: false,
          });
        }
      }
      $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
    }
    renderAssistantMessage(assistantEl, assistantRaw, {
      streaming: false,
      collapseTools: true,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      aborted = true;
      if (!assistantRaw.trim()) {
        assistantRaw = t("chat.stoppedTag");
      } else {
        assistantRaw += `\n\n${t("chat.stoppedTag")}`;
      }
    } else {
      assistantRaw += `\n${t("chat.errorTag")} ${networkErrorHint(err)}`;
    }
    renderAssistantMessage(assistantEl, assistantRaw, {
      streaming: false,
      collapseTools: true,
    });
  } finally {
    chatAbortController = null;
    const reply = assistantRaw.trim();
    if (reply) {
      chatState.history.push({ role: "assistant", content: reply });
      chatState.history = trimLocalHistory(chatState.history);
      updateChatTitle();
      void renderConversationHistory();
    } else if (aborted) {
      appendMessage("system", t("chat.stoppedAgent"));
    }
    setChatBusy(false);
    if (skillAuthorMode) void refreshSkillsCache();
    $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
  }
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (chatBusy) return;
  const input = $("#chat-message");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  await sendChatMessage(message, { showUserMessage: true });
});

$("#chat-stop-btn")?.addEventListener("click", () => {
  stopChatGeneration();
});

$("#chat-message")?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.isComposing) return;
  if (e.shiftKey) return;
  e.preventDefault();
  if (chatBusy) return;
  $("#chat-form")?.requestSubmit();
});

window.addEventListener("message", (ev) => {
  if (ev?.data?.type !== "studio-preview-http-error") return;
  handlePreviewHttpErrorMessage(ev.data);
});

async function refreshUiLanguage() {
  window.StudioI18n?.applyI18n?.();
  setChatBusy(chatBusy);
  updateChatTitle();
  updateRuntimeErrorUi();

  if (!$("#project-panel")?.classList.contains("hidden")) {
    await renderProjectList(projectsCache);
  }

  if (!$("#setup-panel")?.classList.contains("hidden")) {
    const cached = editingDbAlias
      ? projectsCache.find((p) => p.db_alias === editingDbAlias)
      : null;
    showSetupForm(cached || (editingDbAlias ? { db_alias: editingDbAlias } : null));
  }

  if (lastMainStatus && !$("#main-panel")?.classList.contains("hidden")) {
    const status = lastMainStatus;
    const sources = (status.source_databases || []).join(", ") || t("common.none");
    const storageHtml = formatStorageSummary(status);
    $("#status-bar-text").innerHTML = t("main.statusBar", {
      alias: status.db_alias,
      sources,
      storage: storageHtml,
      ...formatLlmStatusParams(status),
    });
    await renderConversationHistory();
  }

  if (chatViewMode === "skills") {
    if ($("#skills-detail-title") && !skillsBrowserActiveId) {
      $("#skills-detail-title").textContent = t("skills.select");
    }
    renderSkillsBrowserList(getFilteredSkillsCache());
    if (!skillsBrowserActiveId) clearSkillDetailPanel();
  } else if (chatViewMode === "artifacts") {
    $("#chat-conv-title").textContent = t("artifacts.title");
    updateArtifactsEditorUi();
    void renderArtifactsTreePanel();
  } else if (chatViewMode === "system-preview") {
    $("#chat-conv-title").textContent = t("preview.title");
    const project = $("#system-preview-project-select")?.value;
    if (project) renderSystemPreviewMeta(project);
  } else if (skillAuthorMode) {
    $("#chat-conv-title").textContent = t("skillAuthor.title");
  }

  renderSourceFileList();
  if ($("#source-db-list")?.children.length) {
    const names = collectSourceDatabases();
    initSourceDbList(names);
  }
}

window.addEventListener("studio:langchange", () => {
  void refreshUiLanguage();
});

init();
