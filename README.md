# Emparentar y Renombrar Inteligente

Extension **3.6.0** for **Blender 4.2+**, distributed through Blender's native
remote extension repositories. Source and releases are hosted in this GitHub
repository; no separate server or access token is required.

Blender addon to rename and parent objects for doors, closets, and primitives
based on naming rules. It expects an active object named `wallN`,
`interiorwallN`, `floorN`, or `ceilingN` and a selection in Object Mode.

## Features
- Smart renaming for doors, closet doors with panels/hardware, and primitives
- Parents processed objects under the active wall/interiorwall/floor/ceiling
- Preserves the chrome family (e.g. wall0_chrome0, interiorwall1_chrome2,
  ceiling0_chrome0), aligns the parent prefix, and resolves duplicate indices.
- Operator available in View3D > Object menu
- Objects without a recognized naming rule open a family selector with name previews.
- Floors suggest `bathfloor`: `Cube` + active `floor0` becomes `floor0_bathfloor0`.

## Requirements
- Blender 4.2+

## Install from the remote repository

Repository URL (paste this complete URL into Blender):

```text
https://raw.githubusercontent.com/SaulOscuro/Emparentar_Renombrar_Operador/codex/extension-repository/stable/index.json
```

1. In Blender 4.2, open Edit > Preferences > Get Extensions and allow online access.
2. Open Repositories, choose Add Remote Repository, and paste the URL above.
3. Refresh the repository and install **Emparentar y Renombrar Inteligente**.
4. Enable the extension. Future releases appear through Blender's native update controls.

If the previous legacy ZIP is enabled, disable it in Add-ons before enabling the
extension: both versions provide the same operator. The objects and their names
remain in the scene.

The release ZIP can also be installed using **Install from Disk** in Get Extensions.
Installing through the remote repository is the route that provides remote updates.

## Usage
1. In Object Mode, select the objects you want to process.
2. Select the parent last so it is active: `wallN`, `interiorwallN`, `floorN`, or `ceilingN`.
3. Run View3D > Object > Emparentar y Renombrar Inteligente.
4. If objects have no recognized family, choose a family in the dialog and review
   the proposed names. Confirm to rename and parent, or cancel to leave the scene
   unchanged. The chosen family applies to all objects without a rule in the selection.

## Family suggestions (3.4.0)

- `floorN`: suggests `bathfloor`, with `primitive` available as a generic alternative.
- `wallN`, `interiorwallN`, `ceilingN`: specific suggestions are pending; the dialog
  currently offers only the generic `primitive` family.
- Recognized families, including `chrome` and previously assigned `bathfloor`, keep
  their existing rules. Indices avoid collisions, even with objects outside the parent.
- A selection of several unnamed objects gets successive available names, for example
  `floor0_bathfloor0` and `floor0_bathfloor1`. Existing named families in a mixed selection
  retain their own family.
- Door and closet hierarchies retain their existing handling: select one hierarchy
  root and the active parent. Hierarchies are skipped when processing multiple roots.

Future suggestions belong in `SUGERENCIAS_POR_PADRE`; also add their naming patterns
to `naming_rules.NOMBRE_ESPECIAL_RE` so previously assigned names remain recognized.

For scripts, use `INVOKE_DEFAULT` to open the selector. Non-interactive calls with
unnamed objects must explicitly pass a valid family, for example:

```python
bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
```

## Viewport name overlays (3.6.0)

The 3D Viewport **View** menu has three independent switches:

- **Selection Name Overlay:** the active selected object's name follows the cursor,
  in white for supported names.
- **All Object Names:** labels every visible object at its visual center.
- **Unsupported Names (Red):** labels unsupported names in bright red, slightly
  larger and with a `!` marker. Objects do not need to be selected. Red takes
  priority over white when modes are combined.

Selection names and red warnings start enabled; all-object names start disabled.
The switches apply for the current session and survive opening another blend.
Blender's Show Overlays switch hides these labels too. Hidden objects are excluded.
Renaming an object refreshes its label. These are display-only tools: they never
rename, reparent or delete objects and do not change materials or object colors.

The red overlay validates whole naming structures, not just matching substrings:

- Valid: `wall1`, `wall1_chrome0`, `floor0_bathfloor0`, `ceiling0_vent0` and the
  supported door/closet frame, panel and hardware paths.
- Red: `Cube`, `wall_1`, `wall1_1`, `wall0_Cube`, `wall0_primitive0`, unknown
  families and malformed family paths.
- `primitive` remains available as a parenting fallback, but is deliberately
  excluded from the display whitelist. Root structures and the existing
  `toallero_colgadorN` exception remain valid. Supported `.001` duplicate suffixes
  on family names retain their existing recognition.

The approved display families are alacena, apagador, bathfloor, board, chrome,
closet, coladera, colgador, collider, door, enchufe, estufa, faucet, fridge,
fridge&micro, glass, hvac, jaladera, lamp, lampara, lavabo, luz, mirror, perchero,
regadera, repisa, seat, stuff, trim, vent, wall and window.

This checks naming structure; it does not infer object contents or validate their
actual parenting relationships. Attribution is in `THIRD_PARTY_NOTICES.md`.

## Validation

Run the integration checks in a separate, factory-startup Blender process:

```text
blender --background --factory-startup --python-exit-code 1 --python tests/test_blender.py
```

The checks replace the test scene; do not run them in a working project.

Version 3.6.0 is tested with Blender **4.2.23 LTS**. Release packages are built and
validated with Blender 4.2's native extension commands. The minimum supported
version in the manifest is **4.2.0**.

## Build a release

```text
python scripts/build_extension.py --blender "path/to/blender.exe" --output-dir "dist/3.6.0"
```

The output directory must be empty. The script runs the integration tests, builds
and validates the extension ZIP, then generates `index.json` with its size and
SHA-256. It uses a separate Blender test profile.

Source lives on `main`. The `codex/extension-repository` branch contains the
`stable/index.json` catalog and immutable versioned ZIPs. For the next release,
increase `version` in `blender_manifest.toml`, build into a new directory, add the
new ZIP and replace the catalog in one distribution commit. Keep previous ZIPs.
Verify the published catalog and downloaded archive hash before reporting a release.

## Files
- __init__.py
- naming_rules.py
- name_overlays.py
- blender_manifest.toml
- tests/test_blender.py
- scripts/build_extension.py

## License
GPL-3.0
