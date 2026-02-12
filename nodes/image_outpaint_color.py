import hashlib
import os

import folder_paths
import numpy as np
import torch
from PIL import Image, ImageOps


class ImageOutpaintColorCanvas:
    """
    Load an image, expand its canvas without scaling the original image,
    and fill the new areas with a user-selected solid color.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "outpaint_mask")
    FUNCTION = "expand_canvas"

    @classmethod
    def INPUT_TYPES(cls):
        input_dir = folder_paths.get_input_directory()
        files = [
            f
            for f in os.listdir(input_dir)
            if os.path.isfile(os.path.join(input_dir, f))
        ]

        return {
            "required": {
                "image": (sorted(files), {"image_upload": True}),
                "expand_left": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "expand_right": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "expand_top": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "expand_bottom": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "background_color": ("STRING", {"default": "#ffffff"}),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, image, **kwargs):
        if not folder_paths.exists_annotated_filepath(image):
            return f"Invalid image file: {image}"

        try:
            cls._parse_color(kwargs.get("background_color", "#ffffff"))
        except ValueError as exc:
            return str(exc)

        return True

    @classmethod
    def IS_CHANGED(cls, image, **kwargs):
        image_path = folder_paths.get_annotated_filepath(image)
        hasher = hashlib.sha256()
        with open(image_path, "rb") as handle:
            hasher.update(handle.read())

        # Include widget values so graph caching invalidates when they change.
        hasher.update(str(kwargs.get("expand_left", 0)).encode("utf-8"))
        hasher.update(str(kwargs.get("expand_right", 0)).encode("utf-8"))
        hasher.update(str(kwargs.get("expand_top", 0)).encode("utf-8"))
        hasher.update(str(kwargs.get("expand_bottom", 0)).encode("utf-8"))
        hasher.update(str(kwargs.get("background_color", "#ffffff")).encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _parse_color(color_text):
        value = color_text.strip()
        if not value:
            raise ValueError("background_color cannot be empty.")

        named_colors = {
            "black": (0, 0, 0),
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "gray": (128, 128, 128),
            "grey": (128, 128, 128),
        }

        lower_value = value.lower()
        if lower_value in named_colors:
            r, g, b = named_colors[lower_value]
            return (r / 255.0, g / 255.0, b / 255.0)

        if value.startswith("#"):
            hex_value = value[1:]
            if len(hex_value) == 3:
                hex_value = "".join(ch * 2 for ch in hex_value)
            if len(hex_value) != 6:
                raise ValueError(
                    "background_color must be #RGB, #RRGGBB, 'r,g,b', or a basic color name."
                )
            try:
                r = int(hex_value[0:2], 16)
                g = int(hex_value[2:4], 16)
                b = int(hex_value[4:6], 16)
            except ValueError as exc:
                raise ValueError("background_color has invalid hex digits.") from exc
            return (r / 255.0, g / 255.0, b / 255.0)

        if "," in value:
            parts = [p.strip() for p in value.split(",")]
            if len(parts) != 3:
                raise ValueError("background_color 'r,g,b' format needs exactly 3 values.")
            try:
                channels = [float(p) for p in parts]
            except ValueError as exc:
                raise ValueError("background_color RGB values must be numbers.") from exc

            if all(0.0 <= c <= 1.0 for c in channels):
                return tuple(channels)
            if all(0.0 <= c <= 255.0 for c in channels):
                return tuple(c / 255.0 for c in channels)
            raise ValueError("background_color RGB values must be in range 0-1 or 0-255.")

        raise ValueError(
            "Unsupported background_color format. Use #RRGGBB, #RGB, r,g,b, or a basic color name."
        )

    @staticmethod
    def _load_image_as_tensor(image_name):
        image_path = folder_paths.get_annotated_filepath(image_name)
        image = Image.open(image_path)
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")

        array = np.array(image).astype(np.float32) / 255.0
        return torch.from_numpy(array).unsqueeze(0)

    def expand_canvas(
        self,
        image,
        expand_left,
        expand_right,
        expand_top,
        expand_bottom,
        background_color,
    ):
        source = self._load_image_as_tensor(image)
        color_rgb = self._parse_color(background_color)

        _, source_h, source_w, _ = source.shape
        out_h = source_h + expand_top + expand_bottom
        out_w = source_w + expand_left + expand_right

        fill = torch.tensor(color_rgb, dtype=source.dtype).view(1, 1, 1, 3)
        out_image = fill.repeat(1, out_h, out_w, 1)

        y1 = expand_top
        y2 = expand_top + source_h
        x1 = expand_left
        x2 = expand_left + source_w
        out_image[:, y1:y2, x1:x2, :] = source

        # 1.0 marks new outpaint area, 0.0 marks original image area.
        out_mask = torch.ones((out_h, out_w), dtype=source.dtype)
        out_mask[y1:y2, x1:x2] = 0.0

        return (out_image, out_mask)
