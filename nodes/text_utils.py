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
    """
    Picks a single item from a list of strings by index.

    Use it after your String Splitter (Batch), which returns a STRING with
    OUTPUT_IS_LIST = (True,). Because this node sets INPUT_IS_LIST = True,
    Comfy will pass the *entire* list of prompts into `items` in one call,
    instead of running the node once per element.
    """

    CATEGORY = "lzits nodes"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("item",)
    FUNCTION = "run"
    INPUT_IS_LIST = True  

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "items": (
                    "STRING",
                    {
                        "forceInput": True,  # connect from String Splitter output
                    },
                ),
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 999,
                        "step": 1,
                    },
                ),
            }
        }

    def run(self, items, index):
        # Here, `items` is guaranteed to be a *list* of strings.
        if not items:
            return ("",)

        # INPUT_IS_LIST = True affects ALL inputs, so index arrives as a list too
        # Handle nested lists and single values
        while isinstance(index, (list, tuple)) and len(index) > 0:
            index = index[0]
        
        if isinstance(index, (list, tuple)):
            index = 0

        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0

        # Clamp index to valid range
        index = max(0, min(index, len(items) - 1))

        return (items[index],)
