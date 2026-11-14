"""Shared GLB preflight for Blender 4.2/5.x. Never edits names or parents.

Intercept execute (not just the File menu), before the exporter writes anything.
Multiple J3D addons share one hook; disabling restores the native method.
"""
import uuid
import bpy

_state = None
_owner = __package__
_marker = '_j3d_glb_parenting_preflight'


def candidates(context, options):
    scenes = [context.scene] if options.get('use_active_scene') else bpy.data.scenes
    collection = None
    if options.get('collection'):
        collection = bpy.data.collections.get(options['collection'])
        allowed = set(collection.all_objects) if collection else set()
    elif options.get('use_active_collection'):
        collection = context.collection
        allowed = set(collection.all_objects if options.get('use_active_collection_with_nested') else collection.objects)
    else:
        allowed = None
    seen = set()
    for scene in scenes:
        for obj in scene.objects:
            if obj in seen or obj.type != 'MESH' or obj.parent is not None:
                continue
            seen.add(obj)
            if allowed is not None and obj not in allowed:
                continue
            if options.get('use_selection') and not obj.select_get():
                continue
            if options.get('use_visible') and (not obj.visible_get() or obj.hide_viewport
                    or all(c.hide_viewport for c in obj.users_collection)):
                continue
            if options.get('use_renderable') and (obj.hide_render or all(c.hide_render for c in obj.users_collection)):
                continue
            yield obj


def missing_parents(context, options, rules):
    result = []
    for obj in candidates(context, options):
        name = rules.canonical(obj.name)
        expected = rules.expected_parent(name)
        if expected and rules.unsupported_reason(name) is None:
            result.append((obj.name, expected))
    return sorted(result)


def export_options(operator):
    return operator.as_keywords(ignore=('rna_type', 'filter_glob'))


def register(rules):
    global _state
    import io_scene_gltf2
    cls = io_scene_gltf2.ExportGLTF2
    existing = getattr(cls, _marker, None)
    if existing is not None:
        existing['owners'].add(_owner)
        _state = existing
        return
    state = {'owners': {_owner}, 'original': cls.execute, 'pending': {}, 'bypass': False,
             'rules': rules, 'class': cls, 'timers': set()}
    _state = state

    class J3D_OT_glb_parenting_warning(bpy.types.Operator):
        bl_idname = 'j3d_naming.glb_parenting_warning'
        bl_label = 'Objetos sin emparentar'
        bl_options = {'INTERNAL'}
        token: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
        action: bpy.props.EnumProperty(name='Acción', items=(
            ('REVIEW', 'Revisar objetos', 'Cancelar la exportación y seleccionar los objetos pendientes'),
            ('EXPORT', 'Exportar igualmente', 'Exportar esta vez sin cambiar el parentesco')),
            default='REVIEW', options={'SKIP_SAVE'})

        def invoke(self, context, _event):
            if self.token not in state['pending']:
                return {'CANCELLED'}
            return context.window_manager.invoke_props_dialog(self, width=500)

        def draw(self, _context):
            request = state['pending'].get(self.token)
            if request is None:
                return
            self.layout.label(text='Algunos objetos no están emparentados.', icon='INFO')
            self.layout.label(text='¿Quieres revisarlos antes de exportar el GLB?')
            for name, expected in request['issues'][:6]:
                self.layout.label(text=name + ' → ' + expected)
            if len(request['issues']) > 6:
                self.layout.label(text='Y ' + str(len(request['issues']) - 6) + ' más…')
            self.layout.prop(self, 'action', expand=True)

        def cancel(self, _context):
            state['pending'].pop(self.token, None)

        def execute(self, context):
            request = state['pending'].pop(self.token, None)
            if request is None or context.scene != request['scene']:
                self.report({'WARNING'}, 'La escena cambió; vuelve a exportar.')
                return {'CANCELLED'}
            if self.action == 'REVIEW':
                names = {name for name, _ in request['issues']}
                if context.mode != 'OBJECT':
                    self.report({'INFO'}, 'Revisa los objetos en Modo Objeto y vuelve a exportar.')
                    return {'FINISHED'}
                for obj in context.view_layer.objects:
                    obj.select_set(obj.name in names and obj.visible_get() and not obj.hide_select)
                first = next((o for o in context.selected_objects if o.name in names), None)
                if first:
                    context.view_layer.objects.active = first
                self.report({'INFO'}, 'Exportación cancelada para revisar el parentesco.')
                return {'FINISHED'}
            state['bypass'] = True
            try:
                # Same native exporter/options, exactly once. No rename/reparent.
                return bpy.ops.export_scene.gltf('EXEC_DEFAULT', **request['options'])
            finally:
                state['bypass'] = False

    bpy.utils.register_class(J3D_OT_glb_parenting_warning)
    state['dialog'] = J3D_OT_glb_parenting_warning

    def execute(operator, context):
        if not state['owners'] or state['bypass'] or operator.export_format != 'GLB':
            return state['original'](operator, context)
        options = export_options(operator)
        issues = missing_parents(context, options, state['rules'])
        if not issues:
            return state['original'](operator, context)
        if bpy.app.background:
            operator.report({'WARNING'}, 'GLB no exportado: algunos objetos no están emparentados: '
                            + ', '.join(name for name, _ in issues[:6]))
            return {'CANCELLED'}
        token = uuid.uuid4().hex
        state['pending'][token] = {'options': options, 'issues': issues, 'scene': context.scene}
        window = context.window

        def popup():
            state['timers'].discard(popup)
            if not state['owners'] or token not in state['pending']:
                return None
            if window not in bpy.context.window_manager.windows[:]:
                state['pending'].pop(token, None)
                return None
            # Wait for the native file browser to close, then show in the main window.
            with bpy.context.temp_override(window=window):
                window.cursor_warp(window.width // 2, window.height // 2)
                bpy.ops.j3d_naming.glb_parenting_warning('INVOKE_DEFAULT', token=token)
            return None

        state['timers'].add(popup)
        bpy.app.timers.register(popup, first_interval=0.2)
        return {'CANCELLED'}

    state['wrapper'] = execute
    cls.execute = execute
    setattr(cls, _marker, state)


def unregister():
    global _state
    state, _state = _state, None
    if state is None:
        return
    state['owners'].discard(_owner)
    if state['owners']:
        return
    for timer in tuple(state['timers']):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    state['timers'].clear()
    state['pending'].clear()
    if state['class'].execute is state['wrapper']:
        state['class'].execute = state['original']
    if getattr(state['class'], _marker, None) is state:
        delattr(state['class'], _marker)
    bpy.utils.unregister_class(state['dialog'])
