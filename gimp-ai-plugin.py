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
import ssl
import base64
import tempfile

gi.require_version('Gimp', '3.0')
gi.require_version('Gegl', '0.4')
gi.require_version('Gio', '2.0')
from gi.repository import Gimp, GLib, Gegl, Gio

class GimpAIPlugin(Gimp.PlugIn):
    """Simplified AI Plugin"""
    
    def _test_http_request(self):
        """Test basic HTTP functionality"""
        try:
            # Test different endpoints and approaches
            test_configs = [
                ("http://httpbin.org/get", "HTTP httpbin.org", None),
                ("https://api.github.com", "HTTPS GitHub API (unverified)", "unverified"),
                ("https://httpbin.org/get", "HTTPS httpbin.org (unverified)", "unverified"),
                ("http://example.com", "HTTP example.com", None)
            ]
            
            for url, test_name, ssl_mode in test_configs:
                try:
                    print(f"DEBUG: Trying {test_name}...")
                    req = urllib.request.Request(url)
                    req.add_header('User-Agent', 'GIMP-AI-Plugin/1.0')
                    
                    if url.startswith('https'):
                        if ssl_mode == "unverified":
                            ctx = ssl.create_default_context()
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        else:
                            ctx = ssl.create_default_context()
                    else:
                        ctx = None
                    
                    with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                        status_code = response.getcode()
                        data = response.read().decode('utf-8')[:200]  # First 200 chars
                        return True, f"{test_name} successful! Status: {status_code}, Data preview: {data[:50]}..."
                        
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
            drawable_name = drawable.get_name() if hasattr(drawable, 'get_name') else "Unknown"
            
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
            
            # Create a temporary image copy for export
            temp_image = image.duplicate()
            
            # Get the active layer from the temp image
            layers = temp_image.get_layers()
            if not layers or len(layers) == 0:
                return False, "No layers found in image", None
            temp_drawable = layers[0]  # Use first layer
            
            # Get dimensions
            width = temp_image.get_width()
            height = temp_image.get_height()
            
            # Resize if too large
            if width > max_size or height > max_size:
                scale_factor = min(max_size / width, max_size / height)
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                
                print(f"DEBUG: Resizing from {width}x{height} to {new_width}x{new_height}")
                temp_image.scale(new_width, new_height)
            
            # Export to temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_filename = temp_file.name
            
            try:
                # Use GIMP's export function (GIMP 3.x style)
                print(f"DEBUG: Attempting to export to {temp_filename}")
                
                # Try different export approaches for GIMP 3.x
                export_success = False
                
                # Simple approach: just create a basic PNG using standard Python
                try:
                    # Method 1: Use GEGL buffer to export directly
                    print("DEBUG: Trying GEGL buffer export")
                    buffer = temp_drawable.get_buffer()
                    
                    # Create a simple PNG using Python imaging (basic approach)
                    # For now, let's create a mock PNG file to test the rest of the pipeline
                    print("DEBUG: Creating mock PNG file for testing")
                    
                    # Write a minimal valid PNG file (1x1 pixel for testing)
                    # PNG signature + IHDR + IDAT + IEND
                    mock_png_data = (
                        b'\x89PNG\r\n\x1a\n'  # PNG signature
                        b'\x00\x00\x00\rIHDR'  # IHDR chunk
                        b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'  # 1x1 RGB
                        b'\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xdd\x8d\xb4\x1c'  # IDAT
                        b'\x00\x00\x00\x00IEND\xae B`\x82'  # IEND
                    )
                    
                    with open(temp_filename, 'wb') as f:
                        f.write(mock_png_data)
                    
                    export_success = True
                    print("DEBUG: Mock PNG created successfully")
                    
                except Exception as e:
                    print(f"DEBUG: Mock PNG creation failed: {e}")
                    return False, f"PNG creation failed: {e}", None
                
                print(f"DEBUG: Export success: {export_success}")
                if not export_success:
                    return False, "Export to PNG failed", None
                
                # Read the exported file and encode to base64
                with open(temp_filename, 'rb') as f:
                    png_data = f.read()
                
                base64_data = base64.b64encode(png_data).decode('utf-8')
                
                # Clean up
                os.unlink(temp_filename)
                temp_image.delete()
                
                info = f"Exported {len(png_data)} bytes as PNG, base64 length: {len(base64_data)}"
                return True, info, base64_data
                
            except Exception as e:
                # Clean up on error
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
                return False, f"Export process failed: {str(e)}", None
                
        except Exception as e:
            return False, f"Image export error: {str(e)}", None
    
    def do_query_procedures(self):
        return ["gimp-ai-inpaint", "gimp-ai-remove", "gimp-ai-enhance", "gimp-ai-settings"]
    
    def do_create_procedure(self, name):
        if name == "gimp-ai-inpaint":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN,
                self.run_inpaint, None
            )
            procedure.set_menu_label("AI Inpaint Selection")
            procedure.add_menu_path('<Image>/Filters/AI/')
            return procedure
        
        elif name == "gimp-ai-remove":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN,
                self.run_remove, None
            )
            procedure.set_menu_label("AI Remove Object")
            procedure.add_menu_path('<Image>/Filters/AI/')
            return procedure
        
        elif name == "gimp-ai-enhance":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN,
                self.run_enhance, None
            )
            procedure.set_menu_label("AI Enhance Image")
            procedure.add_menu_path('<Image>/Filters/AI/')
            return procedure
        
        elif name == "gimp-ai-settings":
            procedure = Gimp.ImageProcedure.new(
                self, name, Gimp.PDBProcType.PLUGIN,
                self.run_settings, None
            )
            procedure.set_menu_label("AI Plugin Settings")
            procedure.add_menu_path('<Image>/Filters/AI/')
            return procedure
        
        return None
    
    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        print("DEBUG: AI Inpaint Selection called!")
        
        # Test image export functionality
        success, message, base64_data = self._export_image_for_ai(image, drawables[0] if drawables else None)
        
        if success:
            # Show first 100 chars of base64 data as preview
            preview = base64_data[:100] + "..." if len(base64_data) > 100 else base64_data
            full_message = f"✅ Image Export Successful!\n\n{message}\n\nBase64 preview: {preview}"
            Gimp.message(full_message)
            print(f"DEBUG: Image export succeeded: {message}")
        else:
            Gimp.message(f"❌ Image Export Failed: {message}")
            print(f"DEBUG: Image export failed: {message}")
        
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