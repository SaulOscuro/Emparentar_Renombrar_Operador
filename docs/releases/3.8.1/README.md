# Emparentar 3.8.1

Red viewport labels now mean an unrecognized naming family only. Missing or
incorrect parents and duplicate suffixes no longer color a recognized family
red. The full read-only audit remains available independently.

Before native GLB export writes a file, recognized child meshes without a parent
show a central informational dialog. Review cancels the export and selects the
visible selectable affected objects; Export Anyway resumes the same native
export/options once. Cancel writes nothing. No branch renames/reparents objects.
Roots, existing parents and objects filtered out by the export options do not
prompt. Plain glTF is unaffected. Background exports cannot ask a question and
return CANCELLED with the affected names, rather than silently writing a GLB.

The same guard ships in J3D through the versioned dependency. It is installed
once even if both addons are enabled and native execute is restored on disable.

Validation: 36 existing Blender tests; custom-family regression; actual native
GLB exports; foreground File > Export file-browser flow and drawn dialog in
Blender 4.2.23 and 5.2.4; confirmation, cancellation, review, selection/visibility/
render filters, existing parents and repeated enable/disable.

Package: 46134 bytes. SHA-256:
`1084e1ef1f69bb9b0d6b6286f68dd561b599d6fbd4e5a65ab3fce20e01c876ea`.
