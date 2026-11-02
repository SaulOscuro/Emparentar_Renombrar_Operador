"""Custom family controls; changing acceptance never mutates scene objects."""
import zlib
import bpy
from . import family_store, naming_rules as rules

# Strings backing dynamic EnumProperty items must remain alive for RNA.
_enum_items = {}
_enabled = False


def family_items(base):
    custom = tuple(sorted(family_store.families() - rules.DISPLAY_FAMILIES))
    key = (tuple(base), custom)
    if key not in _enum_items:
        items = list(base)
        used = {item[3] for item in items}
        for name in custom:
            number = (zlib.crc32(name.encode()) & 0x7fffffff) or 2
            while number in used:
                number = (number + 1) & 0x7fffffff
            used.add(number)
            items.append((name, name, 'Familia personalizada', number))
        _enum_items[key] = tuple(items)
    return _enum_items[key]


def _active_mesh(context):
    obj = getattr(context, 'active_object', None)
    if obj is None and getattr(context, 'view_layer', None):
        obj = context.view_layer.objects.active
    return obj if obj and obj.type == 'MESH' else None


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _save(operator, value, accepted):
    try:
        label = family_store.normalize_family(value)
        if label in rules.DISPLAY_FAMILIES:
            raise ValueError('Esta familia ya forma parte de las reglas incluidas.')
        family_store.set_family(label, accepted=accepted)
    except (OSError, ValueError) as exc:
        operator.report({'ERROR'}, str(exc))
        return {'CANCELLED'}
    _redraw()
    operator.report({'INFO'}, ('Familia aceptada: ' if accepted else 'Familia retirada: ') + label)
    return {'FINISHED'}


class ERO_OT_add_family(bpy.types.Operator):
    bl_idname = 'ero.add_custom_family'
    bl_label = 'Añadir familia'
    bl_description = 'Acepta una familia en ambos add-ons; no modifica objetos'
    family: bpy.props.StringProperty(name='Familia', description='Por ejemplo wood, sin números', options={'SKIP_SAVE'})

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, _context):
        self.layout.prop(self, 'family')
        self.layout.label(text='Se aplicará a ambos add-ons y a todas las escenas.')
        self.layout.label(text='Ejemplo: wood admite wall3_wood0.')

    def execute(self, _context):
        return _save(self, self.family, True)


class ERO_OT_accept_selected_family(bpy.types.Operator):
    bl_idname = 'ero.accept_selected_family'
    bl_label = 'Aceptar familia del objeto seleccionado'
    bl_description = 'Detecta y confirma la familia del objeto activo, sin renombrarlo ni emparentarlo'
    family: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    source_name: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _active_mesh(context) is not None

    def invoke(self, context, _event):
        obj = _active_mesh(context)
        try:
            self.family = family_store.family_from_name(obj.name)
            if self.family in rules.DISPLAY_FAMILIES or self.family in family_store.families():
                self.report({'INFO'}, 'La familia ya está admitida; revisa el nombre y su parentesco.')
                return {'CANCELLED'}
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.source_name = obj.name
        return context.window_manager.invoke_props_dialog(self, width=480)

    def draw(self, _context):
        self.layout.label(text=self.source_name, icon='OBJECT_DATA')
        self.layout.label(text='Aceptar familia: ' + self.family)
        self.layout.label(text='Se aplicará a ambos add-ons y a todas las escenas.')
        self.layout.label(text='Los avisos por padres incorrectos seguirán activos.')

    def execute(self, context):
        obj = _active_mesh(context)
        if not obj or obj.name != self.source_name or not self.family:
            self.report({'ERROR'}, 'La selección cambió; vuelve a abrir la confirmación.')
            return {'CANCELLED'}
        try:
            if family_store.family_from_name(obj.name) != self.family:
                raise ValueError('La familia del objeto cambió.')
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return _save(self, self.family, True)


class ERO_OT_remove_family(bpy.types.Operator):
    bl_idname = 'ero.remove_custom_family'
    bl_label = 'Quitar familia personalizada'
    family: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, _context):
        self.layout.label(text='Quitar familia: ' + self.family)
        self.layout.label(text='Volverá a marcarse en rojo en ambos add-ons.')
        self.layout.label(text='Los objetos conservarán sus nombres.')

    def execute(self, _context):
        return _save(self, self.family, False)


def draw_controls(layout, context):
    box = layout.box()
    box.label(text='Familias personalizadas', icon='PRESET')
    box.label(text='Lista compartida entre ambos add-ons.')
    controls = box.column(align=True)
    controls.operator_context = 'INVOKE_DEFAULT'
    controls.operator(ERO_OT_add_family.bl_idname, icon='ADD')
    controls.operator(ERO_OT_accept_selected_family.bl_idname, icon='CHECKMARK')
    labels = sorted(family_store.families() - rules.DISPLAY_FAMILIES)
    if not labels:
        box.label(text='Aún no hay familias personalizadas.')
    for label in labels:
        row = box.row(align=True)
        row.label(text=label)
        row.operator_context = 'INVOKE_DEFAULT'
        row.operator(ERO_OT_remove_family.bl_idname, text='', icon='X').family = label
    problem = family_store.error()
    if problem:
        box.label(text='Error al leer la configuración compartida.', icon='ERROR')
        box.label(text=problem)
    # Useful when moving/backing up the shared list; independent of Blender version.
    box.label(text=str(family_store.config_path()))


class ERO_PT_custom_families(bpy.types.Panel):
    bl_idname = 'ERO_PT_custom_families'
    bl_label = 'Familias personalizadas'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Emparentar'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        draw_controls(self.layout, context)


def _menu(self, _context):
    old = self.layout.operator_context
    self.layout.operator_context = 'INVOKE_DEFAULT'
    self.layout.operator(ERO_OT_accept_selected_family.bl_idname)
    self.layout.operator_context = old


def _tick():
    if not _enabled:
        return None
    if family_store.refresh():
        _redraw()
    return 1.0


CLASSES = (ERO_OT_add_family, ERO_OT_accept_selected_family, ERO_OT_remove_family, ERO_PT_custom_families)


def register():
    global _enabled
    for cls in CLASSES:
        if not cls.is_registered:
            bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.remove(_menu)
    bpy.types.VIEW3D_MT_object.append(_menu)
    _enabled = True
    family_store.refresh(force=True)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)


def unregister():
    global _enabled
    _enabled = False
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    bpy.types.VIEW3D_MT_object.remove(_menu)
    for cls in reversed(CLASSES):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
