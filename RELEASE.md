# Release Process

This document explains the release process for the GIMP AI Plugin.

## Overview

Releases are **automated via GitHub Actions**. When a PR is merged to `main`, the workflow:
1. Bumps the version based on PR labels (`major`, `minor`, or `patch`)
2. Commits the version bump and creates a git tag
3. Builds the release package using `build_release.py`
4. Creates a GitHub release with the ZIP file attached

## Automated Release Process (Recommended)

### Step 1: Label Your PR

Before merging a PR to `main`, add a version bump label:
- **`major`** - Breaking changes (e.g., 0.8.0 → 1.0.0)
- **`minor`** - New features, default if no label (e.g., 0.8.0 → 0.9.0)
- **`patch`** - Bug fixes (e.g., 0.8.0 → 0.8.1)

### Step 2: Merge the PR

When you merge the PR to `main`, the GitHub Actions workflow automatically:
1. Detects the version bump type from labels
2. Runs `tools/bump_version.py` to update the VERSION in `gimp-ai-plugin.py`
3. Commits the version bump
4. Creates and pushes a git tag (e.g., `v0.9.0`)
5. Runs `build_release.py` to create the release ZIP
6. Creates a GitHub release with the ZIP attached

### Step 3: Review the Release

After the workflow completes:
1. Go to the repository's [Releases page](https://github.com/lukaso/gimp-ai/releases)
2. Review the auto-generated release notes
3. Edit if needed to add highlights or clarifications
4. The release ZIP is already attached and ready for download

That's it! The release is published automatically.

## Manual Release Process (Fallback)

If you need to create a release manually (e.g., workflow issues):

### Building the Release Package

Run the build script to create a distributable ZIP package:

```bash
python3 build_release.py
```

This creates `dist/gimp-ai-plugin-vX.X.X.zip` containing:
- The `gimp-ai-plugin/` folder with both required Python files
- Complete documentation (INSTALL.md, README.md, TROUBLESHOOTING.md)
- Automated installer script (`install_plugin.py`)
- Quick start guide (QUICK_START.txt)

### Manual Release Steps

1. **Bump the version manually**:
   ```bash
   python3 tools/bump_version.py --type minor  # or major/patch
   ```

2. **Commit and tag**:
   ```bash
   NEW_VERSION=$(grep VERSION gimp-ai-plugin.py | grep -oP "\d+\.\d+\.\d+")
   git add gimp-ai-plugin.py
   git commit -m "chore(release): bump version to v$NEW_VERSION"
   git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"
   git push origin main
   git push origin "v$NEW_VERSION"
   ```

3. **Build release package**:
   ```bash
   python3 build_release.py
   ```

4. **Create release on GitHub**:
   - Go to repository → Releases → "Create a new release"
   - Select the tag you just created
   - Use the template below for release notes
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

## The build_release.py Script

The `build_release.py` script is used by both the automated workflow and manual release process. It:

1. **Extracts the version** from `gimp-ai-plugin.py` (reads the VERSION constant)
2. **Creates a clean build directory** in `dist/`
3. **Copies plugin files** (`gimp-ai-plugin.py` and `coordinate_utils.py`) into a `gimp-ai-plugin/` subdirectory
4. **Copies documentation** (INSTALL.md, README.md, TROUBLESHOOTING.md, CHANGELOG.md, LICENSE)
5. **Includes the installer** (`install_plugin.py`)
6. **Generates QUICK_START.txt** with installation instructions
7. **Creates a ZIP file** named `gimp-ai-plugin-vX.X.X.zip`

### When build_release.py is Called

- **Automatically**: By the GitHub Actions workflow (`.github/workflows/bump-and-release.yml`) when a PR is merged to main
- **Manually**: By developers testing the release process or creating manual releases

The script is designed to be idempotent and safe to run multiple times.

## Version Bumping

Version management is handled by `tools/bump_version.py`, which:
- Reads the current VERSION from `gimp-ai-plugin.py`
- Increments it based on the bump type (major/minor/patch)
- Updates the VERSION constant in `gimp-ai-plugin.py`
- Prints the new version to stdout

The VERSION constant in `gimp-ai-plugin.py` is the **single source of truth** for the plugin version.

> **Note**: If the VERSION constant doesn't exist yet in `gimp-ai-plugin.py`, you'll need to add it first:
> ```python
> VERSION = "0.8.0"
> ```
> Place it near the top of the file after the imports. The `build_release.py` script has a fallback to "0.8.0-beta" if VERSION is not found, but the workflow requires it for automated version bumping.

### Usage

```bash
# Bump patch version (0.8.0 → 0.8.1)
python3 tools/bump_version.py --type patch

# Bump minor version (0.8.0 → 0.9.0) - default
python3 tools/bump_version.py --type minor

# Bump major version (0.8.0 → 1.0.0)
python3 tools/bump_version.py --type major
```

The script modifies `gimp-ai-plugin.py` in place and outputs the new version number.

## Developer Tools

All release-related tools are located in the `tools/` directory:

- **`tools/bump_version.py`** - Version bumping script (used by workflow and manual releases)

Main release script in the root:

- **`build_release.py`** - Package builder (called by workflow, also used manually)

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

### Testing the Build Script

Before merging a PR that will trigger a release, test locally:

1. **Test version bumping**:
   ```bash
   # Dry run - see what would change
   python3 tools/bump_version.py --type minor
   # Check the version changed in gimp-ai-plugin.py
   grep VERSION gimp-ai-plugin.py
   # Revert if testing
   git checkout gimp-ai-plugin.py
   ```

2. **Test package building**:
   ```bash
   python3 build_release.py
   ```

3. **Verify ZIP contents**:
   ```bash
   unzip -l dist/gimp-ai-plugin-v*.zip
   ```

4. **Test the automated installer**:
   ```bash
   cd /tmp
   unzip /path/to/dist/gimp-ai-plugin-v*.zip
   python3 install_plugin.py
   ```

5. **Verify all documentation files are present and up-to-date**

### Testing the Workflow

To test the automated workflow without creating a real release:
1. Create a test branch off `main`
2. Make a small change
3. Open a PR to a test branch (not `main`)
4. The workflow won't run (it only runs on merges to `main`)
5. Review the workflow file to ensure all steps make sense

## Release Checklist

### For Automated Releases (Normal Process)

- [ ] PR has clear description of changes
- [ ] PR is labeled with version bump type (`major`, `minor`, or `patch`)
- [ ] CHANGELOG.md is updated with changes
- [ ] All tests pass
- [ ] Merge PR to `main`
- [ ] Wait for GitHub Actions workflow to complete
- [ ] Review the auto-generated release on GitHub
- [ ] Edit release notes if needed
- [ ] Verify ZIP is attached and has correct contents

### For Manual Releases (Fallback)

- [ ] Bump version with `tools/bump_version.py`
- [ ] Update CHANGELOG.md
- [ ] Commit version bump
- [ ] Create and push git tag
- [ ] Build package with `build_release.py`
- [ ] Test the automated installer
- [ ] Verify ZIP contains all required files
- [ ] Create GitHub release manually
- [ ] Upload ZIP file as release asset
- [ ] Publish release

## Workflow File Location

The automated release workflow is defined in:
```
.github/workflows/bump-and-release.yml
```

This workflow requires:
- **Trigger**: PR merged to `main`
- **Permissions**: `contents: write` (for creating tags and releases)
- **Token**: Uses `RELEASE_PUBLISH_TOKEN` secret or falls back to `github.token`

## Troubleshooting

### Workflow Doesn't Run

- Check that PR was merged to `main` (not just closed)
- Verify workflow file syntax with GitHub's workflow validator
- Check repository Actions settings (Actions must be enabled)

### Build Fails in Workflow

- Test `build_release.py` locally first
- Check that all required files exist in the repository
- Verify Python 3.x is available in the workflow environment

### Version Bump Fails

- Ensure `gimp-ai-plugin.py` contains a VERSION constant
- Check that VERSION is in the format: `VERSION = "X.Y.Z"`
- Verify `tools/bump_version.py` runs locally without errors

### Release ZIP is Missing Files

- Check `build_release.py` script for list of included files
- Ensure all documentation files are committed to the repository
- Verify the script completes without errors
