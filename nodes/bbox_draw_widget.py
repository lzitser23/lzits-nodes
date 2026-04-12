import numpy as np
import torch
from PIL import Image, ImageDraw


class BBoxDrawWidget:
    """
    Interactive bounding box drawing node.
    The in-node canvas shows the input image as a background.
    Drag to draw a red (source) box and a green (target) box.
    Outputs the conditioned image (with boxes drawn) for the object-move LoRA,
    plus the clean original image which the frontend uses as the canvas background.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("conditioned_image", "source_image")
    FUNCTION = "apply_boxes"

    @classmethod
    def INPUT_TYPES(cls):
        c = lambda d: ("INT", {"default": d, "min": 0, "max": 8192, "step": 1})
        return {
            "required": {
                "image": ("IMAGE",),
                "source_x1": c(0),
                "source_y1": c(0),
                "source_x2": c(0),
                "source_y2": c(0),
                "target_x1": c(0),
                "target_y1": c(0),
                "target_x2": c(0),
                "target_y2": c(0),
                "line_width": ("INT", {"default": 3, "min": 1, "max": 20, "step": 1}),
            }
        }

    def apply_boxes(
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

            if source_x2 > source_x1 and source_y2 > source_y1:
                draw.rectangle(
                    [source_x1, source_y1, source_x2, source_y2],
                    outline=(255, 0, 0),
                    width=line_width,
                )
            if target_x2 > target_x1 and target_y2 > target_y1:
                draw.rectangle(
                    [target_x1, target_y1, target_x2, target_y2],
                    outline=(0, 255, 0),
                    width=line_width,
                )

            out_arr = np.array(pil_img).astype(np.float32) / 255.0
            results.append(torch.from_numpy(out_arr))

        # Second output is the clean passthrough — used by the JS canvas as background.
        return (torch.stack(results), image)
