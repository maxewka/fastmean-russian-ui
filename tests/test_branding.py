"""Original distributable icon resources and runtime-only native branding.

The managed harness reads only its own generated resource and disposable text
fixtures. It never starts FASTMEAN or loads the locale-emulation runtime.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib


PROJECT = Path(__file__).resolve().parents[1]
POLICY_ERRORS = {4551, 577, 1260}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ICON = load_module("helper_icon_for_test", PROJECT / "assets/make_icon.py")


def ico_entries(data: bytes) -> list[tuple[int, bytes]]:
    reserved, kind, count = struct.unpack_from("<HHH", data)
    if (reserved, kind) != (0, 1):
        raise ValueError("Not a Windows icon directory")
    result = []
    expected_offset = 6 + count * 16
    for index in range(count):
        width, height, colors, zero, planes, bits, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
        if width != height or colors or zero or planes != 1 or bits != 32 or offset != expected_offset:
            raise ValueError("Invalid icon frame directory")
        frame = data[offset:offset + length]
        if len(frame) != length:
            raise ValueError("Truncated icon frame")
        result.append((width or 256, frame))
        expected_offset += length
    if expected_offset != len(data):
        raise ValueError("Unexpected bytes after icon frames")
    return result


HARNESS = r'''
using System;
using System.Drawing;
using System.IO;
using System.Reflection;

internal static class BrandingHarness
{
    private static int Main(string[] args)
    {
        string fixture = Path.Combine(args[0], "Fastmean.exe");
        File.WriteAllText(fixture, "nonexecutable fixture, not native FASTMEAN");
        foreach (int size in new int[] { 16, 24, 32, 48, 64, 128, 256 })
            using (Icon icon = AppBranding.LoadIcon(fixture, size))
            using (Bitmap bitmap = icon.ToBitmap())
                if (icon.Width != size || icon.Height != size || bitmap.GetPixel(0, 0).A != 0)
                    throw new InvalidDataException("Embedded icon frame failed at " + size + ": " +
                        icon.Width + "x" + icon.Height + ", corner alpha=" + bitmap.GetPixel(0, 0).A);
        using (Bitmap header = AppBranding.LoadHeaderImage(null, 64))
            if (header.Width != 64 || header.Height != 64 || header.GetPixel(0, 0).A != 0)
                throw new InvalidDataException("Header image failed");
        string executable = Assembly.GetExecutingAssembly().Location;
        using (Icon associated = Icon.ExtractAssociatedIcon(executable))
        using (Bitmap bitmap = associated.ToBitmap())
        {
            Color mark = bitmap.GetPixel(bitmap.Width / 2, bitmap.Height / 8);
            if (mark.R < 150 || mark.G > 100 || mark.B > 100)
                throw new InvalidDataException("The Win32 EXE icon is not the original red helper mark");
        }
        if (AppBranding.PreferredShortcutIcon(fixture, executable) != executable)
            throw new InvalidDataException("Nonexecutable native fixture must fall back to the helper icon");
        Console.WriteLine("{\"ok\":true,\"sizes_checked\":7,\"native_application_started\":false}");
        return 0;
    }
}
'''


class BrandingSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (PROJECT / "assets/helper-icon.svg").read_bytes()
        cls.icon = ICON.icon_bytes(cls.source)

    def test_original_svg_has_no_embedded_or_external_native_artwork(self):
        root = ET.fromstring(self.source)
        self.assertEqual(root.attrib["viewBox"], "0 0 64 64")
        self.assertTrue(all(element.tag.rsplit("}", 1)[-1] in {"title", "rect", "polygon", "line"}
                            for element in root))
        self.assertIn(b"SPDX-License-Identifier: LGPL-3.0-only", self.source)
        self.assertIn(b"not the proprietary FASTMEAN logo", self.source)

    def test_icon_contains_all_windows_sizes_with_valid_dib_and_png_frames(self):
        entries = ico_entries(self.icon)
        self.assertEqual([size for size, _ in entries], list(ICON.SIZES))
        for size, frame in entries:
            with self.subTest(size=size):
                if size == 256:
                    self.assertTrue(frame.startswith(b"\x89PNG\r\n\x1a\n"))
                    offset, compressed = 8, bytearray()
                    while offset < len(frame):
                        length = struct.unpack_from(">I", frame, offset)[0]
                        name = frame[offset + 4:offset + 8]
                        payload = frame[offset + 8:offset + 8 + length]
                        checksum = struct.unpack_from(">I", frame, offset + 8 + length)[0]
                        self.assertEqual(checksum, zlib.crc32(name + payload) & 0xFFFFFFFF)
                        if name == b"IHDR":
                            self.assertEqual(struct.unpack(">IIBBBBB", payload), (256, 256, 8, 6, 0, 0, 0))
                        if name == b"IDAT":
                            compressed.extend(payload)
                        offset += 12 + length
                    rows = zlib.decompress(compressed)
                    self.assertEqual(len(rows), size * (1 + size * 4))
                    self.assertEqual(rows[:5], b"\0\0\0\0\0")
                else:
                    header, width, doubled_height, planes, bits = struct.unpack_from("<IiiHH", frame)
                    self.assertEqual((header, width, doubled_height, planes, bits), (40, size, size * 2, 1, 32))
                    mask_stride = ((size + 31) // 32) * 4
                    self.assertEqual(len(frame), 40 + size * size * 4 + mask_stride * size)
                    self.assertEqual(frame[40:44], b"\0\0\0\0")
                    self.assertTrue(frame[40 + size * size * 4] & 0x80)

    def test_artwork_stays_readable_at_smallest_and_largest_sizes(self):
        for size in (16, 256):
            rgba = ICON.render_rgba(self.source, size)
            colors = {tuple(rgba[index:index + 4]) for index in range(0, len(rgba), 4)}
            with self.subTest(size=size):
                self.assertIn((197, 44, 53, 255), colors)   # Red helper tile.
                self.assertIn((255, 255, 255, 255), colors)  # White amplifier symbol.
                self.assertIn((39, 93, 168, 255), colors)   # Russian tricolor cue.
                self.assertIn((0, 0, 0, 0), colors)

    def test_source_bundle_contains_vector_generator_and_branding_code_only(self):
        build = load_module("branding_build_for_test", PROJECT / "build.py")
        sources = build.own_sources()
        for path in ("assets/helper-icon.svg", "assets/make_icon.py", "assets/README.md",
                     "src/AppBranding.cs", "tests/test_branding.py"):
            self.assertIn(path, sources)
        self.assertFalse(any(name.startswith("assets/") and name.endswith((".ico", ".png", ".exe", ".dll"))
                             for name in sources))
        code = (PROJECT / "build.py").read_text(encoding="utf-8")
        self.assertEqual(code.count('"/win32icon:" + str(icon_path)'), 2)
        self.assertIn('str(icon_path) + ",FastmeanRussianUI.Branding.Icon"', code)


@unittest.skipUnless(os.name == "nt", "Windows .NET Framework icon extraction is required")
class BrandingWindowsTests(unittest.TestCase):
    def test_managed_fallback_frames_and_compiled_exe_icon_are_real(self):
        compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        if not compiler.is_file():
            self.skipTest("Existing .NET Framework compiler is not available")
        with tempfile.TemporaryDirectory(prefix="fastmean-branding-test-") as temporary:
            folder = Path(temporary)
            icon = folder / "helper.ico"
            icon.write_bytes(ICON.icon_bytes())
            harness = folder / "BrandingHarness.cs"
            harness.write_text(HARNESS, encoding="utf-8")
            executable = folder / "BrandingHarness.exe"
            try:
                compiled = subprocess.run([str(compiler), "/nologo", "/target:exe", "/platform:x86",
                    "/reference:System.Drawing.dll", "/out:" + str(executable),
                    "/win32icon:" + str(icon), "/resource:" + str(icon) + ",FastmeanRussianUI.Branding.Icon",
                    str(harness), str(PROJECT / "src/AppBranding.cs")], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                checked = subprocess.run([str(executable), str(folder)], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            except OSError as error:
                if getattr(error, "winerror", None) in POLICY_ERRORS:
                    self.skipTest("Windows execution policy blocked the owned test harness: " + str(error))
                raise
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(json.loads(checked.stdout),
                {"ok": True, "sizes_checked": 7, "native_application_started": False})


if __name__ == "__main__":
    unittest.main()
