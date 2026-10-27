# Helper artwork

`helper-icon.svg` is original LGPL-3.0-only artwork for this optional helper:
an amplifier symbol on a red tile and a Russian tricolor cue. It is not the
proprietary FASTMEAN logo and contains no extracted native application pixels.

`make_icon.py` rasterizes that small, reviewed SVG subset using only Python's
standard library. The build generates 16, 24, 32, 48, 64, 128 and 256 pixel ICO
frames in its private staging folder. Small frames use 32-bit DIBs; the 256
pixel frame uses PNG. No fonts, graphics SDK or downloaded artwork is required.

The installer may read the icon from an already installed `Fastmean.exe` for
its window and header at runtime. A desktop shortcut can likewise reference
that existing executable's icon. Those native pixels are never included in
the helper's source bundle, payload or downloadable EXE.
