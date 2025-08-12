#!/usr/bin/env python3
"""
Comprehensive test suite for coordinate transformation functions.

These tests validate the mathematical correctness of the coordinate transformations
used in the GIMP AI Plugin without requiring GIMP to be installed.
"""

import sys
import os

# Add parent directory to path so we can import coordinate_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinate_utils import (
    calculate_context_extraction,
    calculate_mask_coordinates,
    calculate_placement_coordinates,
    validate_context_info,
    test_coordinate_properties
)


def test_basic_context_extraction():
    """Test basic context extraction with centered selection."""
    print("=== Testing Basic Context Extraction ===")
    
    # Test case: 400x300 selection in 1200x800 image  
    img_width, img_height = 1200, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 400, 250, 800, 550
    
    result = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Validate basic structure
    assert 'selection_bounds' in result
    assert 'context_square' in result
    assert 'target_size' in result
    assert result['has_selection'] == True
    
    # Check that context square contains selection
    ctx_x1, ctx_y1, ctx_size, _ = result['context_square']
    ctx_x2, ctx_y2 = ctx_x1 + ctx_size, ctx_y1 + ctx_size
    
    assert ctx_x1 <= sel_x1, f"Context left {ctx_x1} should be <= selection left {sel_x1}"
    assert ctx_y1 <= sel_y1, f"Context top {ctx_y1} should be <= selection top {sel_y1}"
    assert ctx_x2 >= sel_x2, f"Context right {ctx_x2} should be >= selection right {sel_x2}"
    assert ctx_y2 >= sel_y2, f"Context bottom {ctx_y2} should be >= selection bottom {sel_y2}"
    
    print(f"✓ Selection ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})")
    print(f"✓ Context square ({ctx_x1},{ctx_y1}) to ({ctx_x2},{ctx_y2}), size {ctx_size}")
    print(f"✓ Target size: {result['target_size']}")


def test_boundary_selection():
    """Test selection at image boundaries."""
    print("\n=== Testing Boundary Selection ===")
    
    # Selection touching left and top edges
    img_width, img_height = 1000, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 0, 0, 200, 150
    
    result = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Validation failed: {error_msg}"
    
    # Check padding is calculated correctly
    padding = result['padding']
    print(f"✓ Boundary selection, padding: left={padding[0]}, top={padding[1]}, right={padding[2]}, bottom={padding[3]}")
    
    # Left and top padding should be > 0 since context extends beyond image
    assert padding[0] > 0, "Should have left padding for boundary selection"
    assert padding[1] > 0, "Should have top padding for boundary selection"


def test_corner_selection():
    """Test selection in image corner."""
    print("\n=== Testing Corner Selection ===")
    
    # Selection in bottom-right corner
    img_width, img_height = 800, 600
    sel_x1, sel_y1, sel_x2, sel_y2 = 650, 450, 800, 600
    
    result = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Validate
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Corner selection validation failed: {error_msg}"
    
    # Check that we get appropriate padding
    padding = result['padding']
    print(f"✓ Corner selection, padding: left={padding[0]}, top={padding[1]}, right={padding[2]}, bottom={padding[3]}")
    
    # Should have right and bottom padding
    assert padding[2] > 0, "Should have right padding for corner selection"
    assert padding[3] > 0, "Should have bottom padding for corner selection"


def test_large_selection():
    """Test selection covering most of the image."""
    print("\n=== Testing Large Selection ===")
    
    # Selection covering 80% of image
    img_width, img_height = 1000, 1000
    margin = 100
    sel_x1, sel_y1 = margin, margin
    sel_x2, sel_y2 = img_width - margin, img_height - margin
    
    result = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Large selection validation failed: {error_msg}"
    
    # Context should be larger than selection
    ctx_x1, ctx_y1, ctx_size, _ = result['context_square']
    print(f"✓ Large selection {sel_x2-sel_x1}x{sel_y2-sel_y1}, context size: {ctx_size}")
    
    # Should use 1024 target size for large selections
    assert result['target_size'] == 1024, f"Expected 1024 target size, got {result['target_size']}"


def test_small_selection():
    """Test very small selection."""
    print("\n=== Testing Small Selection ===")
    
    # 50x50 selection in large image
    img_width, img_height = 2000, 1500
    sel_x1, sel_y1, sel_x2, sel_y2 = 1000, 750, 1050, 800
    
    result = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Small selection validation failed: {error_msg}"
    
    # Should use 512 target size for small selections
    assert result['target_size'] == 512, f"Expected 512 target size, got {result['target_size']}"
    
    # Context should have minimum padding
    ctx_x1, ctx_y1, ctx_size, _ = result['context_square']
    sel_size = max(sel_x2 - sel_x1, sel_y2 - sel_y1)
    expected_padding = max(32, int(sel_size * 0.4))
    print(f"✓ Small selection {sel_x2-sel_x1}x{sel_y2-sel_y1}, context size: {ctx_size}, expected padding: {expected_padding}")


def test_no_selection():
    """Test behavior with no selection."""
    print("\n=== Testing No Selection ===")
    
    img_width, img_height = 800, 600
    
    result = calculate_context_extraction(img_width, img_height, 0, 0, 0, 0, has_selection=False)
    
    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"No selection validation failed: {error_msg}"
    
    # Should default to center area
    assert result['has_selection'] == False
    assert result['target_size'] == 512
    
    # Selection bounds should be centered
    sel_bounds = result['selection_bounds']
    print(f"✓ No selection, defaults to center: {sel_bounds}")


def test_mask_coordinates():
    """Test mask coordinate calculations."""
    print("\n=== Testing Mask Coordinates ===")
    
    # Create a context extraction result
    img_width, img_height = 1200, 900
    sel_x1, sel_y1, sel_x2, sel_y2 = 400, 300, 800, 600
    
    context_info = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    target_size = 1024
    
    # Calculate mask coordinates
    mask_coords = calculate_mask_coordinates(context_info, target_size)
    
    # Should be rectangle type
    assert mask_coords['mask_type'] == 'rectangle'
    
    # Coordinates should be within bounds
    assert 0 <= mask_coords['x1'] < target_size
    assert 0 <= mask_coords['y1'] < target_size
    assert 0 < mask_coords['x2'] <= target_size
    assert 0 < mask_coords['y2'] <= target_size
    
    # x1 < x2 and y1 < y2
    assert mask_coords['x1'] < mask_coords['x2']
    assert mask_coords['y1'] < mask_coords['y2']
    
    print(f"✓ Mask coordinates: ({mask_coords['x1']},{mask_coords['y1']}) to ({mask_coords['x2']},{mask_coords['y2']})")
    print(f"✓ Scale factor: {mask_coords['scale_factor']}")


def test_placement_coordinates():
    """Test placement coordinate calculations."""
    print("\n=== Testing Placement Coordinates ===")
    
    # Create a context extraction result
    img_width, img_height = 1000, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 300, 200, 700, 500
    
    context_info = calculate_context_extraction(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    
    # Calculate placement coordinates
    placement = calculate_placement_coordinates(context_info)
    
    # Should have required fields
    assert 'paste_x' in placement
    assert 'paste_y' in placement
    assert 'result_width' in placement
    assert 'result_height' in placement
    
    # Placement should cover the selection area
    paste_x, paste_y = placement['paste_x'], placement['paste_y']
    result_w, result_h = placement['result_width'], placement['result_height']
    
    # Check that placement covers selection
    covers_selection = (
        paste_x <= sel_x1 and paste_y <= sel_y1 and
        paste_x + result_w >= sel_x2 and paste_y + result_h >= sel_y2
    )
    assert covers_selection, f"Placement ({paste_x},{paste_y}) {result_w}x{result_h} should cover selection ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
    
    print(f"✓ Placement: ({paste_x},{paste_y}) size {result_w}x{result_h}")
    print(f"✓ Covers selection: {covers_selection}")


def test_mathematical_properties():
    """Test mathematical properties using built-in test function."""
    print("\n=== Testing Mathematical Properties ===")
    
    test_cases = [
        (1200, 800, 400, 250, 800, 550),  # Centered selection
        (1000, 800, 0, 0, 200, 150),      # Boundary selection
        (800, 600, 650, 450, 800, 600),   # Corner selection
        (2000, 1500, 1000, 750, 1050, 800)  # Small selection
    ]
    
    for i, (img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2) in enumerate(test_cases):
        print(f"\nTest case {i+1}: Selection ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2}) in {img_w}x{img_h}")
        
        results = test_coordinate_properties(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2)
        
        # All properties should pass
        assert results['validation_passed'], f"Validation failed: {results['validation_error']}"
        assert results['context_contains_selection'], "Context should contain selection"
        assert results['mask_coordinates_valid'], "Mask coordinates should be valid"
        assert results['placement_covers_selection'], "Placement should cover selection"
        
        print("✓ All properties validated successfully")


def test_edge_cases():
    """Test edge cases that might cause issues."""
    print("\n=== Testing Edge Cases ===")
    
    # Very small image
    print("Testing very small image...")
    result = calculate_context_extraction(100, 100, 10, 10, 90, 90)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Small image should be valid"
    print("✓ Very small image handled correctly")
    
    # Very large image
    print("Testing very large image...")
    result = calculate_context_extraction(10000, 8000, 1000, 1000, 5000, 4000)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Large image should be valid"
    print("✓ Very large image handled correctly")
    
    # Square selection
    print("Testing square selection...")
    result = calculate_context_extraction(1000, 1000, 400, 400, 600, 600)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Square selection should be valid"
    print("✓ Square selection handled correctly")
    
    # Thin rectangle selection
    print("Testing thin rectangle selection...")
    result = calculate_context_extraction(1000, 800, 100, 300, 900, 320)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Thin rectangle should be valid"
    print("✓ Thin rectangle handled correctly")


def run_all_tests():
    """Run all coordinate transformation tests."""
    print("🧪 Running Coordinate Transformation Tests")
    print("=" * 60)
    
    try:
        test_basic_context_extraction()
        test_boundary_selection()
        test_corner_selection()
        test_large_selection()
        test_small_selection()
        test_no_selection()
        test_mask_coordinates()
        test_placement_coordinates()
        test_mathematical_properties()
        test_edge_cases()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("✓ Context extraction works correctly")
        print("✓ Mask coordinates are valid")
        print("✓ Placement coordinates align properly")
        print("✓ Edge cases are handled")
        print("✓ Mathematical properties are satisfied")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)