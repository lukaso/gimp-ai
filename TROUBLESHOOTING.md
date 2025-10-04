# Troubleshooting Guide

Common issues and solutions for the GIMP AI Plugin.

---

## 🚨 Installation Issues

### Plugin Not Appearing in GIMP Menus

**Symptoms**: No "AI" submenu under Filters menu

**Solutions**:

1. **Check plugin directory structure**:

   - **macOS**: `~/Library/Application Support/GIMP/3.1/plug-ins/gimp-ai-plugin/` (or 3.0)
   - **Linux**: `~/.config/GIMP/3.1/plug-ins/gimp-ai-plugin/` (or 3.0)
   - **Windows**: `%APPDATA%\GIMP\3.1\plug-ins\gimp-ai-plugin\` (or 3.0)

2. **Verify subdirectory and both files are present**:

   ```
   plug-ins/
   └── gimp-ai-plugin/
       ├── gimp-ai-plugin.py
       └── coordinate_utils.py
   ```

3. **Check file permissions** (Linux/macOS):

   ```bash
   chmod +x ~/path/to/gimp-ai-plugin/gimp-ai-plugin.py
   ```

4. **Restart GIMP completely** (quit and reopen)

5. **Check GIMP version**: Plugin requires GIMP 3.0.4+ or 3.1.x

### Wrong GIMP Version Directory

**Symptoms**: Plugin installed but not loading

**Solution**: Check your GIMP version:

- Open GIMP → Help → About GIMP
- Use matching directory (3.0 vs 3.1)
- Install in correct version-specific folder

---

## 🔧 Configuration Issues

### "No API Key Configured" Error

**Symptoms**: Error dialog when trying to use any AI feature

**Solutions**:

1. Go to `Filters > AI > Settings` (if available)
2. Or use any AI feature and click "Configure" in the error dialog
3. Enter your OpenAI API key
4. Settings are automatically saved to GIMP preferences

### Invalid API Key Error

**Symptoms**: "Authentication failed" or similar errors

**Solutions**:

1. **Verify API key**: Copy from OpenAI dashboard exactly
2. **Check key format**: Should start with `sk-`
3. **Test key**: Try in OpenAI playground first
4. **Account status**: Ensure OpenAI account has credits

### Settings Not Persisting

**Symptoms**: Need to re-enter API key every restart

**Solutions**:

1. **Check GIMP preferences directory permissions**
2. **Manual config location** (if needed):
   - **macOS**: `~/Library/Application Support/GIMP/3.1/gimp-ai-plugin/config.json`
   - **Linux**: `~/.config/GIMP/3.1/gimp-ai-plugin/config.json`
   - **Windows**: `%APPDATA%\GIMP\3.1\gimp-ai-plugin\config.json`

---

## 🖥️ Platform-Specific Issues

### macOS Issues

**"Python not found" error**:

- GIMP 3.x includes Python - shouldn't happen
- If it does, reinstall GIMP from official source

**Permission denied errors**:

```bash
xattr -d com.apple.quarantine ~/Library/Application\ Support/GIMP/3.1/plug-ins/gimp-ai-plugin.py
```

### Linux Issues

**Plugin directory doesn't exist**:

```bash
mkdir -p ~/.config/GIMP/3.1/plug-ins/gimp-ai-plugin/
```

**Python import errors**:

- Check if GIMP was compiled with Python support
- Some package managers have GIMP without Python

**Flatpak GIMP**:

- Plugin directory: `~/.var/app/org.gimp.GIMP/config/GIMP/3.1/plug-ins/gimp-ai-plugin/`
- May have restricted network access

### Windows Issues

**Path not found**:

- Use Windows Explorer to navigate to `%APPDATA%\GIMP\3.1\plug-ins\gimp-ai-plugin\`
- Create directory if it doesn't exist

**Antivirus blocking**:

- Some antivirus software blocks .py files
- Add plugin directory to exceptions

---

## 🌐 Network & API Issues

### "Connection timeout" Errors

**Symptoms**: Operations fail with timeout messages

**Solutions**:

1. **Check internet connection**
2. **Firewall/proxy**: Ensure HTTPS traffic allowed
3. **Corporate networks**: May block OpenAI API
4. **Large images**: Try smaller images first

### "Rate limit exceeded"

**Symptoms**: API calls rejected with rate limit error

**Solutions**:

1. **Wait and retry**: OpenAI has rate limits
2. **Check usage**: Review OpenAI dashboard
3. **Upgrade plan**: If on free tier, consider paid plan

### Slow Performance

**Symptoms**: Operations take very long to complete

**Solutions**:

1. **Image size**: Try images under 1024px first
2. **Network speed**: Check internet connection
3. **Server load**: OpenAI API can be slower during peak times

---

## 🐛 Runtime Errors

### "Selection not found" Error

**Symptoms**: Inpainting fails even with selection

**Solutions**:

1. **Make selection before** running inpainting
2. **Check selection visibility**: View → Show Selection
3. **Refresh selection**: Select → None, then reselect

### Plugin Crashes GIMP

**Symptoms**: GIMP closes unexpectedly

**Solutions**:

1. **Check GIMP Error Console**: Windows → Error Console
2. **Update GIMP**: Use latest 3.1.x if possible
3. **Reduce image size**: Try smaller images
4. **Report bug**: Include error console output

### "Coordinate transformation failed"

**Symptoms**: Error in coordinate calculations

**Solutions**:

1. **Check image dimensions**: Very unusual sizes may fail
2. **Selection bounds**: Ensure selection is within image
3. **Try simple rectangular selection** first

---

## 📊 Performance Optimization

### Reduce Processing Time

1. **Resize large images** before processing
2. **Use smaller selections** for inpainting
3. **Simple prompts** process faster than complex ones

---

## 🆘 Getting Help

### Before Reporting Issues

1. **Check this guide** for common solutions
2. **Try with a simple test image** (small, basic selection)
3. **Check GIMP Error Console** for detailed errors
4. **Test internet connection** and API key independently

### Reporting Bugs (Beta Testing)

Include this information:

- **OS and version** (e.g., "Windows 11", "Ubuntu 22.04", "macOS Ventura")
- **GIMP version** (exact version from Help → About)
- **Plugin version** (0.8.0-beta)
- **Error messages** from GIMP Error Console
- **Steps to reproduce** the issue
- **Image details** (size, format, what you were trying to do)

### Beta Feedback Template

```
**Platform**: [Windows/Linux/macOS + version]
**GIMP Version**: [e.g., 3.1.2]
**Issue Type**: [Installation/Configuration/Runtime/Performance]
**Description**: [What happened vs what you expected]
**Error Messages**: [Any error dialog text or console output]
**Steps**: [Exact steps to reproduce]
**Image Details**: [Size, format, selection details if relevant]
```

---

## 📝 Logs and Debugging

### Enable Debug Output

Currently, debug output goes to GIMP's Error Console:

- **View logs**: Windows → Dockable Dialogs → Error Console
- **Clear logs**: Right-click in console → Clear
- **Save logs**: Copy text from console for bug reports

### Temporary Workarounds

- **Restart GIMP** often resolves temporary issues
- **Try smaller images** if processing fails
- **Use simple selections** (rectangles) for testing
- **Test with basic prompts** like "blue sky" or "green grass"

---

_This troubleshooting guide will be updated based on beta feedback. Report new issues on GitHub!_
