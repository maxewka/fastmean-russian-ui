"""Compile/test the pure launcher-path resolver, never the locale loader.

The console harness resolves disposable text fixtures named Fastmean.exe; it
does not start FASTMEAN, load Locale Emulator, modify Windows or touch user SCMs.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
RESOLVER = PROJECT / "src/FastmeanLaunchPaths.cs"
POLICY_ERRORS = {4551, 577, 1260}

HARNESS = r'''
using System;
using System.IO;
using System.Text;

internal static class ResolverTests
{
    private const string ExeBytes = "resolver-only text fixture; not executable";
    private const string ScmBytes = "private original SCM fixture, never rewritten";

    private static void Check(bool value, string message)
    {
        if (!value) throw new Exception(message);
    }

    private static string FileAt(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(path, text, new UTF8Encoding(false));
        return Path.GetFullPath(path);
    }

    private static string ExeAt(string directory)
    {
        return FileAt(Path.Combine(directory, "Fastmean.exe"), ExeBytes);
    }

    private static void Config(string directory, string text)
    {
        Directory.CreateDirectory(directory);
        // A normal UTF-8 BOM and final CRLF must survive Windows text editors.
        File.WriteAllText(Path.Combine(directory, "FASTMEAN_EXE.txt"), text,
            new UTF8Encoding(true));
    }

    private static void Matches(FastmeanLaunchPaths.Request request,
                                string target, string document)
    {
        Check(String.Equals(request.Target, Path.GetFullPath(target),
            StringComparison.OrdinalIgnoreCase), "Wrong native executable target");
        Check(String.Equals(request.Document, document == null ? null : Path.GetFullPath(document),
            StringComparison.OrdinalIgnoreCase), "Wrong document path");
    }

    private static void Fails(Action action, string diagnosticPart)
    {
        Exception error = null;
        try { action(); } catch (Exception caught) { error = caught; }
        Check(error != null, "Invalid launch request was accepted");
        Check(!String.IsNullOrWhiteSpace(error.Message), "Missing actionable error");
        if (diagnosticPart != null)
            Check(error.Message.IndexOf(diagnosticPart, StringComparison.OrdinalIgnoreCase) >= 0,
                  "Error did not identify its invalid configuration: " + error.Message);
    }

    private static void Configured(string root)
    {
        string helper = Path.Combine(root, "helper directory");
        string local = Path.Combine(root, "local application data");
        string target = ExeAt(Path.Combine(root, "Установленная программа"));
        string document = FileAt(Path.Combine(root, "Схемы с пробелами", "фильтр 20 Ом.SCM"), ScmBytes);
        Config(helper, "\r\n" + target + "\r\n\r\n");
        Matches(FastmeanLaunchPaths.Resolve(new string[0], helper, local), target, null);
        Matches(FastmeanLaunchPaths.Resolve(new string[] { document }, helper, local), target, document);
        Matches(FastmeanLaunchPaths.Resolve(new string[] { target }, helper, local), target, null);
        string previous = Environment.CurrentDirectory;
        try
        {
            Environment.CurrentDirectory = root;
            string relativeDocument = Path.Combine("Схемы с пробелами", "фильтр 20 Ом.SCM");
            Matches(FastmeanLaunchPaths.Resolve(new string[] { relativeDocument }, helper, local),
                    target, document);
        }
        finally { Environment.CurrentDirectory = previous; }
        Check(File.ReadAllText(target) == ExeBytes, "Source executable fixture changed");
        Check(File.ReadAllText(document) == ScmBytes, "Source SCM fixture changed");
    }

    private static void Discovery(string root)
    {
        string helper = Path.Combine(root, "application", "RussianRuntime");
        Directory.CreateDirectory(helper);
        string local = Path.Combine(root, "local");
        string parent = ExeAt(Path.GetDirectoryName(helper));
        string oldVersion = ExeAt(Path.Combine(local, "FASTMEAN 6.0"));
        string newVersion = ExeAt(Path.Combine(local, "FASTMEAN 6.1"));
        // AppDomain.CurrentDomain.BaseDirectory normally includes this slash.
        Matches(FastmeanLaunchPaths.Resolve(new string[0], helper + Path.DirectorySeparatorChar, local),
                parent, null);
        string sibling = ExeAt(helper);
        Matches(FastmeanLaunchPaths.Resolve(new string[0], helper, local), sibling, null);
        File.Delete(sibling);
        File.Delete(parent);
        Matches(FastmeanLaunchPaths.Resolve(new string[0], helper, local), newVersion, null);
        File.Delete(newVersion);
        Matches(FastmeanLaunchPaths.Resolve(new string[0], helper, local), oldVersion, null);
        File.Delete(oldVersion);
        Fails(delegate { FastmeanLaunchPaths.Resolve(new string[0], helper, local); }, null);
        string explicitTarget = ExeAt(Path.Combine(root, "explicit licensed application"));
        string document = FileAt(Path.Combine(root, "explicit document.scm"), ScmBytes);
        Config(helper, "invalid\r\nconfiguration\r\n");
        Matches(FastmeanLaunchPaths.Resolve(new string[] { explicitTarget, document }, helper, local),
                explicitTarget, document);
        Matches(FastmeanLaunchPaths.Resolve(new string[] { explicitTarget }, helper, local),
                explicitTarget, null);
        Check(File.ReadAllText(document) == ScmBytes, "Explicit document was rewritten");
    }

    private static void BadConfiguration(string root)
    {
        string helper = Path.Combine(root, "helper");
        string local = Path.Combine(root, "local");
        string target = ExeAt(Path.Combine(root, "valid target"));
        // A fallback exists: a present broken config must not silently select it.
        ExeAt(Path.Combine(local, "FASTMEAN 6.1"));
        string wrongName = FileAt(Path.Combine(root, "NotFastmean.exe"), ExeBytes);
        string[] cases = new string[] {
            "", "\r\n \r\n", target + "\r\n" + target,
            "relative\\Fastmean.exe", "C:Fastmean.exe", "\\Fastmean.exe",
            "\"" + target + "\"", target + "\0", target + "\u0001", wrongName,
            Path.Combine(root, "absent target", "Fastmean.exe")
        };
        foreach (string text in cases)
        {
            Config(helper, text);
            Fails(delegate { FastmeanLaunchPaths.Resolve(new string[0], helper, local); },
                  "FASTMEAN_EXE.txt");
        }
        Check(File.ReadAllText(target) == ExeBytes, "Configured target fixture changed");
    }

    private static void BadArguments(string root)
    {
        string helper = Path.Combine(root, "helper");
        string local = Path.Combine(root, "local");
        string target = ExeAt(Path.Combine(root, "valid native app"));
        string document = FileAt(Path.Combine(root, "user document.scm"), ScmBytes);
        string wrongExecutable = FileAt(Path.Combine(root, "Other.exe"), ExeBytes);
        string wrongDocument = FileAt(Path.Combine(root, "wrong.txt"), ScmBytes);
        Config(helper, target);
        string[][] cases = new string[][] {
            new string[] { "" }, new string[] { null },
            new string[] { target, document, "extra" },
            new string[] { document, target }, new string[] { document, document },
            new string[] { wrongExecutable }, new string[] { wrongDocument },
            new string[] { Path.Combine(root, "missing", "Fastmean.exe") },
            new string[] { Path.Combine(root, "missing.scm") },
            new string[] { target, Path.Combine(root, "missing.scm") },
            new string[] { target, wrongDocument },
            new string[] { "\"" + target + "\"", document },
            new string[] { target, document + "\0" }
        };
        foreach (string[] args in cases)
            Fails(delegate { FastmeanLaunchPaths.Resolve(args, helper, local); }, null);
        Check(File.ReadAllText(target) == ExeBytes, "Argument executable fixture changed");
        Check(File.ReadAllText(document) == ScmBytes, "Argument SCM fixture changed");
    }

    private static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            string root = Path.GetFullPath(args[1]);
            Directory.CreateDirectory(root);
            switch (args[0])
            {
                case "configured": Configured(root); break;
                case "discovery": Discovery(root); break;
                case "bad_config": BadConfiguration(root); break;
                case "bad_args": BadArguments(root); break;
                default: throw new Exception("Unknown test case");
            }
            Console.WriteLine("PASS " + args[0]);
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }
}
'''


@unittest.skipUnless(os.name == "nt", "Windows .NET Framework compiler required for resolver tests")
class FontFixPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        if not compiler.is_file():
            raise unittest.SkipTest("Existing .NET Framework 4.x C# compiler unavailable")
        cls.compiler = compiler
        cls.temporary = tempfile.TemporaryDirectory(prefix="fastmean-path-resolver-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        source = cls.root / "ResolverTests.cs"
        source.write_text(HARNESS, encoding="utf-8-sig")
        cls.harness = cls.root / "ResolverTests.exe"
        try:
            compiled = subprocess.run([str(compiler), "/nologo", "/target:exe", "/platform:anycpu",
                "/out:" + str(cls.harness), str(RESOLVER), str(source)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                raise unittest.SkipTest("Windows policy blocked pure resolver test compilation: " + str(error))
            raise
        if compiled.returncode:
            raise AssertionError("Pure path resolver compilation failed:\n" + compiled.stdout + compiled.stderr)

    def run_case(self, name):
        try:
            completed = subprocess.run([str(self.harness), name, str(self.root / name)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                self.skipTest("Windows policy blocked pure resolver test harness: " + str(error))
            raise
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PASS " + name, completed.stdout)

    def test_file_association_and_no_argument_launch_preserve_unicode_documents(self):
        self.run_case("configured")

    def test_explicit_target_overrides_config_and_discovery_has_deterministic_precedence(self):
        self.run_case("discovery")

    def test_malformed_present_config_fails_instead_of_selecting_a_fallback(self):
        self.run_case("bad_config")

    def test_invalid_explicit_arguments_and_missing_files_fail_without_rewriting_sources(self):
        self.run_case("bad_args")

    def test_actual_x86_windows_runner_check_returns_json_without_loading_native_files(self):
        helper = self.root / "actual runner check"
        helper.mkdir()
        runner = helper / "FastmeanRuRunner.exe"
        target = helper / "Русская программа с пробелами" / "Fastmean.exe"
        target.parent.mkdir()
        target.write_bytes(b"not a native executable; resolver fixture only")
        document = helper / "Схемы пользователя" / "фильтр 20 Ом.scm"
        document.parent.mkdir()
        document.write_bytes(b"private SCM fixture; preserve these exact bytes")
        for name in ("LoaderDll.dll", "LocaleEmulator.dll"):
            (helper / name).write_bytes(b"not a native DLL; must never be loaded")
        config = helper / "FASTMEAN_EXE.txt"
        config.write_text(str(target) + "\r\n", encoding="utf-8-sig")
        fixtures = {path: path.read_bytes() for path in (target, document, config,
            helper / "LoaderDll.dll", helper / "LocaleEmulator.dll")}
        try:
            compiled = subprocess.run([str(self.compiler), "/nologo", "/target:winexe", "/platform:x86",
                "/reference:System.Windows.Forms.dll", "/out:" + str(runner),
                "/win32manifest:" + str(PROJECT / "src/FastmeanRuRunner.manifest"),
                str(PROJECT / "src/FastmeanRuRunner.cs"), str(RESOLVER)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                self.skipTest("Windows policy blocked check-only runner compilation: " + str(error))
            raise
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)

        for supplied, expected_code in ((document, 0), (helper / "Нет такой схемы.scm", 1)):
            with self.subTest(document=supplied.name):
                try:
                    completed = subprocess.run([str(runner), "--check", str(supplied)],
                        capture_output=True, text=True, encoding="utf-8", timeout=15)
                except OSError as error:
                    if getattr(error, "winerror", None) in POLICY_ERRORS:
                        self.skipTest("Windows policy blocked check-only runner: " + str(error))
                    raise
                self.assertEqual(completed.returncode, expected_code, completed.stdout + completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual(result["ok"], expected_code == 0)
                self.assertIs(result["native_launch_started"], False)
                if expected_code == 0:
                    self.assertEqual(Path(result["target"]), target)
                    self.assertEqual(Path(result["document"]), document)
                    self.assertIs(result["windows_settings_changed"], False)
                else:
                    self.assertTrue(result["error"])
                self.assertEqual({path: path.read_bytes() for path in fixtures}, fixtures)


if __name__ == "__main__":
    unittest.main()
