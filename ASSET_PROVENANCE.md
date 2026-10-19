# Bundled asset provenance and publishing check

The add-on depends on `assets/pylonElectricity.blend`. It is a compact reference `.blend` supplied by the project author and used to append source objects, the edge-based pylon, Geometry Nodes groups and electric/cable materials. It is **not** the manually arranged two-pylon scene added to the user's working file.

**Before making this repository public, the asset owner should verify and confirm:**

1. The pylon geometry and geometry-node electricity effect are original, or legally redistributable under terms compatible with this release.
2. Any material, image, linked library, included addon data or third-party node-group content in the `.blend` is redistributable. The source file contains a `Geo-Scatter: Per BlendFile Properties` text block and a `Rusty Pylons` material name; those identifiers **do not establish their licenses**.
3. Only assets necessary for the add-on remain inside the `.blend` (remove unrelated objects/data using Blender if needed).
4. No private local paths, credentials, or personal project data remain.

The **Python source code** is distributed under GPL-3.0-or-later. That statement does not assert ownership of third-party content embedded in the `.blend`. If the original `.blend` needs sanitization, replace it with a rights-cleared file that retains the required source objects, node groups, and materials, and rerun the Blender test checklist.
