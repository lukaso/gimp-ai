# Creating a GitHub Release

This document explains how to create a release for the GIMP AI Plugin.

## Building the Release Package

Run the build script to create a distributable ZIP package:

```bash
python3 build_release.py
```

This creates `dist/gimp-ai-plugin-vX.X.X.zip` containing:
- The `gimp-ai-plugin/` folder with both required Python files
- Complete documentation (INSTALL.md, README.md, TROUBLESHOOTING.md)
- Automated installer script (`install_plugin.py`)
- Quick start guide (QUICK_START.txt)

## Creating a GitHub Release

1. **Tag the release**:
   ```bash
   git tag -a v0.8.0-beta -m "Release v0.8.0-beta"
   git push origin v0.8.0-beta
   ```

2. **Create release on GitHub**:
   - Go to repository → Releases → "Create a new release"
   - Select the tag you just created
   - Use the template below for the release notes
   - Upload the ZIP file from `dist/`

## Release Notes Template

```markdown
# GIMP AI Plugin v0.8.0-beta

A Python plugin for GIMP 3.0+ that integrates AI image generation capabilities.

## 📥 Download

Download **gimp-ai-plugin-v0.8.0-beta.zip** below.

## ✨ What's New

[List changes here - see CHANGELOG.md]

## 🚀 Installation (Super Easy!)

### Option 1: Automated Installer (Recommended)

1. Download and extract `gimp-ai-plugin-v0.8.0-beta.zip`
2. Run: `python3 install_plugin.py`
3. Restart GIMP
4. Configure your OpenAI API key in `Filters → AI → Settings`

That's it! The installer handles everything automatically.

### Option 2: Manual Installation

1. Extract the ZIP file
2. Copy the `gimp-ai-plugin` folder to your GIMP plug-ins directory:
   - **Windows**: `%APPDATA%\GIMP\3.0\plug-ins\`
   - **macOS**: `~/Library/Application Support/GIMP/3.0/plug-ins/`
   - **Linux**: `~/.config/GIMP/3.0/plug-ins/`
3. On Linux/macOS: `chmod +x gimp-ai-plugin/gimp-ai-plugin.py`
4. Restart GIMP

See **INSTALL.md** (included in ZIP) for detailed step-by-step instructions.

## 📋 Requirements

- GIMP 3.0.4+ or 3.1.x
- OpenAI API key ([get one here](https://platform.openai.com))
- Internet connection

## 🎨 Features

- **AI Inpainting** - Fill selected areas with AI-generated content
- **Image Generation** - Create new images from text descriptions
- **Layer Composite** - Intelligently blend layers with AI guidance

## 📚 Documentation

Included in the ZIP file:
- **QUICK_START.txt** - Get started in minutes
- **INSTALL.md** - Detailed installation guide
- **README.md** - Feature overview and usage
- **TROUBLESHOOTING.md** - Common issues and solutions

## 🆘 Need Help?

- 📖 Check **TROUBLESHOOTING.md** (in the ZIP)
- 🐛 [Report issues on GitHub](https://github.com/lukaso/gimp-ai/issues)

## 🧪 Beta Notes

This is a **beta release**. We're looking for testers on all platforms!

Please report:
- Installation issues
- Plugin crashes or errors
- Platform-specific problems
- Feature requests

---

**Download the ZIP, run the installer, and start creating with AI!**
```

## Files in the Release Package

When users download `gimp-ai-plugin-v0.8.0-beta.zip`, they get:

```
gimp-ai-plugin-v0.8.0-beta.zip
├── CHANGELOG.md                    # Version history
├── INSTALL.md                      # Complete installation guide
├── LICENSE                         # MIT license
├── QUICK_START.txt                 # Quick reference guide
├── README.md                       # Feature overview
├── TROUBLESHOOTING.md              # Problem solving guide
├── install_plugin.py               # Automated installer script
└── gimp-ai-plugin/                 # Plugin folder (ready to copy)
    ├── gimp-ai-plugin.py          # Main plugin file
    └── coordinate_utils.py         # Required helper functions
```

## What Makes This Easy for Users

1. **Clear file structure** - The `gimp-ai-plugin` folder is ready to copy directly
2. **Automated installer** - Just run `python3 install_plugin.py`
3. **Complete documentation** - Everything needed is in the ZIP
4. **Quick start guide** - Text file for quick reference
5. **Platform support** - Works on Windows, macOS, Linux (including Flatpak)

## Testing a Release

Before publishing:

1. Build the package: `python3 build_release.py`
2. Extract the ZIP in a test directory
3. Try the automated installer
4. Verify all documentation files are present
5. Check file permissions on the Python files

## Upload Checklist

- [ ] Build release package with `build_release.py`
- [ ] Test the automated installer
- [ ] Verify ZIP contains all required files
- [ ] Create git tag
- [ ] Draft GitHub release with proper notes
- [ ] Upload ZIP file as release asset
- [ ] Publish release
