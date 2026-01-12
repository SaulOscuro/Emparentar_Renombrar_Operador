# Emparentar Renombrar Operador

Blender addon to rename and parent objects for doors, closets, and primitives
based on naming rules. It expects an active object named `wallN`,
`interiorwallN`, or `ceilingN` and a selection in Object Mode.

## Features
- Smart renaming for doors, closet doors with panels/hardware, and primitives
- Parents processed objects under the active wall/interiorwall/ceiling
- Operator available in View3D > Object menu

## Requirements
- Blender 4.2+

## Installation
1. In Blender, open Edit > Preferences > Add-ons.
2. Click Install and select the addon folder (or a zip if you package it).
3. Enable "Emparentar y Renombrar Inteligente".

## Usage
1. Select a parent object named `wallN`, `interiorwallN`, or `ceilingN`.
2. Select the objects you want to process in Object Mode.
3. Run View3D > Object > Emparentar y Renombrar Inteligente.

## Files
- __init__.py

## License
GPL-3.0
