#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Minimal GIMP AI Plugin test - just to check loading
"""

import sys
import gi

gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, GLib

class TestAIPlugin(Gimp.PlugIn):
    """Minimal test plugin"""
    
    def do_query_procedures(self):
        """Return list of available procedures"""
        return ["test-ai-plugin"]
    
    def do_set_i18n(self, name):
        """Set internationalization"""
        return False
    
    def do_create_procedure(self, name):
        """Create procedure based on name"""
        if name == "test-ai-plugin":
            procedure = Gimp.ImageProcedure.new(
                self, name,
                Gimp.PDBProcType.PLUGIN,
                self.run_test, None
            )
            
            procedure.set_image_types("*")
            procedure.set_menu_label("Test AI Plugin")
            procedure.add_menu_path('<Image>/Filters/AI/')
            procedure.set_documentation(
                "Test AI plugin loading",
                "Simple test to see if AI menu appears",
                name
            )
            procedure.set_attribution("Test", "Test", "2024")
            
            return procedure
        return None
    
    def run_test(self, procedure, run_mode, image, drawables, config, run_data):
        """Run test operation"""
        try:
            Gimp.message("Test AI plugin is working!")
            return procedure.new_return_values(
                Gimp.PDBStatusType.SUCCESS,
                GLib.Error()
            )
        except Exception as e:
            return procedure.new_return_values(
                Gimp.PDBStatusType.EXECUTION_ERROR,
                GLib.Error(str(e))
            )

# Entry point
if __name__ == "__main__":
    Gimp.main(TestAIPlugin.__gtype__, sys.argv)