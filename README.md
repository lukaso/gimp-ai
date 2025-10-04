# GIMP AI Plugin v0.8 Beta

A Python plugin for GIMP 3.0+ that integrates AI image generation capabilities directly into GIMP. This is a **beta release** seeking testers on all platforms.

Currently supports **OpenAI's gpt-image-1** models for inpainting and image generation. Future plans include support for additional AI providers.

## ✨ Features

- **🎨 AI Inpainting**: Fill selected areas with AI-generated content using text prompts and selection masks
- **🖼️ AI Image Generation**: Create new images from text descriptions as new layers
- **🔄 AI Layer Composite**: Intelligently blend AI content into existing images
- **⚙️ Easy Configuration**: Built-in settings dialog, no external config files needed

## 📋 Requirements

- **GIMP 3.0.4+ or 3.1.x** (earlier versions not supported)
- **Internet connection** for AI API calls
- **OpenAI API key** (get one at [platform.openai.com](https://platform.openai.com))
- **Zero external dependencies** - uses only Python standard library + GIMP APIs

## 🚀 Quick Installation

**Just 2 files to copy!** No external dependencies or complex setup.

### 📁 Find Your GIMP Plugin Directory:

- **macOS**: `~/Library/Application Support/GIMP/3.0/plug-ins/` (or 3.1)
- **Linux**: `~/.config/GIMP/3.0/plug-ins/` (or 3.1)
- **Windows**: `%APPDATA%\GIMP\3.0\plug-ins\` (or 3.1)

### 📥 Copy Files:

1. **Create plugin subdirectory**:

   ```bash
   # Create the gimp-ai-plugin directory
   mkdir "~/path/to/plug-ins/gimp-ai-plugin"
   ```

2. **Copy both files** to the subdirectory:

   - `gimp-ai-plugin.py` → `gimp-ai-plugin/gimp-ai-plugin.py`
   - `coordinate_utils.py` → `gimp-ai-plugin/coordinate_utils.py`

3. **Make executable** (Linux/macOS only):

   ```bash
   chmod +x ~/path/to/plug-ins/gimp-ai-plugin/gimp-ai-plugin.py
   ```

4. **Restart GIMP**

### 🎯 Quick Test:

After restart, look for **Filters → AI** in the menu. If you don't see it, check the [troubleshooting guide](TROUBLESHOOTING.md).

## ⚙️ Configuration

1. **Try any AI feature** - you'll be prompted to configure
2. **Enter your OpenAI API key** - it's saved automatically
3. **You're ready to go!**

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

- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[CHANGELOG.md](CHANGELOG.md)** - What's new and known issues
- **[TODO.md](TODO.md)** - Development roadmap

## ⚖️ License

MIT License - see [LICENSE](LICENSE) file for details
