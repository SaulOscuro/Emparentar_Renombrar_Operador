"""Version-independent, shared custom naming families. No Blender dependency."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

SCHEMA_VERSION = 1
RESERVED = frozenset({'primitive', 'stuff', 'wall', 'interiorwall', 'floor', 'ceiling',
    'frame', 'hardware', 'leftpanel', 'rightpanel', 'closedleftpanel', 'closedrightpanel',
    'openleftpanel', 'openrightpanel'})
LABEL = re.compile(r'[a-z]+(?:&[a-z]+)*', re.ASCII)
NAME = re.compile(r'(?:wall|interiorwall|floor|ceiling)\d+_([a-z]+(?:&[a-z]+)*)\d+(?:\.\d{3,})?', re.I | re.ASCII)
_path = None
_signature = None
_families = frozenset()
_error = ''
_next_check = 0.0


def config_path():
    # This override also keeps automated tests away from real user preferences.
    override = os.environ.get('J3D_NAMING_CONFIG')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming')))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return base / 'J3DTools' / 'naming_families.json'


def normalize_family(value):
    if not isinstance(value, str):
        raise ValueError('Escribe una familia, por ejemplo wood.')
    label = value.strip().lower()
    if not 1 <= len(label) <= 48 or not LABEL.fullmatch(label):
        raise ValueError('Usa letras sin números, espacios ni guiones; por ejemplo wood.')
    if label in RESERVED:
        raise ValueError('Esta familia está reservada o excluida de los nombres admitidos.')
    return label


def family_from_name(name):
    match = NAME.fullmatch(name)
    if not match:
        raise ValueError('Se requiere un nombre como wall3_wood0, con padre, familia e índice.')
    return normalize_family(match.group(1))


def _read(path):
    if not path.exists():
        return {'schema_version': SCHEMA_VERSION, 'families': []}
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('El archivo de familias supera el tamaño permitido.')
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Formato de configuración de familias no compatible.')
    labels = data.get('families')
    if not isinstance(labels, list) or len(labels) > 256:
        raise ValueError('La lista debe contener como máximo 256 familias.')
    data['families'] = sorted({normalize_family(label) for label in labels})
    return data


def refresh(force=False):
    global _path, _signature, _families, _error, _next_check
    path = config_path()
    now = time.monotonic()
    if not force and path == _path and now < _next_check:
        return False
    before = (_path, _families, _error)
    if path != _path:
        _path, _signature, _families, _error = path, None, frozenset(), ''
    _next_check = now + 1.0
    try:
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
        except FileNotFoundError:
            signature = ('missing',)
        if force or signature != _signature:
            data = _read(path)
            _families = frozenset(data['families'])
            _error = ''
            _signature = signature
    except (OSError, ValueError) as exc:
        # Preserve the last valid list and never overwrite a damaged file.
        _error = 'No se pudo leer la lista compartida: ' + str(exc)
    return before != (_path, _families, _error)


def families():
    refresh()
    return _families


def error():
    refresh()
    return _error


@contextmanager
def _file_lock(path):
    # OS locks are released even if Blender exits while writing. Both copies of
    # this module use the same lock, preventing simultaneous lost updates.
    with path.with_suffix('.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Otra instancia está guardando familias; vuelve a intentarlo.') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def set_family(value, *, accepted):
    label = normalize_family(value)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path):
        data = _read(path)  # Read under the lock, rather than using a stale cache.
        labels = set(data['families'])
        previous = set(labels)
        if accepted:
            labels.add(label)
        else:
            labels.discard(label)
        if len(labels) > 256:
            raise ValueError('La lista admite como máximo 256 familias.')
        if labels != previous:
            data['families'] = sorted(labels)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                                 prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(data, stream, ensure_ascii=False, indent=2)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
    refresh(force=True)
    return label
