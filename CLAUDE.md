# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Instructions

For comprehensive repository guidelines, architecture details, coding conventions, and development workflows, see:

**[.github/copilot-instructions.md](.github/copilot-instructions.md)**

This file contains all the essential information about the GIMP AI Plugin project, including:

- Project overview and key features
- Technology stack (Python 3, GIMP 3.0 API, GTK, GEGL)
- Architecture and core files
- Key design principles
- Coding guidelines (PEP 8, GIMP API patterns, error handling)
- Testing infrastructure and guidelines
- Build and validation steps
- OpenAI API integration details
- Documentation standards
- Development workflow
- Version compatibility
- Security considerations
- Pull request guidelines

## Quick Reference

### Core Files

- **`gimp-ai-plugin.py`** - Main GIMP plugin (~4000 lines)
- **`coordinate_utils.py`** - Pure math utilities, no GIMP dependencies (~600 lines)
- **`install.py`** / **`install_simple.py`** - Installation scripts

### Key Design Principles

- **Separation of Concerns**: Pure coordinate math isolated in `coordinate_utils.py`
- **Stateless Operations**: New layers created for all results (non-destructive)
- **No External Dependencies**: Only standard library + GIMP APIs
- **Error Resilience**: Graceful handling of API failures and user cancellation

### Testing & Validation

```bash
# Syntax check
python3 -m py_compile gimp-ai-plugin.py coordinate_utils.py

# Unit tests
python3 -m pytest tests/

# Manual testing in GIMP required for full validation
```

### Installation Paths

- **macOS**: `~/Library/Application Support/GIMP/3.0/plug-ins/`
- **Linux**: `~/.config/GIMP/3.0/plug-ins/`
- **Windows**: `%APPDATA%\GIMP\3.0\plug-ins\`

## Documentation Files

- **README.md** - User-facing installation and usage guide
- **ALGORITHMS.md** - Detailed coordinate transformation algorithms
- **CHANGELOG.md** - Version history and known issues
- **TROUBLESHOOTING.md** - Platform-specific issues and solutions
- **TODO.md** - Development roadmap and beta testing plan
