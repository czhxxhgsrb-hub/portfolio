const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");

const toggleBtn = document.getElementById("toggleBtn");
const stepBtn = document.getElementById("stepBtn");
const resetBtn = document.getElementById("resetBtn");
const info = document.getElementById("info");

const W = canvas.width;
const H = canvas.height;

const clamp01 = (x) => Math.max(0, Math.min(1, x));

let running = true;
let latestId = 0;

class Participant {
    constructor(name, politicalView, influenciable) {
        this.id = ++latestId;
        this.name = name;
        this.politicalView = clamp01(politicalView);
        this.influenciable = clamp01(influenciable);
    }
    matchScore(_other) { throw new Error("abstract"); }
    onInteraction(_other, _isMatch) { throw new Error("abstract"); }
}

class FreeThinker extends Participant {
    matchScore(other) {
        return 1 - Math.abs(this.politicalView - other.politicalView);
    }
    onInteraction(other, _isMatch) {
        const current = this.politicalView;
        const target = other.politicalView;
        const viewdiff = (target - current) * this.influenciable;
        this.politicalView = clamp01(current + viewdiff);
        return this.politicalView;
    }
}

class CloseMinded extends Participant {
    matchScore(other) {
        return 1 - Math.abs(this.politicalView - other.politicalView);
    }
    onInteraction(other, _isMatch) {
        const current = this.politicalView;
        const target = other.politicalView;
        const closeness = this.matchScore(other);
        const viewdiff = (target - current) * this.influenciable * closeness;
        this.politicalView = clamp01(current + viewdiff);
        return this.politicalView;
    }
}

class Unpredictable extends Participant {
    matchScore(other) {
        return 1 - Math.abs(this.politicalView - other.politicalView);
    }
    onInteraction(other, _isMatch) {
        const current = this.politicalView;
        const target = other.politicalView;
        const viewdiff = (target - current) * this.influenciable;
        this.politicalView = clamp01(current + viewdiff);

        // “unpredictable”: influenciable ændrer sig hver gang
        this.influenciable = Math.random();
        return this.politicalView;
    }
}

class Safe extends Participant {
    matchScore(other) {
        return 1 - Math.abs(this.politicalView - other.politicalView);
    }
    onInteraction(_other, _isMatch) {
        const center = 0.5;
        const current = this.politicalView;
        const viewdiff = (center - current) * this.influenciable;
        this.politicalView = clamp01(current + viewdiff);
        return this.politicalView;
    }
}

function createParticipants() {
    latestId = 0;
    return [
        new FreeThinker("A (FRE)", 0.2, 0.6),
        new FreeThinker("B (FRE)", 0.8, 0.8),
        new CloseMinded("C (CLO)", 0.9, 0.2),
        new CloseMinded("D (CLO)", 0.1, 0.2),
        new Unpredictable("E (UNP)", 0.5, 0.5),
        new Unpredictable("F (UNP)", 0.5, 0.5),
        new Safe("G (SAF)", 0.3, 0.6),
        new Safe("H (SAF)", 0.7, 0.6),
    ];
}

function layout(ps) {
    const n = ps.length;
    const cx = W / 2;
    const cy = H / 2;
    const radius = Math.min(W, H) * 0.35;

    const pos = new Map();
    ps.forEach((p, i) => {
        const angle = (2 * Math.PI * i) / n;
        pos.set(p.id, {
            x: cx + radius * Math.cos(angle),
            y: cy + radius * Math.sin(angle),
        });
    });
    return pos;
}

function computeEdges(ps) {
    const edges = [];
    for (let i = 0; i < ps.length; i++) {
        for (let j = i + 1; j < ps.length; j++) {
            if (ps[i].matchScore(ps[j]) > 0.5) edges.push([ps[i], ps[j]]);
        }
    }
    return edges;
}

function pickTwoDifferent(ps) {
    const i1 = Math.floor(Math.random() * ps.length);
    let i2 = Math.floor(Math.random() * ps.length);
    while (i2 === i1) i2 = Math.floor(Math.random() * ps.length);
    return [ps[i1], ps[i2]];
}

function simulateStep(ps) {
    const [p1, p2] = pickTwoDifferent(ps);
    const score = p1.matchScore(p2);
    const isMatch = score > 0.5;
    if (isMatch) {
        p1.onInteraction(p2, true);
        p2.onInteraction(p1, true);
    }
}

function draw(ps, pos) {
    ctx.clearRect(0, 0, W, H);

    // hvid baggrund
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, W, H);

    // edges
    const edges = computeEdges(ps);
    ctx.strokeStyle = "#ddd";
    ctx.lineWidth = 1;
    edges.forEach(([a, b]) => {
        const p1 = pos.get(a.id);
        const p2 = pos.get(b.id);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
    });

    // nodes + labels
    ctx.font = "14px Helvetica, Arial, sans-serif";
    ctx.fillStyle = "#000";
    ctx.strokeStyle = "#000";

    ps.forEach((p) => {
        const { x, y } = pos.get(p.id);

        // node: enkel cirkel
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fillStyle = "#fff";
        ctx.fill();
        ctx.strokeStyle = "#000";
        ctx.stroke();

        // labels
        ctx.fillStyle = "#000";
        ctx.fillText(p.name, x + 12, y - 4);
        ctx.fillText(p.politicalView.toFixed(2), x + 12, y + 12);
    });

    info.textContent = `Edges: ${edges.length}`;
}

let participants = createParticipants();
let positions = layout(participants);

// tick (ca. som din 70ms timer)
setInterval(() => {
    if (running) simulateStep(participants);
}, 70);

// render loop
function loop() {
    draw(participants, positions);
    requestAnimationFrame(loop);
}
loop();

// controls
toggleBtn.addEventListener("click", () => {
    running = !running;
    toggleBtn.textContent = running ? "Pause" : "Play";
});

stepBtn.addEventListener("click", () => {
    simulateStep(participants);
});

resetBtn.addEventListener("click", () => {
    participants = createParticipants();
    positions = layout(participants);
});
