// SPDX-License-Identifier: LGPL-3.0-only
// Optional, non-elevating per-process Russian locale helper for FASTMEAN.
// Native ABI adapted from xupefei/Locale-Emulator v2.5.0.1 LEProc/LoaderWrapper.cs
// and LEProc/LERegistryRedirector.cs, licensed LGPL-3.0.
// https://github.com/xupefei/Locale-Emulator/tree/v2.5.0.1
// Modified 2026-10-27: file-association arguments and no-launch diagnostics.
// Two exact file-type label registry READ overrides exist in process memory only.
// No updater, installer, registry writes or UAC fallback.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

internal static class FastmeanRuRunner
{
    [StructLayout(LayoutKind.Sequential)]
    private struct TimeFields
    {
        internal ushort Year, Month, Day, Hour, Minute, Second, Milliseconds, Weekday;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct RtlTimeZone
    {
        internal int Bias;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 64)] internal byte[] StandardName;
        internal TimeFields StandardDate;
        internal int StandardBias;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 64)] internal byte[] DaylightName;
        internal TimeFields DaylightDate;
        internal int DaylightBias;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Leb
    {
        internal uint AnsiCodePage, OemCodePage, LocaleID, DefaultCharset, HookUILanguageAPI;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 64)] internal byte[] DefaultFaceName;
        internal RtlTimeZone Timezone;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SystemTime
    {
        internal ushort Year, Month, Weekday, Day, Hour, Minute, Second, Milliseconds;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NativeTimeZone
    {
        internal int Bias;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] internal string StandardName;
        internal SystemTime StandardDate;
        internal int StandardBias;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] internal string DaylightName;
        internal SystemTime DaylightDate;
        internal int DaylightBias;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo
    {
        internal int cb;
        internal string reserved, desktop, title;
        internal uint x, y, xSize, ySize, xCountChars, yCountChars, fillAttribute, flags;
        internal short showWindow, reserved2Bytes;
        internal IntPtr reserved2, stdin, stdout, stderr;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation
    {
        internal IntPtr process, thread;
        internal uint processId, threadId;
    }

    [DllImport("LoaderDll.dll", CharSet = CharSet.Unicode)]
    private static extern uint LeCreateProcess(IntPtr leb, string applicationName,
        string commandLine, string currentDirectory, uint creationFlags,
        ref StartupInfo startupInfo, out ProcessInformation processInformation,
        IntPtr processAttributes, IntPtr threadAttributes, IntPtr environment, IntPtr token);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern uint GetTimeZoneInformation(out NativeTimeZone timezone);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    private static TimeFields ConvertTime(SystemTime value)
    {
        return new TimeFields { Year = value.Year, Month = value.Month, Day = value.Day,
            Hour = value.Hour, Minute = value.Minute, Second = value.Second,
            Milliseconds = value.Milliseconds, Weekday = value.Weekday };
    }

    private static byte[] NameBytes(string value)
    {
        byte[] result = new byte[64];
        byte[] source = Encoding.Unicode.GetBytes(value ?? String.Empty);
        Array.Copy(source, result, Math.Min(source.Length, 62));
        return result;
    }

    // Official LERegistryRedirector x86-to-64 ABI uses 64-bit *relative offsets*,
    // not host pointers: LEB256, UInt64 count, then two 128-byte entry pairs.
    // REGISTRY_ENTRY64 offsets: Root0, SubKey8, ValueName24, Type40, Data48,
    // DataSize56. UNICODE_STRING64 is {ushort Length0, MaximumLength2,
    // padding4, Int64 Buffer8}; the two sizes exclude the NUL terminator.
    // These literal registry paths are root-relative, have no wildcards and
    // target only the unnamed value. Core resolves actual native full paths
    // read-only with KEY_QUERY_VALUE and compares case-insensitively.
    private static void PutUInt16(List<byte> bytes, int index, ushort value)
    {
        byte[] valueBytes = BitConverter.GetBytes(value);
        for (int i = 0; i < valueBytes.Length; i++) bytes[index + i] = valueBytes[i];
    }

    private static void PutUInt32(List<byte> bytes, int index, uint value)
    {
        byte[] valueBytes = BitConverter.GetBytes(value);
        for (int i = 0; i < valueBytes.Length; i++) bytes[index + i] = valueBytes[i];
    }

    private static void PutUInt64(List<byte> bytes, int index, ulong value)
    {
        byte[] valueBytes = BitConverter.GetBytes(value);
        for (int i = 0; i < valueBytes.Length; i++) bytes[index + i] = valueBytes[i];
    }

    private static ulong AppendString(List<byte> bytes, string value, out ushort byteLength)
    {
        byte[] utf16 = Encoding.Unicode.GetBytes(value);
        byteLength = checked((ushort)utf16.Length);
        ulong relativeOffset = checked((ulong)bytes.Count);
        bytes.AddRange(utf16);
        bytes.Add(0);
        bytes.Add(0);
        return relativeOffset;
    }

    private static void PutUnicodeString64(List<byte> bytes, int index,
        ushort byteLength, ulong relativeOffset)
    {
        PutUInt16(bytes, index, byteLength);
        PutUInt16(bytes, index + 2, byteLength);
        PutUInt64(bytes, index + 8, relativeOffset);
    }

    private static void PutTypeLabelEntry(List<byte> bytes, int pairOffset,
        ulong root, string subkey)
    {
        ushort keyLength, nameLength, dataLength;
        ulong keyOffset = AppendString(bytes, subkey, out keyLength);
        ulong nameOffset = AppendString(bytes, String.Empty, out nameLength);
        // Include the UTF-16 terminator in REG_SZ DataSize, as required by
        // Windows query-value semantics. The helper appends that terminator.
        ulong dataOffset = AppendString(bytes, "\u0421\u0445\u0435\u043c\u0430 FASTMEAN", out dataLength);
        ulong dataSize = checked((ulong)dataLength + 2UL);
        if (keyOffset < 520UL || nameOffset < 520UL || dataOffset < 520UL ||
            dataOffset + dataSize > (ulong)bytes.Count)
            throw new InvalidOperationException("Registry read override has an invalid relative offset.");

        // Upstream uses Original=Redirected. Original key/default value forms
        // the exact query matcher; Redirected.Data supplies the memory result.
        for (int half = 0; half < 2; half++)
        {
            int entry = pairOffset + half * 64;
            PutUInt64(bytes, entry, root);
            PutUnicodeString64(bytes, entry + 8, keyLength, keyOffset);
            PutUnicodeString64(bytes, entry + 24, nameLength, nameOffset);
            PutUInt32(bytes, entry + 40, 1U); // REG_SZ
            PutUInt64(bytes, entry + 48, dataOffset);
            PutUInt64(bytes, entry + 56, dataSize);
        }
    }

    private static byte[] BuildTypeLabelReadOverrides(int lebSize)
    {
        if (lebSize != 256 || !BitConverter.IsLittleEndian)
            throw new InvalidOperationException("Unexpected registry-read override ABI.");
        // Fixed header and table are fully zeroed, including native padding.
        List<byte> bytes = new List<byte>(new byte[lebSize + 8 + 2 * 128]);
        PutUInt64(bytes, lebSize, 2UL);
        PutTypeLabelEntry(bytes, 264, 0x80000001UL, @"Software\Classes\FASTMEAN.Scheme");
        PutTypeLabelEntry(bytes, 392, 0x80000000UL, @"FASTMEAN.Scheme");
        // Upstream LoaderDll adds its LEB prefix and entry-table size again
        // when calculating the native block copy length. Reserve zero guard
        // bytes so even that conservative copy stays inside this allocation.
        // No string/data offsets point into this unused guard region.
        bytes.AddRange(new byte[lebSize + 2 * 128]);
        return bytes.ToArray();
    }

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--check") return CheckOnly(args);
        return RunNative(args);
    }

    private static FastmeanLaunchPaths.Request ResolveRequest(string[] args)
    {
        if (IntPtr.Size != 4)
            throw new InvalidOperationException("This launcher must be compiled as x86.");
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        FastmeanLaunchPaths.Request request = FastmeanLaunchPaths.Resolve(args, baseDirectory,
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData));
        if (!File.Exists(Path.Combine(baseDirectory, "LoaderDll.dll")) ||
            !File.Exists(Path.Combine(baseDirectory, "LocaleEmulator.dll")))
            throw new FileNotFoundException("LoaderDll.dll and LocaleEmulator.dll must be next to the launcher.");
        return request;
    }

    private static int CheckOnly(string[] args)
    {
        // This is a Windows-subsystem EXE. Setting OutputEncoding requires a
        // console, while a redirected stdout pipe is valid without one.
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true });
        try
        {
            string[] remaining = new string[args.Length - 1];
            Array.Copy(args, 1, remaining, 0, remaining.Length);
            FastmeanLaunchPaths.Request request = ResolveRequest(remaining);
            Console.WriteLine("{\"ok\":true,\"target\":" + JsonString(request.Target) +
                ",\"document\":" + JsonString(request.Document) +
                ",\"native_launch_started\":false,\"windows_settings_changed\":false}");
            return 0;
        }
        catch (Exception error)
        {
            Console.WriteLine("{\"ok\":false,\"error\":" + JsonString(error.Message) +
                ",\"native_launch_started\":false}");
            return 1;
        }
    }

    // Do not JIT native loader calls while performing a --check request.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int RunNative(string[] args)
    {
        IntPtr block = IntPtr.Zero;
        try
        {
            string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
            FastmeanLaunchPaths.Request request = ResolveRequest(args);
            string target = request.Target;
            string document = request.Document;
            // Affects only the launcher process and its DLL search path.
            Directory.SetCurrentDirectory(baseDirectory);

            NativeTimeZone nativeZone;
            if (GetTimeZoneInformation(out nativeZone) == UInt32.MaxValue)
                throw new InvalidOperationException("Could not read the current process timezone.");

            Leb data = new Leb {
                AnsiCodePage = 1251, OemCodePage = 866, LocaleID = 1049,
                DefaultCharset = 204, HookUILanguageAPI = 0,
                DefaultFaceName = new byte[64],
                Timezone = new RtlTimeZone {
                    Bias = nativeZone.Bias,
                    StandardName = NameBytes(nativeZone.StandardName),
                    StandardDate = ConvertTime(nativeZone.StandardDate),
                    StandardBias = nativeZone.StandardBias,
                    DaylightName = NameBytes(nativeZone.DaylightName),
                    DaylightDate = ConvertTime(nativeZone.DaylightDate),
                    DaylightBias = nativeZone.DaylightBias
                }
            };
            int size = Marshal.SizeOf(typeof(Leb));
            if (size != 256)
                throw new InvalidOperationException("Unexpected Locale Emulator ABI size: " + size);
            // Supply only the two exact file-type label reads.
            // There is no registry API call or persistent registry write here.
            byte[] localReadOverrides = BuildTypeLabelReadOverrides(size);
            block = Marshal.AllocHGlobal(localReadOverrides.Length);
            Marshal.Copy(localReadOverrides, 0, block, localReadOverrides.Length);
            Marshal.StructureToPtr(data, block, false);

            StartupInfo startup = new StartupInfo { cb = Marshal.SizeOf(typeof(StartupInfo)) };
            ProcessInformation process;
            string commandLine = "\"" + target + "\"";
            if (document != null) commandLine += " \"" + document + "\"";
            uint result = LeCreateProcess(block, target, commandLine,
                Path.GetDirectoryName(target), 0, ref startup, out process,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            if (result != 0)
                throw new InvalidOperationException("Locale Emulator could not start FASTMEAN. Native error: 0x" + result.ToString("X8") + ". No elevation was attempted.");
            if (process.thread != IntPtr.Zero) CloseHandle(process.thread);
            if (process.process != IntPtr.Zero) CloseHandle(process.process);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message + Environment.NewLine + Environment.NewLine +
                "The optional helper stopped. If Windows Application Control or Smart App Control blocks it, use FASTMEAN MCP without this helper. No elevation or security-policy changes are attempted.",
                "FASTMEAN Russian launcher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            if (block != IntPtr.Zero) Marshal.FreeHGlobal(block);
        }
    }

    private static string JsonString(string value)
    {
        if (value == null) return "null";
        StringBuilder result = new StringBuilder("\"");
        foreach (char character in value)
        {
            if (character == '\\' || character == '"') result.Append('\\').Append(character);
            else if (character < 32) result.Append("\\u").Append(((int)character).ToString("x4"));
            else result.Append(character);
        }
        return result.Append('"').ToString();
    }
}
