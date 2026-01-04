import bpy
from bpy.types import Operator, Context, Event, UILayout
from bpy.props import BoolProperty, StringProperty, EnumProperty

from ..core.networkutils import (
    translate_string
)

from ..core.commonutils import (
    draw_wrapped_texts, draw_title_box_layout, get_all_child_objects, get_armature_meshes, draw_toggleable_layout
)

from ..core.objectutils import (
    apply_object_transforms
)

from .common import Tools_SubCategoryPanel

class OBJECT_PT_Translate_Panel(Tools_SubCategoryPanel):
    bl_label : str = "Object"
    
    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        bx = draw_title_box_layout(layout,text='Object Tools',icon='OBJECT_DATA')
        
        if context.active_object: pass
        else:
            draw_wrapped_texts(bx, text="Select an Object",max_chars=40 , icon='HELP')
            return
        
        transformbox = draw_title_box_layout(bx,text=f'Transform (Active: {context.active_object.name})',icon='TRANSFORM_ORIGINS',align=True)
        transformbox.operator(OBJECT_OT_Apply_Transform.bl_idname)
            
        translatebox = draw_title_box_layout(bx,text=f'Translate (Active: {context.active_object.name})',icon='NETWORK_DRIVE',align=True)
        
        text = [
            "Requires Internet Connection\n",
            "Translator: Google Translate",
        ]
        
        draw_wrapped_texts(translatebox," ".join(text),alert=True, boxed=False)
        
        translatebox.separator()
        
        op = translatebox.operator(OBJECT_OT_Translate_Object.bl_idname)
        
class OBJECT_OT_Translate_Object_Process(Operator):
    bl_idname = 'objectdata.translate_object'
    bl_label = 'Translating Names'
    bl_options = {'INTERNAL'}
    
    translate_types: bpy.props.EnumProperty(
        name="Translate",
        items=[
            ('BONES', "Bone Names", ""),
            ('SHAPEKEYS', "Shape Key Names", ""),
            ('OBJECTS', "Object Names", ""),
            ('MATERIALS', "Material Names", ""),
        ],
        options={'ENUM_FLAG'}
    )
    
    no_spaces: bpy.props.BoolProperty(default=True)
    include_children: bpy.props.BoolProperty(default=True)
    source_lang: bpy.props.StringProperty(default="auto")
    
    def process_name(self, name: str) -> str:
        if self.no_spaces:
            return name.replace(' ', '_')
        return name
    
    def process_object(self, obj):
        translated_count = 0
        translations_log = []
        
        if 'BONES' in self.translate_types and obj.type == 'ARMATURE':
            bone_names = [bone.name for bone in obj.data.bones]
            if bone_names:
                print(f"[Translation] Processing {len(bone_names)} bones in armature '{obj.name}'")
                translated_names = translate_string(bone_names, source_lang=self.source_lang)
                
                bone_map = {old: self.process_name(new) for old, new in zip(bone_names, translated_names)}
                
                for old_name, new_name in bone_map.items():
                    if old_name != new_name:
                        bone = obj.data.bones.get(old_name)
                        if bone:
                            bone.name = new_name.lower()
                            translated_count += 1
                            log_entry = f"  Bone: '{old_name}' → '{new_name.lower()}'"
                            print(log_entry)
                            translations_log.append(log_entry)
            
            if hasattr(obj.data, 'collections'):
                collection_names = [col.name for col in obj.data.collections]
                if collection_names:
                    print(f"[Translation] Processing {len(collection_names)} bone collections")
                    translated_names = translate_string(collection_names, source_lang=self.source_lang)
                    
                    for col, new_name in zip(obj.data.collections, translated_names):
                        new_name = self.process_name(new_name)
                        if col.name != new_name:
                            old_col_name = col.name
                            col.name = new_name
                            translated_count += 1
                            log_entry = f"  Bone Collection: '{old_col_name}' → '{new_name}'"
                            print(log_entry)
                            translations_log.append(log_entry)
        
        if 'SHAPEKEYS' in self.translate_types:
            if obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                key_blocks = obj.data.shape_keys.key_blocks
                shapekey_names = [kb.name for kb in key_blocks]
                
                if shapekey_names:
                    print(f"[Translation] Processing {len(shapekey_names)} shape keys in '{obj.name}'")
                    translated_names = translate_string(shapekey_names, source_lang=self.source_lang)
                    
                    for kb, new_name in zip(key_blocks, translated_names):
                        new_name = self.process_name(new_name)
                        if kb.name != new_name:
                            old_kb_name = kb.name
                            kb.name = new_name
                            translated_count += 1
                            log_entry = f"  Shape Key: '{old_kb_name}' → '{new_name}'"
                            print(log_entry)
                            translations_log.append(log_entry)
        
        if 'OBJECTS' in self.translate_types:
            names_to_translate = [obj.name]
            if obj.data and hasattr(obj.data, 'name'):
                names_to_translate.append(obj.data.name)
            
            print(f"[Translation] Processing object names for '{obj.name}'")
            translated_names = translate_string(names_to_translate, source_lang=self.source_lang)
            
            new_obj_name = self.process_name(translated_names[0])
            if obj.name != new_obj_name:
                old_obj_name = obj.name
                obj.name = new_obj_name
                translated_count += 1
                log_entry = f"  Object: '{old_obj_name}' → '{new_obj_name}'"
                print(log_entry)
                translations_log.append(log_entry)
            
            if len(translated_names) > 1 and obj.data and hasattr(obj.data, 'name'):
                new_data_name = self.process_name(translated_names[1])
                if obj.data.name != new_data_name:
                    old_data_name = obj.data.name
                    obj.data.name = new_data_name
                    translated_count += 1
                    log_entry = f"  Object Data: '{old_data_name}' → '{new_data_name}'"
                    print(log_entry)
                    translations_log.append(log_entry)
        
        if 'MATERIALS' in self.translate_types:
            if obj.data and hasattr(obj.data, 'materials'):
                materials = [mat for mat in obj.data.materials if mat]
                material_names = [mat.name for mat in materials]
                
                if material_names:
                    print(f"[Translation] Processing {len(material_names)} materials in '{obj.name}'")
                    translated_names = translate_string(material_names, source_lang=self.source_lang)
                    
                    for mat, new_name in zip(materials, translated_names):
                        new_name = self.process_name(new_name)
                        if mat.name != new_name:
                            old_mat_name = mat.name
                            mat.name = new_name
                            translated_count += 1
                            log_entry = f"  Material: '{old_mat_name}' → '{new_name}'"
                            print(log_entry)
                            translations_log.append(log_entry)
        
        return translated_count, translations_log
    
    def execute(self, context):
        try:
            obj = context.active_object
            
            if not obj:
                self.report({'ERROR'}, "No active object selected")
                return {'CANCELLED'}
            
            print("=" * 60)
            print(f"[Translation] Starting translation process")
            print(f"[Translation] Source language: {self.source_lang}")
            print(f"[Translation] Active object: '{obj.name}'")
            print("=" * 60)
            
            objects_to_process = [obj]
            
            if self.include_children:
                if obj.type == 'ARMATURE':
                    armature_meshes = get_armature_meshes(obj)
                    if armature_meshes:
                        print(f"[Translation] Found {len(armature_meshes)} armature meshes")
                    objects_to_process.extend(armature_meshes)
                
                children = get_all_child_objects(obj)
                if children:
                    print(f"[Translation] Found {len(children)} child objects")
                objects_to_process.extend(children)
            
            print(f"[Translation] Total objects to process: {len(objects_to_process)}")
            print("-" * 60)
            
            total_translated = 0
            all_translations = []
            
            for i, current_obj in enumerate(objects_to_process, 1):
                print(f"[Translation] Processing object {i}/{len(objects_to_process)}: '{current_obj.name}'")
                count, logs = self.process_object(current_obj)
                total_translated += count
                all_translations.extend(logs)
                if count > 0:
                    print(f"[Translation] Translated {count} names in '{current_obj.name}'")
                else:
                    print(f"[Translation] No changes needed for '{current_obj.name}'")
                print("-" * 60)
            
            print("=" * 60)
            print(f"[Translation] Translation complete!")
            print(f"[Translation] Total names updated: {total_translated}")
            print("=" * 60)
            
            if all_translations:
                print("\n[Translation] Summary of all translations:")
                for log in all_translations:
                    print(log)
                print("=" * 60)
            
            self.report({'INFO'}, f"Translation complete! {total_translated} names updated")
            return {'FINISHED'}
            
        except Exception as e:
            print(f"[Translation] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Translation error: {str(e)}")
            return {'CANCELLED'}

class OBJECT_OT_Translate_Object(Operator):
    bl_idname = "objectdata.translate_names"
    bl_label = "Translate Names to English"
    bl_description = "Translate selected name types to English using Google Translate"
    bl_options = {'REGISTER', 'UNDO'}
    
    translate_types: EnumProperty(
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
    
    no_spaces: BoolProperty(
        name="Replace Spaces with Underscore",
        description="Replace spaces with underscores in translated names",
        default=True
    )
    
    include_children: BoolProperty(
        name="Include Child Objects",
        description="Also translate names for all child objects recursively",
        default=True
    )
    
    source_lang: StringProperty(
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
        bpy.ops.objectdata.translate_object(
            'EXEC_DEFAULT',
            translate_types=self.translate_types,
            no_spaces=self.no_spaces,
            include_children=self.include_children,
            source_lang=self.source_lang
        )
        return {'FINISHED'}

class OBJECT_OT_Apply_Transform(Operator):
    bl_idname : str = "objectdata.apply_transform"
    bl_label : str = "Apply Transform"
    bl_description : str = "Apply transforms to object and optionally its children"
    bl_options : set = {'REGISTER', 'UNDO'}
    
    location: BoolProperty(
        name="Location",
        description="Apply location transform",
        default=True
    )
    
    rotation: BoolProperty(
        name="Rotation",
        description="Apply rotation transform",
        default=True
    )
    
    scale: BoolProperty(
        name="Scale",
        description="Apply scale transform",
        default=True
    )
    
    include_children: BoolProperty(
        name="Include Children",
        description="Apply transforms to children as well",
        default=True
    )
    
    fix_bone_empties: BoolProperty(
        name="Fix Bone-Parented Empties",
        description="Automatically fix bone-parented empties after applying transforms to armatures",
        default=True
    )
    
    @classmethod
    def poll(cls, context : Context) -> bool:
        return bool(context.active_object)
    
    def invoke(self, context : Context, event : Event) -> set:
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context : Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        col = layout.column(align=True)
        col.label(text="Transform Components:")
        col.prop(self, "location")
        col.prop(self, "rotation")
        col.prop(self, "scale")
        
        col = layout.column(align=True)
        col.label(text="Options:")
        col.prop(self, "include_children")
        
        if context.active_object and context.active_object.type == 'ARMATURE':
            col.label(text="Armature Options:")
            col.prop(self, "fix_bone_empties")
    
    def execute(self, context : Context) -> set:
        obj = context.active_object
        
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        
        try:
            count, fixed_count = apply_object_transforms(
                obj=obj,
                location=self.location,
                rotation=self.rotation,
                scale=self.scale,
                include_children=self.include_children,
                fix_bone_parented=self.fix_bone_empties
            )
            
            if fixed_count > 0:
                self.report({'INFO'}, f"Applied transforms to {count} object(s), fixed {fixed_count} empty(s)")
            else:
                self.report({'INFO'}, f"Applied transforms to {count} object(s)")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply transforms: {str(e)}")
            return {'CANCELLED'}