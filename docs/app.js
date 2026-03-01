/* bim-eskd drawing viewer */

const BASE = (() => {
  const path = location.pathname;
  // Support both root and subdirectory deployments
  if (path.includes("/bim-eskd/")) {
    return path.substring(0, path.indexOf("/bim-eskd/") + "/bim-eskd/".length);
  }
  return path.endsWith("/") ? path : path.substring(0, path.lastIndexOf("/") + 1);
})();

let state = {
  projects: [],
  currentProject: null,
  currentSheet: null,
  zoom: 1,
  panX: 0,
  panY: 0,
  isPanning: false,
  startX: 0,
  startY: 0,
};

// ── Init ──

async function init() {
  setupTheme();
  setupControls();
  await loadProjects();
}

async function loadProjects() {
  const sidebar = document.getElementById("sidebar-content");
  sidebar.innerHTML = '<div class="loading">Loading...</div>';

  try {
    // Load project index
    const res = await fetch(BASE + "projects/index.json");
    if (!res.ok) throw new Error("No projects/index.json");
    const index = await res.json();
    state.projects = index.projects || [];
  } catch {
    // Fallback: try to detect projects from known manifest paths
    state.projects = [];
    const knownProjects = ["001_server_container"];
    for (const pid of knownProjects) {
      try {
        const res = await fetch(BASE + `projects/${pid}/manifest.json`);
        if (res.ok) {
          const manifest = await res.json();
          state.projects.push(manifest);
        }
      } catch { /* skip */ }
    }
  }

  renderSidebar();

  if (state.projects.length > 0) {
    selectProject(state.projects[0].project);
  }
}

// ── Sidebar ──

function renderSidebar() {
  const sidebar = document.getElementById("sidebar-content");
  if (state.projects.length === 0) {
    sidebar.innerHTML = '<div class="sidebar-heading">No projects found</div>';
    return;
  }

  let html = '<div class="sidebar-heading">Projects</div>';

  for (const proj of state.projects) {
    const isActive = state.currentProject === proj.project;
    html += `<div class="project-item ${isActive ? "active" : ""}"
                  data-project="${proj.project}">
               ${proj.title || proj.project}
             </div>`;

    if (isActive && proj.sheets) {
      for (const sheet of proj.sheets) {
        const sheetActive = state.currentSheet === sheet.file;
        html += `<div class="sheet-item ${sheetActive ? "active" : ""}"
                      data-project="${proj.project}"
                      data-sheet="${sheet.file}">
                   ${sheet.title || sheet.file}
                   <span class="sheet-format">${sheet.format || ""}</span>
                 </div>`;
      }
    }
  }

  sidebar.innerHTML = html;

  // Bind clicks
  sidebar.querySelectorAll(".project-item").forEach((el) => {
    el.addEventListener("click", () => selectProject(el.dataset.project));
  });
  sidebar.querySelectorAll(".sheet-item").forEach((el) => {
    el.addEventListener("click", () =>
      loadSheet(el.dataset.project, el.dataset.sheet)
    );
  });
}

async function selectProject(projectId) {
  state.currentProject = projectId;
  state.currentSheet = null;

  // Find or load manifest
  let proj = state.projects.find((p) => p.project === projectId);
  if (!proj || !proj.sheets) {
    try {
      const res = await fetch(BASE + `projects/${projectId}/manifest.json`);
      if (res.ok) {
        proj = await res.json();
        const idx = state.projects.findIndex((p) => p.project === projectId);
        if (idx >= 0) state.projects[idx] = proj;
        else state.projects.push(proj);
      }
    } catch { /* skip */ }
  }

  renderSidebar();

  if (proj && proj.sheets && proj.sheets.length > 0) {
    loadSheet(projectId, proj.sheets[0].file);
  } else {
    showEmpty("No sheets in this project");
  }
}

// ── Sheet viewer ──

async function loadSheet(projectId, sheetFile) {
  state.currentSheet = sheetFile;
  state.currentProject = projectId;
  renderSidebar();

  const viewer = document.getElementById("viewer-content");
  viewer.innerHTML = '<div class="loading">Loading sheet...</div>';

  try {
    const url = BASE + `projects/${projectId}/sheets/${sheetFile}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const svgText = await res.text();
    viewer.innerHTML = svgText;

    // Reset zoom/pan
    resetView();
  } catch (e) {
    viewer.innerHTML = `<div class="empty-state">
      <p>Could not load sheet: ${e.message}</p>
    </div>`;
  }
}

function showEmpty(msg) {
  const viewer = document.getElementById("viewer-content");
  viewer.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
}

// ── Zoom & Pan ──

function resetView() {
  const viewer = document.querySelector(".viewer");
  const content = document.getElementById("viewer-content");
  const svg = content.querySelector("svg");
  if (!svg) return;

  // Fit SVG to viewer
  const vw = viewer.clientWidth;
  const vh = viewer.clientHeight;
  const sw = svg.viewBox.baseVal.width || svg.clientWidth;
  const sh = svg.viewBox.baseVal.height || svg.clientHeight;

  if (sw <= 0 || sh <= 0) {
    state.zoom = 1;
  } else {
    state.zoom = Math.min(vw / (sw + 40), vh / (sh + 40));
  }

  state.panX = (vw - sw * state.zoom) / 2;
  state.panY = (vh - sh * state.zoom) / 2;
  applyTransform();
}

function applyTransform() {
  const content = document.getElementById("viewer-content");
  content.style.transform =
    `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
  document.getElementById("zoom-level").textContent =
    Math.round(state.zoom * 100) + "%";
}

function zoomIn() {
  zoomTo(state.zoom * 1.25);
}

function zoomOut() {
  zoomTo(state.zoom / 1.25);
}

function zoomTo(newZoom) {
  const viewer = document.querySelector(".viewer");
  const cx = viewer.clientWidth / 2;
  const cy = viewer.clientHeight / 2;

  const oldZoom = state.zoom;
  state.zoom = Math.max(0.1, Math.min(10, newZoom));

  // Zoom toward center
  state.panX = cx - (cx - state.panX) * (state.zoom / oldZoom);
  state.panY = cy - (cy - state.panY) * (state.zoom / oldZoom);
  applyTransform();
}

function zoomFit() {
  resetView();
}

function setupControls() {
  const viewer = document.querySelector(".viewer");

  // Wheel zoom
  viewer.addEventListener("wheel", (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const rect = viewer.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const oldZoom = state.zoom;
    state.zoom = Math.max(0.1, Math.min(10, state.zoom * factor));

    state.panX = mx - (mx - state.panX) * (state.zoom / oldZoom);
    state.panY = my - (my - state.panY) * (state.zoom / oldZoom);
    applyTransform();
  }, { passive: false });

  // Pan with mouse drag
  viewer.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    state.isPanning = true;
    state.startX = e.clientX - state.panX;
    state.startY = e.clientY - state.panY;
  });

  window.addEventListener("mousemove", (e) => {
    if (!state.isPanning) return;
    state.panX = e.clientX - state.startX;
    state.panY = e.clientY - state.startY;
    applyTransform();
  });

  window.addEventListener("mouseup", () => {
    state.isPanning = false;
  });

  // Keyboard shortcuts
  window.addEventListener("keydown", (e) => {
    if (e.key === "+" || e.key === "=") zoomIn();
    else if (e.key === "-") zoomOut();
    else if (e.key === "0") zoomFit();
  });

  // Buttons
  document.getElementById("btn-zoom-in").addEventListener("click", zoomIn);
  document.getElementById("btn-zoom-out").addEventListener("click", zoomOut);
  document.getElementById("btn-zoom-fit").addEventListener("click", zoomFit);
  document.getElementById("btn-print").addEventListener("click", () => window.print());
  document.getElementById("btn-theme").addEventListener("click", toggleTheme);

  // Prev/next sheet navigation
  document.getElementById("btn-prev").addEventListener("click", navigatePrev);
  document.getElementById("btn-next").addEventListener("click", navigateNext);
}

// ── Navigation ──

function navigatePrev() {
  const proj = state.projects.find((p) => p.project === state.currentProject);
  if (!proj || !proj.sheets) return;
  const idx = proj.sheets.findIndex((s) => s.file === state.currentSheet);
  if (idx > 0) loadSheet(proj.project, proj.sheets[idx - 1].file);
}

function navigateNext() {
  const proj = state.projects.find((p) => p.project === state.currentProject);
  if (!proj || !proj.sheets) return;
  const idx = proj.sheets.findIndex((s) => s.file === state.currentSheet);
  if (idx < proj.sheets.length - 1) loadSheet(proj.project, proj.sheets[idx + 1].file);
}

// ── Theme ──

function setupTheme() {
  const saved = localStorage.getItem("bim-eskd-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("bim-eskd-theme", next);
}

// ── Start ──

document.addEventListener("DOMContentLoaded", init);
