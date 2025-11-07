from bpy.types import Operator, Context, Event, UILayout
from bpy.props import BoolProperty, StringProperty, EnumProperty

from ..core.networkutils import (
    translate_to_english
)

from ..core.commonutils import (
    draw_wrapped_text_col, draw_title_box, get_all_children, getArmatureMeshes, create_toggle_section
)

from ..core.objectutils import (
    apply_object_transforms
)

from .common import Tools_SubCategoryPanel

class OBJECT_PT_translate_panel(Tools_SubCategoryPanel):
    bl_label : str = "Object Tools"
    
    def draw(self, context : Context) -> None:
        layout : UILayout = self.layout
        
        bx = draw_title_box(layout,text='Object Tools',icon='OBJECT_DATA')
        
        if context.active_object: pass
        else:
            draw_wrapped_text_col(bx, text="Select an Object",max_chars=40 , icon='HELP')
            return
        
        transformbox = draw_title_box(bx,text=f'Transform (Active: {context.active_object.name})',icon='TRANSFORM_ORIGINS',align=True)
        
        transformbox.separator()
        
        text = [
            "Key Differences:\n",
            "- Automatically applies transforms to child objects\n",
            "- Filter which child types to include/exclude\n",
            "- Fixes bone-parented empties on armatures (prevents position errors when scale is applied)\n\n",
            
            "Use this when you need to apply transforms to complex hierarchies, ",
            "especially armatures with bone-parented empties that would otherwise get misplaced.\n\n",
            
            "Note: This only applies object transforms. For armature pose application, use 'Apply Current Pose as Rest Pose' instead."
        ]
        
        text2 = [
            "Will only work on the current active object, multi apply is not applicable\n\n"
            "Ideally should only be used for complex object hierarchies! Will work poorly for simple apply, just use blender's instead"
        ]
        
        transform_helpsection = create_toggle_section(transformbox,context.scene.vs,'show_applytransform_help',show_text='Show Help',icon='HELP')
        
        if transform_helpsection is not None:
            draw_wrapped_text_col(transform_helpsection, " ".join(text), alert=False, boxed=False)
            draw_wrapped_text_col(transform_helpsection, " ".join(text2), alert=True, boxed=False)
        
        transformbox.separator()
        
        transformbox.operator(OBJECT_OT_apply_transform.bl_idname)
            
        translatebox = draw_title_box(bx,text=f'Translate (Active: {context.active_object.name})',icon='NETWORK_DRIVE',align=True)
        
        text = [
            "This requires Internet Connection!\n",
            "Translator: Google Translate\n\n",
            "This will temporary freeze blender depending how much it will translate.",
            "If entries didn't get translate, try again later as you may have hit Google's limit"
        ]
        
        draw_wrapped_text_col(translatebox," ".join(text),alert=True, boxed=False)
        
        translatebox.separator()
        
        op = translatebox.operator(OBJECT_OT_translate_names.bl_idname)
        
class OBJECT_OT_translate_names(Operator):
    bl_idname : str = "object.translate_names"
    bl_label : str = "Translate Names to English"
    bl_description : str = "Translate selected name types to English using Google Translate"
    bl_options : set = {'REGISTER', 'UNDO'}
    
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
    
    def invoke(self, context : Context, event : Event) -> set:
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context : Context) -> None:
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
    
    def execute(self, context : Context) -> set:
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
    
class OBJECT_OT_apply_transform(Operator):
    bl_idname : str = "object.apply_transform"
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
    
    excluded_types: EnumProperty(
        name="Exclude Types",
        description="Object types to exclude from transform application",
        items=[
            ('EMPTY', "Empty", "Exclude empty objects"),
            ('CURVE', "Curve", "Exclude curve objects"),
            ('LIGHT', "Light", "Exclude light objects"),
            ('CAMERA', "Camera", "Exclude camera objects"),
        ],
        options={'ENUM_FLAG'},
        default={'EMPTY', 'CURVE'}
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
        
        if self.include_children:
            col.label(text="Excluded Types:")
            col.prop(self, "excluded_types")
        
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
        
        excluded_types = set(self.excluded_types)
        
        try:
            count, fixed_count = apply_object_transforms(
                obj=obj,
                location=self.location,
                rotation=self.rotation,
                scale=self.scale,
                include_children=self.include_children,
                excluded_types=excluded_types,
                fix_bone_empties=self.fix_bone_empties
            )
            
            if fixed_count > 0:
                self.report({'INFO'}, f"Applied transforms to {count} object(s), fixed {fixed_count} empty(s)")
            else:
                self.report({'INFO'}, f"Applied transforms to {count} object(s)")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to apply transforms: {str(e)}")
            return {'CANCELLED'}