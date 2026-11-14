"""Carry declared custom families with the blend; never infer them from names."""
import json
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from . import family_store, nomenclature_catalog as catalog

KEY = 'j3d_naming_families'


@lru_cache(maxsize=64)
def decode(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        return frozenset()
    try:
        data = json.loads(raw)
        labels = data.get('families')
        if data.get('schema_version') != 1 or not isinstance(labels, list) or len(labels) > 256:
            return frozenset()
        return frozenset(family_store.normalize_family(label) for label in labels)
    except (TypeError, ValueError, AttributeError):
        return frozenset()


def project_families():
    result = set()
    for scene in getattr(bpy.data, 'scenes', ()):
        raw = scene.get(KEY, '')
        if isinstance(raw, str):
            result.update(decode(raw))
    return frozenset(result)


def _write(labels):
    payload = json.dumps({'schema_version': 1, 'families': sorted(labels)}, ensure_ascii=False)
    for scene in getattr(bpy.data, 'scenes', ()):
        if scene.library is None and scene.get(KEY, '') != payload:
            scene[KEY] = payload


@persistent
def save_families(_unused):
    # Snapshot declarations on Save. Opening a project never rewrites personal
    # preferences and never accepts arbitrary object names as family definitions.
    _write(catalog.custom_families())


def remove_family(label):
    _write(project_families() - {label} - catalog.OFFICIAL_FAMILIES)


def register():
    catalog._project_reader = project_families
    if save_families not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(save_families)


def unregister():
    if save_families in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(save_families)
    catalog._project_reader = None


# Background consumers that import the addon without registering UI can still
# read an incoming project's declarations. Register/unregister manages Save only.
catalog._project_reader = project_families
