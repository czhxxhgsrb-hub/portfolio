async function loadProjects() {
  const list = document.getElementById("projectsList");
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

    list.innerHTML = projects.map(p => {
      // vælg primært link: live hvis findes, ellers repo
      const href = p.live || p.repo || "#";
      const title = escapeHtml(p.title ?? "Untitled");
      const desc = p.description ? ` <span class="muted">— ${escapeHtml(p.description)}</span>` : "";

      return `<li><a href="${href}" target="_blank" rel="noreferrer">${title}</a>${desc}</li>`;
    }).join("");

  } catch (e) {
    empty.textContent = "Kunne ikke hente projects.json (tjek at filen findes).";
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
