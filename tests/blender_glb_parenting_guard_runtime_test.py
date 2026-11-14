"""Native GLB export preflight on both Blender 4.2 and 5.2, UI and background."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback
import bpy
import addon_utils

OUT = Path(os.environ['J3D_TEST_ROOT'])
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = Path(os.environ.get('J3D_GUARD_ADDON_SOURCE', str(Path(__file__).resolve().parents[1])))
spec = importlib.util.spec_from_file_location('guard_addon_under_test', SOURCE / '__init__.py')
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.view.show_splash = False
addon_utils.enable('io_scene_gltf2', default_set=False)
import io_scene_gltf2
native = io_scene_gltf2.ExportGLTF2.execute
addon.register()
guard = __import__(spec.name + '.glb_parenting_guard', fromlist=['*'])
overlay = __import__(spec.name + ('.name_overlays' if bpy.app.version < (5,0,0) else '.selection_overlay'), fromlist=['*'])


def mesh(name):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


root = mesh('wall1')
child = mesh('wall1_estufa0')
child.location = (4,2,1)
bpy.context.view_layer.update()
before = (child.name, child.parent, child.matrix_world.copy())
overlay._OverlayRuntime.invalid_names_enabled = True
assert overlay.label_style(child.name, child)[1] == overlay.NORMAL_COLOR
child.name = 'wall1_unknownfamily0'
assert overlay.label_style(child.name, child)[1] == overlay.ERROR_COLOR
child.name = before[0]


def export(name, **kwargs):
    return bpy.ops.export_scene.gltf('EXEC_DEFAULT', filepath=str(OUT / (name + '.glb')),
                                    export_format='GLB', use_active_scene=True, **kwargs)


def pending(name):
    assert export(name) == {'CANCELLED'}
    assert not (OUT / (name + '.glb')).exists()
    token, = guard._state['pending']
    return token


def silence_popup_timer():
    for fn in tuple(guard._state['timers']):
        if bpy.app.timers.is_registered(fn):
            bpy.app.timers.unregister(fn)
    guard._state['timers'].clear()


def finish():
    try:
        if not bpy.app.background:
            # The first real popup was cancelled. The next export is a fresh decision.
            for token in list(guard._state['pending']):
                guard._state['pending'].pop(token)
            token = pending('approved')
            silence_popup_timer()
            assert bpy.ops.j3d_naming.glb_parenting_warning('EXEC_DEFAULT', token=token, action='EXPORT') == {'FINISHED'}
            assert (OUT / 'approved.glb').read_bytes()[:4] == b'glTF'
            assert before == (child.name, child.parent, child.matrix_world.copy())
            # Approval does not leak into a subsequent export.
            token = pending('review')
            silence_popup_timer()
            assert bpy.ops.j3d_naming.glb_parenting_warning('EXEC_DEFAULT', token=token, action='REVIEW') == {'FINISHED'}
            assert not (OUT / 'review.glb').exists()
            assert child.select_get() and bpy.context.active_object == child
            assert before == (child.name, child.parent, child.matrix_world.copy())
        else:
            assert export('blocked') == {'CANCELLED'}
            assert not (OUT / 'blocked.glb').exists()
        # Selection filter ignores an orphan that is not being exported.
        child.select_set(False)
        root.select_set(True)
        bpy.context.view_layer.objects.active = root
        assert export('root-only', use_selection=True) == {'FINISHED'}
        child.hide_set(True)
        assert not guard.missing_parents(bpy.context, {'use_active_scene':True,'use_visible':True}, guard._state['rules'])
        child.hide_set(False)
        child.hide_render = True
        assert not guard.missing_parents(bpy.context, {'use_active_scene':True,'use_renderable':True}, guard._state['rules'])
        child.hide_render = False
        # Existing parents and structural roots do not prompt.
        child.parent = root
        assert export('parented') == {'FINISHED'}
        addon.unregister()
        assert io_scene_gltf2.ExportGLTF2.execute is native
        addon.register()
        first = io_scene_gltf2.ExportGLTF2.execute
        guard.register(guard._state['rules'])
        assert io_scene_gltf2.ExportGLTF2.execute is first
        addon.unregister()
        assert io_scene_gltf2.ExportGLTF2.execute is native
        result = {'success': True, 'version':bpy.app.version_string, 'foreground':not bpy.app.background,
                  'checks':['family-only color','native export interception','no file before approval',
                            'selection/visibility/render filters','parented export','hook lifecycle',
                            'one-export approval and review preserve geometry/parent/names']}
        (OUT / 'guard-result.json').write_text(json.dumps(result, indent=2))
        print('GLB_PARENTING_GUARD_PASS', result, flush=True)
        if not bpy.app.background:
            bpy.ops.wm.quit_blender()
    except Exception:
        traceback.print_exc()
        (OUT / 'guard-result.json').write_text(json.dumps({'success':False,'error':traceback.format_exc()}))
        if bpy.app.background:
            raise
        os._exit(1)


if bpy.app.background:
    finish()
else:
    drawn = []
    original_draw = guard._state['dialog'].draw
    def observed_draw(self, context):
        drawn.append(context.window.as_pointer())
        original_draw(self, context)
    guard._state['dialog'].draw = observed_draw
    def capture_popup():
        assert drawn, 'The export warning dialog was not drawn'
        assert guard._state['pending'], 'The file-browser export did not pause'
        assert not (OUT / 'cancelled.glb').exists()
        bpy.ops.screen.screenshot(filepath=str(OUT / 'export-popup.png'))
        bpy.context.window.event_simulate(type='ESC', value='PRESS')
        bpy.context.window.event_simulate(type='ESC', value='RELEASE')
        bpy.app.timers.register(finish, first_interval=.4)
    def confirm_browser():
        browser = next((w, a) for w in bpy.context.window_manager.windows
                       for a in w.screen.areas if a.type == 'FILE_BROWSER')
        with bpy.context.temp_override(window=browser[0], area=browser[1]):
            bpy.ops.file.execute('EXEC_DEFAULT')
        bpy.app.timers.register(capture_popup, first_interval=1.0)
    def open_browser():
        assert bpy.ops.export_scene.gltf('INVOKE_DEFAULT', filepath=str(OUT/'cancelled.glb'),
                    export_format='GLB', use_active_scene=True) == {'RUNNING_MODAL'}
        bpy.app.timers.register(confirm_browser, first_interval=1.0)
    def dismiss_startup():
        bpy.context.window.event_simulate(type='ESC', value='PRESS')
        bpy.context.window.event_simulate(type='ESC', value='RELEASE')
        bpy.app.timers.register(open_browser, first_interval=.4)
    bpy.app.timers.register(dismiss_startup, first_interval=.8)
