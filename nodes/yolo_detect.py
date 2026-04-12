import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

# Ultralytics is loaded lazily so ComfyUI still starts if it isn't installed yet.
_ultralytics_error = None
try:
    from ultralytics import YOLO as _YOLO
except ImportError as exc:
    _ultralytics_error = exc
    _YOLO = None

# Module-level model cache so weights aren't reloaded on every run.
_model_cache: dict = {}


def _get_model(model_name: str):
    if _YOLO is None:
        raise RuntimeError(
            "ultralytics is not installed. Run: pip install ultralytics"
        ) from _ultralytics_error
    if model_name not in _model_cache:
        _model_cache[model_name] = _YOLO(model_name)
    return _model_cache[model_name]


class YOLODetectDraw:
    """
    Run YOLO object detection on an image and draw bounding boxes.
    Boxes are drawn green when confidence >= high_conf_threshold, red otherwise.
    Labels show class name and confidence score.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "detect_and_draw"

    _MODELS = [
        "yolov8n.pt",
        "yolov8s.pt",
        "yolov8m.pt",
        "yolov8l.pt",
        "yolov8x.pt",
    ]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": (cls._MODELS,),
                "conf_threshold": (
                    "FLOAT",
                    {"default": 0.25, "min": 0.01, "max": 1.0, "step": 0.01},
                ),
                "high_conf_threshold": (
                    "FLOAT",
                    {"default": 0.6, "min": 0.01, "max": 1.0, "step": 0.01},
                ),
                "line_width": ("INT", {"default": 2, "min": 1, "max": 20, "step": 1}),
                "show_labels": ("BOOLEAN", {"default": True}),
            }
        }

    def detect_and_draw(
        self,
        image,
        model,
        conf_threshold,
        high_conf_threshold,
        line_width,
        show_labels,
    ):
        yolo = _get_model(model)

        # Try to load a font; fall back to PIL default if not available.
        try:
            font = ImageFont.truetype("arial.ttf", size=14)
        except (IOError, OSError):
            font = ImageFont.load_default()

        results = []
        for img_tensor in image:
            arr = (img_tensor.numpy() * 255.0).clip(0, 255).astype(np.uint8)
            pil_img = Image.fromarray(arr, mode="RGB")

            detections = yolo(pil_img, conf=conf_threshold, verbose=False)[0]

            draw = ImageDraw.Draw(pil_img)
            for box in detections.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = detections.names[cls_id]

                color = (0, 255, 0) if conf >= high_conf_threshold else (255, 0, 0)

                draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)

                if show_labels:
                    text = f"{label} {conf:.2f}"
                    # Draw a small filled background behind the text for readability.
                    bbox = draw.textbbox((x1, y1), text, font=font)
                    draw.rectangle(
                        [bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2],
                        fill=color,
                    )
                    draw.text((x1, y1), text, fill=(0, 0, 0), font=font)

            out_arr = np.array(pil_img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(out_arr))

        return (torch.stack(results),)
