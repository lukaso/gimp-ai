# Changelog

All notable changes to the GIMP AI Plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0-beta] - 2024-10-04

### 🎉 Initial Beta Release

#### Added

- **AI Inpainting**: Fill selected areas with AI-generated content using text prompts

  - Context-aware inpainting that considers surrounding image content
  - Support for complex selections and masks
  - Intelligent coordinate transformation for optimal AI processing

- **AI Image Generation**: Create new images from text descriptions

  - Generates images as new layers in current document
  - Respects GIMP canvas dimensions and aspect ratios
  - Multiple size options with automatic optimization

- **AI Layer Composite**: Intelligently blend new content into existing images

  - Seamless integration of AI-generated content
  - Automatic color and lighting matching
  - Preserves image quality and coherence

- **Settings Management**: User-friendly configuration through GIMP dialogs

  - Secure API key storage in GIMP preferences
  - No external configuration files needed
  - Multiple AI provider support (OpenAI ready, extensible)

- **Robust Processing Pipeline**:

  - Threaded API calls with progress indicators
  - Cancellable operations
  - Memory-efficient image handling
  - Error recovery and user feedback

#### Technical Features

- **Zero External Dependencies**: Uses only Python standard library and GIMP APIs
- **Cross-Platform**: Designed for macOS, Linux, and Windows
- **GIMP 3.x Compatible**: Works with GIMP 3.0.4+ and 3.1.x

#### Known Issues/Limitations

- Debug output still visible in GIMP Console
- Windows and Linux installation paths need validation from users
- Large image processing (>2048px) may be slow on some systems
- Limited to OpenAI
- Resolution limited by OpenAI constraints (1024px, 1536px)

#### Testing Status

- ✅ **macOS**: Fully tested on Apple Silicon and Intel Macs
- ❓ **Linux**: Needs beta testing on Ubuntu/Fedora
- ❓ **Windows**: Needs beta testing on Windows 10/11

### 🔧 Developer Notes

- Plugin architecture supports easy addition of new AI providers
- Coordinate transformation system handles complex image manipulations
- Comprehensive test suite for coordinate calculations
- Modular design for future feature additions

---

## Beta Testing

This is a beta release. Please report:

1. Installation success/failure
2. Plugin visibility in GIMP menus
3. Any crashes or errors
4. Performance with different image sizes
5. General usability feedback

**Report issues at**: [GitHub Issues](https://github.com/yourusername/gimp-ai/issues)

---

### Support

- **Requirements**: GIMP 3.0.4+ or 3.1.x, Internet connection
- **Installation**: Copy 2 files to GIMP plugins directory
- **Configuration**: Use `Filters > AI` in GIMP and chose one of the options, then click `Settings` in the dialog
- **Documentation**: See README.md and TROUBLESHOOTING.md
