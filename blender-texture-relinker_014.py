bl_info = {
    "name": "Missing Assets Scanner",
    "author": "Assistant",
    "version": (0, 5, 0),
    "blender": (4, 5, 0),
    "location": "View3D > N-Panel > Missing Assets",
    "description": "Scan for missing assets in the current file",
    "category": "Scene",
}

import bpy
import os
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import StringProperty, CollectionProperty

class MissingAssetItem(PropertyGroup):
    """Property group to store missing asset information"""
    name: StringProperty(name="Name")
    type: StringProperty(name="Type")
    path: StringProperty(name="Path")

class MISSING_ASSETS_OT_scan(Operator):
    """Scan for missing assets in the current file"""
    bl_idname = "missing_assets.scan"
    bl_label = "Scan For Missing Assets"
    bl_description = "Scan the current file for missing external assets"
    
    def execute(self, context):
        # Clear previous results
        context.scene.missing_assets_list.clear()
        
        missing_count = 0
        
        # Check for missing images
        for img in bpy.data.images:
            if img.source in {'FILE', 'SEQUENCE', 'MOVIE'}:
                if not img.has_data:
                    item = context.scene.missing_assets_list.add()
                    item.name = img.name
                    item.type = "Image"
                    item.path = img.filepath if img.filepath else "No path"
                    missing_count += 1
        
        # Check for missing libraries
        for lib in bpy.data.libraries:
            if not lib.filepath or not bpy.path.abspath(lib.filepath):
                item = context.scene.missing_assets_list.add()
                item.name = lib.name
                item.type = "Library"
                item.path = lib.filepath if lib.filepath else "No path"
                missing_count += 1
        
        # Check for missing sound files
        for sound in bpy.data.sounds:
            if sound.filepath and not sound.packed_file:
                try:
                    # Try to access the sound data to check if file exists
                    sound.filepath
                except:
                    item = context.scene.missing_assets_list.add()
                    item.name = sound.name
                    item.type = "Sound"
                    item.path = sound.filepath if sound.filepath else "No path"
                    missing_count += 1
        
        # Check for missing cache files
        for obj in bpy.data.objects:
            # Check modifiers
            for mod in obj.modifiers:
                # Mesh Cache modifier
                if mod.type == 'MESH_CACHE' and mod.filepath:
                    try:
                        with open(bpy.path.abspath(mod.filepath), 'r'):
                            pass
                    except:
                        item = context.scene.missing_assets_list.add()
                        item.name = f"{obj.name} - {mod.name}"
                        item.type = "Mesh Cache"
                        item.path = mod.filepath
                        missing_count += 1
                
                # Ocean modifier
                elif mod.type == 'OCEAN' and mod.use_foam and mod.foam_layer_name:
                    if mod.filepath:
                        try:
                            with open(bpy.path.abspath(mod.filepath), 'r'):
                                pass
                        except:
                            item = context.scene.missing_assets_list.add()
                            item.name = f"{obj.name} - {mod.name}"
                            item.type = "Ocean Cache"
                            item.path = mod.filepath
                            missing_count += 1
        
        # Update the count
        context.scene.missing_assets_count = missing_count
        
        if missing_count == 0:
            self.report({'INFO'}, "No missing assets found!")
        else:
            self.report({'WARNING'}, f"Found {missing_count} missing assets")
        
        return {'FINISHED'}

class MISSING_ASSETS_OT_clear_directory(Operator):
    """Clear the directory path"""
    bl_idname = "missing_assets.clear_directory"
    bl_label = "Clear Directory"
    bl_description = "Clear the directory path"
    
    def execute(self, context):
        context.scene.missing_assets_search_directory = ""
        return {'FINISHED'}

class MISSING_ASSETS_OT_relink(Operator):
    """Relink missing assets by searching in the specified directory"""
    bl_idname = "missing_assets.relink"
    bl_label = "Relink Assets"
    bl_description = "Search for and relink missing assets"
    
    _timer = None
    _current_item = 0
    _items_to_process = []
    _relinked_count = 0
    
    @classmethod
    def poll(cls, context):
        # Always allow the operator to be called
        return True
    
    def modal(self, context, event):
        # Check if user wants to cancel
        if context.scene.missing_assets_is_searching and not context.scene.missing_assets_continue_search:
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            if self._current_item < len(self._items_to_process):
                # Process one item
                item = self._items_to_process[self._current_item]
                context.scene.missing_assets_status = f"Searching for: {item['name']}"
                
                # Try to find and relink the asset
                if self.relink_asset(context, item):
                    self._relinked_count += 1
                
                self._current_item += 1
                
                # Update progress AFTER incrementing (so it reaches 100%)
                context.scene.missing_assets_progress = self._current_item / len(self._items_to_process)
                
                # Force UI update
                for area in context.screen.areas:
                    area.tag_redraw()
                
                return {'RUNNING_MODAL'}
            else:
                # Finished processing
                self.finish(context)
                return {'FINISHED'}
        
        return {'PASS_THROUGH'}
    
    def relink_asset(self, context, item):
        """Try to relink a single asset"""
        search_dir = context.scene.missing_assets_search_directory
        if not search_dir or not os.path.exists(search_dir):
            return False
        
        # Get the filename from the path
        filename = os.path.basename(item['path'])
        if not filename or filename == "No path":
            return False
        
        # Search for the file in the directory and subdirectories
        for root, dirs, files in os.walk(search_dir):
            if filename in files:
                new_path = os.path.join(root, filename)
                
                # Relink based on asset type
                if item['type'] == "Image":
                    for img in bpy.data.images:
                        if img.name == item['name']:
                            # Store old path for debugging
                            old_path = img.filepath
                            
                            # Update the filepath
                            img.filepath = new_path
                            
                            # Try multiple reload methods
                            try:
                                img.reload()
                                # Force update
                                img.update()
                                
                                # Verify the image now has data
                                if img.has_data:
                                    print(f"Successfully relinked: {item['name']}")
                                    print(f"  Old path: {old_path}")
                                    print(f"  New path: {new_path}")
                                    return True
                                else:
                                    print(f"Failed to load data for: {item['name']}")
                                    # Revert if unsuccessful
                                    img.filepath = old_path
                            except Exception as e:
                                print(f"Error relinking {item['name']}: {str(e)}")
                                img.filepath = old_path
                            return False
                
                elif item['type'] == "Library":
                    for lib in bpy.data.libraries:
                        if lib.name == item['name']:
                            old_path = lib.filepath
                            lib.filepath = new_path
                            try:
                                lib.reload()
                                print(f"Successfully relinked library: {item['name']}")
                                return True
                            except Exception as e:
                                print(f"Error relinking library {item['name']}: {str(e)}")
                                lib.filepath = old_path
                            return False
                
                elif item['type'] == "Sound":
                    for sound in bpy.data.sounds:
                        if sound.name == item['name']:
                            old_path = sound.filepath
                            sound.filepath = new_path
                            # Sounds don't have a reload method, but update the path
                            sound.update_tag()
                            print(f"Successfully relinked sound: {item['name']}")
                            return True
                
                elif item['type'] == "Mesh Cache":
                    # Extract object and modifier names
                    obj_mod = item['name'].split(' - ')
                    if len(obj_mod) == 2:
                        obj_name, mod_name = obj_mod
                        if obj_name in bpy.data.objects:
                            obj = bpy.data.objects[obj_name]
                            for mod in obj.modifiers:
                                if mod.name == mod_name and mod.type == 'MESH_CACHE':
                                    old_path = mod.filepath
                                    mod.filepath = new_path
                                    # Force modifier update
                                    obj.update_tag()
                                    print(f"Successfully relinked mesh cache: {item['name']}")
                                    return True
        
        print(f"File not found for: {item['name']} (looking for: {filename})")
        return False
    
    def execute(self, context):
        # Check if already searching - if so, stop the search
        if context.scene.missing_assets_is_searching:
            context.scene.missing_assets_continue_search = False
            return {'FINISHED'}
        
        # Clear status
        context.scene.missing_assets_status = "Initializing..."
        
        # Prepare list of items to process
        self._items_to_process = []
        for item in context.scene.missing_assets_list:
            self._items_to_process.append({
                'name': item.name,
                'type': item.type,
                'path': item.path
            })
        
        if not self._items_to_process:
            self.report({'INFO'}, "No missing assets to relink")
            context.scene.missing_assets_status = "No missing assets to relink"
            return {'FINISHED'}
        
        if not context.scene.missing_assets_search_directory:
            self.report({'ERROR'}, "Please specify a search directory")
            context.scene.missing_assets_status = "Error: No search directory specified"
            return {'CANCELLED'}
        
        # Set searching flags
        context.scene.missing_assets_is_searching = True
        context.scene.missing_assets_continue_search = True
        context.scene.missing_assets_progress = 0.0
        
        # Reset counters
        self._current_item = 0
        self._relinked_count = 0
        
        # Add timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def finish(self, context):
        # Remove timer
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        
        # Clear searching flags
        context.scene.missing_assets_is_searching = False
        context.scene.missing_assets_continue_search = False
        context.scene.missing_assets_progress = 0.0
        context.scene.missing_assets_progress = 0.0
        
        # Update status
        context.scene.missing_assets_status = f"Completed: Relinked {self._relinked_count} assets"
        
        # Report results
        self.report({'INFO'}, f"Relinked {self._relinked_count} assets")
        
        # Automatically run scan to update the list
        bpy.ops.missing_assets.scan()
    
    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        
        # Clear searching flags
        context.scene.missing_assets_is_searching = False
        context.scene.missing_assets_continue_search = False
        
        context.scene.missing_assets_status = f"Stopped: Relinked {self._relinked_count} assets"
        self.report({'INFO'}, f"Search stopped. Relinked {self._relinked_count} assets before stopping.")

class MISSING_ASSETS_PT_panel(Panel):
    """Panel in the N-Panel for missing assets scanner"""
    bl_label = "Missing Assets Scanner"
    bl_idname = "MISSING_ASSETS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Missing Assets"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Directory input box
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Search Directory:", icon='FILE_FOLDER')
        
        # Directory path input and clear button
        row = box.row(align=True)
        row.prop(scene, "missing_assets_search_directory", text="")
        row.operator("missing_assets.clear_directory", text="", icon='X', emboss=True)
        
        layout.separator()
        
        # Scan button
        row = layout.row()
        row.scale_y = 1.5
        row.operator("missing_assets.scan", icon='VIEWZOOM')
        
        # Results box with collapsible header
        box = layout.box()
        
        # Header row with expand/collapse toggle
        row = box.row()
        
        # Toggle expand/collapse
        icon = 'DOWNARROW_HLT' if scene.missing_assets_show_details else 'RIGHTARROW'
        row.prop(scene, "missing_assets_show_details", 
                icon=icon, text="", emboss=False)
        
        # Asset count
        if scene.missing_assets_count > 0:
            row.label(text=f"Missing Assets: {scene.missing_assets_count}", icon='ERROR')
        else:
            row.label(text="Missing Assets: 0", icon='CHECKMARK')
        
        # Show detailed list only if expanded
        if scene.missing_assets_show_details:
            if len(scene.missing_assets_list) > 0:
                col = box.column(align=True)
                
                for item in scene.missing_assets_list:
                    # Create a sub-box for each missing asset
                    asset_box = col.box()
                    asset_box.scale_y = 0.8
                    
                    # Asset name and type
                    row = asset_box.row()
                    row.label(text=item.name, icon='DOT')
                    row.label(text=f"[{item.type}]")
                    
                    # Asset path
                    row = asset_box.row()
                    row.scale_y = 0.7
                    row.label(text=f"Path: {item.path}")
                    
                    col.separator(factor=0.5)
            else:
                box.label(text="No scan performed yet or no missing assets found", icon='INFO')
        
        # Relink section - ALWAYS VISIBLE AT THE BOTTOM
        layout.separator()
        
        # Relink button - changes to Stop when searching
        row = layout.row()
        row.scale_y = 1.2
        if scene.missing_assets_is_searching:
            row.operator("missing_assets.relink", text="Stop", icon='CANCEL')
        else:
            row.operator("missing_assets.relink", text="Relink Assets", icon='LINK_BLEND')
        
        # Status box
        status_box = layout.box()
        status_box.scale_y = 0.8
        
        # Show progress bar when searching, otherwise show status text
        if scene.missing_assets_is_searching:
            # Progress bar with percentage and current item
            percent = int(scene.missing_assets_progress * 100)
            status_box.progress(
                factor=scene.missing_assets_progress,
                type="BAR",
                text=f"{scene.missing_assets_status} - {percent}%"
            )
        else:
            # Normal status display
            row = status_box.row()
            row.label(text="Status:", icon='INFO')
            row = status_box.row()
            row.label(text=scene.missing_assets_status)

# Registration
classes = [
    MissingAssetItem,
    MISSING_ASSETS_OT_scan,
    MISSING_ASSETS_OT_clear_directory,
    MISSING_ASSETS_OT_relink,
    MISSING_ASSETS_PT_panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to scene
    bpy.types.Scene.missing_assets_list = CollectionProperty(type=MissingAssetItem)
    bpy.types.Scene.missing_assets_count = bpy.props.IntProperty(default=0)
    bpy.types.Scene.missing_assets_show_details = bpy.props.BoolProperty(
        name="Show Details",
        description="Show/hide detailed missing assets list",
        default=True
    )
    bpy.types.Scene.missing_assets_search_directory = StringProperty(
        name="Directory",
        description="Directory to search for missing assets",
        default="",
        subtype='DIR_PATH'
    )
    bpy.types.Scene.missing_assets_status = StringProperty(
        name="Status",
        description="Current status of the relink operation",
        default="Ready"
    )
    bpy.types.Scene.missing_assets_is_searching = bpy.props.BoolProperty(
        name="Is Searching",
        description="Whether a search is currently in progress",
        default=False
    )
    bpy.types.Scene.missing_assets_continue_search = bpy.props.BoolProperty(
        name="Continue Search",
        description="Flag to control search continuation",
        default=False
    )
    bpy.types.Scene.missing_assets_progress = bpy.props.FloatProperty(
        name="Progress",
        description="Search progress (0.0 to 1.0)",
        default=0.0,
        min=0.0,
        max=1.0
    )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    # Remove properties from scene
    del bpy.types.Scene.missing_assets_list
    del bpy.types.Scene.missing_assets_count
    del bpy.types.Scene.missing_assets_show_details
    del bpy.types.Scene.missing_assets_search_directory
    del bpy.types.Scene.missing_assets_status
    del bpy.types.Scene.missing_assets_is_searching
    del bpy.types.Scene.missing_assets_continue_search
    del bpy.types.Scene.missing_assets_progress

if __name__ == "__main__":
    register()
