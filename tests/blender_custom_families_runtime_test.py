"""Custom families in real Blender: UI confirmation, scene safety and parenting."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import bpy
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if not bpy.app.background or 'J3D_NAMING_CONFIG' not in os.environ:
    raise RuntimeError('Requires background Blender and an isolated J3D_NAMING_CONFIG.')
scratch = Path(os.environ['J3D_TEST_ROOT']) / 'custom-families'
scratch.mkdir(parents=True, exist_ok=True)
isolated = tempfile.TemporaryDirectory(dir=scratch)
os.environ['J3D_NAMING_CONFIG'] = str(Path(isolated.name) / 'families.json')
spec = importlib.util.spec_from_file_location('custom_families_under_test', ROOT / '__init__.py')
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
from custom_families_under_test import family_store as store, family_ui as ui, naming_rules as rules, name_overlays as overlay
PREFIX = 'ero'
PARENT_OPERATOR = 'object.reparent_and_rename_smart'
FAMILY_PROPERTY = 'familia_sin_regla'
ACCEPT_CLASS = ui.ERO_OT_accept_selected_family


def operation(identifier, **kwargs):
    group, name = identifier.split('.')
    return getattr(getattr(bpy.ops, group), name)(**kwargs)


def mesh(name, parent=None):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def select(parent, *children):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (parent, *children):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parent
    bpy.context.view_layer.update()


def rejected(callback):
    try:
        result = callback()
    except RuntimeError:
        return
    assert result == {'CANCELLED'}, result


bpy.ops.wm.read_factory_settings(use_empty=True)
addon.register()
try:
    parent = mesh('wall3')
    first, second = mesh('wall3_wood0', parent), mesh('wall3_wood1', parent)
    select(first)
    snapshot = [(o.name, o.parent, o.matrix_world.copy(), o.data) for o in (first, second)]
    assert rules.unsupported_reason(first.name) is not None
    # Invoke the same confirmation boundary without opening a UI window.
    prompts = []
    probe = SimpleNamespace(family='', source_name='', report=lambda *args: None)
    context = SimpleNamespace(active_object=first, window_manager=SimpleNamespace(
        invoke_props_dialog=lambda op, **kwargs: prompts.append(op.family) or {'RUNNING_MODAL'}))
    assert ACCEPT_CLASS.invoke(probe, context, None) == {'RUNNING_MODAL'}
    assert prompts == ['wood'] and not store.config_path().exists()
    assert rules.unsupported_reason(first.name) is not None  # Cancel makes no change.
    assert operation(PREFIX + '.accept_selected_family', family=probe.family, source_name=probe.source_name) == {'FINISHED'}
    assert store.families() == {'wood'}
    assert snapshot == [(o.name, o.parent, o.matrix_world.copy(), o.data) for o in (first, second)]
    assert rules.unsupported_reason(first.name) is None  # Previously cached warning clears.
    overlay._OverlayRuntime.invalid_names_enabled = True
    assert overlay.label_style(first.name, first)[1] == overlay.NORMAL_COLOR
    first.parent = None
    assert overlay.label_style(first.name, first)[1] == overlay.ERROR_COLOR
    first.parent = parent
    for name in ('wall3_wood', 'wall3_wood0_cube0', 'wall3_stuff0', 'wall3_primitive0'):
        assert rules.unsupported_reason(name) is not None, name
    # Accepting the active family only needs the mesh. It does not rename it.
    select(second)
    before = store.config_path().read_bytes()
    rejected(lambda: operation(PREFIX + '.accept_selected_family', family='wood', source_name=first.name))
    assert store.config_path().read_bytes() == before
    # Rename/parent operations preserve the newly admitted family.
    target = mesh('floor0')
    select(target, first)
    world = first.matrix_world.copy()
    assert operation(PARENT_OPERATOR) == {'FINISHED'}
    assert first.name == 'floor0_wood0' and first.parent == target
    assert first.matrix_world == world
    cube = mesh('Cube')
    select(target, cube)
    assert operation(PARENT_OPERATOR, **{FAMILY_PROPERTY: 'wood'}) == {'FINISHED'}
    assert cube.name == 'floor0_wood1' and cube.parent == target
    # A second separately loaded copy represents the other add-on/version.
    other_spec = importlib.util.spec_from_file_location('other_store', ROOT / 'family_store.py')
    other = importlib.util.module_from_spec(other_spec)
    other_spec.loader.exec_module(other)
    assert other.families() == {'wood'}
    other.set_family('marble', accepted=True)
    store.refresh(force=True)
    assert rules.unsupported_reason('wall3_marble0') is None
    assert operation(PREFIX + '.remove_custom_family', family='wood') == {'FINISHED'}
    assert rules.unsupported_reason('floor0_wood0') is not None
    assert first.name == 'floor0_wood0' and first.parent == target
    assert operation(PREFIX + '.add_custom_family', family='WOOD') == {'FINISHED'}
    assert rules.unsupported_reason('floor0_wood0') is None
    # Register/unregister leaves a single timer and no leaked callbacks.
    ui.register()
    assert bpy.app.timers.is_registered(ui._tick)
    ui.unregister()
    assert not bpy.app.timers.is_registered(ui._tick)
    ui.register()
    assert bpy.app.timers.is_registered(ui._tick)
finally:
    addon.unregister()
    isolated.cleanup()
assert not bpy.app.timers.is_registered(ui._tick)
print('CUSTOM_FAMILIES_RUNTIME_PASS: confirmation, persistence, live rules, parent errors, selection safety and lifecycle')
