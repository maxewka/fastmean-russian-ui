// SPDX-License-Identifier: LGPL-3.0-only
// Per-user installer. No registry, locale, policy, elevation or native-app writes.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Installer
{
    private const string Owner = "fastmean-russian-ui-v1";
    private const string ReceiptName = "installation.json";
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    public sealed class Entry { public string name; public string sha256; public int size; }
    public sealed class Package
    {
        public string format { get; set; }
        public string version { get; set; }
        public Entry[] files { get; set; }
    }
    public sealed class Receipt
    {
        public string owner, version, target, shortcut, shortcut_sha256;
        public Entry[] files;
    }
    private sealed class Options
    {
        internal string Mode = "install", AppDir, Destination;
        internal bool JsonOutput, NoShortcuts, Interactive;
    }
    private sealed class Bundle
    {
        internal string Version;
        internal Dictionary<string, byte[]> Files = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        bool headless = Array.IndexOf(args, "--json") >= 0 || Array.IndexOf(args, "--check") >= 0;
        try
        {
            Options options = Parse(args);
            Bundle bundle = ReadBundle();
            string root = InstallRoot(options.Destination);
            object result;
            if (options.Mode == "uninstall") result = Uninstall(root, bundle);
            else
            {
                string target;
                try { target = FindTarget(options, root); }
                catch (FileNotFoundException)
                {
                    if (!options.Interactive) throw;
                    Application.EnableVisualStyles();
                    using (OpenFileDialog dialog = new OpenFileDialog())
                    {
                        dialog.Title = "Выберите установленную FASTMEAN — Fastmean.exe";
                        dialog.Filter = "FASTMEAN|Fastmean.exe";
                        if (dialog.ShowDialog() != DialogResult.OK) return 2;
                        options.AppDir = dialog.FileName;
                    }
                    target = FindTarget(options, root);
                }
                ValidateExisting(root, bundle);
                result = options.Mode == "check"
                    ? (object)new { ok = true, mode = "check", version = bundle.Version, target = target,
                        install_dir = root, payload_files = bundle.Files.Count, native_launch_started = false,
                        windows_settings_changed = false }
                    : Install(root, target, bundle, options.NoShortcuts);
            }
            if (options.JsonOutput || headless) WriteJson(result);
            if (options.Interactive && options.Mode == "install") ShowCompletion(root, bundle);
            return 0;
        }
        catch (Exception error)
        {
            if (headless) WriteJson(new { ok = false, error = error.Message,
                native_launch_started = false, windows_settings_changed = false });
            else MessageBox.Show(error.Message + "\r\n\r\nНастройки защиты и языка Windows не изменялись.",
                "FASTMEAN — русский интерфейс", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void WriteJson(object value)
    {
        using (StreamWriter writer = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)))
        { writer.WriteLine(Json.Serialize(value)); writer.Flush(); }
    }

    private static Options Parse(string[] args)
    {
        Options result = new Options { Interactive = args.Length == 0 };
        HashSet<string> seen = new HashSet<string>();
        int modes = 0;
        for (int index = 0; index < args.Length; index++)
        {
            string arg = args[index];
            if (!seen.Add(arg)) throw new ArgumentException("Repeated option: " + arg);
            if (arg == "--check" || arg == "--install" || arg == "--uninstall")
            { result.Mode = arg.Substring(2); modes++; }
            else if (arg == "--json") result.JsonOutput = true;
            else if (arg == "--no-shortcuts") result.NoShortcuts = true;
            else if (arg == "--app-dir" || arg == "--destination")
            {
                if (++index >= args.Length) throw new ArgumentException("Missing value for " + arg);
                if (arg == "--app-dir") result.AppDir = args[index];
                else result.Destination = args[index];
            }
            else throw new ArgumentException("Unknown option: " + arg);
        }
        if (modes > 1) throw new ArgumentException("Choose only one install/check/uninstall mode.");
        return result;
    }

    private static string Hash(byte[] value)
    {
        using (SHA256 hash = SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(value)).Replace("-", "").ToLowerInvariant();
    }

    private static string FileHash(string path) { return Hash(File.ReadAllBytes(path)); }

    private static string InstallRoot(string requested)
    {
        string path = Path.GetFullPath(requested ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "FASTMEAN Russian UI"));
        path = path.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (String.Equals(path.TrimEnd('\\'), Path.GetPathRoot(path).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
            throw new IOException("Корень диска не может быть папкой установки.");
        NoLinks(path);
        return path;
    }

    private static void NoLinks(string path)
    {
        string current = Path.GetFullPath(path);
        while (!String.IsNullOrEmpty(current))
        {
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Связанные пути не поддерживаются: " + current);
            current = Path.GetDirectoryName(current);
        }
    }

    private static string OwnedPath(string root, string relative)
    {
        if (String.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.IndexOf(':') >= 0)
            throw new InvalidDataException("Invalid packaged relative path.");
        string[] parts = relative.Replace('\\', '/').Split('/');
        foreach (string part in parts)
            if (part.Length == 0 || part == "." || part == ".." || part.EndsWith(".") || part.EndsWith(" "))
                throw new InvalidDataException("Unsafe packaged filename.");
        string result = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!result.StartsWith(root.TrimEnd('\\', '/') + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Packaged path escaped its destination.");
        NoLinks(result);
        return result;
    }

    private static byte[] Bounded(Stream stream, int maximum)
    {
        using (MemoryStream result = new MemoryStream())
        {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.Read(buffer, 0, buffer.Length)) != 0)
            {
                if (result.Length + count > maximum) throw new InvalidDataException("Packaged file exceeds its size limit.");
                result.Write(buffer, 0, count);
            }
            return result.ToArray();
        }
    }

    private static Bundle ReadBundle()
    {
        Bundle result = new Bundle();
        using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("FastmeanRussianUI.Payload"))
        {
            if (stream == null) throw new InvalidDataException("Installer payload is missing.");
            using (ZipArchive zip = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                if (zip.Entries.Count > 200) throw new InvalidDataException("Too many packaged files.");
                Dictionary<string, ZipArchiveEntry> entries = new Dictionary<string, ZipArchiveEntry>(StringComparer.OrdinalIgnoreCase);
                foreach (ZipArchiveEntry entry in zip.Entries)
                {
                    OwnedPath(Path.Combine(Path.GetTempPath(), "fastmean-payload-validation"), entry.FullName);
                    if (entries.ContainsKey(entry.FullName)) throw new InvalidDataException("Duplicate packaged filename.");
                    entries.Add(entry.FullName, entry);
                }
                ZipArchiveEntry metadata;
                if (!entries.TryGetValue("payload-manifest.json", out metadata))
                    throw new InvalidDataException("Payload manifest is missing.");
                Package manifest;
                using (Stream input = metadata.Open())
                    manifest = Json.Deserialize<Package>(Encoding.UTF8.GetString(Bounded(input, 128 * 1024)));
                if (manifest == null || manifest.format != "fastmean-russianui-payload-v1" ||
                    manifest.files == null || manifest.files.Length + 1 != entries.Count ||
                    String.IsNullOrEmpty(manifest.version)) throw new InvalidDataException("Invalid payload manifest.");
                result.Version = manifest.version;
                long total = 0;
                foreach (Entry file in manifest.files)
                {
                    ZipArchiveEntry entry;
                    if (!entries.TryGetValue(file.name, out entry) || file.size < 0 || file.size > 16 * 1024 * 1024)
                        throw new InvalidDataException("Invalid packaged file declaration.");
                    byte[] data;
                    using (Stream input = entry.Open()) data = Bounded(input, file.size);
                    total += data.Length;
                    if (total > 64 * 1024 * 1024 || data.Length != file.size || Hash(data) != file.sha256)
                        throw new InvalidDataException("Packaged file integrity check failed: " + file.name);
                    result.Files.Add(file.name, data);
                }
            }
        }
        foreach (string name in new string[] { "FastmeanRuRunner.exe", "LoaderDll.dll", "LocaleEmulator.dll" })
            if (!result.Files.ContainsKey(name)) throw new InvalidDataException("Required runtime file missing: " + name);
        return result;
    }

    private static string FindTarget(Options options, string root)
    {
        string[] args = new string[0];
        if (options.AppDir != null)
        {
            string candidate = Path.GetFullPath(options.AppDir);
            if (!String.Equals(Path.GetFileName(candidate), "Fastmean.exe", StringComparison.OrdinalIgnoreCase))
                candidate = Path.Combine(candidate, "Fastmean.exe");
            args = new string[] { candidate };
        }
        return FastmeanLaunchPaths.Resolve(args, root,
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)).Target;
    }

    private static Receipt ReadReceipt(string root)
    {
        string path = OwnedPath(root, ReceiptName);
        if (!File.Exists(path)) return null;
        if (new FileInfo(path).Length > 256 * 1024) throw new IOException("Installation receipt is too large.");
        Receipt receipt = Json.Deserialize<Receipt>(File.ReadAllText(path, Encoding.UTF8));
        if (receipt == null || receipt.owner != Owner || receipt.files == null)
            throw new IOException("Эта папка не принадлежит установщику FASTMEAN Russian UI.");
        HashSet<string> names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (Entry file in receipt.files)
        {
            OwnedPath(root, file.name);
            if (!names.Add(file.name) || file.sha256 == null || file.sha256.Length != 64)
                throw new IOException("Invalid installation receipt.");
        }
        return receipt;
    }

    private static Receipt ValidateExisting(string root, Bundle bundle)
    {
        if (File.Exists(root)) throw new IOException("Путь установки занят файлом.");
        Receipt receipt = ReadReceipt(root);
        if (Directory.Exists(root) && receipt == null && Directory.GetFileSystemEntries(root).Length > 0)
            throw new IOException("Папка уже содержит файлы и не принадлежит этому установщику. Выберите другую папку.");
        if (receipt != null)
        {
            Dictionary<string, string> owned = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (Entry file in receipt.files)
            {
                string path = OwnedPath(root, file.name);
                owned.Add(file.name, file.sha256);
                if (File.Exists(path) && FileHash(path) != file.sha256)
                    throw new IOException("Установленный файл изменён: " + path + ". Он сохранён; выберите новую папку установки.");
            }
            List<string> planned = new List<string>(bundle.Files.Keys);
            planned.Add("FASTMEAN_EXE.txt");
            foreach (string name in planned)
                if (File.Exists(OwnedPath(root, name)) && !owned.ContainsKey(name))
                    throw new IOException("Файл назначения не принадлежит установщику: " + name);
        }
        return receipt;
    }

    private static object Install(string root, string target, Bundle bundle, bool noShortcuts)
    {
        Receipt previous = ValidateExisting(root, bundle);
        Dictionary<string, byte[]> files = new Dictionary<string, byte[]>(bundle.Files, StringComparer.OrdinalIgnoreCase);
        files.Add("FASTMEAN_EXE.txt", new UTF8Encoding(false).GetBytes(target + "\r\n"));
        string parent = Path.GetDirectoryName(root);
        Directory.CreateDirectory(parent);
        string stage = Path.Combine(parent, ".fastmean-russian-ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        List<string> replaced = new List<string>();
        HashSet<string> newlyCreated = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, byte[]> backups = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
        byte[] oldReceipt = File.Exists(Path.Combine(root, ReceiptName)) ? File.ReadAllBytes(Path.Combine(root, ReceiptName)) : null;
        bool newRoot = !Directory.Exists(root);
        try
        {
            foreach (KeyValuePair<string, byte[]> file in files)
            {
                string path = OwnedPath(stage, file.Key);
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllBytes(path, file.Value);
            }
            Receipt receipt = new Receipt { owner = Owner, version = bundle.Version, target = target,
                shortcut = previous == null ? null : previous.shortcut,
                shortcut_sha256 = previous == null ? null : previous.shortcut_sha256 };
            List<Entry> declarations = new List<Entry>();
            foreach (KeyValuePair<string, byte[]> file in files)
                declarations.Add(new Entry { name = file.Key, size = file.Value.Length, sha256 = Hash(file.Value) });
            receipt.files = declarations.ToArray();
            File.WriteAllText(Path.Combine(stage, ReceiptName), Json.Serialize(receipt), new UTF8Encoding(false));
            if (newRoot) Directory.Move(stage, root);
            else
            {
                foreach (KeyValuePair<string, byte[]> file in files)
                {
                    string path = OwnedPath(root, file.Key);
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    if (File.Exists(path)) backups[path] = File.ReadAllBytes(path);
                    else newlyCreated.Add(path);
                    File.Copy(OwnedPath(stage, file.Key), path, true);
                    replaced.Add(path);
                }
                File.Copy(Path.Combine(stage, ReceiptName), Path.Combine(root, ReceiptName), true);
            }
            string shortcutError = null;
            if (!noShortcuts)
            {
                try { CreateShortcut(root, receipt); }
                catch (Exception error) { shortcutError = error.Message; }
            }
            File.WriteAllText(Path.Combine(root, ReceiptName), Json.Serialize(receipt), new UTF8Encoding(false));
            return new { ok = true, status = "installed", version = bundle.Version, install_dir = root,
                helper = Path.Combine(root, "FastmeanRuRunner.exe"), target = target,
                shortcut = receipt.shortcut, shortcut_error = shortcutError,
                file_association_changed = false, windows_settings_changed = false, native_launch_started = false };
        }
        catch
        {
            if (!newRoot)
            {
                foreach (string path in replaced)
                {
                    if (backups.ContainsKey(path)) File.WriteAllBytes(path, backups[path]);
                    else if (newlyCreated.Contains(path)) File.Delete(path);
                }
                if (oldReceipt != null) File.WriteAllBytes(Path.Combine(root, ReceiptName), oldReceipt);
            }
            throw;
        }
        finally
        {
            // Exact stage created above; links are forbidden before recursion.
            if (Directory.Exists(stage))
            {
                if (!String.Equals(Path.GetDirectoryName(Path.GetFullPath(stage)), parent, StringComparison.OrdinalIgnoreCase)
                    || !Path.GetFileName(stage).StartsWith(".fastmean-russian-ui-", StringComparison.Ordinal))
                    throw new IOException("Unexpected installer staging directory; preserved for inspection.");
                NoLinks(stage);
                Directory.Delete(stage, true);
            }
        }
    }

    private static void CreateShortcut(string root, Receipt receipt)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string shortcut = receipt.shortcut;
        if (String.IsNullOrEmpty(shortcut) || !File.Exists(shortcut) || FileHash(shortcut) != receipt.shortcut_sha256)
        {
            shortcut = Path.Combine(desktop, "FASTMEAN (русский).lnk");
            for (int index = 2; File.Exists(shortcut); index++)
                shortcut = Path.Combine(desktop, "FASTMEAN (русский) " + index + ".lnk");
        }
        NoLinks(shortcut);
        Type type = Type.GetTypeFromProgID("WScript.Shell", true);
        object shell = Activator.CreateInstance(type);
        object link = type.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { shortcut });
        Type linkType = link.GetType();
        string helper = Path.Combine(root, "FastmeanRuRunner.exe");
        linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { helper });
        linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { root });
        linkType.InvokeMember("Description", BindingFlags.SetProperty, null, link, new object[] { "FASTMEAN — русский интерфейс и ввод" });
        linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
        receipt.shortcut = shortcut;
        receipt.shortcut_sha256 = FileHash(shortcut);
    }

    private static object Uninstall(string root, Bundle bundle)
    {
        Receipt receipt = ReadReceipt(root);
        if (receipt == null) return new { ok = true, status = "not_installed", install_dir = root };
        List<string> removed = new List<string>(), preserved = new List<string>();
        HashSet<string> allowed = new HashSet<string>(bundle.Files.Keys, StringComparer.OrdinalIgnoreCase);
        allowed.Add("FASTMEAN_EXE.txt");
        foreach (Entry file in receipt.files)
        {
            string path = OwnedPath(root, file.name);
            if (!File.Exists(path)) continue;
            if (!allowed.Contains(file.name) || FileHash(path) != file.sha256) { preserved.Add(path); continue; }
            File.Delete(path);
            removed.Add(path);
        }
        if (!String.IsNullOrEmpty(receipt.shortcut) && File.Exists(receipt.shortcut))
        {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if (String.Equals(Path.GetDirectoryName(receipt.shortcut), desktop, StringComparison.OrdinalIgnoreCase)
                && FileHash(receipt.shortcut) == receipt.shortcut_sha256)
            { NoLinks(receipt.shortcut); File.Delete(receipt.shortcut); }
        }
        if (preserved.Count == 0) File.Delete(Path.Combine(root, ReceiptName));
        // Remove empty owned subdirectories only. Unknown/user files stay put.
        foreach (Entry file in receipt.files)
        {
            string directory = Path.GetDirectoryName(OwnedPath(root, file.name));
            while (directory.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            {
                if (!Directory.Exists(directory) || Directory.GetFileSystemEntries(directory).Length != 0) break;
                Directory.Delete(directory);
                directory = Path.GetDirectoryName(directory);
            }
        }
        if (Directory.GetFileSystemEntries(root).Length == 0) Directory.Delete(root);
        return new { ok = true, status = "uninstalled", install_dir = root, removed_files = removed.Count,
            preserved_modified_files = preserved, windows_settings_changed = false, native_launch_started = false };
    }

    private static void ShowCompletion(string root, Bundle bundle)
    {
        Application.EnableVisualStyles();
        using (Form form = new Form())
        {
            form.Text = "FASTMEAN — русский интерфейс";
            form.ClientSize = new Size(560, 255);
            form.FormBorderStyle = FormBorderStyle.FixedDialog;
            form.MaximizeBox = false;
            form.StartPosition = FormStartPosition.CenterScreen;
            Label text = new Label { AutoSize = false, Left = 24, Top = 20, Width = 510, Height = 145,
                Text = "Готово. Русский запускатель установлен.\r\n\r\nОткрывайте FASTMEAN через новый ярлык на рабочем столе.\r\nДля открытия .scm по умолчанию выберите:\r\n" + Path.Combine(root, "FastmeanRuRunner.exe") +
                    "\r\n\r\nПеред запуском сохраните работу и закройте прежнее окно FASTMEAN." };
            Button open = new Button { Text = "Открыть FASTMEAN", Left = 24, Top = 190, Width = 160, Height = 34 };
            open.Click += delegate {
                Process.Start(new ProcessStartInfo(Path.Combine(root, "FastmeanRuRunner.exe")) { WorkingDirectory = root });
                form.Close();
            };
            Button uninstall = new Button { Text = "Удалить", Left = 205, Top = 190, Width = 110, Height = 34 };
            uninstall.Click += delegate {
                try { Uninstall(root, bundle); MessageBox.Show("Русский запускатель удалён. Файлы FASTMEAN и пользовательские схемы сохранены."); form.Close(); }
                catch (Exception error) { MessageBox.Show(error.Message); }
            };
            Button close = new Button { Text = "Закрыть", Left = 425, Top = 190, Width = 110, Height = 34 };
            close.Click += delegate { form.Close(); };
            form.Controls.AddRange(new Control[] { text, open, uninstall, close });
            form.ShowDialog();
        }
    }
}
