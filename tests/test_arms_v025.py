"""Blender-independent geometry and UI contract tests for v0.2.5."""
from pathlib import Path
import unittest
import sys
import ast
import hashlib
import json
from types import SimpleNamespace

root = Path(__file__).parents[1]
sys.path.insert(0, str(root))
from geometry import calibrate, make_pylon, arm_levels, pylon_apex

fixture = json.loads((root / 'tests' / 'fixtures' / 'pylon_source_geometry.json').read_text())
source_vertices = [tuple(p) for p in fixture['vertices']]
source_edges = [tuple(e) for e in fixture['edges']]
c = calibrate(source_vertices)

class TestArmGenerator(unittest.TestCase):
    def test_levels_and_mesh_size(self):
        for pairs in (1,2,3):
            with self.subTest(pairs=pairs):
                levels=arm_levels(pairs,c.middle_tier,c.spacing)
                verts,edges,sockets=make_pylon(source_vertices,source_edges,c,pairs=pairs)
                self.assertEqual(len(levels),pairs)
                self.assertEqual(len(sockets),pairs*2)
                self.assertEqual(set(sockets), {f'{side}{i}' for i in range(pairs) for side in ('L','R')})
                self.assertTrue(all(0<=v<len(verts) for e in edges for v in e))
                self.assertTrue(all(a!=b for a,b in edges))
                self.assertEqual(len({tuple(sorted(e)) for e in edges}),len(edges))
                self.assertLess(len(verts),120)
                self.assertLess(len(edges),260)
                print(f'{pairs*2} side conductors: {len(verts)} verts, {len(edges)} edges')

    def test_7_uses_existing_6_arm_tower(self):
        verts,edges,sockets=make_pylon(source_vertices,source_edges,c,pairs=3)
        apex=pylon_apex(source_vertices)
        self.assertAlmostEqual(apex[0],0,places=4)
        self.assertAlmostEqual(apex[2],0,places=4)
        self.assertAlmostEqual(apex[1],max(p[1] for p in source_vertices),places=4)
        self.assertGreater(apex[1],max(p[1] for p in sockets.values()))
        self.assertEqual(len(sockets),6)
        self.assertIn(apex,source_vertices)
        self.assertIn(apex,verts)
        # No fourth crossarm is created by the 7-wire mode.
        self.assertEqual(len(verts),83)
        self.assertEqual(len(edges),182)

    def test_invalid_pairs(self):
        for count in (0,4,5,-1):
            with self.assertRaises(ValueError):
                make_pylon(source_vertices,source_edges,c,pairs=count)

class TestSelector(unittest.TestCase):
    def test_layout_helpers_and_mesh_sharing(self):
        src = (root/'__init__.py').read_text()
        wanted={'_side_pairs','_has_top_wire','_wire_count','_variant_key'}
        ast_tree=ast.parse(src)
        functions=[n for n in ast_tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted]
        self.assertEqual(set(n.name for n in functions),wanted)
        g={'hashlib':hashlib}
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(root/'__init__.py'),'exec'),g)
        self.assertEqual([g['_wire_count'](i) for i in (1,2,3,4)],[2,4,6,7])
        self.assertEqual([g['_side_pairs'](i) for i in (1,2,3,4)],[1,2,3,3])
        self.assertTrue(g['_has_top_wire'](4))
        self.assertFalse(g['_has_top_wire'](3))
        source=SimpleNamespace(name='pylon mesh')
        make_settings=lambda n: SimpleNamespace(pairs=str(n),arm_reach=.96,arm_spacing=1.69,
                          arm_height=14.16,insulator_drop=.48)
        self.assertEqual(g['_variant_key'](source,make_settings(3)),g['_variant_key'](source,make_settings(4)))
        self.assertNotEqual(g['_variant_key'](source,make_settings(2)),g['_variant_key'](source,make_settings(4)))

    def test_labels_and_top_hook(self):
        text=(root/'__init__.py').read_text()
        self.assertEqual(text.count('_draw_arm_count_buttons(col, st)'),2)
        self.assertIn('for pairs in (1, 2, 3, 4)',text)
        self.assertIn("text=str(_wire_count(pairs))",text)
        self.assertIn("('4', '7', 'Three arm pairs plus one centered top wire')",text)
        self.assertIn("coordinates['TOP'] = pylon_apex",text)
        self.assertIn("aa['TOP'], bb['TOP'], 'TOP', 3",text)
        self.assertIn("_needs_pylon_rebuild(p)",text)
        self.assertNotIn("('4', '8'",text)
        self.assertIn('"version": (0, 2, 5)',text)

if __name__=='__main__':unittest.main()
