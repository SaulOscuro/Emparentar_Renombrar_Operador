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
        addon.name_overlays._OverlayRuntime.shutdown(bpy.context)
        addon.automatic_tools._snapshot = None
        addon.automatic_tools._undo_snapshot = None
        addon.automatic_tools._reports = {}
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


    def test_approved_display_families_and_roots(self):
        from parenting_under_test.naming_rules import DISPLAY_FAMILIES, unsupported_reason
        self.assertEqual(len(DISPLAY_FAMILIES), 35)
        self.assertNotIn('primitive', DISPLAY_FAMILIES)
        for family in DISPLAY_FAMILIES:
            for parent in ('wall0', 'interiorwall1', 'floor2', 'ceiling3'):
                with self.subTest(parent=parent, family=family):
                    self.assertIsNone(unsupported_reason(f'{parent}_{family}0'))
        for name in ('wall0', 'interiorwall1', 'floor2', 'ceiling3', 'toallero_colgador0', 'wall2_chrome4.001',
                     'ceiling0_black3', 'wall1_lampmetal0', 'wall1_lampemission0'):
            self.assertIsNone(unsupported_reason(name), name)

    def test_unknown_and_excluded_names_are_warnings(self):
        check = addon.name_overlays.unsupported_reason
        for name in ('Cube', 'wall_1', 'wall1_1', 'wall0_Cube', 'wall0_primitive0',
                     'wall0_Primitive1.001', 'wall0_unknownfamily0', 'wall0_door0_Cube',
                     'wall0_chrome', 'wall0_chrome0garbage', 'wall0_chrome0_unknown0',
                     'wall0_hardware0', 'wall0_notchrome0', ' wall0_chrome0'):
            with self.subTest(name=name):
                self.assertIsNotNone(check(name))

    def test_generated_door_and_closet_names_are_accepted(self):
        check = addon.name_overlays.unsupported_reason
        for name in ('wall0_door0_frame0', 'wall0_door0_leftpanel0',
                     'wall0_door0_rightpanel1_hardware2', 'wall0_door0_leftpanel0_door0',
                     'floor0_closet0_door0_frame0',
                     'interiorwall0_closet0_door0_closedleftpanel0_hardware0',
                     'wall0_closet0_door0_openrightpanel0_door0'):
            self.assertIsNone(check(name), name)

    def test_red_labels_do_not_require_selection_and_do_not_edit_objects(self):
        overlay = addon.name_overlays
        parent = make_object('wall0')
        valid = make_object('wall0_chrome0', parent)
        invalid = make_object('Cube', parent)
        primitive = make_object('wall0_primitive0', parent)
        select(parent, valid)
        before = [(o, o.name, o.parent, o.matrix_world.copy(), tuple(o.color))
                  for o in bpy.data.objects]
        overlay._OverlayRuntime.enable_invalid_names(bpy.context)
        labels = list(overlay.visible_name_labels(bpy.context))
        self.assertEqual({obj for obj, style in labels}, {invalid, primitive})
        for obj, (text, color, scale) in labels:
            self.assertFalse(obj.select_get())
            self.assertEqual(text, '! ' + obj.name)
            self.assertEqual(color, overlay.ERROR_COLOR)
            self.assertGreater(scale, 1.0)
        for obj, name, old_parent, matrix, color in before:
            self.assertEqual((obj.name, obj.parent, obj.matrix_world, tuple(obj.color)),
                             (name, old_parent, matrix, color))
        self.assertEqual(set(bpy.context.selected_objects), {parent, valid})

    def test_warning_priority_when_all_names_and_selection_are_enabled(self):
        overlay = addon.name_overlays
        parent = make_object('floor0')
        valid = make_object('floor0_bathfloor0', parent)
        invalid = make_object('wall_1')
        overlay._OverlayRuntime.enable_all_names(bpy.context)
        overlay._OverlayRuntime.enable_invalid_names(bpy.context)
        labels = list(overlay.visible_name_labels(bpy.context))
        self.assertEqual(len(labels), 3)
        styles = {obj: style for obj, style in labels}
        self.assertEqual(styles[valid][1], overlay.NORMAL_COLOR)
        self.assertEqual(styles[invalid][1], overlay.ERROR_COLOR)
        # The cursor label uses this same style decision.
        self.assertEqual(overlay.label_style(invalid.name)[1], overlay.ERROR_COLOR)
        overlay._OverlayRuntime.disable_invalid_names(bpy.context)
        self.assertEqual(overlay.label_style(invalid.name)[1], overlay.NORMAL_COLOR)

    def test_rename_reclassifies_and_hidden_objects_are_excluded(self):
        overlay = addon.name_overlays
        parent = make_object('wall0')
        obj = make_object('Cube', parent)
        hidden = make_object('Unknown')
        hidden.hide_set(True)
        bpy.context.view_layer.update()
        overlay._OverlayRuntime.enable_invalid_names(bpy.context)
        self.assertEqual([o for o, _ in overlay.visible_name_labels(bpy.context)], [obj])
        obj.name = 'wall0_chrome0'
        self.assertEqual(list(overlay.visible_name_labels(bpy.context)), [])
        obj.name = 'wall0_primitive0'
        self.assertEqual([o for o, _ in overlay.visible_name_labels(bpy.context)], [obj])

    def test_overlay_lifecycle_has_one_handler_and_cleans_up(self):
        overlay = addon.name_overlays
        overlay._OverlayRuntime.enable_all_names(bpy.context)
        handle = overlay._OverlayRuntime.draw_handle
        self.assertIsNotNone(handle)
        overlay._OverlayRuntime.enable_invalid_names(bpy.context)
        self.assertEqual(overlay._OverlayRuntime.draw_handle, handle)
        overlay._OverlayRuntime.disable_all_names(bpy.context)
        self.assertEqual(overlay._OverlayRuntime.draw_handle, handle)
        overlay._OverlayRuntime.disable_invalid_names(bpy.context)
        self.assertIsNone(overlay._OverlayRuntime.draw_handle)
        addon.unregister()
        self.assertNotIn(overlay._before_load, bpy.app.handlers.load_pre)
        self.assertNotIn(overlay._after_load, bpy.app.handlers.load_post)
        addon.register()
        self.assertEqual(list(bpy.app.handlers.load_pre).count(overlay._before_load), 1)
        self.assertEqual(list(bpy.app.handlers.load_post).count(overlay._after_load), 1)

    def test_view_menu_contains_all_three_independent_modes(self):
        calls = []
        layout = SimpleNamespace(operator_context='EXEC_REGION_WIN', separator=lambda: None)
        layout.operator = lambda identifier, **kw: calls.append((identifier, layout.operator_context, kw))
        addon.name_overlays._draw_view_menu(SimpleNamespace(layout=layout), bpy.context)
        self.assertEqual({row[0] for row in calls}, {
            'ero.selection_name_overlay_toggle', 'ero.all_object_names_overlay_toggle',
            'ero.unsupported_names_overlay_toggle'})
        self.assertTrue(all(row[1] == 'INVOKE_REGION_WIN' for row in calls))
        self.assertEqual(layout.operator_context, 'EXEC_REGION_WIN')

    def test_blender_show_overlays_switch_is_respected(self):
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            space = bpy.context.space_data
            previous = space.overlay.show_overlays
            try:
                space.overlay.show_overlays = False
                self.assertIsNone(addon.name_overlays._valid_draw_context())
                space.overlay.show_overlays = True
                self.assertIsNotNone(addon.name_overlays._valid_draw_context())
            finally:
                space.overlay.show_overlays = previous


def make_mesh(name, parent=None):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new('TestMesh'))
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


class AutomaticTests(ParentingTests):
    # Only the tests declared below are collected separately.
    def test_live_duplicate_skips_occupied_indices_and_is_idempotent(self):
        root = make_mesh('wall1')
        make_mesh('wall1_lamp0', root)
        make_mesh('wall1_lamp1', root)
        duplicate = make_mesh('wall1_lamp0.001', root)
        select(root, duplicate)
        before = (duplicate.matrix_world.copy(), duplicate.parent, duplicate.data.name)
        self.assertEqual(addon.automatic_tools.run_pass(), 1)
        self.assertEqual(duplicate.name, 'wall1_lamp2')
        self.assertEqual((duplicate.matrix_world, duplicate.parent, duplicate.data.name), before)
        self.assertEqual(set(bpy.context.selected_objects), {root, duplicate})
        self.assertEqual(bpy.context.active_object, root)
        self.assertEqual(addon.automatic_tools.report_for(bpy.context.scene), ())
        self.assertEqual(addon.automatic_tools.run_pass(), 0)

    def test_duplicate_root_keeps_children_and_descendant_prefixes(self):
        make_mesh('wall0')
        root = make_mesh('wall0.001')
        frame = make_mesh('wall0_door0_frame0.001', root)
        panel = make_mesh('wall0_door0_leftpanel0.001', frame)
        hardware = make_mesh('wall0_door0_leftpanel0_hardware0.001', panel)
        addon.automatic_tools.run_pass()
        self.assertEqual([o.name for o in (root, frame, panel, hardware)], [
            'wall1', 'wall1_door0_frame0', 'wall1_door0_leftpanel0',
            'wall1_door0_leftpanel0_hardware0'])
        self.assertEqual((frame.parent, panel.parent, hardware.parent), (root, frame, panel))
        self.assertEqual(addon.automatic_tools.report_for(bpy.context.scene), ())

    def test_duplicate_door_increments_door_not_frame(self):
        root = make_mesh('wall0')
        make_mesh('wall0_door0_frame0', root)
        frame = make_mesh('wall0_door0_frame0.001', root)
        panel = make_mesh('wall0_door0_leftpanel0.001', frame)
        addon.automatic_tools.run_pass()
        self.assertEqual(frame.name, 'wall0_door1_frame0')
        self.assertEqual(panel.name, 'wall0_door1_leftpanel0')
        self.assertEqual(addon.automatic_tools.report_for(bpy.context.scene), ())

    def test_generic_duplicate_stays_an_audit_warning(self):
        make_mesh('Cube')
        obj = make_mesh('Cube.001')
        addon.automatic_tools.run_pass()
        self.assertEqual(obj.name, 'Cube0')
        self.assertTrue(addon.automatic_tools.warning_for(obj))
        self.assertEqual(len(addon.automatic_tools.report_for(bpy.context.scene)), 2)

    def test_two_duplicate_doors_inside_a_duplicate_wall_keep_their_panels(self):
        make_mesh('wall0')
        root = make_mesh('wall0.001')
        frames, panels = [], []
        for suffix in ('.001', '.002'):
            frames.append(make_mesh('wall0_door0_frame0' + suffix, root))
            panels.append(make_mesh('wall0_door0_leftpanel0' + suffix, frames[-1]))
        addon.automatic_tools.run_pass()
        self.assertEqual(root.name, 'wall1')
        self.assertEqual([obj.name for obj in frames], ['wall1_door0_frame0', 'wall1_door1_frame0'])
        self.assertEqual([obj.name for obj in panels], ['wall1_door0_leftpanel0', 'wall1_door1_leftpanel0'])
        self.assertEqual(addon.automatic_tools.report_for(bpy.context.scene), ())

    def test_mid_assignment_failure_restores_all_original_names(self):
        from parenting_under_test.live_naming import assign_atomic
        class Item:
            library = override_library = None
            is_editable = True
            users_scene = ()
            def __init__(self, name, fail=False):
                self._name, self.fail = name, fail
            @property
            def name(self):
                return self._name
            @name.setter
            def name(self, value):
                if self.fail and value == 'wall3':
                    self.fail = False
                    raise RuntimeError('Simulated write failure')
                self._name = value
        one, two = Item('wall0'), Item('wall1', True)
        with self.assertRaises(RuntimeError):
            assign_atomic([(one, 'wall2'), (two, 'wall3')], [one, two])
        self.assertEqual((one.name, two.name), ('wall0', 'wall1'))

    def test_live_rename_waits_for_object_mode(self):
        make_mesh('wall0')
        obj = make_mesh('wall0.001')
        select(obj)
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            addon.automatic_tools.run_pass()
            self.assertEqual(obj.name, 'wall0.001')
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        addon.automatic_tools.run_pass()
        self.assertEqual(obj.name, 'wall1')

    def test_audit_tracks_parent_errors_and_excluded_family_without_mutation(self):
        wall = make_mesh('wall0')
        floor = make_mesh('floor0')
        obj = make_mesh('wall0_chrome0', floor)
        primitive = make_mesh('wall0_primitive0', wall)
        addon.automatic_tools.run_pass()
        self.assertTrue(addon.automatic_tools.warning_for(obj))
        self.assertEqual(obj.parent, floor)
        obj.parent = wall
        addon.automatic_tools.run_pass()
        self.assertFalse(addon.automatic_tools.warning_for(obj))
        self.assertTrue(addon.automatic_tools.warning_for(primitive))
        obj.parent = None
        addon.automatic_tools.run_pass()
        self.assertTrue(addon.automatic_tools.warning_for(obj))

    def test_live_normalized_structural_root_still_parents_as_subwall(self):
        make_mesh('wall0')
        obj = make_mesh('wall0.001')
        target = make_mesh('ceiling0')
        addon.automatic_tools.run_pass()
        self.assertEqual(obj.name, 'wall1')
        select(target, obj)
        self.assertEqual(bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT'), {'FINISHED'})
        self.assertEqual(obj.name, 'ceiling0_wall0')

    def test_protected_multiscene_hierarchy_is_not_partly_renamed(self):
        make_mesh('wall0')
        root = make_mesh('wall0.001')
        child = make_mesh('wall0_chrome0', root)
        other = bpy.data.scenes.new('SharedTest')
        other.collection.objects.link(child)
        try:
            addon.automatic_tools.run_pass()
            self.assertEqual(root.name, 'wall0.001')
            self.assertEqual(child.name, 'wall0_chrome0')
            self.assertTrue(addon.automatic_tools.warning_for(root))
        finally:
            bpy.data.scenes.remove(other)

    def test_rename_options_are_independent_and_materials_unchanged(self):
        make_mesh('wall0')
        obj = make_mesh('wall0.001')
        material = bpy.data.materials.new('Surface.001')
        original_option = addon.automatic_tools.option
        try:
            addon.automatic_tools.option = lambda name: name == 'automatic_audit'
            addon.automatic_tools.run_pass()
            self.assertEqual(obj.name, 'wall0.001')
            self.assertTrue(addon.automatic_tools.report_for(bpy.context.scene))
            addon.automatic_tools.option = lambda name: name == 'live_rename'
            addon.automatic_tools.run_pass()
            self.assertEqual(obj.name, 'wall1')
            self.assertEqual(addon.automatic_tools.report_for(bpy.context.scene), ())
            self.assertEqual(material.name, 'Surface.001')
        finally:
            addon.automatic_tools.option = original_option
            bpy.data.materials.remove(material)

    def test_undo_snapshot_is_not_immediately_renormalized(self):
        make_mesh('wall0')
        obj = make_mesh('wall0.001')
        addon.automatic_tools._before_undo(None)
        addon.automatic_tools._after_undo(None)
        addon.automatic_tools.run_pass()
        self.assertEqual(obj.name, 'wall0.001')
        obj.name = 'wall0.002'
        addon.automatic_tools.run_pass()
        self.assertEqual(obj.name, 'wall1')

    def test_load_enable_disable_callbacks_and_initial_pass(self):
        runtime = addon.automatic_tools
        self.assertTrue(bpy.app.timers.is_registered(runtime._tick))
        runtime._before_load(None)
        self.assertFalse(bpy.app.timers.is_registered(runtime._tick))
        make_mesh('floor0')
        obj = make_mesh('floor0.001')
        runtime._after_load(None)
        self.assertTrue(bpy.app.timers.is_registered(runtime._tick))
        runtime.run_pass()
        self.assertEqual(obj.name, 'floor1')
        addon.unregister()
        self.assertFalse(bpy.app.timers.is_registered(runtime._tick))
        for name, callback in runtime.HANDLERS:
            self.assertNotIn(callback, getattr(bpy.app.handlers, name))
        addon.register()
        for name, callback in runtime.HANDLERS:
            self.assertEqual(list(getattr(bpy.app.handlers, name)).count(callback), 1)

    def test_utf8_overflow_rejects_whole_group(self):
        from parenting_under_test.live_naming import assign_atomic
        one = make_mesh('wall0')
        two = make_mesh('wall1')
        with self.assertRaises(ValueError):
            assign_atomic([(one, 'wall2'), (two, 'ñ' * 32)], bpy.data.objects)
        self.assertEqual((one.name, two.name), ('wall0', 'wall1'))


try:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ParentingTests)
    suite.addTests(AutomaticTests(name) for name in AutomaticTests.__dict__
                   if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError('Blender integration checks failed')
finally:
    addon.unregister()
