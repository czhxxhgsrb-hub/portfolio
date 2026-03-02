const $ = (id) => document.getElementById(id);

const statusEl = $("status");
const infoEl = $("info");
const tbody = $("tbody");

const searchEl = $("search");
const posEl = $("pos");
const sortEl = $("sort");

const loadBtn = $("load");
const loadTeamBtn = $("loadTeam");

const teamEl = $("team");

let players = [];
let filtered = [];

function setStatus(msg) {
    statusEl.textContent = msg;
}

function fmt(n, d = 2) {
    const x = Number(n);
    return Number.isFinite(x) ? x.toFixed(d) : "";
}

function renderTable(rows) {
    tbody.innerHTML = rows.map(p => `
    <tr>
      <td>${escapeHtml(p.name)}</td>
      <td>${escapeHtml(p.position)}</td>
      <td>${escapeHtml(p.team)}</td>
      <td class="num">${fmt(p.price, 1)}</td>
      <td class="num">${fmt(p.predicted_points_next_3, 2)}</td>
      <td class="num">${fmt(p.value_score, 2)}</td>
    </tr>
  `).join("");
}

function escapeHtml(s) {
    return String(s ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function applyFilters() {
    const q = searchEl.value.trim().toLowerCase();
    const pos = posEl.value;

    filtered = players.filter(p => {
        const okName = !q || String(p.name).toLowerCase().includes(q);
        const okPos = !pos || p.position === pos;
        return okName && okPos;
    });

    const sort = sortEl.value;
    const by = (key, dir) => (a, b) => (dir * (Number(a[key]) - Number(b[key])));

    if (sort === "pred_desc") filtered.sort(by("predicted_points_next_3", -1));
    if (sort === "value_desc") filtered.sort(by("value_score", -1));
    if (sort === "price_asc") filtered.sort(by("price", +1));
    if (sort === "name_asc") filtered.sort((a, b) => String(a.name).localeCompare(String(b.name)));

    renderTable(filtered);

    infoEl.textContent =
        `Loaded: ${players.length} players\n` +
        `Showing: ${filtered.length}\n` +
        `Tip: Use search + position filter + sort.`;
}

async function loadProjections() {
    setStatus("Loading projections…");
    try {
        const res = await fetch("./projections.json", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        players = await res.json();
        setStatus("Projections loaded.");
        applyFilters();
    } catch (err) {
        setStatus("Failed to load projections.");
        infoEl.textContent = `Error: ${err.message}\n\nMake sure you run build_site_data.py and that projections.json is next to index.html.`;
    }
}

function renderTeamBlock(title, list, captainName) {
    const header = `<div class="subtitle">${escapeHtml(title)}</div>`;
    const cards = (list || []).map(p => {
        const cap = captainName && p.name === captainName ? " (C)" : "";
        return `
      <div class="card">
        <div>
          <div><b>${escapeHtml(p.name)}${cap}</b></div>
          <div class="small">${escapeHtml(p.position)} · ${escapeHtml(p.team)}</div>
        </div>
        <div class="num">
          <div>${fmt(p.price, 1)}</div>
          <div class="small">${fmt(p.predicted_points_next_3, 2)}</div>
        </div>
      </div>
    `;
    }).join("");

    return header + cards;
}

async function loadOptimalTeam() {
    setStatus("Loading optimal team…");
    try {
        const res = await fetch("./optimal_442.json", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        const captain = data.captain?.name || "";
        const totals = data.totals || {};

        teamEl.innerHTML =
            `<div class="info">Formation: ${escapeHtml(data.formation || "4-4-2")}
Total cost: ${fmt(totals.total_cost, 2)}
XI points next 3: ${fmt(totals.xi_points_next_3, 2)}
XI + captain next 3: ${fmt(totals.xi_plus_captain_next_3, 2)}</div>` +
            renderTeamBlock("Starting XI", data.starting_xi, captain) +
            `<div style="height:10px;"></div>` +
            renderTeamBlock("Bench", data.bench, captain);

        setStatus("Optimal team loaded.");
    } catch (err) {
        setStatus("Failed to load optimal team.");
        teamEl.innerHTML = "";
        infoEl.textContent = `Error: ${err.message}\n\nMake sure optimal_442.json exists (run build_site_data.py).`;
    }
}

// Wire up UI
loadBtn.addEventListener("click", loadProjections);
loadTeamBtn.addEventListener("click", loadOptimalTeam);

searchEl.addEventListener("input", applyFilters);
posEl.addEventListener("change", applyFilters);
sortEl.addEventListener("change", applyFilters);

// Optional: auto-load projections on page open
loadProjections();