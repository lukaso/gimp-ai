#!/usr/bin/env python3
"""
Installation script for GIMP AI Plugin
Automatically installs the plugin to the correct GIMP plugins directory
"""

import os
import sys
import platform
import shutil
import subprocess
from pathlib import Path

def get_gimp_plugins_dir():
    """Get the GIMP plugins directory for the current platform"""
    system = platform.system()
    
    if system == "Windows":
        # Windows: %APPDATA%\GIMP\3.0\plug-ins\
        appdata = os.environ.get('APPDATA')
        if appdata:
            return os.path.join(appdata, 'GIMP', '3.0', 'plug-ins')
    
    elif system == "Darwin":  # macOS
        # macOS: ~/Library/Application Support/GIMP/3.0/plug-ins/
        home = os.path.expanduser('~')
        return os.path.join(home, 'Library', 'Application Support', 'GIMP', '3.0', 'plug-ins')
    
    elif system == "Linux":
        # Linux: ~/.config/GIMP/3.0/plug-ins/
        home = os.path.expanduser('~')
        return os.path.join(home, '.config', 'GIMP', '3.0', 'plug-ins')
    
    return None

def install_plugin():
    """Install the plugin to GIMP plugins directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_file = os.path.join(current_dir, 'gimp_ai_plugin.py')
    
    if not os.path.exists(plugin_file):
        print("Error: gimp_ai_plugin.py not found in current directory")
        return False
    
    plugins_dir = get_gimp_plugins_dir()
    if not plugins_dir:
        print("Error: Could not determine GIMP plugins directory for your system")
        return False
    
    # Create plugins directory if it doesn't exist
    os.makedirs(plugins_dir, exist_ok=True)
    
    # Copy plugin file
    dest_file = os.path.join(plugins_dir, 'gimp_ai_plugin.py')
    shutil.copy2(plugin_file, dest_file)
    
    # Make executable on Unix-like systems
    if platform.system() in ['Darwin', 'Linux']:
        os.chmod(dest_file, 0o755)
    
    print(f"Plugin installed successfully to: {dest_file}")
    return True

def check_dependencies():
    """Check if standard library modules are available (they should be)"""
    standard_modules = ['urllib.request', 'json', 'base64', 'tempfile', 'ssl', 'time']
    missing_modules = []
    
    for module in standard_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print("ERROR: Missing standard library modules:")
        for module in missing_modules:
            print(f"  - {module}")
        print("\nThis indicates a problem with your Python installation.")
        return False
    
    return True

def main():
    print("GIMP AI Plugin Installation Script")
    print("=" * 40)
    
    # Check dependencies
    print("Checking Python standard library...")
    if not check_dependencies():
        print("\nThere appears to be an issue with your Python installation.")
        return 1
    
    print("Standard library modules OK")
    
    # Install plugin
    print("\nInstalling plugin...")
    if install_plugin():
        print("\nInstallation completed successfully!")
        print("\nNext steps:")
        print("1. Restart GIMP if it's currently running")
        print("2. Configure your API keys via: Filters > AI > AI Plugin Settings")
        print("3. Start using AI features via the Filters > AI menu")
        print("\n✨ No additional dependencies needed - uses only built-in Python modules!")
        return 0
    else:
        print("\nInstallation failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())