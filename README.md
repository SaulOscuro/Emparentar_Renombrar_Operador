# Emparentar y Renombrar Inteligente

Extension **3.5.0** for **Blender 4.2+**, distributed through Blender's native
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
to `NOMBRE_ESPECIAL_RE` so previously assigned names remain recognized.

For scripts, use `INVOKE_DEFAULT` to open the selector. Non-interactive calls with
unnamed objects must explicitly pass a valid family, for example:

```python
bpy.ops.object.reparent_and_rename_smart('EXEC_DEFAULT', familia_sin_regla='bathfloor')
```

## Validation

Run the integration checks in a separate, factory-startup Blender process:

```text
blender --background --factory-startup --python-exit-code 1 --python tests/test_blender.py
```

The checks replace the test scene; do not run them in a working project.

Version 3.5.0 is tested with Blender **4.2.23 LTS**. Release packages are built and
validated with Blender 4.2's native extension commands. The minimum supported
version in the manifest is **4.2.0**.

## Build a release

```text
python scripts/build_extension.py --blender "path/to/blender.exe" --output-dir "dist/3.5.0"
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
- blender_manifest.toml
- tests/test_blender.py
- scripts/build_extension.py

## License
GPL-3.0
