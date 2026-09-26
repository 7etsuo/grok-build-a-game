# GAME TITLE

## Engine
- Godot 4 with GDScript. Use static types where practical. Standard build, not .NET.
- Compatibility renderer (`gl_compatibility`).
- Window 1920x1080, stretch mode `canvas_items`, stretch aspect `keep`.

## Layout
- `scenes/` for `.tscn`, `scripts/` for `.gd`, `assets/` for art and sound, `docs/` for design docs.
- `.gitignore` is `.godot/` only. Keep generated `*.uid` files.

## Workflow
- Build one PR Plan step at a time. The human plays it and makes the commit. Do not commit. Never delete a file unless the human asks.
- After every change, from the repo root, as two separate processes:

```text
godot --headless --path . --import
godot --headless --path . --quit-after 300
```

- Do not combine `--import` with `--quit-after` or `--write-movie`. Do not pass `--headless` with `--write-movie`.
- Exit 0 is not success. A parse error can still exit 0. The log must contain no `ERROR` and no `WARNING`. A new `class_name` is invisible to `--quit-after` until `--import` has run.
- `--quit-after` counts frames, not seconds. Headless is not 60 fps. Movie Maker is 60 fps, so frame N is about N/60 seconds.
- One known driver line is not a warning to fix: `Could not set V-Sync mode, as changing V-Sync mode is not supported by the graphics driver` on llvmpipe. Do not change project settings to silence it.
- Boot stdout, after the engine banner, is one exact line agreed in the GDD. Record that line here once the first boot step exists: `GAME boot ...`
- To see the game, record with `--write-movie /tmp/GAME/frame.png`, open the frames, and look at them. Do not call a visual step done from the log alone.
- Art follows `docs/art-direction.md` once that file exists. Keep placeholder drawing. Do not delete it when real sprites arrive.
- End every step with a short list of what the human should test.
