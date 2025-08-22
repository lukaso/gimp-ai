#!/usr/bin/env python3
"""
Test suite for shape-aware coordinate transformation functions.

Tests the new OpenAI shape selection and padding algorithms.
"""

import sys
import os

# Add parent directory to path so we can import coordinate_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinate_utils import (
    get_optimal_openai_shape,
    calculate_padding_for_shape,
    extract_context_with_selection,
    calculate_result_placement,
    calculate_scale_from_shape
)


def test_optimal_shape_selection():
    """Test OpenAI shape selection based on aspect ratio."""
    print("=== Testing Optimal Shape Selection ===")
    
    test_cases = [
        # (width, height, expected_shape, description)
        (1920, 1080, (1536, 1024), "16:9 landscape"),
        (1080, 1920, (1024, 1536), "9:16 portrait"),
        (1024, 1024, (1024, 1024), "1:1 square"),
        (1200, 1000, (1024, 1024), "Near square (1.2 ratio)"),
        (1000, 1200, (1024, 1024), "Near square (0.83 ratio)"),
        (2000, 1000, (1536, 1024), "2:1 wide landscape"),
        (500, 1500, (1024, 1536), "1:3 tall portrait"),
        (1440, 1080, (1536, 1024), "4:3 landscape"),
        (1080, 1440, (1024, 1536), "3:4 portrait"),
        (0, 0, (1024, 1024), "Invalid dimensions"),
        (-100, 200, (1024, 1024), "Negative dimension"),
    ]
    
    for width, height, expected, desc in test_cases:
        result = get_optimal_openai_shape(width, height)
        assert result == expected, f"Failed for {desc}: {width}x{height} -> got {result}, expected {expected}"
        print(f"✓ {desc}: {width}x{height} -> {result}")
    
    print("✓ All shape selections correct")


def test_padding_calculations():
    """Test padding calculations for different shapes."""
    print("\n=== Testing Padding Calculations ===")
    
    test_cases = [
        # (current_size, target_size, description)
        ((800, 600), (1024, 1024), "4:3 to square"),
        ((1920, 1080), (1536, 1024), "16:9 to landscape"),
        ((1080, 1920), (1024, 1536), "9:16 to portrait"),
        ((500, 500), (1024, 1024), "Small square to large square"),
        ((2000, 2000), (1024, 1024), "Large to small (scale down)"),
    ]
    
    for (curr_w, curr_h), (tgt_w, tgt_h), desc in test_cases:
        result = calculate_padding_for_shape(curr_w, curr_h, tgt_w, tgt_h)
        
        # Verify scale factor
        scale = result['scale_factor']
        scaled_w, scaled_h = result['scaled_size']
        
        # Check that scaled dimensions fit within target
        assert scaled_w <= tgt_w, f"Scaled width {scaled_w} exceeds target {tgt_w}"
        assert scaled_h <= tgt_h, f"Scaled height {scaled_h} exceeds target {tgt_h}"
        
        # Check padding sums to fill target
        pad_left, pad_top, pad_right, pad_bottom = result['padding']
        total_width = scaled_w + pad_left + pad_right
        total_height = scaled_h + pad_top + pad_bottom
        
        assert total_width == tgt_w, f"Padded width {total_width} != target {tgt_w}"
        assert total_height == tgt_h, f"Padded height {total_height} != target {tgt_h}"
        
        print(f"✓ {desc}: scale={scale:.2f}, padding=({pad_left},{pad_top},{pad_right},{pad_bottom})")


def test_context_extraction_with_shapes():
    """Test context extraction with optimal shape selection."""
    print("\n=== Testing Context Extraction with Shapes ===")
    
    # Test landscape image with selection
    img_w, img_h = 1920, 1080
    sel_x1, sel_y1, sel_x2, sel_y2 = 800, 400, 1200, 700
    
    # Test focused mode
    result = extract_context_with_selection(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='focused')
    
    assert result['mode'] == 'focused'
    assert 'target_shape' in result
    assert 'padding_info' in result
    assert result['has_selection'] == True
    
    # Selection should be within extract region
    sel_in_extract = result['selection_in_extract']
    assert sel_in_extract[0] >= 0
    assert sel_in_extract[1] >= 0
    
    print(f"✓ Focused extraction: shape={result['target_shape']}, needs_padding={result['needs_padding']}")
    
    # Test full mode
    result = extract_context_with_selection(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='full')
    
    assert result['mode'] == 'full'
    assert result['extract_region'] == (0, 0, img_w, img_h)
    assert result['target_shape'] == (1536, 1024)  # Landscape shape for 16:9
    
    print(f"✓ Full extraction: shape={result['target_shape']}")
    
    # Test no selection
    result = extract_context_with_selection(img_w, img_h, 0, 0, 0, 0, has_selection=False)
    
    assert result['has_selection'] == False
    assert 'target_shape' in result
    
    print(f"✓ No selection: shape={result['target_shape']}")


def test_boundary_aware_extraction():
    """Test that extraction avoids extending beyond boundaries when possible."""
    print("\n=== Testing Boundary-Aware Extraction ===")
    
    # Selection near top-left corner
    img_w, img_h = 1000, 800
    sel_x1, sel_y1, sel_x2, sel_y2 = 50, 50, 150, 150
    
    result = extract_context_with_selection(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2)
    
    extract_region = result['extract_region']
    extract_x1, extract_y1, extract_w, extract_h = extract_region
    
    # Should shift context to avoid going negative
    assert extract_x1 >= 0, "Extract should not go beyond left edge"
    assert extract_y1 >= 0, "Extract should not go beyond top edge"
    
    print(f"✓ Top-left corner: extract at ({extract_x1},{extract_y1})")
    
    # Selection near bottom-right corner
    sel_x1, sel_y1, sel_x2, sel_y2 = 850, 650, 950, 750
    
    result = extract_context_with_selection(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2)
    
    extract_region = result['extract_region']
    extract_x1, extract_y1, extract_w, extract_h = extract_region
    extract_x2 = extract_x1 + extract_w
    extract_y2 = extract_y1 + extract_h
    
    # Should shift context to avoid going beyond image
    assert extract_x2 <= img_w, "Extract should not go beyond right edge"
    assert extract_y2 <= img_h, "Extract should not go beyond bottom edge"
    
    print(f"✓ Bottom-right corner: extract ends at ({extract_x2},{extract_y2})")


def test_result_placement():
    """Test placement calculations for AI results."""
    print("\n=== Testing Result Placement ===")
    
    # Full mode placement
    context_info = {
        'mode': 'full',
        'extract_region': (0, 0, 1920, 1080),
        'target_shape': (1536, 1024)
    }
    
    result_shape = (1536, 1024)
    original_shape = (1920, 1080)
    
    placement = calculate_result_placement(result_shape, original_shape, context_info)
    
    assert placement['placement_mode'] == 'replace'
    assert placement['position'] == (0, 0)
    assert placement['size'] == original_shape
    
    print(f"✓ Full mode placement: scale={placement['scale']}")
    
    # Focused mode placement
    context_info = {
        'mode': 'focused',
        'extract_region': (100, 50, 800, 600),
        'target_shape': (1024, 1024)
    }
    
    result_shape = (1024, 1024)
    
    placement = calculate_result_placement(result_shape, original_shape, context_info)
    
    assert placement['placement_mode'] == 'composite'
    assert placement['position'] == (100, 50)
    assert placement['size'] == (800, 600)
    
    print(f"✓ Focused mode placement: position={placement['position']}, size={placement['size']}")


def test_scale_calculations():
    """Test scale factor calculations."""
    print("\n=== Testing Scale Calculations ===")
    
    test_cases = [
        ((1920, 1080), (1536, 1024), "16:9 to OpenAI landscape"),
        ((1024, 1024), (512, 512), "Downscale square"),
        ((512, 768), (1024, 1536), "Upscale to portrait"),
        ((100, 100), (1000, 1000), "10x scale up"),
    ]
    
    for source, target, desc in test_cases:
        result = calculate_scale_from_shape(source, target)
        
        scale_x = result['scale_x']
        scale_y = result['scale_y']
        uniform = result['uniform_scale']
        
        # Verify calculations
        assert abs(scale_x - target[0]/source[0]) < 0.001, f"scale_x calculation wrong"
        assert abs(scale_y - target[1]/source[1]) < 0.001, f"scale_y calculation wrong"
        assert uniform == min(scale_x, scale_y), f"uniform_scale should be min"
        
        print(f"✓ {desc}: scale_x={scale_x:.2f}, scale_y={scale_y:.2f}, uniform={uniform:.2f}")


def test_aspect_ratio_preservation():
    """Test that aspect ratios are preserved correctly."""
    print("\n=== Testing Aspect Ratio Preservation ===")
    
    # Wide image should get landscape shape
    img_w, img_h = 2560, 1440
    shape = get_optimal_openai_shape(img_w, img_h)
    assert shape == (1536, 1024), f"Wide image should get landscape shape"
    
    # Tall image should get portrait shape
    img_w, img_h = 1080, 2160
    shape = get_optimal_openai_shape(img_w, img_h)
    assert shape == (1024, 1536), f"Tall image should get portrait shape"
    
    # Test that padding preserves aspect ratio
    padding_info = calculate_padding_for_shape(2560, 1440, 1536, 1024)
    scale = padding_info['scale_factor']
    scaled_w, scaled_h = padding_info['scaled_size']
    
    # Check aspect ratio preserved (within rounding error)
    original_ratio = 2560 / 1440
    scaled_ratio = scaled_w / scaled_h
    assert abs(original_ratio - scaled_ratio) < 0.01, f"Aspect ratio not preserved"
    
    print(f"✓ Aspect ratios preserved correctly")


def test_edge_cases():
    """Test edge cases and error conditions."""
    print("\n=== Testing Edge Cases ===")
    
    # Zero dimensions
    shape = get_optimal_openai_shape(0, 100)
    assert shape == (1024, 1024), "Should default to square for invalid dimensions"
    
    # Very small dimensions
    result = extract_context_with_selection(10, 10, 2, 2, 8, 8)
    assert 'target_shape' in result
    
    # Very large dimensions
    result = extract_context_with_selection(10000, 8000, 1000, 1000, 2000, 2000)
    assert 'target_shape' in result
    
    # Selection larger than image (shouldn't happen but test anyway)
    result = extract_context_with_selection(100, 100, -50, -50, 150, 150)
    extract = result['extract_region']
    assert extract[0] >= 0 and extract[1] >= 0, "Extract should be clamped to image bounds"
    
    print("✓ Edge cases handled correctly")


def run_all_tests():
    """Run all shape-aware function tests."""
    print("🧪 Running Shape-Aware Function Tests")
    print("=" * 60)
    
    try:
        test_optimal_shape_selection()
        test_padding_calculations()
        test_context_extraction_with_shapes()
        test_boundary_aware_extraction()
        test_result_placement()
        test_scale_calculations()
        test_aspect_ratio_preservation()
        test_edge_cases()
        
        print("\n" + "=" * 60)
        print("🎉 ALL SHAPE-AWARE TESTS PASSED!")
        print("✓ Optimal shape selection works")
        print("✓ Padding calculations are correct")
        print("✓ Boundary-aware extraction works")
        print("✓ Result placement is accurate")
        print("✓ Aspect ratios are preserved")
        
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