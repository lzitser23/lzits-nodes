import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const COORD_NAMES = [
    "source_x1", "source_y1", "source_x2", "source_y2",
    "target_x1", "target_y1", "target_x2", "target_y2",
];

app.registerExtension({
    name: "lzits.BBoxDrawWidget",

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "BBoxDrawWidget") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);
            this._bboxState = createState(this);
            addCanvasWidget(this._bboxState);
            restoreFromWidgets(this._bboxState);
        };

        // After execution, output index 1 is the clean source_image passthrough.
        // Load it into the canvas as the background.
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            onExecuted?.apply(this, arguments);
            const imgInfo = output?.images?.[1];
            if (imgInfo && this._bboxState) {
                const url = api.apiURL(
                    `/view?filename=${encodeURIComponent(imgInfo.filename)}` +
                    `&subfolder=${encodeURIComponent(imgInfo.subfolder ?? "")}` +
                    `&type=${imgInfo.type ?? "temp"}`
                );
                loadBackground(this._bboxState, url);
            }
        };

        // Restore drawn boxes when a saved workflow is loaded.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (config) {
            onConfigure?.apply(this, arguments);
            if (this._bboxState) {
                restoreFromWidgets(this._bboxState);
                redraw(this._bboxState);
            }
        };

        // Clear the canvas background when the image input is disconnected.
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected) {
            onConnectionsChange?.apply(this, arguments);
            if (type === 1 /* INPUT */ && index === 0 && !connected && this._bboxState) {
                this._bboxState.bgImage = null;
                this._bboxState.imageW = 512;
                this._bboxState.imageH = 512;
                setStatus(this._bboxState, "Connect an image and run once to load the preview.");
                redraw(this._bboxState);
            }
        };
    },
});

// ─── State ────────────────────────────────────────────────────────────────────

function createState(node) {
    return {
        node,
        canvas: null,
        ctx: null,
        bgImage: null,
        imageW: 512,
        imageH: 512,
        sourceBox: null,    // { x1, y1, x2, y2 } in image-space pixels
        targetBox: null,
        mode: "source",     // "source" | "target"
        dragging: false,
        dragStart: null,
        dragCurrent: null,
        statusEl: null,
        modeBtn: null,
    };
}

// ─── Widget creation ──────────────────────────────────────────────────────────

function addCanvasWidget(state) {
    const { node } = state;

    // Hide the raw INT coordinate widgets — the canvas replaces them visually.
    // computeSize returning -4 collapses the widget row to nothing while keeping
    // its value in the serialized graph so coordinates survive save/load.
    for (const name of COORD_NAMES) {
        const w = node.widgets?.find(w => w.name === name);
        if (w) w.computeSize = () => [0, -4];
    }

    // ── Container ──
    const container = document.createElement("div");
    container.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:4px 4px 2px;";

    // ── Toolbar ──
    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;gap:6px;";

    const modeBtn = document.createElement("button");
    applyModeStyle(modeBtn, "source");
    modeBtn.onclick = () => {
        state.mode = state.mode === "source" ? "target" : "source";
        applyModeStyle(modeBtn, state.mode);
    };
    state.modeBtn = modeBtn;

    const clearBtn = document.createElement("button");
    clearBtn.textContent = "Clear All";
    clearBtn.style.cssText =
        "padding:4px 10px;background:#444;color:#eee;border:none;" +
        "border-radius:4px;cursor:pointer;font-size:12px;";
    clearBtn.onclick = () => {
        state.sourceBox = null;
        state.targetBox = null;
        syncWidgets(state);
        redraw(state);
    };

    toolbar.appendChild(modeBtn);
    toolbar.appendChild(clearBtn);

    // ── Canvas ──
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 512;
    canvas.style.cssText =
        "width:100%;display:block;cursor:crosshair;" +
        "border-radius:4px;border:1px solid #333;";
    state.canvas = canvas;
    state.ctx = canvas.getContext("2d");

    attachMouseHandlers(state);

    // ── Status line ──
    const statusEl = document.createElement("div");
    statusEl.style.cssText = "font-size:11px;color:#888;text-align:center;padding:2px 0;";
    statusEl.textContent = "Connect an image and run once to load the preview.";
    state.statusEl = statusEl;

    container.appendChild(toolbar);
    container.appendChild(canvas);
    container.appendChild(statusEl);

    node.addDOMWidget("bbox_canvas", "BBoxCanvas", container, {
        serialize: false,
        computeSize([width]) {
            const aspect = state.imageH / state.imageW;
            const drawH = Math.round((width - 8) * aspect);
            const clampedH = Math.min(Math.max(drawH, 120), 400);
            return [width, clampedH + 52]; // +52 for toolbar + status
        },
    });

    redraw(state);
}

function applyModeStyle(btn, mode) {
    if (mode === "source") {
        btn.textContent = "● Draw Source (Red)";
        btn.style.cssText =
            "flex:1;padding:4px 8px;background:#c0392b;color:#fff;" +
            "border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:bold;";
    } else {
        btn.textContent = "● Draw Target (Green)";
        btn.style.cssText =
            "flex:1;padding:4px 8px;background:#27ae60;color:#fff;" +
            "border:none;border-radius:4px;cursor:pointer;font-size:12px;font-weight:bold;";
    }
}

// ─── Mouse handling ───────────────────────────────────────────────────────────

function attachMouseHandlers(state) {
    const { canvas } = state;

    canvas.addEventListener("mousedown", e => {
        if (e.button !== 0) return;
        state.dragging = true;
        state.dragStart = toImageCoords(state, e);
        state.dragCurrent = { ...state.dragStart };
        e.preventDefault();
        e.stopPropagation();
    });

    canvas.addEventListener("mousemove", e => {
        if (!state.dragging) return;
        state.dragCurrent = toImageCoords(state, e);
        redraw(state);
        drawLiveBox(state);
        e.preventDefault();
    });

    const commit = e => {
        if (!state.dragging) return;
        state.dragging = false;
        if (state.dragStart && state.dragCurrent) {
            const box = makeBox(state.dragStart, state.dragCurrent);
            // Ignore tiny accidental clicks (< 4px in either dimension).
            if (box.x2 - box.x1 >= 4 && box.y2 - box.y1 >= 4) {
                if (state.mode === "source") state.sourceBox = box;
                else state.targetBox = box;
                syncWidgets(state);
            }
        }
        redraw(state);
        e.preventDefault();
    };

    canvas.addEventListener("mouseup", commit);
    canvas.addEventListener("mouseleave", commit);
}

function toImageCoords(state, e) {
    const rect = state.canvas.getBoundingClientRect();
    const sx = state.imageW / rect.width;
    const sy = state.imageH / rect.height;
    return {
        x: Math.round((e.clientX - rect.left) * sx),
        y: Math.round((e.clientY - rect.top) * sy),
    };
}

function makeBox(a, b) {
    return {
        x1: Math.min(a.x, b.x),
        y1: Math.min(a.y, b.y),
        x2: Math.max(a.x, b.x),
        y2: Math.max(a.y, b.y),
    };
}

// ─── Drawing ──────────────────────────────────────────────────────────────────

function redraw(state) {
    const { ctx, imageW, imageH, bgImage, sourceBox, targetBox } = state;
    ctx.clearRect(0, 0, imageW, imageH);

    if (bgImage) {
        ctx.drawImage(bgImage, 0, 0, imageW, imageH);
    } else {
        ctx.fillStyle = "#1a1a1a";
        ctx.fillRect(0, 0, imageW, imageH);
        ctx.fillStyle = "#555";
        ctx.font = `${Math.max(12, Math.round(imageW * 0.028))}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText("Run graph once to load image preview", imageW / 2, imageH / 2);
    }

    if (sourceBox) strokeBox(ctx, sourceBox, "rgba(255,60,60,1)", 3);
    if (targetBox) strokeBox(ctx, targetBox, "rgba(60,255,60,1)", 3);
}

function drawLiveBox(state) {
    if (!state.dragStart || !state.dragCurrent) return;
    const box = makeBox(state.dragStart, state.dragCurrent);
    const color = state.mode === "source" ? "rgba(255,60,60,0.75)" : "rgba(60,255,60,0.75)";
    strokeBox(state.ctx, box, color, 2);
}

function strokeBox(ctx, box, color, lw) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.strokeRect(box.x1 + 0.5, box.y1 + 0.5, box.x2 - box.x1, box.y2 - box.y1);
    ctx.restore();
}

// ─── Widget sync ──────────────────────────────────────────────────────────────

function syncWidgets(state) {
    setW(state.node, "source_x1", state.sourceBox?.x1 ?? 0);
    setW(state.node, "source_y1", state.sourceBox?.y1 ?? 0);
    setW(state.node, "source_x2", state.sourceBox?.x2 ?? 0);
    setW(state.node, "source_y2", state.sourceBox?.y2 ?? 0);
    setW(state.node, "target_x1", state.targetBox?.x1 ?? 0);
    setW(state.node, "target_y1", state.targetBox?.y1 ?? 0);
    setW(state.node, "target_x2", state.targetBox?.x2 ?? 0);
    setW(state.node, "target_y2", state.targetBox?.y2 ?? 0);
}

function setW(node, name, value) {
    const w = node.widgets?.find(w => w.name === name);
    if (w) w.value = value;
}

function restoreFromWidgets(state) {
    const get = name => state.node.widgets?.find(w => w.name === name)?.value ?? 0;
    const sx1 = get("source_x1"), sy1 = get("source_y1");
    const sx2 = get("source_x2"), sy2 = get("source_y2");
    const tx1 = get("target_x1"), ty1 = get("target_y1");
    const tx2 = get("target_x2"), ty2 = get("target_y2");
    if (sx2 > sx1 && sy2 > sy1) state.sourceBox = { x1: sx1, y1: sy1, x2: sx2, y2: sy2 };
    if (tx2 > tx1 && ty2 > ty1) state.targetBox = { x1: tx1, y1: ty1, x2: tx2, y2: ty2 };
}

// ─── Background image loading ─────────────────────────────────────────────────

function loadBackground(state, url) {
    const img = new Image();
    img.onload = () => {
        state.bgImage = img;
        state.imageW = img.naturalWidth;
        state.imageH = img.naturalHeight;
        state.canvas.width = img.naturalWidth;
        state.canvas.height = img.naturalHeight;
        setStatus(
            state,
            `${img.naturalWidth} × ${img.naturalHeight} px  —  ` +
            `draw red source box, then green target box`
        );
        state.node.setDirtyCanvas(true, true);
        redraw(state);
    };
    img.onerror = () => setStatus(state, "Failed to load image preview.");
    img.src = url;
}

function setStatus(state, text) {
    if (state.statusEl) state.statusEl.textContent = text;
}
