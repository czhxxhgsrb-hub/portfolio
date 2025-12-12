const yearEl = document.getElementById("year");
yearEl.textContent = new Date().getFullYear();

async function loadProjects() {
    const grid = document.getElementById("projectsGrid");
    const empty = document.getElementById("emptyState");

    try {
        const res = await fetch("./projects.json", { cache: "no-store" });
        const data = await res.json();
        const projects = data.projects ?? [];

        if (!projects.length) {
            empty.style.display = "block";
            return;
        }

        empty.style.display = "none";
        grid.innerHTML = projects.map(p => `
      <article class="card project">
        <div>
          <h3>${escapeHtml(p.title ?? "Untitled")}</h3>
          <p class="muted">${escapeHtml(p.description ?? "")}</p>
        </div>
        <div class="badges">
          ${(p.tags ?? []).map(t => `<span class="badge">${escapeHtml(t)}</span>`).join("")}
        </div>
        <div class="project__links">
          ${p.live ? `<a href="${p.live}" target="_blank" rel="noreferrer">Live</a>` : ""}
          ${p.repo ? `<a href="${p.repo}" target="_blank" rel="noreferrer">Repo</a>` : ""}
        </div>
      </article>
    `).join("");
    } catch (e) {
        empty.textContent = "Kunne ikke hente projects.json endnu – tjek at filerne ligger korrekt.";
        empty.style.display = "block";
    }
}

function escapeHtml(str) {
    return String(str)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

loadProjects();
