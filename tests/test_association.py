"""Association ownership transactions against an injected in-memory registry.

No test opens real registry keys, starts FASTMEAN, or loads Locale Emulator.
The compiled managed harness has only disposable file paths and MemoryStore.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
POLICY_ERRORS = {4551, 577, 1260}
HARNESS = r'''
using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;

internal static class AssociationTests
{
    private sealed class MemoryStore : HelperAssociation.IStore
    {
        internal Dictionary<string, HelperAssociation.Value> Values =
            new Dictionary<string, HelperAssociation.Value>(StringComparer.OrdinalIgnoreCase);
        internal int Writes;
        internal bool FailAfterWrite;
        internal bool FailReadsAfterWrite, IgnoreNextWrite;
        internal int FailBeforeWriteAt;
        private string Id(string key, string name) { return key + "|" + name; }
        internal void Set(string key, string name, string text, int kind)
        { Values[Id(key, name)] = new HelperAssociation.Value(text, kind); }
        public HelperAssociation.Value Read(string key, string name)
        {
            if (FailReadsAfterWrite && Writes > 0) throw new IOException("read denied after attempted write");
            HelperAssociation.Value value;
            return Values.TryGetValue(Id(key, name), out value)
                ? new HelperAssociation.Value(value.text, value.kind) : null;
        }
        public void Write(string key, string name, HelperAssociation.Value value)
        {
            Check(key == HelperAssociation.CommandKey && name == String.Empty,
                "Attempted a write outside the one existing helper command");
            Writes++;
            if (FailBeforeWriteAt == Writes) throw new IOException("restoration write denied");
            if (IgnoreNextWrite) { IgnoreNextWrite = false; return; }
            Set(key, name, value.text, value.kind);
            if (FailAfterWrite) { FailAfterWrite = false; throw new IOException("committed write failure"); }
        }
        internal string Snapshot()
        { return new JavaScriptSerializer().Serialize(Values); }
    }

    private static string Native, Local, Legacy, Helper, OtherHelper;
    private static void Check(bool condition, string message)
    { if (!condition) throw new Exception(message); }
    private static void Throws(Action action)
    {
        bool caught = false;
        try { action(); } catch (IOException) { caught = true; }
        Check(caught, "Expected the guarded operation to fail");
    }
    private static MemoryStore Selected(bool latest)
    {
        MemoryStore store = new MemoryStore();
        store.Set(latest ? HelperAssociation.LatestChoiceKey : HelperAssociation.ChoiceKey,
            "ProgId", HelperAssociation.HelperProgId, 1);
        store.Set(HelperAssociation.CommandKey, String.Empty, HelperAssociation.Command(Legacy), 1);
        store.Set(HelperAssociation.ChoiceKey, "Hash", "protected-user-choice-bytes", 1);
        store.Set(@"Software\Classes\FASTMEAN.Scheme\shell\open\command", String.Empty,
            "\"" + Native + "\" -o \"%1\"", 1);
        return store;
    }
    private static HelperAssociation.Plan Plan(MemoryStore store, string helper,
        HelperAssociation.Receipt previous, string[] owned)
    { return HelperAssociation.Inspect(store, helper, Native, Local, owned, previous); }
    private static string Current(MemoryStore store)
    { return store.Read(HelperAssociation.CommandKey, String.Empty).text; }
    private static HelperAssociation.Applied Apply(MemoryStore store, string helper,
        HelperAssociation.Receipt previous)
    {
        return HelperAssociation.Apply(store, Plan(store, helper, previous, null),
            delegate(HelperAssociation.Receipt backup) { Check(HelperAssociation.ValidReceipt(backup), "Invalid backup"); });
    }

    private static void Upgrade(bool latest)
    {
        MemoryStore store = Selected(latest);
        store.Set(HelperAssociation.CommandKey, String.Empty, HelperAssociation.Command(Legacy), 2);
        string original = store.Snapshot();
        HelperAssociation.Plan plan = Plan(store, Helper, null, null);
        Check(plan.Changes && plan.Status == "update_existing_helper", "Legacy helper was not recognized");
        Check(store.Writes == 0 && store.Snapshot() == original, "Check mode changed state");
        int backups = 0;
        HelperAssociation.Applied applied = HelperAssociation.Apply(store, plan,
            delegate(HelperAssociation.Receipt receipt)
            {
                Check(store.Writes == 0 && Current(store) == HelperAssociation.Command(Legacy), "Backup followed write");
                Check(receipt.original.kind == 2, "Original registry kind lost");
                backups++;
            });
        Check(applied.Changed && backups == 1 && store.Writes == 1, "Wrong transaction count");
        Check(Current(store) == HelperAssociation.Command(Helper), "Wrong installed command");
        Check(store.Read(HelperAssociation.ChoiceKey, "Hash").text == "protected-user-choice-bytes", "Protected hash changed");
        Check(store.Read(@"Software\Classes\FASTMEAN.Scheme\shell\open\command", "").text.Contains("-o"), "Native registration changed");
        // Serialization must retain ownership for a future installer process.
        JavaScriptSerializer json = new JavaScriptSerializer();
        var reloaded = json.Deserialize<HelperAssociation.Receipt>(json.Serialize(applied.Ownership));
        Check(HelperAssociation.Restore(store, reloaded), "Uninstall did not restore owned command");
        Check(store.Snapshot() == original, "Uninstall did not preserve the exact original state/kind");
    }

    private static void NonHelperChoices()
    {
        foreach (string choice in new string[] { null, "FASTMEAN.Scheme", "Applications\\Other.exe" })
        {
            MemoryStore store = Selected(true);
            store.Values.Remove(HelperAssociation.LatestChoiceKey + "|ProgId");
            if (choice != null) store.Set(HelperAssociation.LatestChoiceKey, "ProgId", choice, 1);
            string before = store.Snapshot();
            var plan = Plan(store, Helper, null, null);
            Check(!plan.Changes, "Created or replaced an unrelated default");
            HelperAssociation.Apply(store, plan, null);
            Check(store.Writes == 0 && store.Snapshot() == before, "Unrelated state changed");
        }
        MemoryStore conflict = Selected(true);
        conflict.Set(HelperAssociation.ChoiceKey, "ProgId", "FASTMEAN.Scheme", 1);
        Check(!Plan(conflict, Helper, null, null).Changes, "Conflicting choices were guessed at");
    }

    private static void UnrecognizedCommands()
    {
        foreach (string command in new string[] {
            HelperAssociation.Command(OtherHelper), "\"" + Native + "\" -o \"%1\"",
            "\"" + Legacy + "\" \"%1\" \"extra\"", "\"" + Legacy + "\" %1",
            "\"" + Legacy + "\" \"" + Path.Combine(Local, "Other", "Fastmean.exe") + "\" \"%1\"" })
        {
            MemoryStore store = Selected(true);
            store.Set(HelperAssociation.CommandKey, "", command, 1);
            string before = store.Snapshot();
            Check(!Plan(store, Helper, null, null).Changes, "Unrecognized command was overwritten");
            Check(store.Writes == 0 && store.Snapshot() == before, "Inspect was not read only");
        }
        MemoryStore unsupported = Selected(true);
        unsupported.Set(HelperAssociation.CommandKey, "", "not a string registration", 4);
        Check(!Plan(unsupported, Helper, null, null).Changes, "Unsupported registry kind was overwritten");
        unsupported.Values.Remove(HelperAssociation.CommandKey + "|");
        Check(!Plan(unsupported, Helper, null, null).Changes, "Missing command was created");
    }

    private static void OwnedCustomAndExplicitNative()
    {
        MemoryStore custom = Selected(true);
        custom.Set(HelperAssociation.CommandKey, "", HelperAssociation.Command(OtherHelper), 1);
        Check(Plan(custom, Helper, null, new string[] { OtherHelper }).Changes, "Verified prior custom installation not recognized");
        MemoryStore explicitNative = Selected(true);
        explicitNative.Set(HelperAssociation.CommandKey, "",
            "\"" + Legacy + "\" \"" + Native + "\" \"%1\"", 1);
        var applied = Apply(explicitNative, Helper, null);
        Check(applied.Changed && HelperAssociation.Restore(explicitNative, applied.Ownership), "Explicit native argument not preserved");
    }

    private static void IdempotenceAndMigration()
    {
        MemoryStore store = Selected(true);
        string first = Current(store);
        var installed = Apply(store, Helper, null);
        int writes = store.Writes;
        var same = Apply(store, Helper, installed.Ownership);
        Check(!same.Changed && store.Writes == writes && same.Ownership.original.text == first, "Upgrade lost original ownership");
        var moved = Apply(store, OtherHelper, same.Ownership);
        Check(moved.Changed && moved.Ownership.original.text == first, "Moved install lost first original command");
        Check(HelperAssociation.Rollback(store, moved) && Current(store) == HelperAssociation.Command(Helper), "Failed upgrade rollback restored wrong generation");
        moved = Apply(store, OtherHelper, installed.Ownership);
        Check(HelperAssociation.Restore(store, moved.Ownership) && Current(store) == first, "Uninstall restored an intermediate generation");
        MemoryStore userConfigured = Selected(true);
        userConfigured.Set(HelperAssociation.CommandKey, "", HelperAssociation.Command(Helper), 1);
        var existing = Apply(userConfigured, Helper, null);
        Check(!existing.Changed && existing.Ownership == null, "Claimed ownership of an untouched user registration");
    }

    private static void BackupFailureAndRaces()
    {
        MemoryStore store = Selected(true);
        string original = store.Snapshot();
        Throws(delegate { HelperAssociation.Apply(store, Plan(store, Helper, null, null),
            delegate(HelperAssociation.Receipt receipt) { throw new IOException("backup failed"); }); });
        Check(store.Writes == 0 && store.Snapshot() == original, "Backup failure changed association");
        var commandRace = Plan(store, Helper, null, null);
        store.Set(HelperAssociation.CommandKey, "", "user changed this command", 1);
        Throws(delegate { HelperAssociation.Apply(store, commandRace, delegate(HelperAssociation.Receipt receipt) { }); });
        Check(store.Writes == 0 && Current(store) == "user changed this command", "Concurrent command edit was lost");
        store = Selected(true);
        MemoryStore captured = store;
        Throws(delegate { HelperAssociation.Apply(captured, Plan(captured, Helper, null, null),
            delegate(HelperAssociation.Receipt receipt)
            { captured.Set(HelperAssociation.LatestChoiceKey, "ProgId", "FASTMEAN.Scheme", 1); }); });
        Check(store.Writes == 0 && Current(store) == HelperAssociation.Command(Legacy), "Choice changed during backup was ignored");
    }

    private static void ExternalChangesAndInvalidReceipts()
    {
        MemoryStore store = Selected(true);
        var applied = Apply(store, Helper, null);
        store.Set(HelperAssociation.CommandKey, "", "external edit", 1);
        int writes = store.Writes;
        Check(!HelperAssociation.Rollback(store, applied), "Rollback overwrote external edit");
        Check(!HelperAssociation.Restore(store, applied.Ownership), "Uninstall overwrote external edit");
        Check(store.Writes == writes && Current(store) == "external edit", "External edit changed");
        store.Set(HelperAssociation.CommandKey, "", HelperAssociation.Command(Helper), 1);
        applied.Ownership.key = @"Software\Classes\Other.exe";
        Check(!HelperAssociation.Restore(store, applied.Ownership), "Malformed receipt key was accepted");
        applied.Ownership.key = HelperAssociation.CommandKey;
        applied.Ownership.original.text = "\"arbitrary.exe\" \"%1\"";
        Check(!HelperAssociation.Restore(store, applied.Ownership), "Malformed restored command was accepted");
        Check(store.Writes == writes, "Malformed receipt performed a write");
    }

    private static void CommittedWriteFailure()
    {
        MemoryStore store = Selected(true);
        string original = store.Snapshot();
        store.FailAfterWrite = true;
        Throws(delegate { Apply(store, Helper, null); });
        Check(store.Writes == 2 && store.Snapshot() == original, "Partially committed registry write was not rolled back");
    }

    private static void UncertainRecovery()
    {
        foreach (bool readFails in new bool[] { false, true })
        {
            MemoryStore store = Selected(true);
            store.FailAfterWrite = true;
            store.FailReadsAfterWrite = readFails;
            if (!readFails) store.FailBeforeWriteAt = 2;
            bool recovered = false;
            try { Apply(store, Helper, null); }
            catch (HelperAssociation.RecoveryException error)
            {
                recovered = true;
                Check(error.Attempted != null && error.Attempted.Changed,
                    "Lost potentially committed transaction state");
                Check(error.Attempted.Replaced.text == HelperAssociation.Command(Legacy) &&
                    error.Attempted.Written.text == HelperAssociation.Command(Helper),
                    "Recovery state does not describe the exact attempted registration");
                Check(HelperAssociation.ValidReceipt(error.Attempted.Ownership) &&
                    error.WriteError is IOException && error.RestoreError is IOException,
                    "Recovery exception lost ownership or original failure details");
            }
            Check(recovered, "Uncertain restoration did not request target/backup preservation");
            Check(store.Values[HelperAssociation.CommandKey + "|"].text == HelperAssociation.Command(Helper),
                "Fixture did not retain the uncertain new registration");
        }
    }

    private static void UncommittedWrite()
    {
        MemoryStore store = Selected(true);
        string original = store.Snapshot();
        store.IgnoreNextWrite = true;
        Throws(delegate { Apply(store, Helper, null); });
        Check(store.Writes == 1 && store.Snapshot() == original,
            "A silently uncommitted write was accepted or changed the original registration");
    }

    private static void UncommittedRestoration()
    {
        MemoryStore store = Selected(true);
        var applied = Apply(store, Helper, null);
        store.IgnoreNextWrite = true;
        Throws(delegate { HelperAssociation.Rollback(store, applied); });
        Check(Current(store) == HelperAssociation.Command(Helper), "Rollback fixture unexpectedly changed state");
        store.IgnoreNextWrite = true;
        Throws(delegate { HelperAssociation.Restore(store, applied.Ownership); });
        Check(Current(store) == HelperAssociation.Command(Helper), "Restore fixture unexpectedly changed state");
        Check(HelperAssociation.Restore(store, applied.Ownership) && Current(store) == HelperAssociation.Command(Legacy),
            "A subsequent confirmed restoration failed");
    }

    private static int Main(string[] args)
    {
        string root = Path.GetFullPath(args[1]);
        Local = Path.Combine(root, "local data");
        Native = Path.Combine(Local, "FASTMEAN 6.1", "Fastmean.exe");
        Legacy = Path.Combine(Path.GetDirectoryName(Native), "RussianRuntime", "FastmeanRuRunner.exe");
        Helper = Path.Combine(Local, "FASTMEAN Russian UI", "FastmeanRuRunner.exe");
        OtherHelper = Path.Combine(root, "Иная папка с пробелами", "FastmeanRuRunner.exe");
        switch (args[0])
        {
            case "latest": Upgrade(true); break;
            case "classic": Upgrade(false); break;
            case "unrelated": NonHelperChoices(); break;
            case "commands": UnrecognizedCommands(); break;
            case "custom": OwnedCustomAndExplicitNative(); break;
            case "upgrades": IdempotenceAndMigration(); break;
            case "races": BackupFailureAndRaces(); break;
            case "external": ExternalChangesAndInvalidReceipts(); break;
            case "partial": CommittedWriteFailure(); break;
            case "recovery": UncertainRecovery(); break;
            case "uncommitted": UncommittedWrite(); break;
            case "uncommitted-restore": UncommittedRestoration(); break;
            default: throw new Exception("Unknown case");
        }
        Console.WriteLine("PASS " + args[0]);
        return 0;
    }
}
'''


@unittest.skipUnless(os.name == "nt", "Windows .NET Framework association transaction tests")
class AssociationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        if not compiler.is_file():
            raise unittest.SkipTest("Existing .NET Framework 4.x compiler unavailable")
        cls.temporary = tempfile.TemporaryDirectory(prefix="fastmean-association-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        source = cls.root / "AssociationTests.cs"
        source.write_text(HARNESS, encoding="utf-8-sig")
        cls.harness = cls.root / "AssociationTests.exe"
        try:
            compiled = subprocess.run([str(compiler), "/nologo", "/target:exe", "/platform:anycpu",
                "/langversion:5", "/reference:System.Web.Extensions.dll", "/out:" + str(cls.harness),
                str(PROJECT / "src/HelperAssociation.cs"), str(source)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                raise unittest.SkipTest("Windows policy blocked ordinary harness compilation: " + str(error))
            raise
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)

    def run_case(self, case):
        try:
            completed = subprocess.run([str(self.harness), case, str(self.root)],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error:
            if getattr(error, "winerror", None) in POLICY_ERRORS:
                self.skipTest("Windows policy blocked ordinary managed harness: " + str(error))
            raise
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PASS " + case, completed.stdout)

    def test_latest_choice_upgrade_backup_and_uninstall_preserve_original_registry_kind(self):
        self.run_case("latest")

    def test_classic_choice_upgrade_and_uninstall_leave_hash_and_native_registration_alone(self):
        self.run_case("classic")

    def test_missing_unrelated_and_conflicting_choices_never_change_a_default(self):
        self.run_case("unrelated")

    def test_unknown_helper_locations_extra_arguments_and_missing_values_are_preserved(self):
        self.run_case("commands")

    def test_verified_custom_previous_install_and_explicit_native_argument_are_supported(self):
        self.run_case("custom")

    def test_idempotent_upgrades_migration_and_rollback_retain_first_original_registration(self):
        self.run_case("upgrades")

    def test_failed_backup_and_concurrent_choice_or_command_edits_prevent_write(self):
        self.run_case("races")

    def test_uninstall_and_rollback_preserve_external_changes_and_reject_invalid_receipts(self):
        self.run_case("external")

    def test_write_failure_after_commit_restores_only_the_attempted_owned_value(self):
        self.run_case("partial")

    def test_write_and_restoration_failure_retains_exact_recovery_state_for_installer(self):
        self.run_case("recovery")

    def test_write_that_returns_without_committing_is_rejected_by_readback(self):
        self.run_case("uncommitted")

    def test_rollback_and_uninstall_never_report_success_without_confirmed_restoration(self):
        self.run_case("uncommitted-restore")


if __name__ == "__main__":
    unittest.main()
