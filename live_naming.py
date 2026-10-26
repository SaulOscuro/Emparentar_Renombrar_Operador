"""NoDot allocation adapted from J3DSyncManager, with Blender 4.2 limits.

Only mesh object names are normalized. A duplicated parent and the matching
names below it are planned together, and every write is checked and reversible.
"""
import re
import uuid

DUPLICATE = re.compile(r'\.\d{3,}(?=_|$)')
INDEX = re.compile(r'^(.*?)(\d*)$')
FRAME = re.compile(r'^(.*_door\d+)_frame\d+$', re.IGNORECASE)


def canonical(name):
    while DUPLICATE.search(name):
        name = DUPLICATE.sub('', name)
    return name


def editable(obj):
    return (obj.library is None and obj.override_library is None
            and obj.is_editable and len(obj.users_scene) <= 1)


def assign_atomic(assignments, namespace):
    """Keep object references and restore every original if any write fails."""
    assignments = [(obj, target) for obj, target in assignments if obj.name != target]
    if not assignments:
        return
    targets = [name for _, name in assignments]
    # Blender 4.2 ID names have a 63-byte UTF-8 limit (5.x increased it).
    if len(targets) != len(set(targets)) or any(
            not name or len(name.encode('utf-8')) > 63 for name in targets):
        raise ValueError('El nombre no cabe en Blender 4.2 o está repetido')
    members = {obj for obj, _ in assignments}
    if any(item.name in targets for item in namespace if item not in members):
        raise ValueError('Otro objeto ocupa un nombre propuesto')
    if not all(editable(obj) for obj in members):
        raise ValueError('La jerarquía contiene objetos protegidos o compartidos')
    originals = [(obj, obj.name) for obj, _ in assignments]

    def temporary_names():
        for obj, _ in assignments:
            obj.name = '_ero_' + uuid.uuid4().hex

    try:
        temporary_names()
        for obj, target in assignments:
            obj.name = target
            if obj.name != target:
                raise ValueError('Blender no pudo asignar el nombre completo')
    except Exception:
        temporary_names()
        for obj, original in originals:
            obj.name = original
            if obj.name != original:
                raise RuntimeError('No se pudo restaurar un nombre original')
        raise


def _depth(obj):
    depth = 0
    parent = obj.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _plan_group(root, objects):
    clean = canonical(root.name)
    # A door frame identifies the complete door, including its panels/hardware.
    frame = FRAME.fullmatch(clean)
    if frame and root.children:
        old_prefix = frame.group(1)
        root_suffix = clean[len(old_prefix):]
    else:
        # An embedded .001 belongs to that component, not the last child.
        match = DUPLICATE.search(root.name)
        old_prefix = canonical(root.name[:match.start()])
        root_suffix = canonical(root.name[match.end():])
    group = [(root, root_suffix)]
    for child in sorted(root.children_recursive, key=lambda item: (_depth(item), item.name)):
        if child.type != 'MESH':
            continue
        name = canonical(child.name)
        if name.startswith(old_prefix + '_'):
            group.append((child, name[len(old_prefix):]))
    if not all(editable(obj) for obj, _ in group):
        raise ValueError('Jerarquía protegida o compartida entre escenas')
    members = {obj for obj, _ in group}
    occupied = {obj.name for obj in objects if obj not in members}
    stem, digits = INDEX.fullmatch(old_prefix).groups()
    index = int(digits) if digits else 0
    while True:
        prefix = f'{stem}{index}'
        # Distinct children may collapse to the same name after stripping .001.
        # Allocate them in parent-first order and propagate their new prefixes.
        reserved = set(occupied)
        mapping = {}
        assignments = []
        for obj, suffix in group:
            desired = prefix + suffix
            parent = obj.parent
            while parent in members:
                old, new = mapping.get(parent, ('', ''))
                if old and desired.startswith(old + '_'):
                    desired = new + desired[len(old):]
                    break
                parent = parent.parent
            candidate = desired
            if candidate in reserved and obj is not root:
                door_frame = FRAME.fullmatch(candidate) if obj.children else None
                indexed = door_frame.group(1) if door_frame else candidate
                tail = candidate[len(indexed):]
                base, number = INDEX.fullmatch(indexed).groups()
                next_index = int(number) if number else 0
                while candidate in reserved:
                    next_index += 1
                    candidate = f'{base}{next_index}{tail}'
            if obj is root and candidate in reserved:
                break
            reserved.add(candidate)
            assignments.append((obj, candidate))
            old_frame = FRAME.fullmatch(prefix + suffix)
            new_frame = FRAME.fullmatch(candidate)
            mapping[obj] = ((old_frame.group(1), new_frame.group(1))
                            if old_frame and new_frame and obj.children
                            else (prefix + suffix, candidate))
        else:
            return assignments
        index += 1


def normalize_objects(objects):
    """Return changed count and per-object failures; no geometry/data writes."""
    objects = list(objects)
    changed = 0
    failures = {}
    for obj in sorted(objects, key=lambda item: (_depth(item), item.name)):
        if obj.type != 'MESH' or not DUPLICATE.search(obj.name):
            continue
        if not editable(obj):
            failures[obj.as_pointer()] = 'Duplicado protegido o compartido entre escenas'
            continue
        try:
            plan = _plan_group(obj, objects)
            count = sum(item.name != target for item, target in plan)
            assign_atomic(plan, objects)
            changed += count
        except (ValueError, RuntimeError) as exc:
            failures[obj.as_pointer()] = str(exc)
    return changed, failures
