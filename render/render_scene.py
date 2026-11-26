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
and elevation fitted to the parts' bounding boxes (``dim_px.fit_camera``).

Dimensions: the manifest's ``dimensions`` (world, mm, as the transforms;
``export_scene.view_dimensions``) are fitted into the frame with the parts,
and every point (``dim_px.dim_points``) is projected through the placed
camera (``world_to_camera_view``) to pixels, origin top-left, and written to
``<out>.dims.json`` once the render is written::

    {"resolution": [w, h],
     "dimensions": [{"label", "kind", "fallback", "a", "b",
                     "line_a", "line_b"},                 # linear
                    {"label", "kind", "fallback", "centre", "a", "b",
                     "arc"},                              # angle
                    {"kind", "fallback", "points",
                     "style"}],                           # outline (no label)
     "projection": {
       "camera": {"azimuth_deg", "elevation_deg", "lens_mm", "frame_margin",
                  "fit_resolution", "matrix_world_m", "sensor_width_mm",
                  "sensor_fit", "shift", "resolution"},
       "fit_parts": [{"part", "corners_m"}],
       "world_mm": [{<the dimension's point keys>: [x, y, z] or a list}],
       "max_reprojection_error_px"}}

``projection`` reproduces the pixels without Blender
(``tests/test_renders.py``): ``world_mm`` is each dimension's points, in
``dimensions``' order and keys; ``camera`` holds ``dim_px.fit_camera``'s
inputs (with ``fit_parts``, every object's world bounding-box corners) and
the placed camera (``matrix_world_m``, row major, metres) that
``dim_px.camera_view`` projects with.  Every point is projected both ways
and the render fails if they differ by more than REPROJECT_TOLERANCE_PX;
the largest difference is ``max_reprojection_error_px``.

``line_a``/``line_b`` are the dimension line's ends (``a``/``b`` + offset);
``points`` is an outline's polyline;
``arc`` is the angle's arc from ``a`` to ``b`` sampled at dim_px.ARC_STEPS + 1
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
from dim_px import (FRAME_MARGIN, SENSOR_WIDTH_MM, camera_axes, camera_view,  # noqa: E402
                    dim_points, direction, fit_camera, flat_points, to_px)

MM = 0.001
#: How far (pixels) ``dim_px.camera_view`` may be from Blender's
#: ``world_to_camera_view`` on any dimension point before the render fails.
REPROJECT_TOLERANCE_PX = 0.5
SCREEN_STRENGTH = 1.6
#: The world's strength as light (it is 1.0, pure white, to the camera).
WORLD_LIGHT = 0.3
#: Light power (W per square metre of the scene's bounding radius).
LIGHT_W = {"key": 90.0, "fill": 30.0, "rim": 70.0}


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

def project_dimensions(scene, cam, dims, fit: dict) -> dict:
    """The sidecar: every dimension point (``dim_px.dim_points``) in pixels
    (origin top-left) of the rendered image, through Blender's
    ``world_to_camera_view``; raises if one is behind the camera or off the
    image.  Its ``projection`` records what reproduces those pixels without
    Blender: each dimension's world points (mm), the camera (``fit``: the
    inputs of ``dim_px.fit_camera``, and the placed camera's matrix and
    lens) and the largest distance between Blender's pixels and
    ``dim_px.camera_view``'s, which must be under REPROJECT_TOLERANCE_PX."""
    bpy.context.view_layer.update()          # the camera's matrix_world after _camera
    pct = scene.render.resolution_percentage
    w = scene.render.resolution_x * pct // 100
    h = scene.render.resolution_y * pct // 100
    data = cam.data
    camera = {**fit["camera"],
              "matrix_world_m": [v for row in cam.matrix_world for v in row],
              "sensor_width_mm": data.sensor_width, "sensor_fit": data.sensor_fit,
              "shift": [data.shift_x, data.shift_y], "resolution": [w, h]}
    worst = 0.0

    def px(p_mm, name: str, key: str) -> list[float]:
        nonlocal worst
        what = f"dimension {name} {key} {tuple(p_mm)}"
        p_m = Vector(p_mm) * MM
        v = world_to_camera_view(scene, cam, p_m)
        got = to_px((v.x, v.y, v.z), w, h, what)
        ox, oy, oz = camera_view(camera, tuple(p_m))
        # unrounded (to_px rounds to 0.001 px), so the error is the maths'
        err = math.hypot((ox - v.x) * w, (oy - v.y) * h)
        if not (oz > 0 and err <= REPROJECT_TOLERANCE_PX):
            raise RuntimeError(f"{what}: Blender projects it to {got}, dim_px.camera_view "
                               f"to {[ox * w, (1 - oy) * h]} at depth {oz} ({err:.3f} px "
                               f"apart, more than {REPROJECT_TOLERANCE_PX} px)")
        worst = max(worst, err)
        return got

    out, world = [], []
    for i, d in enumerate(dims):
        e = {k: d[k] for k in ("label", "kind", "style", "fallback") if k in d}
        name = repr(d["label"]) if "label" in d else f"#{i} ({d['kind']})"
        pts = dim_points(d)
        for key, v in pts.items():
            e[key] = ([px(p, name, key) for p in v] if isinstance(v, list)
                      else px(v, name, key))
        out.append(e)
        world.append({k: ([list(p) for p in v] if isinstance(v, list) else list(v))
                      for k, v in pts.items()})
    print(f"render_scene: dim_px.camera_view is within {worst:.6f} px of "
          f"world_to_camera_view on every dimension point")
    return {"resolution": [w, h], "dimensions": out,
            "projection": {"camera": camera, "fit_parts": fit["parts"],
                           "world_mm": world, "max_reprojection_error_px": worst}}


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
    +90 at the right (+X) (``dim_px.direction``, which the tests use)."""
    return Vector(direction(az_deg, el_deg))


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


def _camera(cam_cfg, objs, res, extra=()) -> dict:
    """Place the scene's camera with ``dim_px.fit_camera``: at the
    manifest's bearing and elevation, fitted to every object's bounding-box
    corners (tighter than the scene box's corners, which overshoot an
    L-shaped open box) and ``extra`` (the dimensions' points, metres).
    Returns the fit's inputs for the sidecar: ``{"camera": {...},
    "parts": [{"part", "corners_m"}]}``."""
    scene = bpy.context.scene
    data = bpy.data.cameras.new("camera")
    data.lens = cam_cfg["lens_mm"]
    data.sensor_width = SENSOR_WIDTH_MM
    data.sensor_fit = "HORIZONTAL"
    data.shift_x = data.shift_y = 0.0
    data.clip_start, data.clip_end = 0.01, 100.0
    cam = bpy.data.objects.new("camera", data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    az, el = cam_cfg["azimuth_deg"], cam_cfg["elevation_deg"]
    # dim_px's axes are Blender's track-to (camera -Z at the scene, +Y up)
    rot = (-_direction(az, el)).to_track_quat("-Z", "Y").to_matrix()
    ours = camera_axes(az, el)
    for k in range(3):
        col = [rot[r][k] for r in range(3)]
        if max(abs(p - q) for p, q in zip(col, ours[k])) > 1e-5:
            raise RuntimeError(f"dim_px.camera_axes axis {k} {ours[k]} is not "
                               f"to_track_quat's {col}")
    parts = [{"part": o.name,
              "corners_m": [list(o.matrix_world @ Vector(c)) for c in o.bound_box]}
             for o in objs]
    corners = [tuple(p) for e in parts for p in e["corners_m"]]
    m = fit_camera(az, el, data.lens, res, corners, [tuple(p) for p in extra],
                   FRAME_MARGIN, SENSOR_WIDTH_MM)
    cam.matrix_world = Matrix([m[0:4], m[4:8], m[8:12], m[12:16]])
    return {"camera": {"azimuth_deg": az, "elevation_deg": el, "lens_mm": data.lens,
                       "frame_margin": FRAME_MARGIN, "fit_resolution": list(res)},
            "parts": parts}


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
    fit = _camera(man["camera"], objs, res, [Vector(p) * MM for p in flat_points(dims)])
    lo, hi = _bounds(objs)
    centre, radius = (lo + hi) / 2, (hi - lo).length / 2
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
    side = project_dimensions(scene, scene.camera, dims, fit)
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
