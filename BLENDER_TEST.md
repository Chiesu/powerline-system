# Blender 5.2.1 functional test - Powerline System 0.2.5

## Fresh scene (about 2 minutes)

1. Install via Preferences > Get Extensions > Install from Disk. Restart Blender after replacing an older build.
2. On a new scene open N > Powerlines. Confirm the selector shows **2 | 4 | 6 | 7**, not 8.
3. Select **7** and Create Line. Confirm **two pylons with the same three arm pairs as the 6 preset**, plus one visible cable from the apex of each. Expected: **7 cables**.
4. Enable **Show Attachment Points** under Advanced. Each pylon should contain L0-L2, R0-R2 and **TOP**. The TOP locator must be at the pylon's highest vertex, not on a fourth arm pair.
5. Move and rotate either pylon in Object Mode. All 7 cables should remain connected to their respective anchors.
6. Add two more pylons. Four pylons with three sections must show **21 cables** total, including one apex-to-apex cable per section.
7. Change selector **7 -> 6 -> 4 -> 2 -> 7**. The three sections must contain **21 -> 18 -> 12 -> 6 -> 21** cables, with no orphan top cables or empty objects left behind.
8. Check that 6/7 variants share the same edge mesh datablock when their shape values match. Verify Sag, Wind, and Electricity toggles remain functional.
9. Save, reopen, move a middle pylon. Its cables must remain connected on both sides.

## Upgrade an existing v0.2.4 eight-arm scene

1. Save a backup of the original scene before opening it with v0.2.5.
2. Open the scene using the v0.2.5 addon. With an 8-arm route saved under the old fourth preset, the sidebar shows 7.
3. **Click 7 once** (even if already highlighted), or click **Update All Pylons**.
4. Confirm the fourth cross-arm pair disappears on *all* pylons, replaced by a single top-center cable attachment per support. Count 7 cables per section.
5. Confirm transforms, spacing, wind, electricity, and route order are retained.

## Known constraints

Blender runtime validation is required; offline tests alone do not prove evaluation in the actual viewport. The addon is calibrated to the original bundled pylon, not other imported pylon models. Review the bundled `.blend` for redistribution rights before GitHub publication.
