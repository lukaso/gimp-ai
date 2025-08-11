#!/usr/bin/env python3
"""
Simplified installation script for GIMP AI Plugin
Works with GIMP's bundled Python environment
"""

import os
import sys
import platform
import shutil
from pathlib import Path

def get_gimp_plugins_dir():
    """Get the GIMP plugins directory for the current platform"""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        home = os.path.expanduser('~')
        return os.path.join(home, 'Library', 'Application Support', 'GIMP', '3.0', 'plug-ins')
    elif system == "Linux":
        home = os.path.expanduser('~')
        return os.path.join(home, '.config', 'GIMP', '3.0', 'plug-ins')
    elif system == "Windows":
        appdata = os.environ.get('APPDATA')
        if appdata:
            return os.path.join(appdata, 'GIMP', '3.0', 'plug-ins')
    
    return None

def install_plugin():
    """Install the plugin to GIMP plugins directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_file = os.path.join(current_dir, 'gimp_ai_plugin.py')
    
    if not os.path.exists(plugin_file):
        print("❌ Error: gimp_ai_plugin.py not found in current directory")
        return False
    
    plugins_dir = get_gimp_plugins_dir()
    if not plugins_dir:
        print("❌ Error: Could not determine GIMP plugins directory for your system")
        return False
    
    print(f"📁 GIMP plugins directory: {plugins_dir}")
    
    # Create plugins directory if it doesn't exist
    try:
        os.makedirs(plugins_dir, exist_ok=True)
        print("✅ Plugins directory ready")
    except PermissionError:
        print("❌ Error: Permission denied creating plugins directory")
        return False
    
    # Copy plugin file
    dest_file = os.path.join(plugins_dir, 'gimp_ai_plugin.py')
    try:
        shutil.copy2(plugin_file, dest_file)
        print(f"✅ Plugin copied to: {dest_file}")
    except (IOError, PermissionError) as e:
        print(f"❌ Error copying plugin: {e}")
        return False
    
    # Make executable on Unix-like systems
    if platform.system() in ['Darwin', 'Linux']:
        try:
            os.chmod(dest_file, 0o755)
            print("✅ Plugin made executable")
        except PermissionError:
            print("⚠️  Warning: Could not make plugin executable")
    
    return True

def create_sample_config():
    """Create a sample configuration file"""
    config_dir = os.path.expanduser("~/.config/gimp-ai")
    config_file = os.path.join(config_dir, "config.json")
    
    if os.path.exists(config_file):
        print("ℹ️  Configuration file already exists")
        return
    
    try:
        os.makedirs(config_dir, exist_ok=True)
        
        sample_config = """{
    "api_provider": "openai",
    "openai": {
        "api_key": "your-openai-api-key-here",
        "model": "gpt-4-vision-preview"
    },
    "anthropic": {
        "api_key": "your-anthropic-api-key-here",
        "model": "claude-3-sonnet-20240229"
    },
    "settings": {
        "image_quality": 0.85,
        "max_image_size": 1024,
        "timeout": 30
    }
}"""
        
        with open(config_file, 'w') as f:
            f.write(sample_config)
        
        print(f"✅ Sample config created: {config_file}")
        
    except (IOError, PermissionError) as e:
        print(f"⚠️  Could not create sample config: {e}")

def main():
    print("🎨 GIMP AI Plugin - Simple Installation")
    print("=" * 45)
    
    # Install plugin
    print("\n📦 Installing plugin...")
    if not install_plugin():
        print("\n❌ Installation failed!")
        return 1
    
    # Create sample config
    print("\n⚙️  Setting up configuration...")
    create_sample_config()
    
    print("\n" + "=" * 45)
    print("✅ Installation completed!")
    
    print("\n📋 Next steps:")
    print("1. 🔄 Restart GIMP if it's currently running")
    print("2. 🔑 Configure API keys via: Filters > AI > AI Plugin Settings")
    print("3. 🖼️  Test with a small image selection")
    
    print("\n✨ No additional dependencies required!")
    print("   This plugin uses only built-in Python modules.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())