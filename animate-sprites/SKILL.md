---
name: animate-sprites
description: "Animate a game's unit sprites video-first with Grok Imagine and deliver clean horizontal sprite-sheet strips timed to how fast each unit moves. Pick a flat key color far from that unit's own colors, plant every frame's feet on the shadow line, and keep limbs, muzzle flashes, and death poses inside the cell. Use when the user runs /animate-sprites, or asks to animate sprites, make a walk, fire, or death strip, chroma-key a sheet, or fix magenta edges, interior key smears, floating feet, clipped frames, or baked shadows."
---

# Animate sprites

The image model draws the rest pose. The video model supplies the motion. Harvest frames, key them, and pack a horizontal strip of square cells: width is a multiple of height, and height is the cell size.

The pass/fail rules live in `scripts/check_strips.py` in this skill's directory. Run it from there. Do not restate or loosen its thresholds.

## Key color

Run `suggest` on the rest-pose sprite before making a plate. It chooses green, blue, red, or magenta.

```bash
python3 scripts/check_strips.py suggest rest.png
```

Use the plate it prints. A purple or violet body is in the magenta family: keying it on magenta turns the armor transparent and leaves holes with a lilac rim. Green is the plate that stays far from that body. A unit with its own green glow rejects green for the same reason. Do not override `suggest` because the still sprite looks opaque; video compression pulls body pixels toward the plate.

Build the plate in code. Composite the sprite onto a flat field of that RGB. Do not ask the image model to draw the background. Leave a wide margin of plate around the figure. A walk swings the arms past the rest pose. A death sprawls farther than a walk. If any frame's body touches the plate edge, those pixels are gone; reshoot with the figure smaller on the same plate.

Key with the same script, then despill is already in that command:

```bash
python3 scripts/check_strips.py key frame.png frame_rgba.png --plate green
```

## Animate

For a cycle (walk, idle), pin the plate as both `first_frame` and `last_frame` so the clip closes. For a one-shot (fire, death), pin `first_frame` only. One subject, camera locked, background stays that flat plate. Square aspect, about 6 seconds. Generate two clips at a time; the video tool rate-limits near two per second.

Extract at 12 fps. Pick one cycle. The pinned last frame matches the first, so do not keep both. Skip a frame that severs a limb rather than shipping it.

## Pack

Sample the keyed frame back into a canvas larger than the rest pose. Keep the rest-pose center as the horizontal anchor. The shoulder, the muzzle flash, and the fallen body live outside the original rect. Cropping back to that rect is what cuts them off.

Each strip is one cell size. Place the anchor at `cell / 2` on every frame so the body does not slide sideways against the shadow. Do not recenter a frame on its own bbox.

Plant the feet: the lowest row with at least 3 opaque pixels lands on the same row in every frame. A single pixel below that row is a toe, not noise; do not delete it. Give the cell enough room that no opaque pixel touches the cell edge. Extent plus margin, then one more pixel: a cell sized as `2 * (extent + margin)` still lands the outer pixel on the edge.

A fire trail is key color left where the flash moved, inside the silhouette, not only on the outline. Delete pixels that are outside the rest-pose alpha and are not the hot flash (high red, mid green, red well above blue). Keep the flash.

The game draws the contact shadow. Remove a separate dark puddle or pink specks under the feet. A darkness mask across the lower body punches holes in armor and detaches legs. Do not fill every enclosed gap between limbs; that gap is not a key hole.

## Check

```bash
python3 scripts/check_strips.py check <strip-folder>
python3 scripts/check_strips.py self-test
```

`check` fails on:

- `edge-key` — plate color left on a pixel that touches transparency, including diagonal neighbors. Outside the cell counts as clear.
- `interior-key` — plate color smeared inside the motion, where it does not touch transparency. A handful of pixels is an armor highlight; more than that fails.
- `floating-feet` — the foot row is far above the bottom of the cell, or it jumps between frames.
- `clipped` — an opaque pixel touches a cell edge (or sits inside `--margin`).
- `baked-shadow` — a flat neutral puddle under the feet that is not connected to the body, or specks of the plate that strip was keyed from. Pink specks count only for a magenta plate. A `.plate` file beside the strip (`green`, `magenta`, `blue`, or `red`) is that plate; without one, the checker uses the same choice as `suggest`. A green-keyed purple unit's own purple is not a speck.
- `body-holes` — a transparent hole inside the body with a key-colored rim. An open gap between legs is not a hole.

`--foot-pad 4` matches a Godot strip whose planted row is `cell_height - 5` and allows one stray pixel under it. Run `self-test` after changing the script. Then look at the strips on a flat grey background. The checker does not replace that look: confirm the death pose fits and a walk frame has no smear.

## Godot

Square cells are required when the frame rect is `(index * height, 0, height, height)` and the sprite offset is `(0, -height / 2 + 4)`. That offset puts the row `height - 5` on the contact shadow. A non-square cell needs an engine change, not a wider sheet.

Play the strip from distance traveled. One cycle is one stride in pixels, not a fixed frame rate. In Lunar Age those strides are mech 24, crawler 16, and brute 44.

`art_sprites.gd` in Godot 4.7 cannot use an untyped array literal for a typed array, `for` over an array literal, integer `//`, or a ternary. The boot audit's magenta edge test is 8-connected, and the importer's alpha-border fix does not change opaque pixels, so a diagonal fringe still fails after import.

Mirror a facing only when the silhouette matches. Record with Movie Maker without `--headless`; on a server, run it under a virtual display such as Xvfb. Run `--import` and `--quit-after` as two separate Godot processes. Do not leave a temporary spawn hook in the game after the recording.
