# Attribution

The selection-name and all-object-name viewport helpers in `name_overlays.py`
are adapted from `j3dsyncmanager2/selection_overlay.py` in
[SaulOscuro/J3DSyncManager-2.0](https://github.com/SaulOscuro/J3DSyncManager-2.0),
branch `codex/remaster-implementation` (local source supplied by the owner).
That project is licensed GPL-3.0-or-later. This distribution uses GPL version 3.

The automatic naming allocator and lifecycle in `live_naming.py` and
`automatic_tools.py` adapt the NoDot approach in `naming_service.py` and
`no_dot_live.py` from the same source. The audit's door/parent rules are adapted
from `audit_service.py`. These modules use this extension's own approved families,
Blender 4.2 name limits, hierarchy-aware object renames and a continuous report.

The extension adds shared family validation, independent red name warnings,
warning color priority, rename notifications and file-load cleanup. The original
J3DSyncManager source and repository are not modified by this extension.
