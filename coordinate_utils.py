"""
Pure coordinate transformation utilities for GIMP AI Plugin.

These functions contain no GIMP dependencies and can be unit tested independently.
All coordinate calculations for context extraction, masking, and placement are here.
"""


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
        context_info: Context extraction info from calculate_context_extraction()
        
    Returns:
        dict with placement coordinates
    """
    ctx_x1, ctx_y1, ctx_size, _ = context_info['context_square']
    
    return {
        'paste_x': ctx_x1,
        'paste_y': ctx_y1, 
        'result_width': ctx_size,
        'result_height': ctx_size
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
        'selection_bounds', 'context_square', 'extract_region', 
        'padding', 'target_size', 'has_selection'
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
    
    # Validate context square
    ctx_square = context_info['context_square']
    if len(ctx_square) != 4:
        return False, "context_square must have 4 values (x1, y1, width, height)"
    
    ctx_x1, ctx_y1, ctx_width, ctx_height = ctx_square
    if ctx_width <= 0 or ctx_height <= 0:
        return False, "Context square dimensions must be positive"
    
    # Validate that context square contains selection
    ctx_x2 = ctx_x1 + ctx_width
    ctx_y2 = ctx_y1 + ctx_height
    
    if not (ctx_x1 <= sel_x1 and ctx_y1 <= sel_y1 and ctx_x2 >= sel_x2 and ctx_y2 >= sel_y2):
        return False, "Context square must contain the selection"
    
    # Validate target size
    target_size = context_info['target_size']
    if target_size not in [512, 768, 1024]:
        return False, "target_size must be 512, 768, or 1024"
    
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