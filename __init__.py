"""Powerline System: original line-based pylons + live anchor-driven cables.

Create an independent line from a single bundled pylon source.
Target: Blender 5.2.1 (5.0+ syntax). No frame-change handlers or baking.
"""
bl_info = {
    "name": "Powerline System",
    "author": "Chiesu",
    "version": (0, 2, 5),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Powerlines",
    "description": "Modular line-based pylons with live cable anchors and original electricity FX",
    "category": "Object",
}

import os
import math
import uuid
import hashlib
import traceback
from contextlib import contextmanager

import bpy
from bpy.props import (
    BoolProperty, EnumProperty, FloatProperty, IntProperty,
    PointerProperty, StringProperty,
)
from mathutils import Matrix, Vector
from .geometry import calibrate, make_pylon, arm_levels, pylon_apex

ROOT_COLLECTION = "PWL | Powerline Network"
PYLON_COLLECTION = "PWL | Pylons"
CURVE_TREE_NAME = "PWL | Live Catenary-style Span"
SPAN_TREE_SCHEMA = 2
SOURCE_MESH_NAME = "PWL | Original Pylon Edges"
ANCHOR_COLLECTION = "PWL | Anchors"
SPAN_COLLECTION = "PWL | Cable Spans"
DEMO_FILENAME = "pylonElectricity.blend"
UPDATING = False


def _side_pairs(layout):
    """Number of symmetric crossarm pairs: 7 wires = 3 pairs + apex."""
    value = int(layout)
    if value not in (1, 2, 3, 4):
        raise ValueError('Unsupported arm configuration: ' + str(layout))
    return min(value, 3)


def _has_top_wire(layout):
    return int(layout) == 4


def _wire_count(layout):
    return 2 * _side_pairs(layout) + int(_has_top_wire(layout))


@contextmanager
def hold_updates():
    global UPDATING
    previous = UPDATING
    UPDATING = True
    try:
        yield
    finally:
        UPDATING = previous


def _collection(name, scene):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    root = bpy.data.collections.get(ROOT_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(ROOT_COLLECTION)
    if not any(c == root for c in scene.collection.children):
        scene.collection.children.link(root)
    if col != root and not any(c == col for c in root.children):
        root.children.link(col)
    return col


def _inputs(tree):
    return [item for item in tree.interface.items_tree
            if item.item_type == 'SOCKET' and item.in_out == 'INPUT']


def _socket(tree, name):
    return next((it for it in _inputs(tree) if it.name == name), None)


def _is_gn_rna_interface(mod):
    """Blender 5.2+: GN inputs are typed RNA, not modifier IDProperties.

    Blender 5.0 and 5.1 still use modifier[identifier]. Never attempt
    mapping-style access on a Blender 5.2 NodesModifier.
    """
    return bpy.app.version >= (5, 2, 0)


def _gn_input_property(mod, identifier):
    """Resolve a Blender 5.2 typed modifier input by interface identifier."""
    props = getattr(mod, 'properties', None)
    inputs = getattr(props, 'inputs', None)
    return getattr(inputs, identifier, None) if inputs is not None else None


def _set_group_input(mod, name, value):
    if mod is None or mod.node_group is None:
        return False
    it = _socket(mod.node_group, name)
    if it is None:
        print(f'[Powerline] GN input not found: {name!r}')
        return False
    try:
        if _is_gn_rna_interface(mod):
            entry = _gn_input_property(mod, it.identifier)
            if entry is None or not hasattr(entry, 'value'):
                raise AttributeError(f'No RNA value for GN input {name!r} ({it.identifier})')
            entry.value = value
        else:
            mod[it.identifier] = value
        return True
    except (TypeError, ValueError, KeyError, RuntimeError, AttributeError) as exc:
        print(f'[Powerline] Cannot set GN input {name!r}: {exc}')
        return False


def _get_group_input(mod, name, fallback=None):
    if mod is None or mod.node_group is None:
        return fallback
    it = _socket(mod.node_group, name)
    if it is None:
        return fallback
    default = getattr(it, 'default_value', fallback)
    try:
        if _is_gn_rna_interface(mod):
            entry = _gn_input_property(mod, it.identifier)
            return entry.value if entry is not None and hasattr(entry, 'value') else default
        return mod.get(it.identifier, default)
    except (TypeError, ValueError, KeyError, RuntimeError, AttributeError) as exc:
        print(f'[Powerline] Cannot read GN input {name!r}: {exc}')
        return default


def _source_fx(scene):
    obj = scene.pwl.fx_source
    if obj is None:
        return None
    return next((mod for mod in obj.modifiers
                 if mod.type == 'NODES' and mod.node_group
                 and mod.node_group.name.startswith('GN_CableElectricity_FX')), None)


def _copy_fx(src, dst):
    """Copy the source electricity preset, including material pointers.

    Blender 5.2+ NodesModifiers have *no* IDProperties. Copy named socket
    values from the dynamic RNA interface instead of calling src.keys().
    """
    if src is None or dst is None or src.node_group is None:
        return
    dst.node_group = src.node_group
    for interface_socket in _inputs(src.node_group):
        if interface_socket.socket_type == 'NodeSocketGeometry':
            continue
        identifier = interface_socket.identifier
        try:
            if _is_gn_rna_interface(src):
                source = _gn_input_property(src, identifier)
                target = _gn_input_property(dst, identifier)
                if source is None or target is None:
                    raise AttributeError(f'Missing FX input: {interface_socket.name}')
                # Preserve attribute-driven sockets where the source uses one.
                if getattr(source, 'type', None) == 'ATTRIBUTE':
                    target.type = 'ATTRIBUTE'
                    target.attribute_name = source.attribute_name
                elif hasattr(source, 'value') and hasattr(target, 'value'):
                    if getattr(target, 'type', None) == 'ATTRIBUTE':
                        target.type = 'VALUE'
                    target.value = source.value
                # Geometry and unsupported output-only sockets do not have a value.
            else:
                value = src.get(identifier, None)
                if value is not None:
                    dst[identifier] = value.to_list() if hasattr(value, 'to_list') else value
                for suffix in ('_use_attribute', '_attribute_name'):
                    key = identifier + suffix
                    if key in src:
                        dst[key] = src[key]
        except (ValueError, RuntimeError, TypeError, AttributeError, KeyError) as exc:
            print(f'[Powerline] FX input {interface_socket.name!r} not copied: {exc}')
            raise RuntimeError(
                f'Cannot copy electricity input {interface_socket.name!r}: {exc}'
            ) from exc


def _apply_seed_variation(scene, span, fx_modifier, base_modifier=None):
    """Recreate per-wire phase variation lost when splitting the original grid.

    The user-supplied source modifier always remains untouched. Every FX
    control other than the optional seed offset is copied verbatim.
    """
    if not fx_modifier:
        return
    if base_modifier is None:
        base_modifier=_source_fx(scene)
    if not base_modifier:
        return
    seed=_get_group_input(base_modifier,'Electric Seed',None)
    if not isinstance(seed,(int,float)) or isinstance(seed,bool):
        return
    # Center-top wire uses row 3 -> seed offset 6, distinct from the six sides.
    index=2*span.pwl.span_row + (1 if span.pwl.span_side=='R' else 0)
    new_seed=seed + index if scene.pwl.independent_pulses else seed
    if isinstance(seed,int):new_seed=int(new_seed)
    _set_group_input(fx_modifier,'Electric Seed',new_seed)


def _ensure_span_tree():
    existing = bpy.data.node_groups.get(CURVE_TREE_NAME)
    # The v0.2.1 builder could leave a partially constructed group behind
    # when Blender 5.2 raised on ResampleCurve.mode. Never reuse that group.
    if existing and existing.bl_idname == 'GeometryNodeTree':
        if existing.get('_pwl_span_tree_schema') == SPAN_TREE_SCHEMA:
            return existing
        ng = existing
        ng.nodes.clear()
        ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(CURVE_TREE_NAME, 'GeometryNodeTree')
    iface = ng.interface
    iface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    for name, kind, default, minimum, maximum in [
        ('Start Anchor', 'NodeSocketObject', None, None, None),
        ('End Anchor', 'NodeSocketObject', None, None, None),
        ('Sag Ratio', 'NodeSocketFloat', 0.065, 0.0, 0.4),
        ('Samples', 'NodeSocketInt', 128, 8, 512),
        ('Wind Amplitude', 'NodeSocketFloat', 0.0, 0.0, 5.0),
        ('Wind Frequency', 'NodeSocketFloat', 2.0, 0.0, 24.0),
        ('Wind Speed', 'NodeSocketFloat', 0.6, 0.0, 10.0),
    ]:
        sock = iface.new_socket(name=name, in_out='INPUT', socket_type=kind)
        if default is not None:
            sock.default_value = default
        if minimum is not None:
            sock.min_value = minimum
            sock.max_value = maximum
        if kind == 'NodeSocketObject':
            sock.description = 'Parented locator attached to a pylon arm'
    n = ng.nodes
    n.clear()
    l = ng.links

    def node(kind, label, xy):
        nd = n.new(kind)
        nd.label = label
        nd.location = xy
        return nd

    def m(op, label, xy, val=None):
        nd = node('ShaderNodeMath',label,xy)
        nd.operation = op
        if val is not None:
            nd.inputs[0].default_value = val
        return nd

    def vm(op, label, xy):
        nd = node('ShaderNodeVectorMath',label,xy)
        nd.operation = op
        return nd

    inp = node('NodeGroupInput','Per-span controls',(-1450,560))
    out = node('NodeGroupOutput','Curve goes into original electric FX',(1350,220))
    start = node('GeometryNodeObjectInfo','Start pylon socket',(-1200,560))
    end = node('GeometryNodeObjectInfo','End pylon socket',(-1200,280))
    start.transform_space = 'RELATIVE'
    end.transform_space = 'RELATIVE'
    l.new(inp.outputs['Start Anchor'],start.inputs['Object'])
    l.new(inp.outputs['End Anchor'],end.inputs['Object'])

    line = node('GeometryNodeCurvePrimitiveLine','Live endpoints',(-910,430))
    line.mode='POINTS'
    l.new(start.outputs['Location'],line.inputs['Start'])
    l.new(end.outputs['Location'],line.inputs['End'])
    # A generated line has exactly two points / one straight segment.
    # Cuts = Samples - 2 yields the requested number of evenly spaced points.
    # Blender 5.2 moved Resample Curve's Mode from a node property to an
    # input socket; Subdivide Curve avoids that version-sensitive API.
    samples_to_cuts=node('FunctionNodeIntegerMath','Samples minus endpoints',(-935,65))
    samples_to_cuts.operation = 'SUBTRACT'
    l.new(inp.outputs['Samples'], samples_to_cuts.inputs[0])
    samples_to_cuts.inputs[1].default_value = 2
    resample=node('GeometryNodeSubdivideCurve','Cable quality',(-690,430))
    l.new(line.outputs['Curve'],resample.inputs['Curve'])
    l.new(samples_to_cuts.outputs[0],resample.inputs['Cuts'])
    param=node('GeometryNodeSplineParameter','Along cable',(-860,-100))

    # 4*t*(1-t) is zero at endpoints and 1 at the midpoint.
    one_minus_t=m('SUBTRACT','1 - t',(-640,-240),1.0)
    l.new(param.outputs['Factor'],one_minus_t.inputs[1])
    arch=m('MULTIPLY','Parabola',(-450,-170))
    l.new(param.outputs['Factor'],arch.inputs[0])
    l.new(one_minus_t.outputs[0],arch.inputs[1])
    arch4=m('MULTIPLY','Normalize parabola',(-270,-150),4.0)
    l.new(arch.outputs[0],arch4.inputs[1])

    distance=vm('DISTANCE','Pylon separation',(-890,-520))
    l.new(start.outputs['Location'],distance.inputs[0])
    l.new(end.outputs['Location'],distance.inputs[1])
    drop=m('MULTIPLY','Sag ratio x separation',(-480,-480))
    l.new(distance.outputs['Value'],drop.inputs[0])
    l.new(inp.outputs['Sag Ratio'],drop.inputs[1])
    sag=m('MULTIPLY','Weighted sag',(-80,-450))
    l.new(drop.outputs[0],sag.inputs[0])
    l.new(arch4.outputs[0],sag.inputs[1])
    neg=m('MULTIPLY','Drop world Z',(110,-400),-1.0)
    l.new(sag.outputs[0],neg.inputs[1])
    sag_vec=node('ShaderNodeCombineXYZ','Gravity vector',(350,-400))
    l.new(neg.outputs[0],sag_vec.inputs['Z'])

    # Wind is perpendicular to horizontal span direction, and vanishes at the ends.
    delta=vm('SUBTRACT','Horizontal span direction',(-920,-820))
    l.new(end.outputs['Location'],delta.inputs[0])
    l.new(start.outputs['Location'],delta.inputs[1])
    separate=node('ShaderNodeSeparateXYZ','Horizontal components',(-700,-780))
    l.new(delta.outputs['Vector'],separate.inputs[0])
    invy=m('MULTIPLY','-dY',(-480,-780),-1.0)
    l.new(separate.outputs['Y'],invy.inputs[1])
    perp=node('ShaderNodeCombineXYZ','Perpendicular vector',(-260,-800))
    l.new(invy.outputs[0],perp.inputs['X'])
    l.new(separate.outputs['X'],perp.inputs['Y'])
    norm=vm('NORMALIZE','Wind across the wires',(-40,-760))
    l.new(perp.outputs[0],norm.inputs[0])
    cycles=m('MULTIPLY','Waves along wire',(-730,-1090))
    l.new(param.outputs['Factor'],cycles.inputs[0])
    l.new(inp.outputs['Wind Frequency'],cycles.inputs[1])
    seconds=node('GeometryNodeInputSceneTime','Playback time',(-770,-1300))
    phase=m('MULTIPLY','Wind speed',(-510,-1240))
    l.new(seconds.outputs['Seconds'],phase.inputs[0])
    l.new(inp.outputs['Wind Speed'],phase.inputs[1])
    phase_sum=m('ADD','Traveling wave',(-280,-1150))
    l.new(cycles.outputs[0],phase_sum.inputs[0])
    l.new(phase.outputs[0],phase_sum.inputs[1])
    tau=m('MULTIPLY','Cycles into radians',(-70,-1140),math.tau)
    l.new(phase_sum.outputs[0],tau.inputs[1])
    sinus=m('SINE','Oscillate',(130,-1150))
    l.new(tau.outputs[0],sinus.inputs[0])
    amp=m('MULTIPLY','Wind amplitude',(330,-1040))
    l.new(sinus.outputs[0],amp.inputs[0])
    l.new(inp.outputs['Wind Amplitude'],amp.inputs[1])
    fade=m('MULTIPLY','Pin wind at attachments',(550,-920))
    l.new(arch4.outputs[0],fade.inputs[0])
    l.new(amp.outputs[0],fade.inputs[1])
    wind=vm('SCALE','Wind offset',(750,-730))
    l.new(norm.outputs['Vector'],wind.inputs[0])
    l.new(fade.outputs[0],wind.inputs['Scale'])
    combined=vm('ADD','Sag + wind',(900,-300))
    l.new(sag_vec.outputs[0],combined.inputs[0])
    l.new(wind.outputs['Vector'],combined.inputs[1])
    setpos=node('GeometryNodeSetPosition','Procedural deformation',(1090,250))
    l.new(resample.outputs['Curve'],setpos.inputs['Geometry'])
    l.new(combined.outputs['Vector'],setpos.inputs['Offset'])
    l.new(setpos.outputs['Geometry'],out.inputs['Geometry'])
    ng['_pwl_span_tree_schema'] = SPAN_TREE_SCHEMA
    return ng



def _create_modded_curve(obj,scene,start_anchor,end_anchor):
    ng=_ensure_span_tree()
    gen=obj.modifiers.new('PWL | Live Cable Curve','NODES')
    gen.node_group=ng
    values={
        'Start Anchor':start_anchor,
        'End Anchor':end_anchor,
        'Sag Ratio':scene.pwl.sag_ratio,
        'Samples':scene.pwl.samples,
        'Wind Amplitude':scene.pwl.wind_amplitude,
        'Wind Frequency':scene.pwl.wind_frequency,
        'Wind Speed':scene.pwl.wind_speed,
    }
    for n,v in values.items():
        if not _set_group_input(gen,n,v):
            raise RuntimeError(f'Geometry Nodes input not set: {n}')
    src_fx = _source_fx(scene)
    if src_fx:
        fx=obj.modifiers.new('PWL | Original Electricity FX','NODES')
        _copy_fx(src_fx,fx)
        _set_group_input(fx,'Electric Enabled',scene.pwl.electric_enabled)
        _apply_seed_variation(scene,obj,fx,src_fx)
    else:
        # In a non-demo file, give the span visible geometry even without FX.
        basic=_ensure_basic_surface_tree()
        surf=obj.modifiers.new('PWL | Cable Surface','NODES')
        surf.node_group=basic
    obj.update_tag()


def _ensure_basic_surface_tree():
    ng=bpy.data.node_groups.get('PWL | Fallback Cable Surface')
    if ng:return ng
    ng=bpy.data.node_groups.new('PWL | Fallback Cable Surface','GeometryNodeTree')
    ng.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    ng.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    ni=ng.nodes.new('NodeGroupInput');ni.location=(-560,150)
    circle=ng.nodes.new('GeometryNodeCurvePrimitiveCircle');circle.location=(-330,-40)
    circle.mode='RADIUS'
    circle.inputs['Radius'].default_value=0.02
    circle.inputs['Resolution'].default_value=8
    mesh=ng.nodes.new('GeometryNodeCurveToMesh');mesh.location=(-80,100)
    no=ng.nodes.new('NodeGroupOutput');no.location=(190,100)
    ng.links.new(ni.outputs['Geometry'],mesh.inputs['Curve'])
    ng.links.new(circle.outputs['Curve'],mesh.inputs['Profile Curve'])
    ng.links.new(mesh.outputs['Mesh'],no.inputs['Geometry'])
    return ng



# ---------------------------------------------------------------
# Source library. Appends only 1 pylon source and 1 unlinked FX reference.
# The original scene layout is NEVER brought into the current scene.
# ---------------------------------------------------------------

def _is_live_pointer(obj):
    try:
        return obj is not None and obj.name in bpy.data.objects
    except ReferenceError:
        return False


def _ensure_source(scene):
    """Load source IDs once, not the source scene's objects or placement.

    Both objects are deliberately left without a collection. A fake user
    preserves them on save/reload. They never appear in the viewport/Outliner.
    """
    st = scene.pwl
    if (_is_live_pointer(st.pylon_template) and _is_live_pointer(st.fx_source)
            and st.source_mesh is not None):
        return st.pylon_template
    asset = os.path.join(os.path.dirname(__file__), 'assets', DEMO_FILENAME)
    if not os.path.isfile(asset):
        raise RuntimeError('Bundled pylon reference is missing from the addon.')
    with bpy.data.libraries.load(asset, link=False) as (src, dst):
        for name in ('pylon', 'cables'):
            if name not in src.objects:
                raise RuntimeError('Bundled source is missing object: ' + name)
        # Import the source datablocks, not the old pylon_distant object or scene.
        dst.objects = ['pylon', 'cables']
    pylon = next((obj for obj in dst.objects if obj and obj.name.startswith('pylon')), None)
    fx = next((obj for obj in dst.objects if obj and obj.name.startswith('cables')), None)
    if pylon is None or fx is None:
        raise RuntimeError('Cannot load pylon/FX references from packaged source.')
    if pylon.type != 'MESH':
        raise RuntimeError('Bundled pylon is not an edge mesh.')
    # The source FX may carry a parent pointer to the internal pylon. That is
    # harmless: both objects remain unlinked and are never rendered.
    for ob in (pylon, fx):
        ob.use_fake_user = True
        ob['_pwl_internal_template'] = True
    source = pylon.data
    source.use_fake_user = True
    source['_pwl_source_edges'] = True
    source.name = SOURCE_MESH_NAME
    with hold_updates():
        st.pylon_template = pylon
        st.fx_source = fx
        st.source_mesh = source
        # The boolean follows the actual source modifier default. The other
        # electricity values are copied from the original modifier verbatim.
        preset = _source_fx(scene)
        if preset is not None:
            st.electric_enabled = bool(_get_group_input(preset, 'Electric Enabled', True))
    return pylon


def _mesh_geometry(mesh):
    return [tuple(v.co) for v in mesh.vertices], [tuple(e.vertices) for e in mesh.edges]


def _source_data_for(obj):
    return bpy.data.meshes.get(obj.pwl.source_mesh_name) if obj.pwl.source_mesh_name else None


def _variant_key(source, settings):
    """Exact default variants share the same mesh, like Alt+D linked copies.

    Non-default variants are automatically copy-on-write without changing
    another pylon's geometry. Quantization avoids float-display jitter.
    """
    attrs = (
        source.name,
        _side_pairs(settings.pairs),
        round(settings.arm_reach, 5),
        round(settings.arm_spacing, 5),
        round(settings.arm_height, 5),
        round(settings.insulator_drop, 5),
    )
    return hashlib.sha1(repr(attrs).encode('utf-8')).hexdigest()[:16]


def _variant_mesh(src, settings):
    key = _variant_key(src, settings)
    name = f'PWL | Pylon Edges | {key}'
    existing = bpy.data.meshes.get(name)
    if existing is not None and existing.get('_pwl_key') == key:
        return existing, calibrate(_mesh_geometry(src)[0])
    verts, edges = _mesh_geometry(src)
    calibration = calibrate(verts)
    coords, links, _ = make_pylon(
        verts, edges, calibration,
        pairs=_side_pairs(settings.pairs), reach=settings.arm_reach,
        spacing=settings.arm_spacing, center=settings.arm_height,
        drop=settings.insulator_drop,
    )
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, links, [])
    mesh.update()
    for material in src.materials:
        if material is not None:
            mesh.materials.append(material)
    mesh['_pwl_generated'] = True
    mesh['_pwl_key'] = key
    return mesh, calibration


def _ensure_anchor(obj, key, scene):
    for child in obj.children:
        if child.get('pwl_anchor') == key:
            return child
    col = _collection(ANCHOR_COLLECTION, scene)
    anchor = bpy.data.objects.new(f'{obj.name} | {key}', None)
    col.objects.link(anchor)
    anchor.empty_display_type = 'SPHERE'
    anchor.empty_display_size = 0.13
    anchor.hide_render = True
    anchor.parent = obj
    anchor.matrix_parent_inverse = Matrix.Identity(4)
    anchor['pwl_anchor'] = key
    anchor['pwl_owner_uid'] = obj.pwl.uid
    try:
        anchor.hide_set(not scene.pwl.show_sockets)
    except RuntimeError:
        pass
    return anchor


def _anchors_of(obj):
    return {ch.get('pwl_anchor'): ch for ch in obj.children if ch.get('pwl_anchor')}


def _rebuild_pylon(obj, scene):
    src = _source_data_for(obj)
    if src is None:
        raise RuntimeError('Pylon source geometry no longer exists.')
    new_mesh, c = _variant_mesh(src, obj.pwl)
    count = _side_pairs(obj.pwl.pairs)
    # All arm layouts use the supplied edge-based tower. Mode 7 is identical
    # to mode 6 except for a seventh anchor on the existing tower apex.
    levels = arm_levels(count, obj.pwl.arm_height, obj.pwl.arm_spacing)
    tip_x = c.core_x + obj.pwl.arm_reach
    coordinates = {
        f'{side}{j}': (factor * tip_x, y - obj.pwl.insulator_drop, 0)
        for j, y in enumerate(levels)
        for side, factor in (('L', -1), ('R', 1))
    }
    if _has_top_wire(obj.pwl.pairs):
        coordinates['TOP'] = pylon_apex(_mesh_geometry(src)[0])
    # All matching pylons reuse this exact edge mesh. Their object transforms,
    # parented sockets and GN evaluations remain separate.
    old = obj.data
    obj.data = new_mesh
    for key, co in coordinates.items():
        socket = _ensure_anchor(obj, key, scene)
        socket.location = co
        socket.name = f'{obj.name} | {key}'
        socket['pwl_owner_uid'] = obj.pwl.uid
    for key, child in _anchors_of(obj).items():
        if key not in coordinates:
            bpy.data.objects.remove(child, do_unlink=True)
    if old and old != src and old.users == 0 and old.get('_pwl_generated'):
        bpy.data.meshes.remove(old)


def _needs_pylon_rebuild(obj):
    """Detect both stale 8-arm v0.2.4 meshes and missing top attachments.

    v0.2.4 stored the same enum value '4' for eight wires. Preserve that
    serialized value, but reinterpret it as 7 and migrate on the next 7
    button press, Add Pylon, or Match All Pylons action.
    """
    src = _source_data_for(obj)
    if src is None or obj.data is None:
        return True
    if obj.data.get('_pwl_key') != _variant_key(src, obj.pwl):
        return True
    expected = {f'{side}{i}' for i in range(_side_pairs(obj.pwl.pairs))
                for side in ('L', 'R')}
    if _has_top_wire(obj.pwl.pairs):
        expected.add('TOP')
    return set(_anchors_of(obj)) != expected


def _make_pylon(scene, template, location, clone_from=None):
    """Create an Object.copy with LINKED mesh; no data.copy() here."""
    parent = clone_from or template
    result = parent.copy()
    result.name = 'PWL | Pylon'
    # Object.copy does not copy child locator objects. Build private sockets.
    _collection(PYLON_COLLECTION, scene).objects.link(result)
    result.parent = None
    result.matrix_parent_inverse = Matrix.Identity(4)
    result.rotation_mode = 'XYZ'
    result.location = location
    result.scale = parent.scale.copy() if clone_from else Vector((1, 1, 1))
    result.rotation_euler = parent.rotation_euler.copy()
    result.hide_render = False
    result.hide_set(False)
    with hold_updates():
        prop = result.pwl
        prop.is_pylon = True
        prop.is_span = False
        prop.uid = uuid.uuid4().hex[:12]
        prop.source_mesh_name = scene.pwl.source_mesh.name
        if clone_from is None:
            vs, _ = _mesh_geometry(scene.pwl.source_mesh)
            c = calibrate(vs)
            prop.pairs = scene.pwl.initial_pairs
            prop.arm_reach = c.reach
            prop.arm_height = c.middle_tier
            prop.arm_spacing = c.spacing
            prop.insulator_drop = c.tip_drop
        # When a pylon is copied from an existing pylon the whole settings
        # PropertyGroup is already copied and its geometry key will match.
        _rebuild_pylon(result, scene)
        result['pwl_previous_pairs'] = int(prop.pairs)
    return result


def _pylons(scene):
    return sorted((obj for obj in scene.objects if obj.pwl.is_pylon),
                  key=lambda ob: (ob.pwl.route_index, ob.name))


def _spans(scene):
    return [obj for obj in scene.objects if obj.pwl.is_span]


def _next_index(scene):
    return max((ob.pwl.route_index for ob in _pylons(scene)), default=-1) + 1


def _line_direction(rotating_pylon):
    """Transport follows the direction perpendicular to the pylon's arms."""
    direction = rotating_pylon.matrix_world.to_3x3() @ Vector((1, 0, 0))
    direction.z = 0
    if direction.length < 0.00001:
        return Vector((0, 1, 0))
    direction.normalize()
    return Vector((-direction.y, direction.x, 0))


def _extension_position(scene, last):
    if scene.pwl.add_at_cursor:
        return scene.cursor.location.copy()
    ordered = _pylons(scene)
    if len(ordered) > 1:
        prior = ordered[-2]
        delta = last.location - prior.location
        delta.z = 0
        if delta.length > 0.001:
            delta.normalize()
            return last.location + delta * scene.pwl.span_length
    return last.location + _line_direction(last) * scene.pwl.span_length


def _select_only(context, obj):
    for old in context.selected_objects:
        old.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _node_mod(obj, prefix):
    return next((m for m in obj.modifiers
                 if m.type == 'NODES' and m.node_group
                 and m.node_group.name.startswith(prefix)), None)


def _make_span(scene, a, b, start, end, side, idx):
    input_mesh = bpy.data.meshes.new('PWL | Input - GN generates cable')
    obj = bpy.data.objects.new('PWL | Cable', input_mesh)
    _collection(SPAN_COLLECTION, scene).objects.link(obj)
    try:
        with hold_updates():
            obj.pwl.is_span = True
            obj.pwl.start_pylon = a
            obj.pwl.end_pylon = b
            obj.pwl.span_side = side
            obj.pwl.span_row = idx
            _create_modded_curve(obj, scene, start, end)
    except Exception:
        bpy.data.objects.remove(obj, do_unlink=True)
        if input_mesh.users == 0:
            bpy.data.meshes.remove(input_mesh)
        raise
    conductor = 'TOP' if side == 'TOP' else f'{side}{idx+1}'
    obj.name = f'PWL | {a.pwl.route_index+1}-{b.pwl.route_index+1} | {conductor}'
    obj.display_type = 'TEXTURED'
    return obj


def _pair_key(a, b):
    return frozenset((a.as_pointer(), b.as_pointer()))


def _connect(scene, a, b):
    if a == b or not (a and b and a.pwl.is_pylon and b.pwl.is_pylon):
        raise ValueError('Two different rigged pylons are needed.')
    old = [obj for obj in _spans(scene)
           if obj.pwl.start_pylon and obj.pwl.end_pylon
           and _pair_key(obj.pwl.start_pylon, obj.pwl.end_pylon) == _pair_key(a, b)]
    # Prepare replacements before deleting working spans. If Blender rejects
    # a node/socket assignment, leave the previous connection intact.
    aa, bb = _anchors_of(a), _anchors_of(b)
    count = min(_side_pairs(a.pwl.pairs), _side_pairs(b.pwl.pairs))

    def row_match(source_count, wanted):
        if source_count == wanted:
            return list(range(source_count))
        if wanted == 1:
            return [(source_count - 1) // 2]
        return [round(i * (source_count - 1) / (wanted - 1)) for i in range(wanted)]

    made = []
    try:
        for i, (row_a, row_b) in enumerate(zip(
                row_match(_side_pairs(a.pwl.pairs), count),
                row_match(_side_pairs(b.pwl.pairs), count))):
            for side in ('L', 'R'):
                begin = aa.get(f'{side}{row_a}')
                finish = bb.get(f'{side}{row_b}')
                if begin is None or finish is None:
                    raise RuntimeError('Missing a pylon attachment point; rebuild network.')
                made.append(_make_span(scene, a, b, begin, finish, side, i))
        # Seventh conductor: one cable along the actual apex of both towers.
        # Do not create a fourth arm tier. Mixed 6/7 routes stay connected
        # by their common side pairs until the global layout is synchronized.
        if _has_top_wire(a.pwl.pairs) and _has_top_wire(b.pwl.pairs):
            if 'TOP' not in aa or 'TOP' not in bb:
                raise RuntimeError('Missing top attachment; rebuild network.')
            made.append(_make_span(scene, a, b, aa['TOP'], bb['TOP'], 'TOP', 3))
    except Exception:
        for obj in made:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        raise
    for obj in old:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    return len(made)


def _spanned_pairs(scene):
    visited = set()
    for obj in _spans(scene):
        a = obj.pwl.start_pylon
        b = obj.pwl.end_pylon
        if a and b and a.pwl.is_pylon and b.pwl.is_pylon:
            key = _pair_key(a, b)
            if key not in visited:
                visited.add(key)
                yield a, b


def _sync_pylon_connections(scene, changed):
    for a, b in list(_spanned_pairs(scene)):
        if changed in (a, b):
            _connect(scene, a, b)


def _sync_global_arms(scene):
    """Apply one arm layout to EVERY rigged pylon, then refresh all spans.

    Keep per-pylon arm dimensions for art direction. Only the pair count is
    global: a 2/4/6/7 choice updates existing pylons as well as future ones.
    Reconnect once per span *after* every support has its new anchors, so no
    intermediate mixed-arm wiring is created.
    """
    pylons = _pylons(scene)
    target = str(scene.pwl.initial_pairs)
    changed = [p for p in pylons if p.pwl.pairs != target or _needs_pylon_rebuild(p)]
    if not changed:
        return 0, 0
    old_pairs = {p: str(p.pwl.pairs) for p in changed}
    connections = list(_spanned_pairs(scene))
    try:
        with hold_updates():
            for pylon in changed:
                pylon.pwl.pairs = target
                _rebuild_pylon(pylon, scene)
                pylon['pwl_previous_pairs'] = int(target)
            for a, b in connections:
                _connect(scene, a, b)
    except Exception:
        # Restore the earlier configurations if an update fails. Existing
        # spans are not deleted until their replacements were created.
        with hold_updates():
            for pylon, previous in old_pairs.items():
                if not _is_live_pointer(pylon):
                    continue
                try:
                    pylon.pwl.pairs = previous
                    _rebuild_pylon(pylon, scene)
                    pylon['pwl_previous_pairs'] = int(previous)
                except Exception:
                    traceback.print_exc()
            for a, b in connections:
                try:
                    _connect(scene, a, b)
                except Exception:
                    traceback.print_exc()
        raise
    return len(changed), len(connections)


def _global_arms_changed(props, context):
    """Changing the network arm configuration updates the entire route."""
    if UPDATING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene is None:
        return
    try:
        _sync_global_arms(scene)
    except Exception:
        print('[Powerline System] Global arm update failed; original layout restored.')
        traceback.print_exc()


def _sync_all_network_values(scene):
    settings = scene.pwl
    fx_source = _source_fx(scene)
    for obj in _spans(scene):
        node = _node_mod(obj, CURVE_TREE_NAME)
        if node is not None:
            for name, val in (
                ('Sag Ratio', settings.sag_ratio),
                ('Samples', settings.samples),
                ('Wind Amplitude', settings.wind_amplitude),
                ('Wind Frequency', settings.wind_frequency),
                ('Wind Speed', settings.wind_speed),
            ):
                _set_group_input(node, name, val)
        fx = _node_mod(obj, 'GN_CableElectricity_FX')
        if fx is not None:
            _set_group_input(fx, 'Electric Enabled', settings.electric_enabled)
            _apply_seed_variation(scene, obj, fx, fx_source)
        obj.update_tag()


def _delete_network(scene):
    for obj in list(scene.objects):
        if obj.pwl.is_span or obj.pwl.is_pylon or obj.get('pwl_anchor'):
            mesh = obj.data if obj.type == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0 and mesh.get('_pwl_generated'):
                bpy.data.meshes.remove(mesh)
    # The hidden source IDs intentionally survive so the user can create
    # another route without relinking external assets.


def _pylon_changed(props, context):
    if UPDATING:
        return
    obj = props.id_data
    if not isinstance(obj, bpy.types.Object) or not props.is_pylon:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    try:
        with hold_updates():
            was = int(obj.get('pwl_previous_pairs', int(props.pairs)))
            _rebuild_pylon(obj, scene)
            if was != int(props.pairs):
                _sync_pylon_connections(scene, obj)
            obj['pwl_previous_pairs'] = int(props.pairs)
    except Exception as ex:
        print('[Powerline System] Pylon rebuild failed:', ex)


def _network_changed(props, context):
    if UPDATING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    with hold_updates():
        _sync_all_network_values(scene)


def _socket_vis_changed(props, context):
    if UPDATING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    for obj in scene.objects:
        if obj.get('pwl_anchor'):
            try:
                obj.hide_set(not props.show_sockets)
            except RuntimeError:
                pass

# ---------------------------------------------------------------
# Scene and object properties
# ---------------------------------------------------------------

class PWL_PylonSettings(bpy.types.PropertyGroup):
    is_pylon: BoolProperty(default=False)
    is_span: BoolProperty(default=False)
    uid: StringProperty(default='')
    source_mesh_name: StringProperty(default='')
    route_index: IntProperty(name='Route position', default=-1, min=-1)
    pairs: EnumProperty(
        name='Arm pairs',
        description='Choose 2, 4, 6, or 7 wires (7 = six side wires + one at the apex)',
        items=[('1', '2', 'One pair of arms'),
               ('2', '4', 'Two pairs of arms'),
               ('3', '6', 'Three pairs of arms'),
               ('4', '7', 'Three arm pairs plus one centered top wire')],
        default='3', update=_pylon_changed)
    arm_reach: FloatProperty(name='Arm Length', subtype='DISTANCE',
                             min=0.1, max=12, default=0.96, precision=3,
                             update=_pylon_changed)
    arm_spacing: FloatProperty(name='Arm Gap', subtype='DISTANCE',
                               min=0.1, max=20, default=1.69,
                               precision=3, update=_pylon_changed)
    arm_height: FloatProperty(name='Arm Height', subtype='DISTANCE',
                              min=1, max=200, default=14.16,
                              precision=3, update=_pylon_changed)
    insulator_drop: FloatProperty(name='Cable Offset', subtype='DISTANCE',
                                  min=0, max=5, default=0.48,
                                  precision=3, update=_pylon_changed)
    start_pylon: PointerProperty(type=bpy.types.Object)
    end_pylon: PointerProperty(type=bpy.types.Object)
    span_side: StringProperty(default='')
    span_row: IntProperty(default=0)


class PWL_SceneSettings(bpy.types.PropertyGroup):
    pylon_template: PointerProperty(name='Internal pylon template', type=bpy.types.Object)
    source_mesh: PointerProperty(name='Internal original source mesh', type=bpy.types.Mesh)
    fx_source: PointerProperty(name='Original electricity preset', type=bpy.types.Object)
    initial_pairs: EnumProperty(
        name='Conductors', description='Use 2, 4, 6 or 7 conductors on every pylon; 7 adds one wire at the tower apex',
        items=[('1', '2', 'One arm pair across the whole line'),
               ('2', '4', 'Two arm pairs across the whole line'),
               ('3', '6', 'Three arm pairs across the whole line'),
               ('4', '7', 'Three arm pairs plus one centered top conductor')],
        default='3', update=_global_arms_changed)
    span_length: FloatProperty(
        name='Pylon Spacing', subtype='DISTANCE', description='Default distance to the next pylon',
        default=30, min=1, max=1000, precision=1)
    add_at_cursor: BoolProperty(
        name='Use 3D Cursor', default=False,
        description='Place the next pylon at the 3D cursor instead of extending the current route')
    sag_ratio: FloatProperty(
        name='Sag', description='Maximum sag / pylon spacing', subtype='PERCENTAGE',
        min=0, max=0.4, default=0.065, precision=1, update=_network_changed)
    samples: IntProperty(name='Cable Quality', min=8, max=512,
                         default=128, update=_network_changed)
    wind_amplitude: FloatProperty(
        name='Wind', subtype='DISTANCE',
        description='Maximum sideways displacement in metres; pinned at both endpoints',
        min=0, max=5, default=0, precision=2, update=_network_changed)
    wind_frequency: FloatProperty(name='Wind Waves', min=0, max=24,
                                  default=2, update=_network_changed)
    wind_speed: FloatProperty(name='Wind Speed', min=0, max=10,
                              default=0.6, update=_network_changed)
    electric_enabled: BoolProperty(
        name='Electricity', default=True,
        description='Retain the original electricity effect using the source preset',
        update=_network_changed)
    independent_pulses: BoolProperty(
        name='Vary Pulse Seeds', default=False,
        description='Modify the original electricity seed for each cable to offset pulse timing',
        update=_network_changed)
    show_sockets: BoolProperty(
        name='Show Attachment Points', default=False, update=_socket_vis_changed)
    show_selected_pylon: BoolProperty(name='Selected Pylon Controls', default=False)
    advanced: BoolProperty(name='Advanced', default=False)
    fx_advanced: BoolProperty(name='Electricity Preset', default=False)


# ---------------------------------------------------------------
# Three-step network UX: Create -> Move -> Add
# ---------------------------------------------------------------

class PWL_OT_select_arm_count(bpy.types.Operator):
    bl_idname = 'pwl.select_arm_count'
    bl_label = 'Set Wire Layout'
    bl_description = 'Set conductors on every pylon (7 = 6 side wires plus 1 centered at the apex)'
    bl_options = {'REGISTER', 'UNDO'}

    pairs: IntProperty(name='Layout preset', min=1, max=4, options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        new_value = str(self.pairs)
        old_value = scene.pwl.initial_pairs
        try:
            # Avoid double synchronization: the property has its own update
            # callback for scripts, while the button controls the UI transaction.
            with hold_updates():
                scene.pwl.initial_pairs = new_value
            changed, connections = _sync_global_arms(scene)
        except Exception as exc:
            with hold_updates():
                scene.pwl.initial_pairs = old_value
            traceback.print_exc()
            self.report({'ERROR'}, f'Could not set {_wire_count(self.pairs)} conductors: {type(exc).__name__}: {exc}')
            return {'CANCELLED'}
        if changed:
            self.report({'INFO'}, f'{_wire_count(self.pairs)} conductors applied to {changed} pylons; updated {connections} sections.')
        return {'FINISHED'}


def _draw_arm_count_buttons(layout, settings):
    """Stable, compact, explicitly labelled 2 | 4 | 6 | 7 selector."""
    row = layout.row(align=True)
    for pairs in (1, 2, 3, 4):
        button = row.operator(
            'pwl.select_arm_count', text=str(_wire_count(pairs)),
            depress=(settings.initial_pairs == str(pairs)),
        )
        button.pairs = pairs



class PWL_OT_create_line(bpy.types.Operator):
    bl_idname = 'pwl.create_line'
    bl_label = 'Create Line'
    bl_description = 'Create 2 matching, linked-geometry pylons with live electricity cables'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        if _pylons(scene):
            self.report({'WARNING'}, 'A Powerline route already exists. Use Add Pylon to extend it.')
            return {'CANCELLED'}
        try:
            template = _ensure_source(scene)
            with hold_updates():
                first = _make_pylon(scene, template, scene.cursor.location.copy())
                first.pwl.route_index = 0
                context.view_layer.update()
                second_position = first.location + _line_direction(first) * scene.pwl.span_length
                second = _make_pylon(scene, template, second_position, clone_from=first)
                second.pwl.route_index = 1
                num_cables = _connect(scene, first, second)
                _select_only(context, second)
            self.report({'INFO'},
                        f'Line created: 2 linked-mesh pylons, {num_cables} live cables. Move either pylon with G.')
            return {'FINISHED'}
        except Exception as error:
            # Print a complete stack trace for the next runtime diagnostic.
            traceback.print_exc()
            # Failure should never leave one partial pylon and broken spans.
            with hold_updates():
                _delete_network(scene)
            self.report({'ERROR'}, f'Could not create powerline: {type(error).__name__}: {error}')
            return {'CANCELLED'}


class PWL_OT_add_pylon(bpy.types.Operator):
    bl_idname = 'pwl.add_pylon'
    bl_label = 'Add Pylon'
    bl_description = 'Extend the last section automatically, linking the new cables to the previous pylon'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        ordered = _pylons(scene)
        if not ordered:
            self.report({'ERROR'}, 'Click Create Line first.')
            return {'CANCELLED'}
        result = None
        try:
            # Also normalize routes saved from pre-0.2.3 versions where arm
            # counts could be overridden independently per pylon.
            _sync_global_arms(scene)
            ordered = _pylons(scene)
            last = ordered[-1]
            pos = _extension_position(scene, last)
            with hold_updates():
                result = _make_pylon(scene, scene.pwl.pylon_template, pos, clone_from=last)
                result.pwl.route_index = _next_index(scene)
                num = _connect(scene, last, result)
                _select_only(context, result)
            self.report({'INFO'},
                        f'Added pylon {result.pwl.route_index+1}, connected {num} new cables. Move it with G.')
            return {'FINISHED'}
        except Exception as error:
            # Roll back only the newly created pylon; earlier route stays live.
            if result and _is_live_pointer(result):
                with hold_updates():
                    for span in list(_spans(scene)):
                        if span.pwl.start_pylon == result or span.pwl.end_pylon == result:
                            data = span.data
                            bpy.data.objects.remove(span, do_unlink=True)
                            if data and data.users == 0:
                                bpy.data.meshes.remove(data)
                    for child in list(result.children):
                        if child.get('pwl_anchor'):
                            bpy.data.objects.remove(child, do_unlink=True)
                    mesh = result.data
                    bpy.data.objects.remove(result, do_unlink=True)
                    if mesh and mesh.users == 0 and mesh.get('_pwl_generated'):
                        bpy.data.meshes.remove(mesh)
            traceback.print_exc()
            self.report({'ERROR'}, f'Could not extend line: {type(error).__name__}: {error}')
            return {'CANCELLED'}


class PWL_OT_rebuild_route(bpy.types.Operator):
    bl_idname = 'pwl.rebuild_route'
    bl_label = 'Rebuild Cable Connections'
    bl_description = 'Recreate every cable in route order (use if pylons have been deleted or manually modified)'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        pylons = _pylons(scene)
        if len(pylons) < 2:
            self.report({'ERROR'}, 'Need at least two rigged pylons.')
            return {'CANCELLED'}
        try:
            with hold_updates():
                # Remove only generated cable objects, leave actual pylons intact.
                for span in _spans(scene):
                    mesh = span.data
                    bpy.data.objects.remove(span, do_unlink=True)
                    if mesh and mesh.users == 0:
                        bpy.data.meshes.remove(mesh)
                for idx, ob in enumerate(pylons):
                    ob.pwl.route_index = idx
                    # Rebuild normalizes any legacy mixed-arm line as well.
                    ob.pwl.pairs = scene.pwl.initial_pairs
                    if _source_data_for(ob):
                        _rebuild_pylon(ob, scene)
                    ob['pwl_previous_pairs'] = int(ob.pwl.pairs)
                count = sum(_connect(scene, a, b)
                            for a, b in zip(pylons, pylons[1:]))
            self.report({'INFO'}, f'Rebuilt {len(pylons)-1} sections with {count} cables.')
            return {'FINISHED'}
        except Exception as error:
            traceback.print_exc()
            self.report({'ERROR'}, f'Route rebuild failed: {type(error).__name__}: {error}')
            return {'CANCELLED'}


class PWL_OT_sync_arm_layout(bpy.types.Operator):
    bl_idname = 'pwl.sync_arm_layout'
    bl_label = 'Match All Pylons'
    bl_description = 'Set every pylon to the network arm layout, including older mixed configurations'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            changed, connections = _sync_global_arms(context.scene)
        except Exception as error:
            traceback.print_exc()
            self.report({'ERROR'}, f'Could not synchronize arms: {error}')
            return {'CANCELLED'}
        if not changed:
            self.report({'INFO'}, 'All pylons already match.')
        else:
            self.report({'INFO'},
                        f'Synchronized {changed} pylons; refreshed {connections} cable sections.')
        return {'FINISHED'}


class PWL_OT_restore(bpy.types.Operator):
    bl_idname = 'pwl.clear_network'
    bl_label = 'Delete Powerline Network'
    bl_description = 'Delete generated pylons, attachment points and cables; leave existing scene objects untouched'
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        with hold_updates():
            _delete_network(context.scene)
        self.report({'INFO'}, 'Generated route removed; reference source retained for future use.')
        return {'FINISHED'}


class PWL_OT_apply_fx(bpy.types.Operator):
    bl_idname = 'pwl.apply_fx'
    bl_label = 'Update Electricity Across Line'
    bl_description = 'Copy the original electricity FX values to all generated cable spans'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        src = _source_fx(scene)
        if src is None:
            self.report({'ERROR'}, 'Missing original electricity reference.')
            return {'CANCELLED'}
        count = 0
        for span in _spans(scene):
            dst = _node_mod(span, 'GN_CableElectricity_FX')
            if dst is None:
                continue
            _copy_fx(src, dst)
            _set_group_input(dst, 'Electric Enabled', scene.pwl.electric_enabled)
            _apply_seed_variation(scene, span, dst, src)
            span.update_tag()
            count += 1
        self.report({'INFO'}, f'Updated electricity preset on {count} cables.')
        return {'FINISHED'}


class PWL_PT_main(bpy.types.Panel):
    bl_label = 'Powerline System'
    bl_idname = 'PWL_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Powerlines'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        st = scene.pwl
        pylons = _pylons(scene)
        spans = _spans(scene)
        active = context.object

        if not pylons:
            col = layout.column(align=True)
            col.label(text='NEW POWERLINE', icon='OUTLINER_OB_MESH')
            col.label(text='WIRES · ALL PYLONS')
            _draw_arm_count_buttons(col, st)
            col.prop(st, 'span_length', text='Spacing')
            col.operator('pwl.create_line', text='Create Line (2 Pylons)', icon='ADD')
            layout.separator(factor=0.6)
            layout.label(text='2 matching pylons + live cables', icon='INFO')
            layout.label(text='Move either pylon with G')
            return

        layout.label(text=f'{len(pylons)} pylons   /   {max(0, len(pylons)-1)} sections   /   {len(spans)} cables',
                     icon='MOD_CURVE')
        col = layout.column(align=True)
        col.operator('pwl.add_pylon', text='Add Pylon + Connect', icon='ADD')
        col.label(text='Move any pylon with G')

        layout.separator(factor=0.5)
        col = layout.column(align=True)
        col.label(text='WIRES · ALL PYLONS')
        _draw_arm_count_buttons(col, st)
        # Include old v0.2.4 scenes whose saved '4' choice still uses a
        # four-pair mesh. Pressing 7 or this button upgrades them in place.
        if any(p.pwl.pairs != st.initial_pairs or _needs_pylon_rebuild(p) for p in pylons):
            col.operator('pwl.sync_arm_layout', text='Update All Pylons', icon='FILE_REFRESH')

        if active and active.pwl.is_pylon:
            box = layout.box()
            box.prop(st, 'show_selected_pylon',
                     text=f'Pylon {active.pwl.route_index + 1:02d} · Shape',
                     icon='TRIA_DOWN' if st.show_selected_pylon else 'TRIA_RIGHT',
                     emboss=False)
            if st.show_selected_pylon:
                box.prop(active.pwl, 'arm_reach', slider=True)
                row = box.row(align=True)
                row.prop(active.pwl, 'arm_height', text='Height')
                row.prop(active.pwl, 'arm_spacing', text='Gap')
                box.prop(active.pwl, 'insulator_drop')
                box.label(text=f'Shared edge mesh: {active.data.users} pylons', icon='LINKED')

        layout.separator(factor=0.5)
        col = layout.column(align=True)
        col.label(text='CABLES', icon='CURVE_DATA')
        col.prop(st, 'sag_ratio', slider=True)
        col.prop(st, 'wind_amplitude', slider=True)
        col.prop(st, 'electric_enabled', text='Electricity', toggle=True)

        box = layout.box()
        box.prop(st, 'advanced', text='Advanced', emboss=False,
                 icon='TRIA_DOWN' if st.advanced else 'TRIA_RIGHT')
        if st.advanced:
            box.prop(st, 'span_length', text='Next Spacing')
            box.prop(st, 'add_at_cursor', text='Add Next at 3D Cursor')
            box.prop(st, 'show_sockets')
            box.separator(factor=0.5)
            box.prop(st, 'samples')
            box.prop(st, 'wind_frequency')
            box.prop(st, 'wind_speed')
            box.prop(st, 'independent_pulses')
            box.operator('pwl.rebuild_route', text='Rebuild Route', icon='FILE_REFRESH')
            fx = _source_fx(scene)
            if fx:
                box.prop(st, 'fx_advanced', text='Electricity Preset', emboss=False,
                         icon='TRIA_DOWN' if st.fx_advanced else 'TRIA_RIGHT')
                if st.fx_advanced:
                    for socket in _inputs(fx.node_group):
                        if socket.name.startswith(('Electric', 'Cable')):
                            key = socket.identifier
                            try:
                                if _is_gn_rna_interface(fx):
                                    entry = _gn_input_property(fx, key)
                                    if entry is not None and hasattr(entry, 'value'):
                                        box.prop(entry, 'value', text=socket.name)
                                elif key in fx:
                                    box.prop(fx, f'["{key}"]', text=socket.name)
                            except (RuntimeError, TypeError, ValueError, AttributeError):
                                pass
                    box.operator('pwl.apply_fx', text='Apply FX Settings to Line', icon='FILE_REFRESH')
            box.separator(factor=0.4)
            box.operator('pwl.clear_network', text='Delete Generated Network', icon='TRASH')


CLASSES = (
    PWL_PylonSettings,
    PWL_SceneSettings,
    PWL_OT_select_arm_count,
    PWL_OT_create_line,
    PWL_OT_add_pylon,
    PWL_OT_rebuild_route,
    PWL_OT_sync_arm_layout,
    PWL_OT_restore,
    PWL_OT_apply_fx,
    PWL_PT_main,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.pwl = PointerProperty(type=PWL_PylonSettings)
    bpy.types.Scene.pwl = PointerProperty(type=PWL_SceneSettings)


def unregister():
    del bpy.types.Scene.pwl
    del bpy.types.Object.pwl
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
