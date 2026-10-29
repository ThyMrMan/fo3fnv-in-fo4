"""Load a gun_pose_scene.py JSON into Blender (run inside Blender, e.g. over its MCP add-on):

    import runpy
    runpy.run_path('tools/nif/blender_pose_scene.py', init_globals={'SCENE': '<scene.json>', 'RENDER': '<dir or None>'})

Each group becomes a collection, its objects parented to an empty spaced along X, with a camera at the empty's
origin and the group's field of view (horizontal). Marks are small spheres named after the bone or node; gun, arms
and marks get flat colors. With RENDER, each group renders (Workbench) to <RENDER>/<group>.png from its camera.
See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import json
import math
import re
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

#: Distance between groups along X (game units).
SPACING = 300.0
#: Flat color per mesh kind.
COLORS = {'gun': (0.35, 0.35, 0.4, 1.0), 'arms': (0.85, 0.6, 0.45, 1.0), 'mark': (1.0, 0.1, 0.1, 1.0)}
#: Mark sphere radius (game units).
MARK_RADIUS = 0.6
#: Orthographic views of the gun and hands: (image right, image up, toward the camera) in the camera frame.
ORTHO = {'left': ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
         'top': ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))}
#: Render width over height; an orthographic view's margin around its box; how far back it sits.
ASPECT, ORTHO_MARGIN, ORTHO_DISTANCE = 16 / 9, 1.15, 400.0


def material(kind: str):
    """The flat material of mesh kind `kind`, made once."""
    name = f'pose_{kind}'
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = COLORS[kind]
    return mat


def mesh_object(name: str, verts: list, tris: list, kind: str, parent, collection):
    """A mesh object of `verts`/`tris` under `parent` in `collection`."""
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], tris)
    data.update()
    obj = bpy.data.objects.new(name, data)
    obj.data.materials.append(material(kind))
    obj.parent = parent
    collection.objects.link(obj)
    return obj


def mark_object(name: str, at: list, parent, collection):
    """A small sphere named `name` at `at` under `parent`."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=MARK_RADIUS, location=at, segments=12, ring_count=6)
    obj = bpy.context.active_object
    obj.name = f'mark {name}'
    obj.data.materials.append(material('mark'))
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    obj.parent = parent
    return obj


def group(name: str, data: dict, index: int):
    """Group `name` of the scene as a collection; its cameras (the game's view, then ORTHO's)."""
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    origin = bpy.data.objects.new(f'{name} origin', None)
    origin.location = (index * SPACING, 0.0, 0.0)
    collection.objects.link(origin)
    for m in data['meshes']:
        mesh_object(f'{name}: {m["kind"]} {m["name"]}', m['verts'], m['tris'], m['kind'], origin, collection)
    for m in data['marks']:
        mark_object(m['name'], m['at'], origin, collection)
    points = [p for m in data['meshes'] if m['kind'] == 'gun' for p in m['verts']] + [m['at'] for m in data['marks']]
    low = [min(p[k] for p in points) for k in range(3)]
    high = [max(p[k] for p in points) for k in range(3)]
    view = camera(f'{name} camera', origin, collection, fov=data['fov'])
    return (view, *(camera(f'{name} {label}', origin, collection, frame=(axes, low, high))
                     for label, axes in ORTHO.items()))


def camera(name: str, parent, collection, fov: float = 0.0, frame: 'tuple | None' = None):
    """A camera object `name` under `parent`: at the origin with horizontal field of view `fov` (degrees), or with
    `frame` (ORTHO axes, box low and high corners) an orthographic one framing that box."""
    data = bpy.data.cameras.new(name)
    data.sensor_fit = 'HORIZONTAL'
    data.clip_start, data.clip_end = 0.1, 5000.0
    obj = bpy.data.objects.new(name, data)
    if frame is None:
        data.angle = math.radians(fov)
    else:
        (right, up, back), low, high = frame
        size = [h - lo for h, lo in zip(high, low)]
        center = Vector([(h + lo) / 2 for h, lo in zip(high, low)])
        across = max(abs(Vector(right).dot(Vector(size))), abs(Vector(up).dot(Vector(size))) * ASPECT)
        data.type, data.ortho_scale = 'ORTHO', across * ORTHO_MARGIN
        obj.matrix_world = Matrix((right, up, back)).transposed().to_4x4()
        obj.location = center + Vector(back) * ORTHO_DISTANCE
    obj.parent = parent
    collection.objects.link(obj)
    return obj


def clear() -> None:
    """Remove every collection and object a previous load made (names ending ' origin' parent them)."""
    for coll in [c for c in bpy.data.collections if any(o.name.endswith(' origin') for o in c.objects)]:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)


def render(cameras: dict, out_dir: Path) -> None:
    """Render each group alone from its cameras to <out_dir>/<group> <view|left|top>.png."""
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, pair in cameras.items():
        for layer in bpy.context.view_layer.layer_collection.children:
            layer.exclude = layer.name != name
        for label, cam in zip(('view', *ORTHO), pair):
            scene.camera = cam
            scene.render.filepath = str(out_dir / (re.sub(r'[^\w\- ]', '_', name) + f' {label}.png'))
            bpy.ops.render.render(write_still=True)
    for layer in bpy.context.view_layer.layer_collection.children:
        layer.exclude = False


def load(path: str, out_dir: 'str | None' = None) -> list:
    """Load scene JSON `path` (replacing an earlier load); render each group into `out_dir` when given."""
    clear()
    groups = json.loads(Path(path).read_text(encoding='utf-8'))
    cameras = {name: group(name, data, i) for i, (name, data) in enumerate(groups.items())}
    if out_dir:
        render(cameras, Path(out_dir))
    return list(cameras)


if 'SCENE' in globals():
    print(load(globals()['SCENE'], globals().get('RENDER')))
