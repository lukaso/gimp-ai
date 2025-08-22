"""
Pure coordinate transformation utilities for GIMP AI Plugin.

These functions contain no GIMP dependencies and can be unit tested independently.
All coordinate calculations for context extraction, masking, and placement are here.
"""


def get_optimal_openai_shape(width, height):
    """
    Select optimal OpenAI shape based on image dimensions.
    
    Args:
        width: Image width in pixels
        height: Image height in pixels
        
    Returns:
        tuple: (target_width, target_height) - one of (1024, 1024), (1536, 1024), (1024, 1536)
    """
    if width <= 0 or height <= 0:
        return (1024, 1024)  # Default to square for invalid dimensions
        
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


def calculate_padding_for_shape(current_width, current_height, target_width, target_height):
    """
    Calculate padding needed to fit content into target OpenAI shape.
    
    Args:
        current_width: Current content width
        current_height: Current content height
        target_width: Target width (1024 or 1536)
        target_height: Target height (1024 or 1536)
        
    Returns:
        dict: {
            'scale_factor': Applied scaling factor,
            'scaled_size': (scaled_width, scaled_height),
            'padding': (left, top, right, bottom)
        }
    """
    # Calculate scale to fit within target
    scale_x = target_width / current_width
    scale_y = target_height / current_height
    scale = min(scale_x, scale_y)
    
    # Scale dimensions
    scaled_width = int(current_width * scale)
    scaled_height = int(current_height * scale)
    
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


def extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2, 
                                  mode='focused', has_selection=True):
    """
    Extract context region around selection for inpainting with optimal shape.
    
    Args:
        img_width: Source image width
        img_height: Source image height
        sel_x1, sel_y1, sel_x2, sel_y2: Selection bounds
        mode: 'focused' for partial extraction, 'full' for whole image
        has_selection: Whether there's an active selection
        
    Returns:
        dict: Context extraction parameters with optimal shape
    """
    if not has_selection:
        # No selection - use center area
        target_shape = get_optimal_openai_shape(img_width, img_height)
        # Create a default selection in center
        size = min(img_width, img_height, 512)
        sel_x1 = (img_width - size) // 2
        sel_y1 = (img_height - size) // 2
        sel_x2 = sel_x1 + size
        sel_y2 = sel_y1 + size
        
    sel_width = sel_x2 - sel_x1
    sel_height = sel_y2 - sel_y1
    
    if mode == 'full':
        # Send entire image with mask
        target_shape = get_optimal_openai_shape(img_width, img_height)
        padding_info = calculate_padding_for_shape(img_width, img_height, 
                                                  target_shape[0], target_shape[1])
        return {
            'mode': 'full',
            'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
            'extract_region': (0, 0, img_width, img_height),
            'target_shape': target_shape,
            'needs_padding': True,
            'padding_info': padding_info,
            'has_selection': has_selection
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
    padding_info = calculate_padding_for_shape(ctx_width, ctx_height,
                                              target_shape[0], target_shape[1])
    
    return {
        'mode': 'focused',
        'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
        'extract_region': (ctx_x1, ctx_y1, ctx_width, ctx_height),
        'selection_in_extract': (
            sel_x1 - ctx_x1,
            sel_y1 - ctx_y1,
            sel_x2 - ctx_x1,
            sel_y2 - ctx_y1
        ),
        'target_shape': target_shape,
        'needs_padding': ctx_width != target_shape[0] or ctx_height != target_shape[1],
        'padding_info': padding_info,
        'has_selection': has_selection
    }


def calculate_result_placement(result_shape, original_shape, context_info):
    """
    Calculate placement for AI result back into original image.
    
    Args:
        result_shape: (width, height) of AI result
        original_shape: (width, height) of original image
        context_info: Context extraction info used for generation
        
    Returns:
        dict: Placement parameters
    """
    if context_info['mode'] == 'full':
        # Full image mode: scale entire result to original size
        scale_x = original_shape[0] / result_shape[0]
        scale_y = original_shape[1] / result_shape[1]
        
        return {
            'placement_mode': 'replace',
            'scale': (scale_x, scale_y),
            'position': (0, 0),
            'size': original_shape
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
            'size': (extract_region[2], extract_region[3])
        }


def calculate_scale_from_shape(source_shape, target_shape):
    """
    Calculate scaling factors between two shapes.
    
    Args:
        source_shape: (width, height) tuple
        target_shape: (width, height) tuple
        
    Returns:
        dict: {
            'scale_x': Horizontal scale factor,
            'scale_y': Vertical scale factor,
            'uniform_scale': Min of scale_x and scale_y (preserves aspect ratio)
        }
    """
    scale_x = target_shape[0] / source_shape[0] if source_shape[0] > 0 else 1.0
    scale_y = target_shape[1] / source_shape[1] if source_shape[1] > 0 else 1.0
    
    return {
        'scale_x': scale_x,
        'scale_y': scale_y,
        'uniform_scale': min(scale_x, scale_y)
    }


def calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2, has_selection=True):
    """
    Calculate context square extraction parameters for a selection.
    
    Args:
        img_width: Width of the original image
        img_height: Height of the original image  
        sel_x1, sel_y1, sel_x2, sel_y2: Selection bounds
        has_selection: Whether there's an active selection
        
    Returns:
        dict with context extraction parameters
    """
    if not has_selection:
        # Default to center area if no selection
        size = min(img_width, img_height, 512)
        x = (img_width - size) // 2
        y = (img_height - size) // 2
        return {
            'selection_bounds': (x, y, x + size, y + size),
            'context_square': (x, y, size, size),
            'extract_region': (x, y, size, size),
            'padding': (0, 0, 0, 0),  # left, top, right, bottom
            'has_selection': False,
            'target_size': 512
        }
    
    sel_width = sel_x2 - sel_x1
    sel_height = sel_y2 - sel_y1
    
    # Calculate context padding (30-50% of selection size, min 32px, max 200px)
    context_padding = max(32, min(200, int(max(sel_width, sel_height) * 0.4)))
    
    # Calculate desired context square
    ctx_x1 = sel_x1 - context_padding
    ctx_y1 = sel_y1 - context_padding
    ctx_x2 = sel_x2 + context_padding
    ctx_y2 = sel_y2 + context_padding
    
    ctx_width = ctx_x2 - ctx_x1
    ctx_height = ctx_y2 - ctx_y1
    
    # Make it square by expanding the smaller dimension
    square_size = max(ctx_width, ctx_height)
    
    # Center the square around the selection
    sel_center_x = (sel_x1 + sel_x2) // 2
    sel_center_y = (sel_y1 + sel_y2) // 2
    
    square_x1 = sel_center_x - square_size // 2
    square_y1 = sel_center_y - square_size // 2
    square_x2 = square_x1 + square_size
    square_y2 = square_y1 + square_size
    
    # Calculate padding needed if square extends beyond image boundaries
    pad_left = max(0, -square_x1)
    pad_top = max(0, -square_y1)
    pad_right = max(0, square_x2 - img_width)
    pad_bottom = max(0, square_y2 - img_height)
    
    # Adjust extraction region to stay within image bounds
    extract_x1 = max(0, square_x1)
    extract_y1 = max(0, square_y1)
    extract_x2 = min(img_width, square_x2)
    extract_y2 = min(img_height, square_y2)
    extract_width = extract_x2 - extract_x1
    extract_height = extract_y2 - extract_y1
    
    # Optimize square size for OpenAI (prefer 512, 768, or 1024)
    if square_size <= 512:
        target_size = 512
    elif square_size <= 768:
        target_size = 768
    else:
        target_size = 1024
    
    return {
        'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
        'context_square': (square_x1, square_y1, square_size, square_size),
        'extract_region': (extract_x1, extract_y1, extract_width, extract_height),
        'padding': (pad_left, pad_top, pad_right, pad_bottom),
        'target_size': target_size,
        'has_selection': True
    }


def calculate_mask_coordinates(context_info, target_size):
    """
    Calculate mask coordinates for selection within context square.
    
    Args:
        context_info: Context extraction info from calculate_context_extraction()
        target_size: Target size for the mask (e.g. 1024)
        
    Returns:
        dict with mask coordinates
    """
    if not context_info['has_selection']:
        # Create center circle mask for no selection case
        center = target_size // 2
        radius = target_size // 4
        return {
            'mask_type': 'circle',
            'center_x': center,
            'center_y': center,
            'radius': radius,
            'target_size': target_size
        }
    
    # Get context square info
    sel_x1, sel_y1, sel_x2, sel_y2 = context_info['selection_bounds']
    ctx_x1, ctx_y1, ctx_size, _ = context_info['context_square']
    
    # Calculate selection position within the context square
    sel_in_ctx_x1 = sel_x1 - ctx_x1
    sel_in_ctx_y1 = sel_y1 - ctx_y1
    sel_in_ctx_x2 = sel_x2 - ctx_x1
    sel_in_ctx_y2 = sel_y2 - ctx_y1
    
    # Scale to target size
    scale = target_size / ctx_size
    mask_sel_x1 = int(sel_in_ctx_x1 * scale)
    mask_sel_y1 = int(sel_in_ctx_y1 * scale)
    mask_sel_x2 = int(sel_in_ctx_x2 * scale)
    mask_sel_y2 = int(sel_in_ctx_y2 * scale)
    
    # Ensure coordinates are within bounds
    mask_sel_x1 = max(0, min(target_size - 1, mask_sel_x1))
    mask_sel_y1 = max(0, min(target_size - 1, mask_sel_y1))
    mask_sel_x2 = max(0, min(target_size, mask_sel_x2))
    mask_sel_y2 = max(0, min(target_size, mask_sel_y2))
    
    return {
        'mask_type': 'rectangle',
        'x1': mask_sel_x1,
        'y1': mask_sel_y1,
        'x2': mask_sel_x2,
        'y2': mask_sel_y2,
        'target_size': target_size,
        'scale_factor': scale
    }


def calculate_placement_coordinates(context_info):
    """
    Calculate where to place the AI result back in the original image.
    
    Args:
        context_info: Context extraction info from extract_context_with_selection()
        
    Returns:
        dict with placement coordinates
    """
    ctx_x1, ctx_y1, ctx_width, ctx_height = context_info['extract_region']
    
    return {
        'paste_x': ctx_x1,
        'paste_y': ctx_y1, 
        'result_width': ctx_width,
        'result_height': ctx_height
    }


def validate_context_info(context_info):
    """
    Validate that context_info contains all required fields with valid values.
    
    Args:
        context_info: Context info dict to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    required_fields = [
        'selection_bounds', 'extract_region', 'target_shape', 'has_selection'
    ]
    
    for field in required_fields:
        if field not in context_info:
            return False, f"Missing required field: {field}"
    
    # Validate selection bounds
    sel_bounds = context_info['selection_bounds']
    if len(sel_bounds) != 4:
        return False, "selection_bounds must have 4 values (x1, y1, x2, y2)"
    
    sel_x1, sel_y1, sel_x2, sel_y2 = sel_bounds
    if sel_x2 <= sel_x1 or sel_y2 <= sel_y1:
        return False, "Invalid selection bounds: x2 <= x1 or y2 <= y1"
    
    # Validate extract region
    extract_region = context_info['extract_region']
    if len(extract_region) != 4:
        return False, "extract_region must have 4 values (x1, y1, width, height)"
    
    ext_x1, ext_y1, ext_width, ext_height = extract_region
    if ext_width <= 0 or ext_height <= 0:
        return False, "Extract region dimensions must be positive"
    
    # Validate that extract region contains selection (for focused mode)
    if context_info.get('mode') == 'focused':
        ext_x2 = ext_x1 + ext_width
        ext_y2 = ext_y1 + ext_height
        
        if not (ext_x1 <= sel_x1 and ext_y1 <= sel_y1 and ext_x2 >= sel_x2 and ext_y2 >= sel_y2):
            return False, "Extract region must contain the selection"
    
    # Validate target shape
    target_shape = context_info['target_shape']
    if not isinstance(target_shape, tuple) or len(target_shape) != 2:
        return False, "target_shape must be a tuple of (width, height)"
    valid_shapes = [(1024, 1024), (1536, 1024), (1024, 1536)]
    if target_shape not in valid_shapes:
        return False, f"target_shape must be one of {valid_shapes}"
    
    return True, ""


def test_coordinate_properties(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2):
    """
    Test that coordinate calculations satisfy expected mathematical properties.
    
    Returns:
        dict with test results
    """
    context_info = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    mask_coords = calculate_mask_coordinates(context_info, context_info['target_size'])
    placement = calculate_placement_coordinates(context_info)
    
    # Test validation
    is_valid, error_msg = validate_context_info(context_info)
    
    results = {
        'validation_passed': is_valid,
        'validation_error': error_msg,
        'context_contains_selection': True,  # Will be checked below
        'mask_coordinates_valid': True,
        'placement_covers_selection': True
    }
    
    if not is_valid:
        return results
    
    # Check that context square contains selection
    ctx_x1, ctx_y1, ctx_width, ctx_height = context_info['context_square']
    ctx_x2, ctx_y2 = ctx_x1 + ctx_width, ctx_y1 + ctx_height
    
    results['context_contains_selection'] = (
        ctx_x1 <= sel_x1 and ctx_y1 <= sel_y1 and 
        ctx_x2 >= sel_x2 and ctx_y2 >= sel_y2
    )
    
    # Check mask coordinates are within bounds
    if mask_coords['mask_type'] == 'rectangle':
        target_size = context_info['target_size']
        results['mask_coordinates_valid'] = (
            0 <= mask_coords['x1'] < target_size and
            0 <= mask_coords['y1'] < target_size and
            0 < mask_coords['x2'] <= target_size and  
            0 < mask_coords['y2'] <= target_size and
            mask_coords['x1'] < mask_coords['x2'] and
            mask_coords['y1'] < mask_coords['y2']
        )
    
    # Check that placement would cover selection
    paste_x, paste_y = placement['paste_x'], placement['paste_y']
    result_width, result_height = placement['result_width'], placement['result_height']
    
    results['placement_covers_selection'] = (
        paste_x <= sel_x1 and paste_y <= sel_y1 and
        paste_x + result_width >= sel_x2 and paste_y + result_height >= sel_y2
    )
    
    return results