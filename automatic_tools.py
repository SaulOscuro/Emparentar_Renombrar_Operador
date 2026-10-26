"""Lifecycle, automatic audit reports and delayed NoDot normalization."""
import traceback

import bpy
from bpy.app.handlers import persistent

from . import live_audit, live_naming

_enabled = False
_busy = False
_loading = False
_owner = object()
_snapshot = None
_undo_snapshot = None
_reports = {}
_last_renamed = 0
_last_error = ''


def preferences():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def option(name):
    return getattr(preferences(), name, True)


def fingerprint():
    return (option('automatic_audit'), option('live_rename'), tuple(
        (obj.as_pointer(), obj.name, obj.parent.as_pointer() if obj.parent else 0,
         obj.type, live_naming.editable(obj),
         tuple(scene.as_pointer() for scene in obj.users_scene))
        for obj in bpy.data.objects))


def report_for(scene):
    return _reports.get(scene.as_pointer(), ()) if option('automatic_audit') else ()


def warning_for(obj):
    # A cheap per-object check keeps the overlay correct during the delay and
    # when switching scenes. The full report is refreshed outside draw callbacks.
    return bool(live_audit.object_issues(obj)) if option('automatic_audit') else False


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def run_pass(force=False):
    global _busy, _snapshot, _reports, _last_renamed, _last_error
    if not _enabled or _busy or _loading:
        return 0
    if bpy.context.mode != 'OBJECT' or bpy.app.is_job_running('RENDER'):
        return 0
    current = fingerprint()
    if not force and current == _snapshot:
        return 0
    _busy = True
    try:
        failures = {}
        count = 0
        if option('live_rename') and current != _undo_snapshot:
            count, failures = live_naming.normalize_objects(bpy.data.objects)
        _reports = ({scene.as_pointer(): live_audit.audit_scene(scene, failures)
                     for scene in bpy.data.scenes} if option('automatic_audit') else {})
        _last_renamed = count
        _last_error = ''
        _snapshot = fingerprint()
        _redraw()
        return count
    finally:
        _busy = False


def _tick():
    global _last_error
    if not _enabled:
        return None
    try:
        run_pass()
    except Exception as exc:
        # Keep monitoring after a recoverable Blender/context error, but avoid
        # flooding the console every second with the same failure.
        if _last_error != str(exc):
            traceback.print_exc()
        _last_error = str(exc)
    return 1.0


def schedule(*_args):
    if not _enabled or _busy or _loading:
        return
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    bpy.app.timers.register(_tick, first_interval=0.25)


def _subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    for prop in ('name', 'parent'):
        bpy.msgbus.subscribe_rna(key=(bpy.types.Object, prop), owner=_owner,
                                args=(), notify=schedule)


@persistent
def _depsgraph(_scene, graph):
    # Avoid an audit on each viewport redraw. Name-only changes also have msgbus
    # and the one-second fallback for Python changes with no notification.
    if any(isinstance(update.id, bpy.types.Object) for update in graph.updates):
        schedule()


@persistent
def _before_load(_dummy):
    global _loading, _snapshot, _reports, _undo_snapshot
    _loading = True
    _snapshot = None
    _undo_snapshot = None
    _reports = {}
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


@persistent
def _after_load(_dummy):
    global _loading
    _loading = False
    _subscribe()
    schedule()


@persistent
def _before_undo(_dummy):
    global _loading
    _loading = True


@persistent
def _after_undo(_dummy):
    global _loading, _snapshot, _undo_snapshot
    _loading = False
    _snapshot = None
    # Do not immediately reapply a name change that the user just undid.
    _undo_snapshot = fingerprint()
    schedule()


HANDLERS = (
    ('load_pre', _before_load), ('load_post', _after_load),
    ('depsgraph_update_post', _depsgraph),
    ('undo_pre', _before_undo), ('undo_post', _after_undo),
    ('redo_pre', _before_undo), ('redo_post', _after_undo),
)


def settings_changed(_self, _context):
    global _snapshot
    _snapshot = None
    schedule()
    _redraw()


class ERO_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    automatic_audit: bpy.props.BoolProperty(
        name='Auditoría automática', default=True, update=settings_changed,
        description='Revisa nombres y padres al cargar y editar la escena')
    live_rename: bpy.props.BoolProperty(
        name='Live NoDot Rename', default=True, update=settings_changed,
        description='Sustituye .001 por índices libres en objetos de malla')

    def draw(self, _context):
        self.layout.prop(self, 'automatic_audit')
        self.layout.prop(self, 'live_rename')
        self.layout.label(text='Activos al habilitar, actualizar y abrir Blender.')


class ERO_PT_automatic_audit(bpy.types.Panel):
    bl_label = 'Auditoría automática'
    bl_idname = 'ERO_PT_automatic_audit'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Emparentar'

    def draw(self, context):
        layout = self.layout
        prefs = preferences()
        if prefs:
            layout.prop(prefs, 'automatic_audit')
            layout.prop(prefs, 'live_rename')
        if _last_error:
            layout.label(text=_last_error, icon='ERROR')
        if not option('automatic_audit'):
            layout.label(text='Auditoría desactivada')
            return
        if _snapshot is None:
            layout.label(text='Revisión pendiente…', icon='TIME')
            return
        report = report_for(context.scene)
        layout.label(text=f'{len(report)} objetos con avisos', icon='INFO')
        active = context.active_object
        if active:
            reasons = live_audit.object_issues(active)
            if reasons:
                box = layout.box()
                box.label(text=active.name, icon='ERROR')
                for reason in reasons:
                    box.label(text=reason)
        for name, reasons in report[:20]:
            box = layout.box()
            box.label(text=name, icon='ERROR')
            for reason in reasons:
                box.label(text=reason)
        if len(report) > 20:
            layout.label(text=f'{len(report) - 20} avisos más; selecciona un objeto para ver el detalle')


CLASSES = (ERO_Preferences, ERO_PT_automatic_audit)


def register():
    global _enabled, _snapshot, _loading, _undo_snapshot
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _enabled = True
    _loading = False
    _snapshot = None
    _undo_snapshot = None
    _subscribe()
    for name, callback in HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback not in handlers:
            handlers.append(callback)
    schedule()


def unregister():
    global _enabled, _reports, _snapshot, _undo_snapshot
    _enabled = False
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    bpy.msgbus.clear_by_owner(_owner)
    for name, callback in HANDLERS:
        handlers = getattr(bpy.app.handlers, name)
        if callback in handlers:
            handlers.remove(callback)
    _reports = {}
    _snapshot = None
    _undo_snapshot = None
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
