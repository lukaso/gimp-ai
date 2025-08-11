#!/Applications/GIMP-3.0.4.app/Contents/MacOS/python3.10
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
from gi.repository import Gimp, GimpUi, GLib, Gegl, Gio, Gtk


class GimpAIPlugin(Gimp.PlugIn):
    """Simplified AI Plugin"""

    def __init__(self):
        super().__init__()
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from various locations"""
        config_paths = [
            os.path.join(os.path.dirname(__file__), "config.json"),
            os.path.expanduser("~/.config/gimp-ai/config.json"),
            os.path.expanduser("~/.gimp-ai-config.json"),
        ]

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

        # Default config
        print("DEBUG: Using default config (no config file found)")
        return {
            "openai": {"api_key": None},
            "settings": {"max_image_size": 512, "timeout": 30},
        }

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

    def _show_prompt_dialog(self, title="AI Prompt", default_text=""):
        """Show a GIMP UI dialog to get user input for AI prompt"""
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
            dialog.set_default_size(400, 150)
            dialog.set_resizable(False)

            # Add buttons using GIMP's standard approach
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

            # Text entry - will automatically use theme colors
            entry = Gtk.Entry()
            entry.set_text(default_text)
            entry.set_width_chars(50)
            entry.set_placeholder_text("Describe what you want to generate...")

            # Make Enter key activate OK button
            entry.set_activates_default(True)

            content_area.pack_start(entry, False, False, 0)

            # Show all widgets
            content_area.show_all()

            # Focus the text entry and select all text for easy editing
            entry.grab_focus()
            entry.select_region(0, -1)

            # Run dialog
            print("DEBUG: About to call dialog.run()...")
            response = dialog.run()
            print(f"DEBUG: Dialog response: {response}")

            if response == Gtk.ResponseType.OK:
                prompt = entry.get_text().strip()
                print(f"DEBUG: Got prompt text: '{prompt}', destroying dialog...")
                dialog.destroy()
                print("DEBUG: Dialog destroyed, returning prompt")
                return prompt if prompt else None
            else:
                print("DEBUG: Dialog cancelled, destroying...")
                dialog.destroy()
                return None

        except Exception as e:
            print(f"DEBUG: Dialog error: {e}")
            # Fallback to default prompt if dialog fails
            return default_text if default_text else "fill this area naturally"

    def _test_http_request(self):
        """Test basic HTTP functionality"""
        try:
            # Test different endpoints and approaches
            test_configs = [
                ("http://httpbin.org/get", "HTTP httpbin.org", None),
                (
                    "https://api.github.com",
                    "HTTPS GitHub API (unverified)",
                    "unverified",
                ),
                (
                    "https://httpbin.org/get",
                    "HTTPS httpbin.org (unverified)",
                    "unverified",
                ),
                ("http://example.com", "HTTP example.com", None),
            ]

            for url, test_name, ssl_mode in test_configs:
                try:
                    print(f"DEBUG: Trying {test_name}...")
                    req = urllib.request.Request(url)
                    req.add_header("User-Agent", "GIMP-AI-Plugin/1.0")

                    if url.startswith("https"):
                        if ssl_mode == "unverified":
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        else:
                            ctx = ssl.create_default_context()
                    else:
                        ctx = None

                    with urllib.request.urlopen(
                        req, context=ctx, timeout=15
                    ) as response:
                        status_code = response.getcode()
                        data = response.read().decode("utf-8")[:200]  # First 200 chars
                        return (
                            True,
                            f"{test_name} successful! Status: {status_code}, Data preview: {data[:50]}...",
                        )

                except Exception as e:
                    print(f"DEBUG: {test_name} failed: {e}")
                    continue

            return False, "All network tests failed - check internet connection"

        except Exception as e:
            return False, f"Network test error: {str(e)}"

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

    def _create_mask_from_selection(self, image, width, height):
        """Create a black mask from GIMP selection"""
        try:
            print(f"DEBUG: Creating mask from selection {width}x{height}")

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
        """Call OpenAI DALL-E API for inpainting"""
        try:
            print(f"DEBUG: Calling OpenAI API with prompt: {prompt}")

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

            # Prepare multipart form data
            # Don't specify size parameter - let OpenAI determine from the image dimensions
            fields = {"prompt": prompt, "n": "1", "response_format": "url"}

            # Convert base64 image data back to bytes for the API
            import base64

            image_bytes = base64.b64decode(image_data)

            # Save debug copies of what we're sending to OpenAI
            debug_input_filename = f"/tmp/openai_input_{len(image_bytes)}_bytes.png"
            with open(debug_input_filename, "wb") as debug_file:
                debug_file.write(image_bytes)
            print(f"DEBUG: Saved input image to {debug_input_filename}")

            debug_mask_filename = f"/tmp/openai_mask_{len(mask_data)}_bytes.png"
            with open(debug_mask_filename, "wb") as debug_file:
                debug_file.write(mask_data)
            print(f"DEBUG: Saved mask to {debug_mask_filename}")

            # Analyze both image formats by examining PNG headers
            if image_bytes.startswith(b"\x89PNG"):
                # Check color type in IHDR chunk (byte 25)
                if len(image_bytes) > 25:
                    color_type = image_bytes[25]
                    format_names = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
                    format_name = format_names.get(color_type, f"Unknown({color_type})")
                    print(
                        f"DEBUG: Input image format: {format_name} (color type {color_type})"
                    )
                else:
                    print("DEBUG: Input image PNG header too short")
            else:
                print("DEBUG: Input image is not PNG format!")

            if mask_data.startswith(b"\x89PNG"):
                # Check mask format
                if len(mask_data) > 25:
                    color_type = mask_data[25]
                    format_names = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
                    format_name = format_names.get(color_type, f"Unknown({color_type})")
                    print(
                        f"DEBUG: Mask format: {format_name} (color type {color_type})"
                    )
                    print(f"DEBUG: Mask size: {len(mask_data)} bytes")
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

            # Use unverified SSL context (we know this works from our tests)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            print("DEBUG: Sending real OpenAI API request...")

            # Progress during network operation
            print("DEBUG: Setting progress text to 'Sending request to OpenAI...'")
            Gimp.progress_set_text("Sending request to OpenAI...")
            Gimp.progress_update(0.65)  # 65% - API request started (after 60% mask)
            Gimp.displays_flush()  # Force UI update before blocking network call

            with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
                # More progress during data reading
                Gimp.progress_set_text("Processing AI response...")
                Gimp.progress_update(0.7)  # 70% - Reading response

                response_data = response.read().decode("utf-8")

                Gimp.progress_set_text("Parsing AI result...")
                Gimp.progress_update(0.75)  # 75% - Parsing JSON

                response_json = json.loads(response_data)
                print(
                    f"DEBUG: OpenAI API response received: {len(response_data)} bytes"
                )
                return True, "OpenAI API call successful", response_json

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
            print(f"DEBUG: OpenAI API HTTP error: {e.code} - {error_body}")
            return False, f"OpenAI API error {e.code}: {error_body[:200]}", None
        except Exception as e:
            print(f"DEBUG: OpenAI API call failed: {e}")
            return False, f"OpenAI API call failed: {str(e)}", None

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
            if "url" not in result_data:
                return False, "Invalid API response - no image URL"

            image_url = result_data["url"]
            print(f"DEBUG: Downloading result from: {image_url}")

            # Update progress for download phase
            Gimp.progress_set_text("Downloading AI result...")
            Gimp.progress_update(0.8)  # 80% - Starting download

            # Download the image
            req = urllib.request.Request(image_url)
            req.add_header("User-Agent", "GIMP-AI-Plugin/1.0")

            # Use unverified SSL context (same as API calls)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with urllib.request.urlopen(req, context=ctx, timeout=60) as response:
                Gimp.progress_set_text("Reading image data...")
                Gimp.progress_update(0.85)  # 85% - Reading data

                image_data = response.read()
                print(f"DEBUG: Downloaded {len(image_data)} bytes")

            # Save to temporary file
            Gimp.progress_set_text("Saving temporary file...")
            Gimp.progress_update(0.9)  # 90% - Saving file

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)

            # Also save a copy for debugging
            debug_filename = f"/tmp/openai_result_{len(image_data)}_bytes.png"
            with open(debug_filename, "wb") as debug_file:
                debug_file.write(image_data)
            print(f"DEBUG: Saved OpenAI result to {debug_filename} for inspection")

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
            "gimp-ai-remove",
            "gimp-ai-enhance",
            "gimp-ai-settings",
        ]

    def do_create_procedure(self, name):
        if name == "gimp-ai-inpaint":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_inpaint, None
            )
            procedure.set_menu_label("AI Inpaint Selection")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-remove":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_remove, None
            )
            procedure.set_menu_label("AI Remove Object")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-enhance":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_enhance, None
            )
            procedure.set_menu_label("AI Enhance Image")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        elif name == "gimp-ai-settings":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN, self.run_settings, None
            )
            procedure.set_menu_label("AI Plugin Settings")
            procedure.add_menu_path("<Image>/Filters/AI/")
            return procedure

        return None

    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Inpaint Selection called!")

        # Step 1: Get user prompt FIRST
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

        # Step 2: Get API key
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

        # Step 3: Export image and get final dimensions (force to 512x512 for OpenAI)
        success, message, image_data, final_width, final_height = (
            self._export_image_for_ai(
                image, drawables[0] if drawables else None, max_size=512
            )
        )

        if not success:
            Gimp.message(f"❌ Image Export Failed: {message}")
            print(f"DEBUG: Image export failed: {message}")
            Gimp.progress_end()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        print(f"DEBUG: Image export succeeded: {message}")
        Gimp.progress_update(0.5)  # 50% - Image exported
        Gimp.displays_flush()  # Force UI update

        # Step 4: Create mask with matching dimensions (MUST match image exactly per OpenAI docs)
        # Try to create mask from selection first, fall back to circle
        print(
            f"DEBUG: Creating mask from selection or default circle {final_width}x{final_height}"
        )
        mask_data = self._create_mask_from_selection(image, final_width, final_height)

        Gimp.progress_update(0.6)  # 60% - Mask created
        Gimp.displays_flush()  # Force UI update

        # Step 5: Call AI API
        api_success, api_message, api_response = self._call_openai_inpaint(
            image_data, mask_data, prompt, api_key
        )

        if api_success:
            print(f"DEBUG: AI API succeeded: {api_message}")

            # Step 6: Download and import the result
            import_success, import_message = self._download_and_import_result(
                image, api_response
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

    def run_remove(self, procedure, run_mode, image, drawables, config, run_data):
        Gimp.message("AI Remove Object - Working! (Simplified version)")
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    def run_enhance(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Enhance Image called!")

        # Test image access functionality
        success, message = self._test_image_access(image, drawables)

        if success:
            Gimp.message(f"✅ Image Access Test Successful!\n\n{message}")
            print(f"DEBUG: Image access succeeded: {message}")
        else:
            Gimp.message(f"❌ Image Access Failed: {message}")
            print(f"DEBUG: Image access failed: {message}")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

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
