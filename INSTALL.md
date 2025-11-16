# Installation Guide for GIMP AI Plugin

**Complete step-by-step installation instructions for beginners**

This guide will walk you through installing the GIMP AI Plugin, even if you've never installed a GIMP plugin before.

---

## 📋 What You'll Need

Before starting, make sure you have:

1. ✅ **GIMP 3.0.4 or newer** installed (download from [gimp.org](https://www.gimp.org))
2. ✅ **An OpenAI API key** (get one at [platform.openai.com](https://platform.openai.com))
3. ✅ **Internet connection** for downloading files and using AI features

> **Note**: This plugin is **beta software** and currently only works with GIMP 3.0.4+ or 3.1.x

---

## 🎯 Quick Overview

The installation process is simple:

**EASIEST METHOD (Recommended for beginners):**
1. Download the release ZIP
2. Extract it
3. Run: `python3 install_plugin.py`
4. Restart GIMP and configure your API key

**The automated installer does everything for you!**

**MANUAL METHOD:**
1. Download 2 files
2. Create a folder in GIMP's plugin directory
3. Copy the files to that folder
4. Restart GIMP
5. Configure your API key

**That's it!** No complex dependencies, no Python packages to install.

---

## 📥 Step 1: Download the Plugin Files

You need **exactly 2 files**:

1. **`gimp-ai-plugin.py`** - The main plugin file
2. **`coordinate_utils.py`** - Helper functions (required)

### Option A: Download Release Package with Automated Installer (Easiest!)

1. Go to the [Releases page](https://github.com/lukaso/gimp-ai/releases)
2. Download the latest `gimp-ai-plugin-vX.X.X.zip` file
3. Extract the ZIP file
4. Run the automated installer:
   ```bash
   python3 install_plugin.py
   ```
5. Follow the on-screen instructions - it will do everything for you!

> **Using the automated installer?** You can skip to [Step 7: Configure Your API Key](#-step-7-configure-your-api-key) after running it!

### Option B: Download from GitHub Release (Manual Install)

1. Go to the [Releases page](https://github.com/lukaso/gimp-ai/releases)
2. Download the latest `gimp-ai-plugin-vX.X.X.zip` file
3. Extract the ZIP file - you'll see a `gimp-ai-plugin` folder containing both files

### Option C: Download Individual Files

1. Go to the [GitHub repository](https://github.com/lukaso/gimp-ai)
2. Click on `gimp-ai-plugin.py` → Click "Raw" → Save the file (Ctrl+S or Cmd+S)
3. Go back and click on `coordinate_utils.py` → Click "Raw" → Save the file

> **Important**: Keep these two files together - the plugin won't work without both!

---

## 📁 Step 2: Find Your GIMP Plugin Directory

The plugin directory location depends on your operating system.

### Windows

1. Press `Windows + R` to open the Run dialog
2. Type `%APPDATA%\GIMP` and press Enter
3. You should see a folder named `3.0` or `3.1` (depending on your GIMP version)
4. Open that folder, then open the `plug-ins` folder

**Full path example**: `C:\Users\YourName\AppData\Roaming\GIMP\3.0\plug-ins\`

> **Tip**: If you can't find the `AppData` folder, make sure "Hidden items" is checked in Windows Explorer's View menu.

### macOS

1. Open Finder
2. Press `Cmd + Shift + G` (Go to Folder)
3. Enter: `~/Library/Application Support/GIMP/3.0/plug-ins/` (or `3.1` for GIMP 3.1)
4. Press Enter

**Full path**: `/Users/YourName/Library/Application Support/GIMP/3.0/plug-ins/`

> **Tip**: If the `Library` folder is hidden, press `Cmd + Shift + .` (period) in Finder to show hidden files.

### Linux

The plugin directory is at: `~/.config/GIMP/3.0/plug-ins/` (or `3.1`)

You can open it in your file manager or terminal:

```bash
cd ~/.config/GIMP/3.0/plug-ins/
```

**If the directory doesn't exist**, create it:

```bash
mkdir -p ~/.config/GIMP/3.0/plug-ins/
```

### Flatpak GIMP (Linux)

If you installed GIMP via Flatpak, the directory is different:

```bash
~/.var/app/org.gimp.GIMP/config/GIMP/3.0/plug-ins/
```

---

## 📂 Step 3: Create the Plugin Folder

Inside your GIMP `plug-ins` directory, you need to create a **subdirectory** named `gimp-ai-plugin`.

### Visual Directory Structure

Your final structure should look like this:

```
plug-ins/
└── gimp-ai-plugin/          ← Create this folder
    ├── gimp-ai-plugin.py    ← Copy this file here
    └── coordinate_utils.py  ← Copy this file here
```

### How to Create the Folder

**Windows:**
1. Right-click in the `plug-ins` folder
2. Select "New" → "Folder"
3. Name it exactly: `gimp-ai-plugin`

**macOS:**
1. Right-click (or Ctrl+click) in the `plug-ins` folder
2. Select "New Folder"
3. Name it exactly: `gimp-ai-plugin`

**Linux:**
```bash
mkdir ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin
```

> **Important**: The folder name must be exactly `gimp-ai-plugin` (with a hyphen, not underscore).

---

## 📋 Step 4: Copy the Plugin Files

Now copy **both files** you downloaded into the `gimp-ai-plugin` folder you just created.

### Where to Copy:
- **From**: Where you downloaded/extracted the files
- **To**: `plug-ins/gimp-ai-plugin/` (the folder you just created)

### What to Copy:
- ✅ `gimp-ai-plugin.py`
- ✅ `coordinate_utils.py`

Both files must be in the same `gimp-ai-plugin` folder!

---

## 🔧 Step 5: Set File Permissions (Linux/macOS Only)

**Windows users can skip this step.**

On Linux and macOS, you need to make the main plugin file executable:

### macOS:
```bash
chmod +x ~/Library/Application\ Support/GIMP/3.0/plug-ins/gimp-ai-plugin/gimp-ai-plugin.py
```

### Linux:
```bash
chmod +x ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/gimp-ai-plugin.py
```

---

## 🔄 Step 6: Restart GIMP

If GIMP is currently running:
1. **Save your work**
2. **Quit GIMP completely** (don't just close windows - actually quit the application)
3. **Start GIMP again**

> **Important**: You must fully restart GIMP for it to detect the new plugin.

---

## 🔑 Step 7: Configure Your API Key

Now you'll set up your OpenAI API key so the plugin can access AI features.

### Get Your API Key

1. Go to [platform.openai.com](https://platform.openai.com)
2. Sign up or log in
3. Click on your profile icon (top right) → "API Keys"
4. Click "Create new secret key"
5. **Copy the key** (it starts with `sk-` and is very long)
6. **Save it somewhere safe** - you can only see it once!

> **Note**: You'll need to add credits to your OpenAI account to use the API. Check pricing at [openai.com/pricing](https://openai.com/pricing).

### Enter Your API Key in GIMP

**Method 1 (Recommended):**
1. In GIMP, go to `Filters` → `AI` → `Settings`
2. Paste your API key in the "OpenAI API Key" field
3. Click OK

**Method 2 (If Settings menu isn't available):**
1. Try any AI feature (e.g., `Filters` → `AI` → `Image Generator`)
2. You'll see an error dialog about missing API key
3. Click "Configure" in the error dialog
4. Paste your API key
5. Click OK

The plugin will **automatically save** your API key in GIMP's preferences - you only need to enter it once!

---

## ✅ Step 8: Test the Plugin

Let's verify everything is working:

1. **Open any image** in GIMP (or create a new one)
2. **Look for the AI menu**: `Filters` → `AI`
3. You should see these options:
   - 🎨 **Inpainting** - Fill areas with AI-generated content
   - 🖼️ **Image Generator** - Create new images from text
   - 🔄 **Layer Composite** - Blend layers with AI
   - ⚙️ **Settings** - Configure API keys

### Quick Test:

1. Go to `Filters` → `AI` → `Image Generator`
2. Enter a simple prompt like "blue sky with clouds"
3. Click OK
4. After a few seconds, you should see a new layer with AI-generated content!

---

## ❓ Troubleshooting

### I don't see "Filters → AI" in GIMP

**Check these things:**

1. ✅ **Did you restart GIMP completely?** (Quit and reopen)
2. ✅ **Are both files in the right place?**
   ```
   plug-ins/gimp-ai-plugin/gimp-ai-plugin.py
   plug-ins/gimp-ai-plugin/coordinate_utils.py
   ```
3. ✅ **Is the folder named exactly `gimp-ai-plugin`?** (not `gimp_ai_plugin` or `gimp-ai`)
4. ✅ **Do you have GIMP 3.0.4 or newer?** Check: `Help` → `About GIMP`
5. ✅ **Linux/macOS: Did you make the file executable?** (Step 5)

### "No API Key Configured" Error

1. Make sure you've entered your API key (Step 7)
2. The key should start with `sk-`
3. Check for extra spaces when copying/pasting
4. Try removing and re-entering the key

### "Authentication Failed" Error

1. Verify your API key is correct at [platform.openai.com](https://platform.openai.com)
2. Make sure your OpenAI account has available credits
3. Test your API key in OpenAI's playground first

### Plugin Causes GIMP to Crash

1. Check `Windows` → `Error Console` in GIMP for error messages
2. Try with a small test image first (under 1024px)
3. Make sure you're using GIMP 3.0.4 or newer

### Still Having Issues?

See the detailed [TROUBLESHOOTING.md](TROUBLESHOOTING.md) guide or report issues at:
https://github.com/lukaso/gimp-ai/issues

---

## 🎉 You're Done!

Congratulations! You've successfully installed the GIMP AI Plugin.

### Next Steps:

- 📖 Read the [README.md](README.md) to learn about all features
- 🎨 Try the **Inpainting** feature on a photo
- 🖼️ Generate some AI images with **Image Generator**
- 📚 Check [CHANGELOG.md](CHANGELOG.md) for what's new

### Getting Help:

- 💬 **Issues**: [GitHub Issues](https://github.com/lukaso/gimp-ai/issues)
- 📖 **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🐛 **Beta Feedback**: We appreciate bug reports and suggestions!

---

## 🔄 Updating the Plugin

To update to a newer version:

1. Download the new plugin files
2. Replace the old files in `plug-ins/gimp-ai-plugin/`
3. Restart GIMP

Your API key and settings will be preserved.

---

## 🗑️ Uninstalling

To remove the plugin:

1. Delete the `gimp-ai-plugin` folder from your plug-ins directory
2. Restart GIMP

Your API key will remain in GIMP's preferences (harmless).

---

**Need more help?** Check out the [TROUBLESHOOTING.md](TROUBLESHOOTING.md) guide!
