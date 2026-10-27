// SPDX-License-Identifier: LGPL-3.0-only
// Native FASTMEAN artwork is read only from the user's existing application.
// The distributable fallback is our separately authored helper mark.
using System;
using System.ComponentModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

internal static class AppBranding
{
    internal const string IconResourceName = "FastmeanRussianUI.Branding.Icon";

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr CreateIconFromResourceEx(byte[] bits, uint length,
        [MarshalAs(UnmanagedType.Bool)] bool icon, uint version, int width, int height, uint flags);
    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DestroyIcon(IntPtr icon);

    private static Icon ReadEmbeddedIcon(Stream stream, int size)
    {
        // Framework 4's Icon(Stream, Size) treats a 256px directory width byte
        // of zero as zero. Select our frame explicitly so the large PNG frame
        // remains usable without a graphics SDK or a temporary icon file.
        using (BinaryReader reader = new BinaryReader(stream))
        {
            if (reader.ReadUInt16() != 0 || reader.ReadUInt16() != 1)
                throw new InvalidDataException("The helper branding resource is not an ICO.");
            int count = reader.ReadUInt16();
            if (count < 1 || count > 16) throw new InvalidDataException("Invalid helper icon frame count.");
            uint selectedOffset = 0, selectedLength = 0;
            int selectedScore = Int32.MaxValue;
            for (int index = 0; index < count; index++)
            {
                int width = reader.ReadByte();
                int height = reader.ReadByte();
                if (width == 0) width = 256;
                if (height == 0) height = 256;
                reader.ReadUInt16(); // Color count and reserved byte.
                reader.ReadUInt16(); // Color planes.
                reader.ReadUInt16(); // Bits per pixel.
                uint length = reader.ReadUInt32();
                uint offset = reader.ReadUInt32();
                if (width != height || offset < 6 + count * 16 ||
                    length > 4 * 1024 * 1024 || (long)offset + length > stream.Length)
                    throw new InvalidDataException("Invalid helper icon frame bounds.");
                int score = width >= size ? width - size : 256 + (size - width) * 2;
                if (score < selectedScore)
                {
                    selectedScore = score;
                    selectedOffset = offset;
                    selectedLength = length;
                }
            }
            stream.Position = selectedOffset;
            byte[] bits = reader.ReadBytes((int)selectedLength);
            if (bits.Length != selectedLength) throw new EndOfStreamException("Incomplete helper icon frame.");
            IntPtr handle = CreateIconFromResourceEx(bits, selectedLength, true, 0x00030000, size, size, 0);
            if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                using (Icon borrowed = Icon.FromHandle(handle)) return (Icon)borrowed.Clone();
            }
            finally { DestroyIcon(handle); }
        }
    }

    private static bool IsNativeExecutable(string target)
    {
        if (String.IsNullOrWhiteSpace(target) ||
            !String.Equals(Path.GetFileName(target), "Fastmean.exe", StringComparison.OrdinalIgnoreCase))
            return false;
        using (FileStream file = new FileStream(target, FileMode.Open, FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete))
            return file.ReadByte() == 'M' && file.ReadByte() == 'Z';
    }

    // The caller owns the returned Icon and must dispose it after its form closes.
    internal static Icon LoadIcon(string nativeTarget, int size)
    {
        if (size < 16 || size > 256) throw new ArgumentOutOfRangeException("size");
        try
        {
            if (IsNativeExecutable(nativeTarget))
                using (Icon native = Icon.ExtractAssociatedIcon(nativeTarget))
                    if (native != null) return new Icon(native, new Size(size, size));
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        catch (ArgumentException) { }
        catch (Win32Exception) { }
        catch (ExternalException) { }

        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(IconResourceName))
        {
            if (stream != null)
                return ReadEmbeddedIcon(stream, size);
        }
        // A broken/custom build must not turn a successful installation into an
        // error merely because it omitted its optional display-only resource.
        return (Icon)SystemIcons.Application.Clone();
    }

    // The caller owns the returned image independently of the Icon and form.
    internal static Bitmap LoadHeaderImage(string nativeTarget, int size)
    {
        using (Icon icon = LoadIcon(nativeTarget, size))
        {
            Bitmap image = new Bitmap(size, size);
            using (Graphics graphics = Graphics.FromImage(image))
            {
                graphics.Clear(Color.Transparent);
                graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
                graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
                graphics.DrawIcon(icon, new Rectangle(0, 0, size, size));
            }
            return image;
        }
    }

    internal static string PreferredShortcutIcon(string nativeTarget, string helper)
    {
        try { if (IsNativeExecutable(nativeTarget)) return nativeTarget; }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        catch (ArgumentException) { }
        return helper;
    }
}
