import numpy as np
import torch
from PIL import Image, ImageDraw


class PrepareObjectMove:
    """
    Draw a red bounding box (source) and a green bounding box (target) on the
    input image to produce the conditioning image expected by the object-move LoRA.

    Wire ObjectSelector's x1/y1/x2/y2 outputs into the source inputs.
    Set the target inputs manually to define where the object should land.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("conditioned_image",)
    FUNCTION = "prepare"

    @classmethod
    def INPUT_TYPES(cls):
        _coord = lambda default: ("INT", {"default": default, "min": 0, "max": 8192, "step": 1})
        return {
            "required": {
                "image": ("IMAGE",),
                # Source box — wire from ObjectSelector
                "source_x1": _coord(0),
                "source_y1": _coord(0),
                "source_x2": _coord(100),
                "source_y2": _coord(100),
                # Target box — where the object should be moved to
                "target_x1": _coord(200),
                "target_y1": _coord(200),
                "target_x2": _coord(300),
                "target_y2": _coord(300),
                "line_width": ("INT", {"default": 3, "min": 1, "max": 20, "step": 1}),
            }
        }

    def prepare(
        self,
        image,
        source_x1, source_y1, source_x2, source_y2,
        target_x1, target_y1, target_x2, target_y2,
        line_width,
    ):
        results = []
        for img_tensor in image:
            arr = (img_tensor.numpy() * 255.0).clip(0, 255).astype(np.uint8)
            pil_img = Image.fromarray(arr, mode="RGB")
            draw = ImageDraw.Draw(pil_img)

            # Red = source (object's current location)
            draw.rectangle(
                [source_x1, source_y1, source_x2, source_y2],
                outline=(255, 0, 0),
                width=line_width,
            )
            # Green = target (where object should go)
            draw.rectangle(
                [target_x1, target_y1, target_x2, target_y2],
                outline=(0, 255, 0),
                width=line_width,
            )

            out_arr = np.array(pil_img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(out_arr))

        return (torch.stack(results),)
