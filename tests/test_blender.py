"""Integration checks; run only in a separate --background --factory-startup Blender."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import bpy

if not bpy.app.background:
    raise RuntimeError("Run these checks in a separate background Blender process.")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("parenting_under_test", ROOT / "__init__.py")
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()


def make_object(name, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def select(parent, *objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (parent,) + objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parent
    bpy.context.view_layer.update()


class DialogProbe:
    """Capture the dialog boundary without opening a window in a background test."""
    def __init__(self):
        self.opened = False
        self.familia_sin_regla = ""
        self.properties = SimpleNamespace(is_property_set=lambda name: False)

    def invoke_props_dialog(self, operator, width):
        self.opened = True
        self.width = width
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT')

    def invoke(self):
        context = SimpleNamespace(
            active_object=bpy.context.active_object,
            selected_objects=bpy.context.selected_objects,
            window_manager=self,
        )
        return addon.OBJECT_OT_reparent_and_rename_smart.invoke(self, context, None)


class ParentingTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_floor_family_preserves_transform_selection_and_active(self):
        parent = make_object('floor0')
        parent.location = (8, 3, -2)
        parent.rotation_euler = (0.2, -0.5, 0.4)
        parent.scale = (2, 3, 0.5)
        obj = make_object('Cube')
        obj.location = (4, -7, 3)
        obj.rotation_euler = (0.1, 0.3, -0.2)
        obj.scale = (1.2, 0.6, 2)
        select(parent, obj)
        before = obj.matrix_world.copy()
        result = bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
        bpy.context.view_layer.update()
        self.assertEqual(result, {'FINISHED'})
        self.assertEqual(obj.name, 'floor0_bathfloor0')
        self.assertEqual(obj.parent, parent)
        self.assertEqual(set(bpy.context.selected_objects), {parent, obj})
        self.assertEqual(bpy.context.active_object, parent)
        for old_row, new_row in zip(before, obj.matrix_world):
            for old_value, new_value in zip(old_row, new_row):
                self.assertAlmostEqual(old_value, new_value, places=5)

    def test_preview_matches_batch_with_global_name_collisions(self):
        parent = make_object('floor0')
        make_object('floor0_bathfloor0', parent)
        outside = make_object('floor0_bathfloor1')
        objects = [make_object('Cube'), make_object('Sphere')]
        select(parent, *objects)
        pending = addon.objetos_sin_familia([o for o in bpy.context.selected_objects if o != parent])
        reserved = set()
        preview = {}
        for obj in pending:
            preview[obj] = addon.nombre_para_familia(parent, 'bathfloor', obj, reserved)
            reserved.add(preview[obj])
        bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
        self.assertEqual(set(preview.values()), {'floor0_bathfloor2', 'floor0_bathfloor3'})
        for obj, name in preview.items():
            self.assertEqual(obj.name, name)
            self.assertEqual(obj.parent, parent)
        self.assertIsNone(outside.parent)

    def test_existing_chrome_and_new_floor_family_in_same_selection(self):
        parent = make_object('floor0')
        chrome = make_object('wall7_chrome2.001')
        unknown = make_object('Cube')
        select(parent, chrome, unknown)
        bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
        self.assertEqual(chrome.name, 'floor0_chrome2')
        self.assertEqual(unknown.name, 'floor0_bathfloor0')
        self.assertEqual(chrome.parent, parent)

    def test_known_family_moving_into_previewed_name_is_renumbered(self):
        parent = make_object('floor0')
        known = make_object('floor7_bathfloor0')
        unknown = make_object('Cube')
        select(parent, known, unknown)
        preview = addon.nombre_para_familia(parent, 'bathfloor', unknown)
        bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
        self.assertEqual(unknown.name, preview)
        self.assertEqual(known.name, 'floor0_bathfloor1')

    def test_assigned_family_is_stable_on_second_run(self):
        parent = make_object('floor0')
        obj = make_object('Cube')
        select(parent, obj)
        bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
        probe = DialogProbe()
        self.assertEqual(probe.invoke(), {'FINISHED'})
        self.assertFalse(probe.opened)
        self.assertEqual(obj.name, 'floor0_bathfloor0')

    def test_dialog_defaults_and_cancel_do_not_modify_scene(self):
        for parent_type in ('floor', 'wall', 'interiorwall', 'ceiling'):
            with self.subTest(parent_type=parent_type):
                self.setUp()
                parent = make_object(parent_type + '0')
                obj = make_object('Cube')
                select(parent, obj)
                before = obj.matrix_world.copy()
                probe = DialogProbe()
                self.assertEqual(probe.invoke(), {'RUNNING_MODAL'})
                self.assertTrue(probe.opened)
                expected = 'bathfloor' if parent_type == 'floor' else 'primitive'
                self.assertEqual(probe.familia_sin_regla, expected)
                # Cancelling skips execute: reaching the dialog must leave everything untouched.
                self.assertEqual(obj.name, 'Cube')
                self.assertIsNone(obj.parent)
                self.assertEqual(obj.matrix_world, before)
                self.assertEqual(set(bpy.context.selected_objects), {parent, obj})
                self.assertEqual(bpy.context.active_object, parent)

    def test_execute_without_family_does_not_partially_modify_mixed_selection(self):
        parent = make_object('floor0')
        obj = make_object('Cube')
        known = make_object('wall1_chrome0')
        select(parent, obj, known)
        self.assertEqual(bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT'), {'CANCELLED'})
        self.assertEqual(obj.name, 'Cube')
        self.assertEqual(known.name, 'wall1_chrome0')
        self.assertIsNone(obj.parent)
        self.assertIsNone(known.parent)

    def test_generic_family_for_all_parent_types(self):
        for parent_type in ('floor', 'wall', 'interiorwall', 'ceiling'):
            with self.subTest(parent_type=parent_type):
                self.setUp()
                parent = make_object(parent_type + '3')
                obj = make_object('Cube')
                select(parent, obj)
                bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='primitive')
                self.assertEqual(obj.name, parent.name + '_primitive0')
                self.assertEqual(obj.parent, parent)
                self.assertEqual(bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT'), {'FINISHED'})
                self.assertEqual(obj.name, parent.name + '_primitive0')

    def test_existing_structural_duplicate_rule(self):
        parent = make_object('ceiling0')
        obj = make_object('wall1.001')
        select(parent, obj)
        probe = DialogProbe()
        self.assertEqual(probe.invoke(), {'FINISHED'})
        self.assertFalse(probe.opened)
        self.assertEqual(obj.name, 'ceiling0_wall0')
        self.assertEqual(obj.parent, parent)
        self.assertEqual(bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT'), {'FINISHED'})
        self.assertEqual(obj.name, 'ceiling0_wall0')

    def test_existing_door_and_closet_hierarchies(self):
        for is_closet in (False, True):
            with self.subTest(closet=is_closet):
                self.setUp()
                parent = make_object('wall0')
                root = make_object('Closet' if is_closet else 'Door')
                panel = make_object('closedleft' if is_closet else 'left', root)
                hardware = make_object('Handle', panel)
                select(parent, root)
                probe = DialogProbe()
                self.assertEqual(probe.invoke(), {'FINISHED'})
                self.assertFalse(probe.opened)
                base = 'wall0_closet0_door0' if is_closet else 'wall0_door0'
                self.assertEqual(root.name, base + '_frame0')
                self.assertEqual(root.parent, parent)
                self.assertEqual(panel.parent, root)
                self.assertEqual(hardware.parent, panel)
                self.assertEqual(hardware.name, panel.name + '_hardware0')

    def test_invalid_parent_leaves_scene_unchanged(self):
        parent = make_object('Floor')
        obj = make_object('Cube')
        select(parent, obj)
        self.assertEqual(bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT'), {'CANCELLED'})
        self.assertEqual(obj.name, 'Cube')
        self.assertIsNone(obj.parent)

    def test_menu_uses_invoke_and_restores_previous_context(self):
        calls = []
        layout = SimpleNamespace(operator_context='EXEC_REGION_WIN')
        layout.operator = lambda identifier: calls.append((identifier, layout.operator_context))
        addon.menu_func(SimpleNamespace(layout=layout), bpy.context)
        self.assertEqual(calls, [('object.reparent_and_rename_smart', 'INVOKE_DEFAULT')])
        self.assertEqual(layout.operator_context, 'EXEC_REGION_WIN')


try:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ParentingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError('Blender integration checks failed')
finally:
    addon.unregister()
