"""Tests that run without the Blender executable."""
import unittest
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestManifest(unittest.TestCase):
    def test_version_and_package_contents(self):
        manifest = tomllib.loads((ROOT / 'blender_manifest.toml').read_text())
        self.assertEqual(manifest['id'], 'powerline_system')
        self.assertEqual(manifest['version'], '0.2.5')
        self.assertGreaterEqual(manifest['blender_version_min'], '5.2.0')
        for item in ['__init__.py','geometry.py','assets/pylonElectricity.blend','LICENSE']:
            self.assertTrue((ROOT / item).is_file(), item)
        self.assertGreater((ROOT / 'assets/pylonElectricity.blend').stat().st_size,100_000)
