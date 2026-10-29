"""Shared parenting rules and read-only viewport name validation."""
import re
from functools import lru_cache

# Approved display families. Parenting still accepts primitive and stuff;
# the red overlay deliberately excludes both.
DISPLAY_FAMILIES = frozenset({
    'alacena', 'apagador', 'bathfloor', 'bathtub', 'bathub', 'black', 'board', 'chrome', 'closet',
    'coladera', 'colgador', 'collider', 'door', 'enchufe', 'estufa',
    'faucet', 'fridge', 'fridge&micro', 'glass', 'hvac', 'jaladera',
    'lamp', 'lampara', 'lampemission', 'lampmetal', 'lavabo', 'luz', 'mirror', 'perchero',
    'regadera', 'repisa', 'seat', 'trim', 'vent', 'wall', 'window',
})

PADRE_RE = re.compile(r'^(wall|interiorwall|floor|ceiling)\d+$')
DUPLICADO_ESTRUCTURAL_RE = re.compile(
    r'^(?:wall|interiorwall|ceiling)\d+\.\d+$', re.IGNORECASE,
)
NOMBRE_ESPECIAL_RE = re.compile(
    r'^(?:'
    r'(?:wall|interiorwall|floor|ceiling)\d+_(?:'
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
    r'|black\d+|chrome\d+|coladera\d+|colgador\d+|door\d+|glass\d+'
    r'|door\d+_door\d+|door\d+_leftpanel\d+_door\d+|door\d+_rightpanel\d+_door\d+'
    r'|enchufe\d+|estufa\d+|faucet\d+|fridge&micro\d+|fridge\d+|hvac\d+'
    r'|jaladera\d+|lampara\d+|lamp\d+|lampemission\d+|lampmetal\d+|lavabo\d+|luz\d+|mirror\d+'
    r'|perchero\d+|regadera\d+|repisa\d+|seat\d+|stuff\d+|trim\d+|vent\d+|window\d+|collider\d+|\d+'
    r'|bathfloor\d+|bathtub\d+|bathub\d+|primitive\d+|wall\d+'
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


@lru_cache(maxsize=4096)
def unsupported_reason(name):
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
    if family not in DISPLAY_FAMILIES:
        return f'Familia no admitida: {family}'
    if NOMBRE_ESPECIAL_RE.fullmatch(name) or NOMBRE_PUERTA_GENERADO_RE.fullmatch(name):
        return None
    return 'Estructura de familia no admitida'
