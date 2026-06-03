# lzits-nodes
A collection of custom nodes for Comfyui

## Included Nodes
- String Splitter
- String Appender (Suffix)
- String Prepender (Prefix)
- Index Picker
- LoRA Selector Multi-Output
- Image Outpaint (Color Canvas)
- Bernini Model Config
- Bernini Generation Settings
- Bernini Case Builder
- Bernini Run Single GPU
- Bernini Conditioning (Kijai Branch)
- Bernini Load Output Image
- Bernini Setup Commands

## Image Outpaint (Color Canvas)
This node lets you:
- Upload/load an image directly in the node UI.
- Expand the canvas on left/right/top/bottom without scaling the original image.
- Fill new outpaint regions with a chosen color (`#RRGGBB`, `#RGB`, `r,g,b`, or basic names like `white`).
- Output a mask where `1.0` is the new outpaint area and `0.0` is the original image.

## Bernini nodes
Adds first-pass ComfyUI wrappers for ByteDance's Bernini-R renderer from https://github.com/bytedance/Bernini.

The layout now follows the Kijai/WanVideoWrapper style more closely: small typed helper nodes feed a runner node, heavy model code is not imported at ComfyUI startup, widgets have tooltips/descriptions, and the subprocess runner streams logs instead of waiting silently.

Recommended graph:
`Bernini Setup Commands` -> install upstream assets manually, then wire `Bernini Model Config` + `Bernini Case Builder` + `Bernini Generation Settings` into `Bernini Run Single GPU`. For one-frame/image results, connect the runner's `output_path` to `Bernini Load Output Image` to get a normal ComfyUI `IMAGE` tensor.

### Bernini Setup Commands
Outputs copy/paste setup commands to clone Bernini, install its requirements, and download `ByteDance/Bernini-R-Diffusers`.
Bernini currently wants Python 3.11, CUDA 12.4, PyTorch 2.5.1+cu124, and a strong CUDA GPU; H100-class hardware is recommended by the upstream repo.

### Bernini Model Config
Bundles repo path, Python executable, model config directory, optional high/low checkpoint paths, and optional env vars into a typed `BERNINI_CONFIG` object.
This mirrors Kijai's loader/config nodes: set model/env paths once, connect them into the runner, and keep the runner less cluttered.

### Bernini Generation Settings
Bundles frame count, size, steps, seed, fps, guidance mode, and Bernini omega/eta/flow-shift values into a typed `BERNINI_GENARGS` object.

### Bernini Case Builder
Builds a Bernini case JSON object with `task_type`, `guidance_mode`, prompt, media paths, and output path. It outputs both plain strings and a typed `BERNINI_CASE` object for cleaner graphs.

### Bernini Run Single GPU
Runs upstream `infer_single_gpu.py` in a subprocess so ComfyUI can still start even if Bernini dependencies are missing.
Prefer connecting:
- `bernini_config` from Bernini Model Config.
- `bernini_case` from Bernini Case Builder.
- `generation_args` from Bernini Generation Settings.

Fallback widgets are still present for quick one-node tests. The runner supports `dry_run` to build the command/case without launching Bernini, plus `extra_args` for upstream CLI flags that are not exposed yet. Relative outputs are resolved under ComfyUI's output directory when available, output folders are created automatically, and timeout handling kills/reaps hung upstream processes.

### Bernini Load Output Image
Loads a generated `.png`, `.jpg`, `.jpeg`, or `.webp` output path into a ComfyUI `IMAGE` tensor so normal Preview/Save Image nodes can consume Bernini t2i/i2i results. Leave video `.mp4` outputs as path strings for video-specific helper nodes.

### Bernini Conditioning (Kijai Branch)
Optional native-conditioning bridge based on Kijai's `ComfyUI/tree/bernini` branch. It accepts positive/negative conditioning, a VAE, optional source/reference video/images, and emits `context_latents` plus a matching Wan latent. This only changes model behavior when your ComfyUI build understands `context_latents` (Kijai's Bernini branch or a future upstream equivalent); on normal mainline ComfyUI it is present for compatibility but the core Wan model may ignore that extra conditioning.

For text-to-image, use `task_type=t2i`, `num_frames=1`, and a `.png` output path. For video, use one of the video task types, increase `num_frames`, and use a `.mp4` output path.
