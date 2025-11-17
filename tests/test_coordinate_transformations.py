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
    extract_context_with_selection,
    calculate_mask_coordinates,
    calculate_placement_coordinates,
    validate_context_info,
    check_coordinate_properties
)


def test_basic_context_extraction():
    """Test basic context extraction with centered selection."""
    print("=== Testing Basic Context Extraction ===")

    # Test case: 400x300 selection in 1200x800 image
    img_width, img_height = 1200, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 400, 250, 800, 550

    result = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

    # Validate basic structure
    assert 'selection_bounds' in result
    assert 'extract_region' in result
    assert 'target_shape' in result
    assert result['has_selection'] == True

    # Check that extract region contains selection
    ext_x1, ext_y1, ext_width, ext_height = result['extract_region']
    ext_x2, ext_y2 = ext_x1 + ext_width, ext_y1 + ext_height

    assert ext_x1 <= sel_x1, f"Extract left {ext_x1} should be <= selection left {sel_x1}"
    assert ext_y1 <= sel_y1, f"Extract top {ext_y1} should be <= selection top {sel_y1}"
    assert ext_x2 >= sel_x2, f"Extract right {ext_x2} should be >= selection right {sel_x2}"
    assert ext_y2 >= sel_y2, f"Extract bottom {ext_y2} should be >= selection bottom {sel_y2}"

    print(f"✓ Selection ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})")
    print(f"✓ Extract region ({ext_x1},{ext_y1}) to ({ext_x2},{ext_y2}), size {ext_width}x{ext_height}")
    print(f"✓ Target shape: {result['target_shape']}")


def test_boundary_selection():
    """Test selection at image boundaries."""
    print("\n=== Testing Boundary Selection ===")

    # Selection touching left and top edges
    img_width, img_height = 1000, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 0, 0, 200, 150

    result = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Validation failed: {error_msg}"

    # Check padding info
    print(f"✓ Boundary selection, needs_padding: {result['needs_padding']}")
    if result['needs_padding']:
        padding_info = result['padding_info']
        if 'padding' in padding_info:
            pad_left, pad_top, pad_right, pad_bottom = padding_info['padding']
            print(f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}")


def test_corner_selection():
    """Test selection in image corner."""
    print("\n=== Testing Corner Selection ===")

    # Selection in bottom-right corner
    img_width, img_height = 800, 600
    sel_x1, sel_y1, sel_x2, sel_y2 = 650, 450, 800, 600

    result = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

    # Validate
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Corner selection validation failed: {error_msg}"

    # Check padding info
    print(f"✓ Corner selection, needs_padding: {result['needs_padding']}")
    if result['needs_padding']:
        padding_info = result['padding_info']
        if 'padding' in padding_info:
            pad_left, pad_top, pad_right, pad_bottom = padding_info['padding']
            print(f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}")


def test_large_selection():
    """Test selection covering most of the image."""
    print("\n=== Testing Large Selection ===")

    # Selection covering 80% of image
    img_width, img_height = 1000, 1000
    margin = 100
    sel_x1, sel_y1 = margin, margin
    sel_x2, sel_y2 = img_width - margin, img_height - margin

    result = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Large selection validation failed: {error_msg}"

    # Extract region should cover selection
    ext_x1, ext_y1, ext_width, ext_height = result['extract_region']
    print(f"✓ Large selection {sel_x2-sel_x1}x{sel_y2-sel_y1}, extract region: {ext_width}x{ext_height}")

    # Should use large target shape for large selections
    target_shape = result['target_shape']
    print(f"✓ Target shape: {target_shape}")
    assert target_shape in [(1024, 1024), (1536, 1024), (1024, 1536)], f"Expected valid target shape, got {target_shape}"


def test_small_selection():
    """Test very small selection."""
    print("\n=== Testing Small Selection ===")

    # 50x50 selection in large image
    img_width, img_height = 2000, 1500
    sel_x1, sel_y1, sel_x2, sel_y2 = 1000, 750, 1050, 800

    result = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"Small selection validation failed: {error_msg}"

    # Should use small target shape for small selections
    target_shape = result['target_shape']
    print(f"✓ Small selection {sel_x2-sel_x1}x{sel_y2-sel_y1}, target shape: {target_shape}")
    assert target_shape in [(1024, 1024), (1536, 1024), (1024, 1536)], f"Expected valid target shape, got {target_shape}"


def test_no_selection():
    """Test behavior with no selection."""
    print("\n=== Testing No Selection ===")

    img_width, img_height = 800, 600

    result = extract_context_with_selection(img_width, img_height, 0, 0, 0, 0, has_selection=False)

    # Should be valid
    is_valid, error_msg = validate_context_info(result)
    assert is_valid, f"No selection validation failed: {error_msg}"

    # Should default to full image mode
    assert result['has_selection'] == False
    assert 'target_shape' in result

    # Should be in full mode
    print(f"✓ No selection, mode: {result['mode']}, target shape: {result['target_shape']}")


def test_mask_coordinates():
    """Test mask coordinate calculations."""
    print("\n=== Testing Mask Coordinates ===")

    # Create a context extraction result
    img_width, img_height = 1200, 900
    sel_x1, sel_y1, sel_x2, sel_y2 = 400, 300, 800, 600

    context_info = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)
    target_shape = context_info['target_shape']
    target_size = max(target_shape)

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

    context_info = extract_context_with_selection(img_width, img_height, sel_x1, sel_y1, sel_x2, sel_y2)

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
        
        results = check_coordinate_properties(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2)
        
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
    result = extract_context_with_selection(100, 100, 10, 10, 90, 90)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Small image should be valid"
    print("✓ Very small image handled correctly")

    # Very large image
    print("Testing very large image...")
    result = extract_context_with_selection(10000, 8000, 1000, 1000, 5000, 4000)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Large image should be valid"
    print("✓ Very large image handled correctly")

    # Square selection
    print("Testing square selection...")
    result = extract_context_with_selection(1000, 1000, 400, 400, 600, 600)
    is_valid, _ = validate_context_info(result)
    assert is_valid, "Square selection should be valid"
    print("✓ Square selection handled correctly")

    # Thin rectangle selection
    print("Testing thin rectangle selection...")
    result = extract_context_with_selection(1000, 800, 100, 300, 900, 320)
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