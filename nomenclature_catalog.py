"""Authoritative family catalog shared by Emparentar and J3D.

Membership is defined here, never inferred from the current material workflow.
Personal families extend it; the optional project reader supplies declarations
carried by a .blend received from another user.
"""
from . import family_store

OFFICIAL_FAMILIES = frozenset({
    'alacena', 'apagador', 'bathfloor', 'bathtub', 'bathub', 'black', 'board',
    'cabinet', 'chrome', 'closet', 'coladera', 'colgador', 'collider', 'cubierta',
    'cubiertacabinet', 'cubiertalavabo', 'door', 'enchufe', 'estufa', 'faucet',
    'fridge', 'fridge&micro', 'glass', 'hvac', 'jaladera', 'lamp', 'lampara',
    'lampemission', 'lampmetal', 'lavabo', 'luz', 'microwave', 'mirror', 'perchero',
    'regadera', 'rejillas', 'repisa', 'seat', 'showertray', 'trim', 'tuborepisa',
    'vent', 'wall', 'wallbathtiles', 'white', 'window', 'wood',
})
_project_reader = None


def families():
    project = _project_reader() if _project_reader else frozenset()
    return OFFICIAL_FAMILIES | family_store.families() | project


def custom_families():
    return families() - OFFICIAL_FAMILIES
