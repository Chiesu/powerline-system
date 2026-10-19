"""Offline contract tests for the addon live-span node construction.
This intentionally does not replace a Blender runtime test.
"""
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

bpy = types.ModuleType('bpy')
bpy.types = types.SimpleNamespace(
    PropertyGroup=type('PropertyGroup', (), {}),
    Operator=type('Operator', (), {}),
    Panel=type('Panel', (), {}),
    Object=type('Object', (), {}),
    Mesh=type('Mesh', (), {}),
    Scene=type('Scene', (), {}),
)
bpy.app = types.SimpleNamespace(version=(5, 2, 1))
props = types.ModuleType('bpy.props')
for propname in ('BoolProperty','EnumProperty','FloatProperty','IntProperty','PointerProperty','StringProperty'):
    setattr(props, propname, lambda **kwargs: None)
bpy.props = props
sys.modules['bpy'] = bpy
sys.modules['bpy.props'] = props
mathutils = types.ModuleType('mathutils')
mathutils.Matrix = type('Matrix', (), {})
mathutils.Vector = type('Vector', (), {})
sys.modules['mathutils'] = mathutils

class Socket:
    def __init__(self, name):
        self.name = name
        self.default_value = None
        self.description = ''
        self.min_value = None
        self.max_value = None

class Sockets:
    def __init__(self, names):
        self.by_name = {}
        self.by_number = []
        for name in names:
            socket = Socket(name)
            self.by_name.setdefault(name, socket)
            self.by_number.append(socket)
    def __getitem__(self, key):
        if isinstance(key, int): return self.by_number[key]
        return self.by_name[key]

NODE_SOCKETS = {
    'NodeGroupInput': ([], ["Start Anchor", "End Anchor", "Sag Ratio", "Samples", "Wind Amplitude", "Wind Frequency", "Wind Speed"]),
    'NodeGroupOutput': (['Geometry'], []),
    'GeometryNodeObjectInfo': (['Object'], ['Location']),
    'GeometryNodeCurvePrimitiveLine': (['Start', 'End'], ['Curve']),
    'FunctionNodeIntegerMath': (['Value', 'Value'], ['Value']),
    'GeometryNodeSubdivideCurve': (['Curve', 'Cuts'], ['Curve']),
    'GeometryNodeSplineParameter': ([], ['Factor']),
    'ShaderNodeMath': (['Value', 'Value'], ['Value']),
    'ShaderNodeVectorMath': (['Vector', 'Vector', 'Scale'], ['Vector', 'Value']),
    'ShaderNodeCombineXYZ': (['X','Y','Z'], ['Vector']),
    'ShaderNodeSeparateXYZ': (['Vector'], ['X','Y','Z']),
    'GeometryNodeInputSceneTime': ([], ['Seconds']),
    'GeometryNodeSetPosition': (['Geometry','Offset'], ['Geometry']),
}
class Node:
    def __init__(self,kind):
        assert kind in NODE_SOCKETS, kind
        self.kind = kind
        self.label = ''
        self.location = (0,0)
        i, o = NODE_SOCKETS[kind]
        self.inputs = Sockets(i)
        self.outputs = Sockets(o)
        # Guard the Blender 5.2 API. No legacy Resample Curve.mode.
        self.operation = ''
        self.transform_space = ''
        self.mode = '' if kind == 'GeometryNodeCurvePrimitiveLine' else None

class NodeCollection:
    def __init__(self): self.items=[]
    def new(self,kind):
        n=Node(kind)
        self.items.append(n)
        return n
    def clear(self): self.items.clear()

class Links:
    def __init__(self): self.items=[]
    def new(self,out,inp):
        assert out is not None and inp is not None
        self.items.append((out,inp))

class InterfaceItem(Socket):
    def __init__(self,name,in_out,socket_type):
        super().__init__(name)
        self.item_type='SOCKET'
        self.in_out=in_out
        self.socket_type=socket_type
        self.identifier='Socket_0'
class Interface:
    def __init__(self): self.items_tree=[]
    def new_socket(self,name,in_out,socket_type):
        item = InterfaceItem(name,in_out,socket_type)
        self.items_tree.append(item)
        return item
    def clear(self): self.items_tree.clear()

class Tree:
    def __init__(self,name,kind):
        self.name=name
        self.bl_idname=kind
        self.nodes=NodeCollection()
        self.links=Links()
        self.interface=Interface()
        self.store={}
    def get(self,k,default=None):return self.store.get(k,default)
    def __setitem__(self,k,value): self.store[k]=value

class NodeGroups:
    def __init__(self): self.groups={}
    def new(self,name,kind):
        new=Tree(name,kind)
        self.groups[name]=new
        return new
    def get(self,name):return self.groups.get(name)

bpy.data = types.SimpleNamespace(node_groups=NodeGroups())
spec = importlib.util.spec_from_file_location('powerline_system', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
addon = importlib.util.module_from_spec(spec)
sys.modules['powerline_system'] = addon
spec.loader.exec_module(addon)
graph=addon._ensure_span_tree()
assert graph.get('_pwl_span_tree_schema') == 2
assert len(graph.nodes.items)>=25
assert any(node.kind=='GeometryNodeSubdivideCurve' for node in graph.nodes.items)
assert not any(node.kind=='GeometryNodeResampleCurve' for node in graph.nodes.items)
assert any(node.kind=='FunctionNodeIntegerMath' and node.operation=='SUBTRACT' and node.inputs[1].default_value==2 for node in graph.nodes.items)
assert any(so.name=='Value' and si.name=='Cuts' for so,si in graph.links.items)
assert addon._ensure_span_tree() is graph
# Verify recovery when a previous release left an incomplete node group.
graph.store['_pwl_span_tree_schema'] = 1
graph.nodes.items.clear()
recovered=addon._ensure_span_tree()
assert recovered is graph
assert recovered.get('_pwl_span_tree_schema') == 2
assert any(node.kind=='GeometryNodeSubdivideCurve' for node in recovered.nodes.items)
print('PASS: Geometry Nodes type/socket contract, Samples minus 2, cache and partial-group recovery.')
