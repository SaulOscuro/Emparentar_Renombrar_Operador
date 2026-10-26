"""Automatic scene audit using this add-on's approved naming families."""
import re

from .naming_rules import PADRE_RE, unsupported_reason
from .live_naming import canonical, DUPLICATE


def expected_parent(name):
    if PADRE_RE.fullmatch(name) or name.startswith('toallero_colgador'):
        return None
    parts = name.split('_')
    final = parts[-1]
    if re.fullmatch(r'hardware\d+|door\d+', final, re.IGNORECASE) and len(parts) > 2:
        return '_'.join(parts[:-1])
    if re.fullmatch(r'(?:closed|open)?(?:left|right)panel\d+', final, re.IGNORECASE):
        return '_'.join(parts[:-1]) + '_frame0'
    return parts[0]


def object_issues(obj):
    if obj.type != 'MESH':
        return ()
    name = obj.name
    clean = canonical(name)
    issues = []
    reason = unsupported_reason(clean)
    if reason:
        issues.append(reason)
    if DUPLICATE.search(name):
        issues.append('Sufijo de duplicado pendiente de corregir')
    if reason is None:
        expected = expected_parent(clean)
        if expected and obj.parent is None:
            issues.append(f'Falta el padre {expected}')
        elif expected and canonical(obj.parent.name) != expected:
            issues.append(f'Padre esperado: {expected}; actual: {obj.parent.name}')
    return tuple(issues)


def audit_scene(scene, failures=None):
    failures = failures or {}
    report = []
    for obj in sorted(scene.objects, key=lambda item: item.name):
        if obj.type != 'MESH':
            continue
        issues = list(object_issues(obj))
        failure = failures.get(obj.as_pointer())
        if failure and failure not in issues:
            issues.append(failure)
        if issues:
            report.append((obj.name, tuple(issues)))
    return tuple(report)
