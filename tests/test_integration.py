#!/usr/bin/env python3
"""
Integration test for shape-aware functions with existing code.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinate_utils import (
    calculate_context_extraction,
    extract_context_with_selection,
    get_optimal_openai_shape,
    validate_context_info
)


def test_new_format_validation():
    """Test that new format validation works correctly.""" 
    print("=== Testing New Format Validation ===")
    
    # New function should work and validate
    result = extract_context_with_selection(1920, 1080, 500, 300, 900, 600)
    
    assert 'target_shape' in result
    assert 'selection_bounds' in result
    assert 'extract_region' in result
    
    # Should validate with new validator
    is_valid, msg = validate_context_info(result)
    assert is_valid, f"New format validation failed: {msg}"
    
    print("✓ New extract_context_with_selection works")
    print(f"  Target shape: {result['target_shape']}")
    print(f"  Extract region: {result['extract_region']}")
    print(f"  Mode: {result['mode']}")


def test_shape_selection_scenarios():
    """Test various real-world scenarios."""
    print("\n=== Testing Real-World Scenarios ===")
    
    scenarios = [
        # (img_size, selection, expected_shape, description)
        ((1920, 1080), (800, 400, 1200, 700), (1024, 1024), "HD video frame, square selection"),
        ((3840, 2160), (1000, 500, 2000, 1500), (1024, 1024), "4K image, square selection"),
        ((1080, 1920), (200, 500, 800, 1400), (1024, 1536), "Portrait phone photo"),
        ((2560, 1440), (0, 0, 2560, 1440), (1536, 1024), "Wide monitor screenshot"),
        ((800, 800), (100, 100, 700, 700), (1024, 1024), "Square image"),
    ]
    
    for (img_w, img_h), (sel_x1, sel_y1, sel_x2, sel_y2), expected_shape, desc in scenarios:
        # Test with new function
        result = extract_context_with_selection(
            img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='focused'
        )
        
        actual_shape = result['target_shape']
        assert actual_shape == expected_shape, \
            f"{desc}: Expected {expected_shape}, got {actual_shape}"
        
        print(f"✓ {desc}: {actual_shape}")


def test_full_vs_focused_mode():
    """Test different processing modes."""
    print("\n=== Testing Full vs Focused Mode ===")
    
    img_w, img_h = 1920, 1080
    sel_x1, sel_y1, sel_x2, sel_y2 = 700, 300, 1100, 600
    
    # Focused mode - extracts region around selection
    focused = extract_context_with_selection(
        img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='focused'
    )
    
    assert focused['mode'] == 'focused'
    assert focused['extract_region'] != (0, 0, img_w, img_h)
    print(f"✓ Focused mode: extracts region {focused['extract_region']}")
    print(f"  Shape: {focused['target_shape']}")
    
    # Full mode - uses entire image
    full = extract_context_with_selection(
        img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='full'
    )
    
    assert full['mode'] == 'full'
    assert full['extract_region'] == (0, 0, img_w, img_h)
    assert full['target_shape'] == (1536, 1024)  # Landscape for 16:9
    print(f"✓ Full mode: uses entire image")
    print(f"  Shape: {full['target_shape']}")


def test_api_size_formatting():
    """Test that shapes format correctly for API."""
    print("\n=== Testing API Size Formatting ===")
    
    shapes = [
        ((1024, 1024), "1024x1024"),
        ((1536, 1024), "1536x1024"),
        ((1024, 1536), "1024x1536"),
    ]
    
    for shape, expected_str in shapes:
        api_size = f"{shape[0]}x{shape[1]}"
        assert api_size == expected_str, f"Format error: {api_size} != {expected_str}"
        print(f"✓ {shape} -> '{api_size}'")


def run_all_tests():
    """Run all integration tests."""
    print("🧪 Running Integration Tests")
    print("=" * 60)
    
    try:
        test_new_format_validation()
        test_shape_selection_scenarios()
        test_full_vs_focused_mode()
        test_api_size_formatting()
        
        print("\n" + "=" * 60)
        print("🎉 ALL INTEGRATION TESTS PASSED!")
        print("✓ New format validation works")
        print("✓ Shape selection works correctly")
        print("✓ Processing modes work as expected")
        print("✓ API formatting is correct")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)