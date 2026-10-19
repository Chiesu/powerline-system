# Powerline System v0.2.5

**Change: 2 | 4 | 6 | 7 conductors**

- Replaced the previous 8-arm option with **7**: three symmetrical side arm pairs (the original 6 layout) and a single additional conductor joining the center apex of each pylon.
- The extra wire follows tower movement, rotation and animation like the existing cable spans.
- A 7-wire route shares the **same edge mesh as the 6-wire layout**: no fourth crossarm pair or separate pylon geometry is created.
- Arm presets remain global for all supports, including those already placed; 4 pylons = 3 spans x 7 = 21 live cables.
- Preserved the source electricity node group, materials, original FX settings, wind, sag and linked geometry.
- **Compatibility:** v0.2.4 scenes previously saved with 8 wires can be converted by clicking **7** once or **Update All Pylons**. The previous fourth crossarm pair is replaced with the top attachment while leaving pylon transforms intact.

**Install:** Blender 5.2.1 > Preferences > Get Extensions > Install from Disk; choose `powerline_system-0.2.5.zip` without extracting it.

**Status:** syntax/geometry/network migration/GN structure/ZIP integrity tested offline. The new 7-wire layout must be verified in Blender before public release.

**License note:** Check the embedded demo `.blend` for third-party assets and redistribution rights before publishing on GitHub. Python source GPL-3.0-or-later.
