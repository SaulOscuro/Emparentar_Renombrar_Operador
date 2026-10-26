"""
Addon de Blender para renombrar y emparentar objetos segun reglas de puertas,
closets y primitivos.
Requiere un objeto activo llamado wallN/interiorwallN/floorN/ceilingN y seleccion en Modo Objeto.
Modifica nombres, jerarquias y seleccion en la escena usando bpy.ops.
"""
# -------------------------------------------------------------------------
#                 Addon: Emparentador y Renombrador Inteligente
# -------------------------------------------------------------------------
# Este addon unificado renombra y emparenta objetos seleccionados.
# - Si el objeto tiene hijos y su nombre sugiere "closet", lo trata como jerarquía de puerta de closet (con hardware).
# - Si el objeto tiene hijos y no es un closet, lo trata como una jerarquía de puerta estándar (con hardware).
# - Si no tiene hijos, conserva su familia o solicita una si no hay una regla reconocida.
#
# v3.6.1: Admite black, lampmetal y lampemission en emparentado y visores.
# v3.6.0: Visores de nombres y avisos rojos para familias no admitidas.
# v3.5.0: Extension para Blender 4.2 con distribucion mediante repositorio remoto.
# v3.4.0: Selector de familia para objetos sin regla y sugerencia bathfloor para floorN.
# v3.3.1: Reconoce chromeN como familia y conserva su nombre al emparentar.
# v3.3.0: Añadida lógica para convertir duplicados wall/interiorwall/ceiling
#         en sub-walls del padre activo usando el formato "<padre>_wallN".
# v3.2.0: Añadido manejo de hardware para los paneles de las puertas de closet.
#         Ajustada la captura de hijos para el hardware en jerarquías.
# v3.1.0: Añadida jerarquía para puertas de closet con nomenclatura específica.
#         Introducida función para encontrar índice global de closet.
#         Modificada la lógica de detección de tipo de jerarquía.
# v3.0.1: Corregido el error 'menu_func is not defined' al registrar el addon.
# v3.0.0: Unificada la lógica de jerarquías y primitivos en un solo operador.
# -------------------------------------------------------------------------

import bpy
import re


from .naming_rules import PADRE_RE, DUPLICADO_ESTRUCTURAL_RE, NOMBRE_ESPECIAL_RE
from . import name_overlays


# Las tuplas permanentes mantienen vivos los textos del EnumProperty de Blender.
# Añadir aquí las sugerencias de cada padre cuando estén definidas.
FAMILIA_GENERICA = ("primitive", "primitive (genérico)", "Usar la familia genérica", 0)
SUGERENCIAS_POR_PADRE = {
    "wall": (),
    "interiorwall": (),
    "floor": (("bathfloor", "bathfloor", "Piso de baño", 1),),
    "ceiling": (),
}
OPCIONES_POR_PADRE = {
    tipo: sugerencias + (FAMILIA_GENERICA,)
    for tipo, sugerencias in SUGERENCIAS_POR_PADRE.items()
}
OPCIONES_GENERICAS = (FAMILIA_GENERICA,)


def opciones_familia(self, context):
    padre = context.active_object if context else None
    match = PADRE_RE.fullmatch(padre.name) if padre else None
    return OPCIONES_POR_PADRE[match.group(1)] if match else OPCIONES_GENERICAS


def objetos_sin_familia(objetos):
    """Las jerarquías conservan su tratamiento de puertas/closets existente."""
    return [obj for obj in objetos if not obj.children
            and not NOMBRE_ESPECIAL_RE.fullmatch(obj.name.strip())
            and not DUPLICADO_ESTRUCTURAL_RE.fullmatch(obj.name.strip())]


def nombre_para_familia(padre, familia, objeto, reservados=()):
    """Calcula un nombre libre, también si lo ocupa un objeto fuera del padre."""
    prefijo = f"{padre.name}_{familia}"
    indice = encontrar_siguiente_indice(padre, prefijo, exclude_obj=objeto)
    while True:
        nombre = f"{prefijo}{indice}"
        existente = bpy.data.objects.get(nombre)
        if nombre not in reservados and (existente is None or existente == objeto):
            return nombre
        indice += 1


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

    patron_prefijo_closet = re.compile(
        r'^(?:wall|interiorwall|floor|ceiling)\d+_closet\d+_door\d+_(.+)$',
        re.IGNORECASE,
    )

    def iterar_hijos_recursivos(objeto):
        for hijo in objeto.children:
            yield hijo
            yield from iterar_hijos_recursivos(hijo)

    def actualizar_prefijo_closet(objeto):
        match = patron_prefijo_closet.match(objeto.name)
        if not match:
            return
        nuevo_nombre = f"{nombre_base_puerta_actual_closet}_{match.group(1)}"
        if objeto.name != nuevo_nombre:
            objeto.name = nuevo_nombre

    for hijo in iterar_hijos_recursivos(objeto_raiz_puerta_closet_original):
        actualizar_prefijo_closet(hijo)
    
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

    familia_sin_regla: bpy.props.EnumProperty(
        name="Familia",
        description="Familia para los objetos sin una regla de nombre reconocida",
        items=opciones_familia,
        options={'SKIP_SAVE'},
    )

    @classmethod
    def poll(cls, context):
        """El emparentado requiere una selección en Modo Objeto."""
        return (context.mode == 'OBJECT' and context.active_object is not None
                and len(context.selected_objects) > 1)

    def invoke(self, context, event):
        padre = context.active_object
        if not padre or not PADRE_RE.fullmatch(padre.name):
            return self.execute(context)
        pendientes = objetos_sin_familia(
            [obj for obj in context.selected_objects if obj != padre]
        )
        if not pendientes:
            return self.execute(context)
        opciones = opciones_familia(self, context)
        if (not self.properties.is_property_set("familia_sin_regla")
                or self.familia_sin_regla not in {item[0] for item in opciones}):
            self.familia_sin_regla = opciones[0][0]
        return context.window_manager.invoke_props_dialog(self, width=480)

    def check(self, context):
        # Actualizar los ejemplos cuando cambia la familia elegida.
        return True

    def draw(self, context):
        layout = self.layout
        padre = context.active_object
        match = PADRE_RE.fullmatch(padre.name) if padre else None
        if not match:
            layout.label(text="Selecciona un padre válido para continuar.", icon='ERROR')
            return
        pendientes = objetos_sin_familia(
            [obj for obj in context.selected_objects if obj != padre]
        )
        layout.label(text=f"Padre: {padre.name}")
        layout.label(text=f"Objetos sin familia reconocida: {len(pendientes)}")
        if not SUGERENCIAS_POR_PADRE[match.group(1)]:
            layout.label(text=f"Aún no hay sugerencias para {match.group(1)}.", icon='INFO')
        layout.prop(self, "familia_sin_regla", text="Familia")
        box = layout.box()
        box.label(text="Nombres propuestos:")
        reservados = set()
        for obj in pendientes[:5]:
            nombre = nombre_para_familia(padre, self.familia_sin_regla, obj, reservados)
            reservados.add(nombre)
            box.label(text=f"{obj.name} → {nombre}")
        if len(pendientes) > 5:
            box.label(text=f"… y {len(pendientes) - 5} objetos más")
        layout.label(text="La familia elegida se aplica a todos los objetos sin regla.")

    def execute(self, context):
        """
        Valida el objeto padre, procesa jerarquias o primitivos y restaura seleccion.
        Modifica nombres y jerarquias en la escena y usa reportes para feedback.
        Retorna {'FINISHED'} o {'CANCELLED'}.
        """
        original_active = context.view_layer.objects.active
        original_selection = context.selected_objects[:]
        objeto_padre = context.active_object
        if context.mode != 'OBJECT' or objeto_padre is None:
            self.report({'WARNING'}, "Selecciona los objetos y su padre en Modo Objeto.")
            return {'CANCELLED'}
        
        # --- Paso 1: Validar objeto padre y seleccion ---
        match_padre = PADRE_RE.fullmatch(objeto_padre.name)
        if not match_padre:
            self.report({'WARNING'}, "Padre activo debe ser wallN, interiorwallN, floorN o ceilingN.")
            return {'CANCELLED'}
            
        objetos_a_procesar = [obj for obj in context.selected_objects if obj != objeto_padre]
        
        if not objetos_a_procesar:
            self.report({'WARNING'}, "No se seleccionaron objetos para procesar (además del padre activo).")
            return {'CANCELLED'}

        pendientes = objetos_sin_familia(objetos_a_procesar)
        familia_elegida = "primitive"
        if pendientes:
            # EXEC_DEFAULT también debe recibir una elección explícita antes de modificar la escena.
            if not self.properties.is_property_set("familia_sin_regla"):
                self.report({'WARNING'}, "Hay objetos sin familia. Ejecuta el operador desde el menú para elegir una.")
                return {'CANCELLED'}
            familia_elegida = self.familia_sin_regla
            if familia_elegida not in {item[0] for item in opciones_familia(self, context)}:
                self.report({'WARNING'}, "La familia elegida no está disponible para este padre.")
                return {'CANCELLED'}
            # Procesar primero los nombres previsualizados; las reglas existentes resuelven después sus conflictos.
            objetos_a_procesar = pendientes + [obj for obj in objetos_a_procesar if obj not in pendientes]

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
            for obj_individual in objetos_a_procesar:
                if obj_individual.children:
                    # Si estamos en este bloque, significa que o se seleccionaron múltiples objetos,
                    # y este en particular tiene hijos, o se seleccionó uno solo sin hijos (que se procesaría abajo).
                    # Si len(objetos_a_procesar) > 1 y este tiene hijos, se omite.
                    self.report({'WARNING'}, f"Omitiendo jerarquía '{obj_individual.name}' al procesar múltiples objetos. Procese jerarquías de una en una.")
                    jerarquias_omitidas +=1
                    continue
                
                # Convertir duplicados de wall/interiorwall/ceiling en sub-walls del padre activo.
                nombre_obj = obj_individual.name
                nombre_obj_limpio = nombre_obj.strip() if nombre_obj != nombre_obj.strip() else nombre_obj
                if DUPLICADO_ESTRUCTURAL_RE.fullmatch(nombre_obj_limpio):
                    indice_wall = encontrar_siguiente_indice(
                        objeto_padre,
                        f"{objeto_padre.name}_wall",
                        exclude_obj=obj_individual,
                    )
                    obj_individual.name = f"{objeto_padre.name}_wall{indice_wall}"
                    emparentar_con_operador_seguro(context, obj_individual, objeto_padre)
                    count_primitivos += 1
                    continue

                # Mantener enchufeN/apagadorN (limpiar .###); si hay conflicto, buscar siguiente indice
                match_especial = NOMBRE_ESPECIAL_RE.fullmatch(nombre_obj)
                if not match_especial and nombre_obj != nombre_obj.strip():
                    # Tolerar espacios accidentales sin cambiar la intencion del nombre.
                    match_especial = NOMBRE_ESPECIAL_RE.fullmatch(nombre_obj.strip())
                if match_especial:
                    nombre_base = nombre_obj.strip() if nombre_obj != nombre_obj.strip() else nombre_obj
                    nombre_base = re.sub(r'\.\d+$', '', nombre_base)
                    # Alinear el prefijo wall/interiorwall/floor/ceiling con el objeto padre activo.
                    match_prefijo = re.match(r'^(?:wall|interiorwall|floor|ceiling)\d+_(.+)$', nombre_base, re.IGNORECASE)
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

                # Aplicar la familia elegida a los objetos sin regla.
                obj_individual.name = nombre_para_familia(objeto_padre, familia_elegida, obj_individual)
                emparentar_con_operador_seguro(context, obj_individual, objeto_padre)
                count_primitivos += 1
            
            if count_primitivos > 0:
                self.report({'INFO'}, f"Se procesaron {count_primitivos} objetos.")
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
    contexto_anterior = self.layout.operator_context
    self.layout.operator_context = 'INVOKE_DEFAULT'
    self.layout.operator(OBJECT_OT_reparent_and_rename_smart.bl_idname)
    self.layout.operator_context = contexto_anterior

def register():
    """Registra el operador y el menu en Blender al habilitar el addon."""
    bpy.utils.register_class(OBJECT_OT_reparent_and_rename_smart)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    name_overlays.register()

def unregister():
    """Desregistra el operador y el menu al deshabilitar el addon."""
    name_overlays.unregister()
    bpy.utils.unregister_class(OBJECT_OT_reparent_and_rename_smart)
    bpy.types.VIEW3D_MT_object.remove(menu_func)

if __name__ == "__main__":
    # Para pruebas, descomentar y ejecutar en Blender's text editor
    # Asegúrate de tener una escena de prueba configurada.
    # register()
    pass
