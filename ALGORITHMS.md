# OpenAI Image Generation Algorithms

This document describes the algorithms for preparing images for OpenAI's DALL-E API and processing the results.

## OpenAI API Constraints

The DALL-E API accepts three specific image dimensions:
- **Square**: 1024 � 1024
- **Landscape**: 1536 × 1024  
- **Portrait**: 1024 × 1536

When dimensions aren't specified, the API chooses based on input, making it difficult to match results back to the original image during inpainting.

## Current Implementation Status

###  Implemented
- Square context extraction (512�512, 768�768, or 1024�1024)
- Basic mask generation for selections
- Context padding calculation
- Extension beyond image boundaries

### L Not Implemented
- Non-square shape selection
- Smart boundary-aware padding
- Aspect ratio preservation
- Advanced mask feathering

## Core Algorithms

### 1. Optimal Shape Selection

Given an image dimension, return the best matching OpenAI shape.

```python
def get_optimal_openai_shape(width, height):
    """
    Select optimal OpenAI shape based on image dimensions.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        tuple: (target_width, target_height)
    """
    aspect_ratio = width / height
    
    if aspect_ratio > 1.3:
        # Landscape orientation
        return (1536, 1024)
    elif aspect_ratio < 0.77:
        # Portrait orientation  
        return (1024, 1536)
    else:
        # Square or near-square
        return (1024, 1024)
```

### 2. Image Padding to Match OpenAI Shape

Pad an image to match the target OpenAI dimensions while preserving content.

```python
def pad_image_to_shape(image, target_width, target_height):
    """
    Pad image to match OpenAI shape, centering the content.
    
    Args:
        image: Source image
        target_width: Target width (1024 or 1536)
        target_height: Target height (1024 or 1536)
        
    Returns:
        dict: {
            'padded_image': Padded image data,
            'padding': (left, top, right, bottom),
            'scale_factor': Applied scaling factor
        }
    """
    img_width = image.width
    img_height = image.height
    
    # Calculate scale to fit within target
    scale_x = target_width / img_width
    scale_y = target_height / img_height
    scale = min(scale_x, scale_y)
    
    # Scale image
    scaled_width = int(img_width * scale)
    scaled_height = int(img_height * scale)
    
    # Calculate padding to center
    pad_left = (target_width - scaled_width) // 2
    pad_top = (target_height - scaled_height) // 2
    pad_right = target_width - scaled_width - pad_left
    pad_bottom = target_height - scaled_height - pad_top
    
    return {
        'scale_factor': scale,
        'scaled_size': (scaled_width, scaled_height),
        'padding': (pad_left, pad_top, pad_right, pad_bottom)
    }
```

### 3. Context Extraction Around Selection

Extract a region around a selection with appropriate context for inpainting.

```python
def extract_context_with_selection(image, selection, mode='focused'):
    """
    Extract context region around selection for inpainting.
    
    Args:
        image: Source image dimensions (width, height)
        selection: Selection bounds (x1, y1, x2, y2)
        mode: 'focused' for partial extraction, 'full' for whole image
        
    Returns:
        dict: Context extraction parameters
    """
    img_width, img_height = image
    sel_x1, sel_y1, sel_x2, sel_y2 = selection
    sel_width = sel_x2 - sel_x1
    sel_height = sel_y2 - sel_y1
    
    if mode == 'full':
        # Send entire image with mask
        target_shape = get_optimal_openai_shape(img_width, img_height)
        return {
            'mode': 'full',
            'extract_region': (0, 0, img_width, img_height),
            'target_shape': target_shape,
            'needs_padding': True
        }
    
    # Focused mode: extract region around selection
    # Calculate context padding (30-50% of selection, min 50px, max 300px)
    context_pad = max(50, min(300, int(max(sel_width, sel_height) * 0.4)))
    
    # Initial context bounds
    ctx_x1 = sel_x1 - context_pad
    ctx_y1 = sel_y1 - context_pad
    ctx_x2 = sel_x2 + context_pad
    ctx_y2 = sel_y2 + context_pad
    
    # Smart boundary handling: prefer not to extend beyond image
    if ctx_x1 < 0:
        shift = -ctx_x1
        ctx_x1 = 0
        ctx_x2 = min(img_width, ctx_x2 + shift)
    if ctx_y1 < 0:
        shift = -ctx_y1
        ctx_y1 = 0
        ctx_y2 = min(img_height, ctx_y2 + shift)
    if ctx_x2 > img_width:
        shift = ctx_x2 - img_width
        ctx_x2 = img_width
        ctx_x1 = max(0, ctx_x1 - shift)
    if ctx_y2 > img_height:
        shift = ctx_y2 - img_height
        ctx_y2 = img_height
        ctx_y1 = max(0, ctx_y1 - shift)
    
    ctx_width = ctx_x2 - ctx_x1
    ctx_height = ctx_y2 - ctx_y1
    
    # Determine optimal shape for context
    target_shape = get_optimal_openai_shape(ctx_width, ctx_height)
    
    return {
        'mode': 'focused',
        'extract_region': (ctx_x1, ctx_y1, ctx_width, ctx_height),
        'selection_in_extract': (
            sel_x1 - ctx_x1,
            sel_y1 - ctx_y1,
            sel_x2 - ctx_x1,
            sel_y2 - ctx_y1
        ),
        'target_shape': target_shape,
        'needs_padding': ctx_width != target_shape[0] or ctx_height != target_shape[1]
    }
```

### 4. Mask Generation

Generate a mask for the selection area within the context.

```python
def generate_mask(context_info, feather_radius=10):
    """
    Generate mask for inpainting based on context extraction.
    
    Args:
        context_info: Context extraction info from extract_context_with_selection
        feather_radius: Pixels to feather the mask edges
        
    Returns:
        Binary mask array matching target_shape dimensions
    """
    target_width, target_height = context_info['target_shape']
    
    # Create black mask (areas to preserve)
    mask = create_black_image(target_width, target_height)
    
    if context_info['mode'] == 'full':
        # Full image mode: need to scale selection to target shape
        scale_x = target_width / context_info['extract_region'][2]
        scale_y = target_height / context_info['extract_region'][3]
        # ... scale and position selection
    else:
        # Focused mode: selection within extract region
        sel_in_extract = context_info['selection_in_extract']
        # Account for any padding/scaling to target shape
        # ... position selection in mask
    
    # Apply feathering for smooth blending
    if feather_radius > 0:
        mask = apply_gaussian_blur(mask, feather_radius)
    
    return mask
```

### 5. Result Scaling and Placement

Scale the AI-generated result back and place it correctly in the original image.

```python
def place_result_in_image(result, original_image, context_info):
    """
    Place AI result back into original image at correct position.
    
    Args:
        result: AI-generated image at target_shape dimensions
        original_image: Original image to composite onto
        context_info: Context extraction info used for generation
        
    Returns:
        dict: Placement parameters
    """
    if context_info['mode'] == 'full':
        # Full image mode: scale entire result to original size
        scale_x = original_image.width / result.width
        scale_y = original_image.height / result.height
        
        return {
            'placement_mode': 'replace',
            'scale': (scale_x, scale_y),
            'position': (0, 0)
        }
    else:
        # Focused mode: scale and position extract region
        extract_region = context_info['extract_region']
        target_shape = context_info['target_shape']
        
        # Calculate scale from result back to extract size
        scale_x = extract_region[2] / target_shape[0]
        scale_y = extract_region[3] / target_shape[1]
        
        return {
            'placement_mode': 'composite',
            'scale': (scale_x, scale_y),
            'position': (extract_region[0], extract_region[1]),
            'blend_mode': 'normal'
        }
```

### 6. Layer Mask Generation for Partial Inpainting

When placing a partial inpaint result, generate a layer mask to blend only the modified areas.

```python
def generate_layer_mask(context_info, selection_mask):
    """
    Generate layer mask for blending partial inpaint results.
    
    Args:
        context_info: Context extraction info
        selection_mask: Original selection as binary mask
        
    Returns:
        Layer mask for compositing
    """
    if context_info['mode'] == 'full':
        # Use selection mask directly, scaled to image size
        return scale_mask(selection_mask, context_info['original_size'])
    else:
        # Create mask for just the extracted region
        extract_region = context_info['extract_region']
        layer_mask = create_transparent_mask(original_size)
        
        # Fill only the extract region area
        place_mask_region(
            layer_mask,
            selection_mask,
            position=extract_region[:2],
            size=extract_region[2:]
        )
        
        return layer_mask
```

## Implementation Notes

### Current Limitations

1. **Square-only extraction**: Current implementation only works with square extracts (512�512, 768�768, 1024�1024)
2. **Boundary extension**: Extends beyond image boundaries, creating artificial context
3. **No aspect ratio preservation**: Forces everything to squares, causing distortion

### Recommended Improvements

1. **Smart Shape Selection**
   - Analyze image/selection aspect ratio
   - Choose optimal OpenAI shape (square/landscape/portrait)
   - Minimize padding and scaling

2. **Boundary-Aware Context**
   - Prefer shifting context window over extending beyond image
   - Only extend beyond boundaries when selection is at edge
   - Use image content for padding when possible

3. **Progressive Mask Feathering**
   - Variable feather radius based on selection size
   - Directional feathering for edge selections
   - Preserve hard edges where appropriate

4. **Multi-Resolution Support**
   - Handle images larger than OpenAI max dimensions
   - Tile-based processing for very large images
   - Smart downsampling for quality preservation

## Usage Examples

### Example 1: Generate New Layer
```python
# No selection, generate at closest shape to image
image_dims = (1920, 1080)  # Landscape image
target_shape = get_optimal_openai_shape(*image_dims)  # Returns (1536, 1024)
padded = pad_image_to_shape(image, *target_shape)
# Send to OpenAI...
```

### Example 2: Focused Inpainting
```python
# Inpaint a selection with context
selection = (500, 300, 700, 500)  # 200�200 selection
context = extract_context_with_selection(
    image=(1920, 1080),
    selection=selection,
    mode='focused'
)
mask = generate_mask(context)
# Send context extract and mask to OpenAI...
result_placement = place_result_in_image(result, original, context)
```

### Example 3: Full Image Inpainting
```python
# Send entire image but only modify selection
context = extract_context_with_selection(
    image=(1920, 1080),
    selection=(500, 300, 700, 500),
    mode='full'
)
# Scales full image to optimal shape with selection mask
```

## Testing Considerations

Key properties to verify:
1. Context always contains full selection
2. Masks align correctly with selections after scaling
3. Results place back at exact selection position
4. No data loss during scale up/down cycles
5. Padding is symmetric and reversible