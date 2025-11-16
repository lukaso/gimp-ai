# Copilot Instructions

This file provides guidance to GitHub Copilot when working with code in this repository.

## Project Overview

**GIMP AI Plugin** is a Python plugin for GIMP 3.0+ that integrates AI image generation capabilities directly into GIMP. This is a beta release (v0.8) supporting OpenAI's image generation models for inpainting, image generation, and layer compositing.

### Key Features
- **AI Inpainting**: Fill selected areas with AI-generated content using text prompts and selection masks
- **AI Image Generation**: Create new images from text descriptions as new layers
- **AI Layer Composite**: Intelligently blend AI content into existing images
- **Zero External Dependencies**: Uses only Python standard library + GIMP APIs

## Technology Stack

### Languages & Frameworks
- **Python 3.x**: Primary development language (compatible with GIMP's Python interpreter)
- **GIMP 3.0+ API**: Using GObject Introspection (gi) bindings
- **GTK 3.0**: For user interface dialogs and widgets
- **GEGL**: For image processing operations

### Key Libraries (all via gi bindings)
- `gi.repository.Gimp` - GIMP plugin API
- `gi.repository.GimpUi` - GIMP UI components
- `gi.repository.Gtk` - GTK UI toolkit
- `gi.repository.Gegl` - Image processing operations
- Standard library only: `urllib`, `json`, `base64`, `tempfile`, `ssl`

### External APIs
- **OpenAI Image API** (`https://api.openai.com/v1/images/...`)
  - Generations endpoint for creating images
  - Edits endpoint for inpainting

## Architecture

### Core Files

1. **`gimp-ai-plugin.py`** (Main plugin, ~4000 lines)
   - `GimpAIPlugin` class: Main plugin entry point
   - Procedure registration (3 procedures: inpainting, generation, composite)
   - Configuration management (API key storage)
   - UI dialogs (GTK-based settings and progress)
   - OpenAI API communication
   - Image processing pipeline

2. **`coordinate_utils.py`** (Pure math utilities, ~600 lines)
   - **Pure functions with no GIMP dependencies** (unit testable)
   - Coordinate transformations for context extraction
   - Mask calculations
   - Optimal shape selection for OpenAI API (1024×1024, 1536×1024, 1024×1536)
   - Padding and scaling algorithms
   - See `ALGORITHMS.md` for detailed algorithm documentation

3. **`install.py`** / **`install_simple.py`**
   - Installation scripts for copying files to GIMP plugin directories

### Key Design Principles

- **Separation of Concerns**: Pure coordinate math is isolated in `coordinate_utils.py`
- **Stateless Operations**: New layers are created for all results (non-destructive)
- **No External Dependencies**: Only standard library + GIMP APIs to simplify installation
- **Error Resilience**: Graceful handling of API failures and user cancellation

## Coding Guidelines

### Python Style
- **PEP 8 compliant**: Follow standard Python conventions
- **Docstrings**: All functions should have clear docstrings with Args/Returns
- **Type hints**: Not currently used, but acceptable to add for new code
- **Indentation**: 4 spaces (no tabs)
- **Line length**: Prefer ~100 chars, but no strict limit

### GIMP API Patterns
```python
# Always use gi bindings with version requirements
import gi
gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp, GimpUi

# Plugin class must inherit from Gimp.PlugIn
class MyPlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return ["my-procedure-name"]
    
    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(...)
        return procedure
```

### Configuration Management
- API keys stored in `~/.config/gimp-ai-plugin/config.json`
- Fallback locations: `~/.gimp-ai-config.json`, local `config.json`
- Never commit real API keys to the repository

### Error Handling
- Always wrap API calls in try/except blocks
- Provide user-friendly error messages via `Gimp.message()`
- Handle cancellation via `self._cancel_requested` flag
- Log detailed errors for debugging (can include in error dialogs)

## Testing

### Current Test Infrastructure

1. **`test_plugin.py`**: Basic validation tests
   - Configuration file validation
   - Dependency checks (optional)
   - Module import tests

2. **`test_minimal.py`**: Minimal plugin loading test

3. **`tests/`**: Directory for additional unit tests

### Testing Guidelines

- **Unit tests**: Pure functions in `coordinate_utils.py` should have unit tests
- **Integration tests**: Not currently implemented (would require GIMP environment)
- **Manual testing**: Required for UI and GIMP integration
  - Test all three procedures: inpainting, generation, composite
  - Test with various image sizes and aspect ratios
  - Test cancellation behavior
  - Test error handling (invalid API keys, network failures)

### Running Tests
```bash
# Unit tests (for coordinate_utils.py)
python3 -m pytest tests/

# Manual testing in GIMP
# 1. Copy plugin files to GIMP plugin directory
# 2. Restart GIMP
# 3. Check Filters → AI menu
# 4. Test each feature with various inputs
```

## Build & Validation

### Installation Process
```bash
# The plugin has no build step - just copy files:
mkdir -p ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/
cp gimp-ai-plugin.py ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/
cp coordinate_utils.py ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/
chmod +x ~/.config/GIMP/3.0/plug-ins/gimp-ai-plugin/gimp-ai-plugin.py
```

### Platform-Specific Paths
- **macOS**: `~/Library/Application Support/GIMP/3.0/plug-ins/`
- **Linux**: `~/.config/GIMP/3.0/plug-ins/`
- **Windows**: `%APPDATA%\GIMP\3.0\plug-ins\`

### Validation Steps
1. **Syntax check**: `python3 -m py_compile gimp-ai-plugin.py coordinate_utils.py`
2. **Import test**: `python3 -c "import coordinate_utils"`
3. **GIMP recognition**: Plugin appears in Filters → AI menu after restart

### No External Dependencies to Manage
The plugin intentionally uses only standard library + GIMP APIs. The `requirements.txt` file documents this is intentional.

## OpenAI API Integration

### Supported Image Dimensions
OpenAI DALL-E API only accepts three specific sizes:
- **Square**: 1024 × 1024
- **Landscape**: 1536 × 1024  
- **Portrait**: 1024 × 1536

### Shape Selection Algorithm
See `coordinate_utils.py` `get_optimal_openai_shape()`:
- Aspect ratio > 1.3 → Landscape
- Aspect ratio < 0.77 → Portrait
- Otherwise → Square

### Image Processing Pipeline
1. **Extract context** around selection (or full image)
2. **Pad/scale** to match OpenAI dimensions
3. **Create mask** from GIMP selection
4. **Call API** with image, mask, and prompt
5. **Place result** back into GIMP, accounting for scaling/padding
6. **Create layer mask** to limit visibility to original selection

Detailed algorithms documented in `ALGORITHMS.md`.

## Documentation

### Essential Files
- **`README.md`**: Installation, usage, and quick start guide
- **`CHANGELOG.md`**: Version history and known issues
- **`TROUBLESHOOTING.md`**: Platform-specific issues and solutions
- **`TODO.md`**: Development roadmap and beta testing plan
- **`ALGORITHMS.md`**: Detailed coordinate transformation algorithms
- **`LICENSE`**: MIT license

### Documentation Standards
- Keep README focused on user-facing content
- Technical details go in ALGORITHMS.md or code comments
- Update CHANGELOG.md for all notable changes
- Add new issues to TROUBLESHOOTING.md as they're discovered

## Development Workflow

### Making Changes

1. **Test locally first**: Copy to GIMP plugin dir and restart GIMP
2. **Test all three features**: Inpainting, generation, composite
3. **Test error paths**: Invalid inputs, API failures, cancellation
4. **Update documentation**: If adding features or changing behavior
5. **Consider coordinate_utils.py**: If adding coordinate logic, keep it pure (no GIMP deps)

### Common Tasks

**Adding a new procedure:**
1. Add procedure name to `do_query_procedures()`
2. Implement creation in `do_create_procedure()`
3. Implement run method (e.g., `run_inpaint()`)
4. Update menu registration in `do_set_i18n()`

**Modifying coordinate logic:**
1. Update functions in `coordinate_utils.py`
2. Add unit tests for new logic
3. Update `ALGORITHMS.md` if algorithm changes
4. Test with various image sizes/aspect ratios

**Changing API integration:**
1. Update in `_call_openai_api()` or related methods
2. Handle new error cases
3. Update configuration if needed
4. Test with real API calls

## Version Compatibility

### GIMP Versions
- **Minimum**: GIMP 3.0.4
- **Tested**: GIMP 3.0.4, 3.1.x
- **Not supported**: GIMP 2.x (uses different Python API)

### Python Versions
- Compatible with Python 3.x included with GIMP
- No external dependencies required

### Platform Support
- **macOS**: Fully tested (Intel and Apple Silicon)
- **Linux**: Beta testing needed
- **Windows**: Beta testing needed

## Known Issues & Limitations

(See `CHANGELOG.md` for current version's known issues)

### API Limitations
- OpenAI API only accepts specific image dimensions (1024×1024, 1536×1024, 1024×1536)
- AI may modify areas outside selection for visual coherence (only final output is masked)

### Performance Considerations
- Large images (>2048px) may require more memory
- API calls can take 10-30 seconds depending on network/load
- Cancellation is only checked between major operations

## Pull Request Guidelines

### Before Submitting
- Test all affected features in GIMP
- Update relevant documentation
- Run syntax checks: `python3 -m py_compile *.py`
- Check that plugin still loads in GIMP
- If changing coordinate logic, add/update unit tests

### PR Description Should Include
- What feature/bug is being addressed
- How to test the changes manually
- Any new dependencies or requirements
- Screenshots if UI changes are involved
- Update to CHANGELOG.md if user-facing change

### Review Checklist
- [ ] Code follows Python conventions (PEP 8)
- [ ] No external dependencies added (unless absolutely necessary)
- [ ] Plugin loads and appears in GIMP menu
- [ ] All three features still work (inpainting, generation, composite)
- [ ] Error handling is appropriate
- [ ] Documentation updated if needed
- [ ] No API keys committed to repository

## Security Considerations

- **API Keys**: Never commit API keys to the repository
- **User Input**: Sanitize prompts and inputs before sending to API
- **HTTPS**: Always use HTTPS for API communication (handled by urllib)
- **File Permissions**: Plugin file should be executable on Unix-like systems
- **Temporary Files**: Clean up temporary image files after use

## Getting Help

- **Troubleshooting**: See `TROUBLESHOOTING.md` first
- **Algorithms**: See `ALGORITHMS.md` for coordinate transformation details
- **GIMP API**: Official docs at https://www.gimp.org/docs/python/
- **Issues**: Report bugs on GitHub issue tracker
