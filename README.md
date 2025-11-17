# GIMP AI Plugin Beta

A Python plugin for GIMP 3.0.4+ that integrates AI image generation capabilities directly into GIMP. This is a **beta release** seeking testers on all platforms.

Currently supports **OpenAI's gpt-image-1** models for inpainting and image generation. Future plans include support for additional AI providers.

## ✨ Features

- **🎨 AI Inpainting**: Fill selected areas with AI-generated content using text prompts and selection masks
- **🖼️ AI Image Generation**: Create new images from text descriptions as new layers
- **🔄 AI Layer Composite**: Intelligently blend AI content into existing images
- **⚙️ Easy Configuration**: Built-in settings dialog, no external config files needed

## 📋 Requirements

- **GIMP 3.0.4 or newer** (all GIMP 3.X versions from 3.0.4 onwards)
- **Internet connection** for AI API calls
- **OpenAI API key** (get one at [platform.openai.com](https://platform.openai.com))
- **Zero external dependencies** - uses only Python standard library + GIMP APIs

## 🚀 Installation

**Just 2 files to copy!** No external dependencies or complex setup.

### Easiest Way: Automated Installer 🎯

1. **Download** the [latest release ZIP](https://github.com/lukaso/gimp-ai/releases)
2. **Extract** the ZIP file
3. **Run** the installer: `python3 install_plugin.py`
4. **Restart GIMP** and configure your API key

Done! The installer handles everything automatically.

### Manual Install (3 Simple Steps)

1. **Download 2 files**: `gimp-ai-plugin.py` and `coordinate_utils.py`
2. **Create folder**: Make a `gimp-ai-plugin` folder in your GIMP plug-ins directory
3. **Copy files**: Put both files in that folder, restart GIMP

### Need Help? 📖

**👉 [Read the Complete Installation Guide (INSTALL.md)](INSTALL.md) 👈**

The installation guide includes:

- ✅ Step-by-step instructions for beginners
- ✅ How to find your GIMP plugin directory on Windows/Mac/Linux
- ✅ Screenshots and visual examples
- ✅ How to get and configure your OpenAI API key
- ✅ Troubleshooting for "Filter → AI not found" issues

### Quick Reference

**Plugin folder location by OS** (replace `3.0` with your GIMP version):

- **Windows**: `%APPDATA%\GIMP\3.0\plug-ins\gimp-ai-plugin\`
- **macOS**: `~/Library/Application Support/GIMP/3.0/plug-ins/gimp-ai-plugin/`
- **Linux**: `~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/`

> **Note**: The automated installer will detect all compatible GIMP versions (3.0.4+) and let you choose which one to install to.

**Required folder structure:**

```
plug-ins/
└── gimp-ai-plugin/          ← Create this folder
    ├── gimp-ai-plugin.py    ← Required file #1
    └── coordinate_utils.py  ← Required file #2
```

**After copying files:**

- Linux/macOS: Run `chmod +x gimp-ai-plugin.py` in the folder
- Restart GIMP completely
- Look for `Filters → AI` in the menu

## ⚙️ Configuration

1. **Get an OpenAI API key** from [platform.openai.com](https://platform.openai.com)
2. In GIMP: go to `Filters → AI → Settings`
3. **Paste your API key** (starts with `sk-`)
4. Click OK - it's saved automatically!

> **First time?** See [INSTALL.md](INSTALL.md) for detailed API key instructions.

## 🎨 Usage

### AI Inpainting

**Fill selected areas with AI-generated content using text prompts**

1. **Open image** in GIMP
2. **Make a selection** of area to inpaint (or no selection for full image)
3. **Go to** `Filters → AI → Inpainting`
4. **Choose processing mode**:
   - **🔍 Focused (High Detail)**: Best for small edits, maximum resolution, selection required
   - **🖼️ Full Image (Consistent)**: Best for large changes, works with or without selection
5. **Enter prompt** (e.g., "blue sky with clouds", "remove the object")
6. **Result**: New layer with AI-generated content, automatically masked to selection area

**Selection Mask Behavior:**

- **Soft masks**: AI can redraw content _outside_ the selection to maintain visual coherence
- **With selection**: Final result is masked to show only within selected area, but AI considers surrounding context
- **No selection** (Full Image mode): Entire image is processed and replaced
- **Smart feathering**: Automatic edge blending for seamless integration

⚠️ **Important**: The AI model may modify areas outside your selection to create coherent results. Only the final output is masked to your selection.

### AI Image Generation

1. **Open or create** any GIMP document
2. **Go to** `Filters → AI → Image Generator`
3. **Enter prompt** (e.g., "a red dragon on mountain")
4. **New layer created** with generated image

### AI Layer Composite

**Intelligently combines multiple visible layers using AI guidance**

1. **Set up your layers**:

   - **Bottom layer** = base/background (what gets modified)
   - **Upper layers** = elements to integrate (people, objects, etc.)
   - Make sure desired layers are **visible**

2. **Go to** `Filters → AI → Layer Composite`

3. **Enter integration prompt** (e.g., "blend the person naturally into the forest scene")

4. **Choose mode**:

   - **✅ Include selection mask**: Uses selection on base layer to limit where changes occur
   - **❌ No mask**: AI can modify the entire base layer to integrate upper layers

5. **Result**: A new layer is created, taking the base layer and intelligently modifying it to incorporate all visible layers

## 🐛 Find Issues?

- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) first
- Report at: [GitHub Issues](https://github.com/yourusername/gimp-ai/issues)

## 📚 Documentation

- **[INSTALL.md](INSTALL.md)** - Complete installation guide for users
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[CHANGELOG.md](CHANGELOG.md)** - What's new and known issues
- **[TODO.md](TODO.md)** - Development roadmap
- **[RELEASE.md](RELEASE.md)** - Release process for maintainers

## 🔧 For Developers

### Creating Releases

Releases are automated via GitHub Actions. See **[RELEASE.md](RELEASE.md)** for details.

**Quick overview:**

- Label PRs with `major`, `minor`, or `patch` for version bumps
- Merge to `main` triggers automated release creation
- The workflow builds the package and creates a GitHub release

### Tools

- **`build_release.py`** - Creates distributable ZIP packages (used by workflow)
- **`tools/bump_version.py`** - Bumps version in `gimp-ai-plugin.py` (used by workflow)

## ⚖️ License

MIT License - see [LICENSE](LICENSE) file for details
