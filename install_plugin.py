#!/usr/bin/env python3
"""
Automated installer for GIMP AI Plugin
Works on Windows, macOS, and Linux

This script will:
1. Detect your operating system
2. Find your GIMP plugins directory
3. Copy the plugin files to the correct location
4. Set appropriate permissions
5. Provide next steps

Usage:
    python3 install_plugin.py
"""

import os
import sys
import platform
import shutil
from pathlib import Path


def get_gimp_plugins_dir():
    """Get the GIMP plugins directory for the current platform"""
    system = platform.system()
    
    # Try to detect GIMP 3.1 first, then 3.0
    gimp_versions = ['3.1', '3.0']
    
    if system == "Windows":
        appdata = os.environ.get('APPDATA')
        if appdata:
            for version in gimp_versions:
                path = os.path.join(appdata, 'GIMP', version, 'plug-ins')
                if os.path.exists(os.path.join(appdata, 'GIMP', version)):
                    return path
            # Default to 3.0 if neither exists
            return os.path.join(appdata, 'GIMP', '3.0', 'plug-ins')
    
    elif system == "Darwin":  # macOS
        home = os.path.expanduser('~')
        for version in gimp_versions:
            path = os.path.join(home, 'Library', 'Application Support', 'GIMP', version, 'plug-ins')
            if os.path.exists(os.path.join(home, 'Library', 'Application Support', 'GIMP', version)):
                return path
        # Default to 3.0 if neither exists
        return os.path.join(home, 'Library', 'Application Support', 'GIMP', '3.0', 'plug-ins')
    
    elif system == "Linux":
        home = os.path.expanduser('~')
        
        # Check for Flatpak installation first
        flatpak_base = os.path.join(home, '.var', 'app', 'org.gimp.GIMP', 'config', 'GIMP')
        for version in gimp_versions:
            path = os.path.join(flatpak_base, version, 'plug-ins')
            if os.path.exists(os.path.join(flatpak_base, version)):
                return path
        
        # Check standard installation
        for version in gimp_versions:
            path = os.path.join(home, '.config', 'GIMP', version, 'plug-ins')
            if os.path.exists(os.path.join(home, '.config', 'GIMP', version)):
                return path
        
        # Default to 3.0 if neither exists
        return os.path.join(home, '.config', 'GIMP', '3.0', 'plug-ins')
    
    return None


def find_plugin_files():
    """Find the plugin files in the current directory or parent directory"""
    current_dir = Path(__file__).parent
    
    required_files = ['gimp-ai-plugin.py', 'coordinate_utils.py']
    
    # Check current directory
    all_found = all((current_dir / f).exists() for f in required_files)
    if all_found:
        return current_dir
    
    # Check if we're in a subdirectory (e.g., extracted from ZIP)
    # Look for gimp-ai-plugin subdirectory
    plugin_subdir = current_dir / 'gimp-ai-plugin'
    if plugin_subdir.exists():
        all_found = all((plugin_subdir / f).exists() for f in required_files)
        if all_found:
            return plugin_subdir
    
    return None


def install_plugin():
    """Install the plugin to GIMP plugins directory"""
    
    print("=" * 60)
    print("   GIMP AI Plugin - Automated Installer")
    print("=" * 60)
    print()
    
    # Detect OS
    system = platform.system()
    os_name = {
        'Windows': '🪟 Windows',
        'Darwin': '🍎 macOS',
        'Linux': '🐧 Linux'
    }.get(system, system)
    
    print(f"Detected OS: {os_name}")
    print()
    
    # Find plugin files
    print("📁 Looking for plugin files...")
    source_dir = find_plugin_files()
    
    if not source_dir:
        print("❌ ERROR: Could not find plugin files!")
        print()
        print("Please make sure you have these files:")
        print("  • gimp-ai-plugin.py")
        print("  • coordinate_utils.py")
        print()
        print("They should be in the same directory as this installer.")
        return False
    
    plugin_file = source_dir / 'gimp-ai-plugin.py'
    utils_file = source_dir / 'coordinate_utils.py'
    
    print(f"✅ Found plugin files in: {source_dir}")
    print()
    
    # Get GIMP plugins directory
    print("🔍 Finding GIMP plugins directory...")
    plugins_dir = get_gimp_plugins_dir()
    
    if not plugins_dir:
        print("❌ ERROR: Could not determine GIMP plugins directory")
        print()
        print("Please install GIMP 3.0.4+ first, or install manually:")
        print("See INSTALL.md for manual installation instructions.")
        return False
    
    print(f"✅ GIMP plugins directory: {plugins_dir}")
    print()
    
    # Create plugins directory if it doesn't exist
    try:
        os.makedirs(plugins_dir, exist_ok=True)
    except PermissionError:
        print("❌ ERROR: Permission denied creating plugins directory")
        print(f"   Path: {plugins_dir}")
        print()
        print("Try running as administrator/sudo, or install manually.")
        return False
    
    # Create plugin subdirectory
    plugin_dest_dir = os.path.join(plugins_dir, 'gimp-ai-plugin')
    print(f"📂 Creating plugin directory: {plugin_dest_dir}")
    
    try:
        os.makedirs(plugin_dest_dir, exist_ok=True)
        print("✅ Plugin directory created")
    except PermissionError:
        print("❌ ERROR: Permission denied creating plugin subdirectory")
        return False
    
    print()
    
    # Copy plugin files
    print("📋 Copying plugin files...")
    
    try:
        dest_plugin = os.path.join(plugin_dest_dir, 'gimp-ai-plugin.py')
        dest_utils = os.path.join(plugin_dest_dir, 'coordinate_utils.py')
        
        shutil.copy2(plugin_file, dest_plugin)
        print(f"  ✅ gimp-ai-plugin.py")
        
        shutil.copy2(utils_file, dest_utils)
        print(f"  ✅ coordinate_utils.py")
        
    except (IOError, PermissionError) as e:
        print(f"❌ ERROR copying files: {e}")
        return False
    
    print()
    
    # Set executable permissions on Unix-like systems
    if platform.system() in ['Darwin', 'Linux']:
        print("🔐 Setting file permissions...")
        try:
            os.chmod(dest_plugin, 0o755)
            print("✅ Plugin made executable")
        except PermissionError:
            print("⚠️  Warning: Could not make plugin executable")
            print("   You may need to run: chmod +x " + dest_plugin)
    
    print()
    print("=" * 60)
    print("✅ Installation completed successfully!")
    print("=" * 60)
    
    return True


def print_next_steps():
    """Print instructions for next steps"""
    print()
    print("📋 NEXT STEPS:")
    print()
    print("1. 🔄 Restart GIMP completely (quit and reopen)")
    print()
    print("2. 🔍 Check for the AI menu:")
    print("   In GIMP: Filters → AI")
    print()
    print("3. 🔑 Configure your API key:")
    print("   a. Get an OpenAI API key from: https://platform.openai.com")
    print("   b. In GIMP: Filters → AI → Settings")
    print("   c. Paste your API key (starts with 'sk-')")
    print("   d. Click OK")
    print()
    print("4. 🎨 Test the plugin:")
    print("   Try: Filters → AI → Image Generator")
    print("   Enter a prompt like: 'blue sky with clouds'")
    print()
    print("=" * 60)
    print()
    print("📖 For more help:")
    print("   • Installation guide: INSTALL.md")
    print("   • Troubleshooting: TROUBLESHOOTING.md")
    print("   • Report issues: https://github.com/lukaso/gimp-ai/issues")
    print()
    print("🎉 Enjoy using GIMP AI Plugin!")


def main():
    """Main entry point"""
    try:
        success = install_plugin()
        
        if success:
            print_next_steps()
            return 0
        else:
            print()
            print("Installation failed. Please try manual installation:")
            print("See INSTALL.md for detailed instructions.")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("Please try manual installation. See INSTALL.md for instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
