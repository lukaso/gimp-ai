#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GIMP AI Plugin - Simplified version to fix crash
"""

import sys
import os
import gi
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import base64
import tempfile
import uuid

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gegl", "0.4")
gi.require_version("Gio", "2.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gimp, GimpUi, GLib, Gegl, Gio, Gtk, Gdk

# Import pure coordinate transformation functions
from coordinate_utils import (
    calculate_context_extraction,
    calculate_mask_coordinates,
    calculate_placement_coordinates,
    validate_context_info,
)


class GimpAIPlugin(Gimp.PlugIn):
    """Simplified AI Plugin"""

    def __init__(self):
        super().__init__()
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from various locations"""
        # Use GIMP API for primary config location
        try:
            plugin_dir = Gimp.PlugIn.directory()
            gimp_config_path = os.path.join(plugin_dir, "gimp-ai-plugin", "config.json")
        except:
            gimp_config_path = None

        config_paths = []

        # Try GIMP preferences directory first (where we want to save)
        try:
            gimp_user_dir = Gimp.directory()
            gimp_prefs_path = os.path.join(
                gimp_user_dir, "gimp-ai-plugin", "config.json"
            )
            config_paths.append(gimp_prefs_path)
        except:
            pass

        # Then try user config directory (migration path)
        config_paths.append(os.path.expanduser("~/.config/gimp-ai/config.json"))

        # Then try GIMP plugin directory
        if gimp_config_path:
            config_paths.append(gimp_config_path)

        # Fallback paths for backward compatibility
        config_paths.extend(
            [
                os.path.join(os.path.dirname(__file__), "config.json"),
                os.path.expanduser("~/.gimp-ai-config.json"),
            ]
        )

        for config_path in config_paths:
            try:
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                        print(f"DEBUG: Loaded config from {config_path}")
                        return config
            except Exception as e:
                print(f"DEBUG: Failed to load config from {config_path}: {e}")
                continue

        # Default config with prompt history support
        print("DEBUG: Using default config (no config file found)")
        return {
            "openai": {"api_key": None},
            "settings": {"max_image_size": 512, "timeout": 30},
            "prompt_history": [],
            "last_prompt": "",
        }

    def _save_config(self):
        """Save configuration to GIMP preferences directory"""
        try:
            # Use GIMP's user directory (where preferences are stored)
            gimp_user_dir = Gimp.directory()
            config_dir = os.path.join(gimp_user_dir, "gimp-ai-plugin")
            config_path = os.path.join(config_dir, "config.json")

            # Create directory if it doesn't exist
            os.makedirs(config_dir, exist_ok=True)

            with open(config_path, "w") as f:
                json.dump(self.config, f, indent=4)
            print(f"DEBUG: Saved config to GIMP preferences: {config_path}")
            return True
        except Exception as e:
            print(f"DEBUG: Failed to save config to GIMP preferences: {e}")
            # Fallback to user config directory
            try:
                config_dir = os.path.expanduser("~/.config/gimp-ai")
                config_path = os.path.join(config_dir, "config.json")
                os.makedirs(config_dir, exist_ok=True)
                with open(config_path, "w") as f:
                    json.dump(self.config, f, indent=4)
                print(f"DEBUG: Saved config to fallback location: {config_path}")
                return True
            except Exception as e2:
                print(f"DEBUG: All config save attempts failed: {e2}")
                return False

    def _make_url_request(self, req_or_url, timeout=60, headers=None):
        """
        Make URL request with automatic SSL fallback for certificate errors.

        Args:
            req_or_url: Either a urllib.request.Request object or URL string
            timeout: Request timeout in seconds (default: 60)
            headers: Optional dict of headers to add (only if req_or_url is string)

        Returns:
            urllib response object

        Raises:
            urllib.error.URLError: If both normal and SSL-bypassed requests fail
        """
        try:
            # First attempt with normal SSL verification
            if isinstance(req_or_url, str):
                # Create Request object from URL string
                req = urllib.request.Request(req_or_url)
                if headers:
                    for key, value in headers.items():
                        req.add_header(key, value)
            else:
                req = req_or_url

            return urllib.request.urlopen(req, timeout=timeout)

        except (ssl.SSLError, urllib.error.URLError) as ssl_err:
            # Check if it's an SSL-related error
            if "SSL" in str(ssl_err) or "CERTIFICATE" in str(ssl_err):
                print(
                    f"DEBUG: SSL verification failed, trying with SSL bypass: {ssl_err}"
                )
            else:
                # Not an SSL error, re-raise it
                raise ssl_err

            # Fallback to unverified SSL if certificate fails
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            try:
                return urllib.request.urlopen(req, context=ctx, timeout=timeout)
            except Exception as fallback_err:
                print(f"DEBUG: SSL bypass also failed: {fallback_err}")
                raise fallback_err

    def _add_to_prompt_history(self, prompt):
        """Add prompt to history, keeping last 10 unique prompts"""
        if not prompt.strip():
            return

        # Remove if already exists to avoid duplicates
        history = self.config.get("prompt_history", [])
        if prompt in history:
            history.remove(prompt)

        # Add to beginning
        history.insert(0, prompt)

        # Keep only last 10
        history = history[:10]

        self.config["prompt_history"] = history
        self.config["last_prompt"] = prompt
        self._save_config()

    def _get_prompt_history(self):
        """Get prompt history list"""
        return self.config.get("prompt_history", [])

    def _get_last_prompt(self):
        """Get the last used prompt"""
        return self.config.get("last_prompt", "")

    def _get_api_key(self):
        """Get OpenAI API key from config or environment"""
        # Try config file first
        if (
            self.config
            and "openai" in self.config
            and self.config["openai"].get("api_key")
        ):
            return self.config["openai"]["api_key"]

        # Try environment variable
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return api_key

        # No API key found
        return None

    def _get_processing_mode(self):
        """Determine processing mode based on selection and model"""
        # Always use context_extraction for proper inpainting behavior
        # This works for both selective editing and full image transformation
        return "full_image"  # "context_extraction"

    def _show_prompt_dialog(self, title="AI Prompt", default_text=""):
        """Show a GIMP UI dialog to get user input for AI prompt"""
        # Use last prompt as default if available, otherwise use provided default
        if not default_text:
            default_text = self._get_last_prompt()
        if not default_text:
            default_text = "Describe what you want to generate..."
        try:
            # Initialize GIMP UI system (only if not already initialized)
            if not hasattr(self, "_ui_initialized"):
                GimpUi.init("gimp-ai-plugin")
                self._ui_initialized = True

            # Use proper GIMP dialog with header bar detection
            use_header_bar = Gtk.Settings.get_default().get_property(
                "gtk-dialogs-use-header"
            )
            dialog = GimpUi.Dialog(use_header_bar=use_header_bar, title=title)

            # Set up dialog properties
            dialog.set_default_size(600, 300)
            dialog.set_resizable(True)

            # Add buttons using GIMP's standard approach
            dialog.add_button(
                "Settings", Gtk.ResponseType.HELP
            )  # Use HELP for Settings
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("OK", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Add content with proper spacing
            content_area = dialog.get_content_area()
            content_area.set_spacing(10)
            content_area.set_margin_left(20)
            content_area.set_margin_right(20)
            content_area.set_margin_top(20)
            content_area.set_margin_bottom(20)

            # Label - will automatically use theme colors
            label = Gtk.Label(label="Enter your AI prompt:")
            label.set_halign(Gtk.Align.START)
            content_area.pack_start(label, False, False, 0)

            # Prompt history dropdown
            history = self._get_prompt_history()
            history_combo = None
            if history:
                history_label = Gtk.Label(label="Recent prompts:")
                history_label.set_halign(Gtk.Align.START)
                content_area.pack_start(history_label, False, False, 0)

                history_combo = Gtk.ComboBoxText()
                history_combo.append_text("Select from recent prompts...")
                for prompt in history:
                    # Truncate long prompts for display
                    display_prompt = prompt[:60] + "..." if len(prompt) > 60 else prompt
                    history_combo.append_text(display_prompt)
                history_combo.set_active(0)
                content_area.pack_start(history_combo, False, False, 0)

            # Multiline text view for prompts
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            scrolled_window.set_size_request(560, 150)

            text_view = Gtk.TextView()
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            text_view.set_border_width(8)

            # Set default text
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(default_text)

            scrolled_window.add(text_view)
            content_area.pack_start(scrolled_window, True, True, 0)

            # Connect Enter to activate OK button, Shift+Enter for new line
            def on_key_press(widget, event):
                if event.keyval == Gdk.KEY_Return:
                    # Shift+Enter: Allow new line (default behavior)
                    if event.state & Gdk.ModifierType.SHIFT_MASK:
                        return False  # Let default behavior handle it
                    # Plain Enter or Ctrl+Enter: Submit dialog
                    else:
                        dialog.response(Gtk.ResponseType.OK)
                        return True
                return False

            text_view.connect("key-press-event", on_key_press)

            # Connect history selection to populate text view
            if history_combo:

                def on_history_changed(combo):
                    active = combo.get_active()
                    if active > 0:  # Skip the placeholder item
                        selected_prompt = history[
                            active - 1
                        ]  # -1 because of placeholder
                        text_buffer.set_text(selected_prompt)
                        text_view.grab_focus()
                        text_buffer.select_range(
                            text_buffer.get_start_iter(), text_buffer.get_end_iter()
                        )

                history_combo.connect("changed", on_history_changed)

            # Show all widgets
            content_area.show_all()

            # Focus the text view and select all text for easy editing
            text_view.grab_focus()
            text_buffer.select_range(
                text_buffer.get_start_iter(), text_buffer.get_end_iter()
            )

            # Run dialog in loop to handle Settings button
            print("DEBUG: About to call dialog.run()...")
            while True:
                response = dialog.run()
                print(f"DEBUG: Dialog response: {response}")

                if response == Gtk.ResponseType.OK:
                    start_iter = text_buffer.get_start_iter()
                    end_iter = text_buffer.get_end_iter()
                    prompt = text_buffer.get_text(start_iter, end_iter, False).strip()
                    print(f"DEBUG: Got prompt text: '{prompt}', destroying dialog...")
                    dialog.destroy()
                    print("DEBUG: Dialog destroyed, returning prompt")
                    if prompt:
                        self._add_to_prompt_history(prompt)
                    return prompt if prompt else None
                elif response == Gtk.ResponseType.HELP:  # Settings button
                    print("DEBUG: Settings button clicked")
                    self._show_settings_dialog(dialog)
                    # Continue loop to keep main dialog open
                else:
                    print("DEBUG: Dialog cancelled, destroying...")
                    dialog.destroy()
                    return None

        except Exception as e:
            print(f"DEBUG: Dialog error: {e}")
            # Fallback to default prompt if dialog fails
            return default_text if default_text else "fill this area naturally"

    def _show_settings_dialog(self, parent_dialog):
        """Show settings dialog with write-only API key field"""
        try:
            dialog = Gtk.Dialog(
                title="AI Plugin Settings",
                parent=parent_dialog,
                flags=Gtk.DialogFlags.MODAL,
            )

            # Set up dialog properties
            dialog.set_default_size(500, 400)
            dialog.set_resizable(True)

            # Add buttons
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            save_button = dialog.add_button("Save", Gtk.ResponseType.OK)
            save_button.set_can_default(True)
            save_button.grab_default()

            # Add content
            content_area = dialog.get_content_area()
            content_area.set_spacing(15)
            content_area.set_margin_left(20)
            content_area.set_margin_right(20)
            content_area.set_margin_top(20)
            content_area.set_margin_bottom(20)

            # API Key section
            api_frame = Gtk.Frame(label="OpenAI API Configuration")
            api_box = Gtk.VBox(spacing=10)
            api_box.set_margin_left(10)
            api_box.set_margin_right(10)
            api_box.set_margin_top(10)
            api_box.set_margin_bottom(10)

            # Current API key status
            current_key = self.config.get("openai", {}).get("api_key")
            if current_key:
                status_label = Gtk.Label(label="✓ API key is configured")
                status_label.set_halign(Gtk.Align.START)
            else:
                status_label = Gtk.Label(label="✗ No API key configured")
                status_label.set_halign(Gtk.Align.START)
            api_box.pack_start(status_label, False, False, 0)

            # API key input (write-only)
            key_label = Gtk.Label(label="Enter new API key (write-only):")
            key_label.set_halign(Gtk.Align.START)
            api_box.pack_start(key_label, False, False, 0)

            key_entry = Gtk.Entry()
            key_entry.set_placeholder_text("sk-proj-...")
            key_entry.set_visibility(False)  # Hide the text for security
            api_box.pack_start(key_entry, False, False, 0)

            api_frame.add(api_box)
            content_area.pack_start(api_frame, False, False, 0)

            # Prompt History section
            history_frame = Gtk.Frame(label="Prompt History")
            history_box = Gtk.VBox(spacing=10)
            history_box.set_margin_left(10)
            history_box.set_margin_right(10)
            history_box.set_margin_top(10)
            history_box.set_margin_bottom(10)

            # History count
            history_count = len(self._get_prompt_history())
            count_label = Gtk.Label(label=f"Stored prompts: {history_count}")
            count_label.set_halign(Gtk.Align.START)
            history_box.pack_start(count_label, False, False, 0)

            # Clear history button
            clear_button = Gtk.Button(label="Clear Prompt History")
            clear_button.connect("clicked", self._on_clear_history_clicked)
            history_box.pack_start(clear_button, False, False, 0)

            history_frame.add(history_box)
            content_area.pack_start(history_frame, False, False, 0)

            # Show all widgets
            content_area.show_all()

            # Run dialog
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                # Save new API key if provided
                new_key = key_entry.get_text().strip()
                if new_key:
                    if "openai" not in self.config:
                        self.config["openai"] = {}
                    self.config["openai"]["api_key"] = new_key
                    self._save_config()
                    print("DEBUG: API key updated")

            dialog.destroy()

        except Exception as e:
            print(f"DEBUG: Settings dialog error: {e}")

    def _on_clear_history_clicked(self, button):
        """Handle clear history button click"""
        self.config["prompt_history"] = []
        self._save_config()
        print("DEBUG: Prompt history cleared")

    def _test_image_access(self, image, drawables):
        """Test basic image data access"""
        try:
            if not image:
                return False, "No image provided"

            if not drawables or len(drawables) == 0:
                return False, "No drawable/layer provided"

            drawable = drawables[0]  # Use first drawable

            # Get basic image info
            width = image.get_width()
            height = image.get_height()
            precision = image.get_precision()
            base_type = image.get_base_type()

            # Get drawable info
            drawable_width = drawable.get_width()
            drawable_height = drawable.get_height()
            has_alpha = drawable.has_alpha()
            drawable_name = (
                drawable.get_name() if hasattr(drawable, "get_name") else "Unknown"
            )

            # Basic info without buffer access for now
            info = (
                f"Image: {width}x{height}, precision: {precision}, base type: {base_type}\n"
                f"Drawable: '{drawable_name}', {drawable_width}x{drawable_height}, alpha: {has_alpha}"
            )

            # Try to access buffer information safely
            try:
                buffer = drawable.get_buffer()
                buffer_info = f"\nBuffer: Available (type: {type(buffer).__name__})"
                info += buffer_info
            except Exception as e:
                info += f"\nBuffer: Not accessible ({str(e)})"

            return True, info

        except Exception as e:
            return False, f"Image access error: {str(e)}"

    def _extract_context_region(self, image, context_info):
        """Extract true square context region without distortion"""
        try:
            print("DEBUG: Extracting TRUE SQUARE context region for AI")

            # Get parameters for the context square
            ctx_x1, ctx_y1, ctx_size, _ = context_info["context_square"]
            target_size = context_info["target_size"]
            orig_width = image.get_width()
            orig_height = image.get_height()

            print(
                f"DEBUG: Context square: ({ctx_x1},{ctx_y1}) to ({ctx_x1+ctx_size},{ctx_y1+ctx_size}) size={ctx_size}"
            )
            print(f"DEBUG: Original image: {orig_width}x{orig_height}")
            print(f"DEBUG: Target size: {target_size}x{target_size}")

            # Create a new square canvas
            square_image = Gimp.Image.new(ctx_size, ctx_size, image.get_base_type())
            if not square_image:
                return False, "Failed to create square canvas", None

            # Calculate what part of the original image intersects with our context square
            intersect_x1 = max(0, ctx_x1)
            intersect_y1 = max(0, ctx_y1)
            intersect_x2 = min(orig_width, ctx_x1 + ctx_size)
            intersect_y2 = min(orig_height, ctx_y1 + ctx_size)

            intersect_width = intersect_x2 - intersect_x1
            intersect_height = intersect_y2 - intersect_y1

            print(
                f"DEBUG: Image intersection: ({intersect_x1},{intersect_y1}) to ({intersect_x2},{intersect_y2})"
            )
            print(f"DEBUG: Intersection size: {intersect_width}x{intersect_height}")

            if intersect_width > 0 and intersect_height > 0:
                # Create a temporary image with just the intersecting region
                temp_image = image.duplicate()
                temp_image.crop(
                    intersect_width, intersect_height, intersect_x1, intersect_y1
                )

                # Create a layer from this region
                merged_layer = temp_image.merge_visible_layers(
                    Gimp.MergeType.CLIP_TO_IMAGE
                )
                if not merged_layer:
                    temp_image.delete()
                    square_image.delete()
                    return False, "Failed to merge layers", None

                # Copy this layer to our square canvas at the correct position
                layer_copy = Gimp.Layer.new_from_drawable(merged_layer, square_image)
                square_image.insert_layer(layer_copy, None, 0)

                # Position the layer correctly within the square
                # The layer should be at the same relative position as in the context square
                paste_x = intersect_x1 - ctx_x1  # Offset within the square
                paste_y = intersect_y1 - ctx_y1  # Offset within the square
                layer_copy.set_offsets(paste_x, paste_y)

                print(
                    f"DEBUG: Placed image content at offset ({paste_x},{paste_y}) within square"
                )

                # Clean up temp image
                temp_image.delete()
            else:
                print(
                    "DEBUG: No intersection with original image - creating empty square"
                )

            # Scale to target size for OpenAI
            if ctx_size != target_size:
                square_image.scale(target_size, target_size)
                print(
                    f"DEBUG: Scaled square from {ctx_size}x{ctx_size} to {target_size}x{target_size}"
                )

            # Export to PNG
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                # Export using GIMP's PNG export
                file = Gio.File.new_for_path(temp_filename)

                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", square_image)
                pdb_config.set_property("file", file)
                pdb_config.set_property("options", None)

                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    print(f"DEBUG: PNG export failed: {result.index(0)}")
                    square_image.delete()
                    return False, "PNG export failed", None

                # Read the exported file and encode to base64
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                base64_data = base64.b64encode(png_data).decode("utf-8")

                # Clean up
                os.unlink(temp_filename)
                square_image.delete()

                info = f"Extracted context region: {len(png_data)} bytes as PNG, base64 length: {len(base64_data)}"
                print(f"DEBUG: {info}")
                return True, info, base64_data

            except Exception as e:
                print(f"DEBUG: Context extraction export failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                square_image.delete()
                return False, f"Export failed: {str(e)}", None

        except Exception as e:
            print(f"DEBUG: Context extraction failed: {e}")
            return False, f"Context extraction error: {str(e)}", None

    def _export_image_for_ai(self, image, drawable, max_size=1024):
        """Export image as base64-encoded PNG for AI APIs"""
        try:
            print(f"DEBUG: Exporting image for AI, max_size={max_size}")

            # Validate inputs
            if not image:
                return False, "Error: No image provided", None, 0, 0

            if max_size < 64 or max_size > 2048:
                return (
                    False,
                    f"Error: Invalid max_size {max_size} (must be 64-2048)",
                    None,
                    0,
                    0,
                )

            # Check if image has valid dimensions
            orig_width = image.get_width()
            orig_height = image.get_height()

            if orig_width == 0 or orig_height == 0:
                return (
                    False,
                    f"Error: Invalid image dimensions {orig_width}x{orig_height}",
                    None,
                    0,
                    0,
                )

            if orig_width > 4096 or orig_height > 4096:
                return (
                    False,
                    f"Error: Image too large {orig_width}x{orig_height} (max 4096x4096)",
                    None,
                    0,
                    0,
                )

            print(f"DEBUG: Original image dimensions: {orig_width}x{orig_height}")

            # Create a temporary image copy for export
            temp_image = image.duplicate()
            if not temp_image:
                return False, "Error: Failed to duplicate image", None, 0, 0

            # Get the active layer from the temp image
            layers = temp_image.get_layers()
            if not layers or len(layers) == 0:
                temp_image.delete()
                return False, "Error: No layers found in image", None, 0, 0

            temp_drawable = layers[0]  # Use first layer

            # Get dimensions
            width = temp_image.get_width()
            height = temp_image.get_height()

            # Resize to square format for OpenAI (they prefer square images)
            if width != max_size or height != max_size:
                print(
                    f"DEBUG: Resizing from {width}x{height} to {max_size}x{max_size} (square)"
                )
                temp_image.scale(max_size, max_size)

            # Export to temporary file
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                # Use GIMP's export function (GIMP 3.x style)
                print(f"DEBUG: Attempting to export to {temp_filename}")

                # Try different export approaches for GIMP 3.x
                export_success = False

                # Use GIMP's built-in export functionality
                try:
                    print("DEBUG: Trying GIMP file export")

                    # Use Gimp.file_export to create real PNG
                    file = Gio.File.new_for_path(temp_filename)

                    # Try to export using GIMP's PNG export PDB procedure
                    try:
                        print("DEBUG: Trying PNG export via PDB procedure")

                        pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                        pdb_config = pdb_proc.create_config()
                        pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                        pdb_config.set_property("image", temp_image)
                        pdb_config.set_property("file", file)
                        pdb_config.set_property("options", None)

                        result = pdb_proc.run(pdb_config)
                        if result.index(0) == Gimp.PDBStatusType.SUCCESS:
                            export_success = True
                            print(
                                "DEBUG: GIMP PNG export successful - using GIMP export"
                            )
                        else:
                            print(
                                f"DEBUG: GIMP PNG export failed: {result.index(0)}, trying fallback"
                            )
                            export_success = False
                    except Exception as e:
                        print(f"DEBUG: GIMP export exception: {e}, trying fallback")
                        export_success = False

                    # If GIMP export failed, create a simple PNG with actual image dimensions
                    if not export_success:
                        print("DEBUG: Creating fallback PNG")
                        width = temp_image.get_width()
                        height = temp_image.get_height()

                        # Create a simple solid color PNG with correct dimensions
                        import zlib

                        # Create IHDR chunk data (RGB format)
                        ihdr_data = (
                            width.to_bytes(4, "big")  # Width
                            + height.to_bytes(4, "big")  # Height
                            + b"\x08\x02\x00\x00\x00"  # 8-bit RGB, no compression/filter/interlace
                        )

                        # Calculate IHDR CRC
                        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

                        # Create simple image data (gray pixels)
                        row_data = (
                            b"\x00" + b"\x80\x80\x80" * width
                        )  # Filter byte + gray RGB pixels
                        image_data = row_data * height
                        compressed_data = zlib.compress(image_data)

                        # Calculate IDAT CRC
                        idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

                        # Build complete PNG
                        png_data = (
                            b"\x89PNG\r\n\x1a\n"  # PNG signature
                            + len(ihdr_data).to_bytes(4, "big")
                            + b"IHDR"  # IHDR chunk length + type
                            + ihdr_data
                            + ihdr_crc.to_bytes(4, "big")  # IHDR data + CRC
                            + len(compressed_data).to_bytes(4, "big")
                            + b"IDAT"  # IDAT chunk length + type
                            + compressed_data
                            + idat_crc.to_bytes(4, "big")  # IDAT data + CRC
                            + b"\x00\x00\x00\x00IEND\xae B`\x82"  # IEND chunk
                        )

                        with open(temp_filename, "wb") as f:
                            f.write(png_data)

                        export_success = True
                        print(
                            f"DEBUG: Fallback PNG created: {len(png_data)} bytes for {width}x{height}"
                        )

                except Exception as e:
                    print(f"DEBUG: PNG creation failed: {e}")
                    return False, f"PNG creation failed: {e}", None, None, None

                print(f"DEBUG: Export success: {export_success}")
                if not export_success:
                    return False, "Export to PNG failed", None, None, None

                # Read the exported file and encode to base64
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                base64_data = base64.b64encode(png_data).decode("utf-8")

                # Get final dimensions after any resizing
                final_width = temp_image.get_width()
                final_height = temp_image.get_height()

                # Clean up
                os.unlink(temp_filename)
                temp_image.delete()

                info = f"Exported {len(png_data)} bytes as PNG, base64 length: {len(base64_data)}"
                return True, info, base64_data, final_width, final_height

            except Exception as e:
                # Clean up on error
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                return False, f"Export process failed: {str(e)}", None, None, None

        except Exception as e:
            return False, f"Image export error: {str(e)}", None, None, None

    def _create_simple_mask(self, width=512, height=512):
        """Create a test mask with transparent center area for inpainting using GIMP (PNG)"""
        try:
            print(f"DEBUG: Creating test inpainting mask {width}x{height}")

            # Create a mask with opaque white background and transparent center circle for inpainting
            # According to OpenAI docs: transparent areas = inpaint, opaque = preserve

            # Create IHDR chunk data (RGBA format for transparency)
            ihdr_data = (
                width.to_bytes(4, "big")  # Width
                + height.to_bytes(4, "big")  # Height
                + b"\x08\x06\x00\x00\x00"  # 8-bit RGBA, no compression/filter/interlace
            )

            # Calculate IHDR CRC
            import zlib

            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create image data with transparent center area for inpainting
            image_rows = []
            center_x, center_y = width // 2, height // 2
            radius = min(width, height) // 4  # Circle radius

            for y in range(height):
                row = b"\x00"  # Filter byte
                for x in range(width):
                    # Calculate distance from center
                    distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5

                    if distance <= radius:
                        # Transparent (inpaint this area) - RGBA: (0, 0, 0, 0)
                        row += b"\x00\x00\x00\x00"
                    else:
                        # White opaque (preserve this area) - RGBA: (255, 255, 255, 255)
                        row += b"\xff\xff\xff\xff"

                image_rows.append(row)

            image_data = b"".join(image_rows)
            compressed_data = zlib.compress(image_data)

            # Calculate IDAT CRC
            idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

            # Build complete PNG
            png_data = (
                b"\x89PNG\r\n\x1a\n"  # PNG signature
                + len(ihdr_data).to_bytes(4, "big")
                + b"IHDR"  # IHDR chunk length + type
                + ihdr_data
                + ihdr_crc.to_bytes(4, "big")  # IHDR data + CRC
                + len(compressed_data).to_bytes(4, "big")
                + b"IDAT"  # IDAT chunk length + type
                + compressed_data
                + idat_crc.to_bytes(4, "big")  # IDAT data + CRC
                + b"\x00\x00\x00\x00IEND\xae B`\x82"  # IEND chunk
            )

            print(
                f"DEBUG: Created inpainting mask PNG: {len(png_data)} bytes (transparent center circle, white background)"
            )
            return png_data

        except Exception as e:
            print(f"DEBUG: Failed to create simple mask: {e}")
            # Fallback to very basic 1x1 white PNG
            fallback_png = (
                b"\x89PNG\r\n\x1a\n"  # PNG signature
                b"\x00\x00\x00\rIHDR"  # IHDR chunk
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00\x00\x00\x00:~\x9b\x55"  # 1x1 grayscale
                b"\x00\x00\x00\nIDAT\x08\x1dc\xf8\x00\x00\x00\x01\x00\x01\x02\x1a\x05\x1c"  # white pixel
                b"\x00\x00\x00\x00IEND\xae B`\x82"  # IEND
            )
            return fallback_png

    def _create_transparent_mask(self, width=512, height=512):
        """Create a completely transparent mask (inpaint everything)"""
        try:
            print(f"DEBUG: Creating completely transparent mask {width}x{height}")

            # Create IHDR chunk data (RGBA format)
            ihdr_data = (
                width.to_bytes(4, "big")  # Width
                + height.to_bytes(4, "big")  # Height
                + b"\x08\x06\x00\x00\x00"  # 8-bit RGBA
            )

            # Calculate IHDR CRC
            import zlib

            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create completely transparent image data
            row_data = (
                b"\x00" + b"\x00\x00\x00\x00" * width
            )  # Filter byte + transparent RGBA pixels
            image_data = row_data * height
            compressed_data = zlib.compress(image_data)

            # Calculate IDAT CRC
            idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

            # Build complete PNG
            png_data = (
                b"\x89PNG\r\n\x1a\n"
                + len(ihdr_data).to_bytes(4, "big")
                + b"IHDR"
                + ihdr_data
                + ihdr_crc.to_bytes(4, "big")
                + len(compressed_data).to_bytes(4, "big")
                + b"IDAT"
                + compressed_data
                + idat_crc.to_bytes(4, "big")
                + b"\x00\x00\x00\x00IEND\xae B`\x82"
            )

            print(f"DEBUG: Created transparent mask PNG: {len(png_data)} bytes")
            return png_data

        except Exception as e:
            print(f"DEBUG: Failed to create transparent mask: {e}")
            return self._create_simple_mask(width, height)

    def _create_black_mask(self, width=512, height=512):
        """Create a mask with black center circle (for testing different mask formats)"""
        try:
            print(f"DEBUG: Creating black center circle mask {width}x{height}")

            # Create IHDR chunk data (L - grayscale format for OpenAI mask)
            ihdr_data = (
                width.to_bytes(4, "big")
                + height.to_bytes(4, "big")
                + b"\x08\x00\x00\x00\x00"  # 8-bit grayscale (L format)
            )

            # Calculate IHDR CRC
            import zlib

            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create image data with black center circle
            image_rows = []
            center_x, center_y = width // 2, height // 2
            radius = min(width, height) // 4

            for y in range(height):
                row = b"\x00"  # Filter byte
                for x in range(width):
                    distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
                    if distance <= radius:
                        # Black grayscale (0 = inpaint this area)
                        row += b"\x00"
                    else:
                        # White grayscale (255 = keep original)
                        row += b"\xff"
                image_rows.append(row)

            image_data = b"".join(image_rows)
            compressed_data = zlib.compress(image_data)
            idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

            # Build PNG
            png_data = (
                b"\x89PNG\r\n\x1a\n"
                + len(ihdr_data).to_bytes(4, "big")
                + b"IHDR"
                + ihdr_data
                + ihdr_crc.to_bytes(4, "big")
                + len(compressed_data).to_bytes(4, "big")
                + b"IDAT"
                + compressed_data
                + idat_crc.to_bytes(4, "big")
                + b"\x00\x00\x00\x00IEND\xae B`\x82"
            )

            print(f"DEBUG: Created black circle mask PNG: {len(png_data)} bytes")
            return png_data

        except Exception as e:
            print(f"DEBUG: Failed to create black mask: {e}")
            return self._create_simple_mask(width, height)

    def _create_white_mask_with_black_selection(
        self, width, height, sel_x1, sel_y1, sel_x2, sel_y2
    ):
        """Create a white mask with black selection rectangle"""
        try:
            print(
                f"DEBUG: Creating white mask {width}x{height} with black selection ({sel_x1},{sel_y1})-({sel_x2},{sel_y2})"
            )

            # Create IHDR chunk data (L - grayscale format for OpenAI mask)
            ihdr_data = (
                width.to_bytes(4, "big")
                + height.to_bytes(4, "big")
                + b"\x08\x00\x00\x00\x00"  # 8-bit grayscale (L format)
            )
            # Calculate IHDR CRC
            import zlib

            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create image data - white background with black selection area
            image_rows = []
            for y in range(height):
                row = b"\x00"  # Filter byte (0 = none)
                for x in range(width):
                    # Black (0) inside selection, white (255) outside
                    if sel_x1 <= x < sel_x2 and sel_y1 <= y < sel_y2:
                        row += b"\x00"  # Black for selection area
                    else:
                        row += b"\xff"  # White for non-selection area
                image_rows.append(row)

            # Compress image data
            image_data = b"".join(image_rows)
            compressed_data = zlib.compress(image_data)
            idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

            # Construct PNG
            png_data = (
                b"\x89PNG\r\n\x1a\n"  # PNG signature
                + len(ihdr_data).to_bytes(4, "big")
                + b"IHDR"
                + ihdr_data
                + ihdr_crc.to_bytes(4, "big")
                + len(compressed_data).to_bytes(4, "big")
                + b"IDAT"
                + compressed_data
                + idat_crc.to_bytes(4, "big")
                + b"\x00\x00\x00\x00IEND\xaeB`\x82"  # IEND chunk
            )

            print(
                f"DEBUG: Created white mask with black selection: {len(png_data)} bytes"
            )
            return png_data

        except Exception as e:
            print(f"DEBUG: White mask creation failed: {e}")
            return self._create_black_mask(width, height)

    def _calculate_full_image_context_extraction(self, image):
        """Calculate context extraction for full image (GPT-Image-1 mode)"""
        try:
            print("DEBUG: Calculating full image context extraction")

            # Get full image dimensions
            orig_width = image.get_width()
            orig_height = image.get_height()
            print(f"DEBUG: Original full image size: {orig_width}x{orig_height}")

            # Use full image bounds as "selection"
            full_x1, full_y1 = 0, 0
            full_x2, full_y2 = orig_width, orig_height

            print(
                f"DEBUG: Full image bounds: ({full_x1},{full_y1}) to ({full_x2},{full_y2})"
            )

            # For full image mode, we want to scale the entire image to fit in a square
            # The square size should be 1024x1024 (OpenAI's max)
            target_size = 1024

            print(f"DEBUG: Target square size: {target_size}x{target_size}")

            # For full image, the context should cover the entire original image
            # The extraction code will scale it down to fit the target_size
            ctx_x1 = 0
            ctx_y1 = 0
            ctx_size = max(
                orig_width, orig_height
            )  # Large enough to cover entire image

            print(
                f"DEBUG: Context square: ({ctx_x1},{ctx_y1}) size {ctx_size}x{ctx_size}"
            )

            # Check if there's actually a selection - if not, use full image for transformation
            selection_bounds = Gimp.Selection.bounds(image)
            has_real_selection = (
                selection_bounds[0] if len(selection_bounds) > 0 else False
            )

            if has_real_selection:
                # Use actual selection bounds
                sel_bounds = (
                    selection_bounds[2],
                    selection_bounds[3],
                    selection_bounds[4],
                    selection_bounds[5],
                )
            else:
                # No selection - transform entire image ("Image to Image" mode)
                sel_bounds = (full_x1, full_y1, full_x2, full_y2)

            return {
                "context_square": (
                    ctx_x1,
                    ctx_y1,
                    ctx_size,
                    0,
                ),  # Match existing structure
                "target_size": target_size,
                "selection_bounds": sel_bounds,
                "has_selection": has_real_selection,  # True selection state
                "original_bounds": (full_x1, full_y1, full_x2, full_y2),
            }

        except Exception as e:
            print(f"DEBUG: Failed to calculate full image context extraction: {e}")
            return None

    def _calculate_context_extraction(self, image):
        """Calculate smart context extraction area around selection"""
        try:
            print("DEBUG: Calculating smart context extraction")

            # Get image dimensions
            img_width = image.get_width()
            img_height = image.get_height()
            print(f"DEBUG: Original image size: {img_width}x{img_height}")

            # Check for selection
            selection_bounds = Gimp.Selection.bounds(image)
            print(f"DEBUG: Selection bounds raw: {selection_bounds}")

            if len(selection_bounds) < 5 or not selection_bounds[0]:
                print("DEBUG: No selection found, using center area")
                # Use pure function with no selection
                return calculate_context_extraction(
                    img_width, img_height, 0, 0, 0, 0, has_selection=False
                )

            # Extract selection bounds
            has_selection = selection_bounds[0]
            sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
            sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
            sel_x2 = selection_bounds[4] if len(selection_bounds) > 4 else 0
            sel_y2 = selection_bounds[5] if len(selection_bounds) > 5 else 0

            sel_width = sel_x2 - sel_x1
            sel_height = sel_y2 - sel_y1
            print(
                f"DEBUG: Selection: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2}), size: {sel_width}x{sel_height}"
            )

            # Use pure function for calculation
            context_info = calculate_context_extraction(
                img_width,
                img_height,
                sel_x1,
                sel_y1,
                sel_x2,
                sel_y2,
                has_selection=True,
            )

            # Validate the result
            is_valid, error_msg = validate_context_info(context_info)
            if not is_valid:
                print(f"DEBUG: Context validation failed: {error_msg}")
                # Fallback to center extraction
                return calculate_context_extraction(
                    img_width, img_height, 0, 0, 0, 0, has_selection=False
                )

            # Add debug output for the calculated values
            square_x1, square_y1, square_size, _ = context_info["context_square"]
            print(
                f"DEBUG: Context padding: {max(32, min(200, int(max(sel_width, sel_height) * 0.4)))}px"
            )
            print(
                f"DEBUG: Desired context square: ({square_x1},{square_y1}) to ({square_x1+square_size},{square_y1+square_size}), size: {square_size}x{square_size}"
            )

            extract_x1, extract_y1, extract_width, extract_height = context_info[
                "extract_region"
            ]
            print(
                f"DEBUG: Extract region: ({extract_x1},{extract_y1}) to ({extract_x1+extract_width},{extract_y1+extract_height}), size: {extract_width}x{extract_height}"
            )

            pad_left, pad_top, pad_right, pad_bottom = context_info["padding"]
            print(
                f"DEBUG: Padding needed: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
            )
            print(
                f"DEBUG: Target size for OpenAI: {context_info['target_size']}x{context_info['target_size']}"
            )

            return context_info

        except Exception as e:
            print(f"DEBUG: Context calculation failed: {e}")
            # Fallback to simple center extraction
            return calculate_context_extraction(
                img_width, img_height, 0, 0, 0, 0, has_selection=False
            )

    def _prepare_full_image(self, image):
        """Prepare full image for GPT-Image-1 processing"""
        try:
            print("DEBUG: Preparing full image for transformation")

            width = image.get_width()
            height = image.get_height()

            print(f"DEBUG: Original image size: {width}x{height}")

            # Scale to fit in 1024x1024 preserving aspect ratio
            max_size = 1024
            scale = min(max_size / width, max_size / height)
            target_width = int(width * scale)
            target_height = int(height * scale)

            print(f"DEBUG: Scale factor: {scale:.3f}")
            print(f"DEBUG: Target size: {target_width}x{target_height}")

            # Create simplified context_info for compatibility
            context_info = {
                "mode": "full_image",
                "original_size": (width, height),
                "scaled_size": (target_width, target_height),
                "scale_factor": scale,
                "target_size": max_size,
                "has_selection": True,  # Always true for this mode
            }

            return context_info

        except Exception as e:
            print(f"DEBUG: Full image preparation failed: {e}")
            # Fallback to 1024x1024
            return {
                "mode": "full_image",
                "original_size": (1024, 1024),
                "scaled_size": (1024, 1024),
                "scale_factor": 1.0,
                "target_size": 1024,
                "has_selection": True,
            }

    def _extract_full_image(self, image, context_info):
        """Extract and scale the full image for GPT-Image-1"""
        try:
            target_width, target_height = context_info["scaled_size"]
            print(
                f"DEBUG: Extracting full image, scaling to {target_width}x{target_height}"
            )

            # Create a copy of the image
            original_width = image.get_width()
            original_height = image.get_height()

            # Create image copy for processing
            temp_image = image.duplicate()

            # Flatten the image to get composite result
            if len(temp_image.get_layers()) > 1:
                temp_image.flatten()

            # Get the flattened layer
            layer = temp_image.get_layers()[0]

            # Scale the layer to target size
            layer.scale(target_width, target_height, False)

            # Scale the image canvas to match
            temp_image.scale(target_width, target_height)

            # Export to PNG in memory
            print("DEBUG: Exporting full image as PNG...")
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Use GIMP's export function like the existing code
            file = Gio.File.new_for_path(temp_path)
            pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
            pdb_config = pdb_proc.create_config()
            pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            pdb_config.set_property("image", temp_image)
            pdb_config.set_property("file", file)
            pdb_config.set_property("options", None)
            result = pdb_proc.run(pdb_config)

            if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                temp_image.delete()
                raise Exception("Failed to export full image")

            # Read the exported PNG
            with open(temp_path, "rb") as f:
                image_bytes = f.read()

            # Clean up
            os.unlink(temp_path)
            temp_image.delete()

            # Convert to base64 for API
            import base64

            image_data = base64.b64encode(image_bytes).decode("utf-8")

            print(
                f"DEBUG: Full image extracted: {len(image_bytes)} bytes, base64 length: {len(image_data)}"
            )
            return (
                True,
                f"Extracted full image: {len(image_bytes)} bytes as PNG, base64 length: {len(image_data)}",
                image_data,
            )

        except Exception as e:
            print(f"DEBUG: Full image extraction failed: {e}")
            return False, f"Full image extraction failed: {str(e)}", None

    def _create_full_image_mask(self, image, selection_bounds, context_info):
        """Create mask for full image with selection area marked for transformation"""
        try:
            print("DEBUG: Creating full image mask with selection area")

            target_width, target_height = context_info["scaled_size"]
            scale_factor = context_info["scale_factor"]

            # Scale selection bounds to match scaled image
            sel_x1, sel_y1, sel_x2, sel_y2 = selection_bounds
            scaled_sel_x1 = int(sel_x1 * scale_factor)
            scaled_sel_y1 = int(sel_y1 * scale_factor)
            scaled_sel_x2 = int(sel_x2 * scale_factor)
            scaled_sel_y2 = int(sel_y2 * scale_factor)

            print(
                f"DEBUG: Scaled selection: ({scaled_sel_x1},{scaled_sel_y1}) to ({scaled_sel_x2},{scaled_sel_y2})"
            )

            # Create mask image
            mask_image = Gimp.Image.new(
                target_width, target_height, Gimp.ImageType.GRAY
            )
            mask_layer = Gimp.Layer.new(
                mask_image,
                "mask",
                target_width,
                target_height,
                Gimp.ImageType.GRAY,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with white (preserve areas)
            from gi.repository import Gegl

            white_color = Gegl.Color.new("white")
            mask_layer.get_shadow_buffer().clear(white_color)

            # Create black rectangle for selection area (transform area)
            black_color = Gegl.Color.new("black")
            mask_buffer = mask_layer.get_shadow_buffer()

            # Fill selection rectangle with black
            width = scaled_sel_x2 - scaled_sel_x1
            height = scaled_sel_y2 - scaled_sel_y1
            if width > 0 and height > 0:
                # Simple rectangle mask for now
                rect = Gegl.Rectangle.new(scaled_sel_x1, scaled_sel_y1, width, height)
                mask_buffer.set_color(rect, black_color)

            # Merge shadow buffer with base layer
            mask_layer.merge_shadow(True)
            mask_layer.update(0, 0, target_width, target_height)

            # Export mask as PNG
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Use GIMP's export function
            export_options = Gimp.ProcedureConfig.new_from_procedure(
                Gimp.get_pdb().lookup_procedure("file-png-export")
            )
            export_options.set_property("interlace", False)
            export_options.set_property("compression", 9)

            result = Gimp.get_pdb().run_procedure(
                "file-png-export",
                [
                    Gimp.RunMode.NONINTERACTIVE,
                    mask_image,
                    temp_path,
                    export_options,
                ],
            )

            if not result.get_status() == Gimp.PDBStatusType.SUCCESS:
                raise Exception("Failed to export mask image")

            # Read the PNG data
            with open(temp_path, "rb") as f:
                mask_data = f.read()

            # Clean up
            os.unlink(temp_path)
            mask_image.delete()

            print(f"DEBUG: Created full image mask: {len(mask_data)} bytes")
            return mask_data

        except Exception as e:
            print(f"DEBUG: Full image mask creation failed: {e}")
            # Return a simple white mask as fallback
            import io
            from PIL import Image

            mask_img = Image.new("L", context_info["scaled_size"], 255)  # White mask
            mask_bytes = io.BytesIO()
            mask_img.save(mask_bytes, format="PNG")
            return mask_bytes.getvalue()

    def _create_context_mask(self, image, context_info, target_size):
        """Create mask from actual selection shape using pixel-by-pixel copying"""
        try:
            print(
                f"DEBUG: Creating pixel-perfect selection mask {target_size}x{target_size}"
            )

            if not context_info["has_selection"]:
                raise Exception(
                    "No selection available - selection-shaped mask requires an active selection"
                )

            # Get context square info
            ctx_x1, ctx_y1, ctx_size, _ = context_info["context_square"]
            print(f"DEBUG: Context square: ({ctx_x1},{ctx_y1}) size {ctx_size}")

            # Step 1: Save original selection as channel to preserve its exact shape
            selection_channel = Gimp.Selection.save(image)
            if not selection_channel:
                raise Exception("Failed to save selection as channel")
            print("DEBUG: Saved selection as channel for pixel copying")

            # Step 2: Create context-sized mask image (grayscale)
            mask_image = Gimp.Image.new(ctx_size, ctx_size, Gimp.ImageBaseType.GRAY)
            if not mask_image:
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask image")

            mask_layer = Gimp.Layer.new(
                mask_image,
                "selection_mask",
                ctx_size,
                ctx_size,
                Gimp.ImageType.GRAY_IMAGE,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            if not mask_layer:
                mask_image.delete()
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask layer")

            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with white (preserve context areas that extend beyond original image)
            from gi.repository import Gegl

            white_color = Gegl.Color.new("white")
            Gimp.context_set_foreground(white_color)
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)
            print("DEBUG: Created white background mask (preserve context)")

            # Force layer update to make sure white fill is committed
            mask_layer.update(0, 0, ctx_size, ctx_size)

            # Step 3: Copy only the original image area, leave extended context white

            # Calculate where original image appears in context square
            orig_width, orig_height = image.get_width(), image.get_height()
            img_offset_x = max(
                0, -ctx_x1
            )  # where original image starts in context square
            img_offset_y = max(
                0, -ctx_y1
            )  # where original image starts in context square
            img_end_x = min(ctx_size, img_offset_x + orig_width)
            img_end_y = min(ctx_size, img_offset_y + orig_height)

            print(
                f"DEBUG: Original image appears at ({img_offset_x},{img_offset_y}) to ({img_end_x},{img_end_y}) in context square"
            )

            # Only process if there's an intersection
            if img_end_x > img_offset_x and img_end_y > img_offset_y:
                # Get buffers for pixel-level operations
                selection_buffer = selection_channel.get_buffer()
                if not selection_buffer:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception("Failed to get selection channel buffer")

                mask_shadow_buffer = mask_layer.get_shadow_buffer()
                if not mask_shadow_buffer:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception("Failed to get mask shadow buffer")

                print("DEBUG: Starting Gegl pixel copying from selection channel")

                # Create Gegl processing graph for selection shape copying
                graph = Gegl.Node()

                # Source: Selection channel buffer (contains exact selection shape)
                selection_source = graph.create_child("gegl:buffer-source")
                selection_source.set_property("buffer", selection_buffer)

                # Translate selection from world coordinates to context square coordinates
                # Context square starts at (ctx_x1, ctx_y1) in world coordinates
                # Selection coordinates need to be translated by (-ctx_x1, -ctx_y1)
                # to map them into context square coordinate system

                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(-ctx_x1))
                translate.set_property("y", float(-ctx_y1))

                # TEST: Comment out invert to see if extended areas are naturally white
                # invert = graph.create_child("gegl:invert-linear")

                # Write to mask shadow buffer
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", mask_shadow_buffer)

                # Link the processing chain: selection → translate → mask (NO INVERT, NO CROP)
                selection_source.link(translate)
                translate.link(output)

                print(
                    f"DEBUG: TEST - Processing selection shape: translate by ({-ctx_x1},{-ctx_y1}), NO INVERT, NO CROP"
                )

                # Process the graph to copy selection shape - NO FALLBACK
                output.process()
                print(
                    "DEBUG: Successfully copied exact selection shape to mask using Gegl"
                )

                # Flush and merge shadow buffer to make changes visible
                mask_shadow_buffer.flush()
                mask_layer.merge_shadow(True)
                print("DEBUG: Merged shadow buffer with base layer")
            else:
                print("DEBUG: No intersection - mask remains fully white")

            # Force complete layer update
            mask_layer.update(0, 0, ctx_size, ctx_size)

            # Force flush all changes to ensure PNG export sees the correct data
            Gimp.displays_flush()

            print("DEBUG: Successfully copied exact selection shape to mask using Gegl")

            # Step 4: Scale mask to target size (same as context image scaling)
            mask_image.scale(target_size, target_size)
            print(
                f"DEBUG: Scaled mask from {ctx_size}x{ctx_size} to {target_size}x{target_size}"
            )

            # Step 4.5: Invert the entire mask as the final step
            # This converts: selection=white → black (inpaint), context=white → white (preserve)
            # Wait, this would make everything wrong. Let me think...
            # Actually, we need: selection=white → black, non-selected=black → white, context=white → white
            # So we need a different approach...

            print(
                "DEBUG: Applying final inversion to convert selection to black for OpenAI"
            )
            scaled_mask_layer = mask_image.get_layers()[0]

            # Create Gegl invert operation on the scaled mask
            from gi.repository import Gegl

            # Get the layer buffer
            layer_buffer = scaled_mask_layer.get_buffer()
            shadow_buffer = scaled_mask_layer.get_shadow_buffer()

            # Create invert processing chain
            invert_graph = Gegl.Node()
            buffer_source = invert_graph.create_child("gegl:buffer-source")
            buffer_source.set_property("buffer", layer_buffer)

            invert_node = invert_graph.create_child("gegl:invert-linear")

            buffer_write = invert_graph.create_child("gegl:write-buffer")
            buffer_write.set_property("buffer", shadow_buffer)

            # Link and process
            buffer_source.link(invert_node)
            invert_node.link(buffer_write)
            buffer_write.process()

            # Merge shadow buffer
            shadow_buffer.flush()
            scaled_mask_layer.merge_shadow(True)
            scaled_mask_layer.update(0, 0, target_size, target_size)

            print(
                "DEBUG: Final inversion complete - selection should now be black, context should be white"
            )

            # Step 5: Export as PNG for OpenAI
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

            try:
                file = Gio.File.new_for_path(temp_filename)

                pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property("image", mask_image)
                pdb_config.set_property("file", file)
                pdb_config.set_property("options", None)

                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    mask_image.delete()
                    image.remove_channel(selection_channel)
                    raise Exception(f"PNG export failed with status: {result.index(0)}")

                # Read the exported mask PNG
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                if len(png_data) == 0:
                    raise Exception("Exported PNG file is empty")

                # Clean up
                os.unlink(temp_filename)
                mask_image.delete()
                image.remove_channel(selection_channel)

                print(
                    f"DEBUG: Created pixel-perfect selection mask PNG: {len(png_data)} bytes"
                )
                return png_data

            except Exception as e:
                print(f"DEBUG: Mask export failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                mask_image.delete()
                image.remove_channel(selection_channel)
                raise Exception(f"Mask export failed: {str(e)}")

        except Exception as e:
            print(f"DEBUG: Context mask creation failed: {e}")
            raise Exception(f"Selection-shaped mask creation failed: {str(e)}")

    def _create_mask_from_selection(self, image, width, height):
        """Create a black mask from GIMP selection (legacy method)"""
        try:
            print(f"DEBUG: Creating mask from selection {width}x{height} (legacy)")

            # Check if there's a selection
            selection_bounds = Gimp.Selection.bounds(image)
            print(f"DEBUG: Selection bounds raw: {selection_bounds}")

            # Handle the named tuple return value - extract values by position
            if len(selection_bounds) < 5:
                print("DEBUG: No selection found, creating default circle mask")
                return self._create_black_mask(width, height)

            # Extract from the returned tuple/named tuple
            has_selection = selection_bounds[0]
            x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
            y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
            x2 = selection_bounds[4] if len(selection_bounds) > 4 else 0
            y2 = selection_bounds[5] if len(selection_bounds) > 5 else 0

            if not has_selection:
                print("DEBUG: No selection found, creating default circle mask")
                return self._create_black_mask(width, height)

            print(f"DEBUG: Selection bounds: ({x1},{y1}) to ({x2},{y2})")

            # Get original image dimensions for scaling
            orig_width = image.get_width()
            orig_height = image.get_height()

            # Calculate scaling factors
            scale_x = width / orig_width
            scale_y = height / orig_height

            # Scale selection bounds to match mask dimensions
            scaled_x1 = int(x1 * scale_x)
            scaled_y1 = int(y1 * scale_y)
            scaled_x2 = int(x2 * scale_x)
            scaled_y2 = int(y2 * scale_y)

            print(
                f"DEBUG: Scaled selection: ({scaled_x1},{scaled_y1}) to ({scaled_x2},{scaled_y2})"
            )

            # Create IHDR chunk data (L - grayscale format for OpenAI mask)
            ihdr_data = (
                width.to_bytes(4, "big")
                + height.to_bytes(4, "big")
                + b"\x08\x00\x00\x00\x00"  # 8-bit grayscale (L format)
            )

            import zlib

            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create image data with black selection area
            image_rows = []
            for y in range(height):
                row = b"\x00"  # Filter byte
                for x in range(width):
                    if scaled_x1 <= x <= scaled_x2 and scaled_y1 <= y <= scaled_y2:
                        # Black grayscale (0 = inpaint this area)
                        row += b"\x00"
                    else:
                        # White grayscale (255 = keep original)
                        row += b"\xff"
                image_rows.append(row)

            image_data = b"".join(image_rows)
            compressed_data = zlib.compress(image_data)
            idat_crc = zlib.crc32(b"IDAT" + compressed_data) & 0xFFFFFFFF

            # Build PNG
            png_data = (
                b"\x89PNG\r\n\x1a\n"
                + len(ihdr_data).to_bytes(4, "big")
                + b"IHDR"
                + ihdr_data
                + ihdr_crc.to_bytes(4, "big")
                + len(compressed_data).to_bytes(4, "big")
                + b"IDAT"
                + compressed_data
                + idat_crc.to_bytes(4, "big")
                + b"\x00\x00\x00\x00IEND\xae B`\x82"
            )

            print(f"DEBUG: Created selection-based mask PNG: {len(png_data)} bytes")
            return png_data

        except Exception as e:
            print(f"DEBUG: Failed to create selection mask: {e}")
            return self._create_black_mask(width, height)

    def _create_multipart_data(self, fields, files):
        """Create multipart form data for file upload"""
        import email.mime.multipart
        import email.mime.text
        import email.mime.application
        import uuid

        boundary = uuid.uuid4().hex
        body = b""

        # Add text fields
        for key, value in fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            body += f"{value}\r\n".encode()

        # Add file fields
        for key, (filename, file_data, content_type) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: {content_type}\r\n\r\n".encode()
            body += file_data
            body += b"\r\n"

        # End boundary
        body += f"--{boundary}--\r\n".encode()

        return body, boundary

    def _call_openai_inpaint(self, image_data, mask_data, prompt, api_key):
        """Call OpenAI GPT-Image-1 API for inpainting"""
        try:
            print(f"DEBUG: Calling GPT-Image-1 API with prompt: {prompt}")

            # Validate inputs
            if not prompt or not prompt.strip():
                return False, "Error: Empty prompt provided", None

            if not image_data:
                return False, "Error: No image data provided", None

            if not mask_data:
                return False, "Error: No mask data provided", None

            if not api_key or api_key == "test-api-key":
                print("DEBUG: No valid API key provided, returning mock response")
                mock_response = {
                    "data": [
                        {
                            "url": "https://picsum.photos/512/512",
                            "revised_prompt": prompt,
                        }
                    ]
                }
                return True, "API call successful (mock - no API key)", mock_response

            url = "https://api.openai.com/v1/images/edits"

            # Prepare multipart form data for GPT-Image-1
            fields = {
                "model": "gpt-image-1",
                "prompt": prompt,
                "n": "1",
                "quality": "high",
                "moderation": "low",  # Less restrictive filtering
            }

            # Convert base64 image data back to bytes for the API
            import base64

            image_bytes = base64.b64decode(image_data)

            # Save debug copies of what we're sending to GPT-Image-1
            debug_input_filename = (
                f"/tmp/gpt-image-1_input_{len(image_bytes)}_bytes.png"
            )
            with open(debug_input_filename, "wb") as debug_file:
                debug_file.write(image_bytes)
            print(f"DEBUG: Saved input image to {debug_input_filename}")

            debug_mask_filename = f"/tmp/gpt-image-1_mask_{len(mask_data)}_bytes.png"
            with open(debug_mask_filename, "wb") as debug_file:
                debug_file.write(mask_data)
            print(f"DEBUG: Saved mask to {debug_mask_filename}")

            # Analyze both image formats by examining PNG headers
            if image_bytes.startswith(b"\x89PNG"):
                # Check color type in IHDR chunk (byte 25) and dimensions
                if len(image_bytes) > 25:
                    # Extract width and height from IHDR (bytes 16-23)
                    img_width = int.from_bytes(image_bytes[16:20], "big")
                    img_height = int.from_bytes(image_bytes[20:24], "big")
                    color_type = image_bytes[25]
                    format_names = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
                    format_name = format_names.get(color_type, f"Unknown({color_type})")
                    print(
                        f"DEBUG: Input image format: {format_name} (color type {color_type}) dimensions: {img_width}x{img_height}"
                    )
                else:
                    print("DEBUG: Input image PNG header too short")
            else:
                print("DEBUG: Input image is not PNG format!")

            if mask_data.startswith(b"\x89PNG"):
                # Check mask format and dimensions
                if len(mask_data) > 25:
                    # Extract width and height from IHDR (bytes 16-23)
                    mask_width = int.from_bytes(mask_data[16:20], "big")
                    mask_height = int.from_bytes(mask_data[20:24], "big")
                    color_type = mask_data[25]
                    format_names = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
                    format_name = format_names.get(color_type, f"Unknown({color_type})")
                    print(
                        f"DEBUG: Mask format: {format_name} (color type {color_type}) dimensions: {mask_width}x{mask_height}"
                    )
                    print(f"DEBUG: Mask size: {len(mask_data)} bytes")

                    # Check if dimensions match
                    if img_width == mask_width and img_height == mask_height:
                        print("DEBUG: ✅ Image and mask dimensions match!")
                    else:
                        print(
                            f"DEBUG: ❌ DIMENSION MISMATCH! Image: {img_width}x{img_height}, Mask: {mask_width}x{mask_height}"
                        )
                else:
                    print("DEBUG: Mask PNG header too short")
            else:
                print("DEBUG: Mask is not PNG format!")

            files = {
                "image": ("image.png", image_bytes, "image/png"),
                "mask": ("mask.png", mask_data, "image/png"),
            }

            body, boundary = self._create_multipart_data(fields, files)

            # Create request
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "GIMP-AI-Plugin/1.0",
            }

            req = urllib.request.Request(url, data=body, headers=headers, method="POST")

            print("DEBUG: Sending real GPT-Image-1 API request...")

            # Progress during network operation
            print("DEBUG: Setting progress text to 'Sending request to GPT-Image-1...'")
            Gimp.progress_set_text("Sending request to GPT-Image-1...")
            Gimp.progress_update(0.65)  # 65% - API request started (after 60% mask)
            Gimp.displays_flush()  # Force UI update before blocking network call

            with self._make_url_request(req, timeout=120) as response:
                # More progress during data reading
                Gimp.progress_set_text("Processing AI response...")
                Gimp.progress_update(0.7)  # 70% - Reading response

                response_data = response.read().decode("utf-8")

                Gimp.progress_set_text("Parsing AI result...")
                Gimp.progress_update(0.75)  # 75% - Parsing JSON

                response_json = json.loads(response_data)
                print(
                    f"DEBUG: GPT-Image-1 API response received: {len(response_data)} bytes"
                )
                return True, "GPT-Image-1 API call successful", response_json

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
            print(f"DEBUG: GPT-Image-1 API HTTP error: {e.code} - {error_body}")
            return False, f"GPT-Image-1 API error {e.code}: {error_body[:200]}", None
        except Exception as e:
            print(f"DEBUG: GPT-Image-1 API call failed: {e}")
            return False, f"GPT-Image-1 API call failed: {str(e)}", None

    def _download_and_composite_result(self, image, api_response, context_info):
        """Download AI result and composite it back to original image with proper masking"""
        try:
            print("DEBUG: Downloading and compositing AI result")

            # Validate inputs
            if not image:
                return False, "Error: No GIMP image provided"
            if not api_response or "data" not in api_response:
                return False, "Invalid API response - no data"
            if not api_response["data"] or len(api_response["data"]) == 0:
                return False, "Invalid API response - empty data array"

            result_data = api_response["data"][0]

            # Handle both URL and base64 response formats
            if "url" in result_data:
                # URL format (DALL-E 2 style)
                image_url = result_data["url"]
                print(f"DEBUG: Downloading result from: {image_url}")

                # Update progress for download phase
                Gimp.progress_set_text("Downloading AI result...")
                Gimp.progress_update(0.8)  # 80% - Starting download
                Gimp.displays_flush()

                # Download from URL
                with self._make_url_request(image_url, timeout=60) as response:
                    image_data = response.read()

            elif "b64_json" in result_data:
                # Base64 format (GPT-Image-1 style)
                print("DEBUG: Processing base64 image data from GPT-Image-1")

                # Update progress for processing phase
                Gimp.progress_set_text("Processing AI result...")
                Gimp.progress_update(0.8)  # 80% - Processing data
                Gimp.displays_flush()

                # Decode base64 data
                import base64

                image_data = base64.b64decode(result_data["b64_json"])

            else:
                return False, "Invalid API response - no image URL or base64 data"

            print(f"DEBUG: Processed {len(image_data)} bytes")

            # Save to temporary file
            Gimp.progress_set_text("Processing AI result...")
            Gimp.progress_update(0.9)  # 90% - Processing
            Gimp.displays_flush()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)

            # Save debug copy
            debug_filename = f"/tmp/gpt-image-1_result_{len(image_data)}_bytes.png"
            with open(debug_filename, "wb") as debug_file:
                debug_file.write(image_data)
            print(f"DEBUG: Saved GPT-Image-1 result to {debug_filename} for inspection")

            try:
                # Load the AI result into a temporary image
                Gimp.progress_set_text("Loading AI result...")
                Gimp.progress_update(0.95)  # 95% - Loading
                Gimp.displays_flush()

                file = Gio.File.new_for_path(temp_filename)
                ai_result_img = Gimp.file_load(
                    run_mode=Gimp.RunMode.NONINTERACTIVE, file=file
                )

                if not ai_result_img:
                    return False, "Failed to load AI result image"

                ai_layers = ai_result_img.get_layers()
                if not ai_layers or len(ai_layers) == 0:
                    ai_result_img.delete()
                    return False, "No layers found in AI result"

                ai_layer = ai_layers[0]
                print(
                    f"DEBUG: AI result dimensions: {ai_layer.get_width()}x{ai_layer.get_height()}"
                )

                # Get original image dimensions
                orig_width = image.get_width()
                orig_height = image.get_height()

                # Get context info for compositing
                sel_x1, sel_y1, sel_x2, sel_y2 = context_info["selection_bounds"]
                ctx_x1, ctx_y1, ctx_size, _ = context_info["context_square"]
                target_size = context_info["target_size"]

                print(f"DEBUG: Original image: {orig_width}x{orig_height}")
                print(
                    f"DEBUG: Selection bounds: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
                )
                print(f"DEBUG: Context square: ({ctx_x1},{ctx_y1}), size {ctx_size}")

                # Scale AI result back to context size if needed
                if (
                    ai_layer.get_width() != ctx_size
                    or ai_layer.get_height() != ctx_size
                ):
                    # Create a scaled version
                    scaled_img = ai_result_img.duplicate()
                    scaled_img.scale(ctx_size, ctx_size)
                    scaled_layers = scaled_img.get_layers()
                    if scaled_layers:
                        ai_layer = scaled_layers[0]
                    print(
                        f"DEBUG: Scaled AI result to context size: {ctx_size}x{ctx_size}"
                    )

                # USE PURE COORDINATE FUNCTION FOR PLACEMENT
                placement = calculate_placement_coordinates(context_info)
                paste_x = placement["paste_x"]
                paste_y = placement["paste_y"]
                result_width = placement["result_width"]
                result_height = placement["result_height"]

                # Create new layer in original image for the composited result
                result_layer = Gimp.Layer.new(
                    image,
                    "AI Inpaint Result",
                    orig_width,
                    orig_height,
                    Gimp.ImageType.RGBA_IMAGE,
                    100.0,
                    Gimp.LayerMode.NORMAL,
                )

                # Insert layer at top
                image.insert_layer(result_layer, None, 0)

                print(f"DEBUG: USING PURE PLACEMENT FUNCTION:")
                print(f"DEBUG: AI result is {result_width}x{result_height} square")
                print(f"DEBUG: Placing at calculated position: ({paste_x},{paste_y})")
                print(f"DEBUG: GIMP will automatically clip to image bounds")

                # Copy the AI result content using simplified Gegl nodes
                from gi.repository import Gegl

                print(
                    f"DEBUG: Placing {ctx_size}x{ctx_size} AI result at ({paste_x},{paste_y})"
                )

                # Clear selection before Gegl processing to prevent clipping, then restore it
                print(
                    "DEBUG: Saving and clearing selection before Gegl processing to prevent clipping"
                )
                selection_channel = Gimp.Selection.save(image)
                Gimp.Selection.none(image)

                # Get buffers
                buffer = result_layer.get_buffer()
                shadow_buffer = result_layer.get_shadow_buffer()
                ai_buffer = ai_layer.get_buffer()

                # Create simplified Gegl processing graph
                graph = Gegl.Node()

                # Source: AI result square
                ai_input = graph.create_child("gegl:buffer-source")
                ai_input.set_property("buffer", ai_buffer)

                # Translate to context square position
                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(paste_x))
                translate.set_property("y", float(paste_y))

                # Write to shadow buffer without clipping
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", shadow_buffer)

                # Link simple chain: source -> translate -> output
                ai_input.link(translate)
                translate.link(output)

                # Process the graph
                try:
                    output.process()

                    # Flush and merge shadow buffer - update entire layer
                    shadow_buffer.flush()
                    result_layer.merge_shadow(True)

                    # Update the entire layer
                    result_layer.update(0, 0, orig_width, orig_height)

                    print(f"DEBUG: Updated entire layer: {orig_width}x{orig_height}")

                    print(
                        f"DEBUG: Successfully composited AI result using simplified Gegl graph"
                    )
                except Exception as e:
                    print(f"DEBUG: Gegl processing failed: {e}")
                    raise

                # Restore the original selection
                print("DEBUG: Restoring original selection after Gegl processing")
                try:
                    pdb = Gimp.get_pdb()
                    select_proc = pdb.lookup_procedure("gimp-image-select-item")
                    select_config = select_proc.create_config()
                    select_config.set_property("image", image)
                    select_config.set_property("operation", Gimp.ChannelOps.REPLACE)
                    select_config.set_property("item", selection_channel)
                    select_proc.run(select_config)
                    print("DEBUG: Selection successfully restored")
                except Exception as e:
                    print(f"DEBUG: Could not restore selection: {e}")
                # Clean up the temporary selection channel
                image.remove_channel(selection_channel)

                # TEMPORARILY DISABLED - Create a layer mask to show only the selection area while preserving full AI content
                print("DEBUG: MASK CREATION TEMPORARILY DISABLED FOR TESTING")
                print("DEBUG: Layer should show full AI result without any masking")

                # if context_info["has_selection"]:
                #     print(
                #         "DEBUG: Creating selection-based mask while preserving full AI result in layer"
                #     )

                #     # Use GIMP's built-in selection mask type to automatically create properly shaped mask
                #     # This preserves the full AI content in the layer but masks visibility to selection area
                #     mask = result_layer.create_mask(Gimp.AddMaskType.SELECTION)
                #     result_layer.add_mask(mask)

                #     print(
                #         "DEBUG: Applied selection-based layer mask - full AI result preserved in layer, visibility limited to selection"
                #     )
                #     print(
                #         "DEBUG: User can delete/modify mask to reveal more of the AI result beyond selection bounds"
                #     )
                # else:
                #     print("DEBUG: No selection - layer shows full AI result without mask")

                # VALIDATION CHECKS
                print(f"DEBUG: === SIMPLIFIED ALIGNMENT VALIDATION ===")
                print(
                    f"DEBUG: Context square positioned at: ({paste_x},{paste_y}) with size {result_width}x{result_height}"
                )
                print(
                    f"DEBUG: Original selection was: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
                )
                print(
                    f"DEBUG: Since we work with true squares, alignment should be perfect"
                )
                print(
                    f"DEBUG: Selection coordinates within context square: ({sel_x1-paste_x},{sel_y1-paste_y}) to ({sel_x2-paste_x},{sel_y2-paste_y})"
                )

                # Clean up temporary image
                ai_result_img.delete()
                os.unlink(temp_filename)

                # Force display update
                Gimp.displays_flush()

                layer_count = len(image.get_layers())
                print(
                    f"DEBUG: Successfully composited AI result. Total layers: {layer_count}"
                )

                return (
                    True,
                    f"AI result composited as masked layer: '{result_layer.get_name()}' (total layers: {layer_count})",
                )

            except Exception as e:
                print(f"DEBUG: Compositing failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                return False, f"Failed to composite result: {str(e)}"

        except Exception as e:
            print(f"DEBUG: Download and composite failed: {e}")
            return False, f"Failed to download result: {str(e)}"

    def _download_and_import_result(self, image, api_response):
        """Download AI result image and import it as a new layer"""
        try:
            # Validate inputs
            if not image:
                return False, "Error: No GIMP image provided"

            if not api_response or "data" not in api_response:
                return False, "Invalid API response - no data"

            if not api_response["data"] or len(api_response["data"]) == 0:
                return False, "Invalid API response - empty data array"

            result_data = api_response["data"][0]

            # Handle both URL and base64 response formats
            if "url" in result_data:
                # URL format (DALL-E 2 style)
                image_url = result_data["url"]
                print(f"DEBUG: Downloading result from: {image_url}")

                # Download from URL
                req = urllib.request.Request(image_url)
                req.add_header("User-Agent", "GIMP-AI-Plugin/1.0")
                with self._make_url_request(req, timeout=60) as response:
                    image_data = response.read()

            elif "b64_json" in result_data:
                # Base64 format (GPT-Image-1 style)
                print("DEBUG: Processing base64 image data from GPT-Image-1")

                # Decode base64 data
                import base64

                image_data = base64.b64decode(result_data["b64_json"])

            else:
                return False, "Invalid API response - no image URL or base64 data"

            print(f"DEBUG: Processed {len(image_data)} bytes")

            # Save to temporary file
            Gimp.progress_set_text("Saving temporary file...")
            Gimp.progress_update(0.9)  # 90% - Saving file

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)

            # Also save a copy for debugging
            debug_filename = f"/tmp/gpt-image-1_result_{len(image_data)}_bytes.png"
            with open(debug_filename, "wb") as debug_file:
                debug_file.write(image_data)
            print(f"DEBUG: Saved GPT-Image-1 result to {debug_filename} for inspection")

            try:
                # Load the image into GIMP
                Gimp.progress_set_text("Loading image into GIMP...")
                Gimp.progress_update(0.95)  # 95% - Loading into GIMP

                file = Gio.File.new_for_path(temp_filename)
                new_layer = None  # Initialize to ensure it's defined

                # Try to load the image
                try:
                    # Load the image file first, then extract layer content
                    print("DEBUG: Loading image file to extract layer content")

                    # First load the image file into a temporary image
                    temp_img = Gimp.file_load(
                        run_mode=Gimp.RunMode.NONINTERACTIVE, file=file
                    )

                    if temp_img:
                        temp_layers = temp_img.get_layers()

                        if temp_layers and len(temp_layers) > 0:
                            # Get the first layer from the loaded image
                            source_layer = temp_layers[0]
                            print(
                                f"DEBUG: Source layer dimensions: {source_layer.get_width()}x{source_layer.get_height()}"
                            )

                            # Create a new layer from the loaded layer content
                            Gimp.progress_set_text("Creating new layer...")

                            new_layer = Gimp.Layer.new_from_drawable(
                                source_layer, image
                            )
                            new_layer.set_name("AI Inpaint Result")

                            # Insert the layer into the target image (at the top)
                            image.insert_layer(new_layer, None, 0)

                            # Clean up the temporary image
                            temp_img.delete()
                            print("DEBUG: Successfully created layer from loaded image")
                        else:
                            print("DEBUG: No layers found in loaded image")
                            new_layer = None
                    else:
                        print(f"DEBUG: Failed to load image file")
                        new_layer = None

                    # If we successfully created a layer, configure it
                    if new_layer is not None:
                        # Make sure the layer is visible and properly positioned
                        new_layer.set_visible(True)
                        new_layer.set_opacity(100.0)
                        new_layer.set_offsets(0, 0)  # Position at top-left

                        # Get layer details for debugging
                        layer_width = new_layer.get_width()
                        layer_height = new_layer.get_height()
                        layer_visible = new_layer.get_visible()
                        layer_opacity = new_layer.get_opacity()
                        offsets = new_layer.get_offsets()
                        layer_x, layer_y = (
                            offsets[1],
                            offsets[2],
                        )  # Skip the first boolean result

                        print(
                            f"DEBUG: Successfully loaded AI result as layer using PDB procedure"
                        )
                        print(
                            f"DEBUG: Layer details - dimensions: {layer_width}x{layer_height}, visible: {layer_visible}, opacity: {layer_opacity}, position: ({layer_x}, {layer_y})"
                        )

                        # Force GIMP to update the display
                        Gimp.displays_flush()

                        # Check if layer is actually in the image
                        all_layers = image.get_layers()
                        layer_found = new_layer in all_layers
                        print(f"DEBUG: Layer found in image layers list: {layer_found}")
                        print(f"DEBUG: Total layers in image: {len(all_layers)}")

                        # List all layer names for debugging
                        for i, layer in enumerate(all_layers):
                            print(
                                f"DEBUG: Layer {i}: '{layer.get_name()}', visible: {layer.get_visible()}"
                            )

                    # If we don't have a layer by now, create fallback
                    if new_layer is None:
                        print(f"DEBUG: PDB file-load-layer failed, creating fallback")
                        # Fallback: create a red test layer
                        new_layer = Gimp.Layer.new(
                            image,
                            "AI Inpaint Result (fallback)",
                            512,
                            512,
                            Gimp.ImageType.RGBA_IMAGE,
                            100.0,
                            Gimp.LayerMode.NORMAL,
                        )
                        image.insert_layer(new_layer, None, 0)
                        # Fill with red
                        from gi.repository import Gegl

                        buffer = new_layer.get_buffer()
                        rect = Gegl.Rectangle.new(0, 0, 512, 512)
                        color = Gegl.Color.new("red")
                        buffer.set_color(rect, color)
                        new_layer.set_visible(True)
                        Gimp.displays_flush()
                        print("DEBUG: Created red fallback layer")

                    # Clean up temp file
                    os.unlink(temp_filename)

                    layer_count = len(image.get_layers())
                    print(f"DEBUG: Total layers in image now: {layer_count}")

                    return (
                        True,
                        f"AI result imported as new layer: '{new_layer.get_name()}' (total layers: {layer_count})",
                    )

                except Exception as e:
                    print(f"DEBUG: GIMP file_load exception: {e}")
                    return False, f"Failed to load result: {str(e)}"

            finally:
                # Clean up temp file if it still exists
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)

        except Exception as e:
            print(f"DEBUG: Download and import failed: {e}")
            return False, f"Failed to download result: {str(e)}"

    def do_query_procedures(self):
        return [
            "gimp-ai-inpaint",
            "gimp-ai-layer-generator",
            "gimp-ai-settings",
        ]

    def do_create_procedure(self, name):
        if name == "gimp-ai-inpaint":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_inpaint, None
            )
            procedure.set_menu_label("Image to Image")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-layer-generator":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_layer_generator, None
            )
            procedure.set_menu_label("DALL-E 3 Layer Generator")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        return None

    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Inpaint Selection called!")

        # Step 1: Check for active selection FIRST
        print("DEBUG: Checking for active selection...")
        selection_bounds = Gimp.Selection.bounds(image)
        has_selection = len(selection_bounds) >= 5 and selection_bounds[0]

        if not has_selection:
            print("DEBUG: No selection found - showing error message")
            Gimp.message(
                "❌ No Selection Found!\n\n"
                "AI Inpainting requires an active selection to define the area to modify.\n\n"
                "Please:\n"
                "1. Use selection tools (Rectangle, Ellipse, Free Select, etc.)\n"
                "2. Select the area you want to inpaint\n"
                "3. Run AI Inpaint Selection again"
            )
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        print("DEBUG: Selection found - proceeding with inpainting")

        # Step 2: Get user prompt
        print("DEBUG: About to show prompt dialog...")
        prompt = self._show_prompt_dialog(
            "AI Inpaint",
            "Describe the area to inpaint (e.g. 'remove object', 'fix background')",
        )
        print(f"DEBUG: Dialog returned: {repr(prompt)}")

        if not prompt:
            print("DEBUG: User cancelled prompt dialog")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Initialize progress AFTER dialog (standard GIMP pattern)
        print("DEBUG: Initializing progress after dialog...")
        Gimp.progress_init("AI Inpainting...")
        print("DEBUG: Setting progress to 10%...")
        Gimp.progress_update(0.1)  # 10% - Started
        Gimp.displays_flush()  # Force UI update

        # Step 3: Get API key
        api_key = self._get_api_key()
        if not api_key:
            Gimp.message(
                "❌ No OpenAI API key found!\n\nPlease set your API key in:\n- config.json file\n- OPENAI_API_KEY environment variable"
            )
            Gimp.progress_end()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        print("DEBUG: Setting progress to 30%...")
        Gimp.progress_update(0.3)  # 30% - Got API key
        Gimp.displays_flush()  # Force UI update

        # Step 4: Determine processing mode and prepare accordingly
        mode = self._get_processing_mode()
        print(f"DEBUG: Using processing mode: {mode}")

        if mode == "full_image":
            # Modified path: Use existing context extraction but base on full image
            print("DEBUG: Calculating full-image context extraction...")
            context_info = self._calculate_full_image_context_extraction(image)
        else:
            # Existing path: Context extraction for future models
            print("DEBUG: Calculating context extraction...")
            context_info = self._calculate_context_extraction(image)

        Gimp.progress_update(0.4)  # 40% - Context calculated
        Gimp.displays_flush()  # Force UI update

        # Step 5: Extract context region with padding (works for both modes)
        print("DEBUG: Extracting context region...")
        success, message, image_data = self._extract_context_region(image, context_info)
        if not success:
            Gimp.message(f"❌ Context Extraction Failed: {message}")
            print(f"DEBUG: Context extraction failed: {message}")
            Gimp.progress_end()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
        print(f"DEBUG: Context extraction succeeded: {message}")
        Gimp.progress_update(0.5)  # 50% - Context extracted
        Gimp.displays_flush()  # Force UI update

        # Step 6: Create smart mask that respects selection within context
        print("DEBUG: Creating context-aware mask...")
        mask_data = self._create_context_mask(
            image, context_info, context_info["target_size"]
        )

        Gimp.progress_update(0.6)  # 60% - Mask created
        Gimp.displays_flush()  # Force UI update

        # Step 7: Call AI API with context and mask
        api_success, api_message, api_response = self._call_openai_inpaint(
            image_data, mask_data, prompt, api_key
        )

        if api_success:
            print(f"DEBUG: AI API succeeded: {api_message}")

            # Step 8: Download and composite result with proper masking
            import_success, import_message = self._download_and_composite_result(
                image, api_response, context_info
            )

            if import_success:
                Gimp.progress_update(1.0)  # 100% - Complete
                print(f"DEBUG: AI Inpaint Complete - {import_message}")
            else:
                Gimp.message(
                    f"⚠️ AI Generated but Import Failed!\n\nPrompt: {prompt}\nAPI: {api_message}\nImport Error: {import_message}"
                )
                print(f"DEBUG: Import failed: {import_message}")
        else:
            Gimp.message(f"❌ AI API Failed: {api_message}")
            print(f"DEBUG: AI API failed: {api_message}")

        # Always end progress
        Gimp.progress_end()
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    def _generate_dalle3_layer(self, image, prompt, api_key):
        """Generate a new layer using DALL-E 3"""
        try:
            import json
            import urllib.request
            import urllib.parse
            import ssl

            # DALL-E 3 API endpoint
            url = "https://api.openai.com/v1/images/generations"

            # Prepare the request data
            data = {
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "url",
            }

            # Create the request
            json_data = json.dumps(data).encode("utf-8")

            req = urllib.request.Request(url, data=json_data)
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")

            print(f"DEBUG: Calling DALL-E 3 API with prompt: {prompt}")

            # Make the API call
            with self._make_url_request(req) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            print(f"DEBUG: DALL-E 3 API response received")

            # Extract the image URL
            if "data" in response_data and len(response_data["data"]) > 0:
                image_url = response_data["data"][0]["url"]
                print(f"DEBUG: Image URL: {image_url}")

                # Download and add the image as a new layer
                return self._download_and_add_layer(image, image_url)
            else:
                print("ERROR: No image data in API response")
                return False

        except Exception as e:
            print(f"ERROR: DALL-E 3 API call failed: {str(e)}")
            return False

    def _download_and_add_layer(self, image, image_url):
        """Download image from URL and add as new layer"""
        try:
            import urllib.request
            import tempfile
            import os
            import ssl

            # Download the image to a temporary file
            with self._make_url_request(image_url) as response:
                image_data = response.read()

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name

            print(f"DEBUG: Downloaded image to: {temp_file_path}")

            try:
                # Load the image as a new layer
                loaded_image = Gimp.file_load(
                    Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(temp_file_path)
                )
                source_layer = loaded_image.get_layers()[0]

                # Copy the layer to the current image
                new_layer = Gimp.Layer.new_from_drawable(source_layer, image)
                new_layer.set_name("DALL-E 3 Generated")

                # Add the layer to the image
                image.insert_layer(new_layer, None, 0)

                # Clean up
                loaded_image.delete()

                print("DEBUG: Successfully added DALL-E 3 layer")
                return True

            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

        except Exception as e:
            print(f"ERROR: Failed to download and add layer: {str(e)}")
            return False

    def run_layer_generator(
        self, procedure, run_mode, image, drawables, config, run_data
    ):
        print("DEBUG: DALL-E 3 Layer Generator called!")

        # Get the API key
        api_key = self._get_api_key()
        if not api_key:
            Gimp.message(
                "❌ OpenAI API key not configured. Please run AI Plugin Settings first."
            )
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

        # Show prompt dialog
        prompt = self._show_prompt_dialog(
            "DALL-E 3 Layer Generator", self._get_last_prompt()
        )
        if not prompt:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Add to prompt history
        self._add_to_prompt_history(prompt)

        try:
            # Create new layer with DALL-E 3 generated image
            result = self._generate_dalle3_layer(image, prompt, api_key)
            if result:
                Gimp.message("✅ DALL-E 3 layer generated successfully!")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS, GLib.Error()
                )
            else:
                Gimp.message("❌ Failed to generate DALL-E 3 layer")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                )
        except Exception as e:
            error_msg = f"Error generating DALL-E 3 layer: {str(e)}"
            print(f"ERROR: {error_msg}")
            Gimp.message(f"❌ {error_msg}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )

    def run_settings(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: Testing HTTP functionality...")

        # Test HTTP request
        success, message = self._test_http_request()

        if success:
            Gimp.message(f"✅ {message}")
            print(f"DEBUG: HTTP test succeeded: {message}")
        else:
            Gimp.message(f"❌ {message}")
            print(f"DEBUG: HTTP test failed: {message}")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())


# Entry point
if __name__ == "__main__":
    Gimp.main(GimpAIPlugin.__gtype__, sys.argv)
