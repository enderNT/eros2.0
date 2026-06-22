const listEl = document.querySelector("#log-list");
const refreshButton = document.querySelector("#refresh");
const searchInput = document.querySelector("#search");
const limitSelect = document.querySelector("#limit");
const countEl = document.querySelector("#count");
const latestEl = document.querySelector("#latest");
const stateEl = document.querySelector("#state");
const dbStateEl = document.querySelector("#db-state");
const detailEl = document.querySelector("#detail");
const emptyDetailEl = document.querySelector("#empty-detail");
const detailMetaEl = document.querySelector("#detail-meta");
const detailTitleEl = document.querySelector("#detail-title");
const detailStatusEl = document.querySelector("#detail-status");
const requestTextEl = document.querySelector("#request-text");
const responseTextEl = document.querySelector("#response-text");

let allLogs = [];
let selectedId = null;
let searchTimer = null;

function setState(text, kind = "green") {
  stateEl.textContent = text;
  stateEl.className = `badge ${kind}`;
}

function formatDate(value) {
  if (!value) return "Sin datos";
  return new Intl.DateTimeFormat("es-MX", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function compactDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("es-MX", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function titleFor(log) {
  const conv = log.conversation_id ? `conv ${log.conversation_id}` : "sin conversacion";
  return `${log.operation} · ${log.model || "modelo sin nombre"} · ${conv}`;
}

function previewFor(log) {
  const text = log.request_text || log.response_text || "";
  return text.replace(/\s+/g, " ").trim().slice(0, 180) || "Sin texto registrado";
}

function selectLog(id) {
  selectedId = id;
  const log = allLogs.find((item) => String(item.id) === String(id));
  for (const button of listEl.querySelectorAll(".log-item")) {
    button.classList.toggle("active", button.dataset.id === String(id));
  }

  if (!log) {
    detailEl.hidden = true;
    emptyDetailEl.hidden = false;
    return;
  }

  emptyDetailEl.hidden = true;
  detailEl.hidden = false;
  detailMetaEl.textContent = `${formatDate(log.created_at)} · ${log.provider}`;
  detailTitleEl.textContent = titleFor(log);
  detailStatusEl.textContent = log.status || "ok";
  detailStatusEl.className = `badge ${log.status === "error" ? "error" : "ok"}`;
  requestTextEl.textContent = log.request_text || "";
  responseTextEl.textContent = log.response_text || "";
}

function renderList() {
  listEl.innerHTML = "";
  countEl.textContent = String(allLogs.length);
  latestEl.textContent = allLogs[0] ? compactDate(allLogs[0].created_at) : "Sin datos";

  if (!allLogs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = "No hay llamadas registradas para este filtro.";
    listEl.append(empty);
    selectLog(null);
    return;
  }

  for (const log of allLogs) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "log-item";
    item.dataset.id = log.id;
    item.innerHTML = `
      <span class="meta">${compactDate(log.created_at)} · ${log.status || "ok"}</span>
      <span class="log-item-title"></span>
      <span class="log-item-preview"></span>
    `;
    item.querySelector(".log-item-title").textContent = titleFor(log);
    item.querySelector(".log-item-preview").textContent = previewFor(log);
    item.addEventListener("click", () => selectLog(log.id));
    listEl.append(item);
  }

  const stillExists = allLogs.some((log) => String(log.id) === String(selectedId));
  selectLog(stillExists ? selectedId : allLogs[0].id);
}

async function loadLogs() {
  setState("Cargando", "blue");
  refreshButton.disabled = true;
  try {
    const params = new URLSearchParams({
      limit: limitSelect.value,
      q: searchInput.value.trim(),
    });
    const res = await fetch(`/api/llm-logs?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allLogs = Array.isArray(data.logs) ? data.logs : [];
    dbStateEl.textContent = data.enabled ? "Postgres activo" : "Logger inactivo";
    dbStateEl.className = `badge ${data.enabled ? "blue" : "disabled"}`;
    setState(data.enabled ? "Listo" : "Inactivo", data.enabled ? "green" : "disabled");
    renderList();
  } catch (error) {
    allLogs = [];
    listEl.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = error.message;
    listEl.append(empty);
    countEl.textContent = "0";
    latestEl.textContent = "Sin datos";
    setState("Error", "error");
    selectLog(null);
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadLogs);
limitSelect.addEventListener("change", loadLogs);
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadLogs, 220);
});

loadLogs();
