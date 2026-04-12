import numpy as np
import torch
from PIL import Image, ImageDraw


class DrawBoundingBox:
    """
    Draw a colored bounding box on an image tensor.
    Accepts pixel coordinates (x1, y1) top-left and (x2, y2) bottom-right.
    Chain multiple nodes to draw several boxes on the same image.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "draw_box"

    _COLOR_MAP = {
        "red": (255, 0, 0),
        "green": (0, 255, 0),
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "x1": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "y1": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "x2": ("INT", {"default": 100, "min": 0, "max": 8192, "step": 1}),
                "y2": ("INT", {"default": 100, "min": 0, "max": 8192, "step": 1}),
                "color": (list(cls._COLOR_MAP.keys()),),
                "line_width": ("INT", {"default": 2, "min": 1, "max": 50, "step": 1}),
            }
        }

    def draw_box(self, image, x1, y1, x2, y2, color, line_width):
        rgb = self._COLOR_MAP[color]
        results = []

        for img_tensor in image:  # iterate over batch dimension
            arr = (img_tensor.numpy() * 255.0).clip(0, 255).astype(np.uint8)
            pil_img = Image.fromarray(arr, mode="RGB")

            draw = ImageDraw.Draw(pil_img)
            draw.rectangle([x1, y1, x2, y2], outline=rgb, width=line_width)

            out_arr = np.array(pil_img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(out_arr))

        return (torch.stack(results),)
