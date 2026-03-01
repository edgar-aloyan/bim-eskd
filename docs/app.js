/* bim-eskd drawing viewer — PDF-like continuous scroll */

const BASE = (() => {
  const path = location.pathname;
  if (path.includes("/bim-eskd/")) {
    return path.substring(0, path.indexOf("/bim-eskd/") + "/bim-eskd/".length);
  }
  return path.endsWith("/") ? path : path.substring(0, path.lastIndexOf("/") + 1);
})();

let state = {
  projects: [],
  currentProject: null,
  zoom: 1,
  pages: [],       // DOM elements for each page
  activePageIdx: 0, // currently visible page index
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
    const res = await fetch(BASE + "projects/index.json");
    if (!res.ok) throw new Error("No index");
    const index = await res.json();
    state.projects = index.projects || [];
  } catch {
    state.projects = [];
    for (const pid of ["001_server_container"]) {
      try {
        const res = await fetch(BASE + `projects/${pid}/manifest.json`);
        if (res.ok) state.projects.push(await res.json());
      } catch { /* skip */ }
    }
  }

  renderSidebar();
  if (state.projects.length > 0) {
    selectProject(state.projects[0].project);
  }
}

// ── Sidebar (document outline) ──

function renderSidebar() {
  const sidebar = document.getElementById("sidebar-content");
  if (state.projects.length === 0) {
    sidebar.innerHTML = '<div class="sidebar-heading">No projects</div>';
    return;
  }

  let html = '<div class="sidebar-heading">Document outline</div>';

  for (const proj of state.projects) {
    const isActive = state.currentProject === proj.project;
    html += `<div class="project-item ${isActive ? "active" : ""}"
                  data-project="${proj.project}">
               ${proj.title || proj.project}
             </div>`;

    if (isActive && proj.sheets) {
      proj.sheets.forEach((sheet, i) => {
        const cls = state.activePageIdx === i ? "active" : "";
        html += `<div class="sheet-item ${cls}" data-page="${i}">
                   ${sheet.title || sheet.file}
                   <span class="sheet-page-num">${i + 1}</span>
                 </div>`;
      });
    }
  }

  sidebar.innerHTML = html;

  // Clicks
  sidebar.querySelectorAll(".project-item").forEach((el) => {
    el.addEventListener("click", () => selectProject(el.dataset.project));
  });
  sidebar.querySelectorAll(".sheet-item").forEach((el) => {
    el.addEventListener("click", () => scrollToPage(parseInt(el.dataset.page)));
  });
}

async function selectProject(projectId) {
  state.currentProject = projectId;
  state.activePageIdx = 0;

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
    await loadAllSheets(proj);
  } else {
    showEmpty("No sheets");
  }
}

// ── Load all sheets as continuous pages ──

async function loadAllSheets(proj) {
  const scroll = document.getElementById("viewer-scroll");
  scroll.innerHTML = '<div class="loading">Loading sheets...</div>';
  state.pages = [];

  const fragments = [];

  for (let i = 0; i < proj.sheets.length; i++) {
    const sheet = proj.sheets[i];
    const url = BASE + `projects/${proj.project}/sheets/${sheet.file}`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const svgText = await res.text();

      const page = document.createElement("div");
      page.className = "page";
      page.dataset.pageIdx = i;
      page.innerHTML = svgText;
      fragments.push(page);
    } catch (e) {
      const page = document.createElement("div");
      page.className = "page";
      page.dataset.pageIdx = i;
      page.innerHTML = `<div class="empty-state">Sheet ${i + 1}: ${e.message}</div>`;
      fragments.push(page);
    }
  }

  scroll.innerHTML = "";
  for (const page of fragments) {
    scroll.appendChild(page);
    state.pages.push(page);
  }

  applyZoom();
  updatePageIndicator();
}

function showEmpty(msg) {
  const scroll = document.getElementById("viewer-scroll");
  scroll.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
}

// ── Scroll tracking — highlight active page in sidebar ──

function setupScrollTracking() {
  const viewer = document.querySelector(".viewer");
  viewer.addEventListener("scroll", onScroll);
}

function onScroll() {
  const viewer = document.querySelector(".viewer");
  const viewerTop = viewer.scrollTop + viewer.clientHeight * 0.3;

  let active = 0;
  for (let i = 0; i < state.pages.length; i++) {
    const page = state.pages[i];
    if (page.offsetTop <= viewerTop) {
      active = i;
    }
  }

  if (active !== state.activePageIdx) {
    state.activePageIdx = active;
    updateSidebarActive();
    updatePageIndicator();
  }
}

function updateSidebarActive() {
  document.querySelectorAll(".sheet-item").forEach((el) => {
    const idx = parseInt(el.dataset.page);
    el.classList.toggle("active", idx === state.activePageIdx);
  });
}

function updatePageIndicator() {
  const el = document.getElementById("page-indicator");
  if (el && state.pages.length > 0) {
    el.textContent = `${state.activePageIdx + 1} / ${state.pages.length}`;
  }
}

function scrollToPage(idx) {
  if (idx < 0 || idx >= state.pages.length) return;
  const page = state.pages[idx];
  const viewer = document.querySelector(".viewer");
  viewer.scrollTo({ top: page.offsetTop - 20, behavior: "smooth" });
}

// ── Zoom ──

function applyZoom() {
  const scroll = document.getElementById("viewer-scroll");
  scroll.style.transform = `scale(${state.zoom})`;
  // Adjust width so horizontal scroll works correctly
  scroll.style.width = state.zoom !== 1 ? `${100 / state.zoom}%` : "";
  document.getElementById("zoom-level").textContent =
    Math.round(state.zoom * 100) + "%";
}

function zoomIn() {
  state.zoom = Math.min(5, state.zoom * 1.2);
  applyZoom();
}

function zoomOut() {
  state.zoom = Math.max(0.2, state.zoom / 1.2);
  applyZoom();
}

function zoomFit() {
  // Fit page width to viewer width
  const viewer = document.querySelector(".viewer");
  const page = state.pages[0];
  if (!page) return;
  const svg = page.querySelector("svg");
  if (!svg) return;

  const svgW = svg.viewBox.baseVal.width || svg.clientWidth || 420;
  const viewerW = viewer.clientWidth - 40; // padding
  state.zoom = Math.min(2, viewerW / svgW);
  applyZoom();
}

function setupControls() {
  const viewer = document.querySelector(".viewer");

  // Ctrl+wheel = zoom, plain wheel = scroll (natural PDF behavior)
  viewer.addEventListener("wheel", (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
      state.zoom = Math.max(0.2, Math.min(5, state.zoom * factor));
      applyZoom();
    }
    // Otherwise: default scroll behavior
  }, { passive: false });

  // Keyboard
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "=" || e.key === "+")) {
      e.preventDefault(); zoomIn();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "-") {
      e.preventDefault(); zoomOut();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault(); zoomFit();
    } else if (e.key === "PageDown") {
      scrollToPage(state.activePageIdx + 1);
    } else if (e.key === "PageUp") {
      scrollToPage(state.activePageIdx - 1);
    }
  });

  // Buttons
  document.getElementById("btn-zoom-in").addEventListener("click", zoomIn);
  document.getElementById("btn-zoom-out").addEventListener("click", zoomOut);
  document.getElementById("btn-zoom-fit").addEventListener("click", zoomFit);
  document.getElementById("btn-print").addEventListener("click", () => window.print());
  document.getElementById("btn-theme").addEventListener("click", toggleTheme);

  // Scroll tracking
  setupScrollTracking();
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
