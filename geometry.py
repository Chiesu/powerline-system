"""Pure-python construction for the source pylon's edge-based arm geometry.

The supplied pylon uses local Y for height, local X for arms, and local Z
for front/back depth. This module deliberately avoids bpy so its geometry
logic can be checked without launching Blender.
"""
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class CalibratedPylon:
    height: float
    core_x: float
    core_z: float
    tip_x: float
    lower_tier: float
    middle_tier: float
    upper_tier: float
    tip_drop: float
    remove_from_height: float

    @property
    def spacing(self):
        return (self.upper_tier - self.lower_tier) / 2

    @property
    def reach(self):
        return self.tip_x - self.core_x


def calibrate(coords):
    """Infer the exact 3-row arm module from the provided skeletal mesh."""
    vertices = [tuple(map(float, p)) for p in coords]
    if len(vertices) < 16:
        raise ValueError('A source mesh with at least 16 vertices is required.')
    ymin = min(p[1] for p in vertices)
    ymax = max(p[1] for p in vertices)
    height = ymax - ymin
    if height <= 0.001:
        raise ValueError('Pylon must extend along local Y (height axis).')
    upper = [p for p in vertices if p[1] > ymin + height * 0.68]
    if len(upper) < 8:
        raise ValueError('Cannot locate source arms. Use the included source pylon.')
    xs = sorted(set(round(abs(p[0]), 5) for p in upper if abs(p[0]) > 0.05))
    if len(xs) < 2:
        raise ValueError('The source needs a center frame and outer arm points.')
    # Ignore the tapered leg at the beginning of the upper structure.
    candidate_xs = [x for x in xs if any(abs(abs(p[0])-x)<0.0001 and abs(p[2]) > 0.1 for p in upper)]
    tip_x = max(candidate_xs)
    core_x = min(candidate_xs)
    if tip_x <= core_x * 1.3:
        raise ValueError('The source arm span could not be distinguished from the tower.')
    arm_top = [p for p in upper if abs(abs(p[0]) - tip_x) < 0.0002 and abs(p[2]) > 0.05]
    levels = sorted(set(round(p[1], 5) for p in arm_top))
    if len(levels) != 3:
        raise ValueError(f'Expected three source arm levels, found {len(levels)}: {levels}')
    core_z = median(abs(p[2]) for p in arm_top)
    lower_nodes = [p[1] for p in upper if abs(abs(p[0]) - tip_x) < 0.0002 and abs(p[2]) < core_z * 0.25]
    drops = [min((y - lower for lower in lower_nodes if 0 < y-lower < 1.0), default=0.48) for y in levels]
    tip_drop = median(drops)
    if tip_drop < 0.01:
        tip_drop = 0.48
    return CalibratedPylon(
        height=height,
        core_x=core_x,
        core_z=core_z,
        tip_x=tip_x,
        lower_tier=levels[0],
        middle_tier=levels[1],
        upper_tier=levels[2],
        tip_drop=tip_drop,
        remove_from_height=levels[0] - tip_drop - 0.05,
    )


def arm_levels(pairs, center, spacing):
    """Return symmetric low-to-high tier elevations for 1-3 arm pairs.

    The center remains fixed for every configuration. Odd pair counts have
    a central arm pair; even pair counts straddle it symmetrically.
    """
    if pairs not in (1, 2, 3):
        raise ValueError('Arm pairs must be one, two, or three.')
    if spacing < 0:
        raise ValueError('Arm spacing must be nonnegative.')
    return [center + (i - (pairs - 1) / 2) * spacing for i in range(pairs)]


def make_pylon(source_coords, source_edges, calibrated, pairs=3,
               reach=None, spacing=None, center=None, drop=None):
    """Return (vertices, edges, sockets), without realizing any tube geometry.

    The original tower skeleton is preserved, and only its cross-arm modules
    are replaced. Each socket is positioned at the bottom point of its arm.
    Socket keys are stable (L0/R0 through L3/R3) and follow low-to-high order.
    """
    if pairs not in (1, 2, 3):
        raise ValueError('Arm pairs must be one, two, or three.')
    c = calibrated
    reach = c.reach if reach is None else float(reach)
    spacing = c.spacing if spacing is None else float(spacing)
    center = c.middle_tier if center is None else float(center)
    drop = c.tip_drop if drop is None else float(drop)
    if min(reach, spacing, drop) < 0:
        raise ValueError('Reach, spacing, and drop must be nonnegative.')
    levels = arm_levels(pairs, center, spacing)

    all_verts = [tuple(map(float, p)) for p in source_coords]
    cutoff_x = c.core_x + (c.tip_x-c.core_x)*0.45
    retained = []
    for a, b in source_edges:
        p, q = all_verts[a], all_verts[b]
        # Remove only the original lateral arm geometry (never the tower legs).
        # This includes the triangulated hanging tips.
        outer = (abs(p[0]) > cutoff_x or abs(q[0]) > cutoff_x)
        upper = (p[1] > c.remove_from_height and q[1] > c.remove_from_height)
        if not (outer and upper):
            retained.append((int(a), int(b)))

    used = set(i for edge in retained for i in edge)
    out_vertices = []
    indices = {}
    coord_index = {}
    for idx in sorted(used):
        co=all_verts[idx]
        key=tuple(round(v,5) for v in co)
        if key not in coord_index:
            coord_index[key] = len(out_vertices)
            out_vertices.append(co)
        indices[idx] = coord_index[key]
    out_edges = []
    edge_set = set()

    def edge(a,b):
        if a == b:
            return
        k=tuple(sorted((a,b)))
        if k not in edge_set:
            edge_set.add(k)
            out_edges.append((a,b))

    for a,b in retained:
        edge(indices[a],indices[b])

    def vertex(co):
        co=tuple(float(v) for v in co)
        k=tuple(round(v,5) for v in co)
        if k not in coord_index:
            coord_index[k]=len(out_vertices)
            out_vertices.append(co)
        return coord_index[k]

    tip_x = c.core_x + reach
    sockets={}
    for level_idx,y in enumerate(levels):
        # We keep the four center-frame corners, and extend the side arms
        # using the same triangular-tip topology seen in the original source.
        core = {}
        for side in (-1,1):
            for depth_side in (-1,1):
                core[side,depth_side]=vertex((side*c.core_x,y,depth_side*c.core_z))
        edge(core[-1,-1],core[1,-1])
        edge(core[-1,1],core[1,1])
        edge(core[-1,-1],core[-1,1])
        edge(core[1,-1],core[1,1])
        for side,side_name in ((-1,'L'),(1,'R')):
            front=vertex((side*tip_x,y,-c.core_z))
            back=vertex((side*tip_x,y,c.core_z))
            lower=vertex((side*tip_x,y-drop,0))
            edge(core[side,-1],front)
            edge(core[side,1],back)
            edge(front,back)
            edge(front,lower)
            edge(back,lower)
            sockets[f'{side_name}{level_idx}']=(side*tip_x,y-drop,0.0)
    return out_vertices,out_edges,sockets


def pylon_apex(source_coords):
    """Highest centered vertex in the original tower's local coordinates.

    Seven-wire layouts connect the seventh span to this apex, not to a
    synthetic fourth crossarm. Parent-relative empties keep it live under
    pylon translation, rotation, and scaling.
    """
    coords = [tuple(map(float, p)) for p in source_coords]
    if not coords:
        raise ValueError('Cannot find an apex in an empty pylon mesh.')
    return min(coords, key=lambda p: (-p[1], p[0]*p[0] + p[2]*p[2]))
