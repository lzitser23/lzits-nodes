# lzits-nodes
A collection of custom nodes for Comfyui

## Overview

This repository contains a small set of quality-of-life text utility nodes for ComfyUI, designed to make prompt and string manipulation easier inside your workflows. The nodes focus on simple, predictable behavior so you can chain them together for tasks like building prompt batches, adding trigger phrases, or composing structured text for different models.

All nodes appear under the `lzits nodes` category in the ComfyUI node browser.

## Nodes

### SimpleTextSplitter

**Purpose:**  
Split a single text block into multiple strings for batch processing.

**How it works:**

- Takes an input `text` (multiline supported) and a `delimiter`.
- If the delimiter is set to `\n`, it is treated as a real newline, allowing you to split by lines.
- If the delimiter is empty, the node returns the original text as a single item.
- Leading and trailing whitespace around each split part is stripped.
- Empty results are discarded.

**Typical use cases:**

- Turning a comma-separated list into a batch of prompts.
- Splitting a long list of phrases (each on its own line) into individual prompts for batched generation.
- Preparing multiple variations of text to feed into downstream nodes in one go.

### SimpleTextAppender

**Purpose:**  
Append a fixed piece of text (suffix) to an existing string.

**How it works:**

- Takes `input_text`, a `separator`, and `text_to_append`.
- If the separator is set to `\n`, it is converted to a newline character.
- Produces: `input_text + separator + text_to_append`.

**Typical use cases:**

- Adding a consistent ending phrase to prompts.
- Appending style tags, camera settings, or negative prompt hints.
- Combining a base prompt with a dynamic suffix in a clean and reusable way.

### SimpleTextPrepender

**Purpose:**  
Prepend text to the start of an existing string (prefix), useful for LoRA trigger tokens or fixed prompt headers.

**How it works:**

- Takes `input_text`, a `separator`, and `text_to_prepend`.
- If the separator is set to `\n`, it is converted to a newline.
- Produces: `text_to_prepend + separator + input_text`.

**Typical use cases:**

- Adding LoRA trigger tokens before an existing prompt.
- Prepending prefixes like “mxviv,” or style tags to prompts generated elsewhere in your workflow.
- Creating consistent structured prompts where a fixed header always comes first.
