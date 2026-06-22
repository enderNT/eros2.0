const listEl = document.querySelector("#flow-list");
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
const stageListEl = document.querySelector("#stage-list");

let allFlows = [];
let selectedFlowId = null;
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

function flowTitle(flow) {
  const msg = flow.message_id ? `msg ${flow.message_id}` : flow.flow_id;
  const conv = flow.conversation_id ? `conv ${flow.conversation_id}` : "sin conversacion";
  return `${msg} · ${conv}`;
}

function previewFor(flow) {
  return (flow.preview_text || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180) || "Sin texto registrado";
}

function escapeText(value) {
  return String(value ?? "");
}

function selectFlowInList(flowId) {
  for (const button of listEl.querySelectorAll(".flow-item")) {
    button.classList.toggle("active", button.dataset.flowId === String(flowId));
  }
}

async function selectFlow(flowId) {
  selectedFlowId = flowId;
  selectFlowInList(flowId);

  if (!flowId) {
    detailEl.hidden = true;
    emptyDetailEl.hidden = false;
    return;
  }

  setState("Cargando", "blue");
  try {
    const params = new URLSearchParams({ flow_id: flowId });
    const res = await fetch(`/api/llm-flow?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderFlowDetail(data.flow);
    setState("Listo", "green");
  } catch (error) {
    emptyDetailEl.hidden = false;
    detailEl.hidden = true;
    emptyDetailEl.querySelector("p").textContent = error.message;
    setState("Error", "error");
  }
}

function renderList() {
  listEl.innerHTML = "";
  countEl.textContent = String(allFlows.length);
  latestEl.textContent = allFlows[0] ? compactDate(allFlows[0].last_created_at) : "Sin datos";

  if (!allFlows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = "No hay flujos registrados para este filtro.";
    listEl.append(empty);
    selectFlow(null);
    return;
  }

  for (const flow of allFlows) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "flow-item";
    item.dataset.flowId = flow.flow_id;
    item.innerHTML = `
      <span class="meta">${compactDate(flow.last_created_at)} · ${flow.call_count} eventos · ${flow.has_error ? "error" : "ok"}</span>
      <span class="flow-item-title"></span>
      <span class="flow-item-preview"></span>
    `;
    item.querySelector(".flow-item-title").textContent = flowTitle(flow);
    item.querySelector(".flow-item-preview").textContent = previewFor(flow);
    item.addEventListener("click", () => selectFlow(flow.flow_id));
    listEl.append(item);
  }

  const stillExists = allFlows.some((flow) => String(flow.flow_id) === String(selectedFlowId));
  selectFlow(stillExists ? selectedFlowId : allFlows[0].flow_id);
}

function renderFlowDetail(flow) {
  emptyDetailEl.hidden = true;
  detailEl.hidden = false;
  detailMetaEl.textContent = `${formatDate(flow.first_created_at)} · ${flow.call_count} eventos`;
  detailTitleEl.textContent = flowTitle(flow);
  detailStatusEl.textContent = flow.status || "ok";
  detailStatusEl.className = `badge ${flow.status === "error" ? "error" : "ok"}`;
  stageListEl.innerHTML = "";

  flow.stages.forEach((stage, index) => {
    const stageEl = document.createElement("section");
    stageEl.className = "stage";
    stageEl.dataset.open = "true";
    stageEl.innerHTML = `
      <button class="stage-toggle" type="button">
        <span class="stage-symbol">-</span>
        <span class="stage-title">
          <span class="step-label">Paso ${index + 1}</span>
          <strong></strong>
        </span>
        <span class="badge blue">${stage.calls.length} eventos</span>
      </button>
      <div class="stage-body"></div>
    `;
    stageEl.querySelector(".stage-title strong").textContent = stage.label;
    stageEl.querySelector(".stage-toggle").addEventListener("click", () => toggleStage(stageEl));
    const body = stageEl.querySelector(".stage-body");
    stage.calls.forEach((call, callIndex) => body.append(renderCall(call, callIndex)));
    stageListEl.append(stageEl);
  });
}

function renderCall(call, callIndex) {
  const card = document.createElement("article");
  card.className = "call-card";
  const key = `call-${call.id}`;
  card.innerHTML = `
    <div class="call-head">
      <div class="call-title">
        <span class="meta">Evento ${callIndex + 1} · ${compactDate(call.created_at)}</span>
        <strong></strong>
      </div>
      <span class="badge ${call.status === "error" ? "error" : "ok"}">${call.status || "ok"}</span>
    </div>
    <div class="tabs" role="tablist">
      <button class="tab-button active" type="button" data-tab="${key}-input">Input</button>
      <button class="tab-button" type="button" data-tab="${key}-output">Output</button>
    </div>
    <div class="tab-panel" data-panel="${key}-input"><pre></pre></div>
    <div class="tab-panel" data-panel="${key}-output" hidden><pre></pre></div>
  `;
  card.querySelector(".call-title strong").textContent = call.model
    ? `${call.operation} · ${call.model}`
    : call.operation;
  card.querySelector(`[data-panel="${key}-input"] pre`).textContent = escapeText(call.request_text);
  card.querySelector(`[data-panel="${key}-output"] pre`).textContent = escapeText(call.response_text);
  card.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => activateTab(card, button.dataset.tab));
  });
  return card;
}

function activateTab(card, tabId) {
  card.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  card.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== tabId;
  });
}

function toggleStage(stageEl) {
  const isOpen = stageEl.dataset.open === "true";
  stageEl.dataset.open = String(!isOpen);
  stageEl.querySelector(".stage-symbol").textContent = isOpen ? "+" : "-";
  stageEl.querySelector(".stage-body").hidden = isOpen;
}

async function loadFlows() {
  setState("Cargando", "blue");
  refreshButton.disabled = true;
  try {
    const params = new URLSearchParams({
      limit: limitSelect.value,
      q: searchInput.value.trim(),
    });
    const res = await fetch(`/api/llm-flows?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allFlows = Array.isArray(data.flows) ? data.flows : [];
    dbStateEl.textContent = data.enabled ? "Postgres activo" : "Logger inactivo";
    dbStateEl.className = `badge ${data.enabled ? "blue" : "disabled"}`;
    setState(data.enabled ? "Listo" : "Inactivo", data.enabled ? "green" : "disabled");
    renderList();
  } catch (error) {
    allFlows = [];
    listEl.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = error.message;
    listEl.append(empty);
    countEl.textContent = "0";
    latestEl.textContent = "Sin datos";
    setState("Error", "error");
    selectFlow(null);
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", loadFlows);
limitSelect.addEventListener("change", loadFlows);
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadFlows, 220);
});

loadFlows();
