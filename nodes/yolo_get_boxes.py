import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

_ultralytics_error = None
try:
    from ultralytics import YOLO as _YOLO
except ImportError as exc:
    _ultralytics_error = exc
    _YOLO = None

_model_cache: dict = {}

_MODELS = [
    "yolov8n.pt",
    "yolov8s.pt",
    "yolov8m.pt",
    "yolov8l.pt",
    "yolov8x.pt",
]


def _get_model(model_name: str):
    if _YOLO is None:
        raise RuntimeError(
            "ultralytics is not installed. Run: pip install ultralytics"
        ) from _ultralytics_error
    if model_name not in _model_cache:
        _model_cache[model_name] = _YOLO(model_name)
    return _model_cache[model_name]


class YOLOGetBoxes:
    """
    Run YOLO detection and output structured detection data (YOLO_DETECTIONS).
    Also outputs a yellow-box preview image so you can see what was found
    before wiring into ObjectSelector.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("YOLO_DETECTIONS", "IMAGE")
    RETURN_NAMES = ("detections", "preview")
    FUNCTION = "get_boxes"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model": (_MODELS,),
                "conf_threshold": (
                    "FLOAT",
                    {"default": 0.25, "min": 0.01, "max": 1.0, "step": 0.01},
                ),
            }
        }

    def get_boxes(self, image, model, conf_threshold):
        yolo = _get_model(model)

        try:
            font = ImageFont.truetype("arial.ttf", size=14)
        except (IOError, OSError):
            font = ImageFont.load_default()

        # Run detection on the first image in the batch.
        arr = (image[0].numpy() * 255.0).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(arr, mode="RGB")
        raw = yolo(pil_img, conf=conf_threshold, verbose=False)[0]

        detections = []
        for box in raw.boxes:
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            conf = float(box.conf[0])
            label = raw.names[int(box.cls[0])]
            detections.append({"label": label, "conf": conf, "x1": x1, "y1": y1, "x2": x2, "y2": y2})

        # Build preview with yellow boxes so the user knows what labels to use.
        preview = pil_img.copy()
        draw = ImageDraw.Draw(preview)
        for det in detections:
            draw.rectangle(
                [det["x1"], det["y1"], det["x2"], det["y2"]],
                outline=(255, 255, 0),
                width=2,
            )
            text = f"{det['label']} {det['conf']:.2f}"
            tb = draw.textbbox((det["x1"], det["y1"]), text, font=font)
            draw.rectangle([tb[0] - 2, tb[1] - 2, tb[2] + 2, tb[3] + 2], fill=(255, 255, 0))
            draw.text((det["x1"], det["y1"]), text, fill=(0, 0, 0), font=font)

        preview_arr = np.array(preview).astype(np.float32) / 255.0
        preview_tensor = torch.from_numpy(preview_arr).unsqueeze(0)

        return (detections, preview_tensor)


class ObjectSelector:
    """
    Pick a detected object by label name from a YOLO_DETECTIONS list.
    Returns the bounding box of the highest-confidence match.
    Wire the four INT outputs into PrepareObjectMove as the source box.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING", "FLOAT")
    RETURN_NAMES = ("x1", "y1", "x2", "y2", "label", "confidence")
    FUNCTION = "select_object"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "detections": ("YOLO_DETECTIONS",),
                "label": ("STRING", {"default": "person"}),
            }
        }

    def select_object(self, detections, label):
        label_lower = label.strip().lower()
        matches = [d for d in detections if d["label"].lower() == label_lower]

        if not matches:
            available = sorted(set(d["label"] for d in detections))
            raise ValueError(
                f"No detection found for label '{label}'. "
                f"Available labels: {available}"
            )

        best = max(matches, key=lambda d: d["conf"])
        return (best["x1"], best["y1"], best["x2"], best["y2"], best["label"], best["conf"])
