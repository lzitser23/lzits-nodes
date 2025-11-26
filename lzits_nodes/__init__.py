# File: __init__.py

# 1. Import the new class
from .text_utils import SimpleTextSplitter, SimpleTextAppender, SimpleTextPrepender, IndexPicker

# 2. Add to Class Mappings
NODE_CLASS_MAPPINGS = {
    "SimpleTextSplitter": SimpleTextSplitter,
    "SimpleTextAppender": SimpleTextAppender,
    "SimpleTextPrepender": SimpleTextPrepender, 
    "IndexPicker": IndexPicker,
}

# 3. Add to Display Name Mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleTextSplitter": "String Splitter (Batch)",
    "SimpleTextAppender": "String Appender (Suffix)",
    "SimpleTextPrepender": "String Prepender (Prefix)", 
    "IndexPicker": "Index Picker (lzits)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']