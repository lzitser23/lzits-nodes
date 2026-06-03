# File: __init__.py

# 1. Import the new classes
from .nodes.text_utils import SimpleTextSplitter, SimpleTextAppender, SimpleTextPrepender, IndexPicker
from .nodes.lora_utils import LoRASelectorMulti
from .nodes.image_outpaint_color import ImageOutpaintColorCanvas
from .nodes.yolo_get_boxes import YOLOGetBoxes, ObjectSelector
from .nodes.bbox_draw_widget import BBoxDrawWidget
from .nodes.bernini_runner import (
    BerniniModelConfig,
    BerniniGenerationSettings,
    BerniniCaseBuilder,
    BerniniRunSingleGPU,
    LzitsBerniniConditioning,
    BerniniLoadOutputImage,
    BerniniSetupCommands,
)

# 2. Add to Class Mappings
NODE_CLASS_MAPPINGS = {
    "SimpleTextSplitter": SimpleTextSplitter,
    "SimpleTextAppender": SimpleTextAppender,
    "SimpleTextPrepender": SimpleTextPrepender,
    "IndexPicker": IndexPicker,
    "LoRASelectorMulti": LoRASelectorMulti,
    "ImageOutpaintColorCanvas": ImageOutpaintColorCanvas,
    "YOLOGetBoxes": YOLOGetBoxes,
    "ObjectSelector": ObjectSelector,
    "BBoxDrawWidget": BBoxDrawWidget,
    "BerniniModelConfig": BerniniModelConfig,
    "BerniniGenerationSettings": BerniniGenerationSettings,
    "BerniniCaseBuilder": BerniniCaseBuilder,
    "BerniniRunSingleGPU": BerniniRunSingleGPU,
    "LzitsBerniniConditioning": LzitsBerniniConditioning,
    "BerniniLoadOutputImage": BerniniLoadOutputImage,
    "BerniniSetupCommands": BerniniSetupCommands,
}

# 3. Add to Display Name Mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleTextSplitter": "String Splitter",
    "SimpleTextAppender": "String Appender (Suffix)",
    "SimpleTextPrepender": "String Prepender (Prefix)",
    "IndexPicker": "Index Picker",
    "LoRASelectorMulti": "LoRA Selector Multi-Output",
    "ImageOutpaintColorCanvas": "Image Outpaint (Color Canvas)",
    "YOLOGetBoxes": "YOLO Get Boxes",
    "ObjectSelector": "Object Selector",
    "BBoxDrawWidget": "Bounding Box Draw",
    "BerniniModelConfig": "Bernini Model Config",
    "BerniniGenerationSettings": "Bernini Generation Settings",
    "BerniniCaseBuilder": "Bernini Case Builder",
    "BerniniRunSingleGPU": "Bernini Run Single GPU",
    "LzitsBerniniConditioning": "Bernini Conditioning (Kijai Branch)",
    "BerniniLoadOutputImage": "Bernini Load Output Image",
    "BerniniSetupCommands": "Bernini Setup Commands",
}

WEB_DIRECTORY = "./web"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
