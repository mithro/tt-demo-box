"""Render one scene manifest (``scripts/export_scene.py``) with Blender.

Runs inside Blender (only ``bpy`` and the standard library)::

    blender -b --factory-startup -P render/render_scene.py -- \\
        --manifest tmp/scene/printed-open-front.json --out output/renders/printed-open-front.png

The manifest lists each part's STL (mm, closed placement), its 4 x 4
``transform`` (row major, mm), ``material`` and base ``colour``, and the
monitor screens (a quad in mm with its image).  The scene is converted to
metres (the transforms are pre-multiplied by 1/1000) so the lights' watts mean
what they say.

Look: Cycles on the CPU (all cores), the manifest's samples, denoising OFF
(Debian's Blender 4.3.2 is built without OpenImageDenoise and fails with
"build has no OpenImageDenoise support" otherwise), a white world, a white
ground under the lowest part, a three-point light rig (key, fill, rim) sized
from the scene's bounding box, and a 35 mm camera at the manifest's bearing
and elevation fitted to the bounding box.

Dimensions: the manifest's ``dimensions`` (world, mm, as the transforms;
``export_scene.view_dimensions``) are fitted into the frame with the parts,
and every point is projected through the placed camera
(``world_to_camera_view``) to pixels, origin top-left, and written to
``<out>.dims.json`` once the render is written::

    {"resolution": [w, h],
     "dimensions": [{"label", "kind", "fallback", "a", "b",
                     "line_a", "line_b"},                 # linear
                    {"label", "kind", "fallback", "centre", "a", "b",
                     "arc"}]}                             # angle

``line_a``/``line_b`` are the dimension line's ends (``a``/``b`` + offset);
``arc`` is the angle's arc from ``a`` to ``b`` sampled at ARC_STEPS + 1
points (it projects to an ellipse, not a circle).  A point behind the camera
or outside the image raises.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))   # Blender's -P does not
from dim_px import _to_px  # noqa: E402

MM = 0.001
#: Margin round the fitted framing (the camera backs off by this factor).
FRAME_MARGIN = 1.10
SCREEN_STRENGTH = 1.6
#: The world's strength as light (it is 1.0, pure white, to the camera).
WORLD_LIGHT = 0.3
#: Light power (W per square metre of the scene's bounding radius).
LIGHT_W = {"key": 90.0, "fill": 30.0, "rim": 70.0}
#: Segments the angle arc is sampled in.
ARC_STEPS = 32


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="render_scene.py")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--samples", type=int, default=None, help="override (quick looks)")
    ap.add_argument("--scale", type=int, default=100, help="resolution percentage")
    return ap.parse_args(argv)


def _clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)


def _matrix(rows16) -> Matrix:
    m = Matrix([rows16[0:4], rows16[4:8], rows16[8:12], rows16[12:16]])
    return Matrix.Scale(MM, 4) @ m


# --- materials ------------------------------------------------------------------------

_MATS: dict = {}


def _principled(name, colour, **inputs):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    for k, v in inputs.items():
        bsdf.inputs[k].default_value = v
    return mat, bsdf


def _plywood(colour):
    """Birch ply: the base colour with soft diagonal grain bands."""
    mat, bsdf = _principled("plywood", colour, Roughness=0.62)
    nt = mat.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "DIAGONAL"
    wave.inputs["Scale"].default_value = 0.06          # object coords are mm
    wave.inputs["Distortion"].default_value = 3.5
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 1.5
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.4
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    lo = tuple(c * 0.9 for c in colour)
    ramp.color_ramp.elements[0].color = (*lo, 1.0)
    ramp.color_ramp.elements[1].color = (*colour, 1.0)
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.8
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])
    nt.links.new(noise.outputs["Fac"], mix.inputs[2])
    nt.links.new(mix.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def material(kind: str, colour) -> bpy.types.Material:
    key = (kind, tuple(round(c, 4) for c in colour))
    if key in _MATS:
        return _MATS[key]
    colour = tuple(colour)
    if kind == "plywood":
        mat = _plywood(colour)
    elif kind == "pla":
        mat, _ = _principled("pla", colour, Roughness=0.48)
    elif kind == "metal":
        mat, _ = _principled("metal", colour, Metallic=1.0, Roughness=0.32)
    elif kind == "rubber":
        mat, _ = _principled("rubber", colour, Roughness=0.85)
    elif kind == "plastic":
        mat, _ = _principled("plastic", colour, Roughness=0.3)
    elif kind == "pcb":
        mat, _ = _principled("pcb", colour, Roughness=0.22)
    else:
        raise ValueError(f"unknown material {kind!r}")
    _MATS[key] = mat
    return mat


def _screen_material(image: Path):
    mat = bpy.data.materials.new("screen")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(image))
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = SCREEN_STRENGTH
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


# --- dimensions -------------------------------------------------------------------------

def _arc(centre, a, b, steps=ARC_STEPS) -> list[Vector]:
    """Points on the circular arc about ``centre`` from ``a`` to ``b`` (equal
    radii), the short way round."""
    c, va, vb = Vector(centre), Vector(a) - Vector(centre), Vector(b) - Vector(centre)
    r = va.length
    if r <= 0 or abs(vb.length - r) > 1e-6 * max(r, 1.0):
        raise ValueError(f"angle arms differ: {va.length} and {vb.length}")
    u = va.normalized()
    theta = va.angle(vb)
    w = (vb - u * vb.dot(u)).normalized()
    return [c + (u * math.cos(theta * i / steps) + w * math.sin(theta * i / steps)) * r
            for i in range(steps + 1)]


def dim_points(d) -> dict[str, list]:
    """A dimension's named points (manifest mm): linear ``a``, ``b``,
    ``line_a``, ``line_b``; angle ``centre``, ``a``, ``b`` and ``arc`` (a
    list)."""
    if d["kind"] == "linear":
        off = Vector(d["offset"])
        return {"a": Vector(d["a"]), "b": Vector(d["b"]),
                "line_a": Vector(d["a"]) + off, "line_b": Vector(d["b"]) + off}
    if d["kind"] == "angle":
        return {"centre": Vector(d["centre"]), "a": Vector(d["a"]), "b": Vector(d["b"]),
                "arc": _arc(d["centre"], d["a"], d["b"])}
    raise ValueError(f"unknown dimension kind {d['kind']!r}")


def _flat_points(dims) -> list[Vector]:
    """Every dimension point, in Blender's metres."""
    out = []
    for d in dims:
        for v in dim_points(d).values():
            out += [p * MM for p in (v if isinstance(v, list) else [v])]
    return out


def project_dimensions(scene, cam, dims) -> dict:
    """The sidecar: every dimension point in pixels (origin top-left) of the
    rendered image; raises if one is behind the camera or off the image."""
    bpy.context.view_layer.update()          # the camera's matrix_world after _camera
    pct = scene.render.resolution_percentage
    w = scene.render.resolution_x * pct // 100
    h = scene.render.resolution_y * pct // 100

    def px(p_mm: Vector, label: str, key: str) -> list[float]:
        v = world_to_camera_view(scene, cam, p_mm * MM)
        return _to_px((v.x, v.y, v.z), w, h, f"dimension {label!r} {key} {tuple(p_mm)}")

    out = []
    for d in dims:
        e = {k: d[k] for k in ("label", "kind", "fallback")}
        for key, v in dim_points(d).items():
            e[key] = ([px(p, d["label"], key) for p in v] if isinstance(v, list)
                      else px(v, d["label"], key))
        out.append(e)
    return {"resolution": [w, h], "dimensions": out}


# --- scene ------------------------------------------------------------------------------

def _import_part(path: Path, name: str):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.wm.stl_import(filepath=str(path))
    obj = bpy.context.selected_objects[0]
    obj.name = name
    mesh = obj.data
    mesh.shade_smooth()
    mesh.set_sharp_from_angle(angle=math.radians(35.0))
    return obj


def _screen(entry, base: Path):
    quad = entry["quad"]
    mesh = bpy.data.meshes.new("screen")
    mesh.from_pydata([tuple(p) for p in quad], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, co in zip(mesh.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[loop].uv = co
    obj = bpy.data.objects.new("screen", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = _matrix(entry["transform"])
    mesh.materials.append(_screen_material(base / entry["image"]))
    return obj


def _bounds(objs):
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def _world():
    """White to the camera; a dimmer white as light (WORLD_LIGHT), so the
    background reads pure white without washing the parts out."""
    w = bpy.data.worlds.new("white")
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = WORLD_LIGHT
    cam_bg = nt.nodes.new("ShaderNodeBackground")
    cam_bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    cam_bg.inputs["Strength"].default_value = 1.0
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg.outputs["Background"], mix.inputs[1])
    nt.links.new(cam_bg.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], nt.nodes["World Output"].inputs["Surface"])
    bpy.context.scene.world = w


def _over_white(scene):
    scene.use_nodes = True
    nt = scene.node_tree
    layers, comp = nt.nodes["Render Layers"], nt.nodes["Composite"]
    over = nt.nodes.new("CompositorNodeAlphaOver")
    over.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(layers.outputs["Image"], over.inputs[2])
    nt.links.new(over.outputs["Image"], comp.inputs["Image"])


def _ground(z, size):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    g = bpy.context.active_object
    g.name = "ground"
    g.is_shadow_catcher = True
    g.data.materials.append(material("rubber", (0.8, 0.8, 0.8)))
    return g


def _area(name, loc, target, power, size):
    data = bpy.data.lights.new(name, type="AREA")
    data.energy = power
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    return obj


def _direction(az_deg, el_deg) -> Vector:
    """Unit vector from the scene towards the camera: bearing 0 in front (-Y),
    +90 at the right (+X)."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))


def _lights(centre, radius, az_deg):
    """Key (front-left, high), fill (front-right, low, soft), rim (behind)
    relative to the camera's bearing."""
    d = 4.0 * radius
    _area("key", centre + _direction(az_deg - 45, 50) * d, centre,
          LIGHT_W["key"] * radius ** 2, radius * 1.6)
    _area("fill", centre + _direction(az_deg + 60, 20) * d, centre,
          LIGHT_W["fill"] * radius ** 2, radius * 2.4)
    _area("rim", centre + _direction(az_deg + 180, 45) * d, centre,
          LIGHT_W["rim"] * radius ** 2, radius * 1.2)


def _camera(cam_cfg, objs, res, extra=()):
    scene = bpy.context.scene
    data = bpy.data.cameras.new("camera")
    data.lens = cam_cfg["lens_mm"]
    data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("camera", data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    lo, hi = _bounds(objs)
    centre = (lo + hi) / 2
    back = _direction(cam_cfg["azimuth_deg"], cam_cfg["elevation_deg"])
    rot = (-back).to_track_quat("-Z", "Y")
    cam.rotation_euler = rot.to_euler()
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    data.clip_start, data.clip_end = 0.01, 100.0
    # Points to fit: every object's bounding-box corners (tighter than the
    # scene box's corners, which overshoot an L-shaped open box), and
    # ``extra`` (the dimensions' points, metres).
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box] + list(extra)
    tan_x = data.sensor_width / 2 / data.lens / FRAME_MARGIN
    tan_y = tan_x * res[1] / res[0]

    def extents(dist, sx, sy):
        """Projected (x0, x1, y0, y1) as tangents, camera at centre + back *
        dist, shifted sx right and sy up."""
        c = centre + back * dist + right * sx + up * sy
        xs, ys = [], []
        for p in pts:
            v = p - c
            z = -v.dot(back)
            if z <= 1e-6:
                return None
            xs.append(v.dot(right) / z)
            ys.append(v.dot(up) / z)
        return min(xs), max(xs), min(ys), max(ys)

    def fit(dist):
        """Centre the projection by shifting the camera; does it then fit?"""
        sx = sy = 0.0
        for _ in range(8):
            e = extents(dist, sx, sy)
            if e is None:
                return False, sx, sy
            sx += (e[0] + e[1]) / 2 * dist
            sy += (e[2] + e[3]) / 2 * dist
        e = extents(dist, sx, sy)
        ok = e is not None and e[1] - e[0] <= 2 * tan_x and e[3] - e[2] <= 2 * tan_y
        return ok, sx, sy

    lo_d, hi_d = 0.0, 100.0 * (hi - lo).length
    for _ in range(50):
        mid = (lo_d + hi_d) / 2
        if fit(mid)[0]:
            hi_d = mid
        else:
            lo_d = mid
    _ok, sx, sy = fit(hi_d)
    cam.location = centre + back * hi_d + right * sx + up * sy
    return centre, (hi - lo).length / 2, lo


def main() -> int:
    a = _args()
    man = json.loads(a.manifest.read_text())
    sidecar = a.out.with_name(a.out.name + ".dims.json")
    sidecar.unlink(missing_ok=True)          # no stale sidecar survives a failure
    base = a.manifest.parent
    _clear()
    scene = bpy.context.scene
    t0 = time.time()
    objs = []
    for e in man["parts"]:
        o = _import_part(base / e["file"], e["part"])
        o.matrix_world = _matrix(e["transform"])
        o.data.materials.clear()
        o.data.materials.append(material(e["material"], e["colour"]))
        objs.append(o)
    objs += [_screen(s, base) for s in man.get("screens", ())]
    print(f"render_scene: {len(objs)} objects imported in {time.time() - t0:.1f} s")

    res = man["resolution"]
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = a.scale
    dims = man["dimensions"]
    centre, radius, lo = _camera(man["camera"], objs, res, _flat_points(dims))
    _ground(lo.z, radius * 40)
    _world()
    _lights(centre, radius, man["camera"]["azimuth_deg"])

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = a.samples or man["samples"]
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = os.cpu_count()
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    # The ground is a shadow catcher on a transparent film, laid over pure
    # white: soft contact shadows, no horizon.
    scene.render.film_transparent = True
    _over_white(scene)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(a.out.resolve())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    # Projected before the (long) render, so a dimension off the frame fails
    # fast and leaves no image; written after it, so a sidecar means a render.
    side = project_dimensions(scene, scene.camera, dims)
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"render_scene: {man['name']} {res[0]}x{res[1]} @{a.scale}% "
          f"{scene.cycles.samples} samples, {scene.render.threads} threads: "
          f"rendered in {time.time() - t1:.1f} s -> {a.out}")
    sidecar.write_text(json.dumps(side, indent=1) + "\n")
    print(f"render_scene: {len(dims)} dimensions projected -> {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
