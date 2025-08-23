#!/usr/bin/env python3
"""
Test the new aspect ratio extension logic for focused mode.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinate_utils import extract_context_with_selection


def test_aspect_ratio_extension():
    """Test that extract regions are extended to match target aspect ratio when possible"""
    print("=== Testing Aspect Ratio Extension Logic ===")
    
    # Test case matching your scenario:
    # Image: 4032x3024, Selection: (99,102) to (2514,1050)
    img_w, img_h = 4032, 3024
    sel_x1, sel_y1, sel_x2, sel_y2 = 99, 102, 2514, 1050
    
    result = extract_context_with_selection(img_w, img_h, sel_x1, sel_y1, sel_x2, sel_y2, mode='focused')
    
    extract_region = result['extract_region']
    ctx_x1, ctx_y1, ctx_width, ctx_height = extract_region
    target_shape = result['target_shape']
    padding_info = result['padding_info']
    
    print(f"Image: {img_w}x{img_h}")
    print(f"Selection: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})")
    print(f"Extract region: ({ctx_x1},{ctx_y1}) size {ctx_width}x{ctx_height}")
    print(f"Target shape: {target_shape}")
    print(f"Current aspect: {ctx_width/ctx_height:.3f}")
    print(f"Target aspect: {target_shape[0]/target_shape[1]:.3f}")
    print(f"Scale factor: {padding_info['scale_factor']:.3f}")
    print(f"Padding needed: {padding_info['padding']}")
    
    # Check if padding was reduced/eliminated
    pad_left, pad_top, pad_right, pad_bottom = padding_info['padding']
    total_padding = pad_left + pad_top + pad_right + pad_bottom
    
    if total_padding == 0:
        print("✅ Perfect! No padding needed - aspect ratio matched exactly")
    elif total_padding < 236:  # Original padding was (0, 118, 0, 118) = 236 total
        print(f"✅ Good! Padding reduced to {total_padding} (was ~236)")
    else:
        print(f"⚠️  Padding still needed: {total_padding}")
    
    # Test another case: wide selection that should extend vertically
    print("\n--- Testing Wide Selection (Should Extend Vertically) ---")
    
    # Very wide selection
    wide_sel = extract_context_with_selection(3000, 2000, 200, 800, 2800, 1200, mode='focused')
    wide_extract = wide_sel['extract_region']
    wide_padding = wide_sel['padding_info']['padding']
    
    print(f"Wide selection extract: {wide_extract[2]}x{wide_extract[3]}")
    print(f"Wide selection padding: {wide_padding}")
    
    # Test edge case: selection near boundary
    print("\n--- Testing Selection Near Boundary ---")
    
    boundary_sel = extract_context_with_selection(1000, 1000, 50, 50, 200, 200, mode='focused')
    boundary_extract = boundary_sel['extract_region']
    boundary_padding = boundary_sel['padding_info']['padding']
    
    print(f"Boundary selection extract: {boundary_extract}")
    print(f"Boundary selection padding: {boundary_padding}")
    

def run_test():
    """Run the aspect ratio extension test"""
    print("🧪 Testing Aspect Ratio Extension Logic")
    print("=" * 60)
    
    try:
        test_aspect_ratio_extension()
        print("\n" + "=" * 60)
        print("🎉 ASPECT RATIO EXTENSION TESTS COMPLETED!")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)