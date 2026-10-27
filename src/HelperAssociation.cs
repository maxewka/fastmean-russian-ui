// SPDX-License-Identifier: LGPL-3.0-only
// Repair only an existing registration of the already selected Russian helper.
// Never creates a default, edits UserChoice/its hash, or starts an application.
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Win32;

internal static class HelperAssociation
{
    internal const string HelperProgId = @"Applications\FastmeanRuRunner.exe";
    internal const string CommandKey = @"Software\Classes\Applications\FastmeanRuRunner.exe\shell\open\command";
    internal const string ChoiceKey = @"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.scm\UserChoice";
    internal const string LatestChoiceKey = @"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.scm\UserChoiceLatest\ProgId";
    private const string Owner = "fastmean-russian-ui-association-v1";

    // Public fields make the bounded ownership record serializable as part of
    // installation.json and the private pre-write backup. Registry kinds are
    // recorded numerically so the original REG_SZ/REG_EXPAND_SZ is restored.
    public sealed class Value
    {
        public string text;
        public int kind;
        public Value() { }
        public Value(string text, int kind) { this.text = text; this.kind = kind; }
    }

    public sealed class Receipt
    {
        public string owner, key, value_name;
        public Value original, installed;
    }

    internal interface IStore
    {
        Value Read(string key, string name);
        void Write(string key, string name, Value value);
    }

    internal sealed class RegistryStore : IStore
    {
        public Value Read(string key, string name)
        {
            using (RegistryKey opened = Registry.CurrentUser.OpenSubKey(key, false))
            {
                if (opened == null) return null;
                object value = opened.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames);
                if (value == null) return null;
                return new Value(value as string, (int)opened.GetValueKind(name));
            }
        }

        public void Write(string key, string name, Value value)
        {
            // This class never creates registry keys or extends the whitelist.
            if (key != CommandKey || name != String.Empty || !StringValue(value))
                throw new InvalidOperationException("Unexpected helper association write.");
            using (RegistryKey opened = Registry.CurrentUser.OpenSubKey(CommandKey, true))
            {
                if (opened == null) throw new IOException("The existing helper registration disappeared.");
                opened.SetValue(String.Empty, value.text, (RegistryValueKind)value.kind);
            }
        }
    }

    internal sealed class Plan
    {
        internal string Status;
        internal Value Current, Desired;
        internal Receipt Previous;
        internal bool Changes { get { return Status == "update_existing_helper"; } }
    }

    internal sealed class Applied
    {
        internal bool Changed;
        internal Receipt Ownership;
        internal Value Replaced, Written;
    }

    internal sealed class RecoveryException : IOException
    {
        // A write may have committed, but its restoration could not be verified.
        // The installer must retain the new helper and the pre-write backup
        // instead of applying ordinary file rollback against an uncertain link.
        internal readonly Applied Attempted;
        internal readonly Exception WriteError, RestoreError;

        internal RecoveryException(Applied attempted, Exception writeError, Exception restoreError)
            : base("The helper association write failed and its restoration could not be verified. " +
                "Preserve the installed helper and its saved association backup.", restoreError)
        {
            Attempted = attempted;
            WriteError = writeError;
            RestoreError = restoreError;
        }
    }

    internal static string Command(string helper)
    {
        return "\"" + HelperPath(helper) + "\" \"%1\"";
    }

    // ownedPriorHelpers must come from a receipt whose ownership and file
    // integrity the caller has already checked, never from untrusted CLI data.
    internal static Plan Inspect(IStore store, string helper, string nativeExe,
        string localApplicationData, string[] ownedPriorHelpers, Receipt previous)
    {
        if (store == null) throw new ArgumentNullException("store");
        string currentHelper = HelperPath(helper);
        string native = AbsolutePath(nativeExe);
        if (!String.Equals(Path.GetFileName(native), "Fastmean.exe", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("The native application must be Fastmean.exe.");
        Plan plan = new Plan { Current = Clone(store.Read(CommandKey, String.Empty)),
            Desired = new Value(Command(currentHelper), (int)RegistryValueKind.String),
            Previous = ValidReceipt(previous) ? Clone(previous) : null };
        if (!SelectedHelper(store)) { plan.Status = "different_or_missing_choice"; return plan; }
        if (!StringValue(plan.Current)) { plan.Status = "missing_or_unsupported_registration"; return plan; }
        if (Same(plan.Current, plan.Desired)) { plan.Status = "already_current"; return plan; }

        HashSet<string> known = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        known.Add(currentHelper);
        known.Add(Path.Combine(Path.GetDirectoryName(native), "RussianRuntime", "FastmeanRuRunner.exe"));
        if (!String.IsNullOrWhiteSpace(localApplicationData))
        {
            string local = AbsolutePath(localApplicationData);
            known.Add(Path.Combine(local, "FASTMEAN Russian UI", "FastmeanRuRunner.exe"));
            foreach (string version in new string[] { "FASTMEAN 6.1", "FASTMEAN 6.0" })
                known.Add(Path.Combine(local, version, "RussianRuntime", "FastmeanRuRunner.exe"));
        }
        if (ownedPriorHelpers != null)
            foreach (string prior in ownedPriorHelpers) known.Add(HelperPath(prior));
        if (plan.Previous != null && Same(plan.Current, plan.Previous.installed))
            known.Add(ParseHelper(plan.Previous.installed.text, native));
        string registered = ParseHelper(plan.Current.text, native);
        if (registered == null || !known.Contains(registered))
        { plan.Status = "unrecognized_helper_registration"; return plan; }
        plan.Status = "update_existing_helper";
        return plan;
    }

    internal static Applied Apply(IStore store, Plan plan, Action<Receipt> saveBackup)
    {
        if (store == null || plan == null) throw new ArgumentNullException("store/plan");
        Applied applied = new Applied { Ownership = Clone(plan.Previous) };
        if (!plan.Changes) return applied;
        if (saveBackup == null) throw new ArgumentNullException("saveBackup");
        if (!SelectedHelper(store) || !Same(store.Read(CommandKey, String.Empty), plan.Current))
            throw new IOException("The .scm application choice or helper command changed during installation; preserved.");
        Receipt ownership = new Receipt { owner = Owner, key = CommandKey, value_name = String.Empty,
            original = Clone(plan.Previous != null && Same(plan.Current, plan.Previous.installed)
                ? plan.Previous.original : plan.Current), installed = Clone(plan.Desired) };
        // The caller must persist this backup before returning. A failed backup
        // prevents the write; installer rollback uses Replaced, while uninstall
        // uses the first original registration retained in Ownership.
        saveBackup(Clone(ownership));
        if (!SelectedHelper(store) || !Same(store.Read(CommandKey, String.Empty), plan.Current))
            throw new IOException("The .scm helper registration changed while saving its backup; preserved.");
        applied.Replaced = Clone(plan.Current);
        applied.Written = Clone(plan.Desired);
        applied.Ownership = ownership;
        try
        {
            store.Write(CommandKey, String.Empty, plan.Desired);
            if (!Same(store.Read(CommandKey, String.Empty), plan.Desired))
                throw new IOException("The helper association write could not be verified.");
        }
        catch (Exception writeError)
        {
            // A registry implementation can report failure after committing.
            // Restore only when its value still equals our attempted write.
            try
            {
                if (Same(store.Read(CommandKey, String.Empty), plan.Desired))
                {
                    store.Write(CommandKey, String.Empty, plan.Current);
                    if (!Same(store.Read(CommandKey, String.Empty), plan.Current))
                        throw new IOException("The previous helper association could not be restored.");
                }
            }
            catch (Exception restoreError)
            {
                applied.Changed = true; // Commit state is uncertain; retain the target.
                throw new RecoveryException(applied, writeError, restoreError);
            }
            throw;
        }
        applied.Changed = true;
        return applied;
    }

    internal static bool Rollback(IStore store, Applied applied)
    {
        if (applied == null || !applied.Changed) return false;
        if (!Same(store.Read(CommandKey, String.Empty), applied.Written)) return false;
        store.Write(CommandKey, String.Empty, applied.Replaced);
        if (!Same(store.Read(CommandKey, String.Empty), applied.Replaced))
            throw new IOException("The previous helper association could not be verified after rollback.");
        return true;
    }

    internal static bool Restore(IStore store, Receipt receipt)
    {
        if (!ValidReceipt(receipt)) return false;
        if (!Same(store.Read(CommandKey, String.Empty), receipt.installed)) return false;
        store.Write(CommandKey, String.Empty, receipt.original);
        if (!Same(store.Read(CommandKey, String.Empty), receipt.original))
            throw new IOException("The original helper association could not be verified after restoration.");
        return true;
    }

    internal static bool ValidReceipt(Receipt receipt)
    {
        if (receipt == null || receipt.owner != Owner || receipt.key != CommandKey ||
            receipt.value_name != String.Empty || !StringValue(receipt.original) ||
            !StringValue(receipt.installed)) return false;
        // Both saved values must remain narrowly shaped helper commands. The
        // optional historical native argument is validated during Inspect.
        return SavedHelperCommand(receipt.original.text) && SavedHelperCommand(receipt.installed.text);
    }

    private static bool SavedHelperCommand(string command)
    {
        string[] parts = QuotedArguments(command);
        if (parts == null || (parts.Length != 2 && parts.Length != 3) || parts[parts.Length - 1] != "%1") return false;
        try
        {
            HelperPath(parts[0]);
            return parts.Length == 2 || String.Equals(Path.GetFileName(AbsolutePath(parts[1])),
                "Fastmean.exe", StringComparison.OrdinalIgnoreCase);
        }
        catch (ArgumentException) { return false; }
        catch (NotSupportedException) { return false; }
    }

    private static bool SelectedHelper(IStore store)
    {
        Value classic = store.Read(ChoiceKey, "ProgId");
        Value latest = store.Read(LatestChoiceKey, "ProgId");
        // Conflicting Windows-version representations are not guessed at.
        if (classic != null && (!StringValue(classic) || !String.Equals(classic.text, HelperProgId, StringComparison.OrdinalIgnoreCase))) return false;
        if (latest != null && (!StringValue(latest) || !String.Equals(latest.text, HelperProgId, StringComparison.OrdinalIgnoreCase))) return false;
        return classic != null || latest != null;
    }

    private static string ParseHelper(string command, string native)
    {
        string[] parts = QuotedArguments(command);
        if (parts == null || (parts.Length != 2 && parts.Length != 3) || parts[parts.Length - 1] != "%1") return null;
        try
        {
            if (parts.Length == 3 && !String.Equals(AbsolutePath(parts[1]), native, StringComparison.OrdinalIgnoreCase)) return null;
            return HelperPath(parts[0]);
        }
        catch (ArgumentException) { return null; }
        catch (NotSupportedException) { return null; }
    }

    private static string[] QuotedArguments(string command)
    {
        if (String.IsNullOrEmpty(command)) return null;
        List<string> parts = new List<string>();
        int index = 0;
        while (index < command.Length)
        {
            while (index < command.Length && command[index] == ' ') index++;
            if (index == command.Length) break;
            if (command[index++] != '"') return null;
            int start = index;
            while (index < command.Length && command[index] != '"')
            { if (Char.IsControl(command[index])) return null; index++; }
            if (index == command.Length) return null;
            parts.Add(command.Substring(start, index++ - start));
            if (index < command.Length && command[index] != ' ') return null;
            if (parts.Count > 3) return null;
        }
        return parts.ToArray();
    }

    private static string HelperPath(string path)
    {
        string full = AbsolutePath(path);
        if (!String.Equals(Path.GetFileName(full), "FastmeanRuRunner.exe", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Expected FastmeanRuRunner.exe.");
        return full;
    }

    private static string AbsolutePath(string path)
    {
        if (String.IsNullOrWhiteSpace(path)) throw new ArgumentException("Expected an absolute file path.");
        foreach (char character in path)
            if (character == '"' || Char.IsControl(character)) throw new ArgumentException("Invalid path character.");
        string root = Path.GetPathRoot(path);
        if (String.IsNullOrEmpty(root) || root.Length < 2 || root.EndsWith(":", StringComparison.Ordinal))
            throw new ArgumentException("Expected an absolute file path.");
        return Path.GetFullPath(path);
    }

    private static bool StringValue(Value value)
    {
        return value != null && value.text != null &&
            (value.kind == (int)RegistryValueKind.String || value.kind == (int)RegistryValueKind.ExpandString);
    }

    private static bool Same(Value left, Value right)
    {
        return left != null && right != null && left.kind == right.kind && left.text == right.text;
    }

    private static Value Clone(Value value) { return value == null ? null : new Value(value.text, value.kind); }
    private static Receipt Clone(Receipt receipt)
    {
        return receipt == null ? null : new Receipt { owner = receipt.owner, key = receipt.key,
            value_name = receipt.value_name, original = Clone(receipt.original), installed = Clone(receipt.installed) };
    }
}
