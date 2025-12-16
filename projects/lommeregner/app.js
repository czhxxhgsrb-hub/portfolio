const display = document.getElementById("display");

document.querySelector(".keys").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.value) display.value += btn.dataset.value;
    if (btn.dataset.action === "clear") display.value = "";
    if (btn.dataset.action === "equals") {
        const expr = display.value;

        const m = expr.match(/^(\d+)([+\-*])(\d+)$/);
        if (!m) {
            display.value = "Error";
            return;
        }

        const a = m[1];
        const op = m[2];
        const b = m[3];

        try {
            if (op === "+") {
                display.value = a + b;
            } else if (op === "*") {
                const times = Number(a);
                if (!Number.isFinite(times) || times < 0) throw new Error();
                display.value = b.repeat(times);
            } else if (op === "-") {
                if (!a.includes(b)) throw new Error();
                const out = a.replace(b, "");
                display.value = out === "" ? "0" : out;
            }
        } catch {
            display.value = "Error";
        }
    }
});
