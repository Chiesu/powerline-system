"""Blender-independent network tests: 2/4/6/7 including same-value migration."""
import ast
import contextlib
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE=Path(__file__).parents[1]/'__init__.py'
TREE=ast.parse(SOURCE.read_text())
NAMES={'_side_pairs','_has_top_wire','_wire_count','_pair_key','_connect','_spanned_pairs','_sync_global_arms'}
FUNCTIONS=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert {n.name for n in FUNCTIONS}==NAMES

class FakePylon:
    next_id=0
    def __init__(self,layout='3'):
        self.pwl=SimpleNamespace(pairs=str(layout),is_pylon=True)
        self.meta={}
        self.anchor_count=int(layout)*2
        self.stale=False
        self.ref=FakePylon.next_id; FakePylon.next_id+=1
    def __setitem__(self,key,val):self.meta[key]=val
    def as_pointer(self):return self.ref

class FakeCable:
    def __init__(self,scene,a,b,side,idx):
        self.scene=scene
        self.pwl=SimpleNamespace(start_pylon=a,end_pylon=b,span_side=side,span_row=idx,is_span=True)
        self.data=SimpleNamespace(users=0)

class FakeBpy:
    def __init__(self):
        self.data=SimpleNamespace(objects=SimpleNamespace(remove=self.remove_obj),
                                  meshes=SimpleNamespace(remove=lambda mesh:None))
    def remove_obj(self,obj,do_unlink=False):obj.scene.spans.remove(obj)

class TestNetwork(unittest.TestCase):
    def setUp(self):
        self.pylons=[FakePylon() for i in range(4)]
        self.scene=SimpleNamespace(pwl=SimpleNamespace(initial_pairs='3'),spans=[],pylons=self.pylons)
        self.fail_once=False
        self.bpy=FakeBpy()

        def make_span(scene,a,b,start,end,side,idx):
            if self.fail_once:
                self.fail_once=False
                raise RuntimeError('simulated Blender failure')
            o=FakeCable(scene,a,b,side,idx)
            scene.spans.append(o)
            return o

        def anchors(p):
            if p.stale and p.pwl.pairs=='4':
                result={f'{side}{i}':(p.ref,side,i) for i in range(4) for side in ('L','R')}
            else:
                pairs=min(int(p.pwl.pairs),3)
                result={f'{side}{i}':(p.ref,side,i) for i in range(pairs) for side in ('L','R')}
                if p.pwl.pairs=='4':result['TOP']=(p.ref,'TOP',0)
            return result
        def rebuild(p,scene):
            p.stale=False
            p.anchor_count=len(anchors(p))

        @contextlib.contextmanager
        def hold_updates():yield

        self.ns={'bpy':self.bpy,'_spans':lambda s:list(s.spans),
            '_pylons':lambda s:list(s.pylons),'_make_span':make_span,
            '_anchors_of':anchors,'_rebuild_pylon':rebuild,
            '_needs_pylon_rebuild':lambda p:p.stale,
            '_is_live_pointer':lambda p:True,'hold_updates':hold_updates,'traceback':traceback}
        exec(compile(ast.Module(body=FUNCTIONS,type_ignores=[]),str(SOURCE),'exec'),self.ns)
        for a,b in zip(self.pylons,self.pylons[1:]):self.ns['_connect'](self.scene,a,b)

    def assert_layout(self,wire_count,layout):
        self.assertEqual(len(self.scene.spans),3*wire_count)
        for p in self.pylons:
            self.assertEqual(p.pwl.pairs,str(layout))
            self.assertEqual(p.anchor_count,wire_count)
        for a,b in zip(self.pylons,self.pylons[1:]):
            group=[c for c in self.scene.spans if c.pwl.start_pylon==a and c.pwl.end_pylon==b]
            self.assertEqual(len(group),wire_count)
            self.assertEqual(len({(c.pwl.span_side,c.pwl.span_row) for c in group}),wire_count)
            if wire_count==7:
                top=[c for c in group if c.pwl.span_side=='TOP']
                self.assertEqual(len(top),1)
                self.assertEqual(top[0].pwl.span_row,3)
            else:self.assertFalse(any(c.pwl.span_side=='TOP' for c in group))

    def test_six_to_seven_and_back(self):
        self.assert_layout(6,3)
        for layout,count in ((4,7),(2,4),(1,2),(4,7),(3,6)):
            self.scene.pwl.initial_pairs=str(layout)
            self.assertEqual(self.ns['_sync_global_arms'](self.scene),(4,3))
            self.assert_layout(count,layout)
        self.assertEqual(self.ns['_sync_global_arms'](self.scene),(0,0))

    def test_saved_eight_mode_migrates_to_seven_with_same_enum_value(self):
        # Simulate v0.2.4: same '4' enum, old fourth-pair mesh and old 8 cables.
        self.scene.pwl.initial_pairs='4'
        for p in self.pylons:
            p.pwl.pairs='4'
            p.anchor_count=8
            p.stale=True
        self.scene.spans.clear()
        for a,b in zip(self.pylons,self.pylons[1:]):
            for i in range(4):
                for side in ('L','R'):
                    self.scene.spans.append(FakeCable(self.scene,a,b,side,i))
        self.assertEqual(len(self.scene.spans),24)
        self.assertEqual(self.ns['_sync_global_arms'](self.scene),(4,3))
        self.assert_layout(7,4)
        self.assertFalse(any(p.stale for p in self.pylons))

    def test_mixed_six_seven_only_common_side_cables(self):
        a,b=self.pylons[:2]
        b.pwl.pairs='4'
        self.ns['_rebuild_pylon'](b,self.scene)
        self.assertEqual(self.ns['_connect'](self.scene,a,b),6)
        group=[c for c in self.scene.spans if c.pwl.start_pylon==a and c.pwl.end_pylon==b]
        self.assertEqual(len(group),6)
        self.assertFalse(any(c.pwl.span_side=='TOP' for c in group))

    def test_failed_switch_preserves_working_old_cables(self):
        self.scene.pwl.initial_pairs='4'
        self.fail_once=True
        with self.assertRaisesRegex(RuntimeError,'simulated Blender'):
            self.ns['_sync_global_arms'](self.scene)
        self.assert_layout(6,3)

if __name__=='__main__':unittest.main()
