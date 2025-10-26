from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty, EnumProperty

from ..core.networkutils import (
    translate_to_english
)

from ..core.commonutils import (
    draw_wrapped_text_col, draw_title_box, get_all_children, getArmatureMeshes
)

from .common import Tools_SubCategoryPanel

class TRANSLATE_PT_translate_panel(Tools_SubCategoryPanel):
    bl_label = "Translate Tools"
    
    def draw(self, context):
        layout = self.layout
        
        bx = draw_title_box(layout,text='Translate Tools',icon='NETWORK_DRIVE')
        
        if context.active_object: pass
        else:
            draw_wrapped_text_col(bx, text="Select an Object",max_chars=40 , icon='HELP')
            return
            
        text = [
            "This requires Internet Connection!\n",
            "Translator: Google Translate\n\n",
            "This will temporary freeze blender depending how much it will translate.",
            "If entries didn't get translate, try again later as you may have hit Google's limit"
        ]
        draw_wrapped_text_col(bx," ".join(text),alert=True,)
        
        draw_wrapped_text_col(bx,text=f"Active: {context.active_object.name}")   
        op = bx.operator(TRANSLATE_OT_translate_names.bl_idname)

class TRANSLATE_OT_translate_names(Operator):
    bl_idname = "object.translate_names"
    bl_label = "Translate Names to English"
    bl_description = "Translate selected name types to English using Google Translate"
    bl_options = {'REGISTER', 'UNDO'}
    
    translate_types:EnumProperty(
        name="Translate",
        description="Select what to translate",
        items=[
            ('BONES', "Bone Names", "Translate armature bone names"),
            ('SHAPEKEYS', "Shape Key Names", "Translate shape key names"),
            ('OBJECTS', "Object Names", "Translate object names"),
            ('MATERIALS', "Material Names", "Translate material names"),
        ],
        options={'ENUM_FLAG'},
        default={'BONES', 'SHAPEKEYS', 'OBJECTS', 'MATERIALS'}
    )
    
    no_spaces:BoolProperty(
        name="Replace Spaces with Underscore",
        description="Replace spaces with underscores in translated names",
        default=True
    )
    
    include_children:BoolProperty(
        name="Include Child Objects",
        description="Also translate names for all child objects recursively",
        default=True
    )
    
    source_lang:StringProperty(
        name="Source Language",
        description="Source language code (auto for auto-detect)",
        default="auto"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        
        layout.label(text="Translation Options:", icon='WORLD')
        
        box = layout.box()
        col = box.column(align=True)
        col.prop(self, "translate_types")
        
        layout.separator()
        
        col = layout.column(align=True)
        col.prop(self, "no_spaces")
        col.prop(self, "include_children")
        
        layout.separator()
        
        layout.prop(self, "source_lang")
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}
        
        def process_name(name: str) -> str:
            if self.no_spaces:
                return name.replace(' ', '_')
            return name
        
        objects_to_process = [obj]
        
        if self.include_children:
            if obj.type == 'ARMATURE':
                armature_meshes = getArmatureMeshes(obj)
                objects_to_process.extend(armature_meshes)
            
            children = get_all_children(obj)
            objects_to_process.extend(children)
        
        translated_count = 0
        
        for current_obj in objects_to_process:
            if 'BONES' in self.translate_types and current_obj.type == 'ARMATURE':
                bone_names = [bone.name for bone in current_obj.data.bones]
                if bone_names:
                    print(f"Translating {len(bone_names)} bone names...")
                    translated_names = translate_to_english(bone_names, source_lang=self.source_lang)
                    
                    bone_map = {old: process_name(new) for old, new in zip(bone_names, translated_names)}
                    
                    for old_name, new_name in bone_map.items():
                        if old_name != new_name:
                            bone = current_obj.data.bones.get(old_name)
                            if bone:
                                bone.name = new_name
                                translated_count += 1
                
                if hasattr(current_obj.data, 'collections'):
                    collection_names = [col.name for col in current_obj.data.collections]
                    if collection_names:
                        print(f"Translating {len(collection_names)} bone collection names...")
                        translated_names = translate_to_english(collection_names, source_lang=self.source_lang)
                        
                        for col, new_name in zip(current_obj.data.collections, translated_names):
                            new_name = process_name(new_name)
                            if col.name != new_name:
                                col.name = new_name
                                translated_count += 1
            
            if 'SHAPEKEYS' in self.translate_types:
                if current_obj.data and hasattr(current_obj.data, 'shape_keys') and current_obj.data.shape_keys:
                    key_blocks = current_obj.data.shape_keys.key_blocks
                    shapekey_names = [kb.name for kb in key_blocks]
                    
                    if shapekey_names:
                        print(f"Translating {len(shapekey_names)} shape key names...")
                        translated_names = translate_to_english(shapekey_names, source_lang=self.source_lang)
                        
                        for kb, new_name in zip(key_blocks, translated_names):
                            new_name = process_name(new_name)
                            if kb.name != new_name:
                                kb.name = new_name
                                translated_count += 1
            
            if 'OBJECTS' in self.translate_types:
                names_to_translate = [current_obj.name]
                if current_obj.data and hasattr(current_obj.data, 'name'):
                    names_to_translate.append(current_obj.data.name)
                
                print(f"Translating object names...")
                translated_names = translate_to_english(names_to_translate, source_lang=self.source_lang)
                
                new_obj_name = process_name(translated_names[0])
                if current_obj.name != new_obj_name:
                    current_obj.name = new_obj_name
                    translated_count += 1
                
                if len(translated_names) > 1 and current_obj.data and hasattr(current_obj.data, 'name'):
                    new_data_name = process_name(translated_names[1])
                    if current_obj.data.name != new_data_name:
                        current_obj.data.name = new_data_name
                        translated_count += 1
            
            if 'MATERIALS' in self.translate_types:
                if current_obj.data and hasattr(current_obj.data, 'materials'):
                    materials = [mat for mat in current_obj.data.materials if mat]
                    material_names = [mat.name for mat in materials]
                    
                    if material_names:
                        print(f"Translating {len(material_names)} material names...")
                        translated_names = translate_to_english(material_names, source_lang=self.source_lang)
                        
                        for mat, new_name in zip(materials, translated_names):
                            new_name = process_name(new_name)
                            if mat.name != new_name:
                                mat.name = new_name
                                translated_count += 1
        
        self.report({'INFO'}, f"Translation complete! {translated_count} names updated")
        return {'FINISHED'}