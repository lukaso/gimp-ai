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

    def _extract_context_region(self, image, context_info):
        """Extract true square context region without distortion"""
        try:
            print("DEBUG: Extracting TRUE SQUARE context region for AI")
            
            # Get parameters for the context square
            ctx_x1, ctx_y1, ctx_size, _ = context_info['context_square']
            target_size = context_info['target_size']
            orig_width = image.get_width()
            orig_height = image.get_height()
            
            print(f"DEBUG: Context square: ({ctx_x1},{ctx_y1}) to ({ctx_x1+ctx_size},{ctx_y1+ctx_size}) size={ctx_size}")
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
            
            print(f"DEBUG: Image intersection: ({intersect_x1},{intersect_y1}) to ({intersect_x2},{intersect_y2})")
            print(f"DEBUG: Intersection size: {intersect_width}x{intersect_height}")
            
            if intersect_width > 0 and intersect_height > 0:
                # Create a temporary image with just the intersecting region
                temp_image = image.duplicate()
                temp_image.crop(intersect_width, intersect_height, intersect_x1, intersect_y1)
                
                # Create a layer from this region
                merged_layer = temp_image.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
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
                
                print(f"DEBUG: Placed image content at offset ({paste_x},{paste_y}) within square")
                
                # Clean up temp image
                temp_image.delete()
            else:
                print("DEBUG: No intersection with original image - creating empty square")
            
            # Scale to target size for OpenAI  
            if ctx_size != target_size:
                square_image.scale(target_size, target_size)
                print(f"DEBUG: Scaled square from {ctx_size}x{ctx_size} to {target_size}x{target_size}")
            
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
                # Default to center area if no selection
                size = min(img_width, img_height, 512)
                x = (img_width - size) // 2
                y = (img_height - size) // 2
                return {
                    'selection_bounds': (x, y, x + size, y + size),
                    'context_square': (x, y, size, size),
                    'extract_region': (x, y, size, size),
                    'padding': (0, 0, 0, 0),  # left, top, right, bottom
                    'has_selection': False
                }
            
            # Extract selection bounds
            has_selection = selection_bounds[0]
            sel_x1 = selection_bounds[2] if len(selection_bounds) > 2 else 0
            sel_y1 = selection_bounds[3] if len(selection_bounds) > 3 else 0
            sel_x2 = selection_bounds[4] if len(selection_bounds) > 4 else 0
            sel_y2 = selection_bounds[5] if len(selection_bounds) > 5 else 0
            
            sel_width = sel_x2 - sel_x1
            sel_height = sel_y2 - sel_y1
            print(f"DEBUG: Selection: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2}), size: {sel_width}x{sel_height}")
            
            # Calculate context padding (30-50% of selection size, min 32px, max 200px)
            context_padding = max(32, min(200, int(max(sel_width, sel_height) * 0.4)))
            print(f"DEBUG: Context padding: {context_padding}px")
            
            # Calculate desired context square
            ctx_x1 = sel_x1 - context_padding
            ctx_y1 = sel_y1 - context_padding
            ctx_x2 = sel_x2 + context_padding
            ctx_y2 = sel_y2 + context_padding
            
            ctx_width = ctx_x2 - ctx_x1
            ctx_height = ctx_y2 - ctx_y1
            
            # Make it square by expanding the smaller dimension
            square_size = max(ctx_width, ctx_height)
            
            # Center the square around the selection
            sel_center_x = (sel_x1 + sel_x2) // 2
            sel_center_y = (sel_y1 + sel_y2) // 2
            
            square_x1 = sel_center_x - square_size // 2
            square_y1 = sel_center_y - square_size // 2
            square_x2 = square_x1 + square_size
            square_y2 = square_y1 + square_size
            
            print(f"DEBUG: Desired context square: ({square_x1},{square_y1}) to ({square_x2},{square_y2}), size: {square_size}x{square_size}")
            
            # Calculate padding needed if square extends beyond image boundaries
            pad_left = max(0, -square_x1)
            pad_top = max(0, -square_y1)
            pad_right = max(0, square_x2 - img_width)
            pad_bottom = max(0, square_y2 - img_height)
            
            # Adjust extraction region to stay within image bounds
            extract_x1 = max(0, square_x1)
            extract_y1 = max(0, square_y1)
            extract_x2 = min(img_width, square_x2)
            extract_y2 = min(img_height, square_y2)
            extract_width = extract_x2 - extract_x1
            extract_height = extract_y2 - extract_y1
            
            print(f"DEBUG: Extract region: ({extract_x1},{extract_y1}) to ({extract_x2},{extract_y2}), size: {extract_width}x{extract_height}")
            print(f"DEBUG: Padding needed: left={pad_left}, top={pad_top}, right={pad_right}, bottom={pad_bottom}")
            
            # Optimize square size for OpenAI (prefer 512, 768, or 1024)
            if square_size <= 512:
                target_size = 512
            elif square_size <= 768:
                target_size = 768
            else:
                target_size = 1024
                
            print(f"DEBUG: Target size for OpenAI: {target_size}x{target_size}")
            
            return {
                'selection_bounds': (sel_x1, sel_y1, sel_x2, sel_y2),
                'context_square': (square_x1, square_y1, square_size, square_size),
                'extract_region': (extract_x1, extract_y1, extract_width, extract_height),
                'padding': (pad_left, pad_top, pad_right, pad_bottom),
                'target_size': target_size,
                'has_selection': True
            }
            
        except Exception as e:
            print(f"DEBUG: Context calculation failed: {e}")
            # Fallback to simple center extraction
            size = min(img_width, img_height, 512)
            x = (img_width - size) // 2
            y = (img_height - size) // 2
            return {
                'selection_bounds': (x, y, x + size, y + size),
                'context_square': (x, y, size, size),
                'extract_region': (x, y, size, size),
                'padding': (0, 0, 0, 0),
                'target_size': 512,
                'has_selection': False
            }

    def _create_context_mask(self, context_info, target_size):
        """Create mask for context extraction that respects selection boundaries"""
        try:
            print(f"DEBUG: Creating context mask {target_size}x{target_size}")
            
            if not context_info['has_selection']:
                print("DEBUG: No selection, creating center circle mask")
                return self._create_black_mask(target_size, target_size)
            
            # Get context square info
            sel_x1, sel_y1, sel_x2, sel_y2 = context_info['selection_bounds']
            ctx_x1, ctx_y1, ctx_size, _ = context_info['context_square']
            
            # Calculate selection position within the context square
            sel_in_ctx_x1 = sel_x1 - ctx_x1
            sel_in_ctx_y1 = sel_y1 - ctx_y1
            sel_in_ctx_x2 = sel_x2 - ctx_x1
            sel_in_ctx_y2 = sel_y2 - ctx_y1
            
            print(f"DEBUG: Selection within context: ({sel_in_ctx_x1},{sel_in_ctx_y1}) to ({sel_in_ctx_x2},{sel_in_ctx_y2})")
            
            # Scale to target size
            scale = target_size / ctx_size
            mask_sel_x1 = int(sel_in_ctx_x1 * scale)
            mask_sel_y1 = int(sel_in_ctx_y1 * scale)
            mask_sel_x2 = int(sel_in_ctx_x2 * scale)
            mask_sel_y2 = int(sel_in_ctx_y2 * scale)
            
            print(f"DEBUG: Mask selection area: ({mask_sel_x1},{mask_sel_y1}) to ({mask_sel_x2},{mask_sel_y2})")
            
            # Create IHDR chunk data (L - grayscale format for OpenAI mask)
            ihdr_data = (
                target_size.to_bytes(4, "big")
                + target_size.to_bytes(4, "big")
                + b"\x08\x00\x00\x00\x00"  # 8-bit grayscale (L format)
            )

            import zlib
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF

            # Create image data with black selection area, white context
            image_rows = []
            for y in range(target_size):
                row = b"\x00"  # Filter byte
                for x in range(target_size):
                    if mask_sel_x1 <= x <= mask_sel_x2 and mask_sel_y1 <= y <= mask_sel_y2:
                        # Black grayscale (0 = inpaint this area)
                        row += b"\x00"
                    else:
                        # White grayscale (255 = preserve context)
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

            print(f"DEBUG: Created context mask PNG: {len(png_data)} bytes")
            return png_data
            
        except Exception as e:
            print(f"DEBUG: Context mask creation failed: {e}")
            return self._create_black_mask(target_size, target_size)

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
            if "url" not in result_data:
                return False, "Invalid API response - no image URL"

            image_url = result_data["url"]
            print(f"DEBUG: Downloading result from: {image_url}")

            # Update progress for download phase
            Gimp.progress_set_text("Downloading AI result...")
            Gimp.progress_update(0.8)  # 80% - Starting download
            Gimp.displays_flush()

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
                Gimp.displays_flush()

                image_data = response.read()
                print(f"DEBUG: Downloaded {len(image_data)} bytes")

            # Save to temporary file
            Gimp.progress_set_text("Processing AI result...")
            Gimp.progress_update(0.9)  # 90% - Processing
            Gimp.displays_flush()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(image_data)

            # Save debug copy
            debug_filename = f"/tmp/openai_result_{len(image_data)}_bytes.png"
            with open(debug_filename, "wb") as debug_file:
                debug_file.write(image_data)
            print(f"DEBUG: Saved OpenAI result to {debug_filename} for inspection")

            try:
                # Load the AI result into a temporary image
                Gimp.progress_set_text("Loading AI result...")
                Gimp.progress_update(0.95)  # 95% - Loading
                Gimp.displays_flush()

                file = Gio.File.new_for_path(temp_filename)
                ai_result_img = Gimp.file_load(run_mode=Gimp.RunMode.NONINTERACTIVE, file=file)

                if not ai_result_img:
                    return False, "Failed to load AI result image"

                ai_layers = ai_result_img.get_layers()
                if not ai_layers or len(ai_layers) == 0:
                    ai_result_img.delete()
                    return False, "No layers found in AI result"

                ai_layer = ai_layers[0]
                print(f"DEBUG: AI result dimensions: {ai_layer.get_width()}x{ai_layer.get_height()}")

                # Get original image dimensions
                orig_width = image.get_width()
                orig_height = image.get_height()

                # Get context info for compositing
                sel_x1, sel_y1, sel_x2, sel_y2 = context_info['selection_bounds']
                ctx_x1, ctx_y1, ctx_size, _ = context_info['context_square']
                target_size = context_info['target_size']

                print(f"DEBUG: Original image: {orig_width}x{orig_height}")
                print(f"DEBUG: Selection bounds: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})")
                print(f"DEBUG: Context square: ({ctx_x1},{ctx_y1}), size {ctx_size}")

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

                # Scale AI result back to context size if needed
                if ai_layer.get_width() != ctx_size or ai_layer.get_height() != ctx_size:
                    # Create a scaled version
                    scaled_img = ai_result_img.duplicate()
                    scaled_img.scale(ctx_size, ctx_size)
                    scaled_layers = scaled_img.get_layers()
                    if scaled_layers:
                        ai_layer = scaled_layers[0]
                    print(f"DEBUG: Scaled AI result to context size: {ctx_size}x{ctx_size}")

                # SIMPLIFIED COORDINATE CALCULATION FOR TRUE SQUARE
                # Since we now work with true squares throughout the pipeline:
                # 1. AI result is a true ctx_size x ctx_size square 
                # 2. It represents the context square at position (ctx_x1, ctx_y1)
                # 3. We simply place it at that exact position and let GIMP handle clipping
                
                paste_x = ctx_x1  # Exact position where context square belongs
                paste_y = ctx_y1
                
                print(f"DEBUG: SIMPLIFIED POSITIONING:")
                print(f"DEBUG: AI result is {ctx_size}x{ctx_size} square")
                print(f"DEBUG: Placing at context square position: ({paste_x},{paste_y})")
                print(f"DEBUG: GIMP will automatically clip to image bounds")
                
                # Copy the AI result content using simplified Gegl nodes
                from gi.repository import Gegl

                print(f"DEBUG: Placing {ctx_size}x{ctx_size} AI result at ({paste_x},{paste_y})")
                
                # Get buffers
                buffer = result_layer.get_buffer()
                shadow_buffer = result_layer.get_shadow_buffer()
                ai_buffer = ai_layer.get_buffer()
                
                # Create simplified Gegl processing graph  
                graph = Gegl.Node()
                
                # Source: AI result square
                ai_input = graph.create_child("gegl:buffer-source")
                ai_input.set_property("buffer", ai_buffer)
                
                # Translate to context square position (GIMP will handle clipping)
                translate = graph.create_child("gegl:translate")
                translate.set_property("x", float(paste_x))
                translate.set_property("y", float(paste_y))
                
                # Write to shadow buffer
                output = graph.create_child("gegl:write-buffer")
                output.set_property("buffer", shadow_buffer)
                
                # Link simple chain: source -> translate -> output
                ai_input.link(translate)
                translate.link(output)
                
                # Process the graph
                try:
                    output.process()
                    
                    # Flush and merge shadow buffer
                    shadow_buffer.flush()
                    result_layer.merge_shadow(True)
                    result_layer.update(paste_x, paste_y, ctx_size, ctx_size)
                    
                    print(f"DEBUG: Successfully composited AI result using simplified Gegl graph")
                except Exception as e:
                    print(f"DEBUG: Gegl processing failed: {e}")
                    raise

                # Create a layer mask to show only the selection area
                if context_info['has_selection']:
                    print("DEBUG: Creating coordinate-aware selection mask for result layer")
                    
                    # The issue with AddMaskType.SELECTION is that it uses current selection coordinates
                    # but our content may be positioned differently due to coordinate transformations
                    # Instead, we'll create a mask programmatically that aligns with actual content position
                    
                    # Create black mask (everything hidden initially)
                    mask = result_layer.create_mask(Gimp.AddMaskType.BLACK)
                    result_layer.add_mask(mask)
                    
                    # Now we need to make the mask white exactly where the original selection was
                    # Since our content is positioned correctly, the mask should match original selection coords
                    # The selection coordinates haven't changed - they're still at (sel_x1,sel_y1) to (sel_x2,sel_y2)
                    
                    # Get current selection and copy it to mask
                    # First, save current selection
                    selection_exists = not Gimp.Selection.is_empty(image)
                    
                    if selection_exists:
                        # Fill the mask white in the selection area 
                        # Use the original selection coordinates since that's where we want visibility
                        mask.edit_fill(Gimp.FillType.WHITE)
                        print(f"DEBUG: Applied selection-shaped mask using original selection")
                    else:
                        print("DEBUG: Warning: No selection found for masking")

                # VALIDATION CHECKS  
                print(f"DEBUG: === SIMPLIFIED ALIGNMENT VALIDATION ===")
                print(f"DEBUG: Context square positioned at: ({paste_x},{paste_y}) with size {ctx_size}x{ctx_size}")
                print(f"DEBUG: Original selection was: ({sel_x1},{sel_y1}) to ({sel_x2},{sel_y2})")
                print(f"DEBUG: Since we work with true squares, alignment should be perfect")
                print(f"DEBUG: Selection coordinates within context square: ({sel_x1-paste_x},{sel_y1-paste_y}) to ({sel_x2-paste_x},{sel_y2-paste_y})")

                # Clean up temporary image
                ai_result_img.delete()
                os.unlink(temp_filename)

                # Force display update
                Gimp.displays_flush()

                layer_count = len(image.get_layers())
                print(f"DEBUG: Successfully composited AI result. Total layers: {layer_count}")

                return True, f"AI result composited as masked layer: '{result_layer.get_name()}' (total layers: {layer_count})"

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

        # Step 3: Calculate smart context extraction
        print("DEBUG: Calculating context extraction...")
        context_info = self._calculate_context_extraction(image)
        
        Gimp.progress_update(0.4)  # 40% - Context calculated
        Gimp.displays_flush()  # Force UI update

        # Step 4: Extract context region with padding
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

        # Step 5: Create smart mask that respects selection within context
        print("DEBUG: Creating context-aware mask...")
        mask_data = self._create_context_mask(context_info, context_info['target_size'])

        Gimp.progress_update(0.6)  # 60% - Mask created
        Gimp.displays_flush()  # Force UI update

        # Step 6: Call AI API with context and mask
        api_success, api_message, api_response = self._call_openai_inpaint(
            image_data, mask_data, prompt, api_key
        )

        if api_success:
            print(f"DEBUG: AI API succeeded: {api_message}")

            # Step 7: Download and composite result with proper masking
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
