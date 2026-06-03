import json
import logging
import os
import queue
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    from comfy.utils import ProgressBar
except Exception:  # lets this module unit-test outside ComfyUI
    ProgressBar = None

try:
    import folder_paths
except Exception:  # lets this module unit-test outside ComfyUI
    folder_paths = None


log = logging.getLogger(__name__)

GUIDANCE_MODES = ["rv2v", "v2v", "v2v_chain", "t2v", "r2v_apg", "v2v_apg", "t2v_apg"]
TASK_TYPES = ["t2i", "i2i", "t2v", "v2v", "rv2v", "r2v", "mv2v"]

if folder_paths is not None:
    # Kijai-style: register a discoverable model folder key for users who want
    # to keep Bernini dirs under ComfyUI/models/bernini. Diffusers directories
    # still need to be typed/pasted because Comfy's filename list is file-based.
    try:
        folder_paths.add_model_folder_path("bernini", os.path.join(folder_paths.models_dir, "bernini"))
    except Exception:
        pass


def _split_paths(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    text = text.replace(";", "\n").replace(",", "\n")
    return [line.strip().strip('"') for line in text.splitlines() if line.strip()]


def _normalize_optional_path(value):
    value = str(value or "").strip().strip('"')
    return value or None


def _bool_flag(cmd, enabled, flag):
    if enabled:
        cmd.append(flag)


def _quote_cmd(cmd):
    if os.name == "nt":
        return subprocess.list2cmdline([str(part) for part in cmd])
    return " ".join(shlex.quote(str(part)) for part in cmd)


def _split_extra_args(extra_args):
    return shlex.split(extra_args, posix=(os.name != "nt"))


def _shell_quote(text):
    if os.name == "nt":
        return subprocess.list2cmdline([str(text)])
    return shlex.quote(str(text))


def _repo_script(repo_dir, script_name):
    repo = Path(repo_dir).expanduser().resolve()
    script = repo / script_name
    if not script.exists():
        raise FileNotFoundError(
            f"Could not find {script_name} in '{repo}'. Clone ByteDance/Bernini first: "
            "git clone https://github.com/bytedance/Bernini.git"
        )
    return repo, script


def _case_dict(prompt, task_type, guidance_mode, output_path, image_path="", video_paths="", reference_images=""):
    case = {
        "task_type": task_type,
        "guidance_mode": guidance_mode,
        "prompt": prompt,
        "output": output_path,
    }

    image = _normalize_optional_path(image_path)
    videos = _split_paths(video_paths)
    images = _split_paths(reference_images)

    if image:
        case["image"] = image
    if videos:
        case["video"] = videos
    if images:
        case["images"] = images
    return case


def _parse_json_object(text, label):
    if not text or not str(text).strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return data


def _make_temp_case(case_json):
    fd, name = tempfile.mkstemp(prefix="bernini_case_", suffix=".json")
    case_path = Path(name)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(case_json)
    try:
        os.chmod(case_path, 0o600)
    except Exception:
        pass
    return case_path


def _comfy_output_dir():
    if folder_paths is not None:
        try:
            return Path(folder_paths.get_output_directory()).resolve()
        except Exception:
            pass
    return None


def _resolve_output_path(output_path, repo):
    raw = _normalize_optional_path(output_path) or "bernini_output.png"
    path = Path(raw).expanduser()
    if path.is_absolute():
        resolved = path.resolve()
    else:
        base = _comfy_output_dir() or Path(repo).resolve()
        resolved = (base / path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _output_ui_payload(path):
    if folder_paths is None:
        return None
    try:
        output_dir = Path(folder_paths.get_output_directory()).resolve()
        resolved = Path(path).resolve()
        if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            return None
        rel = resolved.relative_to(output_dir)
        return {
            "images": [
                {
                    "filename": rel.name,
                    "subfolder": str(rel.parent).replace("\\", "/") if str(rel.parent) != "." else "",
                    "type": "output",
                }
            ]
        }
    except Exception:
        return None


def _load_image_tensor(path):
    try:
        import numpy as np
        import torch
        from PIL import Image, ImageOps
    except Exception as exc:
        raise RuntimeError("Loading Bernini image outputs requires pillow, numpy, and torch.") from exc
    image = Image.open(path)
    image = ImageOps.exif_transpose(image).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)



def _resize_long_edge_comfy(image, max_size, stride=16):
    import comfy.utils

    h, w = image.shape[1], image.shape[2]
    scale = min(float(max_size) / max(h, w), 1.0)
    nh = max(stride, round(h * scale / stride) * stride)
    nw = max(stride, round(w * scale / stride) * stride)
    return comfy.utils.common_upscale(image[:, :, :, :3].movedim(-1, 1), nw, nh, "area", "disabled").movedim(1, -1)

def _terminate_process(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


def _run_streaming_subprocess(cmd, cwd, env, timeout_seconds):
    lines = []
    output_queue = queue.Queue()
    proc = None

    def reader(stream):
        try:
            for line in iter(stream.readline, ""):
                output_queue.put(line)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert proc.stdout is not None
        thread = threading.Thread(target=reader, args=(proc.stdout,), daemon=True)
        thread.start()
        deadline = time.monotonic() + int(timeout_seconds)
        while True:
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                lines.append(line)
                log.info("Bernini: %s", line.rstrip())

            return_code = proc.poll()
            if return_code is not None:
                thread.join(timeout=2)
                while True:
                    try:
                        line = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    lines.append(line)
                    log.info("Bernini: %s", line.rstrip())
                return return_code, "".join(lines)

            if time.monotonic() > deadline:
                _terminate_process(proc)
                raise subprocess.TimeoutExpired(cmd, int(timeout_seconds), output="".join(lines))
            time.sleep(0.2)
    except Exception:
        _terminate_process(proc)
        raise


def _progress(total):
    if ProgressBar is None:
        return None
    try:
        return ProgressBar(total)
    except Exception:
        return None


def _update_progress(pbar, amount=1):
    if pbar is None:
        return
    try:
        pbar.update(amount)
    except Exception:
        pass


class BerniniModelConfig:
    """Kijai-style config/loader node for upstream ByteDance/Bernini paths."""

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Collects Bernini repo, Python, config/model, checkpoint, and prompt-enhancer env settings into a reusable BERNINI_CONFIG object."
    RETURN_TYPES = ("BERNINI_CONFIG", "STRING")
    RETURN_NAMES = ("bernini_config", "summary")
    FUNCTION = "build_config"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bernini_repo_dir": ("STRING", {"default": str(Path.home() / "Bernini"), "tooltip": "Folder containing infer_single_gpu.py from https://github.com/bytedance/Bernini"}),
                "python_executable": ("STRING", {"default": sys.executable, "tooltip": "Python in the Bernini environment. Usually a Python 3.11 CUDA env, not necessarily ComfyUI's Python."}),
                "config": ("STRING", {"default": str(Path.home() / "Bernini-R-Diffusers"), "tooltip": "Recommended: ByteDance/Bernini-R-Diffusers local directory. Alternative: configs/bernini_renderer_wan22."}),
                "high_noise_ckpt": ("STRING", {"default": "", "tooltip": "Optional. Set with low_noise_ckpt for separate checkpoint layout."}),
                "low_noise_ckpt": ("STRING", {"default": "", "tooltip": "Optional. Set with high_noise_ckpt for separate checkpoint layout."}),
            },
            "optional": {
                "env_json": ("STRING", {"multiline": True, "default": "", "tooltip": "Optional env vars as JSON, e.g. {\"CUDA_VISIBLE_DEVICES\":\"0\", \"BERNINI_PE_API_KEY\":\"...\"}"}),
            },
        }

    def build_config(self, bernini_repo_dir, python_executable, config, high_noise_ckpt="", low_noise_ckpt="", env_json=""):
        hi = _normalize_optional_path(high_noise_ckpt)
        lo = _normalize_optional_path(low_noise_ckpt)
        if bool(hi) != bool(lo):
            raise ValueError("high_noise_ckpt and low_noise_ckpt must either both be set or both be empty")
        env = _parse_json_object(env_json, "env_json")
        cfg = {
            "bernini_repo_dir": str(Path(bernini_repo_dir).expanduser()),
            "python_executable": _normalize_optional_path(python_executable) or sys.executable,
            "config": str(Path(config).expanduser()) if config else "",
            "high_noise_ckpt": hi or "",
            "low_noise_ckpt": lo or "",
            "env": {str(k): str(v) for k, v in env.items()},
        }
        summary_cfg = dict(cfg)
        summary_cfg["env"] = {
            key: ("<redacted>" if any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD")) else value)
            for key, value in cfg["env"].items()
        }
        summary = json.dumps(summary_cfg, ensure_ascii=False, indent=2)
        return (cfg, summary)


class BerniniGenerationSettings:
    """Bundle generation knobs so the runner node stays readable in large graphs."""

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Kijai-style args node for Bernini sampling/generation parameters. Connect to Bernini Run Single GPU."
    RETURN_TYPES = ("BERNINI_GENARGS", "STRING")
    RETURN_NAMES = ("generation_args", "summary")
    FUNCTION = "build_args"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "num_frames": ("INT", {"default": 1, "min": 1, "max": 241, "step": 1, "tooltip": "Use 1 for text-to-image/image editing. Use >1 for video."}),
                "width": ("INT", {"default": 848, "min": 64, "max": 2048, "step": 8}),
                "height": ("INT", {"default": 480, "min": 64, "max": 2048, "step": 8}),
                "max_image_size": ("INT", {"default": 848, "min": 64, "max": 4096, "step": 8}),
                "num_inference_steps": ("INT", {"default": 40, "min": 1, "max": 100, "step": 1}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2147483647, "step": 1}),
                "fps": ("INT", {"default": 16, "min": 1, "max": 120, "step": 1}),
                "guidance_mode": (GUIDANCE_MODES, {"default": "t2v", "tooltip": "Can be overridden by the case JSON if the case contains guidance_mode."}),
            },
            "optional": {
                "flow_shift": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 20.0, "step": 0.1}),
                "omega_V": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_I": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_TI": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_scale": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 20.0, "step": 0.05}),
                "eta": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    def build_args(self, **kwargs):
        data = dict(kwargs)
        summary = json.dumps(data, ensure_ascii=False, indent=2)
        return (data, summary)


class BerniniCaseBuilder:
    """Build a Bernini case JSON file for the ByteDance/Bernini inference scripts."""

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Builds upstream Bernini case JSON. Outputs both plain STRINGs and a typed BERNINI_CASE for cleaner graphs."
    RETURN_TYPES = ("STRING", "STRING", "BERNINI_CASE")
    RETURN_NAMES = ("case_json", "case_path", "bernini_case")
    FUNCTION = "build_case"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "A cinematic shot of a marble statue coming to life."}),
                "task_type": (TASK_TYPES, {"default": "t2i"}),
                "guidance_mode": (GUIDANCE_MODES, {"default": "t2v"}),
                "output_path": ("STRING", {"default": "outputs/bernini_output.png", "tooltip": "Use .png for one-frame image outputs, .mp4 for video outputs."}),
                "save_case_path": ("STRING", {"default": "", "tooltip": "Optional path to save the case JSON for debugging/reuse."}),
            },
            "optional": {
                "image_path": ("STRING", {"default": "", "tooltip": "Single source image for i2i/editing."}),
                "video_paths": ("STRING", {"multiline": True, "default": "", "tooltip": "One or more source videos, one per line."}),
                "reference_images": ("STRING", {"multiline": True, "default": "", "tooltip": "Reference images, one per line."}),
            },
        }

    def build_case(self, prompt, task_type, guidance_mode, output_path, save_case_path="", image_path="", video_paths="", reference_images=""):
        case = _case_dict(prompt, task_type, guidance_mode, output_path, image_path, video_paths, reference_images)
        case_json = json.dumps(case, ensure_ascii=False, indent=2)
        case_path = _normalize_optional_path(save_case_path) or ""
        if case_path:
            path = Path(case_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(case_json, encoding="utf-8")
            case_path = str(path)
        return (case_json, case_path, case)


class BerniniRunSingleGPU:
    """Run ByteDance/Bernini infer_single_gpu.py from ComfyUI.

    Kijai-inspired wrapper shape: keep heavy model code out of ComfyUI import,
    expose typed config/case/generation helper nodes, and stream subprocess logs.
    """

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Runs upstream Bernini infer_single_gpu.py in a subprocess. Prefer connecting Bernini Model Config + Case Builder + Generation Settings for cleaner graphs."
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("output_path", "case_json", "command", "log")
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bernini_repo_dir": ("STRING", {"default": str(Path.home() / "Bernini"), "tooltip": "Fallback if bernini_config is not connected."}),
                "python_executable": ("STRING", {"default": sys.executable, "tooltip": "Fallback if bernini_config is not connected."}),
                "config": ("STRING", {"default": str(Path.home() / "Bernini-R-Diffusers"), "tooltip": "Fallback if bernini_config is not connected."}),
                "high_noise_ckpt": ("STRING", {"default": "", "tooltip": "Optional fallback if bernini_config is not connected."}),
                "low_noise_ckpt": ("STRING", {"default": "", "tooltip": "Optional fallback if bernini_config is not connected."}),
                "prompt": ("STRING", {"multiline": True, "default": "A cinematic shot of a marble statue coming to life."}),
                "task_type": (TASK_TYPES, {"default": "t2i"}),
                "guidance_mode": (GUIDANCE_MODES, {"default": "t2v"}),
                "output_path": ("STRING", {"default": "outputs/bernini_output.png"}),
                "num_frames": ("INT", {"default": 1, "min": 1, "max": 241, "step": 1}),
                "width": ("INT", {"default": 848, "min": 64, "max": 2048, "step": 8}),
                "height": ("INT", {"default": 480, "min": 64, "max": 2048, "step": 8}),
                "num_inference_steps": ("INT", {"default": 40, "min": 1, "max": 100, "step": 1}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2147483647, "step": 1}),
                "timeout_seconds": ("INT", {"default": 1800, "min": 60, "max": 86400, "step": 60}),
            },
            "optional": {
                "bernini_config": ("BERNINI_CONFIG", {"tooltip": "From Bernini Model Config. Overrides repo/python/config/checkpoint widgets."}),
                "bernini_case": ("BERNINI_CASE", {"tooltip": "From Bernini Case Builder. Overrides prompt/media widgets."}),
                "generation_args": ("BERNINI_GENARGS", {"tooltip": "From Bernini Generation Settings. Overrides generation widgets."}),
                "case_json_override": ("STRING", {"multiline": True, "default": "", "forceInput": True, "tooltip": "Optional raw JSON override if not using bernini_case."}),
                "image_path": ("STRING", {"default": ""}),
                "video_paths": ("STRING", {"multiline": True, "default": ""}),
                "reference_images": ("STRING", {"multiline": True, "default": ""}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "system_prompt": ("STRING", {"multiline": True, "default": ""}),
                "max_image_size": ("INT", {"default": 848, "min": 64, "max": 4096, "step": 8}),
                "fps": ("INT", {"default": 16, "min": 1, "max": 120, "step": 1}),
                "flow_shift": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 20.0, "step": 0.1}),
                "omega_V": ("FLOAT", {"default": 1.25, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_I": ("FLOAT", {"default": 4.5, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_TI": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 20.0, "step": 0.05}),
                "omega_scale": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 20.0, "step": 0.05}),
                "eta": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "use_prompt_enhancer": ("BOOLEAN", {"default": False}),
                "dry_run": ("BOOLEAN", {"default": False, "tooltip": "Build command/case but do not execute. Useful while wiring workflows."}),
                "extra_args": ("STRING", {"multiline": True, "default": "", "tooltip": "Advanced: extra CLI args appended with platform-aware shlex splitting."}),
                "show_preview": ("BOOLEAN", {"default": True, "tooltip": "For image outputs inside ComfyUI/output, return UI preview metadata."}),
            },
        }

    def run(
        self,
        bernini_repo_dir,
        python_executable,
        config,
        high_noise_ckpt,
        low_noise_ckpt,
        prompt,
        task_type,
        guidance_mode,
        output_path,
        num_frames,
        width,
        height,
        num_inference_steps,
        seed,
        timeout_seconds,
        bernini_config=None,
        bernini_case=None,
        generation_args=None,
        case_json_override="",
        image_path="",
        video_paths="",
        reference_images="",
        negative_prompt="",
        system_prompt="",
        max_image_size=848,
        fps=16,
        flow_shift=5.0,
        omega_V=1.25,
        omega_I=4.5,
        omega_TI=4.0,
        omega_scale=0.8,
        eta=0.5,
        use_prompt_enhancer=False,
        dry_run=False,
        extra_args="",
        show_preview=True,
    ):
        cfg = dict(bernini_config or {})
        bernini_repo_dir = cfg.get("bernini_repo_dir", bernini_repo_dir)
        python_executable = cfg.get("python_executable", python_executable)
        config = cfg.get("config", config)
        high_noise_ckpt = cfg.get("high_noise_ckpt", high_noise_ckpt)
        low_noise_ckpt = cfg.get("low_noise_ckpt", low_noise_ckpt)

        gen = dict(generation_args or {})
        num_frames = gen.get("num_frames", num_frames)
        width = gen.get("width", width)
        height = gen.get("height", height)
        max_image_size = gen.get("max_image_size", max_image_size)
        num_inference_steps = gen.get("num_inference_steps", num_inference_steps)
        seed = gen.get("seed", seed)
        fps = gen.get("fps", fps)
        guidance_mode = gen.get("guidance_mode", guidance_mode)
        flow_shift = gen.get("flow_shift", flow_shift)
        omega_V = gen.get("omega_V", omega_V)
        omega_I = gen.get("omega_I", omega_I)
        omega_TI = gen.get("omega_TI", omega_TI)
        omega_scale = gen.get("omega_scale", omega_scale)
        eta = gen.get("eta", eta)

        if dry_run:
            repo = Path(bernini_repo_dir).expanduser().resolve()
            script = repo / "infer_single_gpu.py"
        else:
            repo, script = _repo_script(bernini_repo_dir, "infer_single_gpu.py")
        python_executable = _normalize_optional_path(python_executable) or sys.executable

        if bernini_case is not None:
            case = dict(bernini_case)
            output_path = case.get("output", output_path)
        elif case_json_override and case_json_override.strip():
            case = _parse_json_object(case_json_override, "case_json_override")
            output_path = case.get("output", output_path)
        else:
            case = _case_dict(prompt, task_type, guidance_mode, output_path, image_path, video_paths, reference_images)

        resolved_output_path = _resolve_output_path(output_path, repo)
        case["output"] = str(resolved_output_path)
        case_json = json.dumps(case, ensure_ascii=False, indent=2)
        case_path = _make_temp_case(case_json)

        cmd = [
            python_executable,
            str(script),
            "--config", str(config),
            "--case", str(case_path),
            "--num_frames", str(int(num_frames)),
            "--width", str(int(width)),
            "--height", str(int(height)),
            "--max_image_size", str(int(max_image_size)),
            "--num_inference_steps", str(int(num_inference_steps)),
            "--seed", str(int(seed)),
            "--fps", str(int(fps)),
            "--flow_shift", str(float(flow_shift)),
            "--omega_V", str(float(omega_V)),
            "--omega_I", str(float(omega_I)),
            "--omega_TI", str(float(omega_TI)),
            "--omega_scale", str(float(omega_scale)),
            "--eta", str(float(eta)),
        ]

        hi = _normalize_optional_path(high_noise_ckpt)
        lo = _normalize_optional_path(low_noise_ckpt)
        if bool(hi) != bool(lo):
            raise ValueError("high_noise_ckpt and low_noise_ckpt must either both be set or both be empty")
        if hi and lo:
            cmd.extend(["--high_noise_ckpt", hi, "--low_noise_ckpt", lo])
        if negative_prompt.strip():
            cmd.extend(["--neg_prompt", negative_prompt])
        if system_prompt.strip():
            cmd.extend(["--system_prompt", system_prompt])
        _bool_flag(cmd, bool(use_prompt_enhancer), "--use_pe")
        if extra_args.strip():
            cmd.extend(_split_extra_args(extra_args))

        quoted = _quote_cmd(cmd)
        if dry_run:
            try:
                case_path.unlink(missing_ok=True)
            except Exception:
                pass
            return (str(resolved_output_path), case_json, quoted, "DRY RUN: command was not executed; temporary case file was removed after command construction.")

        pbar = _progress(3)
        _update_progress(pbar)
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in dict(cfg.get("env", {})).items()})

        try:
            return_code, run_log = _run_streaming_subprocess(cmd, repo, env, timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            output = exc.output or ""
            try:
                case_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"Bernini timed out after {timeout_seconds}s.\nCommand: {quoted}\n\n{output}") from exc
        finally:
            if not dry_run:
                try:
                    case_path.unlink(missing_ok=True)
                except Exception:
                    pass

        _update_progress(pbar)
        if return_code != 0:
            raise RuntimeError(f"Bernini failed with exit code {return_code}.\nCommand: {quoted}\n\n{run_log}")
        _update_progress(pbar)

        result = (str(resolved_output_path), case_json, quoted, run_log)
        ui = _output_ui_payload(resolved_output_path) if show_preview else None
        if ui:
            return {"ui": ui, "result": result}
        return result


class LzitsBerniniConditioning:
    """Kijai bernini-branch compatible in-context conditioning for Wan/Bernini.

    This is intentionally optional: it imports torch/comfy/node_helpers only at
    execution time, and it only has an effect when the installed ComfyUI/Wan
    backend understands the `context_latents` conditioning key (for example
    Kijai's ComfyUI `bernini` branch or a future mainline equivalent).
    """

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Optional native Bernini conditioning node for Kijai's ComfyUI bernini branch. Adds source/reference media as context_latents to conditioning and returns a matching Wan latent."
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "negative", "latent")
    FUNCTION = "apply"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "vae": ("VAE",),
                "width": ("INT", {"default": 832, "min": 16, "max": 8192, "step": 16}),
                "height": ("INT", {"default": 480, "min": 16, "max": 8192, "step": 16}),
                "length": ("INT", {"default": 81, "min": 1, "max": 8192, "step": 4}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096}),
            },
            "optional": {
                "source_video": ("IMAGE", {"tooltip": "Base/edit video frames for v2v/rv2v. Resized to width x height and trimmed to length."}),
                "reference_video": ("IMAGE", {"tooltip": "Moving/content reference frames. Native aspect, long edge capped by ref_max_size."}),
                "reference_images": ("IMAGE", {"tooltip": "Reference image batch. Each image is encoded as its own native-aspect context stream."}),
                "ref_max_size": ("INT", {"default": 848, "min": 16, "max": 8192, "step": 16}),
            },
        }

    def apply(self, positive, negative, vae, width, height, length, batch_size, source_video=None, reference_video=None, reference_images=None, ref_max_size=848):
        try:
            import torch
            import comfy.model_management
            import comfy.utils
            import node_helpers
        except Exception as exc:
            raise RuntimeError("Lzits Bernini Conditioning must run inside ComfyUI with torch, comfy, and node_helpers available.") from exc

        latent = torch.zeros(
            [int(batch_size), 16, ((int(length) - 1) // 4) + 1, int(height) // 8, int(width) // 8],
            device=comfy.model_management.intermediate_device(),
        )

        context = []
        if source_video is not None:
            vid = comfy.utils.common_upscale(source_video[:int(length), :, :, :3].movedim(-1, 1), int(width), int(height), "area", "center").movedim(1, -1)
            context.append(vae.encode(vid[:, :, :, :3]))

        if reference_video is not None:
            ref_vid = _resize_long_edge_comfy(reference_video[:int(length)], int(ref_max_size))
            context.append(vae.encode(ref_vid[:, :, :, :3]))

        if reference_images is not None:
            for i in range(reference_images.shape[0]):
                img = _resize_long_edge_comfy(reference_images[i:i + 1], int(ref_max_size))
                context.append(vae.encode(img[:, :, :, :3]))

        if context:
            positive = node_helpers.conditioning_set_values(positive, {"context_latents": context})
            negative = node_helpers.conditioning_set_values(negative, {"context_latents": context})

        return (positive, negative, {"samples": latent})


class BerniniLoadOutputImage:
    """Load a Bernini PNG/JPEG/WebP output path as a ComfyUI IMAGE tensor."""

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Use after Bernini Run Single GPU for one-frame/t2i outputs. Video outputs should stay as path strings for video helper nodes."
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "load_image"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "output_path": ("STRING", {"default": "", "forceInput": True, "tooltip": "PNG/JPEG/WebP path from Bernini Run Single GPU."}),
            }
        }

    def load_image(self, output_path):
        path = Path(output_path).expanduser().resolve()
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"BerniniLoadOutputImage only supports image files, got: {path}")
        if not path.exists():
            raise FileNotFoundError(f"Bernini output image does not exist: {path}")
        return (_load_image_tensor(path),)


class BerniniSetupCommands:
    """Emit copy/paste setup commands for the newly released Bernini-R renderer."""

    CATEGORY = "lzits nodes/Bernini"
    DESCRIPTION = "Setup helper for ByteDance/Bernini. Produces commands only; it does not install anything automatically."
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("commands",)
    FUNCTION = "commands"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "target_dir": ("STRING", {"default": str(Path.home() / "Bernini")}),
                "model_dir": ("STRING", {"default": str(Path.home() / "Bernini-R-Diffusers")}),
                "install_requirements": ("BOOLEAN", {"default": True}),
            }
        }

    def commands(self, target_dir, model_dir, install_requirements=True):
        target_dir = str(Path(target_dir).expanduser())
        model_dir = str(Path(model_dir).expanduser())
        lines = [
            "# Bernini-R setup commands (run in a Python 3.11 + CUDA 12.4 environment)",
            f"git clone https://github.com/bytedance/Bernini.git {_shell_quote(target_dir)}",
            f"cd {_shell_quote(target_dir)}",
        ]
        if install_requirements:
            lines.append("pip install -r requirements.txt")
        lines.extend([
            "pip install -U huggingface_hub",
            f"hf download ByteDance/Bernini-R-Diffusers --local-dir {_shell_quote(model_dir)}",
            "# Then set Bernini Model Config's bernini_repo_dir/config to those two paths.",
        ])
        return ("\n".join(lines),)


NODE_CLASS_MAPPINGS = {
    "BerniniModelConfig": BerniniModelConfig,
    "BerniniGenerationSettings": BerniniGenerationSettings,
    "BerniniCaseBuilder": BerniniCaseBuilder,
    "BerniniRunSingleGPU": BerniniRunSingleGPU,
    "LzitsBerniniConditioning": LzitsBerniniConditioning,
    "BerniniLoadOutputImage": BerniniLoadOutputImage,
    "BerniniSetupCommands": BerniniSetupCommands,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BerniniModelConfig": "Bernini Model Config",
    "BerniniGenerationSettings": "Bernini Generation Settings",
    "BerniniCaseBuilder": "Bernini Case Builder",
    "BerniniRunSingleGPU": "Bernini Run Single GPU",
    "LzitsBerniniConditioning": "Bernini Conditioning (Kijai Branch)",
    "BerniniLoadOutputImage": "Bernini Load Output Image",
    "BerniniSetupCommands": "Bernini Setup Commands",
}
