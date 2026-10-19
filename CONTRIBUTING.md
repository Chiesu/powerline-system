# Contributing

Powerline System is a small Blender add-on focused on an accessible, predictable network workflow. Contributions are welcome as issues or pull requests.

- Target Blender 5.2.1 first. Include the version and operating system in bug reports.
- Run `python -m unittest discover -s tests -p 'test_*.py' -v` before submitting.
- Test Create Line, Add Pylon + Connect, switching between 2 / 4 / 6 / 7 conductors, transform-driven cable updates, saving and reopening in Blender.
- Avoid adding heavy dependencies, frame-change Python handlers, or scene-specific hardcoded coordinates unless strictly required.
- Do not submit bundled third-party models, textures, materials, or scripts without redistribution rights.

For bug reports, include steps to reproduce, a screenshot, and the full Blender traceback when relevant. Remove private paths and data before attaching `.blend` files.
