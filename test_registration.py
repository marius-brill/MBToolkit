import bpy

# Test script to verify clean_up operator registration
print("Testing MBToolkit registration...")

# Try to find the operator in Blender's registry
operator_id = "mbt.clean_up"
if operator_id in bpy.ops:
    print(f"✓ Operator '{operator_id}' found in bpy.ops")
    
    # Check if it has proper properties
    try:
        op = bpy.ops.mbt.clean_up
        print("✓ Operator callable")
    except Exception as e:
        print(f"✗ Operator not callable: {e}")
else:
    print(f"✗ Operator '{operator_id}' NOT found in bpy.ops")

# Test that the panel is registered properly
panel_id = "MBT_PT_tools"
if panel_id in bpy.types.Panel.__subclasses__():
    print(f"✓ Panel '{panel_id}' found")
else:
    print(f"✗ Panel '{panel_id}' NOT found")

print("Test completed.")