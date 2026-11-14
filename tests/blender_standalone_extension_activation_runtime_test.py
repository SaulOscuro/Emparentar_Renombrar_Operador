"""Native install/enable/disable of the Emparentar extension in isolated Blender."""
import json
import os
from pathlib import Path
import traceback
from zipfile import ZipFile
import bpy
import io_scene_gltf2

OUT=Path(os.environ['J3D_LIFECYCLE_OUT'])
ARCHIVE=Path(os.environ['J3D_LIFECYCLE_ARCHIVE'])
result={'success':False}
try:
    native=io_scene_gltf2.ExportGLTF2.execute
    path=OUT/'private-repository'
    bpy.ops.preferences.extension_repo_add(name='Emparentar Activation Test', type='LOCAL',
        use_custom_directory=True, custom_directory=str(path))
    repo=next(r for r in bpy.context.preferences.extensions.repos if Path(r.directory)==path)
    assert bpy.ops.extensions.package_install_files(filepath=str(ARCHIVE),repo=repo.module,
        enable_on_install=False)=={'FINISHED'}
    name='bl_ext.'+repo.module+'.emparentar_renombrar_operador'
    with ZipFile(ARCHIVE) as package:
        files=[n for n in package.namelist() if not n.endswith('/')]
        assert all((path/'emparentar_renombrar_operador'/n).read_bytes()==package.read(n) for n in files)
    for _ in range(2):
        assert bpy.ops.preferences.addon_enable(module=name)=={'FINISHED'}
        assert io_scene_gltf2.ExportGLTF2.execute is not native
        assert bpy.ops.j3d_naming.glb_parenting_warning.get_rna_type()
        assert bpy.ops.preferences.addon_disable(module=name)=={'FINISHED'}
        assert io_scene_gltf2.ExportGLTF2.execute is native
    result={'success':True,'files':len(files),'blender':bpy.app.version_string,
            'checks':['native installation','restricted enable twice','disable restores native exporter']}
except Exception:
    result['error']=traceback.format_exc()
    print(result['error'])
(OUT/'activation-result.json').write_text(json.dumps(result,indent=2))
print(result,flush=True)
if not result['success']:
    os._exit(1)
os._exit(0)  # Private fixture process; do not open the first-run quit/splash modal.
