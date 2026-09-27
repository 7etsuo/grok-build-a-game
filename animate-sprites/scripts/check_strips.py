#!/usr/bin/env python3
"""Check horizontal sprite strips, suggest a key color, or key a plate.

Pass/fail for a folder of strips lives here. Thresholds are not copied elsewhere.

    python3 check_strips.py check FOLDER [--foot-pad N] [--margin N]
    python3 check_strips.py suggest SPRITE.png
    python3 check_strips.py key INPUT.png OUTPUT.png --plate green
    python3 check_strips.py self-test

Exit 0 when every strip passes. Exit 1 when any check fails.
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

KEYS = ("green", "blue", "red", "magenta")


def key_alpha(red, green, blue, plate):
    """Per-pixel alpha in 0..1 for a flat plate. Shared by suggest and key."""
    red = red.astype(np.float32)
    green = green.astype(np.float32)
    blue = blue.astype(np.float32)
    if plate == "magenta":
        dist = np.abs(red - 255.0) + np.abs(green) + np.abs(blue - 255.0)
        return np.clip((dist - 36.0) / 80.0, 0.0, 1.0)
    if plate == "green":
        lead = green - np.maximum(red, blue)
    elif plate == "blue":
        lead = blue - np.maximum(red, green)
    elif plate == "red":
        lead = red - np.maximum(green, blue)
    else:
        raise SystemExit("unknown plate %s" % plate)
    alpha = np.clip((28.0 - lead) / 22.0, 0.0, 1.0)
    if plate == "green":
        pure = (green > 150.0) & (red < 80.0) & (blue < 80.0)
    elif plate == "blue":
        pure = (blue > 150.0) & (red < 80.0) & (green < 80.0)
    else:
        pure = (red > 150.0) & (green < 80.0) & (blue < 80.0)
    return np.where(pure, 0.0, alpha)


def despilled(red, green, blue, plate):
    red = red.astype(np.float32).copy()
    green = green.astype(np.float32).copy()
    blue = blue.astype(np.float32).copy()
    if plate == "magenta":
        dist = np.abs(red - 255.0) + np.abs(green) + np.abs(blue - 255.0)
        spill = np.clip(np.minimum(red, blue) - green, 0.0, None)
        near = np.clip((150.0 - dist) / 70.0, 0.0, 1.0)
        amount = np.clip((spill - 8.0) / 50.0, 0.0, 1.0) * (0.25 + 0.75 * near)
        red -= spill * amount
        blue -= spill * amount
    elif plate == "green":
        green = np.minimum(green, np.maximum(red, blue))
    elif plate == "blue":
        blue = np.minimum(blue, np.maximum(red, green))
    else:
        red = np.minimum(red, np.maximum(green, blue))
    rgb = np.stack([red, green, blue], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def load_rgba(path):
    image = Image.open(path).convert("RGBA")
    return np.asarray(image)


def cells_of(image):
    height, width = image.shape[:2]
    if height == 0 or width % height != 0:
        return None
    count = width // height
    return [image[:, index * height : (index + 1) * height] for index in range(count)]


def components(mask):
    height, width = mask.shape
    seen = np.zeros((height, width), np.uint8)
    found = []
    ys, xs = np.where(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = 1
        pts = []
        while stack:
            cy, cx = stack.pop()
            pts.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if ny < 0 or nx < 0 or ny >= height or nx >= width or seen[ny, nx] or not mask[ny, nx]:
                    continue
                seen[ny, nx] = 1
                stack.append((ny, nx))
        found.append(pts)
    found.sort(key=len, reverse=True)
    return found


def touches_clear(alpha, y, x):
    """8-connected. Outside this cell counts as clear."""
    height, width = alpha.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if ny < 0 or nx < 0 or ny >= height or nx >= width or alpha[ny, nx] < 20:
                return True
    return False


def clear_touch_mask(alpha):
    clear = alpha < 20
    pad = np.pad(clear, 1, constant_values=True)
    height, width = clear.shape
    touch = np.zeros_like(clear)
    for dy in range(3):
        for dx in range(3):
            touch |= pad[dy : dy + height, dx : dx + width]
    return touch


def magenta_fringe(red, green, blue, alpha):
    apart = np.abs(red.astype(np.int16) - blue.astype(np.int16))
    return (
        (alpha > 40)
        & (red > 100)
        & (blue > 100)
        & (green < 48)
        & (red > green + 35)
        & (blue > green + 35)
        & (apart < 80)
    )


def green_fringe(red, green, blue, alpha):
    # Plate green, not a painted yellow-green glow. Glow keeps a high red channel.
    return (alpha > 40) & (green > 160) & (red < 90) & (blue < 90) & (green > red + 50) & (green > blue + 50)


def magenta_interior(red, green, blue, alpha):
    return (
        (alpha > 40)
        & (blue > 185)
        & (red > 150)
        & (green < 170)
        & (blue > green + 75)
        & (blue + 10 > red)
    )


def green_interior(red, green, blue, alpha):
    return (alpha > 40) & (green > 180) & (red < 100) & (blue < 100) & (green > red + 40) & (green > blue + 40)


def lilac_rim(red, green, blue, alpha):
    # Key-colored rim, tighter than purple armor. Armor green stays above this.
    apart = np.abs(red.astype(np.int16) - blue.astype(np.int16))
    return (
        (alpha > 40)
        & (red > 150)
        & (blue > 150)
        & (green < 60)
        & (red > green + 40)
        & (blue > green + 40)
        & (apart < 80)
    )


def foot_gap(cell):
    alpha = cell[:, :, 3] > 40
    counts = alpha.sum(axis=1)
    foot = None
    for y in range(len(counts) - 1, -1, -1):
        if counts[y] >= 3:
            foot = y
            break
    if foot is None:
        return cell.shape[0]
    return (cell.shape[0] - 1) - foot


def key_specks(red, green, blue, alpha, plate):
    """Leftover plate color. Magenta leftover is pink; a purple body is not."""
    peak = np.maximum(np.maximum(red, green), blue)
    if plate == "magenta":
        return (
            (alpha > 40)
            & (green < 24)
            & (red > 28)
            & (blue > 28)
            & (np.abs(red - blue) < 40)
            & (peak < 100)
        )
    if plate == "green":
        return (alpha > 40) & (green > 40) & (red < 30) & (blue < 30) & (green > red + 15) & (green > blue + 15)
    if plate == "blue":
        return (alpha > 40) & (blue > 40) & (red < 30) & (green < 30) & (blue > red + 15) & (blue > green + 15)
    return (alpha > 40) & (red > 40) & (green < 30) & (blue < 30) & (red > green + 15) & (red > blue + 15)


def check_cell(cell, margin, plate):
    """Return a set of problem codes for one frame. Interior totals are separate."""
    problems = set()
    red = cell[:, :, 0].astype(np.int16)
    green = cell[:, :, 1].astype(np.int16)
    blue = cell[:, :, 2].astype(np.int16)
    alpha = cell[:, :, 3].astype(np.int16)
    opaque = alpha > 40
    height, width = alpha.shape
    touch = clear_touch_mask(alpha)

    if (magenta_fringe(red, green, blue, alpha) & touch).any() or (green_fringe(red, green, blue, alpha) & touch).any():
        problems.add("edge-key")

    if margin <= 0:
        border = np.zeros_like(opaque)
        border[0, :] = True
        border[-1, :] = True
        border[:, 0] = True
        border[:, -1] = True
    else:
        border = np.ones_like(opaque)
        border[margin : height - margin, margin : width - margin] = False
    if (opaque & border).any():
        problems.add("clipped")

    # A baked shadow is its own dark blob, or pink specks that are not part of the body.
    # Armor crevices stay connected to the body and are not a shadow.
    peak = np.maximum(np.maximum(red, green), blue)
    sat = peak - np.minimum(np.minimum(red, green), blue)
    parts = components(opaque)
    if parts:
        main = np.zeros_like(opaque)
        for y, x in parts[0]:
            main[y, x] = True
        for part in parts[1:]:
            if len(part) < 20:
                continue
            ys = [p[0] for p in part]
            xs = [p[1] for p in part]
            cy = sum(ys) / len(ys)
            wide = max(xs) - min(xs) + 1
            tall = max(ys) - min(ys) + 1
            # A ground puddle is flat and sits under the feet. A detached toe is taller than it is wide.
            # A ground puddle is flat, neutral, and bigger than a chipped toe.
            if cy < height * 0.75 or wide < tall or wide < 12 or len(part) < 48:
                continue
            peaks = [int(peak[y, x]) for y, x in part]
            sats = [int(sat[y, x]) for y, x in part]
            if (sum(peaks) / len(peaks)) < 42 and (sum(sats) / len(sats)) < 16:
                problems.add("baked-shadow")
                break
        low = np.arange(height)[:, None] > int(height * 0.8)
        specks = key_specks(red, green, blue, alpha, plate) & ~main & low
        if int(specks.sum()) >= 8:
            problems.add("baked-shadow")

    # A hole eaten out of the body keeps a lilac or green rim. Open gaps between legs do not.
    solid = opaque
    outside = np.zeros_like(solid)
    stack = [(0, x) for x in range(width)] + [(height - 1, x) for x in range(width)]
    stack += [(y, 0) for y in range(height)] + [(y, width - 1) for y in range(height)]
    while stack:
        y, x = stack.pop()
        if y < 0 or x < 0 or y >= height or x >= width or outside[y, x] or solid[y, x]:
            continue
        outside[y, x] = True
        stack.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
    holes = ~solid & ~outside
    rim = lilac_rim(red, green, blue, alpha) | green_fringe(red, green, blue, alpha)
    for part in components(holes):
        if len(part) < 8:
            continue
        rim_hits = 0
        for y, x in part:
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and rim[ny, nx]:
                    rim_hits += 1
                    if rim_hits >= 6:
                        problems.add("body-holes")
                        break
            if "body-holes" in problems:
                break
        if "body-holes" in problems:
            break
    return problems


def interior_counts(cell):
    red = cell[:, :, 0].astype(np.int16)
    green = cell[:, :, 1].astype(np.int16)
    blue = cell[:, :, 2].astype(np.int16)
    alpha = cell[:, :, 3].astype(np.int16)
    touch = clear_touch_mask(alpha)
    magenta = magenta_interior(red, green, blue, alpha) & ~touch
    green_spill = green_interior(red, green, blue, alpha) & ~touch
    return int(magenta.sum()), int(green_spill.sum())


def rank_plates(red, green, blue):
    targets = {"green": (0, 255, 0), "blue": (0, 0, 255), "red": (255, 0, 0), "magenta": (255, 0, 255)}
    ranked = []
    for plate in KEYS:
        alpha = key_alpha(red.astype(np.float32), green.astype(np.float32), blue.astype(np.float32), plate)
        eaten = float((alpha < 0.85).mean())
        family = _family_fraction(red, green, blue, plate)
        kr, kg, kb = targets[plate]
        dist = np.abs(red - kr) + np.abs(green - kg) + np.abs(blue - kb)
        near = float(np.percentile(dist, 5))
        ranked.append((eaten, family, near, plate))
    safe = [row for row in ranked if row[0] <= 0.01 and row[1] <= 0.08]
    pool = safe if safe else ranked
    pool = sorted(pool, key=lambda row: row[2], reverse=True)
    return ranked, pool[0][3]


def infer_plate(image):
    opaque = image[:, :, 3] > 40
    if int(opaque.sum()) < 20:
        return "magenta"
    red = image[:, :, 0][opaque].astype(np.int16)
    green = image[:, :, 1][opaque].astype(np.int16)
    blue = image[:, :, 2][opaque].astype(np.int16)
    _ranked, plate = rank_plates(red, green, blue)
    return plate


def read_plate(path, image):
    """A sibling name.plate file is the plate the strip was keyed from. Otherwise infer it."""
    side = Path(path).with_suffix(".plate")
    if side.is_file():
        word = side.read_text().strip().split()[0]
        if word in KEYS:
            return word
    return infer_plate(image)


def check_image(image, foot_pad, margin, plate):
    frames = cells_of(image)
    if frames is None:
        return {"size"}, []
    problems = set()
    gaps = []
    magenta_inside = 0
    green_inside = 0
    for frame in frames:
        problems |= check_cell(frame, margin, plate)
        gaps.append(foot_gap(frame))
        magenta_n, green_n = interior_counts(frame)
        magenta_inside += magenta_n
        green_inside += green_n
    if magenta_inside > 8 or green_inside > 8:
        problems.add("interior-key")
    if gaps:
        if foot_pad is None:
            if max(gaps) > 8 or max(gaps) - min(gaps) > 1:
                problems.add("floating-feet")
        else:
            # One stray pixel under the planted row is normal. A real float is much larger.
            if any(gap < foot_pad or gap > foot_pad + 1 for gap in gaps):
                problems.add("floating-feet")
    return problems, gaps


def check_folder(folder, foot_pad, margin):
    failures = []
    paths = sorted(Path(folder).glob("*.png"))
    if not paths:
        return ["no strips in %s" % folder]
    for path in paths:
        image = load_rgba(path)
        plate = read_plate(path, image)
        problems, gaps = check_image(image, foot_pad, margin, plate)
        for code in sorted(problems):
            detail = ""
            if code == "floating-feet" and gaps:
                detail = " gaps=%s" % ",".join(str(g) for g in gaps)
            if code == "size":
                detail = " width not divisible by height"
            failures.append("%s %s%s" % (code, path.name, detail))
    return failures


def _family_fraction(red, green, blue, plate):
    if plate == "magenta":
        mask = (red > 80) & (blue > 80) & (green < red - 15) & (green < blue - 15) & (np.abs(red - blue) < 90)
    elif plate == "green":
        mask = (green > red + 15) & (green > blue + 15) & (green > 50)
    elif plate == "blue":
        mask = (blue > red + 20) & (blue > green + 20) & (blue > 60)
    else:
        mask = (red > green + 20) & (red > blue + 20) & (red > 60)
    return float(mask.mean())


def suggest(path):
    image = load_rgba(path)
    opaque = image[:, :, 3] > 40
    if int(opaque.sum()) < 20:
        raise SystemExit("no opaque pixels in %s" % path)
    red = image[:, :, 0][opaque].astype(np.int16)
    green = image[:, :, 1][opaque].astype(np.int16)
    blue = image[:, :, 2][opaque].astype(np.int16)
    ranked, picked = rank_plates(red, green, blue)
    pick = [row for row in ranked if row[3] == picked][0]
    print("plate %s  eaten %.3f  family %.3f  near %d" % (pick[3], pick[0], pick[1], int(pick[2])))
    for eaten, family, near, plate in sorted(ranked, key=lambda row: row[2], reverse=True):
        mark = "ok" if eaten <= 0.01 and family <= 0.08 else "reject"
        print("  %s %s eaten %.3f family %.3f near %d" % (mark, plate, eaten, family, int(near)))
    if not safe:
        print("warning: every plate eats the sprite or shares its hue")
    return pick[3]


def key_file(src, dest, plate):
    image = Image.open(src).convert("RGB")
    arr = np.asarray(image)
    red, green, blue = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    alpha = key_alpha(red, green, blue, plate)
    rgb = despilled(red, green, blue, plate)
    out = np.dstack([rgb, np.clip(alpha * 255.0, 0, 255).astype(np.uint8)])
    Image.fromarray(out, "RGBA").save(dest)


def _blob(draw, box, fill):
    draw.ellipse(box, fill=fill)


def _strip(frames):
    cell = frames[0].size[0]
    sheet = Image.new("RGBA", (cell * len(frames), cell), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.paste(frame, (index * cell, 0))
    return sheet


def _body(cell, top, bottom, color):
    image = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _blob(draw, (8, top, cell - 9, bottom), color)
    return image


def self_test():
    cell = 48
    body = (120, 80, 150, 255)
    cases = {}

    clean_a = _body(cell, 10, 44, body)
    clean_b = _body(cell, 10, 44, body)
    cases["clean"] = (_strip([clean_a, clean_b]), set())

    edge = _body(cell, 10, 44, body)
    ImageDraw.Draw(edge).point((40, 30), fill=(220, 20, 220, 255))
    cases["edge-key"] = (_strip([edge, _body(cell, 10, 44, body)]), {"edge-key"})

    interior = _body(cell, 10, 44, body)
    draw = ImageDraw.Draw(interior)
    for offset in range(12):
        draw.point((16 + offset, 20), fill=(190, 90, 210, 255))
    cases["interior-key"] = (_strip([interior, _body(cell, 10, 44, body)]), {"interior-key"})

    floating = _body(cell, 4, 20, body)
    cases["floating-feet"] = (_strip([floating, floating.copy()]), {"floating-feet"})

    uneven_a = _body(cell, 10, 44, body)
    uneven_b = _body(cell, 10, 41, body)
    cases["uneven-feet"] = (_strip([uneven_a, uneven_b]), {"floating-feet"})

    clipped = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    ImageDraw.Draw(clipped).ellipse((20, 10, 47, 44), fill=body)
    cases["clipped"] = (_strip([clipped, _body(cell, 10, 44, body)]), {"clipped"})

    shadow = _body(cell, 8, 40, body)
    ImageDraw.Draw(shadow).rectangle((12, 42, 36, 46), fill=(18, 16, 14, 255))
    cases["baked-shadow"] = (_strip([shadow, shadow.copy()]), {"baked-shadow"})

    pink = _body(cell, 10, 44, (160, 160, 165, 255))
    ImageDraw.Draw(pink).rectangle((1, 39, 5, 43), fill=(72, 10, 80, 255))
    cases["pink-specks"] = (_strip([pink, _body(cell, 10, 44, (160, 160, 165, 255))]), {"baked-shadow"}, "magenta")

    purple = _body(cell, 10, 44, body)
    ImageDraw.Draw(purple).rectangle((1, 39, 5, 43), fill=(33, 20, 42, 255))
    cases["purple-body"] = (_strip([purple, _body(cell, 10, 44, body)]), set(), "green")

    hole = _body(cell, 8, 44, body)
    draw = ImageDraw.Draw(hole)
    draw.rectangle((18, 16, 26, 24), fill=(0, 0, 0, 0))
    rim = (175, 52, 185, 255)
    draw.rectangle((17, 15, 27, 15), fill=rim)
    draw.rectangle((17, 25, 27, 25), fill=rim)
    draw.rectangle((17, 16, 17, 24), fill=rim)
    draw.rectangle((27, 16, 27, 24), fill=rim)
    cases["body-holes"] = (_strip([hole, _body(cell, 8, 44, body)]), {"body-holes"})

    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, item in cases.items():
            sheet, expected = item[0], item[1]
            plate_name = item[2] if len(item) > 2 else None
            path = root / ("%s.png" % name)
            sheet.save(path)
            if plate_name:
                path.with_suffix(".plate").write_text(plate_name + "\n")
            image = load_rgba(path)
            plate = read_plate(path, image)
            got, _gaps = check_image(image, None, 0, plate)
            got.discard("size")
            if got != expected:
                print("self-test %s expected %s got %s" % (name, sorted(expected), sorted(got)))
                failed = True
    if failed:
        return 1
    print("self-test ok")
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="Check sprite strips, suggest a key, or key a frame.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check")
    check.add_argument("folder")
    check.add_argument("--foot-pad", type=int, default=None, help="Require this many clear rows under the feet. Godot strips use 4.")
    check.add_argument("--margin", type=int, default=0, help="Fail when opaque pixels fall inside this many pixels of a cell edge.")

    suggest_p = sub.add_parser("suggest")
    suggest_p.add_argument("sprite")

    key_p = sub.add_parser("key")
    key_p.add_argument("src")
    key_p.add_argument("dest")
    key_p.add_argument("--plate", required=True, choices=KEYS)

    sub.add_parser("self-test")

    args = parser.parse_args(argv)
    if args.cmd == "self-test":
        return self_test()
    if args.cmd == "suggest":
        suggest(args.sprite)
        return 0
    if args.cmd == "key":
        key_file(args.src, args.dest, args.plate)
        return 0
    failures = check_folder(args.folder, args.foot_pad, args.margin)
    for line in failures:
        print(line)
    if failures:
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
