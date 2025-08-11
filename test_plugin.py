#!/usr/bin/env python3
"""
Test script for GIMP AI Plugin
Basic validation and API connectivity tests
"""

import sys
import json
from pathlib import Path

def test_dependencies():
    """Test if required dependencies are available"""
    print("Testing Python dependencies...")
    
    required_packages = {
        'requests': 'HTTP requests',
        'gi': 'GObject Introspection',
        'json': 'JSON handling',
        'base64': 'Base64 encoding',
        'tempfile': 'Temporary files',
        'os': 'Operating system interface'
    }
    
    missing = []
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"✓ {package} ({description})")
        except ImportError:
            print(f"✗ {package} ({description}) - MISSING")
            missing.append(package)
    
    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Install with: pip install requests pygobject")
        return False
    
    print("All dependencies OK!")
    return True

def test_config_file():
    """Test configuration file"""
    print("\nTesting configuration...")
    
    config_paths = [
        "config.json",
        Path.home() / ".config" / "gimp-ai" / "config.json",
        Path.home() / ".gimp-ai-config.json"
    ]
    
    config_found = False
    for config_path in config_paths:
        if Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                print(f"✓ Config file found: {config_path}")
                
                # Test configuration structure
                required_keys = ['api_provider', 'settings']
                for key in required_keys:
                    if key in config:
                        print(f"  ✓ {key}")
                    else:
                        print(f"  ✗ {key} - missing")
                
                config_found = True
                return config
            except json.JSONDecodeError:
                print(f"✗ Config file invalid JSON: {config_path}")
            except IOError:
                print(f"✗ Cannot read config file: {config_path}")
    
    if not config_found:
        print("No config file found - will use defaults")
        return {}

def test_api_connectivity(config):
    """Test API connectivity"""
    print("\nTesting API connectivity...")
    
    provider = config.get('api_provider', 'openai')
    print(f"Testing {provider} API...")
    
    if provider == 'openai':
        api_config = config.get('openai', {})
        api_key = api_config.get('api_key', '')
        
        if not api_key:
            print("✗ OpenAI API key not configured")
            return False
        
        if not api_key.startswith('sk-'):
            print("✗ OpenAI API key format invalid")
            return False
        
        # Test API connectivity (without actual API call to avoid costs)
        headers = {'Authorization': f'Bearer {api_key}'}
        print("✓ API key format valid")
        print("ℹ Skipping actual API test to avoid charges")
        
    elif provider == 'anthropic':
        api_config = config.get('anthropic', {})
        api_key = api_config.get('api_key', '')
        
        if not api_key:
            print("✗ Anthropic API key not configured")
            return False
        
        if not api_key.startswith('sk-ant-'):
            print("✗ Anthropic API key format invalid")
            return False
        
        print("✓ API key format valid")
        print("ℹ Skipping actual API test to avoid charges")
    
    else:
        print(f"✗ Unknown provider: {provider}")
        return False
    
    return True

def test_plugin_file():
    """Test plugin file exists and is valid"""
    print("\nTesting plugin file...")
    
    plugin_file = Path("gimp_ai_plugin.py")
    if not plugin_file.exists():
        print("✗ Plugin file not found: gimp_ai_plugin.py")
        return False
    
    try:
        with open(plugin_file, 'r') as f:
            content = f.read()
        
        # Check for key components
        required_components = [
            'class GimpAIPlugin',
            'do_query_procedures',
            'run_inpaint',
            'run_remove_object',
            'run_enhance',
            'Gimp.main'
        ]
        
        for component in required_components:
            if component in content:
                print(f"  ✓ {component}")
            else:
                print(f"  ✗ {component} - missing")
                return False
        
        print("✓ Plugin file structure valid")
        return True
        
    except IOError:
        print("✗ Cannot read plugin file")
        return False

def main():
    """Run all tests"""
    print("GIMP AI Plugin Test Suite")
    print("=" * 40)
    
    all_passed = True
    
    # Test dependencies
    if not test_dependencies():
        all_passed = False
    
    # Test plugin file
    if not test_plugin_file():
        all_passed = False
    
    # Test configuration
    config = test_config_file()
    
    # Test API connectivity
    if config and not test_api_connectivity(config):
        all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("✓ All tests passed! Plugin should work correctly.")
        print("\nNext steps:")
        print("1. Install the plugin using install.py")
        print("2. Configure API keys in GIMP: Filters > AI > AI Plugin Settings")
        print("3. Test with a small image selection")
    else:
        print("✗ Some tests failed. Please fix issues before using the plugin.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())