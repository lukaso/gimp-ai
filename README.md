# GIMP AI Plugin

A Python plugin for GIMP 3.0+ that integrates with Large Language Models (LLMs) to provide AI-powered image editing capabilities including inpainting, object removal, and image enhancement.

## Features

- **AI Inpainting**: Fill selected areas intelligently using AI with text prompts
- **Object Removal**: Remove unwanted objects from images with AI-powered background reconstruction
- **Image Enhancement**: Enhance image quality, colors, and details using AI
- **Multi-LLM Support**: Compatible with OpenAI, Anthropic, and other LLM providers

## Requirements

- GIMP 3.0.4 or 3.1.2+
- Internet connection for LLM API calls
- **No external Python dependencies!** Uses only built-in modules

## Installation

1. **Run the installation script:**
   ```bash
   python3 install_simple.py
   ```

2. **Alternative: Manual installation - Copy plugin to GIMP plugins directory:**
   
   On macOS:
   ```bash
   cp gimp_ai_plugin.py ~/Library/Application\ Support/GIMP/3.0/plug-ins/
   chmod +x ~/Library/Application\ Support/GIMP/3.0/plug-ins/gimp_ai_plugin.py
   ```
   
   On Linux:
   ```bash
   cp gimp_ai_plugin.py ~/.config/GIMP/3.0/plug-ins/
   chmod +x ~/.config/GIMP/3.0/plug-ins/gimp_ai_plugin.py
   ```
   
   On Windows:
   ```bash
   copy gimp_ai_plugin.py "%APPDATA%\GIMP\3.0\plug-ins\"
   ```

3. **Restart GIMP**

## Configuration

1. Open GIMP
2. Go to `Filters > AI > AI Plugin Settings`
3. Configure your API key for your chosen LLM provider (OpenAI or Anthropic)

## Usage

### AI Inpainting
1. Open an image in GIMP
2. Make a selection of the area you want to inpaint
3. Go to `Filters > AI > AI Inpaint Selection`
4. Enter a text prompt describing what should fill the area
5. Click OK and wait for the AI to process

### Object Removal
1. Open an image in GIMP
2. Select the object you want to remove
3. Go to `Filters > AI > AI Remove Object`
4. Wait for the AI to remove the object and fill the background

### Image Enhancement
1. Open an image in GIMP
2. Go to `Filters > AI > AI Enhance Image`
3. Enter a prompt describing the enhancement (e.g., "make colors more vibrant")
4. Wait for the AI to enhance the image

## API Providers

The plugin supports multiple LLM providers:

- **OpenAI**: GPT-4 Vision and DALL-E 3
- **Anthropic**: Claude with vision capabilities
- **Custom endpoints**: Any compatible API endpoint

## Development

This plugin is built using the GIMP 3.x Python API with GObject Introspection. The main components are:

- `gimp_ai_plugin.py`: Main plugin file
- `requirements.txt`: Python dependencies
- Image processing pipeline for LLM integration
- GTK-based user interface dialogs

## License

MIT License - see LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with GIMP 3.x
5. Submit a pull request

## Troubleshooting

- Ensure GIMP 3.0+ is installed
- Check that Python dependencies are installed in the correct environment
- Verify the plugin file has execute permissions
- Check GIMP's Error Console for detailed error messages