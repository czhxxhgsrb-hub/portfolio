const display = document.getElementById("display");
const copyMsg = document.getElementById("copy-msg");

// CHANGE THIS to whatever link you want copied:
const LINK_TO_COPY = "oliverfisker.dk";

function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
    }
    // fallback
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return Promise.resolve();
}

let msgTimer = null;

document.querySelector(".keys").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;

    if (btn.dataset.value) display.value += btn.dataset.value;

    if (btn.dataset.action === "clear") {
        display.value = "";

        copyText(LINK_TO_COPY).then(() => {
            copyMsg.textContent = "Link kopieret!";
            copyMsg.classList.add("show");
            clearTimeout(msgTimer);
            msgTimer = setTimeout(() => copyMsg.classList.remove("show"), 1200);
        });
    }

    if (btn.dataset.action === "equals") {
        const m = display.value.match(/^(\d+)([+\-*])(\d+)$/);
        if (!m) { display.value = "Error"; return; }

        const a = m[1], op = m[2], b = m[3];

        try {
            if (op === "+") display.value = a + b;
            if (op === "*") display.value = b.repeat(Number(a)); // 5*6 => 666666
            if (op === "-") {
                if (!a.includes(b)) throw new Error();
                const out = a.replace(b, "");
                display.value = out === "" ? "0" : out;
            }
        } catch {
            display.value = "Error";
        }
    }
});
