#!/usr/bin/env python3
"""Sprite check for a new Godot game.

Fails on a painted checkerboard, a near-white plate, a chroma-green fringe
next to transparency, a missing file, or a canvas that is not the expected
size. Thresholds match the Lunar Age boot audit. The game's loader should
push_error the same messages: art missing, art size, art green, art checker.

Usage:
  check_sprites.py ROOT --size assets/sprites/units/hero.png=96x96
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path


def _paeth(a: int, b: int, c: int) -> int:
	p = a + b - c
	pa = abs(p - a)
	pb = abs(p - b)
	pc = abs(p - c)
	if pa <= pb and pa <= pc:
		return a
	if pb <= pc:
		return b
	return c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytes:
	rows = []
	i = 0
	prev = bytearray(stride)
	for _y in range(height):
		filt = raw[i]
		i += 1
		row = bytearray(raw[i : i + stride])
		i += stride
		if filt == 1:
			for x in range(stride):
				left = row[x - bpp] if x >= bpp else 0
				row[x] = (row[x] + left) & 255
		elif filt == 2:
			for x in range(stride):
				row[x] = (row[x] + prev[x]) & 255
		elif filt == 3:
			for x in range(stride):
				left = row[x - bpp] if x >= bpp else 0
				row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
		elif filt == 4:
			for x in range(stride):
				left = row[x - bpp] if x >= bpp else 0
				up_left = prev[x - bpp] if x >= bpp else 0
				row[x] = (row[x] + _paeth(left, prev[x], up_left)) & 255
		elif filt != 0:
			raise ValueError("bad png filter %s" % filt)
		prev = row
		rows.append(row)
	return b"".join(rows)


def read_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
	data = path.read_bytes()
	if data[:8] != b"\x89PNG\r\n\x1a\n":
		raise ValueError("not a png")
	pos = 8
	width = height = 0
	bit_depth = color_type = interlace = 0
	idat = bytearray()
	while pos < len(data):
		length = struct.unpack(">I", data[pos : pos + 4])[0]
		kind = data[pos + 4 : pos + 8]
		chunk = data[pos + 8 : pos + 8 + length]
		pos += 12 + length
		if kind == b"IHDR":
			width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(">IIBBBBB", chunk)
		elif kind == b"IDAT":
			idat.extend(chunk)
		elif kind == b"IEND":
			break
	if interlace != 0 or bit_depth != 8 or color_type not in (2, 6):
		raise ValueError("png must be non-interlaced 8-bit RGB or RGBA")
	channels = 4 if color_type == 6 else 3
	raw = zlib.decompress(bytes(idat))
	stride = width * channels
	plain = _unfilter(raw, height, stride, channels)
	pixels: list[tuple[int, int, int, int]] = []
	for y in range(height):
		row = plain[y * stride : (y + 1) * stride]
		for x in range(width):
			o = x * channels
			r, g, b = row[o], row[o + 1], row[o + 2]
			a = row[o + 3] if channels == 4 else 255
			pixels.append((r, g, b, a))
	return width, height, pixels


def _at(pixels: list[tuple[int, int, int, int]], width: int, x: int, y: int) -> tuple[int, int, int, int]:
	return pixels[y * width + x]


def green_edge(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bool:
	for y in range(height):
		for x in range(width):
			red, green, blue, alpha = _at(pixels, width, x, y)
			if not (alpha > 40 and green > red + 10 and green > blue + 12 and red < 100 and (red - blue) < 40 and green > 18):
				continue
			near = False
			for yy in range(y - 8, y + 9):
				for xx in range(x - 8, x + 9):
					if xx < 0 or yy < 0 or xx >= width or yy >= height or _at(pixels, width, xx, yy)[3] < 20:
						near = True
						break
				if near:
					break
			if near:
				return True
	return False


def white_plate(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bool:
	count = 0
	for red, green, blue, alpha in pixels:
		hi = max(red, green, blue)
		lo = min(red, green, blue)
		if alpha > 200 and hi - lo < 15 and (red + green + blue) // 3 > 200:
			count += 1
	return count * 100 > width * height * 12


def checker_period(width: int, height: int, pixels: list[tuple[int, int, int, int]], period: int) -> bool:
	sum0 = sum1 = sq0 = sq1 = 0.0
	n0 = n1 = 0
	for y in range(height):
		for x in range(width):
			red, green, blue, alpha = _at(pixels, width, x, y)
			if alpha <= 80:
				continue
			hi = max(red, green, blue)
			lo = min(red, green, blue)
			if hi - lo >= 18:
				continue
			lum = (red + green + blue) / 3.0
			cell = (x // period) + (y // period)
			if cell % 2 == 0:
				sum0 += lum
				sq0 += lum * lum
				n0 += 1
			else:
				sum1 += lum
				sq1 += lum * lum
				n1 += 1
	if n0 < 64 or n1 < 64:
		return False
	mean0 = sum0 / n0
	mean1 = sum1 / n1
	std0 = max(sq0 / n0 - mean0 * mean0, 0.0) ** 0.5
	std1 = max(sq1 / n1 - mean1 * mean1, 0.0) ** 0.5
	hi_mean, lo_mean, hi_std, lo_std = mean0, mean1, std0, std1
	if mean1 > mean0:
		hi_mean, lo_mean, hi_std, lo_std = mean1, mean0, std1, std0
	return hi_std < 14.0 and lo_std < 14.0 and (hi_mean - lo_mean) > 45.0 and hi_mean > 185.0 and lo_mean > 90.0


def checker(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bool:
	if white_plate(width, height, pixels):
		return True
	return any(checker_period(width, height, pixels, period) for period in (4, 8, 16))


def parse_size(text: str) -> tuple[str, int, int]:
	path, _, size = text.partition("=")
	w_text, _, h_text = size.lower().partition("x")
	return path, int(w_text), int(h_text)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("root", type=Path)
	parser.add_argument("--size", action="append", default=[], help="relative path=WxH")
	args = parser.parse_args()
	root = args.root.resolve()
	failed = False
	for item in args.size:
		rel, width, height = parse_size(item)
		path = root / rel
		if not path.is_file():
			print("art missing %s" % rel)
			failed = True
			continue
		try:
			got_w, got_h, pixels = read_png(path)
		except (OSError, ValueError) as exc:
			print("art image %s (%s)" % (rel, exc))
			failed = True
			continue
		if got_w != width or got_h != height:
			print("art size %s" % rel)
			failed = True
		if green_edge(got_w, got_h, pixels):
			print("art green %s" % rel)
			failed = True
		if checker(got_w, got_h, pixels):
			print("art checker %s" % rel)
			failed = True
	return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
