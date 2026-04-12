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

        // After the graph runs, try to get the clean input image from the
        // upstream node's cached preview first, then fall back to our own output.
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (output) {
            onExecuted?.apply(this, arguments);
            if (!this._bboxState) return;

            if (tryLoadFromUpstream(this._bboxState)) return;

            // Fallback: use our own output images. Try index 1 (source_image
            // passthrough) then index 0 (conditioned_image).
            const imgs = output?.images;
            if (!imgs?.length) return;
            const info = imgs.length > 1 ? imgs[1] : imgs[0];
            if (!info) return;

            const qs = new URLSearchParams({
                filename: info.filename,
                subfolder: info.subfolder ?? "",
                type: info.type ?? "temp",
                t: Date.now(),   // cache-bust
            });
            loadBackground(this._bboxState, api.apiURL(`/view?${qs}`));
        };

        // When a node is reconnected after save/load, restore boxes and
        // immediately try to pull the upstream preview.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            if (!this._bboxState) return;
            restoreFromWidgets(this._bboxState);
            redraw(this._bboxState);
            // Small delay so the graph is fully wired before we query links.
            setTimeout(() => tryLoadFromUpstream(this._bboxState), 200);
        };

        // When the image input is connected, immediately try to show the
        // upstream preview so the user doesn't have to run first.
        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected) {
            onConnectionsChange?.apply(this, arguments);
            if (!this._bboxState) return;
            if (type === 1 /* INPUT */ && index === 0) {
                if (connected) {
                    setTimeout(() => tryLoadFromUpstream(this._bboxState), 150);
                } else {
                    this._bboxState.bgImage = null;
                    this._bboxState.imageW = 512;
                    this._bboxState.imageH = 512;
                    setStatus(this._bboxState, "Connect an image and run once to load the preview.");
                    redraw(this._bboxState);
                }
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
        sourceBox: null,
        targetBox: null,
        mode: "source",
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

    // Collapse the raw INT coordinate widgets to zero height.
    // They stay serialized (their values travel to Python) but are invisible.
    for (const name of COORD_NAMES) {
        const w = node.widgets?.find(w => w.name === name);
        if (w) w.computeSize = () => [0, -4];
    }

    const container = document.createElement("div");
    container.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:4px 4px 2px;";

    // Toolbar
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

    // Manual refresh button as a safety fallback
    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "⟳";
    refreshBtn.title = "Reload preview from upstream node";
    refreshBtn.style.cssText =
        "padding:4px 8px;background:#333;color:#eee;border:none;" +
        "border-radius:4px;cursor:pointer;font-size:13px;";
    refreshBtn.onclick = () => tryLoadFromUpstream(state);

    toolbar.appendChild(modeBtn);
    toolbar.appendChild(clearBtn);
    toolbar.appendChild(refreshBtn);

    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 512;
    canvas.style.cssText =
        "width:100%;display:block;cursor:crosshair;" +
        "border-radius:4px;border:1px solid #333;";
    state.canvas = canvas;
    state.ctx = canvas.getContext("2d");

    attachMouseHandlers(state);

    const statusEl = document.createElement("div");
    statusEl.style.cssText = "font-size:11px;color:#888;text-align:center;padding:2px 0;";
    statusEl.textContent = "Connect an image. It will load automatically or click ⟳.";
    state.statusEl = statusEl;

    container.appendChild(toolbar);
    container.appendChild(canvas);
    container.appendChild(statusEl);

    node.addDOMWidget("bbox_canvas", "BBoxCanvas", container, {
        serialize: false,
        computeSize([width]) {
            const aspect = state.imageH / state.imageW;
            const h = Math.round((width - 8) * aspect);
            return [width, Math.min(Math.max(h, 120), 400) + 52];
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

// ─── Upstream image loading ───────────────────────────────────────────────────

// Pull the preview image directly from the node connected to input slot 0.
// This works as soon as that node has been executed at least once — no need
// to run our own node first.
function tryLoadFromUpstream(state) {
    const inputLink = state.node.inputs?.[0]?.link;
    if (inputLink == null) return false;

    const link = app.graph.links[inputLink];
    if (!link) return false;

    const upstream = app.graph.getNodeById(link.origin_id);
    // origin_slot tells us which output of the upstream node is connected.
    const img = upstream?.imgs?.[link.origin_slot ?? 0];

    if (img instanceof HTMLImageElement && img.complete && img.naturalWidth > 0) {
        applyBgImage(state, img);
        return true;
    }
    return false;
}

function applyBgImage(state, img) {
    state.bgImage = img;
    state.imageW = img.naturalWidth;
    state.imageH = img.naturalHeight;
    state.canvas.width = img.naturalWidth;
    state.canvas.height = img.naturalHeight;
    setStatus(
        state,
        `${img.naturalWidth} × ${img.naturalHeight} px  —  ` +
        `Red = source object, Green = destination`
    );
    state.node.setDirtyCanvas(true, true);
    redraw(state);
}

function loadBackground(state, url) {
    const img = new Image();
    img.onload = () => applyBgImage(state, img);
    img.onerror = () => setStatus(state, "Failed to load image preview. Try clicking ⟳.");
    img.src = url;
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
    return {
        x: Math.round((e.clientX - rect.left) * (state.imageW / rect.width)),
        y: Math.round((e.clientY - rect.top) * (state.imageH / rect.height)),
    };
}

function makeBox(a, b) {
    return {
        x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y),
        x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y),
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
        ctx.fillText("Connect an image. Click ⟳ or run the graph to load preview.", imageW / 2, imageH / 2);
    }

    if (sourceBox) strokeBox(ctx, sourceBox, "rgba(255,60,60,1)", 3);
    if (targetBox) strokeBox(ctx, targetBox, "rgba(60,255,60,1)", 3);
}

function drawLiveBox(state) {
    if (!state.dragStart || !state.dragCurrent) return;
    const box = makeBox(state.dragStart, state.dragCurrent);
    strokeBox(state.ctx, box, state.mode === "source" ? "rgba(255,60,60,0.75)" : "rgba(60,255,60,0.75)", 2);
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
    const { node, sourceBox, targetBox } = state;
    const values = {
        source_x1: sourceBox?.x1 ?? 0,
        source_y1: sourceBox?.y1 ?? 0,
        source_x2: sourceBox?.x2 ?? 0,
        source_y2: sourceBox?.y2 ?? 0,
        target_x1: targetBox?.x1 ?? 0,
        target_y1: targetBox?.y1 ?? 0,
        target_x2: targetBox?.x2 ?? 0,
        target_y2: targetBox?.y2 ?? 0,
    };
    for (const [name, value] of Object.entries(values)) {
        const w = node.widgets?.find(w => w.name === name);
        if (w) {
            w.value = value;
            w.callback?.(value); // trigger any ComfyUI update hooks
        }
    }
    // Mark the graph dirty so ComfyUI knows values have changed.
    app.graph.setDirtyCanvas(true);
}

function restoreFromWidgets(state) {
    const get = name => state.node.widgets?.find(w => w.name === name)?.value ?? 0;
    const [sx1, sy1, sx2, sy2] = ["source_x1", "source_y1", "source_x2", "source_y2"].map(get);
    const [tx1, ty1, tx2, ty2] = ["target_x1", "target_y1", "target_x2", "target_y2"].map(get);
    if (sx2 > sx1 && sy2 > sy1) state.sourceBox = { x1: sx1, y1: sy1, x2: sx2, y2: sy2 };
    if (tx2 > tx1 && ty2 > ty1) state.targetBox = { x1: tx1, y1: ty1, x2: tx2, y2: ty2 };
}

function setStatus(state, text) {
    if (state.statusEl) state.statusEl.textContent = text;
}
