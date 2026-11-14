"""Shared parenting rules and read-only viewport name validation."""
import re
from functools import lru_cache
from . import family_store
from . import nomenclature_catalog

# Approved display families. Parenting still accepts primitive and stuff;
# the red overlay deliberately excludes both.
DISPLAY_FAMILIES = nomenclature_catalog.OFFICIAL_FAMILIES

PADRE_RE = re.compile(r'^(wall|interiorwall|floor|ceiling)\d+$')
DUPLICADO_ESTRUCTURAL_RE = re.compile(
    r'^(?:wall|interiorwall|ceiling)\d+\.\d+$', re.IGNORECASE,
)
NOMBRE_ESPECIAL_RE = re.compile(
    r'^(?:'
    r'(?:wall|interiorwall|floor|ceiling)\d+_(?:'
    r'closet\d+'
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
    r'|door\d+_door\d+|door\d+_leftpanel\d+_door\d+|door\d+_rightpanel\d+_door\d+'
    r'|stuff\d+|primitive\d+|\d+'
    r')'
    r'|toallero_colgador\d+'
    r')(?:\.\d+)?$',
    re.IGNORECASE,
)

# Standard-door names produced by the operator but missing from the legacy
# primitive-name expression. Panels/hardware are valid only within a door path.
NOMBRE_PUERTA_GENERADO_RE = re.compile(
    r'^(?:wall|interiorwall|floor|ceiling)\d+_door\d+_'
    r'(?:frame\d+|(?:leftpanel|rightpanel)\d+(?:_hardware\d+)?)'
    r'(?:\.\d+)?$', re.IGNORECASE,
)
PREFIJO_FAMILIA_RE = re.compile(
    r'^(?:wall|interiorwall|floor|ceiling)\d+_([a-z&]+)\d+(?:_|\.|$)',
    re.IGNORECASE,
)


def is_parenting_name(name, custom=None):
    if NOMBRE_ESPECIAL_RE.fullmatch(name) or NOMBRE_PUERTA_GENERADO_RE.fullmatch(name):
        return True
    match = family_store.NAME.fullmatch(name)
    if match is None:
        return False
    family = match.group(1).lower()
    return family in (nomenclature_catalog.families() if custom is None else custom)


def unsupported_reason(name):
    return _unsupported_reason(name, nomenclature_catalog.families())


def family_warning(name):
    """Viewport color checks family membership only, never hierarchy or suffixes."""
    name = re.sub(r'\.\d{3,}(?=_|$)', '', name.strip())
    if PADRE_RE.fullmatch(name) or re.fullmatch(r'toallero_colgador\d+', name, re.I):
        return None
    parts = name.split('_')
    family = re.match(r'^([a-z&]+)', parts[1], re.I) if len(parts) > 1 else None
    if family and family.group(1).lower() in DISPLAY_FAMILIES | nomenclature_catalog.families():
        return None
    return 'Nombre sin familia admitida'


@lru_cache(maxsize=4096)
def _unsupported_reason(name, custom):
    """Return a display warning or None. Never change a name or scene object."""
    if not name or name != name.strip():
        return 'Formato de nombre no admitido'
    if PADRE_RE.fullmatch(name):
        return None
    if re.fullmatch(r'toallero_colgador\d+(?:\.\d+)?', name, re.IGNORECASE):
        return None
    family = PREFIJO_FAMILIA_RE.match(name)
    if family is None:
        return 'Falta un padre y una familia con sus índices'
    family = family.group(1).lower()
    if family not in DISPLAY_FAMILIES and family not in custom:
        return f'Familia no admitida: {family}'
    if is_parenting_name(name, custom):
        return None
    return 'Estructura de familia no admitida'
