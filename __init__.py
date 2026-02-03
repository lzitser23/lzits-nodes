# File: __init__.py

# 1. Import the new classes
from .nodes.text_utils import SimpleTextSplitter, SimpleTextAppender, SimpleTextPrepender, IndexPicker
from .nodes.lora_utils import LoRASelectorMulti

# 2. Add to Class Mappings
NODE_CLASS_MAPPINGS = {
    "SimpleTextSplitter": SimpleTextSplitter,
    "SimpleTextAppender": SimpleTextAppender,
    "SimpleTextPrepender": SimpleTextPrepender,
    "IndexPicker": IndexPicker,
    "LoRASelectorMulti": LoRASelectorMulti,
}

# 3. Add to Display Name Mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleTextSplitter": "String Splitter",
    "SimpleTextAppender": "String Appender (Suffix)",
    "SimpleTextPrepender": "String Prepender (Prefix)",
    "IndexPicker": "Index Picker",
    "LoRASelectorMulti": "LoRA Selector Multi-Output",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']