# SPDX-FileCopyrightText: 2019-2022 Blender Foundation
#
# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import mathutils
from bpy.types import Operator


def get_rig_and_cam(obj):
    if (obj.type == 'ARMATURE'
            and "rig_id" in obj
            and obj["rig_id"].lower() in {"dolly_rig",
                                          "crane_rig", "2d_rig"}):
        cam = None
        for child in obj.children:
            if child.type == 'CAMERA':
                cam = child
                break
        if cam is not None:
            return obj, cam
    elif (obj.type == 'CAMERA'
          and obj.parent is not None
          and "rig_id" in obj.parent
          and obj.parent["rig_id"].lower() in {"dolly_rig",
                                               "crane_rig", "2d_rig"}):
        return obj.parent, obj
    return None, None

def calculate_aim_distance(obj):
    '''This will return the distance of the camera and the aim bone at the time it is called.'''
    camera_bone = obj.pose.bones['Camera'].matrix
    aim_bone = obj.pose.bones['Aim'].matrix
    length = (camera_bone - aim_bone).to_translation().length
    return length

class CameraRigMixin():
    @classmethod
    def poll(cls, context):
        if context.active_object is not None:
            return get_rig_and_cam(context.active_object) != (None, None)

        return False


class ADD_CAMERA_RIGS_OT_set_scene_camera(Operator):
    bl_idname = "add_camera_rigs.set_scene_camera"
    bl_label = "Make Camera Active"
    bl_description = "Makes the camera parented to this rig the active scene camera"

    @classmethod
    def poll(cls, context):
        if context.active_object is not None:
            rig, cam = get_rig_and_cam(context.active_object)
            if cam is not None:
                return cam is not context.scene.camera

        return False

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)
        scene_cam = context.scene.camera

        context.scene.camera = cam
        return {'FINISHED'}


class ADD_CAMERA_RIGS_OT_add_marker_bind(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.add_marker_bind"
    bl_label = "Add Marker and Bind Camera"
    bl_description = "Add marker to current frame then bind rig camera to it (for camera switching)"

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)

        marker = context.scene.timeline_markers.new(
            "cam_" + str(context.scene.frame_current),
            frame=context.scene.frame_current
        )
        marker.camera = cam

        return {'FINISHED'}


class ADD_CAMERA_RIGS_OT_set_dof_bone(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.set_dof_bone"
    bl_label = "Set DOF Bone"
    bl_description = "Set the Aim bone as a DOF target"

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)

        cam.data.dof.focus_object = rig
        cam.data.dof.focus_subtarget = (
            'MCH-Center' if rig["rig_id"].lower() == '2d_rig'
            else 'MCH-Aim_shape_rotation')

        return {'FINISHED'}


class ADD_CAMERA_RIGS_OT_set_dolly_zoom(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.set_dolly_zoom"
    bl_label = "Set Dolly Zoom"
    bl_description = "Use the aim bone as a focal length (Dolly Zoom effect)"

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)

        if rig["rig_id"].lower() == '2d_rig': 
            return {'FINISHED'}

        value = calculate_aim_distance(rig)
        drv = cam.data.animation_data.drivers[0]
        drv.driver.expression = '(distance * (lens+lens_offset) / %s ) / root_scale' %value

        #set the bone color to default
        rig.pose.bones["Aim"].color.palette = 'THEME01'

        return {'FINISHED'}


class ADD_CAMERA_RIGS_OT_remove_dolly_zoom(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.remove_dolly_zoom"
    bl_label = "Remove Dolly Zoom"
    bl_description = "Disconnect the aim bone as a focal length (Dolly Zoom effect)"

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)

        if rig["rig_id"].lower() == '2d_rig': 
            return {'FINISHED'}

        lens_value = cam.data.lens

        # set the lens to the current value
        drv = cam.data.animation_data.drivers[0]
        drv.driver.expression = 'lens'
        rig.pose.bones["Camera"]["lens"] = lens_value

        # reset the offset back to zero
        rig.pose.bones["Camera"]["lens_offset"] = 0

        #set the bone color to default
        rig.pose.bones["Aim"].color.palette = 'DEFAULT'

        return {'FINISHED'}


class ADD_CAMERA_RIGS_OT_shift_to_pivot(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.shift_to_pivot"
    bl_label = "Shift To Pivot"
    bl_description = "Offset the Camera and Aim such that the Aim bone is above the Root control"

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)

        # get the local matrix of the aim bone
        aim_loc = rig.pose.bones["Aim"].matrix_basis.to_translation()

        # create a transform matrix for the z loc of the aim bone
        mat_trans = mathutils.Matrix.Translation( [0, 0, aim_loc[2] + 1.7 ]) # Hardcoded height of rest position   
        # repostion the aim bone so it's above the root (using the original z value)
        rig.pose.bones["Aim"].matrix = rig.pose.bones["Root"].matrix @ mat_trans

        # offset the camera matrix relative to the new aim position
        camera_offset_vector = (rig.pose.bones["Aim"].matrix_basis.to_translation() ) - aim_loc
        camera_offset_matrix = mathutils.Matrix.Translation(camera_offset_vector)
        rig.pose.bones["Camera"].matrix = rig.pose.bones["Camera"].matrix @ camera_offset_matrix
        return {'FINISHED'}

class ADD_CAMERA_RIGS_OT_swap_lens(Operator, CameraRigMixin):
    bl_idname = "add_camera_rigs.swap_lens"
    bl_label = "Swap Lens"
    bl_description = "Set the focal length to a specific value and shift the camera to match the same framing"

    camera_lens: bpy.props.FloatProperty(
        name="Focal Length (mm)",
        default=50,
        min = 1,
        max = 1000,
        description="The value of the new focal length",
    )

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text="Focal Length:")
        row.prop(self, "camera_lens", text="")
        row = layout.row()
        
    def invoke(self, context, event):
        rig, cam = get_rig_and_cam(context.active_object)
        
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        rig, cam = get_rig_and_cam(context.active_object)
        
        # get the vector from aim to camera bone
        vector = (rig.pose.bones["Aim"].matrix - rig.pose.bones["Camera"].matrix).to_translation()
        root_scale =  rig.pose.bones['Root'].matrix.to_scale()
        root_scale = (root_scale[0] + root_scale[1] + root_scale[2] )/ 3  # Average scale

        old_lens = rig.pose.bones["Camera"]["lens"]
        new_lens = self.camera_lens

        # set the new camera lens
        rig.pose.bones["Camera"]["lens"] = new_lens

        # calculate the new distance
        new_distance = ((new_lens * 1.0 * vector.length ) / old_lens)  

        # find the delta distance (divide by root scale to take care of any object and/or root scaling)
        delta_distance = (vector.length - new_distance) / root_scale 
        # turn that into a vector the translation matrix
        movement_vector = vector.normalized() * delta_distance
        camera_offset_matrix = mathutils.Matrix.Translation(movement_vector)
        # move the camera to the correct position
        rig.pose.bones["Camera"].matrix =  camera_offset_matrix @ rig.pose.bones["Camera"].matrix

        return {'FINISHED'}


classes = (
    ADD_CAMERA_RIGS_OT_set_scene_camera,
    ADD_CAMERA_RIGS_OT_add_marker_bind,
    ADD_CAMERA_RIGS_OT_set_dof_bone,
    ADD_CAMERA_RIGS_OT_set_dolly_zoom,
    ADD_CAMERA_RIGS_OT_remove_dolly_zoom,
    ADD_CAMERA_RIGS_OT_shift_to_pivot,
    ADD_CAMERA_RIGS_OT_swap_lens,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in classes:
        unregister_class(cls)
