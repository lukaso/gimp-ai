# Coordinate Transformation Tests

This directory contains comprehensive tests for the coordinate transformation logic used in the GIMP AI Plugin.

## Purpose

The coordinate transformations are the most complex and error-prone part of the inpainting system. These tests validate the mathematical correctness without requiring GIMP to be installed.

## Files

- `test_coordinate_transformations.py` - Main test suite
- `run_tests.py` - Test runner script  
- `README.md` - This documentation

## Running Tests

```bash
# From the project root directory:
python3 tests/run_tests.py
```

## Test Coverage

The test suite validates:

1. **Basic Context Extraction** - Centered selections work correctly
2. **Boundary Cases** - Selections at image edges handle padding properly  
3. **Corner Cases** - Selections in corners calculate boundaries correctly
4. **Size Variations** - Large and small selections use appropriate target sizes
5. **No Selection** - Default center area behavior works
6. **Mask Coordinates** - Selection-to-mask transformations are accurate
7. **Placement Coordinates** - AI results are positioned correctly
8. **Mathematical Properties** - All invariants are satisfied
9. **Edge Cases** - Extreme inputs are handled gracefully

## Mathematical Properties Tested

- **Context Contains Selection**: Context square always fully contains the original selection
- **Mask Coordinates Valid**: All mask coordinates fall within target bounds
- **Scale Consistency**: Scale factors are consistent across transformations  
- **Placement Coverage**: Final placement covers the original selection area
- **Boundary Handling**: Out-of-bounds areas are handled with proper padding

## Installation Independence

These tests run with standard Python (no GIMP dependencies):
- Pure mathematical functions in `coordinate_utils.py`
- No GIMP imports or GUI operations
- Can be run in CI/CD environments
- Fast execution for development workflow

## Expected Output

When all tests pass, you'll see:
```
🎉 ALL TESTS PASSED!
✓ Context extraction works correctly
✓ Mask coordinates are valid  
✓ Placement coordinates align properly
✓ Edge cases are handled
✓ Mathematical properties are satisfied
```

This confirms the coordinate transformation system is mathematically correct.