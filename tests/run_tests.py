#!/usr/bin/env python3
"""
Test runner for GIMP AI Plugin coordinate transformations.

This script runs all coordinate transformation tests and reports results.
It can be run without GIMP installed since it only tests pure Python functions.
"""

import sys
import os

def main():
    """Run all tests and report results."""
    print("GIMP AI Plugin - Coordinate Transformation Test Suite")
    print("=" * 60)
    
    # Ensure we can import test modules
    test_dir = os.path.dirname(os.path.abspath(__file__))
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
    
    # Import and run coordinate tests
    try:
        from test_coordinate_transformations import run_all_tests
        
        print("Running coordinate transformation tests...")
        success = run_all_tests()
        
        if success:
            print("\n🎉 All tests completed successfully!")
            print("The coordinate transformation system is mathematically correct.")
            return 0
        else:
            print("\n❌ Some tests failed.")
            print("Please check the coordinate transformation logic.")
            return 1
            
    except ImportError as e:
        print(f"❌ Failed to import test modules: {e}")
        print("Make sure coordinate_utils.py is in the parent directory.")
        return 1
    except Exception as e:
        print(f"💥 Unexpected error running tests: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())