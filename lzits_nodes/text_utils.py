# File: text_utils.py

class SimpleTextSplitter:
    
    # Splits a string into a list. Useful for batch processing.
    # Input: "A cat, A dog" -> Output: Batch of 2 prompts
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "delimiter": ("STRING", {"default": ","}),
            }
        }

    RETURN_TYPES = ("STRING",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "run"
    CATEGORY = "lzits nodes"

    def run(self, text, delimiter):
        if delimiter == "\\n":
            delimiter = "\n"
            
        if not delimiter:
            return ([text],)

        split_results = [x.strip() for x in text.split(delimiter) if x.strip()]
        return (split_results,)


class SimpleTextAppender:
    
    # Appends a fixed suffix/text to an input string.
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_text": ("STRING", {"forceInput": True}),
                "separator": ("STRING", {"default": " "}),
                "text_to_append": ("STRING", {"multiline": False, "default": ""}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "lzits nodes"

    def run(self, input_text, separator, text_to_append):
        if separator == "\\n":
            separator = "\n"
        
        result = f"{input_text}{separator}{text_to_append}"
        return (result,)
        
class SimpleTextPrepender:
    
   # Adds text to the START (Prefix). Good for LoRA Triggers.
   # Result: "Text to Prepend" + "Separator" + "Input Text"
   
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_text": ("STRING", {"forceInput": True}),
                "separator": ("STRING", {"default": ", "}),
                "text_to_prepend": ("STRING", {"multiline": False, "default": ""}), 
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = "lzits nodes"

    def run(self, input_text, separator, text_to_prepend):
        if separator == "\\n":
            separator = "\n"
        # The logic is reversed here: Prepend + Separator + Input
        result = f"{text_to_prepend}{separator}{input_text}"
        return (result,)
    
    
class IndexPicker:
    
    # Picks a single item from a list of strings by index.

    # If `items` is:
    # - a list: we index into it
    # - a single string: we just pass it through
    

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("item",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # We want this to accept the WHOLE list from a batched output.

                "items": ("STRING", {
                    "forceInput": True,
                }),
                "index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 999,
                    "step": 1
                }),
            }
        }

    def run(self, items, index):
        # make sure index is int
        try:
            index = int(index)
        except Exception:
            index = 0

        # CASE 1: we truly got a list (what we want)
        if isinstance(items, list):
            if not items:
                return ("",)

            if index < 0:
                index = 0
            if index >= len(items):
                index = len(items) - 1

            return (items[index],)

        # CASE 2: items is actually a single string (because Comfy unrolled the batch)
        # In that case, just pass it through so you don't end up indexing characters.
        return (items,)
