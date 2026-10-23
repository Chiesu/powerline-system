# Powerline System 0.2.5

Procedural powerline route builder for **Blender 5.2.1**. Download the installable ZIP from [Releases](https://github.com/Chiesu/powerline-system/releases/latest) (not GitHub's automatically generated source archive). Create two matching pylons, extend the route with one click, and move/rotate supports while all cables follow live. Built around the supplied lightweight edge-based pylon and the existing `GN_CableElectricity_FX` group.

<img width="1920" height="1080" alt="hero" src="https://github.com/user-attachments/assets/e6ee7d1d-7707-4019-a25f-45b543922822" />

## Install

1. Back up your scene. In Blender, open **Edit > Preferences > Get Extensions > Install from Disk**.
2. Install `powerline_system-0.2.5.zip` directly, without extracting it. If a previous extension does not update cleanly, uninstall that version, restart Blender, then install v0.2.5.
3. In the 3D Viewport, press `N` and open **Powerlines**.
4. Select **2 | 4 | 6 | 7** and press **Create Line (2 Pylons)**. Two linked-mesh pylons and their live cable spans appear at the 3D cursor.
5. Move the selected pylon with `G`, or rotate it with `R`. The parented attachment points and their cables follow.
6. Use **Add Pylon + Connect** to extend the line as many times as needed. Each new support is automatically connected to its predecessor.

<img width="1920" height="1080" alt="create-line" src="https://github.com/user-attachments/assets/1ec494c9-ce5c-4f6d-81a7-4612f1f69492" />

## Arm / conductor presets

| Selector | Physical structure | Cable count per section |
|---|---|---:|
| **2** | One left/right arm pair | 2 |
| **4** | Two left/right arm pairs | 4 |
| **6** | Three left/right arm pairs | 6 |
| **7** | The **same three arm pairs as 6**, plus **one cable attached to the centered tower apex** | 7 |

**7 is not four arm pairs.** The tower retains the original 6-arm silhouette. The extra cable's `TOP` attachment sits exactly at the top vertex of the supplied pylon's source mesh. The top locator is parented to its tower, and the extra span is generated through the same live Geometry Nodes chain. In a four-pylon route (three sections), 7 generates **21 cable objects**.

Changing the selector updates **every pylon in the route**, not just the active object. New pylons inherit the network's choice. Matching 6- and 7-wire pylons reuse the **same lightweight edge-mesh datablock**, with a top attachment added only in mode 7.

## Updating from v0.2.4

The old 8-wire preset stored the internal value `4`, now reassigned to the 7-wire preset for compatibility. When opening a saved 8-wire scene, **click the `7` selector once** or use **Update All Pylons** in the Powerlines panel. This replaces each fourth crossarm pair with a top-center attachment and rebuilds the cables across the route. It does not reposition or resize your existing pylons. Existing 2/4/6 layouts remain unchanged.

The addon detects obsolete mesh variants and missing apex anchors. If an update fails, it attempts to restore the previous set of connections. Use a backed-up `.blend` when upgrading.

## UI

<img width="1920" height="1080" alt="route-settings" src="https://github.com/user-attachments/assets/02b72a29-81e7-49ad-9b53-4403f9d4a2a2" />

- **Main actions:** Create Line, Add Pylon + Connect, global 2/4/6/7 selector.
- **Cables:** Sag, Wind, Electricity switch (retains the source modifier defaults).
- **Selected Pylon > Shape** (collapsed): arm length, height, gap, cable offset. Individual dimensions can vary without breaking links.
- **Advanced:** next span spacing, add-at-cursor, show anchors, cable resolution, wind animation, pulse seed variation, rebuild line, reset/deletion, and original electricity preset parameters.

## Architecture

- Appends the original `pylon` and `cables` objects as hidden internal source datablocks. It does **not** import the old two-pylon scene layout or the manually arranged cables.
- Duplicates pylon **Objects** while reusing shared edge-based **Mesh** datablocks; copies each pylon's Mirror and Geometry Nodes modifier stack. Geometry differences use copy-on-write variants rather than changing neighboring pylons.
- Generates parented locator empties for each selected arm tip, plus `TOP` for the 7-wire preset. Each cable's Geometry Nodes modifier references a start/end locator and evaluates live when either pylon moves, rotates, or animates. No Python per-frame callback or baked animation is used.
- Uses simple distance-driven parabolic sag and optional wind; the original `GN_CableElectricity_FX` node group and its material/preset input values remain in the cable modifier stack. The original electric seed is retained unless **Vary Pulse Seeds** is enabled.
- Connections follow creation order. Adding a pylon extends the final section; moving pylons does not reorder the route.

## Limitations

- Tested **offline** for syntax, procedural geometry, migration logic, node graph structure, and package integrity; **Blender viewport runtime testing of the new seventh conductor is still required**.
- The built-in source is specifically calibrated to the provided pylon, whose local **Y** is up, **X** defines arms, and **Z** is depth. It is not an arbitrary imported-tower rigging tool.
- Manual Shift+D / Alt+D on a pylon does not create route-level IDs or automatically connect it. Use **Add Pylon + Connect**.
- Sag is art-directed rather than a fixed-length physical catenary; very large vertical offsets may look unrealistic.
- Long routes contain individual cable objects/modifiers and may evaluate more slowly than a future batched solution.
- Before uploading to GitHub, review redistribution rights for every asset embedded in the bundled `.blend`. The Python source code is GPL-3.0-or-later; that license does not grant rights to third-party demo assets.


## Development

This repository contains the add-on source in the root, the required reference asset under `assets/`, offline tests under `tests/`, and a build script under `scripts/`. Run:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/build_release.py
```

The release builder creates `dist/powerline_system-0.2.5.zip`. Offline tests do **not** replace Blender viewport testing. See [`BLENDER_TEST.md`](BLENDER_TEST.md).

## License and source assets

The original Python source is published under **GPL-3.0-or-later** (see [`LICENSE`](LICENSE)). The add-on requires `assets/pylonElectricity.blend` to build the demo pylons and load the default electricity effect. Review [`ASSET_PROVENANCE.md`](ASSET_PROVENANCE.md) before redistributing the bundled file. Licensing the code does not automatically license unrelated third-party assets.

Issues and contributions are welcome through GitHub. Please include your Blender version and the smallest reproducible scene for bugs.
