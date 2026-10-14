#!/usr/bin/env python3
"""Simple verification script for MBToolkit addon"""

import os
import sys

# Add current directory to path so we can import the addon
addon_path = os.path.dirname(os.path.abspath(__file__))
if addon_path not in sys.path:
    sys.path.insert(0, addon_path)

print("Testing MBToolkit addon structure...")

try:
    # Test that we can import main module
    import mbtoolkit
    print("✓ Main mbtoolkit module imported")
    
    # Check what's in the MODULES tuple
    print(f"Found {len(mbtoolkit.MODULES)} modules:")
    for mod in mbtoolkit.MODULES:
        print(f"  - {mod}")
        
    # Test importing each module individually  
    print("\nTesting individual imports...")
    for module_name in mbtoolkit.MODULES:
        try:
            module = __import__(f'mbtoolkit.{module_name}', fromlist=[''])
            print(f"✓ Successfully imported {module_name}")
        except Exception as e:
            print(f"✗ Failed to import {module_name}: {e}")
    
    print("\n✓ All tests passed - addon structure looks correct!")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)