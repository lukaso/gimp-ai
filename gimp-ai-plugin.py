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
    calculate_mask_coordinates,
    calculate_placement_coordinates,
    validate_context_info,
    get_optimal_openai_shape,
    calculate_padding_for_shape,
    extract_context_with_selection,
    calculate_result_placement,
    calculate_scale_from_shape,
)


class GimpAIPlugin(Gimp.PlugIn):
    """Simplified AI Plugin"""

    def __init__(self):
        super().__init__()
        self.config = self._load_config()
        self._cancel_requested = False

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

    def _get_processing_mode(self, dialog_mode=None):
        """Determine processing mode based on dialog selection or fallback to config"""
        if dialog_mode:
            return dialog_mode

        # Fallback to last used mode from config
        return self.config.get("last_mode", "contextual")

    def _update_progress(self, progress_label, message, gimp_progress=None):
        """Update progress message in dialog with proper emoji encoding, optionally update GIMP progress bar"""
        if progress_label:
            try:
                # Ensure the message is properly encoded for GTK
                # GTK should handle UTF-8 properly, but let's be explicit
                if isinstance(message, str):
                    encoded_message = message.encode("utf-8").decode("utf-8")
                else:
                    encoded_message = str(message)

                # Use GLib.idle_add to ensure the update happens on the main thread
                def update_ui():
                    try:
                        print(
                            f"DEBUG: Actually updating progress label to: {encoded_message}"
                        )
                        progress_label.set_text(encoded_message)
                        progress_label.set_use_markup(
                            False
                        )  # Use plain text, not markup
                        print(
                            f"DEBUG: Progress label text is now: {progress_label.get_text()}"
                        )
                        return False  # Remove from idle queue after running once
                    except Exception as e:
                        print(f"DEBUG: UI update failed: {e}")
                        return False

                # Queue the update on the main thread
                GLib.idle_add(update_ui)

            except Exception as e:
                print(f"DEBUG: Progress update failed: {e}")
                # Fallback without emojis if there's encoding issue
                fallback = (
                    message.encode("ascii", "ignore").decode("ascii")
                    if message
                    else "Processing..."
                )
                try:
                    progress_label.set_text(fallback)
                except:
                    pass

        # Update GIMP progress bar if fraction provided
        if gimp_progress is not None:
            try:
                Gimp.progress_set_text(message)
                Gimp.progress_update(gimp_progress)
                Gimp.displays_flush()
            except:
                pass  # Ignore if not in right context

        return False  # Return False for GLib.idle_add compatibility

    def _create_progress_callback(self, progress_label):
        """Create a reusable progress callback for threading"""

        def progress_callback(message):
            def update_ui():
                self._update_progress(progress_label, message)
                return False

            GLib.idle_add(update_ui)

        return progress_callback

    def _create_progress_widget(self):
        """Create progress label widget for dialogs"""
        progress_label = Gtk.Label()
        progress_label.set_text("Ready to start...")
        return progress_label, progress_label

    def _init_gimp_ui(self):
        """Initialize GIMP UI system if not already done"""
        if not hasattr(self, "_ui_initialized"):
            GimpUi.init("gimp-ai-plugin")
            self._ui_initialized = True

    def _create_dialog_base(self, title="Dialog", size=(500, 400)):
        """Create a standard GIMP dialog with consistent styling"""
        self._init_gimp_ui()

        # Create dialog with header bar detection
        use_header_bar = Gtk.Settings.get_default().get_property(
            "gtk-dialogs-use-header"
        )
        dialog = GimpUi.Dialog(use_header_bar=use_header_bar, title=title)

        # Set up dialog properties
        dialog.set_default_size(size[0], size[1])
        dialog.set_resizable(True)

        return dialog

    def _setup_dialog_content_area(self, dialog, spacing=15, margin=20):
        """Set up dialog content area with consistent styling"""
        content_area = dialog.get_content_area()
        content_area.set_spacing(spacing)
        content_area.set_margin_start(margin)
        content_area.set_margin_end(margin)
        content_area.set_margin_top(margin)
        content_area.set_margin_bottom(margin)
        return content_area

    def _add_api_warning_bar(self, content_area, dialog):
        """Add API key warning info bar if needed, returns (warning_bar, ok_button_needs_config)"""
        api_key = self._get_api_key()
        if api_key:
            return None, False

        # Create warning info bar
        api_warning_bar = Gtk.InfoBar()
        api_warning_bar.set_message_type(Gtk.MessageType.WARNING)
        api_warning_bar.set_show_close_button(False)

        # Warning message
        warning_label = Gtk.Label()
        warning_label.set_markup("⚠️ OpenAI API key not configured")
        warning_label.set_halign(Gtk.Align.START)

        # Configure button - connect to main dialog response
        configure_button = api_warning_bar.add_button(
            "Configure Now", Gtk.ResponseType.APPLY
        )

        # Connect the InfoBar response to the main dialog
        def on_configure_clicked(infobar, response_id):
            if response_id == Gtk.ResponseType.APPLY:
                dialog.response(Gtk.ResponseType.APPLY)

        api_warning_bar.connect("response", on_configure_clicked)

        # Add label to info bar content area
        info_content = api_warning_bar.get_content_area()
        info_content.pack_start(warning_label, False, False, 0)

        content_area.pack_start(api_warning_bar, False, False, 5)

        return api_warning_bar, True

    def _is_debug_mode(self):
        """Check if debug mode is enabled (saves temp files to /tmp)"""
        # Check config first
        debug = self.config.get("debug_mode", False)
        # Allow environment variable override
        if os.environ.get("GIMP_AI_DEBUG") == "1":
            debug = True
        return debug

    def _check_cancel_and_process_events(self):
        """Check if cancel was requested and process minimal UI events"""
        # Process GTK events more aggressively for better UI responsiveness
        try:
            # Process multiple pending events to improve responsiveness
            if hasattr(Gtk, "events_pending"):
                event_count = 0
                while (
                    Gtk.events_pending() and event_count < 5
                ):  # Process up to 5 events
                    Gtk.main_iteration_do(False)  # Non-blocking iteration
                    event_count += 1
        except Exception as e:
            print(f"DEBUG: GTK event processing warning (non-fatal): {e}")

        return self._cancel_requested

    def _show_prompt_dialog(
        self, title="AI Prompt", default_text="", show_mode_selection=True, image=None
    ):
        """Show a GIMP UI dialog to get user input for AI prompt"""
        # Use last prompt as default if available, otherwise use provided default
        if not default_text:
            default_text = self._get_last_prompt()
        if not default_text:
            if title == "AI Inpaint":
                default_text = "Describe the area to inpaint (e.g. 'remove object', 'fix background')"
            else:
                default_text = "Describe what you want to generate..."
        try:
            # Create dialog using helper methods
            dialog = self._create_dialog_base(title, (600, 300))

            # Add buttons using GIMP's standard approach
            dialog.add_button(
                "Settings", Gtk.ResponseType.HELP
            )  # Use HELP for Settings
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("OK", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Set up content area using helper
            content_area = self._setup_dialog_content_area(dialog, spacing=10)

            # Label - will automatically use theme colors
            label = Gtk.Label(label="Enter your AI prompt:")
            label.set_halign(Gtk.Align.START)
            content_area.pack_start(label, False, False, 0)

            # Add API warning bar using helper
            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog
            )
            if needs_config:
                # Disable OK button when no API key
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

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

            # Add mode selection (only for inpainting)
            focused_radio = None
            full_radio = None
            if show_mode_selection:
                mode_frame = Gtk.Frame(label="Processing Mode:")
                mode_frame.set_margin_top(10)
                content_area.pack_start(mode_frame, False, False, 0)

                mode_box = Gtk.VBox()
                mode_box.set_margin_start(10)
                mode_box.set_margin_end(10)
                mode_box.set_margin_top(5)
                mode_box.set_margin_bottom(10)
                mode_frame.add(mode_box)

                # Get last used mode from config
                config = self._load_config()
                last_mode = config.get("last_mode", "contextual")

                # Radio buttons for mode selection
                focused_radio = Gtk.RadioButton.new_with_label(
                    None,
                    "Focused (High Detail) - Best for small edits, maximum resolution",
                )
                focused_radio.set_name("contextual")
                mode_box.pack_start(focused_radio, False, False, 2)

                full_radio = Gtk.RadioButton.new_with_label_from_widget(
                    focused_radio,
                    "Full Image (Consistent) - Best for large changes, visual consistency",
                )
                full_radio.set_name("full_image")
                mode_box.pack_start(full_radio, False, False, 2)

                # Set active radio based on last used mode
                if last_mode == "full_image":
                    full_radio.set_active(True)
                else:
                    focused_radio.set_active(True)

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

            # Add progress widget
            progress_frame, progress_label = self._create_progress_widget()
            content_area.pack_start(progress_frame, False, False, 0)

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
                    # First check if API key is configured (for "Configure & Continue" button)
                    current_api_key = self._get_api_key()
                    if not current_api_key:
                        print("DEBUG: OK clicked but no API key, opening settings")
                        self._show_settings_dialog(dialog)

                        # Re-check API key after settings dialog
                        current_api_key = self._get_api_key()
                        if current_api_key:
                            # API key now configured - update UI
                            if api_warning_bar:
                                api_warning_bar.hide()
                            ok_button.set_sensitive(True)
                            ok_button.set_label("OK")
                            print("DEBUG: API key configured, enabled OK button")
                        else:
                            print("DEBUG: API key still not configured")
                            continue  # Keep dialog open

                    # Now validate the prompt
                    start_iter = text_buffer.get_start_iter()
                    end_iter = text_buffer.get_end_iter()
                    prompt = text_buffer.get_text(start_iter, end_iter, False).strip()

                    # Check if user entered actual content (not just placeholder)
                    placeholder_texts = [
                        "Describe what you want to generate...",
                        "Describe the area to inpaint (e.g. 'remove object', 'fix background')",
                    ]

                    is_placeholder = prompt in placeholder_texts or not prompt.strip()

                    if is_placeholder:
                        # Show error message and keep dialog open
                        error_dialog = Gtk.MessageDialog(
                            parent=dialog,
                            flags=Gtk.DialogFlags.MODAL,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK,
                            text="Please enter a prompt description",
                        )
                        error_dialog.format_secondary_text(
                            "You need to describe what you want to generate or change before proceeding."
                        )
                        error_dialog.run()
                        error_dialog.destroy()
                        continue  # Keep the main dialog open

                    # Get selected mode
                    selected_mode = "contextual"  # default
                    if show_mode_selection and full_radio and full_radio.get_active():
                        selected_mode = "full_image"
                    elif (
                        show_mode_selection
                        and focused_radio
                        and focused_radio.get_active()
                    ):
                        selected_mode = "contextual"
                    # If no mode selection UI, use default "contextual" (for image generator)

                    print(
                        f"DEBUG: Got prompt text: '{prompt}', mode: '{selected_mode}', disabling OK button..."
                    )
                    # Disable OK button to prevent multiple clicks
                    ok_button.set_sensitive(False)
                    ok_button.set_label("Processing...")

                    # Update progress
                    self._update_progress(progress_label, "Validating API key...")

                    if prompt:
                        self._add_to_prompt_history(prompt)
                        # Save the selected mode to config
                        self.config["last_mode"] = selected_mode
                        self._save_config()

                    # Reset cancel flag for new operation
                    self._cancel_requested = False

                    # Add cancel handler to keep dialog responsive during processing
                    def on_dialog_response(dialog, response_id):
                        if response_id == Gtk.ResponseType.CANCEL:
                            print("DEBUG: Cancel button clicked during processing")
                            self._cancel_requested = True
                            return True  # Keep dialog open
                        return False

                    dialog.connect("response", on_dialog_response)

                    # Return dialog, progress_label, and prompt data for processing
                    return (
                        (dialog, progress_label, prompt, selected_mode)
                        if prompt
                        else None
                    )
                elif response == Gtk.ResponseType.APPLY:  # Configure Now button
                    print("DEBUG: Configure Now button clicked")
                    self._show_settings_dialog(dialog)

                    # Re-check API key after settings dialog
                    api_key = self._get_api_key()
                    if api_key:
                        # API key now configured - update UI
                        if api_warning_bar:
                            api_warning_bar.hide()
                        ok_button.set_sensitive(True)
                        ok_button.set_label("OK")
                        print("DEBUG: API key configured, enabled OK button")
                    else:
                        print("DEBUG: API key still not configured")
                    # Continue loop to keep main dialog open
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

    def _show_composite_dialog(self, image):
        """Show dedicated dialog for Layer Composite with visible layers info"""
        try:
            print("DEBUG: Creating Layer Composite dialog")

            # Get visible layers (image.get_layers() returns top-to-bottom order)
            all_layers = image.get_layers()
            visible_layers = [layer for layer in all_layers if layer.get_visible()]

            print(
                f"DEBUG: Found {len(all_layers)} total layers, {len(visible_layers)} visible"
            )
            print(
                f"DEBUG: Layer order (top-to-bottom): {[layer.get_name() for layer in visible_layers]}"
            )

            if len(visible_layers) < 2:
                print("DEBUG: Insufficient visible layers for composite")
                Gimp.message(
                    "❌ Layer Composite requires at least 2 visible layers.\n\nPlease make sure at least 2 layers are visible (eye icon shown) and try again."
                )
                return None

            if len(visible_layers) > 16:
                print(
                    f"DEBUG: Too many visible layers ({len(visible_layers)}), will use first 16"
                )
                visible_layers = visible_layers[:16]

            # Create dialog using helper methods
            dialog = self._create_dialog_base("Layer Composite")

            # Add buttons using GIMP's standard approach
            dialog.add_button(
                "Settings", Gtk.ResponseType.HELP
            )  # Use HELP for Settings
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok_button = dialog.add_button("Composite Layers", Gtk.ResponseType.OK)
            ok_button.set_can_default(True)
            ok_button.grab_default()

            # Set up content area using helper
            content_area = self._setup_dialog_content_area(dialog)

            # Title and info
            title_label = Gtk.Label()
            title_label.set_markup("<b>Layer Composite</b>")
            title_label.set_halign(Gtk.Align.START)
            content_area.pack_start(title_label, False, False, 0)

            info_label = Gtk.Label()
            info_label.set_text(
                f"Will composite {len(visible_layers)} visible layers using AI:"
            )
            info_label.set_halign(Gtk.Align.START)
            content_area.pack_start(info_label, False, False, 0)

            # Add API warning bar using helper
            api_warning_bar, needs_config = self._add_api_warning_bar(
                content_area, dialog
            )
            if needs_config:
                # Disable OK button when no API key
                ok_button.set_sensitive(False)
                ok_button.set_label("Configure & Continue")

            # Layer list (read-only, just for user info)
            layer_frame = Gtk.Frame(label="Layers to composite:")
            content_area.pack_start(layer_frame, False, False, 5)

            layer_box = Gtk.VBox()
            layer_box.set_margin_start(10)
            layer_box.set_margin_end(10)
            layer_box.set_margin_top(5)
            layer_box.set_margin_bottom(10)
            layer_frame.add(layer_box)

            for i, layer in enumerate(visible_layers):
                layer_label = Gtk.Label()
                if (
                    i == len(visible_layers) - 1
                ):  # Last layer is the base (bottom) layer
                    layer_label.set_text(f"Base: {layer.get_name()} (primary layer)")
                else:
                    layer_label.set_text(
                        f"Layer {len(visible_layers) - 1 - i}: {layer.get_name()}"
                    )
                layer_label.set_halign(Gtk.Align.START)
                layer_box.pack_start(layer_label, False, False, 2)

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

            # Prompt text area
            prompt_label = Gtk.Label(label="Describe how to combine these layers:")
            prompt_label.set_halign(Gtk.Align.START)
            content_area.pack_start(prompt_label, False, False, 0)

            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
            )
            scrolled_window.set_min_content_height(100)

            text_view = Gtk.TextView()
            text_view.set_wrap_mode(Gtk.WrapMode.WORD)
            text_view.set_border_width(8)

            # Set default prompt - use last prompt if available
            default_prompt = self._get_last_prompt()
            if not default_prompt:
                default_prompt = "Combine these layers naturally into a cohesive image"
            text_buffer = text_view.get_buffer()
            text_buffer.set_text(default_prompt)

            scrolled_window.add(text_view)
            content_area.pack_start(scrolled_window, True, True, 0)

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

            # Mask option - restore from config
            mask_checkbox = Gtk.CheckButton()
            mask_checkbox.set_label("Include selection mask (applies to base layer)")
            last_use_mask = self.config.get("last_use_mask", False)
            mask_checkbox.set_active(last_use_mask)
            content_area.pack_start(mask_checkbox, False, False, 5)

            # Add progress widget
            progress_frame, progress_label = self._create_progress_widget()
            content_area.pack_start(progress_frame, False, False, 0)

            # Show dialog
            content_area.show_all()
            text_view.grab_focus()

            # Run dialog loop
            while True:
                response = dialog.run()

                if response == Gtk.ResponseType.OK:
                    # Get prompt text
                    start_iter = text_buffer.get_start_iter()
                    end_iter = text_buffer.get_end_iter()
                    prompt = text_buffer.get_text(start_iter, end_iter, False)

                    # Check if user entered actual content (not just placeholder)
                    placeholder_texts = [
                        "Combine these layers naturally into a cohesive image",
                        "Describe what you want to generate...",
                    ]

                    is_placeholder = prompt in placeholder_texts or not prompt.strip()

                    if is_placeholder:
                        # Show error
                        error_dialog = Gtk.MessageDialog(
                            parent=dialog,
                            flags=Gtk.DialogFlags.MODAL,
                            message_type=Gtk.MessageType.WARNING,
                            buttons=Gtk.ButtonsType.OK,
                            text="Please enter a prompt description",
                        )
                        error_dialog.run()
                        error_dialog.destroy()
                        continue

                    use_mask = mask_checkbox.get_active()
                    print(
                        f"DEBUG: Composite dialog OK - {len(visible_layers)} layers, mask: {use_mask}"
                    )

                    # Save mask checkbox state to config
                    self.config["last_use_mask"] = use_mask
                    self._save_config()

                    # Disable OK button to prevent multiple clicks
                    ok_button.set_sensitive(False)
                    ok_button.set_label("Processing...")

                    # Update progress
                    self._update_progress(progress_label, "Validating API key...")

                    # Save prompt to history
                    self._add_to_prompt_history(prompt.strip())

                    # Reset cancel flag for new operation
                    self._cancel_requested = False

                    # Add cancel handler to keep dialog responsive during processing
                    def on_dialog_response(dialog, response_id):
                        if response_id == Gtk.ResponseType.CANCEL:
                            print("DEBUG: Cancel button clicked during processing")
                            self._cancel_requested = True
                            return True  # Keep dialog open
                        return False

                    dialog.connect("response", on_dialog_response)

                    # Return dialog, progress_label, and data for processing
                    return (
                        dialog,
                        progress_label,
                        prompt.strip(),
                        visible_layers,
                        use_mask,
                    )

                elif response == Gtk.ResponseType.HELP:
                    print("DEBUG: Settings button clicked")
                    # Show settings dialog
                    self._show_settings_dialog(dialog)
                    # Check if API key was configured
                    api_key = self._get_api_key()
                    if api_key:
                        print("DEBUG: API key configured, enabled OK button")
                        ok_button.set_sensitive(True)
                        ok_button.set_label("Composite Layers")
                        if api_warning_bar:
                            api_warning_bar.hide()
                    else:
                        print("DEBUG: API key still not configured")

                elif response == Gtk.ResponseType.APPLY:
                    print("DEBUG: Configure Now button clicked")
                    # Show settings dialog when "Configure Now" is clicked
                    self._show_settings_dialog(dialog)
                    # Check if API key was configured
                    api_key = self._get_api_key()
                    if api_key:
                        print("DEBUG: API key configured, enabled OK button")
                        ok_button.set_sensitive(True)
                        ok_button.set_label("Composite Layers")
                        if api_warning_bar:
                            api_warning_bar.hide()
                    else:
                        print("DEBUG: API key still not configured")

                else:
                    dialog.destroy()
                    return None

        except Exception as e:
            print(f"DEBUG: Composite dialog error: {e}")
            return None

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
            content_area.set_margin_start(20)
            content_area.set_margin_end(20)
            content_area.set_margin_top(20)
            content_area.set_margin_bottom(20)

            # API Key section
            api_frame = Gtk.Frame(label="OpenAI API Configuration")
            api_box = Gtk.VBox(spacing=10)
            api_box.set_margin_start(10)
            api_box.set_margin_end(10)
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
            history_box.set_margin_start(10)
            history_box.set_margin_end(10)
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

            # Debug Settings section
            debug_frame = Gtk.Frame(label="Debug Settings")
            debug_box = Gtk.VBox(spacing=10)
            debug_box.set_margin_start(10)
            debug_box.set_margin_end(10)
            debug_box.set_margin_top(10)
            debug_box.set_margin_bottom(10)

            # Debug mode checkbox
            debug_checkbox = Gtk.CheckButton()
            debug_checkbox.set_label("Save debug images to /tmp")
            debug_checkbox.set_active(self.config.get("debug_mode", False))
            debug_box.pack_start(debug_checkbox, False, False, 0)

            # Debug explanation
            debug_info = Gtk.Label()
            debug_info.set_text(
                "Saves intermediate AI processing images for troubleshooting"
            )
            debug_info.set_halign(Gtk.Align.START)
            debug_info.get_style_context().add_class("dim-label")
            debug_box.pack_start(debug_info, False, False, 0)

            debug_frame.add(debug_box)
            content_area.pack_start(debug_frame, False, False, 0)

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
                    print("DEBUG: API key updated")

                # Save debug mode setting
                debug_mode = debug_checkbox.get_active()
                self.config["debug_mode"] = debug_mode
                self._save_config()
                print(f"DEBUG: Debug mode set to {debug_mode}")

            dialog.destroy()

        except Exception as e:
            print(f"DEBUG: Settings dialog error: {e}")

    def _on_clear_history_clicked(self, button):
        """Handle clear history button click"""
        self.config["prompt_history"] = []
        self._save_config()
        print("DEBUG: Prompt history cleared")

    def _extract_context_region(self, image, context_info):
        """Extract context region and scale to optimal OpenAI shape"""
        try:
            print("DEBUG: Extracting context region for AI with optimal shape")

            # Get parameters for the extract region
            ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
            target_shape = context_info["target_shape"]
            target_width, target_height = target_shape
            orig_width = image.get_width()
            orig_height = image.get_height()

            print(
                f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}) to ({ctx_x1+ctx_width},{ctx_y1+ctx_height}) size={ctx_width}x{ctx_height}"
            )
            print(f"DEBUG: Original image: {orig_width}x{orig_height}")
            print(f"DEBUG: Target shape: {target_width}x{target_height}")

            # Create a new canvas with the extract region size
            extract_image = Gimp.Image.new(ctx_width, ctx_height, image.get_base_type())
            if not extract_image:
                return False, "Failed to create extract canvas", None

            # Calculate what part of the original image intersects with our extract region
            intersect_x1 = max(0, ctx_x1)
            intersect_y1 = max(0, ctx_y1)
            intersect_x2 = min(orig_width, ctx_x1 + ctx_width)
            intersect_y2 = min(orig_height, ctx_y1 + ctx_height)

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
                    extract_image.delete()
                    return False, "Failed to merge layers", None

                # Copy this layer to our extract canvas at the correct position
                layer_copy = Gimp.Layer.new_from_drawable(merged_layer, extract_image)
                extract_image.insert_layer(layer_copy, None, 0)

                # Position the layer correctly within the extract region
                # The layer should be at the same relative position as in the extract region
                paste_x = intersect_x1 - ctx_x1  # Offset within the extract region
                paste_y = intersect_y1 - ctx_y1  # Offset within the extract region
                layer_copy.set_offsets(paste_x, paste_y)

                print(
                    f"DEBUG: Placed image content at offset ({paste_x},{paste_y}) within extract region"
                )

                # Clean up temp image
                temp_image.delete()
            else:
                print(
                    "DEBUG: No intersection with original image - creating empty extract region"
                )

            # Scale and pad to target shape for OpenAI (preserve aspect ratio)
            if ctx_width != target_width or ctx_height != target_height:
                # Get padding info to preserve aspect ratio
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    scale_factor = padding_info["scale_factor"]
                    scaled_w, scaled_h = padding_info["scaled_size"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    print(f"DEBUG: Using aspect-ratio preserving scaling:")
                    print(f"  Scale factor: {scale_factor}")
                    print(f"  Scaled size: {scaled_w}x{scaled_h}")
                    print(
                        f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                    )

                    # First scale preserving aspect ratio
                    if scale_factor != 1.0:
                        extract_image.scale(scaled_w, scaled_h)
                        print(
                            f"DEBUG: Scaled to {scaled_w}x{scaled_h} preserving aspect ratio"
                        )

                    # Then add padding to reach target dimensions
                    if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                        # Resize canvas to add padding
                        extract_image.resize(
                            target_width, target_height, pad_left, pad_top
                        )
                        print(
                            f"DEBUG: Added padding to reach {target_width}x{target_height}"
                        )
                else:
                    # Fallback: calculate padding on the fly
                    padding_info = calculate_padding_for_shape(
                        ctx_width, ctx_height, target_width, target_height
                    )
                    scale_factor = padding_info["scale_factor"]
                    scaled_w, scaled_h = padding_info["scaled_size"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    print(f"DEBUG: Calculating padding on the fly:")
                    print(f"  Scale factor: {scale_factor}")
                    print(
                        f"  Padding: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                    )

                    # First scale preserving aspect ratio
                    extract_image.scale(scaled_w, scaled_h)

                    # Then add padding
                    extract_image.resize(target_width, target_height, pad_left, pad_top)

                print(
                    f"DEBUG: Final extract image size: {target_width}x{target_height} (aspect ratio preserved)"
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
                pdb_config.set_property("image", extract_image)
                pdb_config.set_property("file", file)
                pdb_config.set_property("options", None)

                result = pdb_proc.run(pdb_config)
                if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                    print(f"DEBUG: PNG export failed: {result.index(0)}")
                    extract_image.delete()
                    return False, "PNG export failed", None

                # Read the exported file and encode to base64
                with open(temp_filename, "rb") as f:
                    png_data = f.read()

                base64_data = base64.b64encode(png_data).decode("utf-8")

                # Clean up
                os.unlink(temp_filename)
                extract_image.delete()

                info = f"Extracted context region: {len(png_data)} bytes as PNG, base64 length: {len(base64_data)}"
                print(f"DEBUG: {info}")
                return True, info, base64_data

            except Exception as e:
                print(f"DEBUG: Context extraction export failed: {e}")
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                extract_image.delete()
                return False, f"Export failed: {str(e)}", None

        except Exception as e:
            print(f"DEBUG: Context extraction failed: {e}")
            return False, f"Context extraction error: {str(e)}", None


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

            # For full image mode, select optimal OpenAI shape
            target_shape = get_optimal_openai_shape(orig_width, orig_height)
            target_width, target_height = target_shape
            target_size = max(target_width, target_height)  # For backward compatibility

            print(f"DEBUG: Target OpenAI shape: {target_width}x{target_height}")

            # For full image, the context covers the entire original image
            ctx_x1 = 0
            ctx_y1 = 0

            print(
                f"DEBUG: Context region covers entire image: {orig_width}x{orig_height}"
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
                "mode": "full",
                "selection_bounds": sel_bounds,
                "extract_region": (
                    0,
                    0,
                    orig_width,
                    orig_height,
                ),  # Extract entire image
                "target_shape": target_shape,
                "target_size": max(target_shape),  # For backward compatibility
                "needs_padding": True,
                "padding_info": calculate_padding_for_shape(
                    orig_width, orig_height, target_shape[0], target_shape[1]
                ),
                "has_selection": has_real_selection,
                "original_bounds": (full_x1, full_y1, full_x2, full_y2),
            }

        except Exception as e:
            print(f"DEBUG: Failed to calculate full image context extraction: {e}")
            return None

    def _calculate_context_extraction(self, image):
        """Calculate smart context extraction area around selection using optimal shapes"""
        try:
            print("DEBUG: Calculating smart context extraction with optimal shapes")

            # Get image dimensions
            img_width = image.get_width()
            img_height = image.get_height()
            print(f"DEBUG: Original image size: {img_width}x{img_height}")

            # Check for selection
            selection_bounds = Gimp.Selection.bounds(image)
            print(f"DEBUG: Selection bounds raw: {selection_bounds}")

            if len(selection_bounds) < 5 or not selection_bounds[0]:
                print("DEBUG: No selection found, using center area")
                # Use new shape-aware function with no selection
                return extract_context_with_selection(
                    img_width,
                    img_height,
                    0,
                    0,
                    0,
                    0,
                    mode="focused",
                    has_selection=False,
                )

            # Extract selection bounds
            sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
            sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
            sel_x2 = selection_bounds[4] if len(selection_bounds) > 4 else 0
            sel_y2 = selection_bounds[5] if len(selection_bounds) > 5 else 0

            sel_width = sel_x2 - sel_x1
            sel_height = sel_y2 - sel_y1
            print(
                f"DEBUG: Selection: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2}), size: {sel_width}x{sel_height}"
            )

            # Use new shape-aware function for calculation
            context_info = extract_context_with_selection(
                img_width,
                img_height,
                sel_x1,
                sel_y1,
                sel_x2,
                sel_y2,
                mode="focused",
                has_selection=True,
            )

            # Log the optimal shape selected
            print(f"DEBUG: Optimal shape selected: {context_info['target_shape']}")

            # Extract dimensions for any code that still expects target_size
            target_w, target_h = context_info["target_shape"]
            context_info["target_size"] = max(target_w, target_h)

            # Validate still works but now with shape support
            is_valid, error_msg = validate_context_info(context_info)
            if not is_valid:
                print(f"DEBUG: Context validation failed: {error_msg}")
                # Fallback to center extraction
                return extract_context_with_selection(
                    img_width,
                    img_height,
                    0,
                    0,
                    0,
                    0,
                    mode="focused",
                    has_selection=False,
                )

            # Add debug output for the calculated values
            extract_x1, extract_y1, extract_width, extract_height = context_info[
                "extract_region"
            ]
            target_w, target_h = context_info["target_shape"]

            print(
                f"DEBUG: Extract region: ({extract_x1},{extract_y1}) to ({extract_x1+extract_width},{extract_y1+extract_height}), size: {extract_width}x{extract_height}"
            )
            print(f"DEBUG: Target shape for OpenAI: {target_w}x{target_h}")

            if "padding_info" in context_info:
                padding_info = context_info["padding_info"]
                print(f"DEBUG: Scale factor: {padding_info['scale_factor']}")
                print(f"DEBUG: Padding: {padding_info['padding']}")

            return context_info

        except Exception as e:
            print(f"DEBUG: Context calculation failed: {e}")
            # Fallback to simple center extraction
            return extract_context_with_selection(
                img_width, img_height, 0, 0, 0, 0, mode="focused", has_selection=False
            )

    def _prepare_full_image(self, image):
        """Prepare full image for GPT-Image-1 processing with optimal shape"""
        try:
            print("DEBUG: Preparing full image for transformation with optimal shape")

            width = image.get_width()
            height = image.get_height()

            print(f"DEBUG: Original image size: {width}x{height}")

            # Get optimal OpenAI shape for this image
            target_shape = get_optimal_openai_shape(width, height)
            target_width, target_height = target_shape

            print(
                f"DEBUG: Optimal OpenAI shape selected: {target_width}x{target_height}"
            )

            # Calculate padding info for this shape
            padding_info = calculate_padding_for_shape(
                width, height, target_width, target_height
            )
            scale = padding_info["scale_factor"]
            scaled_width, scaled_height = padding_info["scaled_size"]

            print(f"DEBUG: Scale factor: {scale:.3f}")
            print(f"DEBUG: Scaled size: {scaled_width}x{scaled_height}")

            # Create context_info with both old and new format for compatibility
            context_info = {
                "mode": "full_image",
                "original_size": (width, height),
                "scaled_size": (scaled_width, scaled_height),
                "scale_factor": scale,
                "target_shape": target_shape,  # New: optimal shape tuple
                "target_size": (
                    target_width
                    if target_width == target_height
                    else max(target_width, target_height)
                ),  # Old format fallback
                "padding_info": padding_info,
                "has_selection": True,  # Always true for this mode
            }

            return context_info

        except Exception as e:
            print(f"DEBUG: Full image preparation failed: {e}")
            # Fallback to square
            return {
                "mode": "full_image",
                "original_size": (1024, 1024),
                "scaled_size": (1024, 1024),
                "scale_factor": 1.0,
                "target_shape": (1024, 1024),
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

    def _run_threaded_operation(self, operation_func, operation_name, progress_label=None, max_wait_time=300):
        """Generic threaded wrapper for any operation to keep UI responsive"""
        import threading
        import time

        print(f"DEBUG: Starting threaded {operation_name}...")

        # Shared storage for results
        result = {
            "success": False,
            "message": "",
            "data": None,  # Generic data field
            "completed": False,
        }

        def operation_thread():
            try:
                result.update(operation_func())
            except Exception as e:
                print(f"DEBUG: [THREAD] {operation_name} exception: {e}")
                result["success"] = False
                result["message"] = str(e)
                result["data"] = None
            finally:
                result["completed"] = True

        # Start thread
        thread = threading.Thread(target=operation_thread)
        thread.daemon = True
        thread.start()

        # Keep UI responsive while waiting
        start_time = time.time()
        last_update_time = start_time

        print(f"DEBUG: Starting wait loop for {operation_name}, progress_label={progress_label is not None}")
        while not result["completed"]:
            current_time = time.time()
            elapsed = current_time - start_time

            # Update progress every 5 seconds
            if progress_label and current_time - last_update_time > 5:
                print(f"DEBUG: About to call _update_progress at {elapsed:.1f}s")
                minutes = int(elapsed // 60)
                if minutes > 0:
                    self._update_progress(
                        progress_label, f"Still processing... ({minutes}m elapsed)"
                    )
                else:
                    self._update_progress(
                        progress_label, f"Processing... ({int(elapsed)}s elapsed)"
                    )
                last_update_time = current_time
                print(f"DEBUG: _update_progress call completed")

            # Check for cancellation
            if self._check_cancel_and_process_events():
                print(f"DEBUG: {operation_name} cancelled by user")
                if progress_label:
                    self._update_progress(progress_label, "❌ Operation cancelled")
                result["success"] = False
                result["message"] = "Operation cancelled by user"
                break

            # Check for timeout
            if elapsed > max_wait_time:
                print(f"DEBUG: {operation_name} timeout after {max_wait_time} seconds")
                if progress_label:
                    self._update_progress(progress_label, "❌ Request timed out")
                result["success"] = False
                result["message"] = "Request timed out - check internet connection"
                break

            time.sleep(0.1)  # Small sleep to prevent busy waiting

        return result["success"], result["message"], result["data"]

    def _call_openai_generation(
        self, prompt, api_key, size="auto", progress_label=None
    ):
        """Call OpenAI GPT-Image-1 API for image generation with progress updates"""
        try:
            import json
            import urllib.request

            print(f"DEBUG: Calling GPT-Image-1 generation API with prompt: {prompt}")

            # Determine optimal size
            if size == "auto":
                optimal_size = "1536x1024"  # Default landscape
            else:
                optimal_size = size

            print(f"DEBUG: Using size {optimal_size} for generation")

            # Prepare the request data
            data = {
                "model": "gpt-image-1",
                "prompt": prompt,
                "n": 1,
                "size": optimal_size,
                "quality": "high",
            }

            # Create the request
            json_data = json.dumps(data).encode("utf-8")
            url = "https://api.openai.com/v1/images/generations"
            req = urllib.request.Request(url, data=json_data)
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")

            print("DEBUG: Sending real GPT-Image-1 generation request...")

            # Progress during network operation (same pattern as _call_openai_edit)
            if progress_label:
                self._update_progress(
                    progress_label, "🚀 Sending request to GPT-Image-1..."
                )

            # Make the API call with progress updates during the call
            with self._make_url_request(req, timeout=180) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            print("DEBUG: GPT-Image-1 generation response received")

            if progress_label:
                self._update_progress(progress_label, "✅ Processing AI response...")

            # Process the response
            if "data" in response_data and len(response_data["data"]) > 0:
                result_data = response_data["data"][0]

                if "b64_json" in result_data:
                    print("DEBUG: Processing base64 image data from GPT-Image-1")
                    import base64

                    image_data = base64.b64decode(result_data["b64_json"])
                    print(f"DEBUG: Decoded {len(image_data)} bytes of image data")

                    return True, "Image generation successful", image_data
                else:
                    print("ERROR: No b64_json in GPT-Image-1 response")
                    return False, "No image data in response", None
            else:
                print("ERROR: No data in GPT-Image-1 response")
                return False, "No data in API response", None

        except Exception as e:
            print(f"ERROR: GPT-Image-1 generation API call failed: {str(e)}")
            return False, str(e), None

    def _call_openai_generation_threaded(
        self, prompt, api_key, size="auto", progress_label=None
    ):
        """Threaded wrapper for OpenAI image generation API call to keep UI responsive"""
        def operation():
            success, message, image_data = self._call_openai_generation(
                prompt, api_key, size, progress_label
            )
            return {"success": success, "message": message, "data": image_data}

        return self._run_threaded_operation(
            operation, "OpenAI generation API call", progress_label
        )

    def _prepare_layers_for_composite(self, selected_layers):
        """Prepare multiple layers for OpenAI composite API - each layer as separate PNG"""
        try:
            print(f"DEBUG: Preparing {len(selected_layers)} layers for composite API")

            layer_data_list = []

            # Import coordinate utilities for optimal sizing
            from coordinate_utils import get_optimal_openai_shape

            # Process primary layer (bottom/first) with full optimization
            primary_layer = selected_layers[0]
            print(f"DEBUG: Processing primary layer: {primary_layer.get_name()}")

            # Create temporary image with just the primary layer
            primary_temp_image = Gimp.Image.new(
                primary_layer.get_width(),
                primary_layer.get_height(),
                Gimp.ImageBaseType.RGB,
            )

            # Use GIMP's built-in layer copying - much more reliable than manual buffer operations
            print(f"DEBUG: Copying primary layer using new_from_drawable method")
            primary_layer_copy = Gimp.Layer.new_from_drawable(
                primary_layer, primary_temp_image
            )
            primary_layer_copy.set_name("primary_copy")
            primary_temp_image.insert_layer(primary_layer_copy, None, 0)
            print("DEBUG: Primary layer copy completed via new_from_drawable")

            # Get optimal shape for primary image (using existing logic)
            primary_width = primary_temp_image.get_width()
            primary_height = primary_temp_image.get_height()
            optimal_shape = get_optimal_openai_shape(primary_width, primary_height)
            target_width, target_height = optimal_shape

            print(
                f"DEBUG: Primary layer optimal shape: {primary_width}x{primary_height} -> {target_width}x{target_height}"
            )

            # Scale primary image to optimal shape
            primary_temp_image.scale(target_width, target_height)
            primary_layer_copy.scale(target_width, target_height, False)

            # Export primary layer to PNG
            primary_png_data = self._export_layer_to_png(primary_temp_image)
            if primary_png_data:
                layer_data_list.append(primary_png_data)
                print(f"DEBUG: Primary layer exported: {len(primary_png_data)} bytes")

            primary_temp_image.delete()

            # Process additional layers - scale proportionally to match primary
            for i, layer in enumerate(selected_layers[1:], 1):
                print(f"DEBUG: Processing additional layer {i}: {layer.get_name()}")

                # Create temporary image for this layer
                temp_image = Gimp.Image.new(
                    layer.get_width(), layer.get_height(), Gimp.ImageBaseType.RGB
                )

                # Use GIMP's built-in layer copying - much more reliable than manual buffer operations
                print(
                    f"DEBUG: Copying additional layer {i} using new_from_drawable method"
                )
                layer_copy = Gimp.Layer.new_from_drawable(layer, temp_image)
                layer_copy.set_name(f"layer_copy_{i}")
                temp_image.insert_layer(layer_copy, None, 0)
                print(
                    f"DEBUG: Additional layer {i} copy completed via new_from_drawable"
                )

                # Scale to match primary dimensions (proportional scaling)
                scale_x = target_width / layer.get_width()
                scale_y = target_height / layer.get_height()
                scale_factor = min(scale_x, scale_y)  # Maintain aspect ratio

                new_width = int(layer.get_width() * scale_factor)
                new_height = int(layer.get_height() * scale_factor)

                print(
                    f"DEBUG: Scaling layer {i}: {layer.get_width()}x{layer.get_height()} -> {new_width}x{new_height}"
                )

                temp_image.scale(new_width, new_height)
                layer_copy.scale(new_width, new_height, False)

                # If smaller than target, pad with transparency
                if new_width < target_width or new_height < target_height:
                    offset_x = (target_width - new_width) // 2
                    offset_y = (target_height - new_height) // 2
                    temp_image.resize(target_width, target_height, offset_x, offset_y)

                # Export layer to PNG
                layer_png_data = self._export_layer_to_png(temp_image)
                if layer_png_data:
                    layer_data_list.append(layer_png_data)
                    print(
                        f"DEBUG: Additional layer {i} exported: {len(layer_png_data)} bytes"
                    )

                temp_image.delete()

            print(
                f"DEBUG: Successfully prepared {len(layer_data_list)} layers for composite"
            )
            return (
                True,
                f"Prepared {len(layer_data_list)} layers",
                layer_data_list,
                optimal_shape,
            )

        except Exception as e:
            print(f"DEBUG: Layer preparation failed: {e}")
            return False, f"Layer preparation failed: {str(e)}", None, None

    def _export_layer_to_png(self, temp_image):
        """Helper function to export a GIMP image to PNG bytes"""
        try:
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_path = temp_file.name

            # Export using GIMP's PNG export
            file = Gio.File.new_for_path(temp_path)
            pdb_proc = Gimp.get_pdb().lookup_procedure("file-png-export")
            pdb_config = pdb_proc.create_config()
            pdb_config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
            pdb_config.set_property("image", temp_image)
            pdb_config.set_property("file", file)
            pdb_config.set_property("options", None)
            result = pdb_proc.run(pdb_config)

            if result.index(0) != Gimp.PDBStatusType.SUCCESS:
                os.unlink(temp_path)
                return None

            # Read the PNG data
            with open(temp_path, "rb") as f:
                png_data = f.read()

            # Debug the exported PNG
            print(f"DEBUG: Exported PNG size: {len(png_data)} bytes")
            print(
                f"DEBUG: Image dimensions: {temp_image.get_width()}x{temp_image.get_height()}"
            )
            print(
                f"DEBUG: Expected raw size: {temp_image.get_width() * temp_image.get_height() * 4} bytes (RGBA)"
            )
            print(
                f"DEBUG: Compression ratio: {len(png_data) / (temp_image.get_width() * temp_image.get_height() * 4):.4f}"
            )

            os.unlink(temp_path)
            return png_data

        except Exception as e:
            print(f"DEBUG: PNG export failed: {e}")
            return None

    def _create_full_size_mask_then_scale(self, image, selection_channel, context_info):
        """Create mask at full original size, then scale/pad using same operations as image"""
        try:
            target_shape = context_info["target_shape"]
            target_width, target_height = target_shape
            padding_info = context_info["padding_info"]
            scale_factor = padding_info["scale_factor"]
            scaled_w, scaled_h = padding_info["scaled_size"]
            pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

            # Determine the correct base size for mask creation
            if context_info.get("mode") == "full":
                # Full image mode: create mask at full image size
                mask_base_width = image.get_width()
                mask_base_height = image.get_height()
                print(
                    f"DEBUG: Creating mask at full image size {mask_base_width}x{mask_base_height}, then scaling like image"
                )
            else:
                # Focused/contextual mode: create mask at extract region size
                extract_region = context_info["extract_region"]
                mask_base_width = extract_region[2]
                mask_base_height = extract_region[3]
                print(
                    f"DEBUG: Creating mask at extract region size {mask_base_width}x{mask_base_height}, then scaling like image"
                )

            # Use the EXISTING working mask creation logic, but at correct base size
            mask_image = Gimp.Image.new(
                mask_base_width, mask_base_height, Gimp.ImageBaseType.RGB
            )
            mask_layer = Gimp.Layer.new(
                mask_image,
                "selection_mask",
                mask_base_width,
                mask_base_height,
                Gimp.ImageType.RGBA_IMAGE,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with black (preserve areas)
            from gi.repository import Gegl

            black_color = Gegl.Color.new("black")
            Gimp.context_set_foreground(black_color)
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)

            # Copy selection shape exactly as the working code does
            selection_buffer = selection_channel.get_buffer()
            mask_shadow_buffer = mask_layer.get_shadow_buffer()

            # Use the WORKING Gegl approach from the existing code
            graph = Gegl.Node()

            mask_source = graph.create_child("gegl:buffer-source")
            mask_source.set_property("buffer", mask_layer.get_buffer())

            selection_source = graph.create_child("gegl:buffer-source")
            selection_source.set_property("buffer", selection_buffer)

            composite = graph.create_child("gegl:over")
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", mask_shadow_buffer)

            mask_source.link(composite)
            selection_source.connect_to("output", composite, "aux")
            composite.link(output)
            output.process()

            mask_shadow_buffer.flush()
            mask_layer.merge_shadow(True)
            mask_layer.update(0, 0, mask_base_width, mask_base_height)

            # Make white areas transparent (WORKING code)
            transparency_graph = Gegl.Node()
            layer_buffer = mask_layer.get_buffer()
            shadow_buffer = mask_layer.get_shadow_buffer()

            buffer_source = transparency_graph.create_child("gegl:buffer-source")
            buffer_source.set_property("buffer", layer_buffer)

            color_to_alpha = transparency_graph.create_child("gegl:color-to-alpha")
            white_color = Gegl.Color.new("white")
            color_to_alpha.set_property("color", white_color)

            buffer_write = transparency_graph.create_child("gegl:write-buffer")
            buffer_write.set_property("buffer", shadow_buffer)

            buffer_source.link(color_to_alpha)
            color_to_alpha.link(buffer_write)
            buffer_write.process()

            shadow_buffer.flush()
            mask_layer.merge_shadow(True)
            mask_layer.update(0, 0, mask_base_width, mask_base_height)

            print(
                f"DEBUG: Created mask at original size with transparent selection areas"
            )

            # NOW scale using SAME operations as image
            if scale_factor != 1.0:
                mask_image.scale(scaled_w, scaled_h)
                print(f"DEBUG: Scaled mask to {scaled_w}x{scaled_h}")

            if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                mask_image.resize(target_width, target_height, pad_left, pad_top)
                print(
                    f"DEBUG: Added padding to mask to reach {target_width}x{target_height}"
                )

            # Export (same as working code)
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name

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
                os.unlink(temp_filename)
                raise Exception("PNG export failed")

            with open(temp_filename, "rb") as f:
                png_data = f.read()

            os.unlink(temp_filename)
            mask_image.delete()
            image.remove_channel(selection_channel)

            print(f"DEBUG: Created full-size-then-scaled mask: {len(png_data)} bytes")
            return png_data

        except Exception as e:
            print(f"DEBUG: Full size mask creation failed: {e}")
            if "mask_image" in locals():
                mask_image.delete()
            if "selection_channel" in locals():
                image.remove_channel(selection_channel)
            raise Exception(f"Full size mask creation failed: {e}")

    def _create_context_mask(self, image, context_info, target_size):
        """Create mask from actual selection shape using pixel-by-pixel copying"""
        try:
            target_shape = context_info.get("target_shape", (target_size, target_size))
            target_width, target_height = target_shape
            print(
                f"DEBUG: Creating pixel-perfect selection mask {target_width}x{target_height}"
            )

            if not context_info["has_selection"]:
                raise Exception(
                    "No selection available - selection-shaped mask requires an active selection"
                )

            # Get extract region info
            ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
            print(
                f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}) size {ctx_width}x{ctx_height}"
            )

            # Step 1: Save original selection as channel to preserve its exact shape
            selection_channel = Gimp.Selection.save(image)
            if not selection_channel:
                raise Exception("Failed to save selection as channel")
            print("DEBUG: Saved selection as channel for pixel copying")

            # For any mode with padding, use simplified approach that mirrors image processing
            if "padding_info" in context_info:
                return self._create_full_size_mask_then_scale(
                    image, selection_channel, context_info
                )

            # Step 2: Create target-shaped mask image (RGBA for transparency)
            mask_image = Gimp.Image.new(
                target_width, target_height, Gimp.ImageBaseType.RGB
            )
            if not mask_image:
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask image")

            mask_layer = Gimp.Layer.new(
                mask_image,
                "selection_mask",
                target_width,
                target_height,
                Gimp.ImageType.RGBA_IMAGE,
                100.0,
                Gimp.LayerMode.NORMAL,
            )
            if not mask_layer:
                mask_image.delete()
                image.remove_channel(selection_channel)
                raise Exception("Failed to create mask layer")

            mask_image.insert_layer(mask_layer, None, 0)

            # Fill with black background (preserve all areas initially)
            from gi.repository import Gegl

            black_color = Gegl.Color.new("black")
            Gimp.context_set_foreground(black_color)
            mask_layer.edit_fill(Gimp.FillType.FOREGROUND)
            print("DEBUG: Created black background mask (preserve all areas)")

            # Force layer update to make sure black fill is committed
            mask_layer.update(0, 0, target_width, target_height)

            # Explicitly ensure extension areas stay black by filling the entire target area
            print(
                f"DEBUG: Ensuring all extension areas are black in {target_width}x{target_height} mask"
            )

            # Step 3: Copy only the original image area, leave extended context white

            # Calculate where original image appears in context square
            orig_width, orig_height = image.get_width(), image.get_height()
            img_offset_x = max(
                0, -ctx_x1
            )  # where original image starts in context square
            img_offset_y = max(
                0, -ctx_y1
            )  # where original image starts in context square
            # Calculate where the original image content appears in the final padded target shape
            # Account for both extract region and padding
            if "padding_info" in context_info:
                padding_info = context_info["padding_info"]
                scale_factor = padding_info["scale_factor"]
                pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                # Original content is scaled and then padded
                img_end_x = min(
                    target_width - pad_left - pad_right, int(orig_width * scale_factor)
                )
                img_end_y = min(
                    target_height - pad_top - pad_bottom,
                    int(orig_height * scale_factor),
                )

                print(
                    f"DEBUG: Accounting for padding in mask - scale={scale_factor}, padding=({pad_left},{pad_top},{pad_right},{pad_bottom})"
                )
            else:
                # Fallback to simple calculation
                img_end_x = min(
                    ctx_width, orig_width - ctx_x1 if ctx_x1 >= 0 else orig_width
                )
                img_end_y = min(
                    ctx_height, orig_height - ctx_y1 if ctx_y1 >= 0 else orig_height
                )

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

                # Source 1: Current mask buffer (black background)
                mask_source = graph.create_child("gegl:buffer-source")
                mask_source.set_property("buffer", mask_layer.get_buffer())

                # Source 2: Selection channel buffer (contains exact selection shape)
                selection_source = graph.create_child("gegl:buffer-source")
                selection_source.set_property("buffer", selection_buffer)

                # Scale selection if needed to match the final image scaling
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    scale_factor = padding_info["scale_factor"]

                    if abs(scale_factor - 1.0) > 0.001:  # Need scaling
                        print(
                            f"DEBUG: Scaling selection channel by factor {scale_factor}"
                        )
                        scale_op = graph.create_child("gegl:scale-ratio")
                        scale_op.set_property("x", float(scale_factor))
                        scale_op.set_property("y", float(scale_factor))
                        selection_source.link(scale_op)
                        selection_input = scale_op
                    else:
                        selection_input = selection_source
                else:
                    selection_input = selection_source

                # Translate selection to correct position in padded target shape
                # For full image with padding, the selection has been scaled and needs padding offset
                if "padding_info" in context_info:
                    padding_info = context_info["padding_info"]
                    pad_left, pad_top, pad_right, pad_bottom = padding_info["padding"]

                    # Selection has already been scaled, just add padding offset
                    translate_x = pad_left
                    translate_y = pad_top

                    print(
                        f"DEBUG: Mask translation for padded image: translate by ({translate_x},{translate_y})"
                    )
                else:
                    # Original logic for non-padded extracts
                    translate_x = -ctx_x1
                    translate_y = -ctx_y1

                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(translate_x))
                translate.set_property("y", float(translate_y))

                # Connect scaled selection through translate to composite
                selection_input.link(translate)

                # Composite the translated selection over the black background
                # This preserves the black background in extension areas
                composite = graph.create_child("gegl:over")

                # Write to mask shadow buffer
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", mask_shadow_buffer)

                # Link the processing chain:
                # mask_source (black bg) + translated_selection → composite → output
                selection_source.link(translate)
                mask_source.link(composite)
                translate.connect_to("output", composite, "aux")
                composite.link(output)

                print(
                    f"DEBUG: Compositing selection over black background: translate by ({translate_x},{translate_y})"
                )

                # Process the graph to composite selection shape over black background
                output.process()
                print(
                    "DEBUG: Successfully composited selection shape over black background preserving extension areas"
                )

                # Flush and merge shadow buffer to make changes visible
                mask_shadow_buffer.flush()
                mask_layer.merge_shadow(True)
                print("DEBUG: Merged shadow buffer with base layer")
            else:
                print("DEBUG: No intersection - mask remains fully white")

            # Force complete layer update
            mask_layer.update(0, 0, target_width, target_height)

            # Force flush all changes to ensure PNG export sees the correct data
            Gimp.displays_flush()

            print("DEBUG: Successfully copied exact selection shape to mask using Gegl")

            # Step 4: Mask is already at target shape, no scaling needed
            # (Previous version scaled square masks, but we now create masks at target shape)
            print(f"DEBUG: Mask created at target shape {target_width}x{target_height}")

            # Step 4.5: Make selection areas transparent (the one simple change requested)
            # Current state: black background, white selection copied from channel
            # Needed: black background (preserve), transparent selection (inpaint)
            print("DEBUG: Making selection areas transparent for inpainting")
            scaled_mask_layer = mask_image.get_layers()[0]

            # Create a simple color-to-alpha operation to make selection areas transparent
            from gi.repository import Gegl

            transparency_graph = Gegl.Node()

            # Get layer buffer
            layer_buffer = scaled_mask_layer.get_buffer()
            shadow_buffer = scaled_mask_layer.get_shadow_buffer()

            # Source buffer
            buffer_source = transparency_graph.create_child("gegl:buffer-source")
            buffer_source.set_property("buffer", layer_buffer)

            # Convert white (selection) to transparent, keep everything else as-is
            color_to_alpha = transparency_graph.create_child("gegl:color-to-alpha")
            white_color = Gegl.Color.new("white")
            color_to_alpha.set_property("color", white_color)

            # Output buffer
            buffer_write = transparency_graph.create_child("gegl:write-buffer")
            buffer_write.set_property("buffer", shadow_buffer)

            # Process: source → color-to-alpha → output
            buffer_source.link(color_to_alpha)
            color_to_alpha.link(buffer_write)
            buffer_write.process()

            # Merge changes
            shadow_buffer.flush()
            scaled_mask_layer.merge_shadow(True)
            scaled_mask_layer.update(0, 0, target_size, target_size)

            print(
                "DEBUG: Selection areas are now transparent (inpaint), context/extension areas are black (preserved)"
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

    def _apply_smart_mask_feathering(self, mask, image):
        """Apply smart feathering to mask edges for better blending while preserving selection size"""
        try:
            print("DEBUG: Applying smart mask feathering for enhanced edge blending")

            from gi.repository import Gegl

            # Get mask dimensions and buffer
            mask_width = mask.get_width()
            mask_height = mask.get_height()
            mask_buffer = mask.get_buffer()
            shadow_buffer = mask.get_shadow_buffer()

            print(f"DEBUG: Processing mask {mask_width}x{mask_height}")

            # Simplified approach: Apply graduated gaussian blur
            # This softens edges without changing the overall selection area
            graph = Gegl.Node()

            # Source: Current mask buffer
            source = graph.create_child("gegl:buffer-source")
            source.set_property("buffer", mask_buffer)

            # Apply moderate gaussian blur to soften edges
            # Use smaller blur to maintain selection size while softening transitions
            blur = graph.create_child("gegl:gaussian-blur")
            blur.set_property("std-dev-x", 4.0)  # Moderate blur for edge softening
            blur.set_property("std-dev-y", 4.0)

            # Output to shadow buffer
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", shadow_buffer)

            # Link the chain: source -> blur -> output
            source.link(blur)
            blur.link(output)

            # Process the graph
            print("DEBUG: Processing edge feathering...")
            output.process()

            # Merge changes
            shadow_buffer.flush()
            mask.merge_shadow(True)
            mask.update(0, 0, mask_width, mask_height)

            print(
                "DEBUG: Smart edge feathering applied - edges softened while preserving selection area"
            )

        except Exception as e:
            print(f"DEBUG: Smart mask feathering failed (using simple feathering): {e}")
            # Fallback: apply light gaussian blur to entire mask
            try:
                from gi.repository import Gegl

                mask_buffer = mask.get_buffer()
                shadow_buffer = mask.get_shadow_buffer()

                # Simple fallback: light gaussian blur on entire mask
                graph = Gegl.Node()

                source = graph.create_child("gegl:buffer-source")
                source.set_property("buffer", mask_buffer)

                blur = graph.create_child("gegl:gaussian-blur")
                blur.set_property("std-dev-x", 2.0)
                blur.set_property("std-dev-y", 2.0)

                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", shadow_buffer)

                source.link(blur)
                blur.link(output)
                output.process()

                shadow_buffer.flush()
                mask.merge_shadow(True)
                mask.update(0, 0, mask.get_width(), mask.get_height())

                print("DEBUG: Applied fallback simple feathering")

            except Exception as e2:
                print(
                    f"DEBUG: Both smart and simple feathering failed, using original mask: {e2}"
                )

    def _sample_boundary_colors(self, image, context_info):
        """Sample colors around selection boundary for color matching"""
        try:
            print("DEBUG: Sampling boundary colors for color matching")

            if not context_info.get("has_selection", False):
                return None

            # Get selection bounds
            sel_x1, sel_y1, sel_x2, sel_y2 = context_info["selection_bounds"]

            # Sample from a ring around the selection edge
            # Inner ring: just inside selection
            # Outer ring: just outside selection
            sample_width = min(10, (sel_x2 - sel_x1) // 10)  # Adaptive sample width

            # Get the flattened image for color sampling
            merged_layer = None
            try:
                # Create a temporary flattened copy for sampling
                temp_image = image.duplicate()
                merged_layer = temp_image.flatten()

                # Sample colors using GEGL buffer operations
                from gi.repository import Gegl

                layer_buffer = merged_layer.get_buffer()

                # Sample pixels around selection boundary
                inner_samples = []
                outer_samples = []

                # Sample points along the selection perimeter
                sample_points = 20  # Number of sample points

                for i in range(sample_points):
                    # Calculate position along selection perimeter
                    t = i / sample_points

                    # Sample along top and bottom edges
                    if i < sample_points // 2:
                        x = int(sel_x1 + t * 2 * (sel_x2 - sel_x1))
                        y_inner = sel_y1 + sample_width // 2
                        y_outer = sel_y1 - sample_width // 2
                    else:
                        x = int(sel_x2 - (t - 0.5) * 2 * (sel_x2 - sel_x1))
                        y_inner = sel_y2 - sample_width // 2
                        y_outer = sel_y2 + sample_width // 2

                    # Ensure coordinates are within image bounds
                    x = max(0, min(x, image.get_width() - 1))
                    y_inner = max(0, min(y_inner, image.get_height() - 1))
                    y_outer = max(0, min(y_outer, image.get_height() - 1))

                    try:
                        # Sample inner color (inside selection)
                        inner_rect = Gegl.Rectangle.new(x, y_inner, 1, 1)
                        inner_pixel = layer_buffer.get(
                            inner_rect, 1.0, "R'G'B'A u8", Gegl.AbyssPolicy.CLAMP
                        )
                        if len(inner_pixel) >= 3:
                            inner_samples.append(
                                (inner_pixel[0], inner_pixel[1], inner_pixel[2])
                            )

                        # Sample outer color (outside selection)
                        outer_rect = Gegl.Rectangle.new(x, y_outer, 1, 1)
                        outer_pixel = layer_buffer.get(
                            outer_rect, 1.0, "R'G'B'A u8", Gegl.AbyssPolicy.CLAMP
                        )
                        if len(outer_pixel) >= 3:
                            outer_samples.append(
                                (outer_pixel[0], outer_pixel[1], outer_pixel[2])
                            )

                    except Exception as sample_e:
                        print(f"DEBUG: Sample point {i} failed: {sample_e}")
                        continue

                # Calculate average colors
                if inner_samples and outer_samples:
                    # Calculate averages
                    inner_avg = tuple(
                        sum(channel) // len(inner_samples)
                        for channel in zip(*inner_samples)
                    )
                    outer_avg = tuple(
                        sum(channel) // len(outer_samples)
                        for channel in zip(*outer_samples)
                    )

                    # Calculate differences for color correction
                    hue_diff = 0  # Simplified - could calculate actual hue difference
                    brightness_diff = (sum(outer_avg) // 3) - (sum(inner_avg) // 3)

                    color_info = {
                        "inner_avg": inner_avg,
                        "outer_avg": outer_avg,
                        "brightness_diff": brightness_diff,
                        "hue_diff": hue_diff,
                    }

                    print(
                        f"DEBUG: Sampled colors - Inner: {inner_avg}, Outer: {outer_avg}"
                    )
                    print(f"DEBUG: Brightness difference: {brightness_diff}")

                    return color_info
                else:
                    print("DEBUG: No valid color samples collected")
                    return None

            finally:
                # Clean up temporary image
                if merged_layer and hasattr(merged_layer, "get_image"):
                    temp_image = merged_layer.get_image()
                    if temp_image:
                        temp_image.delete()

        except Exception as e:
            print(f"DEBUG: Color sampling failed: {e}")
            return None

    def _apply_color_matching(self, result_layer, color_info):
        """Apply color correction to match sampled boundary colors"""
        if not color_info:
            print("DEBUG: No color info available - skipping color matching")
            return

        try:
            print("DEBUG: Applying color matching based on boundary samples")

            from gi.repository import Gegl

            # Get layer buffer
            layer_buffer = result_layer.get_buffer()
            shadow_buffer = result_layer.get_shadow_buffer()

            # Create color correction graph
            graph = Gegl.Node()

            # Source buffer
            source = graph.create_child("gegl:buffer-source")
            source.set_property("buffer", layer_buffer)

            # Apply brightness/levels adjustment if significant difference
            brightness_diff = color_info.get("brightness_diff", 0)
            if abs(brightness_diff) > 10:  # Only apply if difference is noticeable
                levels = graph.create_child("gegl:levels")

                # Adjust gamma based on brightness difference
                gamma_adjust = 1.0 + (brightness_diff / 255.0)
                gamma_adjust = max(0.5, min(2.0, gamma_adjust))  # Clamp gamma

                levels.set_property("in-low", 0.0)
                levels.set_property("in-high", 1.0)
                levels.set_property("gamma", gamma_adjust)
                levels.set_property("out-low", 0.0)
                levels.set_property("out-high", 1.0)

                source.link(levels)
                current_node = levels

                print(f"DEBUG: Applied gamma correction: {gamma_adjust}")
            else:
                current_node = source
                print(
                    "DEBUG: No significant brightness difference - skipping levels adjustment"
                )

            # Output buffer
            output = graph.create_child("gegl:write-buffer")
            output.set_property("buffer", shadow_buffer)

            current_node.link(output)

            # Process color correction
            output.process()

            # Merge changes
            shadow_buffer.flush()
            result_layer.merge_shadow(True)
            result_layer.update(
                0, 0, result_layer.get_width(), result_layer.get_height()
            )

            print("DEBUG: Color matching applied successfully")

        except Exception as e:
            print(f"DEBUG: Color matching failed: {e}")

    def _create_multipart_data(self, fields, files):
        """Create multipart form data for file upload - supports image arrays"""
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

        # Add file fields - handle both single files and arrays
        for key, file_data in files.items():
            if key == "image" and isinstance(file_data, list):
                # Handle image array for composite mode - use image[] array syntax
                for i, (filename, data, content_type) in enumerate(file_data):
                    body += f"--{boundary}\r\n".encode()
                    body += f'Content-Disposition: form-data; name="image[]"; filename="{filename}"\r\n'.encode()
                    body += f"Content-Type: {content_type}\r\n\r\n".encode()
                    body += data
                    body += b"\r\n"
                print(f"DEBUG: Added {len(file_data)} images to multipart data")
            else:
                # Handle single file (like mask or single image)
                filename, data, content_type = file_data
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
                body += f"Content-Type: {content_type}\r\n\r\n".encode()
                body += data
                body += b"\r\n"

        # End boundary
        body += f"--{boundary}--\r\n".encode()

        return body, boundary

    def _call_openai_edit(
        self,
        image_data,
        mask_data,
        prompt,
        api_key,
        size="1024x1024",
        progress_label=None,
    ):
        """Call OpenAI GPT-Image-1 API for image editing (supports single image or array)"""
        try:
            print(f"DEBUG: Calling GPT-Image-1 API with prompt: {prompt}")

            # Validate inputs
            if not prompt or not prompt.strip():
                return False, "Error: Empty prompt provided", None

            if not image_data:
                return False, "Error: No image data provided", None

            # Support both single image and array of images
            is_array_mode = isinstance(image_data, list)

            if is_array_mode:
                print(f"DEBUG: Array mode: {len(image_data)} images provided")
                if len(image_data) < 2:
                    return (
                        False,
                        "Error: At least 2 images required for composite mode",
                        None,
                    )
                if len(image_data) > 16:
                    return False, "Error: Maximum 16 layers supported", None
            else:
                print("DEBUG: Single image mode")
                if not mask_data:
                    return (
                        False,
                        "Error: No mask data provided for single image mode",
                        None,
                    )

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
                "size": size if size else "1024x1024",  # Use provided size or default
                "moderation": "low",  # Less restrictive filtering
                "input_fidelity": "high",  # High fidelity for better results
            }

            # Prepare files for API based on mode
            import base64

            files = {}

            if is_array_mode:
                # Array mode - multiple images for composite (with same validation as single mode)
                image_files = []

                for i, layer_data in enumerate(image_data):
                    # Debug the input data format
                    print(
                        f"DEBUG: Array input {i} - type: {type(layer_data)}, size: {len(layer_data) if hasattr(layer_data, '__len__') else 'N/A'}"
                    )
                    if hasattr(layer_data, "startswith"):
                        png_header = b"\x89PNG"
                        has_png_header = (
                            layer_data.startswith(png_header)
                            if isinstance(layer_data, bytes)
                            else "not bytes"
                        )
                        print(
                            f"DEBUG: Array input {i} - starts with PNG header: {has_png_header}"
                        )

                    # Apply same validation as single image mode
                    if isinstance(layer_data, str):
                        # Base64 encoded data - decode it
                        print(f"DEBUG: Array input {i} - decoding base64 string")
                        layer_bytes = base64.b64decode(layer_data)
                    else:
                        # Already binary data
                        print(f"DEBUG: Array input {i} - using binary data as-is")
                        layer_bytes = layer_data

                    # Create debug file for inspection (same as single mode)
                    if self._is_debug_mode():
                        debug_filename = f"/tmp/gpt-image-1_array_image_{i}_{len(layer_bytes)}_bytes.png"
                        with open(debug_filename, "wb") as debug_file:
                            debug_file.write(layer_bytes)
                        print(f"DEBUG: Saved array image {i} to {debug_filename}")

                    # Validate PNG format (same as single mode)
                    if layer_bytes.startswith(b"\x89PNG"):
                        if len(layer_bytes) > 25:
                            # Extract dimensions and format info
                            img_width = int.from_bytes(layer_bytes[16:20], "big")
                            img_height = int.from_bytes(layer_bytes[20:24], "big")
                            color_type = layer_bytes[25]
                            format_names = {
                                0: "L",
                                2: "RGB",
                                3: "P",
                                4: "LA",
                                6: "RGBA",
                            }
                            format_name = format_names.get(
                                color_type, f"Unknown({color_type})"
                            )
                            print(
                                f"DEBUG: Array image {i} format: {format_name} (color type {color_type}) dimensions: {img_width}x{img_height}"
                            )
                        else:
                            print(f"DEBUG: Array image {i} PNG header too short")
                    else:
                        print(f"DEBUG: Array image {i} is not PNG format!")

                    image_files.append((f"image_{i}.png", layer_bytes, "image/png"))
                    print(f"DEBUG: Added validated layer {i}: {len(layer_bytes)} bytes")

                files["image"] = image_files

                # Add mask if provided (applies to first image) - with same validation
                if mask_data:
                    # Create debug file for mask
                    if self._is_debug_mode():
                        debug_mask_filename = (
                            f"/tmp/gpt-image-1_array_mask_{len(mask_data)}_bytes.png"
                        )
                        with open(debug_mask_filename, "wb") as debug_file:
                            debug_file.write(mask_data)
                        print(f"DEBUG: Saved array mask to {debug_mask_filename}")

                    # Validate mask format (same as single mode)
                    if mask_data.startswith(b"\x89PNG"):
                        if len(mask_data) > 25:
                            mask_width = int.from_bytes(mask_data[16:20], "big")
                            mask_height = int.from_bytes(mask_data[20:24], "big")
                            color_type = mask_data[25]
                            format_names = {
                                0: "L",
                                2: "RGB",
                                3: "P",
                                4: "LA",
                                6: "RGBA",
                            }
                            format_name = format_names.get(
                                color_type, f"Unknown({color_type})"
                            )
                            print(
                                f"DEBUG: Array mask format: {format_name} (color type {color_type}) dimensions: {mask_width}x{mask_height}"
                            )
                            print(f"DEBUG: Array mask size: {len(mask_data)} bytes")

                            # Check dimensions against first image (if available)
                            if image_files:
                                first_image_bytes = image_files[0][1]
                                if (
                                    first_image_bytes.startswith(b"\x89PNG")
                                    and len(first_image_bytes) > 25
                                ):
                                    first_img_width = int.from_bytes(
                                        first_image_bytes[16:20], "big"
                                    )
                                    first_img_height = int.from_bytes(
                                        first_image_bytes[20:24], "big"
                                    )
                                    if (
                                        first_img_width == mask_width
                                        and first_img_height == mask_height
                                    ):
                                        print(
                                            "DEBUG: ✅ Array mask and first image dimensions match!"
                                        )
                                    else:
                                        print(
                                            f"DEBUG: ❌ DIMENSION MISMATCH! First image: {first_img_width}x{first_img_height}, Mask: {mask_width}x{mask_height}"
                                        )
                        else:
                            print("DEBUG: Array mask PNG header too short")
                    else:
                        print("DEBUG: Array mask is not PNG format!")

                    files["mask"] = ("mask.png", mask_data, "image/png")
                    print(
                        f"DEBUG: Added validated mask: {len(mask_data)} bytes (applies to first image)"
                    )

                print(
                    f"DEBUG: Prepared {len(image_files)} validated images for composite mode"
                )

            else:
                # Single image mode - traditional inpainting
                image_bytes = base64.b64decode(image_data)

                # Save debug copies of what we're sending to GPT-Image-1
                if self._is_debug_mode():
                    debug_input_filename = (
                        f"/tmp/gpt-image-1_input_{len(image_bytes)}_bytes.png"
                    )
                    with open(debug_input_filename, "wb") as debug_file:
                        debug_file.write(image_bytes)
                    print(f"DEBUG: Saved input image to {debug_input_filename}")

                    debug_mask_filename = (
                        f"/tmp/gpt-image-1_mask_{len(mask_data)}_bytes.png"
                    )
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
                        format_name = format_names.get(
                            color_type, f"Unknown({color_type})"
                        )
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
                        format_name = format_names.get(
                            color_type, f"Unknown({color_type})"
                        )
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
            # if progress_label:
            #     self._update_dual_progress(progress_label, "Sending request to GPT-Image-1...", 0.65)
            # else:
            #     # Fallback to old system if no dialog progress
            #     Gimp.progress_set_text("Sending request to GPT-Image-1...")
            #     Gimp.progress_update(0.65)  # 65% - API request started (after 60% mask)
            #     Gimp.displays_flush()  # Force UI update before blocking network call

            with self._make_url_request(req, timeout=120) as response:
                # More progress during data reading
                if progress_label:
                    self._update_progress(
                        progress_label, "Processing AI response...", 0.7
                    )
                else:
                    Gimp.progress_set_text("Processing AI response...")
                    Gimp.progress_update(0.7)  # 70% - Reading response

                response_data = response.read().decode("utf-8")

                if progress_label:
                    self._update_progress(progress_label, "Parsing AI result...", 0.75)
                else:
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

    def _call_openai_edit_threaded(
        self,
        image_data,
        mask_data,
        prompt,
        api_key,
        size="1024x1024",
        progress_label=None,
    ):
        """Threaded wrapper for OpenAI API call to keep UI responsive"""
        def operation():
            success, message, response = self._call_openai_edit(
                image_data, mask_data, prompt, api_key, size, progress_label
            )
            return {"success": success, "message": message, "data": response}

        return self._run_threaded_operation(
            operation, "OpenAI edit API call", progress_label
        )

    def _download_and_composite_result(
        self, image, api_response, context_info, mode, color_info=None
    ):
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
            if self._is_debug_mode():
                debug_filename = f"/tmp/gpt-image-1_result_{len(image_data)}_bytes.png"
                with open(debug_filename, "wb") as debug_file:
                    debug_file.write(image_data)
                print(
                    f"DEBUG: Saved GPT-Image-1 result to {debug_filename} for inspection"
                )

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
                ctx_x1, ctx_y1, ctx_width, ctx_height = context_info["extract_region"]
                target_shape = context_info["target_shape"]

                print(f"DEBUG: Original image: {orig_width}x{orig_height}")
                print(
                    f"DEBUG: Selection bounds: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})"
                )
                print(
                    f"DEBUG: Extract region: ({ctx_x1},{ctx_y1}), size {ctx_width}x{ctx_height}"
                )

                # Scale AI result back to extract region size if needed
                if (
                    ai_layer.get_width() != ctx_width
                    or ai_layer.get_height() != ctx_height
                ):
                    scaled_img = ai_result_img.duplicate()

                    # For any mode with padding, remove padding first, then scale
                    if "padding_info" in context_info:
                        padding_info = context_info["padding_info"]
                        pad_left, pad_top, pad_right, pad_bottom = padding_info[
                            "padding"
                        ]
                        scaled_w, scaled_h = padding_info["scaled_size"]

                        print(
                            f"DEBUG: Removing padding from AI result: crop to {scaled_w}x{scaled_h}"
                        )
                        print(
                            f"DEBUG: Padding to remove: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}"
                        )

                        # Crop to remove padding (get the actual content without black bars)
                        scaled_img.crop(scaled_w, scaled_h, pad_left, pad_top)
                        print(
                            f"DEBUG: Cropped AI result to {scaled_w}x{scaled_h} (removed padding)"
                        )

                        # Now scale the unpadded result to original size
                        scaled_img.scale(ctx_width, ctx_height)
                        print(
                            f"DEBUG: Scaled unpadded result to original size: {ctx_width}x{ctx_height}"
                        )
                    else:
                        # Normal scaling for non-padded results
                        scaled_img.scale(ctx_width, ctx_height)
                        print(
                            f"DEBUG: Scaled AI result to extract region size: {ctx_width}x{ctx_height}"
                        )

                    scaled_layers = scaled_img.get_layers()
                    if scaled_layers:
                        ai_layer = scaled_layers[0]

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
                    f"DEBUG: Placing {ctx_width}x{ctx_height} AI result at ({paste_x},{paste_y})"
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

                # Apply color matching for contextual mode (before masking)
                if mode == "contextual" and color_info:
                    print("DEBUG: Applying color matching to result layer...")
                    self._apply_color_matching(result_layer, color_info)

                # Create a layer mask for contextual mode only
                if mode == "contextual" and context_info["has_selection"]:
                    print(
                        "DEBUG: Creating selection-based mask for contextual mode while preserving full AI result in layer"
                    )

                    # Use GIMP's built-in selection mask type to automatically create properly shaped mask
                    # This preserves the full AI content in the layer but masks visibility to selection area
                    mask = result_layer.create_mask(Gimp.AddMaskType.SELECTION)
                    result_layer.add_mask(mask)

                    # Apply smart feathering to the mask for better blending
                    self._apply_smart_mask_feathering(mask, image)

                    print(
                        "DEBUG: Applied selection-based layer mask with smart feathering - enhanced blending at edges"
                    )
                    print(
                        "DEBUG: Core subject preserved at 100%, edges feathered for seamless integration"
                    )
                else:
                    print(
                        "DEBUG: No selection or full_image mode - layer shows full AI result without mask"
                    )

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

    def do_query_procedures(self):
        return [
            "gimp-ai-inpaint",
            "gimp-ai-layer-generator",
            "gimp-ai-layer-composite",
        ]

    def do_create_procedure(self, name):
        if name == "gimp-ai-inpaint":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_inpaint, None
            )
            procedure.set_menu_label("Inpainting")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-layer-generator":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_layer_generator, None
            )
            procedure.set_menu_label("Image Generator")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-layer-composite":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_layer_composite, None
            )
            procedure.set_menu_label("Layer Composite")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        return None

    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Inpaint Selection called!")

        # Save the currently selected layers before any API calls that might clear them
        original_selected_layers = image.get_selected_layers()
        print(f"DEBUG: Saved {len(original_selected_layers)} originally selected layers")

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
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after no canvas selection error")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        print("DEBUG: Selection found - proceeding with inpainting")

        # Step 2: Get user prompt
        print("DEBUG: About to show prompt dialog...")
        dialog_result = self._show_prompt_dialog(
            "AI Inpaint",
            "",
            show_mode_selection=True,
            image=image,
        )
        print(f"DEBUG: Dialog returned: {repr(dialog_result)}")

        if not dialog_result:
            print("DEBUG: User cancelled prompt dialog")
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after dialog cancel")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Extract dialog, progress_label, prompt and mode from dialog result
        dialog, progress_label, prompt, selected_mode = dialog_result
        print(f"DEBUG: Extracted prompt: '{prompt}', mode: '{selected_mode}'")

        try:
            # Step 3: Get API key
            api_key = self._get_api_key()
            if not api_key:
                self._update_progress(progress_label, "❌ No OpenAI API key found!")
                Gimp.message(
                    "❌ No OpenAI API key found!\n\nPlease set your API key in:\n- config.json file\n- OPENAI_API_KEY environment variable"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Create progress callback for thread-to-UI communication
            progress_callback = self._create_progress_callback(progress_label)

            # Do GIMP operations on main thread, only thread the API call
            mode = self._get_processing_mode(selected_mode)
            print(f"DEBUG: Using processing mode: {mode}")

            self._update_progress(progress_label, "🔍 Processing image...")

            if mode == "full_image":
                print("DEBUG: Calculating full-image context extraction...")
                context_info = self._calculate_full_image_context_extraction(image)
            elif mode == "contextual":
                print("DEBUG: Calculating contextual selection-based extraction...")
                context_info = self._calculate_context_extraction(image)
            else:
                print("DEBUG: Unknown mode, defaulting to contextual extraction...")
                context_info = self._calculate_context_extraction(image)

            self._update_progress(progress_label, "🔍 Analyzing image context...")

            # Sample boundary colors for contextual mode (before inpainting)
            color_info = None
            if (
                mode == "contextual"
                and context_info
                and context_info.get("has_selection", False)
            ):
                print("DEBUG: Sampling boundary colors for color matching...")
                color_info = self._sample_boundary_colors(image, context_info)

            # Extract context region with padding (works for both modes)
            print("DEBUG: Extracting context region...")
            success, message, image_data = self._extract_context_region(
                image, context_info
            )
            if not success:
                self._update_progress(
                    progress_label, f"❌ Context extraction failed: {message}"
                )
                Gimp.message(f"❌ Context Extraction Failed: {message}")
                print(f"DEBUG: Context extraction failed: {message}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )
            print(f"DEBUG: Context extraction succeeded: {message}")

            self._update_progress(progress_label, "🎭 Creating selection mask...")

            # Create smart mask that respects selection within context
            print("DEBUG: Creating context-aware mask...")
            if not context_info:
                self._update_progress(progress_label, "❌ Context info not available")
                Gimp.message("❌ Context info not available")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            mask_data = self._create_context_mask(
                image, context_info, context_info["target_size"]
            )

            self._update_progress(progress_label, "🚀 Starting AI processing...")

            # Determine the optimal size for OpenAI API
            if context_info and "target_shape" in context_info:
                target_w, target_h = context_info["target_shape"]
                api_size = f"{target_w}x{target_h}"
            elif context_info and "target_size" in context_info:
                # Fallback to square for old format
                size = context_info["target_size"]
                api_size = f"{size}x{size}"
            else:
                api_size = "1024x1024"  # Default

            print(f"DEBUG: Using OpenAI API size: {api_size}")

            api_success, api_message, api_response = self._call_openai_edit_threaded(
                image_data,
                mask_data,
                prompt,
                api_key,
                size=api_size,
                progress_label=progress_label,
            )

            if api_success:
                print(f"DEBUG: AI API succeeded: {api_message}")
                self._update_progress(progress_label, "Processing AI response...")

                # Download and composite result with proper masking
                import_success, import_message = self._download_and_composite_result(
                    image, api_response, context_info, mode, color_info
                )

                if import_success:
                    self._update_progress(progress_label, "✅ AI Inpaint Complete!")
                    print(f"DEBUG: AI Inpaint Complete - {import_message}")
                else:
                    self._update_progress(
                        progress_label, f"⚠️ Import Failed: {import_message}"
                    )
                    Gimp.message(
                        f"⚠️ AI Generated but Import Failed!\n\nPrompt: {prompt}\nAPI: {api_message}\nImport Error: {import_message}"
                    )
                    print(f"DEBUG: Import failed: {import_message}")
            else:
                # Check if this was a cancellation vs actual API failure
                if "cancelled" in api_message.lower():
                    self._update_progress(
                        progress_label, "❌ Operation cancelled by user"
                    )
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(
                        progress_label, f"❌ AI API Failed: {api_message}"
                    )
                    Gimp.message(f"❌ AI API Failed: {api_message}")
                print(f"DEBUG: AI API failed: {api_message}")

            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        finally:
            # Always destroy the dialog
            if dialog:
                dialog.destroy()
            # Always restore original layer selection after any operation outcome
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after inpaint operation")

    def run_layer_composite(
        self, procedure, run_mode, image, drawables, config, run_data
    ):
        """Layer Composite - combine multiple layers using OpenAI API"""
        print("DEBUG: Layer Composite called!")

        # Save the currently selected layers before showing dialog (which queries layers and might clear selection)
        original_selected_layers = image.get_selected_layers()
        print(f"DEBUG: Saved {len(original_selected_layers)} originally selected layers")

        # Step 1: Show prompt dialog with layer selection
        print("DEBUG: Showing layer composite dialog...")
        dialog_result = self._show_composite_dialog(image)
        print(f"DEBUG: Dialog returned: {repr(dialog_result)}")

        if not dialog_result:
            print("DEBUG: User cancelled prompt dialog")
            # Restore layer selection before returning
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after dialog cancel")
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Handle composite dialog result: (dialog, progress_label, prompt, layers, use_mask)
        dialog, progress_label, prompt, selected_layers, use_mask = dialog_result
        print(
            f"DEBUG: Layer composite mode: {len(selected_layers)} layers, mask: {use_mask}"
        )

        try:
            # Step 2: Get API key
            api_key = self._get_api_key()
            if not api_key:
                self._update_progress(progress_label, "❌ No OpenAI API key found!")
                Gimp.message(
                    "❌ No OpenAI API key found!\n\nPlease set your API key in:\n- config.json file\n- OPENAI_API_KEY environment variable"
                )
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            # Use existing layer preparation method
            self._update_progress(progress_label, "🔧 Preparing layers...")
            print("DEBUG: Preparing layers for composite...")

            # Reverse layer order so base layer (last in dialog list) is first for API
            layers_for_api = list(reversed(selected_layers))

            # Use the existing preparation method
            success, message, layer_data_list, optimal_shape = (
                self._prepare_layers_for_composite(layers_for_api)
            )
            if not success:
                self._update_progress(
                    progress_label, f"❌ Layer preparation failed: {message}"
                )
                Gimp.message(f"❌ Layer Preparation Failed: {message}")
                print(f"DEBUG: Layer preparation failed: {message}")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error()
                )

            print(f"DEBUG: Layer preparation succeeded: {message}")

            # Always create context_info for result processing (padding removal and scaling)
            img_width = image.get_width()
            img_height = image.get_height()
            target_width, target_height = optimal_shape

            # Import the padding calculation function
            from coordinate_utils import calculate_padding_for_shape

            # Create context_info for result processing
            context_info = {
                "mode": "full",
                "selection_bounds": (
                    0,
                    0,
                    img_width,
                    img_height,
                ),  # Default to full image
                "extract_region": (0, 0, img_width, img_height),  # Full image
                "target_shape": (target_width, target_height),
                "target_size": max(target_width, target_height),
                "needs_padding": True,
                "padding_info": calculate_padding_for_shape(
                    img_width, img_height, target_width, target_height
                ),
                "has_selection": False,  # Will be updated if mask is used
            }

            self._update_progress(progress_label, "Creating mask...")

            # Prepare mask if requested
            mask_data = None
            if use_mask:
                print("DEBUG: Preparing mask for primary layer...")
                # Use the same context-based mask approach as inpainting
                selection_bounds = Gimp.Selection.bounds(image)
                if len(selection_bounds) >= 5 and selection_bounds[0]:
                    print("DEBUG: Creating context-aware mask for layer composite...")

                    # Get selection bounds
                    sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
                    sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
                    sel_x2 = (
                        selection_bounds[4] if len(selection_bounds) > 4 else img_width
                    )
                    sel_y2 = (
                        selection_bounds[5] if len(selection_bounds) > 5 else img_height
                    )

                    # Update context_info with actual selection bounds
                    context_info["selection_bounds"] = (sel_x1, sel_y1, sel_x2, sel_y2)
                    context_info["has_selection"] = True

                    # Create mask using the same function as inpainting
                    mask_data = self._create_context_mask(
                        image, context_info, context_info["target_size"]
                    )
                    print(
                        f"DEBUG: Created context-aware selection mask for composite {target_width}x{target_height}"
                    )
                else:
                    # ERROR: User checked the mask box but there's no selection
                    print("DEBUG: ERROR - Use mask checked but no selection found")
                    self._update_progress(
                        progress_label, "❌ No selection found for mask"
                    )
                    Gimp.message(
                        "❌ Selection Required for Mask\n\n"
                        "You checked 'Include selection mask' but no selection was found.\n\n"
                        "Please either:\n"
                        "• Make a selection on your image, or\n"
                        "• Uncheck 'Include selection mask'"
                    )
                    return procedure.new_return_values(
                        Gimp.PDBStatusType.CANCEL, GLib.Error()
                    )

            self._update_progress(progress_label, "🚀 Starting AI processing...")

            # Call OpenAI API with layer array using optimal shape
            target_width, target_height = optimal_shape
            api_size = f"{target_width}x{target_height}"
            print(
                f"DEBUG: Calling OpenAI API with {len(layer_data_list)} layers, size={api_size}..."
            )

            api_success, api_message, api_response = self._call_openai_edit_threaded(
                layer_data_list,
                mask_data,
                prompt,
                api_key,
                size=api_size,
                progress_label=progress_label,
            )

            if api_success:
                print(f"DEBUG: AI API succeeded: {api_message}")
                self._update_progress(progress_label, "Processing AI response...")

                # Create result layer in GIMP
                if (
                    api_response
                    and "data" in api_response
                    and len(api_response["data"]) > 0
                ):
                    result_data = api_response["data"][0]

                    # Handle both URL and base64 response formats
                    if "b64_json" in result_data:
                        # Base64 format (gpt-image-1)
                        print("DEBUG: Processing base64 composite result...")

                        # Use the same result processing as inpainting to handle padding removal and scaling
                        print(
                            "DEBUG: Using inpainting result processing to handle padding and scaling..."
                        )
                        success, message = self._download_and_composite_result(
                            image, api_response, context_info, "full"
                        )

                        if success:
                            # Rename the layer to indicate it's a composite
                            new_layer = image.get_layers()[0]
                            new_layer.set_name("Layer Composite")

                            self._update_progress(
                                progress_label,
                                "✅ Layer Composite completed successfully!",
                            )
                            Gimp.message("✅ Layer Composite completed successfully!")
                            print("DEBUG: Layer composite creation successful")
                        else:
                            raise Exception(
                                f"Failed to process composite result: {message}"
                            )

                    elif "url" in result_data:
                        # URL format (fallback)
                        print("DEBUG: Downloading composite result from URL...")

                        import urllib.request

                        with urllib.request.urlopen(result_data["url"]) as response:
                            image_data = response.read()

                        # Create new layer with result
                        temp_image = self._create_image_from_data(image_data)
                        if temp_image:
                            new_layer = temp_image.get_layers()[0].copy()
                            new_layer.set_name("Layer Composite")
                            image.insert_layer(new_layer, None, 0)
                            temp_image.delete()

                            Gimp.progress_update(1.0)  # 100% - Complete
                            Gimp.message("✅ Layer Composite completed successfully!")
                        else:
                            raise Exception("Failed to create image from result data")
                    else:
                        raise Exception(
                            "No image data (b64_json or url) in API response"
                        )
                else:
                    self._update_progress(progress_label, "❌ No data in API response")
                    Gimp.message("❌ No data in API response")
            else:
                # Check if this was a cancellation vs actual API failure
                if "cancelled" in api_message.lower():
                    self._update_progress(
                        progress_label, "❌ Operation cancelled by user"
                    )
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(
                        progress_label, f"❌ AI API Failed: {api_message}"
                    )
                    Gimp.message(f"❌ AI API Failed: {api_message}")
                print(f"DEBUG: AI API failed: {api_message}")

            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

        finally:
            # Always destroy the dialog
            if dialog:
                dialog.destroy()
            # Always restore original layer selection after any operation outcome
            if original_selected_layers:
                image.set_selected_layers(original_selected_layers)
                print("DEBUG: Restored layer selection after layer composite operation")

    def _create_image_from_data(self, image_data):
        """Helper function to create GIMP image from binary data"""
        try:
            import tempfile
            import os

            print(f"DEBUG: Writing {len(image_data)} bytes to temp file...")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_file.write(image_data)
                temp_path = temp_file.name
            print(f"DEBUG: Temp file created: {temp_path}")

            # Load image using GIMP
            print("DEBUG: Creating Gio.File...")
            file = Gio.File.new_for_path(temp_path)
            print("DEBUG: Calling Gimp.file_load()...")
            temp_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, file)
            print("DEBUG: Gimp.file_load() completed")

            print("DEBUG: Cleaning up temp file...")
            os.unlink(temp_path)
            print("DEBUG: Image creation successful")
            return temp_image

        except Exception as e:
            print(f"DEBUG: Failed to create image from data: {e}")
            return None

    def _generate_gpt_image_layer_threaded(
        self, image, prompt, api_key, size="auto", progress_label=None
    ):
        """Threaded wrapper for GPT image generation to keep UI responsive"""
        import threading
        import time

        print("DEBUG: Starting threaded GPT-Image-1 generation...")

        # Shared storage for results
        result = {"success": False, "completed": False}

        def generation_thread():
            try:
                # Call the blocking API directly with progress updates
                import json
                import urllib.request
                import ssl

                # Determine optimal size based on image dimensions or user preference
                if size == "auto":
                    img_width = image.get_width()
                    img_height = image.get_height()
                    aspect_ratio = img_width / img_height

                    if aspect_ratio > 1.2:  # Landscape
                        optimal_size = "1536x1024"
                    elif aspect_ratio < 0.83:  # Portrait
                        optimal_size = "1024x1536"
                    else:  # Square or close to square
                        optimal_size = "1024x1024"
                else:
                    optimal_size = size

                print(f"DEBUG: [THREAD] Using size {optimal_size} for generation")

                # Prepare the request data
                data = {
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": 1,
                    "size": optimal_size,
                    "quality": "high",
                }

                # Create the request
                json_data = json.dumps(data).encode("utf-8")
                url = "https://api.openai.com/v1/images/generations"
                req = urllib.request.Request(url, data=json_data)
                req.add_header("Content-Type", "application/json")
                req.add_header("Authorization", f"Bearer {api_key}")

                print("DEBUG: [THREAD] Sending GPT-Image-1 generation request...")
                if progress_label:
                    update_progress = self._create_progress_callback(progress_label)
                    update_progress("🚀 Sending request to GPT-Image-1...")

                # Send request
                with urllib.request.urlopen(req) as response:
                    response_data = response.read().decode("utf-8")

                # Parse response
                response_json = json.loads(response_data)
                print("DEBUG: [THREAD] GPT-Image-1 API response received")

                if progress_label:
                    update_progress("✅ Processing AI response...")

                # Process the response
                if "data" in response_json and len(response_json["data"]) > 0:
                    result_data = response_json["data"][0]

                    if "b64_json" in result_data:
                        print(
                            "DEBUG: [THREAD] Processing base64 image data from GPT-Image-1"
                        )
                        import base64

                        image_data = base64.b64decode(result_data["b64_json"])
                        print(
                            f"DEBUG: [THREAD] Decoded {len(image_data)} bytes of image data"
                        )

                        # Create layer on main thread via GLib.idle_add
                        layer_created = {"success": False}

                        def create_layer():
                            try:
                                success = self._add_layer_from_data(image, image_data)
                                layer_created["success"] = success
                                return False
                            except Exception as e:
                                print(f"ERROR: [MAIN] Failed to create layer: {e}")
                                layer_created["success"] = False
                                return False

                        GLib.idle_add(create_layer)

                        # Wait for layer creation to complete
                        import time

                        while "success" not in layer_created:
                            time.sleep(0.01)

                        result["success"] = layer_created["success"]
                    else:
                        print("ERROR: [THREAD] No b64_json in GPT-Image-1 response")
                        result["success"] = False
                else:
                    print("ERROR: [THREAD] No data in GPT-Image-1 response")
                    result["success"] = False

            except Exception as e:
                print(f"ERROR: [THREAD] Image generation failed: {e}")
                result["success"] = False
            finally:
                result["completed"] = True

        # Start thread
        thread = threading.Thread(target=generation_thread)
        thread.daemon = True
        thread.start()

        # Keep UI responsive while waiting
        max_wait_time = 400  # 6.7 minutes maximum wait (longer for image generation)
        start_time = time.time()
        last_update_time = start_time

        while not result["completed"]:
            current_time = time.time()
            elapsed = current_time - start_time

            # Update progress every 10 seconds
            if progress_label and current_time - last_update_time > 10:
                minutes = int(elapsed // 60)
                if minutes > 0:
                    self._update_progress(
                        progress_label, f"🎨 Still generating... ({minutes}m elapsed)"
                    )
                else:
                    self._update_progress(progress_label, "🎨 Generating image...")
                last_update_time = current_time

            # Check for cancellation
            if self._check_cancel_and_process_events():
                print("DEBUG: Image generation cancelled by user")
                if progress_label:
                    self._update_progress(
                        progress_label, "❌ Generation cancelled by user"
                    )
                result["success"] = False
                break

            # Check for timeout
            if elapsed > max_wait_time:
                print(
                    f"DEBUG: Image generation thread timeout after {max_wait_time} seconds"
                )
                if progress_label:
                    self._update_progress(progress_label, "❌ Generation timed out")
                result["success"] = False
                break

            # Small sleep to prevent CPU spinning
            time.sleep(0.1)

        # Thread completed, return results
        print(
            f"DEBUG: Threaded image generation completed: success={result['success']}"
        )
        return result["success"]

    def _add_layer_from_data(self, image, image_data):
        """Add image from raw data as a new layer"""
        try:
            import tempfile
            import os

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name

            print(f"DEBUG: Saved image data to: {temp_file_path}")

            try:
                # Load the image as a new layer
                loaded_image = Gimp.file_load(
                    Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(temp_file_path)
                )
                source_layer = loaded_image.get_layers()[0]

                # Copy the layer to the current image
                new_layer = Gimp.Layer.new_from_drawable(source_layer, image)
                new_layer.set_name("GPT-Image Generated")

                # Add the layer to the image
                image.insert_layer(new_layer, None, 0)

                # Clean up
                loaded_image.delete()

                print("DEBUG: Successfully added GPT-Image-1 layer")
                return True

            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except:
                    pass

        except Exception as e:
            print(f"ERROR: Failed to add layer from data: {str(e)}")
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
                new_layer.set_name("GPT-Image Generated")

                # Add the layer to the image
                image.insert_layer(new_layer, None, 0)

                # Clean up
                loaded_image.delete()

                print("DEBUG: Successfully added GPT-Image-1 layer")
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
        print("DEBUG: Image Generator called!")

        # Show prompt dialog with API key checking (no mode selection for image generator)
        dialog_result = self._show_prompt_dialog(
            "Image Generator", "", show_mode_selection=False
        )
        if not dialog_result:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        # Extract dialog, progress_label, prompt and mode from dialog result
        dialog, progress_label, prompt, _ = (
            dialog_result  # Ignore mode for layer generator
        )

        try:
            # Get API key (should be available since dialog handles API key checking)
            api_key = self._get_api_key()
            if not api_key:
                self._update_progress(progress_label, "❌ API key not available")
                Gimp.message("❌ API key not available")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                )

            # Update dialog immediately when processing starts
            self._update_progress(progress_label, "🎨 Generating image with AI...")

            # Use threaded generation to keep UI responsive like other functions
            self._update_progress(progress_label, "🚀 Starting image generation...")

            success, message, image_data = self._call_openai_generation_threaded(
                prompt, api_key, size="auto", progress_label=progress_label
            )
            if success and image_data:
                # Create layer from the generated image data
                layer_success = self._add_layer_from_data(image, image_data)
                result = layer_success
            else:
                # Check if this was a cancellation vs actual failure
                if "cancelled" in message.lower():
                    self._update_progress(progress_label, "❌ Operation cancelled")
                    Gimp.message("❌ Operation cancelled by user")
                else:
                    self._update_progress(
                        progress_label, f"❌ Generation failed: {message}"
                    )
                    Gimp.message(f"❌ Generation failed: {message}")
                result = False
            if result:
                self._update_progress(
                    progress_label, "✅ GPT-Image-1 layer generated successfully!"
                )
                Gimp.message("✅ GPT-Image-1 layer generated successfully!")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS, GLib.Error()
                )
            else:
                # Check if this was a cancellation vs actual failure
                if "cancelled" in message.lower():
                    # For cancellation, return SUCCESS status (user action, not an error)
                    return procedure.new_return_values(
                        Gimp.PDBStatusType.SUCCESS, GLib.Error()
                    )
                else:
                    self._update_progress(
                        progress_label, "❌ Failed to generate GPT-Image-1 layer"
                    )
                    Gimp.message("❌ Failed to generate GPT-Image-1 layer")
                    return procedure.new_return_values(
                        Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
                    )
        except Exception as e:
            error_msg = f"Error generating GPT-Image-1 layer: {str(e)}"
            self._update_progress(progress_label, f"❌ Error: {str(e)}")
            print(f"ERROR: {error_msg}")
            Gimp.message(f"❌ {error_msg}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error()
            )
        finally:
            # Always destroy the dialog
            if dialog:
                dialog.destroy()

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
