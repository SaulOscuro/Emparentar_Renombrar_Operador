"""
Addon de Blender para renombrar y emparentar objetos segun reglas de puertas,
closets y primitivos.
Requiere un objeto activo llamado wallN/interiorwallN/ceilingN y seleccion en Modo Objeto.
Modifica nombres, jerarquias y seleccion en la escena usando bpy.ops.
"""
# -------------------------------------------------------------------------
#                 Addon: Emparentador y Renombrador Inteligente
# -------------------------------------------------------------------------
# Este addon unificado renombra y emparenta objetos seleccionados.
# - Si el objeto tiene hijos y su nombre sugiere "closet", lo trata como jerarquía de puerta de closet (con hardware).
# - Si el objeto tiene hijos y no es un closet, lo trata como una jerarquía de puerta estándar (con hardware).
# - Si el objeto no tiene hijos, lo trata como un primitivo.
#
# v3.2.0: Añadido manejo de hardware para los paneles de las puertas de closet.
#         Ajustada la captura de hijos para el hardware en jerarquías.
# v3.1.0: Añadida jerarquía para puertas de closet con nomenclatura específica.
#         Introducida función para encontrar índice global de closet.
#         Modificada la lógica de detección de tipo de jerarquía.
# v3.0.1: Corregido el error 'menu_func is not defined' al registrar el addon.
# v3.0.0: Unificada la lógica de jerarquías y primitivos en un solo operador.
# -------------------------------------------------------------------------

bl_info = {
    "name": "Emparentador y Renombrador Inteligente (Unificado)",
    "author": "Tu Nombre (con asistencia de Gemini)",
    "version": (3, 2, 9),
    "blender": (4, 2, 0),
    "location": "View3D > Object Menu > Emparentar y Renombrar Inteligente",
    "description": "Emparenta y renombra primitivos, puertas estándar (con hardware) o puertas de closet (con paneles y hardware).",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy
import re

def encontrar_siguiente_indice(objeto_padre: bpy.types.Object, prefijo_hijo: str, exclude_obj: bpy.types.Object = None) -> int:
    """
    Calcula el siguiente indice numerico disponible para un prefijo bajo un padre.
    Espera hijos ya nombrados con el prefijo + numero; exclude_obj permite ignorar uno.
    Retorna el proximo indice entero (>= 0). No modifica el estado de Blender.
    """
    max_indice = -1
    patron = re.compile(f"^{re.escape(prefijo_hijo)}(\\d+)($|_)")
    for hijo in objeto_padre.children:
        if hijo == exclude_obj:
            continue
        match = patron.match(hijo.name)
        if match:
            indice_actual = int(match.group(1))
            if indice_actual > max_indice:
                max_indice = indice_actual
    return max_indice + 1

def encontrar_siguiente_indice_closet_global(objeto_padre_wall: bpy.types.Object, prefijo_base_wall_name: str, exclude_obj: bpy.types.Object = None) -> int:
    """
    Calcula el siguiente indice global de closet bajo un wall.
    Busca hijos con patron "<wall>_closetN_door" y toma el maximo encontrado.
    exclude_obj permite omitir un objeto del conteo.
    Retorna el indice libre siguiente. No modifica la escena.
    """
    max_indice_closet = -1
    patron = re.compile(f"^{re.escape(prefijo_base_wall_name)}_closet(\\d+)_door")
    for obj in objeto_padre_wall.children:
        if obj == exclude_obj:
            continue
        match = patron.match(obj.name)
        if match:
            indice_actual = int(match.group(1))
            if indice_actual > max_indice_closet:
                max_indice_closet = indice_actual
    return max_indice_closet + 1

def emparentar_con_operador_seguro(context: bpy.types.Context, child_obj: bpy.types.Object, parent_obj: bpy.types.Object):
    """
    Emparenta child_obj a parent_obj usando bpy.ops y mantiene transformaciones.
    Requiere un contexto valido; cambia seleccion y objeto activo.
    No hace nada si ya estan emparentados.
    """
    # TODO: considerar override de contexto para no depender de la seleccion activa.
    if child_obj.parent == parent_obj: # Ya está correctamente emparentado
        return
    bpy.ops.object.select_all(action='DESELECT')
    child_obj.select_set(True)
    parent_obj.select_set(True)
    context.view_layer.objects.active = parent_obj
    bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

def procesar_jerarquia_puerta(context: bpy.types.Context, objeto_raiz_puerta_original: bpy.types.Object, objeto_padre_wall: bpy.types.Object):
    """
    Renombra y emparenta una jerarquia de puerta estandar.
    Espera un objeto raiz con paneles hijos "left"/"right".
    Renombra marco, paneles y hardware, y los emparenta al wall.
    Modifica nombres y jerarquia en la escena.
    """
    # --- Paso 1: Definir prefijos base ---
    base_door_idx = encontrar_siguiente_indice(objeto_padre_wall, f"{objeto_padre_wall.name}_door", exclude_obj=objeto_raiz_puerta_original)
    nombre_base_puerta = f"{objeto_padre_wall.name}_door{base_door_idx}"
    
    # Guardar hijos (paneles) del objeto raíz ANTES de renombrar/reemparentar el objeto raíz
    hijos_originales_paneles = list(objeto_raiz_puerta_original.children) 
    
    # --- Paso 2: Renombrar marco y emparentar ---
    nombre_marco = f"{nombre_base_puerta}_frame0"
    objeto_raiz_puerta_original.name = nombre_marco
    emparentar_con_operador_seguro(context, objeto_raiz_puerta_original, objeto_padre_wall)
    
    # --- Paso 3: Renombrar paneles y hardware ---
    for panel_original in hijos_originales_paneles:
        panel_type_base = ""
        panel_name_lower = panel_original.name.lower()

        # Guardar hijos (hardware) del panel ANTES de renombrar/reemparentar el panel
        hijos_originales_hardware = list(panel_original.children)

        if "left" in panel_name_lower:
            panel_type_base = "leftpanel"
        elif "right" in panel_name_lower:
            panel_type_base = "rightpanel"
        else:
            print(f"Panel estándar '{panel_original.name}' omitido por no ser 'left' ni 'right'.")
            continue
            
        panel_idx_specific = encontrar_siguiente_indice(objeto_raiz_puerta_original, f"{nombre_base_puerta}_{panel_type_base}", exclude_obj=panel_original)
        nombre_panel_renombrado = f"{nombre_base_puerta}_{panel_type_base}{panel_idx_specific}"
        panel_original.name = nombre_panel_renombrado
        emparentar_con_operador_seguro(context, panel_original, objeto_raiz_puerta_original)
        
        # Renombrar hardware bajo el panel ya renombrado.
        for hardware_obj in hijos_originales_hardware:
            current_hardware_idx = encontrar_siguiente_indice(panel_original, f"{panel_original.name}_hardware", exclude_obj=hardware_obj)
            nombre_hardware = f"{panel_original.name}_hardware{current_hardware_idx}"
            hardware_obj.name = nombre_hardware
            emparentar_con_operador_seguro(context, hardware_obj, panel_original)

def procesar_jerarquia_puerta_closet(context: bpy.types.Context, objeto_raiz_puerta_closet_original: bpy.types.Object, objeto_padre_wall: bpy.types.Object):
    """
    Renombra y emparenta una jerarquia de puerta de closet con paneles y hardware.
    Espera paneles con combinaciones closed/open y left/right en el nombre.
    Renombra marco, paneles y hardware, y los emparenta al wall.
    Modifica nombres y jerarquia en la escena.
    """
    # --- Paso 1: Definir prefijos base para closet ---
    closet_idx = encontrar_siguiente_indice_closet_global(objeto_padre_wall, objeto_padre_wall.name) # exclude_obj no es tan crítico aquí
    prefijo_puerta_en_closet = f"{objeto_padre_wall.name}_closet{closet_idx}_door"
    door_idx = encontrar_siguiente_indice(objeto_padre_wall, prefijo_puerta_en_closet, exclude_obj=objeto_raiz_puerta_closet_original)
    nombre_base_puerta_actual_closet = f"{prefijo_puerta_en_closet}{door_idx}"
    
    # Guardar hijos (paneles) del objeto raíz del closet ANTES de renombrar/reemparentar el objeto raíz
    hijos_originales_paneles = list(objeto_raiz_puerta_closet_original.children) 

    # --- Paso 2: Renombrar marco y emparentar ---
    nombre_marco_closet = f"{nombre_base_puerta_actual_closet}_frame0"
    objeto_raiz_puerta_closet_original.name = nombre_marco_closet
    emparentar_con_operador_seguro(context, objeto_raiz_puerta_closet_original, objeto_padre_wall)
    
    # --- Paso 3: Renombrar paneles y hardware ---
    for panel_original in hijos_originales_paneles:
        panel_name_lower = panel_original.name.lower()
        panel_type = ""

        # Guardar hijos (hardware) del panel ANTES de renombrar/reemparentar el panel
        hijos_originales_hardware_closet = list(panel_original.children)

        # Detectar combinaciones closed/open + left/right desde el nombre original.
        is_left = "left" in panel_name_lower
        is_right = "right" in panel_name_lower
        is_closed = "closed" in panel_name_lower
        is_open = "open" in panel_name_lower

        if is_closed and is_left:
            panel_type = "closedleftpanel"
        elif is_open and is_left:
            panel_type = "openleftpanel"
        elif is_closed and is_right:
            panel_type = "closedrightpanel"
        elif is_open and is_right:
            panel_type = "openrightpanel"
        else:
            print(f"Panel de closet '{panel_original.name}' no coincide con nomenclatura esperada (closed/open + left/right). Omitiendo.")
            continue

        if panel_type:
            # El padre para encontrar el índice del panel es el marco del closet (objeto_raiz_puerta_closet_original ya renombrado)
            panel_idx = encontrar_siguiente_indice(objeto_raiz_puerta_closet_original, f"{nombre_base_puerta_actual_closet}_{panel_type}", exclude_obj=panel_original)
            nombre_panel_renombrado = f"{nombre_base_puerta_actual_closet}_{panel_type}{panel_idx}"
            panel_original.name = nombre_panel_renombrado
            emparentar_con_operador_seguro(context, panel_original, objeto_raiz_puerta_closet_original) # Emparentar panel al marco del closet
            
            # Procesar hardware del panel de closet
            for hardware_obj in hijos_originales_hardware_closet:
                # El padre para encontrar el índice del hardware es el panel_original (ya renombrado y emparentado)
                hardware_idx_closet = encontrar_siguiente_indice(panel_original, f"{panel_original.name}_hardware", exclude_obj=hardware_obj)
                nombre_hardware = f"{panel_original.name}_hardware{hardware_idx_closet}"
                hardware_obj.name = nombre_hardware
                emparentar_con_operador_seguro(context, hardware_obj, panel_original) # Emparentar hardware al panel


class OBJECT_OT_reparent_and_rename_smart(bpy.types.Operator):
    """Operador principal para renombrar y emparentar segun reglas predefinidas."""
    bl_idname = "object.reparent_and_rename_smart"
    bl_label = "Emparentar y Renombrar Inteligente"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Valida que haya objeto activo y mas de un seleccionado."""
        return context.active_object is not None and len(context.selected_objects) > 1

    def execute(self, context):
        """
        Valida el objeto padre, procesa jerarquias o primitivos y restaura seleccion.
        Modifica nombres y jerarquias en la escena y usa reportes para feedback.
        Retorna {'FINISHED'} o {'CANCELLED'}.
        """
        original_active = context.view_layer.objects.active
        original_selection = context.selected_objects[:]
        objeto_padre = context.active_object
        
        # --- Paso 1: Validar objeto padre y seleccion ---
        match_padre = re.match(r'^(wall|interiorwall|ceiling)\d+$', objeto_padre.name)
        if not match_padre:
            self.report({'WARNING'}, "Padre activo debe ser 'wall<índice>', 'interiorwall<índice>' o 'ceiling<índice>'.")
            return {'CANCELLED'}
            
        objetos_a_procesar = [obj for obj in context.selected_objects if obj != objeto_padre]
        
        if not objetos_a_procesar:
            self.report({'WARNING'}, "No se seleccionaron objetos para procesar (además del padre activo).")
            return {'CANCELLED'}

        # --- Paso 2: Procesar jerarquias o primitivos ---
        # Priorizar el procesamiento de jerarquías si solo se selecciona una (además del padre)
        if len(objetos_a_procesar) == 1 and objetos_a_procesar[0].children:
            objeto_raiz_jerarquia = objetos_a_procesar[0]
            nombre_raiz_lower = objeto_raiz_jerarquia.name.lower()

            # Guardar el estado actual para una posible reversión o referencia
            # active_obj_before_processing = context.active_object
            # selected_before_processing = context.selected_objects[:]

            if "closet" in nombre_raiz_lower or "wardrobe" in nombre_raiz_lower:
                procesar_jerarquia_puerta_closet(context, objeto_raiz_jerarquia, objeto_padre)
                self.report({'INFO'}, f"Jerarquía de puerta de closet '{objeto_raiz_jerarquia.name}' procesada.")
            else: 
                procesar_jerarquia_puerta(context, objeto_raiz_jerarquia, objeto_padre)
                self.report({'INFO'}, f"Jerarquía de puerta estándar '{objeto_raiz_jerarquia.name}' procesada.")
        else: # Procesar como primitivos o múltiples objetos sin hijos (o advertir si tienen hijos)
            count_primitivos = 0
            jerarquias_omitidas = 0
            # Patron especial para mantener nomenclaturas definidas y limpiar sufijo .###.
            nombre_especial_re = re.compile(
                r'^(?:'
                r'(?:wall|interiorwall|ceiling)\d+_(?:'
                r'alacena\d+|apagador\d+|board\d+|closet\d+'
                r'|closet\d+_door\d+_frame\d+'
                r'|closet\d+_door\d+_closedleftpanel\d+(?:_hardware\d+)?'
                r'|closet\d+_door\d+_openleftpanel\d+(?:_hardware\d+)?'
                r'|closet\d+_door\d+_closedrightpanel\d+(?:_hardware\d+)?'
                r'|closet\d+_door\d+_openrightpanel\d+(?:_hardware\d+)?'
                r'|closet\d+_door\d+_closedleftpanel\d+_door\d+'
                r'|closet\d+_door\d+_closedrightpanel\d+_door\d+'
                r'|closet\d+_door\d+_door\d+'
                r'|closet\d+_door\d+_openleftpanel\d+_door\d+'
                r'|closet\d+_door\d+_openrightpanel\d+_door\d+'
                r'|coladera\d+|colgador\d+|door\d+|glass\d+'
                r'|door\d+_door\d+|door\d+_leftpanel\d+_door\d+|door\d+_rightpanel\d+_door\d+'
                r'|enchufe\d+|estufa\d+|faucet\d+|fridge&micro\d+|fridge\d+|hvac\d+'
                r'|jaladera\d+|lampara\d+|lamp\d+|lavabo\d+|luz\d+|mirror\d+'
                r'|perchero\d+|regadera\d+|repisa\d+|seat\d+|stuff\d+|trim\d+|vent\d+|window\d+|collider\d+|\d+'
                r')'
                r'|toallero_colgador\d+'
                r')(?:\.\d+)?$',
                re.IGNORECASE,
            )
            for obj_individual in objetos_a_procesar:
                if obj_individual.children:
                    # Si estamos en este bloque, significa que o se seleccionaron múltiples objetos,
                    # y este en particular tiene hijos, o se seleccionó uno solo sin hijos (que se procesaría abajo).
                    # Si len(objetos_a_procesar) > 1 y este tiene hijos, se omite.
                    self.report({'WARNING'}, f"Omitiendo jerarquía '{obj_individual.name}' al procesar múltiples objetos. Procese jerarquías de una en una.")
                    jerarquias_omitidas +=1
                    continue
                
                # Mantener enchufeN/apagadorN (limpiar .###); si hay conflicto, buscar siguiente indice
                nombre_obj = obj_individual.name
                match_especial = nombre_especial_re.match(nombre_obj)
                if not match_especial and nombre_obj != nombre_obj.strip():
                    # Tolerar espacios accidentales sin cambiar la intencion del nombre.
                    match_especial = nombre_especial_re.match(nombre_obj.strip())
                if match_especial:
                    nombre_base = nombre_obj.strip() if nombre_obj != nombre_obj.strip() else nombre_obj
                    nombre_base = re.sub(r'\.\d+$', '', nombre_base)
                    # Alinear el prefijo wall/interiorwall/ceiling con el objeto padre activo.
                    match_prefijo = re.match(r'^(?:wall|interiorwall|ceiling)\d+_(.+)$', nombre_base, re.IGNORECASE)
                    if match_prefijo:
                        nombre_base = f"{objeto_padre.name}_{match_prefijo.group(1)}"
                    existente = bpy.data.objects.get(nombre_base)
                    # Si el nombre base ya existe, buscar el siguiente indice disponible.
                    while existente and existente != obj_individual:
                        match_ultimo = re.search(r'(\d+)(?!.*\d)', nombre_base)
                        if not match_ultimo:
                            break
                        inicio, fin = match_ultimo.span(1)
                        indice_especial = int(match_ultimo.group(1)) + 1
                        nombre_base = f"{nombre_base[:inicio]}{indice_especial}{nombre_base[fin:]}"
                        existente = bpy.data.objects.get(nombre_base)
                    obj_individual.name = nombre_base
                    emparentar_con_operador_seguro(context, obj_individual, objeto_padre)
                    count_primitivos += 1
                    continue

                # Tratar como primitivo
                indice_primitivo = encontrar_siguiente_indice(objeto_padre, f"{objeto_padre.name}_primitive", exclude_obj=obj_individual)
                obj_individual.name = f"{objeto_padre.name}_primitive{indice_primitivo}"
                emparentar_con_operador_seguro(context, obj_individual, objeto_padre)
                count_primitivos += 1
            
            if count_primitivos > 0:
                self.report({'INFO'}, f"Se procesaron {count_primitivos} objetos primitivos.")
            if jerarquias_omitidas == 0 and count_primitivos == 0 and not (len(objetos_a_procesar) == 1 and objetos_a_procesar[0].children) :
                 self.report({'WARNING'}, "No se procesó ningún objeto primitivo válido.")
            elif jerarquias_omitidas > 0 and count_primitivos == 0:
                 self.report({'WARNING'}, "No se procesaron primitivos. Se omitieron jerarquías (procesar de una en una).")


        # --- Paso 3: Restaurar seleccion original ---
        # Restaurar selección y activo (intentar con nombres, ya que las referencias directas pueden cambiar)
        bpy.ops.object.select_all(action='DESELECT')
        
        # Guardar los nombres actuales de la selección original, ya que los objetos pudieron ser renombrados.
        # Esto es un poco más complejo porque el objeto original podría no existir o su "identidad" haber cambiado.
        # La referencia directa 'original_selection' es la más robusta si los objetos no son eliminados/recreados.
        
        # Si la reseleccion falla, inspeccionar original_selection y bpy.data.objects.
        for obj_ref in original_selection:
            try:
                # obj_ref es la referencia original al objeto. Si fue renombrado, la referencia sigue siendo válida
                # mientras el objeto no sea eliminado y recreado.
                if obj_ref and obj_ref.name in bpy.data.objects: # Comprobar si el objeto aún existe y es accesible
                     bpy.data.objects[obj_ref.name].select_set(True)
                # else: # Si el objeto fue renombrado y queremos buscarlo por su nombre original (más complejo)
                    # No es necesario aquí, ya que obj_ref debería seguir apuntando al mismo bloque de datos del objeto
            except ReferenceError:
                 # El objeto original ya no existe en la escena (p.ej. fue eliminado por otro script o manualmente de forma inesperada)
                print(f"Advertencia: No se pudo reseleccionar un objeto de la selección original porque ya no existe.")
                pass 
        
        try:
            if original_active and original_active.name in bpy.data.objects: # Comprobar si el objeto activo original aún existe
                context.view_layer.objects.active = bpy.data.objects[original_active.name]
        except ReferenceError:
            print(f"Advertencia: No se pudo restaurar el objeto activo original porque ya no existe.")
            pass 
            
        return {'FINISHED'}

# --- Registro del Addon ---

def menu_func(self, context):
    """
    Agrega el operador al menu Object del View3D.
    Se usa en register() para insertar el acceso en la UI.
    """
    self.layout.operator(OBJECT_OT_reparent_and_rename_smart.bl_idname)

def register():
    """Registra el operador y el menu en Blender al habilitar el addon."""
    bpy.utils.register_class(OBJECT_OT_reparent_and_rename_smart)
    bpy.types.VIEW3D_MT_object.append(menu_func)

def unregister():
    """Desregistra el operador y el menu al deshabilitar el addon."""
    bpy.utils.unregister_class(OBJECT_OT_reparent_and_rename_smart)
    bpy.types.VIEW3D_MT_object.remove(menu_func)

if __name__ == "__main__":
    # Para pruebas, descomentar y ejecutar en Blender's text editor
    # Asegúrate de tener una escena de prueba configurada.
    # register()
    pass
