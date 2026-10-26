# SPDX-License-Identifier: GPL-3.0-or-later
"""Name overlays adapted from SaulOscuro/J3DSyncManager-2.0 selection_overlay.py.

Selection/all-name drawing retains the original viewport helpers. Unsupported-name
highlighting uses this extension's shared parenting rules without editing objects.
"""

from __future__ import annotations

import blf
import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector
from bpy.types import Operator
from bpy.app.handlers import persistent
from .naming_rules import unsupported_reason


class _OverlayRuntime:
    """Transient state shared by the menu toggles and draw callback."""

    enabled = False
    all_names_enabled = False
    invalid_names_enabled = False
    generation = 0
    draw_handle = None
    mouse_x = -1
    mouse_y = -1
    window_pointer = 0

    @classmethod
    def enable(cls, context, event) -> int:
        cls.generation += 1
        cls.enabled = True
        region = getattr(context, "region", None)
        default_x = region.x + (region.width // 2) if region is not None else 0
        default_y = region.y + (region.height // 2) if region is not None else 0
        cls.mouse_x = getattr(event, "mouse_x", default_x)
        cls.mouse_y = getattr(event, "mouse_y", default_y)
        cls.window_pointer = context.window.as_pointer()

        cls.ensure_draw_handler()
        _tag_viewports_for_redraw(context)
        return cls.generation

    @classmethod
    def disable(cls, context=None) -> None:
        cls.generation += 1
        cls.enabled = False
        cls.mouse_x = -1
        cls.mouse_y = -1
        cls.window_pointer = 0
        cls.release_draw_handler_if_unused()

        if context is not None:
            _tag_viewports_for_redraw(context)

    @classmethod
    def enable_all_names(cls, context) -> None:
        cls.all_names_enabled = True
        cls.ensure_draw_handler()
        _tag_viewports_for_redraw(context)

    @classmethod
    def disable_all_names(cls, context=None) -> None:
        cls.all_names_enabled = False
        cls.release_draw_handler_if_unused()
        if context is not None:
            _tag_viewports_for_redraw(context)

    @classmethod
    def enable_invalid_names(cls, context) -> None:
        cls.invalid_names_enabled = True
        cls.ensure_draw_handler()
        _tag_viewports_for_redraw(context)

    @classmethod
    def disable_invalid_names(cls, context=None) -> None:
        cls.invalid_names_enabled = False
        cls.release_draw_handler_if_unused()
        if context is not None:
            _tag_viewports_for_redraw(context)

    @classmethod
    def ensure_draw_handler(cls) -> None:
        if cls.draw_handle is None:
            cls.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
                _draw_overlays,
                (),
                "WINDOW",
                "POST_PIXEL",
            )

    @classmethod
    def release_draw_handler_if_unused(cls) -> None:
        if cls.enabled or cls.all_names_enabled or cls.invalid_names_enabled or cls.draw_handle is None:
            return

        try:
            bpy.types.SpaceView3D.draw_handler_remove(cls.draw_handle, "WINDOW")
        except (ReferenceError, RuntimeError, ValueError):
            pass
        cls.draw_handle = None

    @classmethod
    def shutdown(cls, context=None) -> None:
        cls.generation += 1
        cls.enabled = False
        cls.all_names_enabled = False
        cls.invalid_names_enabled = False
        cls.mouse_x = -1
        cls.mouse_y = -1
        cls.window_pointer = 0
        cls.release_draw_handler_if_unused()
        if context is not None:
            _tag_viewports_for_redraw(context)


def _tag_viewports_for_redraw(context) -> None:
    """Refresh all 3D Viewports so labels update immediately."""

    window_manager = getattr(context, "window_manager", None)
    if window_manager is None:
        return

    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _active_selected_object(context):
    view_layer = getattr(context, "view_layer", None)
    if view_layer is None:
        return None

    obj = view_layer.objects.active
    if obj is None:
        return None

    try:
        return obj if obj.select_get(view_layer=view_layer) else None
    except (ReferenceError, RuntimeError):
        return None


def _valid_draw_context():
    context = bpy.context
    area = context.area
    region = context.region

    if (
        area is None
        or area.type != "VIEW_3D"
        or region is None
        or region.type != "WINDOW"
        or not context.space_data.overlay.show_overlays
    ):
        return None

    return context, region


def _font_metrics(context):
    ui_scale = max(0.5, float(context.preferences.system.ui_scale))
    font_id = 0
    font_size = max(10, round(12 * ui_scale))
    blf.size(font_id, font_size)
    return font_id, ui_scale


def _draw_text(font_id, label, x, y, color=(1.0, 1.0, 1.0, 1.0)) -> None:
    blf.enable(font_id, blf.SHADOW)
    try:
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 0.9)
        blf.shadow_offset(font_id, 1, -1)
        blf.color(font_id, *color)
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, label)
    finally:
        blf.disable(font_id, blf.SHADOW)


def _visual_center_world(obj, depsgraph):
    """Return the evaluated bounding-box center, falling back to the origin."""

    try:
        evaluated_obj = obj.evaluated_get(depsgraph)
        corners = evaluated_obj.bound_box
        if corners and not all(
            tuple(corner) == (-1.0, -1.0, -1.0) for corner in corners
        ):
            local_center = sum(
                (Vector(corner) for corner in corners),
                Vector(),
            ) / 8.0
            return evaluated_obj.matrix_world @ local_center
        return evaluated_obj.matrix_world.translation.copy()
    except (ReferenceError, RuntimeError, TypeError, ValueError):
        try:
            return obj.matrix_world.translation.copy()
        except ReferenceError:
            return None


NORMAL_COLOR = (1.0, 1.0, 1.0, 1.0)
ERROR_COLOR = (1.0, 0.12, 0.08, 1.0)


def label_style(name, obj=None):
    """The warning color takes priority when multiple overlays are enabled."""
    from .automatic_tools import warning_for
    invalid = _OverlayRuntime.invalid_names_enabled and (
        unsupported_reason(name) is not None or (obj is not None and warning_for(obj)))
    return (f'! {name}', ERROR_COLOR, 1.2) if invalid else (name, NORMAL_COLOR, 1.0)


def visible_name_labels(context):
    """Plan labels for visible objects without selection requirements or edits."""
    for obj in context.visible_objects:
        name = obj.name
        invalid = label_style(name, obj)[1] == ERROR_COLOR
        if _OverlayRuntime.all_names_enabled or invalid:
            yield obj, label_style(name, obj)


def _draw_all_object_names(context, region, font_id, ui_scale) -> None:
    region_data = context.region_data
    if region_data is None:
        return

    depsgraph = context.evaluated_depsgraph_get()

    for obj, (label, color, scale) in visible_name_labels(context):
        center_world = _visual_center_world(obj, depsgraph)
        if center_world is None:
            continue

        center_2d = location_3d_to_region_2d(
            region,
            region_data,
            center_world,
            default=None,
        )
        if center_2d is None:
            continue

        x, y = center_2d
        blf.size(font_id, max(10, round(12 * ui_scale * scale)))
        text_width, text_height = blf.dimensions(font_id, label)
        draw_x = x - (text_width * 0.5)
        draw_y = y - (text_height * 0.5)

        if (
            draw_x + text_width < 0
            or draw_x > region.width
            or draw_y + text_height < 0
            or draw_y > region.height
        ):
            continue

        _draw_text(font_id, label, draw_x, draw_y, color=color)


def cursor_label_position(
    mouse_x,
    mouse_y,
    text_width,
    text_height,
    region_width,
    region_height,
    ui_scale,
):
    """Place a cursor label inside the viewport, flipping at its edges."""

    cursor_gap = round(16 * ui_scale)
    edge_padding = round(6 * ui_scale)

    draw_x = mouse_x + cursor_gap
    draw_y = mouse_y + cursor_gap

    if draw_x + text_width + edge_padding > region_width:
        draw_x = mouse_x - text_width - cursor_gap
    if draw_y + text_height + edge_padding > region_height:
        draw_y = mouse_y - text_height - cursor_gap

    draw_x = max(
        edge_padding,
        min(draw_x, region_width - text_width - edge_padding),
    )
    draw_y = max(
        edge_padding,
        min(draw_y, region_height - text_height - edge_padding),
    )
    return draw_x, draw_y


def _draw_selection_name(context, region, font_id, ui_scale) -> None:
    """Draw the active selected object's name next to the mouse cursor."""

    window = context.window
    if (
        not _OverlayRuntime.enabled
        or window is None
        or window.as_pointer() != _OverlayRuntime.window_pointer
    ):
        return

    mouse_x = _OverlayRuntime.mouse_x - region.x
    mouse_y = _OverlayRuntime.mouse_y - region.y
    if not (0 <= mouse_x < region.width and 0 <= mouse_y < region.height):
        return

    obj = _active_selected_object(context)
    if obj is None:
        return

    label, color, scale = label_style(obj.name, obj)
    blf.size(font_id, max(10, round(12 * ui_scale * scale)))
    text_width, text_height = blf.dimensions(font_id, label)
    draw_x, draw_y = cursor_label_position(
        mouse_x,
        mouse_y,
        text_width,
        text_height,
        region.width,
        region.height,
        ui_scale,
    )
    _draw_text(font_id, label, draw_x, draw_y, color=color)


def _draw_overlays() -> None:
    draw_context = _valid_draw_context()
    if draw_context is None:
        return

    context, region = draw_context
    font_id, ui_scale = _font_metrics(context)

    if _OverlayRuntime.all_names_enabled or _OverlayRuntime.invalid_names_enabled:
        _draw_all_object_names(context, region, font_id, ui_scale)
    if _OverlayRuntime.enabled:
        _draw_selection_name(context, region, font_id, ui_scale)


class ERO_OT_selection_name_overlay_toggle(Operator):
    """Toggle a cursor-following label for the active selected object."""

    bl_idname = "ero.selection_name_overlay_toggle"
    bl_label = "Selection Name Overlay"
    bl_description = "Show the active selected object's name beside the cursor"
    bl_options = {"INTERNAL"}

    _generation = 0

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        if _OverlayRuntime.enabled:
            _OverlayRuntime.disable(context)
            self.report({"INFO"}, "Selection Name Overlay disabled")
            return {"FINISHED"}

        self._generation = _OverlayRuntime.enable(context, event)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "Selection Name Overlay enabled")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if (
            not _OverlayRuntime.enabled
            or self._generation != _OverlayRuntime.generation
        ):
            return {"FINISHED"}

        if context.window is None or (
            context.window.as_pointer() != _OverlayRuntime.window_pointer
        ):
            _OverlayRuntime.disable(context)
            return {"FINISHED"}

        _OverlayRuntime.mouse_x = event.mouse_x
        _OverlayRuntime.mouse_y = event.mouse_y
        _tag_viewports_for_redraw(context)
        return {"PASS_THROUGH"}

    def cancel(self, context):
        if self._generation == _OverlayRuntime.generation:
            _OverlayRuntime.disable(context)


class ERO_OT_all_object_names_overlay_toggle(Operator):
    """Toggle labels at the visual center of every visible object."""

    bl_idname = "ero.all_object_names_overlay_toggle"
    bl_label = "All Object Names"
    bl_description = "Show every visible object's name at its visual center"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if _OverlayRuntime.all_names_enabled:
            _OverlayRuntime.disable_all_names(context)
            self.report({"INFO"}, "All Object Names disabled")
        else:
            _OverlayRuntime.enable_all_names(context)
            self.report({"INFO"}, "All Object Names enabled")
        return {"FINISHED"}


class ERO_OT_unsupported_names_overlay_toggle(Operator):
    """Show unsupported family names in red without changing objects."""

    bl_idname = "ero.unsupported_names_overlay_toggle"
    bl_label = "Unsupported Names (Red)"
    bl_description = "Resalta en rojo los nombres fuera de las familias válidas, incluido primitive"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        if _OverlayRuntime.invalid_names_enabled:
            _OverlayRuntime.disable_invalid_names(context)
        else:
            _OverlayRuntime.enable_invalid_names(context)
        return {"FINISHED"}


CLASSES = (
    ERO_OT_selection_name_overlay_toggle,
    ERO_OT_all_object_names_overlay_toggle,
    ERO_OT_unsupported_names_overlay_toggle,
)


def _draw_view_menu(self, _context) -> None:
    layout = self.layout
    previous_context = layout.operator_context
    layout.operator_context = 'INVOKE_REGION_WIN'
    layout.separator()
    layout.operator(
        ERO_OT_selection_name_overlay_toggle.bl_idname,
        text="Selection Name Overlay",
        icon="CHECKBOX_HLT" if _OverlayRuntime.enabled else "CHECKBOX_DEHLT",
        depress=_OverlayRuntime.enabled,
    )
    layout.operator(
        ERO_OT_all_object_names_overlay_toggle.bl_idname,
        text="All Object Names",
        icon=(
            "CHECKBOX_HLT"
            if _OverlayRuntime.all_names_enabled
            else "CHECKBOX_DEHLT"
        ),
        depress=_OverlayRuntime.all_names_enabled,
    )
    layout.operator(
        ERO_OT_unsupported_names_overlay_toggle.bl_idname,
        text="Unsupported Names (Red)",
        icon="CHECKBOX_HLT" if _OverlayRuntime.invalid_names_enabled else "CHECKBOX_DEHLT",
        depress=_OverlayRuntime.invalid_names_enabled,
    )
    layout.operator_context = previous_context


_startup_requested = False


def _enable_overlay_on_startup():
    """Start the modal mouse listener once a 3D Viewport is available."""

    global _startup_requested

    if not _startup_requested:
        return None

    if _OverlayRuntime.enabled:
        _startup_requested = False
        return None

    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return 0.5

    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue

        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue

            region = next(
                (item for item in area.regions if item.type == "WINDOW"),
                None,
            )
            if region is None:
                continue

            try:
                with bpy.context.temp_override(
                    window=window,
                    screen=screen,
                    area=area,
                    region=region,
                ):
                    result = bpy.ops.ero.selection_name_overlay_toggle(
                        "INVOKE_DEFAULT"
                    )
            except (RuntimeError, TypeError):
                continue

            if "RUNNING_MODAL" in result:
                _startup_requested = False
                return None

    return 0.5


def request_startup_enable(force_restart=False) -> None:
    global _startup_requested

    if bpy.app.background:
        return

    if force_restart and _OverlayRuntime.enabled:
        _OverlayRuntime.disable(bpy.context)

    _startup_requested = True
    if not bpy.app.timers.is_registered(_enable_overlay_on_startup):
        bpy.app.timers.register(_enable_overlay_on_startup, first_interval=0.2)


def _cancel_startup_enable() -> None:
    global _startup_requested

    _startup_requested = False
    if bpy.app.timers.is_registered(_enable_overlay_on_startup):
        bpy.app.timers.unregister(_enable_overlay_on_startup)


def _remove_view_menu_callbacks() -> None:
    menu = bpy.types.VIEW3D_MT_view
    callbacks = list(getattr(menu, "_draw_funcs", ()))
    for callback in callbacks:
        if (
            getattr(callback, "__module__", None) == __name__
            and getattr(callback, "__name__", None) == _draw_view_menu.__name__
        ):
            try:
                menu.remove(callback)
            except (AttributeError, RuntimeError, ValueError):
                pass

    try:
        menu.remove(_draw_view_menu)
    except (AttributeError, RuntimeError, ValueError):
        pass


_message_owner = object()
_load_state = None


def _names_changed():
    _tag_viewports_for_redraw(bpy.context)


def _subscribe_names():
    bpy.msgbus.clear_by_owner(_message_owner)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, 'name'), owner=_message_owner,
        args=(), notify=_names_changed,
    )


@persistent
def _before_load(_dummy):
    global _load_state
    _load_state = (_OverlayRuntime.enabled or _startup_requested,
                   _OverlayRuntime.all_names_enabled,
                   _OverlayRuntime.invalid_names_enabled)
    _cancel_startup_enable()
    _OverlayRuntime.shutdown()


@persistent
def _after_load(_dummy):
    global _load_state
    _subscribe_names()
    if _load_state is not None and not bpy.app.background:
        selection, all_names, invalid_names = _load_state
        if all_names:
            _OverlayRuntime.enable_all_names(bpy.context)
        if invalid_names:
            _OverlayRuntime.enable_invalid_names(bpy.context)
        if selection:
            request_startup_enable()
    _load_state = None


def register_runtime() -> None:
    _remove_view_menu_callbacks()
    bpy.types.VIEW3D_MT_view.append(_draw_view_menu)
    _subscribe_names()
    for handlers, callback in ((bpy.app.handlers.load_pre, _before_load),
                               (bpy.app.handlers.load_post, _after_load)):
        if callback not in handlers:
            handlers.append(callback)
    if not bpy.app.background:
        _OverlayRuntime.enable_invalid_names(bpy.context)
    request_startup_enable()


def unregister_runtime() -> None:
    global _load_state
    _cancel_startup_enable()
    _OverlayRuntime.shutdown(bpy.context)
    bpy.msgbus.clear_by_owner(_message_owner)
    for handlers, callback in ((bpy.app.handlers.load_pre, _before_load),
                               (bpy.app.handlers.load_post, _after_load)):
        if callback in handlers:
            handlers.remove(callback)
    _load_state = None
    _remove_view_menu_callbacks()


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_runtime()


def unregister():
    unregister_runtime()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
