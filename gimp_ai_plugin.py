#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GIMP AI Plugin - LLM-powered image editing
A GIMP 3.x plugin that integrates with LLMs for AI-powered image editing tasks
including inpainting, object removal, and image enhancement.

Author: Your Name
License: MIT
"""

import sys
import os
import gi
import base64
import io
import json
import tempfile
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

# Try to import optional dependencies with fallbacks
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

gi.require_version('Gimp', '3.0')
gi.require_version('GimpUi', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('Gegl', '0.4')
gi.require_version('Gio', '2.0')

from gi.repository import Gimp, GimpUi, GLib, Gtk, GdkPixbuf, Gegl, Gio

class GimpAIPlugin(Gimp.PlugIn):
    """Main plugin class for GIMP AI editing functionality"""
    
    def __init__(self):
        super().__init__()
        self.config_file = None
        self.config = {}
        self._load_configuration()
        
    def _load_configuration(self):
        """Load plugin configuration from config file"""
        config_paths = [
            os.path.join(os.path.dirname(__file__), "config.json"),
            os.path.expanduser("~/.config/gimp-ai/config.json"),
            os.path.expanduser("~/.gimp-ai-config.json")
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        self.config = json.load(f)
                    self.config_file = config_path
                    return
                except (json.JSONDecodeError, IOError) as e:
                    Gimp.message(f"Error loading config from {config_path}: {str(e)}")
        
        # Default configuration
        self.config = {
            "api_provider": "openai",
            "openai": {"api_key": "", "model": "gpt-4-vision-preview"},
            "anthropic": {"api_key": "", "model": "claude-3-sonnet-20240229"},
            "settings": {"image_quality": 0.85, "max_image_size": 1024, "timeout": 30}
        }
    
    def _save_configuration(self):
        """Save current configuration to file"""
        if not self.config_file:
            config_dir = os.path.expanduser("~/.config/gimp-ai")
            os.makedirs(config_dir, exist_ok=True)
            self.config_file = os.path.join(config_dir, "config.json")
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except IOError as e:
            Gimp.message(f"Error saving config: {str(e)}")
    
    def _get_api_config(self) -> Dict[str, Any]:
        """Get API configuration for current provider"""
        provider = self.config.get("api_provider", "openai")
        return self.config.get(provider, {})
    
    def _validate_api_config(self, provider: str = None) -> Tuple[bool, str]:
        """Validate API configuration"""
        if not HAS_REQUESTS:
            return False, "Python 'requests' module not available. Please install: pip3 install requests"
            
        if not provider:
            provider = self.config.get("api_provider", "openai")
        
        api_config = self.config.get(provider, {})
        api_key = api_config.get("api_key", "").strip()
        
        if not api_key:
            return False, f"{provider.title()} API key is not configured. Please check settings."
        
        if len(api_key) < 10:
            return False, f"{provider.title()} API key appears to be invalid (too short)."
        
        # Basic format validation
        if provider == "openai" and not api_key.startswith("sk-"):
            return False, "OpenAI API key should start with 'sk-'"
        elif provider == "anthropic" and not api_key.startswith("sk-ant-"):
            return False, "Anthropic API key should start with 'sk-ant-'"
        
        return True, ""
    
    def _validate_image_size(self, width: int, height: int) -> Tuple[bool, str]:
        """Validate image dimensions for API compatibility"""
        max_size = self.config.get("settings", {}).get("max_image_size", 1024)
        min_size = 64
        
        if width < min_size or height < min_size:
            return False, f"Image too small: minimum size is {min_size}x{min_size} pixels"
        
        if width > max_size or height > max_size:
            return False, f"Image too large: maximum size is {max_size}x{max_size} pixels. Adjust in settings."
        
        # Check aspect ratio for some APIs
        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 4:
            return False, "Image aspect ratio too extreme (max 4:1 ratio supported)"
        
        return True, ""
    
    def _validate_selection_bounds(self, bounds: Tuple[int, int, int, int], 
                                 img_width: int, img_height: int) -> Tuple[bool, str]:
        """Validate selection bounds"""
        x1, y1, x2, y2 = bounds
        
        if x1 < 0 or y1 < 0 or x2 > img_width or y2 > img_height:
            return False, "Selection extends beyond image boundaries"
        
        width = x2 - x1
        height = y2 - y1
        
        if width < 10 or height < 10:
            return False, "Selection too small: minimum 10x10 pixels required"
        
        selection_area = width * height
        image_area = img_width * img_height
        
        if selection_area > image_area * 0.8:
            return False, "Selection too large: select a smaller area for better results"
        
        return True, ""
    
    def _validate_prompt(self, prompt: str) -> Tuple[bool, str]:
        """Validate user prompt"""
        if not prompt or not prompt.strip():
            return False, "Prompt cannot be empty"
        
        prompt = prompt.strip()
        
        if len(prompt) < 3:
            return False, "Prompt too short: please provide a more descriptive prompt"
        
        if len(prompt) > 1000:
            return False, "Prompt too long: please keep under 1000 characters"
        
        # Check for potentially problematic content
        problematic_words = ['hack', 'crack', 'exploit', 'virus', 'malware']
        if any(word in prompt.lower() for word in problematic_words):
            return False, "Prompt contains inappropriate content"
        
        return True, ""
    
    def _safe_api_call(self, api_func, *args, **kwargs):
        """Safely execute API call with retry logic and error handling"""
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                result = api_func(*args, **kwargs)
                return result
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    Gimp.message(f"Request timeout, retrying... (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise Exception("Request timed out after multiple attempts")
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    Gimp.message(f"Connection error, retrying... (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                else:
                    raise Exception("Connection failed after multiple attempts")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Network error: {str(e)}")
            except Exception as e:
                if "rate limit" in str(e).lower():
                    if attempt < max_retries - 1:
                        Gimp.message(f"Rate limited, waiting longer... (attempt {attempt + 1}/{max_retries})")
                        import time
                        time.sleep(retry_delay * 2)
                        retry_delay *= 2
                    else:
                        raise Exception("Rate limit exceeded. Please try again later.")
                else:
                    raise
        
        return None
    
    def _image_to_base64(self, image: Gimp.Image, drawable: Gimp.Drawable, 
                        selection_bounds: Optional[Tuple[int, int, int, int]] = None) -> str:
        """Convert GIMP image/drawable to base64 encoded image"""
        try:
            # Create a temporary file for export
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Export the image or selection
            if selection_bounds:
                x1, y1, x2, y2 = selection_bounds
                # Create a new image from selection
                temp_image = Gimp.Image.new(x2 - x1, y2 - y1, image.get_base_type())
                temp_layer = Gimp.Layer.new_from_drawable(drawable, temp_image)
                temp_image.insert_layer(temp_layer, None, 0)
                
                # Copy selection content
                Gimp.get_pdb().run_procedure('gimp-image-crop', [
                    temp_image, x2 - x1, y2 - y1, x1, y1
                ])
                
                # Export temporary image
                Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, temp_image, [temp_layer], 
                             Gio.File.new_for_path(temp_path))
                temp_image.delete()
            else:
                # Export full drawable
                Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, image, [drawable], 
                             Gio.File.new_for_path(temp_path))
            
            # Read and encode file
            with open(temp_path, 'rb') as f:
                image_data = f.read()
            
            # Cleanup
            os.unlink(temp_path)
            
            return base64.b64encode(image_data).decode('utf-8')
            
        except Exception as e:
            Gimp.message(f"Error converting image to base64: {str(e)}")
            return ""
    
    def _base64_to_layer(self, image: Gimp.Image, base64_data: str, 
                        layer_name: str = "AI Generated") -> Optional[Gimp.Layer]:
        """Create a new layer from base64 image data"""
        try:
            # Decode base64 data
            image_data = base64.b64decode(base64_data)
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_file.write(image_data)
                temp_path = temp_file.name
            
            # Load as new image
            loaded_image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, 
                                        Gio.File.new_for_path(temp_path))
            
            if not loaded_image:
                return None
            
            # Get the first layer from loaded image
            layers = loaded_image.get_layers()
            if not layers:
                loaded_image.delete()
                return None
            
            source_layer = layers[0]
            
            # Create new layer in target image
            new_layer = Gimp.Layer.new_from_drawable(source_layer, image)
            new_layer.set_name(layer_name)
            
            # Cleanup
            loaded_image.delete()
            os.unlink(temp_path)
            
            return new_layer
            
        except Exception as e:
            Gimp.message(f"Error creating layer from base64: {str(e)}")
            return None
        
    def do_query_procedures(self):
        """Return list of available procedures"""
        return [
            "gimp-ai-inpaint",
            "gimp-ai-remove-object", 
            "gimp-ai-enhance",
            "gimp-ai-settings"
        ]
    
    def do_set_i18n(self, name):
        """Set internationalization"""
        return False
    
    def do_create_procedure(self, name):
        """Create procedure based on name"""
        if name == "gimp-ai-inpaint":
            return self._create_inpaint_procedure(name)
        elif name == "gimp-ai-remove-object":
            return self._create_remove_object_procedure(name)
        elif name == "gimp-ai-enhance":
            return self._create_enhance_procedure(name)
        elif name == "gimp-ai-settings":
            return self._create_settings_procedure(name)
        return None
    
    def _create_inpaint_procedure(self, name):
        """Create inpainting procedure"""
        procedure = Gimp.ImageProcedure.new(
            self, name,
            Gimp.PDBProcType.PLUGIN,
            self.run_inpaint, None
        )
        
        procedure.set_image_types("RGB*")
        procedure.set_menu_label("AI Inpaint Selection")
        procedure.add_menu_path('<Image>/Filters/AI/')
        procedure.set_documentation(
            "AI-powered inpainting of selected area",
            "Uses AI to intelligently fill selected areas based on surrounding context and optional text prompt",
            name
        )
        procedure.set_attribution("GIMP AI Plugin", "GIMP AI Plugin", "2024")
        
        # Add text prompt parameter
        procedure.add_argument_from_property(self, "prompt")
        
        return procedure
    
    def _create_remove_object_procedure(self, name):
        """Create object removal procedure"""
        procedure = Gimp.ImageProcedure.new(
            self, name,
            Gimp.PDBProcType.PLUGIN,
            self.run_remove_object, None
        )
        
        procedure.set_image_types("RGB*")
        procedure.set_menu_label("AI Remove Object")
        procedure.add_menu_path('<Image>/Filters/AI/')
        procedure.set_documentation(
            "AI-powered object removal",
            "Uses AI to remove selected objects and intelligently fill the background",
            name
        )
        procedure.set_attribution("GIMP AI Plugin", "GIMP AI Plugin", "2024")
        
        return procedure
    
    def _create_enhance_procedure(self, name):
        """Create image enhancement procedure"""
        procedure = Gimp.ImageProcedure.new(
            self, name,
            Gimp.PDBProcType.PLUGIN,
            self.run_enhance, None
        )
        
        procedure.set_image_types("RGB*")
        procedure.set_menu_label("AI Enhance Image")
        procedure.add_menu_path('<Image>/Filters/AI/')
        procedure.set_documentation(
            "AI-powered image enhancement",
            "Uses AI to enhance image quality, colors, and details based on text prompt",
            name
        )
        procedure.set_attribution("GIMP AI Plugin", "GIMP AI Plugin", "2024")
        
        # Add enhancement prompt parameter
        procedure.add_argument_from_property(self, "prompt")
        
        return procedure
    
    def _create_settings_procedure(self, name):
        """Create settings procedure"""
        procedure = Gimp.Procedure.new(
            self, name,
            Gimp.PDBProcType.PLUGIN,
            self.run_settings, None
        )
        
        procedure.set_menu_label("AI Plugin Settings")
        procedure.add_menu_path('<Image>/Filters/AI/')
        procedure.set_documentation(
            "Configure AI plugin settings",
            "Configure API keys, endpoints, and model settings for the AI plugin",
            name
        )
        procedure.set_attribution("GIMP AI Plugin", "GIMP AI Plugin", "2024")
        
        return procedure
    
    def run_inpaint(self, procedure, run_mode, image, drawables, config, run_data):
        """Run inpainting operation"""
        try:
            if not drawables:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error("No drawable selected")
                )
            
            drawable = drawables[0]
            selection = image.get_selection()
            
            # Check if there's a selection
            is_empty, x1, y1, x2, y2 = selection.bounds(image)
            if is_empty:
                Gimp.message("Please make a selection first")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error("No selection made")
                )
            
            # Validate selection bounds
            valid_selection, selection_error = self._validate_selection_bounds(
                (x1, y1, x2, y2), image.get_width(), image.get_height()
            )
            if not valid_selection:
                Gimp.message(selection_error)
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error(selection_error)
                )
            
            # Validate image size
            valid_size, size_error = self._validate_image_size(
                image.get_width(), image.get_height()
            )
            if not valid_size:
                Gimp.message(size_error)
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error(size_error)
                )
            
            # Validate API configuration
            valid_api, api_error = self._validate_api_config()
            if not valid_api:
                Gimp.message(api_error)
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error(api_error)
                )
            
            # Get prompt from user
            prompt = self._get_user_prompt("Describe what should fill this area:")
            if not prompt:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL,
                    GLib.Error()
                )
            
            # Validate prompt
            valid_prompt, prompt_error = self._validate_prompt(prompt)
            if not valid_prompt:
                Gimp.message(prompt_error)
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error(prompt_error)
                )
            
            # Begin undo group for atomic operation
            image.undo_group_start()
            
            try:
                # Create mask from selection for inpainting
                mask_layer = self._create_mask_from_selection(image, (x1, y1, x2, y2))
                if not mask_layer:
                    raise Exception("Failed to create mask from selection")
                
                # Get image data with context around selection
                context_bounds = self._expand_bounds((x1, y1, x2, y2), 
                                                   image.get_width(), image.get_height(), 
                                                   padding=50)
                
                # Convert image and mask to base64 for API call
                image_b64 = self._image_to_base64(image, drawable, context_bounds)
                mask_b64 = self._image_to_base64(image, mask_layer, context_bounds)
                
                if not image_b64 or not mask_b64:
                    raise Exception("Failed to encode image data")
                
                # Call AI API for inpainting with progress updates
                Gimp.progress_init("AI Inpainting...")
                Gimp.progress_set_text("Sending request to AI service...")
                result_b64 = self._safe_api_call(
                    self._call_inpaint_api, image_b64, mask_b64, prompt
                )
                
                if not result_b64:
                    raise Exception("AI API call failed")
                
                # Create new layer with result
                result_layer = self._base64_to_layer(image, result_b64, "AI Inpainted")
                if not result_layer:
                    raise Exception("Failed to create result layer")
                
                # Position and blend the result layer
                result_layer.set_offsets(context_bounds[0], context_bounds[1])
                image.insert_layer(result_layer, None, 0)
                
                # Apply the inpainted content only to selected area
                self._apply_layer_with_selection(image, result_layer, selection)
                
                # Cleanup temporary mask layer
                image.remove_layer(mask_layer)
                
                Gimp.message("AI inpainting completed successfully!")
                image.undo_group_end()
                
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS,
                    GLib.Error()
                )
                
            except Exception as e:
                image.undo_group_end()
                raise e
            
        except Exception as e:
            Gimp.message(f"Error in inpainting: {str(e)}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(e))
            )
    
    def _create_mask_from_selection(self, image: Gimp.Image, 
                                  bounds: Tuple[int, int, int, int]) -> Optional[Gimp.Layer]:
        """Create a mask layer from the current selection"""
        try:
            x1, y1, x2, y2 = bounds
            width, height = x2 - x1, y2 - y1
            
            # Create new layer for mask
            mask_layer = Gimp.Layer.new(image, width, height, 
                                      Gimp.ImageType.RGBA_IMAGE, 
                                      "Selection Mask", 100, 
                                      Gimp.LayerMode.NORMAL)
            
            # Fill with white where selection is, transparent elsewhere
            mask_layer.fill(Gimp.FillType.TRANSPARENT)
            
            # Add layer temporarily
            image.insert_layer(mask_layer, None, 0)
            
            # Set selection as context
            image.get_selection().none(image)
            selection_copy = image.get_selection()
            
            # Fill selected area with white
            Gimp.Context.set_foreground(Gimp.RGB.new_with_uchar(255, 255, 255))
            Gimp.get_pdb().run_procedure('gimp-drawable-edit-bucket-fill', [
                mask_layer, Gimp.FillType.FOREGROUND, x1, y1
            ])
            
            return mask_layer
            
        except Exception as e:
            Gimp.message(f"Error creating mask: {str(e)}")
            return None
    
    def _expand_bounds(self, bounds: Tuple[int, int, int, int], 
                      img_width: int, img_height: int, padding: int = 50) -> Tuple[int, int, int, int]:
        """Expand selection bounds with padding while staying within image bounds"""
        x1, y1, x2, y2 = bounds
        
        new_x1 = max(0, x1 - padding)
        new_y1 = max(0, y1 - padding)
        new_x2 = min(img_width, x2 + padding)
        new_y2 = min(img_height, y2 + padding)
        
        return (new_x1, new_y1, new_x2, new_y2)
    
    def _apply_layer_with_selection(self, image: Gimp.Image, layer: Gimp.Layer, 
                                  selection: Gimp.Selection):
        """Apply layer content only within the selection area"""
        try:
            # Create layer mask from selection
            layer_mask = layer.create_mask(Gimp.AddMaskType.SELECTION)
            layer.add_mask(layer_mask)
            
            # Merge down to apply the effect
            image.merge_down(layer, Gimp.MergeType.EXPAND_AS_NECESSARY)
            
        except Exception as e:
            Gimp.message(f"Error applying layer with selection: {str(e)}")
    
    def _call_inpaint_api(self, image_b64: str, mask_b64: str, prompt: str) -> Optional[str]:
        """Call AI API for inpainting operation"""
        try:
            api_config = self._get_api_config()
            provider = self.config.get("api_provider", "openai")
            
            if provider == "openai":
                return self._call_openai_inpaint(image_b64, mask_b64, prompt, api_config)
            elif provider == "anthropic":
                return self._call_anthropic_inpaint(image_b64, mask_b64, prompt, api_config)
            else:
                Gimp.message(f"Unsupported API provider: {provider}")
                return None
                
        except Exception as e:
            Gimp.message(f"API call error: {str(e)}")
            return None
    
    def _call_openai_inpaint(self, image_b64: str, mask_b64: str, prompt: str, 
                           config: Dict[str, Any]) -> Optional[str]:
        """Call OpenAI API for inpainting"""
        try:
            # Validate API configuration
            valid_config, config_error = self._validate_api_config("openai")
            if not valid_config:
                Gimp.message(config_error)
                return None
            
            api_key = config.get("api_key")
            
            # Convert base64 images to files for OpenAI API
            import tempfile
            import base64
            
            # Create temporary files for image and mask
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as img_file:
                img_file.write(base64.b64decode(image_b64))
                img_path = img_file.name
                
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as mask_file:
                mask_file.write(base64.b64decode(mask_b64))
                mask_path = mask_file.name
            
            # Prepare OpenAI API request
            url = "https://api.openai.com/v1/images/edits"
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            # Open files for upload
            with open(img_path, 'rb') as img_f, open(mask_path, 'rb') as mask_f:
                files = {
                    'image': ('image.png', img_f, 'image/png'),
                    'mask': ('mask.png', mask_f, 'image/png')
                }
                
                data = {
                    'prompt': prompt,
                    'n': 1,
                    'size': '1024x1024',
                    'response_format': 'b64_json'
                }
                
                # Make API request
                response = requests.post(url, headers=headers, files=files, data=data, 
                                       timeout=self.config.get("settings", {}).get("timeout", 30))
            
            # Cleanup temporary files
            os.unlink(img_path)
            os.unlink(mask_path)
            
            if response.status_code == 200:
                result = response.json()
                if 'data' in result and len(result['data']) > 0:
                    return result['data'][0]['b64_json']
                else:
                    Gimp.message("OpenAI API returned no image data")
                    return None
            else:
                error_msg = f"OpenAI API error ({response.status_code})"
                if response.text:
                    try:
                        error_data = response.json()
                        error_msg += f": {error_data.get('error', {}).get('message', response.text)}"
                    except:
                        error_msg += f": {response.text}"
                Gimp.message(error_msg)
                return None
                
        except Exception as e:
            Gimp.message(f"OpenAI API error: {str(e)}")
            return None
    
    def _call_anthropic_inpaint(self, image_b64: str, mask_b64: str, prompt: str,
                              config: Dict[str, Any]) -> Optional[str]:
        """Call Anthropic API for inpainting"""
        try:
            api_key = config.get("api_key")
            model = config.get("model", "claude-3-sonnet-20240229")
            
            if not api_key:
                Gimp.message("Anthropic API key not configured. Please check settings.")
                return None
            
            # Since Claude doesn't directly edit images, we use it to analyze and suggest
            # then potentially call another service or return instructions
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            
            # Create request payload with image analysis
            data = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""I need to inpaint this image with the following prompt: "{prompt}". 
                                The masked area (shown in the mask image) should be filled with content matching the prompt. 
                                Please analyze the image context and provide detailed instructions for what should fill the masked area to create a coherent result.
                                Focus on colors, textures, lighting, and style consistency."""
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64
                                }
                            },
                            {
                                "type": "text",
                                "text": "Here is the mask showing which area to inpaint:"
                            },
                            {
                                "type": "image", 
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": mask_b64
                                }
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(url, headers=headers, json=data, 
                                   timeout=self.config.get("settings", {}).get("timeout", 30))
            
            if response.status_code == 200:
                result = response.json()
                if 'content' in result and len(result['content']) > 0:
                    analysis = result['content'][0]['text']
                    
                    # For now, show Claude's analysis to the user
                    # In a full implementation, this could be used to guide other AI services
                    Gimp.message(f"Claude Analysis: {analysis}")
                    
                    # Since Claude can't generate images directly, suggest using OpenAI
                    Gimp.message("Note: Claude provides analysis but cannot generate images. Consider using OpenAI for actual inpainting.")
                    return None
                else:
                    Gimp.message("Anthropic API returned no content")
                    return None
            else:
                error_msg = f"Anthropic API error ({response.status_code})"
                if response.text:
                    try:
                        error_data = response.json()
                        if 'error' in error_data:
                            error_msg += f": {error_data['error'].get('message', response.text)}"
                        else:
                            error_msg += f": {response.text}"
                    except:
                        error_msg += f": {response.text}"
                Gimp.message(error_msg)
                return None
                
        except Exception as e:
            Gimp.message(f"Anthropic API error: {str(e)}")
            return None
    
    def run_remove_object(self, procedure, run_mode, image, drawables, config, run_data):
        """Run object removal operation"""
        try:
            if not drawables:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error("No drawable selected")
                )
            
            drawable = drawables[0]
            selection = image.get_selection()
            
            # Check if there's a selection
            is_empty, x1, y1, x2, y2 = selection.bounds(image)
            if is_empty:
                Gimp.message("Please select the object to remove first")
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error("No selection made")
                )
            
            # Begin undo group
            image.undo_group_start()
            
            try:
                # Create mask from selection for object removal
                mask_layer = self._create_mask_from_selection(image, (x1, y1, x2, y2))
                if not mask_layer:
                    raise Exception("Failed to create mask from selection")
                
                # Get image context
                context_bounds = self._expand_bounds((x1, y1, x2, y2), 
                                                   image.get_width(), image.get_height(), 
                                                   padding=100)
                
                # Convert to base64
                image_b64 = self._image_to_base64(image, drawable, context_bounds)
                mask_b64 = self._image_to_base64(image, mask_layer, context_bounds)
                
                if not image_b64 or not mask_b64:
                    raise Exception("Failed to encode image data")
                
                # Call AI API for object removal (using inpainting with background prompt)
                Gimp.progress_init("AI Object Removal...")
                removal_prompt = "seamlessly fill this area with background that matches the surrounding environment, removing the selected object completely"
                result_b64 = self._call_inpaint_api(image_b64, mask_b64, removal_prompt)
                
                if not result_b64:
                    raise Exception("AI API call failed")
                
                # Apply result
                result_layer = self._base64_to_layer(image, result_b64, "Object Removed")
                if not result_layer:
                    raise Exception("Failed to create result layer")
                
                result_layer.set_offsets(context_bounds[0], context_bounds[1])
                image.insert_layer(result_layer, None, 0)
                
                self._apply_layer_with_selection(image, result_layer, selection)
                image.remove_layer(mask_layer)
                
                Gimp.message("Object removal completed successfully!")
                image.undo_group_end()
                
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS,
                    GLib.Error()
                )
                
            except Exception as e:
                image.undo_group_end()
                raise e
            
        except Exception as e:
            Gimp.message(f"Error in object removal: {str(e)}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(e))
            )
    
    def run_enhance(self, procedure, run_mode, image, drawables, config, run_data):
        """Run image enhancement operation"""
        try:
            if not drawables:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CALLING_ERROR,
                    GLib.Error("No drawable selected")
                )
            
            drawable = drawables[0]
            
            # Get enhancement prompt from user
            prompt = self._get_user_prompt("Describe how to enhance this image (e.g., 'make colors more vibrant', 'improve lighting', 'increase sharpness'):")
            if not prompt:
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL,
                    GLib.Error()
                )
            
            # Begin undo group
            image.undo_group_start()
            
            try:
                # For enhancement, we work with the whole image or selection
                selection = image.get_selection()
                is_empty, x1, y1, x2, y2 = selection.bounds(image)
                
                if not is_empty:
                    # Work with selection
                    bounds = (x1, y1, x2, y2)
                    context_bounds = self._expand_bounds(bounds, 
                                                       image.get_width(), image.get_height(), 
                                                       padding=20)
                else:
                    # Work with whole image
                    context_bounds = (0, 0, image.get_width(), image.get_height())
                
                # Convert image to base64
                image_b64 = self._image_to_base64(image, drawable, context_bounds)
                if not image_b64:
                    raise Exception("Failed to encode image data")
                
                # Call AI API for enhancement
                Gimp.progress_init("AI Image Enhancement...")
                result_b64 = self._call_enhance_api(image_b64, prompt)
                
                if not result_b64:
                    raise Exception("AI API call failed")
                
                # Create result layer
                result_layer = self._base64_to_layer(image, result_b64, "AI Enhanced")
                if not result_layer:
                    raise Exception("Failed to create result layer")
                
                # Position the layer
                result_layer.set_offsets(context_bounds[0], context_bounds[1])
                image.insert_layer(result_layer, None, 0)
                
                # If there was a selection, apply only to selected area
                if not is_empty:
                    self._apply_layer_with_selection(image, result_layer, selection)
                
                Gimp.message("Image enhancement completed successfully!")
                image.undo_group_end()
                
                return procedure.new_return_values(
                    Gimp.PDBStatusType.SUCCESS,
                    GLib.Error()
                )
                
            except Exception as e:
                image.undo_group_end()
                raise e
            
        except Exception as e:
            Gimp.message(f"Error in image enhancement: {str(e)}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(e))
            )
    
    def _call_enhance_api(self, image_b64: str, prompt: str) -> Optional[str]:
        """Call AI API for image enhancement"""
        try:
            api_config = self._get_api_config()
            provider = self.config.get("api_provider", "openai")
            
            if provider == "openai":
                return self._call_openai_enhance(image_b64, prompt, api_config)
            elif provider == "anthropic":
                return self._call_anthropic_enhance(image_b64, prompt, api_config)
            else:
                Gimp.message(f"Unsupported API provider: {provider}")
                return None
                
        except Exception as e:
            Gimp.message(f"Enhancement API call error: {str(e)}")
            return None
    
    def _call_openai_enhance(self, image_b64: str, prompt: str, 
                           config: Dict[str, Any]) -> Optional[str]:
        """Call OpenAI API for image enhancement"""
        try:
            # OpenAI doesn't have direct enhancement, so we use image generation with prompt
            api_key = config.get("api_key")
            if not api_key:
                Gimp.message("OpenAI API key not configured.")
                return None
            
            # Use image variation or generation based on the original
            # For now, show limitation message
            Gimp.message("OpenAI enhancement: This feature works best with inpainting. Consider using specific editing operations.")
            return None
            
        except Exception as e:
            Gimp.message(f"OpenAI enhancement error: {str(e)}")
            return None
    
    def _call_anthropic_enhance(self, image_b64: str, prompt: str,
                              config: Dict[str, Any]) -> Optional[str]:
        """Call Anthropic API for image enhancement analysis"""
        try:
            api_key = config.get("api_key")
            model = config.get("model", "claude-3-sonnet-20240229")
            
            if not api_key:
                Gimp.message("Anthropic API key not configured.")
                return None
            
            # Use Claude to analyze and provide enhancement suggestions
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            
            data = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Analyze this image and provide specific technical guidance for the enhancement: "{prompt}". 
                                Provide detailed GIMP-specific instructions including:
                                - Specific filters to apply
                                - Color adjustments needed
                                - Curves or levels modifications
                                - Layer blend modes that would help
                                - Specific parameter values when possible
                                Be very specific and actionable."""
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64
                                }
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(url, headers=headers, json=data, 
                                   timeout=self.config.get("settings", {}).get("timeout", 30))
            
            if response.status_code == 200:
                result = response.json()
                if 'content' in result and len(result['content']) > 0:
                    suggestions = result['content'][0]['text']
                    
                    # Show Claude's enhancement suggestions
                    self._show_enhancement_dialog(suggestions)
                    return None
                else:
                    Gimp.message("Anthropic API returned no suggestions")
                    return None
            else:
                Gimp.message(f"Anthropic API error ({response.status_code})")
                return None
                
        except Exception as e:
            Gimp.message(f"Anthropic enhancement error: {str(e)}")
            return None
    
    def _show_enhancement_dialog(self, suggestions: str):
        """Show dialog with enhancement suggestions"""
        dialog = Gtk.Dialog(
            title="AI Enhancement Suggestions",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        
        dialog.add_button("OK", Gtk.ResponseType.OK)
        dialog.set_default_size(500, 400)
        
        content_area = dialog.get_content_area()
        
        # Create scrollable text view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.set_editable(False)
        
        buffer = text_view.get_buffer()
        buffer.set_text(suggestions)
        
        scrolled.add(text_view)
        content_area.pack_start(scrolled, True, True, 10)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()
    
    def run_settings(self, procedure, run_mode, config, run_data):
        """Run settings dialog"""
        try:
            # Show settings dialog
            if self._show_settings_dialog():
                self._save_configuration()
                Gimp.message("Settings saved successfully!")
            
            return procedure.new_return_values(
                Gimp.PDBStatusType.SUCCESS,
                GLib.Error()
            )
            
        except Exception as e:
            Gimp.message(f"Settings error: {str(e)}")
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(e))
            )
    
    def _show_settings_dialog(self) -> bool:
        """Show comprehensive settings dialog"""
        dialog = Gtk.Dialog(
            title="GIMP AI Plugin Settings",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.OK)
        dialog.set_default_size(500, 600)
        
        content_area = dialog.get_content_area()
        
        # Create notebook for tabbed interface
        notebook = Gtk.Notebook()
        content_area.pack_start(notebook, True, True, 10)
        
        # API Provider Tab
        api_page = self._create_api_settings_page()
        api_label = Gtk.Label(label="API Settings")
        notebook.append_page(api_page, api_label)
        
        # General Settings Tab
        general_page = self._create_general_settings_page()
        general_label = Gtk.Label(label="General")
        notebook.append_page(general_page, general_label)
        
        # About Tab
        about_page = self._create_about_page()
        about_label = Gtk.Label(label="About")
        notebook.append_page(about_page, about_label)
        
        dialog.show_all()
        
        response = dialog.run()
        success = response == Gtk.ResponseType.OK
        
        if success:
            # Save settings from dialog
            self._save_settings_from_dialog(dialog)
        
        dialog.destroy()
        
        return success
    
    def _create_api_settings_page(self) -> Gtk.Widget:
        """Create API settings page"""
        vbox = Gtk.VBox(spacing=10)
        vbox.set_margin_left(10)
        vbox.set_margin_right(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        
        # Provider selection
        provider_frame = Gtk.Frame(label="API Provider")
        provider_box = Gtk.VBox(spacing=5)
        provider_box.set_margin_left(10)
        provider_box.set_margin_right(10)
        provider_box.set_margin_top(10)
        provider_box.set_margin_bottom(10)
        
        self.provider_combo = Gtk.ComboBoxText()
        self.provider_combo.append("openai", "OpenAI (DALL-E)")
        self.provider_combo.append("anthropic", "Anthropic (Claude)")
        self.provider_combo.set_active_id(self.config.get("api_provider", "openai"))
        provider_box.pack_start(self.provider_combo, False, False, 0)
        
        provider_frame.add(provider_box)
        vbox.pack_start(provider_frame, False, False, 0)
        
        # OpenAI Settings
        openai_frame = Gtk.Frame(label="OpenAI Settings")
        openai_box = Gtk.VBox(spacing=5)
        openai_box.set_margin_left(10)
        openai_box.set_margin_right(10)
        openai_box.set_margin_top(10)
        openai_box.set_margin_bottom(10)
        
        openai_box.pack_start(Gtk.Label(label="API Key:"), False, False, 0)
        self.openai_key_entry = Gtk.Entry()
        self.openai_key_entry.set_visibility(False)  # Hide password
        self.openai_key_entry.set_text(self.config.get("openai", {}).get("api_key", ""))
        openai_box.pack_start(self.openai_key_entry, False, False, 0)
        
        openai_box.pack_start(Gtk.Label(label="Model:"), False, False, 0)
        self.openai_model_combo = Gtk.ComboBoxText()
        self.openai_model_combo.append("gpt-4-vision-preview", "GPT-4 Vision Preview")
        self.openai_model_combo.append("dall-e-3", "DALL-E 3")
        self.openai_model_combo.set_active_id(self.config.get("openai", {}).get("model", "gpt-4-vision-preview"))
        openai_box.pack_start(self.openai_model_combo, False, False, 0)
        
        openai_frame.add(openai_box)
        vbox.pack_start(openai_frame, False, False, 0)
        
        # Anthropic Settings
        anthropic_frame = Gtk.Frame(label="Anthropic Settings")
        anthropic_box = Gtk.VBox(spacing=5)
        anthropic_box.set_margin_left(10)
        anthropic_box.set_margin_right(10)
        anthropic_box.set_margin_top(10)
        anthropic_box.set_margin_bottom(10)
        
        anthropic_box.pack_start(Gtk.Label(label="API Key:"), False, False, 0)
        self.anthropic_key_entry = Gtk.Entry()
        self.anthropic_key_entry.set_visibility(False)  # Hide password
        self.anthropic_key_entry.set_text(self.config.get("anthropic", {}).get("api_key", ""))
        anthropic_box.pack_start(self.anthropic_key_entry, False, False, 0)
        
        anthropic_box.pack_start(Gtk.Label(label="Model:"), False, False, 0)
        self.anthropic_model_combo = Gtk.ComboBoxText()
        self.anthropic_model_combo.append("claude-3-sonnet-20240229", "Claude 3 Sonnet")
        self.anthropic_model_combo.append("claude-3-haiku-20240307", "Claude 3 Haiku")
        self.anthropic_model_combo.set_active_id(self.config.get("anthropic", {}).get("model", "claude-3-sonnet-20240229"))
        anthropic_box.pack_start(self.anthropic_model_combo, False, False, 0)
        
        anthropic_frame.add(anthropic_box)
        vbox.pack_start(anthropic_frame, False, False, 0)
        
        return vbox
    
    def _create_general_settings_page(self) -> Gtk.Widget:
        """Create general settings page"""
        vbox = Gtk.VBox(spacing=10)
        vbox.set_margin_left(10)
        vbox.set_margin_right(10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        
        # Image Settings
        image_frame = Gtk.Frame(label="Image Settings")
        image_box = Gtk.VBox(spacing=5)
        image_box.set_margin_left(10)
        image_box.set_margin_right(10)
        image_box.set_margin_top(10)
        image_box.set_margin_bottom(10)
        
        # Image Quality
        image_box.pack_start(Gtk.Label(label="Image Quality (0.1-1.0):"), False, False, 0)
        self.quality_adjustment = Gtk.Adjustment(
            value=self.config.get("settings", {}).get("image_quality", 0.85),
            lower=0.1, upper=1.0, step_increment=0.05
        )
        self.quality_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.quality_adjustment)
        self.quality_scale.set_digits(2)
        image_box.pack_start(self.quality_scale, False, False, 0)
        
        # Max Image Size
        image_box.pack_start(Gtk.Label(label="Max Image Size (pixels):"), False, False, 0)
        self.size_adjustment = Gtk.Adjustment(
            value=self.config.get("settings", {}).get("max_image_size", 1024),
            lower=256, upper=2048, step_increment=256
        )
        self.size_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.size_adjustment)
        self.size_scale.set_digits(0)
        image_box.pack_start(self.size_scale, False, False, 0)
        
        image_frame.add(image_box)
        vbox.pack_start(image_frame, False, False, 0)
        
        # Network Settings
        network_frame = Gtk.Frame(label="Network Settings")
        network_box = Gtk.VBox(spacing=5)
        network_box.set_margin_left(10)
        network_box.set_margin_right(10)
        network_box.set_margin_top(10)
        network_box.set_margin_bottom(10)
        
        network_box.pack_start(Gtk.Label(label="Timeout (seconds):"), False, False, 0)
        self.timeout_adjustment = Gtk.Adjustment(
            value=self.config.get("settings", {}).get("timeout", 30),
            lower=10, upper=120, step_increment=5
        )
        self.timeout_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.timeout_adjustment)
        self.timeout_scale.set_digits(0)
        network_box.pack_start(self.timeout_scale, False, False, 0)
        
        network_frame.add(network_box)
        vbox.pack_start(network_frame, False, False, 0)
        
        return vbox
    
    def _create_about_page(self) -> Gtk.Widget:
        """Create about page"""
        vbox = Gtk.VBox(spacing=10)
        vbox.set_margin_left(20)
        vbox.set_margin_right(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        
        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<b><big>GIMP AI Plugin</big></b>")
        vbox.pack_start(title_label, False, False, 0)
        
        # Description
        desc_text = """AI-powered image editing for GIMP 3.x

Features:
• AI Inpainting - Fill selected areas with AI-generated content
• Object Removal - Remove unwanted objects intelligently  
• Image Enhancement - Get AI suggestions for improving images

Supported AI Services:
• OpenAI (DALL-E for image editing)
• Anthropic (Claude for analysis and suggestions)

Version: 1.0.0
License: MIT"""
        
        desc_label = Gtk.Label(label=desc_text)
        desc_label.set_line_wrap(True)
        vbox.pack_start(desc_label, False, False, 0)
        
        # Links
        links_label = Gtk.Label()
        links_label.set_markup('<a href="https://github.com/your-repo/gimp-ai-plugin">GitHub Repository</a>')
        vbox.pack_start(links_label, False, False, 10)
        
        return vbox
    
    def _save_settings_from_dialog(self, dialog):
        """Save settings from dialog widgets"""
        # Update config from dialog
        self.config["api_provider"] = self.provider_combo.get_active_id()
        
        # OpenAI settings
        if "openai" not in self.config:
            self.config["openai"] = {}
        self.config["openai"]["api_key"] = self.openai_key_entry.get_text()
        self.config["openai"]["model"] = self.openai_model_combo.get_active_id()
        
        # Anthropic settings
        if "anthropic" not in self.config:
            self.config["anthropic"] = {}
        self.config["anthropic"]["api_key"] = self.anthropic_key_entry.get_text()
        self.config["anthropic"]["model"] = self.anthropic_model_combo.get_active_id()
        
        # General settings
        if "settings" not in self.config:
            self.config["settings"] = {}
        self.config["settings"]["image_quality"] = self.quality_adjustment.get_value()
        self.config["settings"]["max_image_size"] = int(self.size_adjustment.get_value())
        self.config["settings"]["timeout"] = int(self.timeout_adjustment.get_value())
    
    def _get_user_prompt(self, message: str) -> Optional[str]:
        """Show dialog to get text prompt from user"""
        dialog = Gtk.Dialog(
            title="AI Prompt",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        
        content_area = dialog.get_content_area()
        
        label = Gtk.Label(label=message)
        content_area.pack_start(label, False, False, 10)
        
        entry = Gtk.Entry()
        entry.set_size_request(400, -1)
        content_area.pack_start(entry, False, False, 10)
        
        dialog.show_all()
        
        response = dialog.run()
        text = entry.get_text() if response == Gtk.ResponseType.OK else None
        
        dialog.destroy()
        
        return text

# Entry point
if __name__ == "__main__":
    Gimp.main(GimpAIPlugin.__gtype__, sys.argv)