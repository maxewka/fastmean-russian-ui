"""Headless installer transactions using private, nonexecutable app fixtures.

Only managed installer CLI and runner --check are executed. FASTMEAN, Locale
Emulator and normal runner launch paths are never started by these tests.
The Windows Shell shortcut round trip saves only in a disposable test directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
POLICY_ERRORS = {4551, 577, 1260}
EXE_FIXTURE = b"private resolver fixture, not a native executable"
SCM_FIXTURE = b"private original circuit fixture; never rewrite these bytes"
MANAGED_HARNESS = r'''
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Web.Script.Serialization;

internal static class ManagedHarness
{
    private static object Call(string name, params object[] args)
    {
        foreach (MethodInfo method in typeof(Installer).GetMethods(BindingFlags.NonPublic | BindingFlags.Static))
            if (method.Name == name && method.GetParameters().Length == args.Length)
                return method.Invoke(null, args);
        throw new Exception("Managed test method not found: " + name);
    }

    [STAThread]
    public static int Main(string[] args)
    {
        object result;
        if (args[0] == "diagnostics")
        {
            Exception wrapped = new TargetInvocationException(new TargetInvocationException(
                new COMException("Desktop write denied", unchecked((int)0x80070005))));
            string message = (string)Call("DescribeError", wrapped);
            result = new { ok = true, message = message,
                failure = (string)Call("CompletionText", args[1], null, message),
                without_shortcut = (string)Call("CompletionText", args[1], null, null),
                success = (string)Call("CompletionText", args[1], "private-desktop-shortcut.lnk", null) };
        }
        else if (args[0] == "shortcut")
        {
            Installer.Receipt receipt = new Installer.Receipt();
            Call("CreateShortcut", args[1], receipt, args[2]);
            object instance = Activator.CreateInstance(Type.GetTypeFromCLSID(
                new Guid("00021401-0000-0000-C000-000000000046"), true));
            try
            {
                ((System.Runtime.InteropServices.ComTypes.IPersistFile)instance).Load(receipt.shortcut, 0);
                var link = (UnicodeShortcut.IShellLinkW)instance;
                var target = new StringBuilder(1024);
                var directory = new StringBuilder(1024);
                var description = new StringBuilder(1024);
                link.GetPath(target, target.Capacity, IntPtr.Zero, 0);
                link.GetWorkingDirectory(directory, directory.Capacity);
                link.GetDescription(description, description.Capacity);
                result = new { ok = true, shortcut = receipt.shortcut, shortcut_sha256 = receipt.shortcut_sha256,
                    target = target.ToString(), directory = directory.ToString(), description = description.ToString() };
            }
            finally { Marshal.FinalReleaseComObject(instance); }
        }
        else
        {
            Type bundleType = typeof(Installer).GetNestedType("Bundle", BindingFlags.NonPublic);
            object bundle = Activator.CreateInstance(bundleType, true);
            bundleType.GetField("Version", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(bundle, "9.0.0");
            var files = (Dictionary<string, byte[]>)bundleType.GetField("Files", BindingFlags.NonPublic | BindingFlags.Instance)
                .GetValue(bundle);
            files.Add("FastmeanRuRunner.exe", Encoding.UTF8.GetBytes("replacement fixture, never execute"));
            files.Add("LoaderDll.dll", Encoding.UTF8.GetBytes("replacement fixture, never load"));
            files.Add("LocaleEmulator.dll", Encoding.UTF8.GetBytes("replacement fixture, never load"));
            bool partialWrite = false;
            Action<string, string, bool> copier = delegate(string source, string destination, bool overwrite)
            {
                if (Path.GetFileName(destination) == "LoaderDll.dll")
                {
                    File.WriteAllText(destination, "partially copied bytes");
                    partialWrite = true;
                    throw new IOException("deliberate partial-copy failure");
                }
                File.Copy(source, destination, overwrite);
            };
            MethodInfo install = null;
            foreach (MethodInfo method in typeof(Installer).GetMethods(BindingFlags.NonPublic | BindingFlags.Static))
                if (method.Name == "Install" && method.GetParameters().Length == 5) install = method;
            if (install == null) throw new Exception("Transactional copy entry point not found");
            try
            {
                install.Invoke(null, new object[] { args[1], args[2], bundle, true, copier });
                throw new Exception("Partial-copy failure unexpectedly succeeded");
            }
            catch (TargetInvocationException error)
            {
                if (!(error.InnerException is IOException) || error.InnerException.Message != "deliberate partial-copy failure")
                    throw;
            }
            if (!partialWrite) throw new Exception("The partial write was not reached");
            result = new { ok = true, partial_write_reached = partialWrite };
        }
        using (var writer = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)))
            writer.WriteLine(new JavaScriptSerializer().Serialize(result));
        return 0;
    }
}
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot(root: Path) -> dict:
    """Record contents without traversing junctions/symlinks."""
    result = {}
    if not root.exists():
        return result
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            info = path.lstat()
            name = path.relative_to(root).as_posix()
            if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                result[name] = ("link", os.readlink(path))
            elif path.is_dir():
                result[name] = ("directory",)
                pending.append(path)
            else:
                result[name] = ("file", sha256(path.read_bytes()))
    return result


@unittest.skipUnless(os.name == "nt", "Windows .NET Framework installer tests")
class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        if not cls.compiler.is_file():
            raise unittest.SkipTest("Existing .NET Framework 4.x compiler unavailable")
        cls.temporary = tempfile.TemporaryDirectory(prefix="fastmean-russianui-installer-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.dist = cls.root / "dist"
        try:
            built = subprocess.run([sys.executable, str(PROJECT / "build.py"), "--output", str(cls.dist),
                "--version", "1.0.0"], cwd=PROJECT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                raise unittest.SkipTest("Windows policy blocked installer test build: " + str(error))
            raise
        output = built.stdout + built.stderr
        if built.returncode:
            if any("[WinError " + str(code) + "]" in output for code in POLICY_ERRORS):
                raise unittest.SkipTest("Windows policy blocked the ordinary build: " + output[-2000:])
            raise AssertionError("Installer build failed:\n" + output[-8000:])
        cls.installer = cls.dist / "FASTMEAN-RussianUI-Setup.exe"
        if not cls.installer.is_file():
            raise AssertionError("Build did not produce the installer EXE")
        manifest = json.loads((cls.dist / "build-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("native_fastmean_included") is not False:
            raise AssertionError("The build must explicitly exclude native FASTMEAN")
        for product in manifest["files"]:
            path = cls.dist / product["name"]
            if sha256(path.read_bytes()) != product["sha256"]:
                raise AssertionError("Built product digest mismatch: " + product["name"])

    def setUp(self):
        if getattr(type(self), "execution_policy_block", None):
            self.skipTest(type(self).execution_policy_block)
        self.case = Path(tempfile.mkdtemp(prefix="case-", dir=self.root)).resolve()
        self.application = self.case / "native app с пробелами"
        self.application.mkdir()
        self.target = self.application / "Fastmean.exe"
        self.target.write_bytes(EXE_FIXTURE)
        self.destination = self.case / "runtime"
        self.document = self.case / "фильтр 20 Ом.scm"
        self.document.write_bytes(SCM_FIXTURE)
        self.addCleanup(self.assert_sources_preserved)

    def assert_sources_preserved(self):
        self.assertEqual(self.target.read_bytes(), EXE_FIXTURE)
        self.assertEqual(self.document.read_bytes(), SCM_FIXTURE)

    def run_cli(self, arguments, expected=0, executable=None):
        try:
            completed = subprocess.run([str(executable or self.installer), *map(str, arguments)],
                cwd=self.case, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                message = "Windows policy blocked this ordinary test executable: " + str(error)
                type(self).execution_policy_block = message
                self.skipTest(message)
            raise
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        try:
            data = json.loads(completed.stdout)
        except ValueError:
            self.fail("Headless CLI did not return JSON: " + completed.stdout + completed.stderr)
        self.assertIs(data["ok"], expected == 0)
        return data

    def options(self, mode="--install", destination=None):
        return [mode, "--json", "--no-shortcuts", "--app-dir", self.application,
                "--destination", destination or self.destination]

    def install(self):
        data = self.run_cli(self.options())
        self.assertEqual(data["status"], "installed")
        self.assertIs(data["windows_settings_changed"], False)
        self.assertIs(data["file_association_changed"], False)
        self.assertIs(data["native_launch_started"], False)
        self.assertIsNone(data["shortcut"])
        self.assertIsNone(data["shortcut_error"])
        return data

    def test_check_validates_payload_and_target_without_creating_install_directory(self):
        before = snapshot(self.case)
        result = self.run_cli(self.options("--check"))
        self.assertEqual(result["mode"], "check")
        self.assertGreaterEqual(result["payload_files"], 3)
        self.assertTrue(Path(result["target"]).samefile(self.target))
        self.assertIs(result["native_launch_started"], False)
        self.assertIs(result["windows_settings_changed"], False)
        self.assertFalse(self.destination.exists())
        self.assertEqual(snapshot(self.case), before)

    def test_install_records_complete_owned_payload_and_exact_native_target(self):
        self.install()
        required = {"FastmeanRuRunner.exe", "LoaderDll.dll", "LocaleEmulator.dll", "FASTMEAN_EXE.txt",
                    "installation.json", "source/src/FastmeanRuRunner.cs", "source/src/FastmeanLaunchPaths.cs",
                    "source/src/Installer.cs", "source/src/UnicodeShortcut.cs", "source/build.py", "source/NOTICE.md",
                    "source/licenses/COPYING", "source/licenses/COPYING.LESSER"}
        self.assertTrue(all((self.destination / name).is_file() for name in required))
        receipt = json.loads((self.destination / "installation.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["owner"], "fastmean-russian-ui-v1")
        self.assertEqual(receipt["version"], "1.0.0")
        self.assertTrue(Path(receipt["target"]).samefile(self.target))
        self.assertEqual((self.destination / "FASTMEAN_EXE.txt").read_text(encoding="utf-8").strip(), str(self.target))
        recorded = set()
        for entry in receipt["files"]:
            self.assertNotIn(entry["name"], recorded)
            recorded.add(entry["name"])
            path = self.destination / entry["name"]
            self.assertTrue(path.resolve().is_relative_to(self.destination))
            self.assertEqual(path.stat().st_size, entry["size"])
            self.assertEqual(sha256(path.read_bytes()), entry["sha256"])
        for name in ("FastmeanRuRunner.exe", "LoaderDll.dll", "LocaleEmulator.dll", "FASTMEAN_EXE.txt"):
            self.assertIn(name, recorded)

    def test_installed_runner_check_preserves_unicode_scm_without_loading_native_libraries(self):
        self.install()
        # Deliberately invalid DLL images prove that --check does not load them.
        for name in ("LoaderDll.dll", "LocaleEmulator.dll"):
            (self.destination / name).write_bytes(b"not a native DLL; must never be loaded")
        before = snapshot(self.destination)
        result = self.run_cli(["--check", self.document], executable=self.destination / "FastmeanRuRunner.exe")
        self.assertTrue(Path(result["document"]).samefile(self.document))
        self.assertTrue(Path(result["target"]).samefile(self.target))
        self.assertIs(result["native_launch_started"], False)
        self.assertIs(result["windows_settings_changed"], False)
        self.assertEqual(snapshot(self.destination), before)

    def test_reinstall_is_idempotent_and_preserves_unknown_files(self):
        self.install()
        unknown = self.destination / "user-note.txt"
        unknown.write_bytes(b"keep this unrelated user file")
        before = snapshot(self.destination)
        self.install()
        self.assertEqual(snapshot(self.destination), before)

    def test_unknown_nonempty_destination_is_rejected_without_changes(self):
        self.destination.mkdir()
        (self.destination / "unrelated.txt").write_bytes(b"preexisting user data")
        before = snapshot(self.case)
        error = self.run_cli(self.options(), expected=1)
        self.assertTrue(error["error"])
        self.assertEqual(snapshot(self.case), before)

    def test_modified_owned_file_blocks_upgrade_before_any_writes(self):
        self.install()
        changed = self.destination / "FastmeanRuRunner.exe"
        changed.write_bytes(changed.read_bytes() + b"private deliberate user modification")
        before = snapshot(self.case)
        error = self.run_cli(self.options(), expected=1)
        self.assertIn(changed.name, error["error"])
        self.assertEqual(snapshot(self.case), before)
        self.assertFalse(list(self.case.glob(".fastmean-russian-ui-*")))

    def test_existing_unowned_target_config_is_never_overwritten(self):
        self.install()
        receipt_path = self.destination / "installation.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        # Emulate an older receipt that does not claim this configuration file.
        receipt["files"] = [entry for entry in receipt["files"] if entry["name"] != "FASTMEAN_EXE.txt"]
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        before = snapshot(self.case)
        error = self.run_cli(self.options(), expected=1)
        self.assertIn("FASTMEAN_EXE.txt", error["error"])
        self.assertEqual(snapshot(self.case), before)

    def test_uninstall_preserves_modified_owned_and_unknown_files(self):
        self.install()
        changed = self.destination / "FastmeanRuRunner.exe"
        modified = changed.read_bytes() + b"private modification; preserve"
        changed.write_bytes(modified)
        unknown = self.destination / "user-note.txt"
        unknown.write_bytes(b"keep unrelated content")
        result = self.run_cli(self.options("--uninstall"))
        self.assertEqual(result["status"], "uninstalled")
        self.assertGreater(result["removed_files"], 0)
        self.assertIn(str(changed), result["preserved_modified_files"])
        self.assertEqual(changed.read_bytes(), modified)
        self.assertEqual(unknown.read_bytes(), b"keep unrelated content")
        self.assertTrue((self.destination / "installation.json").is_file())
        self.assertFalse((self.destination / "LoaderDll.dll").exists())
        self.assertFalse((self.destination / "FASTMEAN_EXE.txt").exists())
        self.assertIs(result["native_launch_started"], False)

    def test_invalid_cli_missing_target_and_drive_root_fail_without_writes(self):
        before = snapshot(self.case)
        cases = [
            self.options("--check") + ["--unknown"],
            self.options("--check") + ["--install"],
            ["--check", "--json", "--app-dir"],
            ["--check", "--json", "--app-dir", self.case / "missing app", "--destination", self.destination],
            self.options("--check", destination=Path(self.case.anchor)),
        ]
        for arguments in cases:
            with self.subTest(arguments=list(map(str, arguments))):
                result = self.run_cli(arguments, expected=1)
                self.assertTrue(result["error"])
                self.assertEqual(snapshot(self.case), before)

    def compile_payload_fixture(self, label, files, bad_digest=False):
        folder = self.case / label
        folder.mkdir()
        manifest = {"format": "fastmean-russianui-payload-v1", "version": "9.0.0",
                    "files": [{"name": name, "size": len(data),
                               "sha256": "0" * 64 if bad_digest and name == "LoaderDll.dll" else sha256(data)}
                              for name, data in files.items()]}
        payload = folder / "payload.zip"
        with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr("payload-manifest.json", json.dumps(manifest))
        executable = folder / "FixtureInstaller.exe"
        command = [str(self.compiler), "/nologo", "/target:winexe", "/platform:x86",
            "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
            "/reference:System.Web.Extensions.dll", "/reference:System.IO.Compression.dll",
            "/reference:System.IO.Compression.FileSystem.dll", "/out:" + str(executable),
            "/win32manifest:" + str(PROJECT / "src/FastmeanRuRunner.manifest"),
            "/resource:" + str(payload) + ",FastmeanRussianUI.Payload",
            str(PROJECT / "src/Installer.cs"), str(PROJECT / "src/FastmeanLaunchPaths.cs"),
            str(PROJECT / "src/UnicodeShortcut.cs")]
        try:
            compiled = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                message = "Windows policy blocked ordinary fixture compilation: " + str(error)
                type(self).execution_policy_block = message
                self.skipTest(message)
            raise
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        return executable

    @staticmethod
    def runtime_fixtures():
        return {"FastmeanRuRunner.exe": b"replacement fixture, never execute",
                "LoaderDll.dll": b"replacement loader fixture, never load",
                "LocaleEmulator.dll": b"replacement library fixture, never load"}

    def test_payload_hash_failure_is_rejected_before_destination_creation(self):
        executable = self.compile_payload_fixture("bad-payload", self.runtime_fixtures(), bad_digest=True)
        before = snapshot(self.case)
        error = self.run_cli(self.options("--check"), expected=1, executable=executable)
        self.assertIn("integrity", error["error"].lower())
        self.assertFalse(self.destination.exists())
        self.assertEqual(snapshot(self.case), before)

    def test_failed_upgrade_rolls_back_replaced_files_and_receipt(self):
        self.install()
        conflict = self.destination / "zz-conflict.txt"
        conflict.mkdir()
        (conflict / "keep.txt").write_bytes(b"unknown directory content must survive")
        files = self.runtime_fixtures()
        files[conflict.name] = b"cannot overwrite a directory with this file"
        executable = self.compile_payload_fixture("rollback-payload", files)
        before = snapshot(self.destination)
        error = self.run_cli(self.options(), expected=1, executable=executable)
        self.assertIn(conflict.name, error["error"])
        self.assertEqual(snapshot(self.destination), before)
        self.assertFalse(list(self.case.glob(".fastmean-russian-ui-*")))

    def compile_managed_harness(self):
        folder = self.case / "managed-harness"
        folder.mkdir()
        source = folder / "ManagedHarness.cs"
        source.write_text(MANAGED_HARNESS, encoding="utf-8")
        executable = folder / "ManagedHarness.exe"
        command = [str(self.compiler), "/nologo", "/target:exe", "/platform:x86", "/main:ManagedHarness",
            "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
            "/reference:System.Web.Extensions.dll", "/reference:System.IO.Compression.dll",
            "/reference:System.IO.Compression.FileSystem.dll", "/out:" + str(executable),
            str(source), str(PROJECT / "src/Installer.cs"), str(PROJECT / "src/FastmeanLaunchPaths.cs"),
            str(PROJECT / "src/UnicodeShortcut.cs")]
        try:
            compiled = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                message = "Windows policy blocked ordinary harness compilation: " + str(error)
                type(self).execution_policy_block = message
                self.skipTest(message)
            raise
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        return executable

    def test_shortcut_failure_reports_inner_hresult_and_honest_completion_without_com(self):
        executable = self.compile_managed_harness()
        before = snapshot(self.case)
        result = self.run_cli(["diagnostics", self.destination], executable=executable)
        self.assertIn("Desktop write denied", result["message"])
        self.assertIn("HRESULT 0x80070005", result["message"])
        self.assertNotIn("target of an invocation", result["message"])
        self.assertIn("создать не удалось", result["failure"])
        self.assertIn(result["message"], result["failure"])
        self.assertIn(str(self.destination / "FastmeanRuRunner.exe"), result["failure"])
        self.assertNotIn("через ярлык", result["failure"])
        self.assertNotIn("через ярлык", result["without_shortcut"])
        self.assertIn("private-desktop-shortcut.lnk", result["success"])
        self.assertNotIn("создать не удалось", result["success"])
        self.assertEqual(snapshot(self.case), before)

    def test_partial_copy_failure_restores_the_failing_file_and_all_previous_changes(self):
        self.install()
        executable = self.compile_managed_harness()
        before = snapshot(self.destination)
        result = self.run_cli(["rollback", self.destination, self.target], executable=executable)
        self.assertIs(result["partial_write_reached"], True)
        self.assertEqual(snapshot(self.destination), before)
        self.assertFalse(list(self.case.glob(".fastmean-russian-ui-*")))

    def test_shell_link_round_trip_preserves_cyrillic_names_and_contents_without_launching(self):
        executable = self.compile_managed_harness()
        helper_root = self.case / "Русский запускатель"
        helper_root.mkdir()
        helper = helper_root / "FastmeanRuRunner.exe"
        helper.write_bytes(EXE_FIXTURE)
        desktop = self.case / "Рабочий стол"
        desktop.mkdir()
        unknown = desktop / "FASTMEAN (русский).lnk"
        unknown.write_bytes(b"unknown existing shortcut fixture; preserve")
        original = unknown.read_bytes()
        result = self.run_cli(["shortcut", helper_root, desktop], executable=executable)
        shortcut = desktop / "FASTMEAN (русский) 2.lnk"
        self.assertEqual(Path(result["shortcut"]), shortcut)
        self.assertTrue(shortcut.is_file())
        self.assertGreater(shortcut.stat().st_size, 76)
        self.assertEqual(result["shortcut_sha256"], sha256(shortcut.read_bytes()))
        self.assertEqual(Path(result["target"]), helper)
        self.assertEqual(Path(result["directory"]), helper_root)
        self.assertEqual(result["description"], "FASTMEAN — русский интерфейс и ввод")
        self.assertEqual(helper.read_bytes(), EXE_FIXTURE)
        self.assertEqual(unknown.read_bytes(), original)
        self.assertEqual(sorted(path.name for path in desktop.iterdir()), sorted([unknown.name, shortcut.name]))

    def make_junction(self, link, target):
        shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if not shell.is_file():
            self.skipTest("Existing Windows PowerShell unavailable for private junction fixture")
        environment = dict(os.environ, FMRUI_TEST_LINK=str(link), FMRUI_TEST_TARGET=str(target))
        try:
            created = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command",
                "New-Item -ItemType Junction -Path $env:FMRUI_TEST_LINK -Target $env:FMRUI_TEST_TARGET -ErrorAction Stop | Out-Null"],
                env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                self.skipTest("Windows policy blocked private junction creation: " + str(error))
            raise
        if created.returncode:
            self.skipTest("Private junction creation unavailable: " + created.stderr[-1000:])
        self.addCleanup(lambda: link.rmdir() if os.path.lexists(link) else None)

    def test_linked_destination_cannot_install_into_its_target(self):
        target = self.case / "outside-destination"
        target.mkdir()
        (target / "keep.txt").write_bytes(b"preserve junction target")
        self.make_junction(self.destination, target)
        before = snapshot(target)
        error = self.run_cli(self.options("--check"), expected=1)
        self.assertTrue(error["error"])
        self.assertEqual(snapshot(target), before)

    def test_uninstall_validates_owned_descendant_links_before_removing_any_files(self):
        self.install()
        source = self.destination / "source"
        outside = self.case / "outside-owned-source"
        # Both directory-move endpoints must stay inside this disposable case.
        self.assertTrue(source.resolve().is_relative_to(self.case))
        self.assertEqual(outside.parent.resolve(), self.case)
        self.assertFalse(outside.exists())
        source.rename(outside)
        self.make_junction(source, outside)
        before_runtime = snapshot(self.destination)
        before_target = snapshot(outside)
        error = self.run_cli(self.options("--uninstall"), expected=1)
        self.assertTrue(error["error"])
        self.assertEqual(snapshot(self.destination), before_runtime)
        self.assertEqual(snapshot(outside), before_target)


if __name__ == "__main__":
    unittest.main()
