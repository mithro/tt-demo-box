# Dimension lines on the 3D renders

Status: approved by Tim, 2026-11-25 ("Add measurements / length markers to all the 3d renders and
such"; approved the short design below with "Yes").

## Intent

Someone looking at a render should see the box's real size at a glance, in the same numbers the
drawing sheets give.

## What each render gets

| View | Dimensions |
|---|---|
| closed | overall width, depth, height (base + lid, closed) |
| open-front | width, and the open height with the 100° lid angle |
| open-back | depth, and how far the open lid reaches behind the back face |
| bank-out | the bank bay's length and width |
| laser-flatpack | each panel's size if legible, otherwise the overall laid-out extent |

The values are the layout's numbers (`demobox/layout.py`), printed through the same rounding as
the sheets (`geom.mm`), so a render can never disagree with a drawing.

## Approach (chosen)

**A 2D overlay drawn after rendering, from Blender's own camera projection.**

1. `scripts/export_scene.py` puts a `dimensions` list in each view's manifest. Each entry holds:
   - two 3D anchor points on the model, in the base frame transformed to the world;
   - an offset direction and distance for the dimension line;
   - the label text.
2. `render/render_scene.py` includes the dimension lines' 3D points when it fits the camera, so
   no line falls outside the frame.
3. After rendering, `render_scene.py` projects each anchor and line point with
   `bpy_extras.object_utils.world_to_camera_view`. It writes the pixel coordinates to a sidecar
   `<render>.dims.json`.
4. A Pillow step (`render/annotate.py`, run by `make renders` after each render) draws onto the
   PNG:
   - extension lines, the dimension line and arrowheads, in the drafting style's blue (`style`
     colours);
   - each label on a small white backing, so it reads over the model.
5. Angles (the 100° lid) are drawn as an arc through projected points, with a label.

**Considered and dropped:** dimension geometry and text built in the 3D scene. It would be
foreshortened and hard to read at oblique views, and the text would be lit and shaded like the
model.

## Rules

- Fail loudly:
  - a projected point outside the image raises;
  - two labels that overlap raise (unless they move, below);
  - a missing sidecar fails `make renders`.
- Labels may be nudged along their dimension line to avoid overlapping the model's silhouette or
  each other. If they still overlap, that is an error, not a silent overlap.
- Renders stay out of `make check`'s byte comparison (Cycles noise), as now. The dimension
  specs, labels and sidecars are tested.

## Tests

- Every label equals the layout's value through `geom.mm`.
- Each view's manifest has the dimensions in the table above.
- The overlay drawing is deterministic: the same sidecar and image give the same pixels.
- A projected point off the frame raises.

## Left to the builder

- Offsets, arrow size, font (DejaVu Sans from the pinned font file, as the packing engraving
  used) and line width.
- Exact anchor points per view.
- Whether the flat-pack shows each panel's size or only the overall extent: legibility decides.
