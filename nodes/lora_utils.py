# File: lora_utils.py
# Multi-Output LoRA Selector Node for ComfyUI

import folder_paths
import comfy.utils
import comfy.lora


class LoRASelectorMulti:
    """
    A LoRA selector node that outputs 7 MODEL outputs, each with the same LoRA
    applied at different strengths. This allows you to select a LoRA once and
    connect it to multiple KSamplers with different strength settings.
    
    Usage:
    1. Connect your base MODEL to the input
    2. Select a LoRA from the dropdown
    3. Adjust the strength for each output as needed
    4. Connect each MODEL output to different KSamplers
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": (folder_paths.get_filename_list("loras"),),
                "strength_1": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_2": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_3": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_4": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_5": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_6": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "strength_7": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MODEL", "MODEL", "MODEL", "MODEL", "MODEL", "MODEL", "MODEL")
    RETURN_NAMES = ("MODEL_1", "MODEL_2", "MODEL_3", "MODEL_4", "MODEL_5", "MODEL_6", "MODEL_7")
    FUNCTION = "apply_lora"
    CATEGORY = "lzits nodes"

    def apply_lora(self, model, lora_name, strength_1, strength_2, strength_3, strength_4, strength_5, strength_6, strength_7):
        # Get the full path to the LoRA file
        lora_path = folder_paths.get_full_path("loras", lora_name)
        
        # Load the LoRA file once
        lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
        
        # Collect all strengths
        strengths = [strength_1, strength_2, strength_3, strength_4, strength_5, strength_6, strength_7]
        
        # Apply LoRA at each strength level
        output_models = []
        for strength in strengths:
            if strength == 0:
                # If strength is 0, just use the original model (no LoRA effect)
                output_models.append(model)
            else:
                # Apply LoRA to model only (no CLIP)
                # load_lora_for_models returns (model_lora, clip_lora)
                model_lora, _ = comfy.lora.load_lora_for_models(model, None, lora, strength, 0)
                output_models.append(model_lora)
        
        return tuple(output_models)
