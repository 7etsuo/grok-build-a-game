---
name: build-a-game
description: >-
  Build a complete 2D Godot 4 GDScript game the way Lunar Age was built:
  install Godot into ~/.local/bin if needed, write AGENTS.md, run /design
  for a GDD whose PR Plan ends in art, a look pass, game feel, and a 60-second
  attract mode, then implement one playable step per turn and stop for the
  user to play and commit. Art goes through docs/art-direction.md and the
  game-assets skill, with a sprite check that fails on checkerboards, green
  fringes, and wrong sizes. Playtest notes and screenshots are fixed and
  proven in Movie Maker frames the agent inspects. Use when the user runs
  /build-a-game, or asks to build a 2D game, start a Godot game, or repeat
  the Lunar Age workflow.
---

# Build a 2D game

This skill stays in force for later turns of the same game: the next PR Plan step, a playtest note, and a screenshot. The project's `AGENTS.md` is the house-rule source. Do not restate it.

## Start

Ask for the game idea before installing, designing, or writing files. If the invoking message already states the idea, use it. Otherwise ask and stop.

## Engine

If `godot --version` fails and `~/.local/bin/godot` is missing, install the latest stable Godot 4 standard Linux build (not .NET) as `~/.local/bin/godot` and prove it with `godot --version`.

## House rules

Copy this skill's `templates/AGENTS.md` to the project root. Replace `GAME TITLE` and the boot-line placeholder with this game's name and the exact boot line from the GDD. Then follow that file.

## Design

Run the `design` skill. Save the GDD at `docs/GDD.md`. Do not implement during the design turn.

The PR Plan is small playable steps. Each step lists its files, human tests, the headless gate, and a Movie Maker command when the picture changes. The plan's tail, in this order, is fixed:

1. Write `docs/art-direction.md`. No PNGs.
2. Replace placeholders with sprites from the `game-assets` skill.
3. Look pass, judged from Movie Maker frames.
4. Game-feel pass.
5. A 60-second attract mode (`--demo`) that shows the whole loop.

Anything the fantasy needs (map, control, economy, combat, win and loss) comes before that tail, one launchable step at a time.

## One step per turn

Implement exactly one PR Plan step, then stop. Do not start the next step. End with that step's what-to-test list.

The human plays and commits. Never delete a file unless they ask.

## Art

`docs/art-direction.md` names every file, canvas size, and prompt before any PNG exists. Generate with the `game-assets` skill. Keep the placeholder drawer.

After generating, run this skill's `scripts/check_sprites.py` with one `--size relative/path=WxH` per file from the art direction. Those predicates are the spec. Wire the same checks into boot so a bad sprite `push_error`s `art missing`, `art size`, `art green`, or `art checker`. Load with `load()`. `FileAccess.file_exists` is false inside an exported pack, so checking the filesystem before `load()` hides shipped art.

Flipbook cells need a transparent pad, or linear filtering samples the next frame. Death smoke fades out. Additive fire still has to show the dark smoke.

## Look

Put this in `docs/art-direction.md` and build it in the look pass. Do not leave it for a polish pass.

- Ground is one seamless texture, tiled from each tile's UV, broken by big soft patches. Keep the tile map for clicks and pathing, and do not draw it. Extend the ground past the play area, darken outside it, and fade into the sky only past the far top. No rock rim. A sky body sits in clear sky, under the HUD.
- Lights are additive sprites, not Light2D: a pool under each building, a small pool in front of each vehicle, a faction glow where the fiction has one, and a soft vignette.
- One shared contact shadow under every unit, building, and prop. No ground, pad, or shadow box baked into a sprite.
- A resource reads as something to take. A blocker is smaller, darker, and rare, and does not share that read.
- Selection is a flat ellipse on the feet, behind the body. HP is a short bar above the head with a thin dark frame. Buildings match.
- The top bar is short, with a hairline under it. A corner minimap shows your units, enemies, and the camera box.
- Dust is a soft puff that fades. A shot is a bright core with a faint glow. An explosion leaves a scorch that fades over several seconds.

## Playtests

Take the numbered notes and the screenshots. Fix each one. Open your own Movie Maker frames and confirm that note before calling it fixed. Attract timing, camera, crowd shape, and readability stay in the demo. Do not retune the real match to make the demo look right.

## Traps

These are not in the house-rules template.

- Edge pan treats a headless or Movie Maker mouse at the origin as inside the margin and walks the camera. Disable it when the display is headless or a movie path is set.
- Reissuing an attack order every frame cancels the approach. Issue it when the target changes.
- A formation tile past weapon range makes that unit stand and never fire. Pick an open tile on the lane that is inside range, or drop the lane.
- One shared path makes a wave walk single file. Spread the spawn tiles and steer a loose swarm.
- `center_on` every frame clears camera shake. Glide when the attract camera should move.
- A building click misses when the hit test is only the footprint. Opaque sprite pixels count.
- This Godot has rejected `//` integer division and assigning an untyped array literal to a typed array. The headless log is the check.
- A `--selftest` flag left on the main scene reloads into itself. Run the test inside the main scene, then remove the flag. A scene started with `-s` does not see autoloads.
- Greying a faction or a resource into the ground removes the read. The hive lost its purple and green cracks; the ore became another boulder. Darken it and keep the color that identifies it.
- A world-position varying across one map-sized quad turns the grain into scanlines. Tile the seamless texture and sample it from that tile's UV.
- An image edit of a painted sprite goes photoreal. Recolor the pixels you have.
- A pale boulder on every blocked tile, drawn at resource size, fills the map. Draw a few small dark ones. Pathing still uses every blocked tile.
- A contact shadow floats when the art's foot is not on the canvas foot line. Put the foot on that line.
- A lamp tucked under the hull, and a sky body placed from world Y alone, never appear. Put the lamp in front of the facing, and place the sky body from a frame.
- Flecks from `x * a + y * b` land in stripes. Scatter them.
- Hard `draw_circle` dust and a width-2 laser stay cheap. An additive `_draw` beam can also fail to show. A Line2D core plus a wider faint line is the one that showed.
