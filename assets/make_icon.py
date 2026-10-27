"""SPDX-License-Identifier: LGPL-3.0-only

Render our original SVG helper mark into a deterministic Windows ICO.
Only the deliberately small rect/polygon/line SVG subset used by this asset
is supported. No native FASTMEAN executable, icon, font or image is read.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import math
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib


SOURCE = Path(__file__).with_name("helper-icon.svg")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _color(value: str | None) -> tuple[int, int, int] | None:
    if value in (None, "none"):
        return None
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError("Only explicit six-digit SVG colors are supported")
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def _distance_squared(x: float, y: float, a: tuple[float, float],
                      b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    fraction = 0 if not length else max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length))
    return (x - a[0] - fraction * dx) ** 2 + (y - a[1] - fraction * dy) ** 2


def _shapes(source: bytes) -> list[tuple]:
    root = ET.fromstring(source)
    if root.get("viewBox") != "0 0 64 64":
        raise ValueError("The icon SVG must retain its 64 by 64 viewBox")
    result = []
    for element in root:
        tag = element.tag.rsplit("}", 1)[-1]
        attributes = element.attrib
        if tag == "title":
            continue
        if tag == "rect":
            result.append((tag, _color(attributes.get("fill")), tuple(float(attributes.get(name, 0))
                for name in ("x", "y", "width", "height", "rx"))))
        elif tag in {"line", "polygon"}:
            if tag == "line":
                points = [(float(attributes["x1"]), float(attributes["y1"])),
                          (float(attributes["x2"]), float(attributes["y2"]))]
            else:
                if attributes.get("fill") != "none":
                    raise ValueError("Only outline polygons are supported")
                points = [tuple(map(float, point.split(","))) for point in attributes["points"].split()]
                points.append(points[0])
            radius_squared = (float(attributes["stroke-width"]) / 2) ** 2
            result.append(("stroke", _color(attributes["stroke"]), (points, radius_squared)))
        else:
            raise ValueError("Unsupported icon SVG element: " + tag)
    return result


def _contains(shape: tuple, x: float, y: float) -> bool:
    if shape[0] == "rect":
        left, top, width, height, radius = shape[2]
        if not (left <= x <= left + width and top <= y <= top + height):
            return False
        if not radius:
            return True
        nearest_x = max(left + radius, min(left + width - radius, x))
        nearest_y = max(top + radius, min(top + height - radius, y))
        return (x - nearest_x) ** 2 + (y - nearest_y) ** 2 <= radius ** 2
    points, radius_squared = shape[2]
    return any(_distance_squared(x, y, first, second) <= radius_squared
               for first, second in zip(points, points[1:]))


@lru_cache(maxsize=16)
def render_rgba(source: bytes, size: int) -> bytes:
    """Return straight-alpha RGBA, averaging a fixed 3x3 grid per pixel."""
    if size not in SIZES:
        raise ValueError("Unsupported Windows icon frame size")
    shapes = list(reversed(_shapes(source)))
    output = bytearray()
    step = 64 / size
    offsets = (1 / 6, 1 / 2, 5 / 6)
    for pixel_y in range(size):
        for pixel_x in range(size):
            red = green = blue = count = 0
            for sample_y in offsets:
                for sample_x in offsets:
                    x, y = (pixel_x + sample_x) * step, (pixel_y + sample_y) * step
                    for shape in shapes:
                        if _contains(shape, x, y):
                            color = shape[1]
                            if color is not None:
                                red += color[0]
                                green += color[1]
                                blue += color[2]
                                count += 1
                            break
            output.extend((round(red / count), round(green / count), round(blue / count), round(count * 255 / 9))
                          if count else (0, 0, 0, 0))
    return bytes(output)


def _chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)


def png_frame(size: int, rgba: bytes) -> bytes:
    rows = b"".join(b"\0" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b""))


def _dib_frame(size: int, rgba: bytes) -> bytes:
    color_rows = bytearray()
    mask_rows = bytearray()
    mask_stride = math.ceil(size / 32) * 4
    for y in range(size - 1, -1, -1):
        mask = bytearray(mask_stride)
        for x in range(size):
            index = (y * size + x) * 4
            red, green, blue, alpha = rgba[index:index + 4]
            color_rows.extend((blue, green, red, alpha))
            if alpha == 0:
                mask[x // 8] |= 1 << (7 - x % 8)
        mask_rows.extend(mask)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(color_rows), 0, 0, 0, 0)
    return header + color_rows + mask_rows


@lru_cache(maxsize=4)
def icon_bytes(source: bytes | None = None) -> bytes:
    if source is None:
        source = SOURCE.read_bytes()
    frames = [png_frame(size, render_rgba(source, size)) if size == 256
              else _dib_frame(size, render_rgba(source, size)) for size in SIZES]
    offset = 6 + len(frames) * 16
    directory = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    for size, frame in zip(SIZES, frames):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(frame), offset))
        offset += len(frame)
    return bytes(directory) + b"".join(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(icon_bytes())


if __name__ == "__main__":
    main()
