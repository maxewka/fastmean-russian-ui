// SPDX-License-Identifier: LGPL-3.0-only
// Pure path resolution for the optional FASTMEAN Russian UI helper.
// No native loading, process launches, registry access or Windows changes.
using System;
using System.IO;
using System.Text;

internal static class FastmeanLaunchPaths
{
    private const string ConfigName = "FASTMEAN_EXE.txt";
    private const string Usage =
        "Usage: FastmeanRuRunner.exe [\"full path to Fastmean.exe\"] [\"document.scm\"]. " +
        "A document.scm may also be supplied by itself through Open with.";

    internal sealed class Request
    {
        internal string Target;
        internal string Document;

        internal Request(string target, string document)
        {
            Target = target;
            Document = document;
        }
    }

    internal static Request Resolve(string[] args, string baseDirectory,
        string localApplicationData)
    {
        if (args == null) throw new ArgumentNullException("args");
        if (args.Length > 2) throw new ArgumentException(Usage);

        string target = null;
        string document = null;
        if (args.Length == 2)
        {
            target = ValidateTarget(args[0]);
            document = ValidateDocument(args[1]);
        }
        else if (args.Length == 1)
        {
            string supplied = FullPath(args[0], "The supplied path");
            if (String.Equals(Path.GetExtension(supplied), ".scm", StringComparison.OrdinalIgnoreCase))
                document = ValidateDocument(supplied);
            else
                target = ValidateTarget(supplied);
        }

        // Relative CLI paths are resolved above, before the runner changes its
        // working directory. An explicit target never reads the configuration.
        if (target == null) target = DiscoverTarget(baseDirectory, localApplicationData);
        return new Request(target, document);
    }

    private static string FullPath(string value, string label)
    {
        if (String.IsNullOrWhiteSpace(value))
            throw new ArgumentException(label + " is empty. " + Usage);
        for (int index = 0; index < value.Length; index++)
        {
            if (value[index] == '"' || Char.IsControl(value[index]))
                throw new ArgumentException(label + " must not contain quotes or control characters.");
        }
        try { return Path.GetFullPath(value); }
        catch (ArgumentException error)
        {
            throw new ArgumentException(label + " is not a valid file path. " + error.Message, error);
        }
        catch (NotSupportedException error)
        {
            throw new ArgumentException(label + " is not a supported file path. " + error.Message, error);
        }
    }

    private static string ValidateTarget(string value)
    {
        string target = FullPath(value, "The FASTMEAN executable path");
        if (!String.Equals(Path.GetFileName(target), "Fastmean.exe", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("The executable must be named Fastmean.exe. " + Usage);
        if (!File.Exists(target))
            throw new FileNotFoundException(
                "FASTMEAN executable was not found. Supply the full path to an existing Fastmean.exe: " + target,
                target);
        return target;
    }

    private static string ValidateDocument(string value)
    {
        string document = FullPath(value, "The document path");
        if (!String.Equals(Path.GetExtension(document), ".scm", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("The document must be a FASTMEAN .scm file. " + Usage);
        if (!File.Exists(document))
            throw new FileNotFoundException("The FASTMEAN .scm document was not found: " + document, document);
        return document;
    }

    private static bool IsAbsolutePath(string value)
    {
        if (!Path.IsPathRooted(value)) return false;
        string root = Path.GetPathRoot(value);
        // On Windows both C:relative and \root-relative are rooted but depend
        // on the caller's current drive/directory. The target config must not.
        return !String.IsNullOrEmpty(root) && root.Length > 1 && !root.EndsWith(":", StringComparison.Ordinal);
    }

    private static string ConfiguredTarget(string config)
    {
        try
        {
            string contents = File.ReadAllText(config, new UTF8Encoding(false, true));
            string target = null;
            using (StringReader reader = new StringReader(contents))
            {
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (String.IsNullOrWhiteSpace(line)) continue;
                    if (target != null)
                        throw new InvalidDataException("Expected exactly one nonempty line.");
                    target = line;
                }
            }
            if (target == null)
                throw new InvalidDataException("Expected one nonempty line containing the executable path.");
            // Validate the untrimmed line so tabs/control characters cannot be
            // silently accepted as surrounding whitespace.
            string checkedPath = FullPath(target, "The configured executable path");
            if (!IsAbsolutePath(target))
                throw new InvalidDataException("The executable path must be absolute, for example C:\\Apps\\FASTMEAN\\Fastmean.exe.");
            return ValidateTarget(checkedPath);
        }
        catch (InvalidDataException error)
        {
            throw ConfigError(config, error);
        }
        catch (IOException error)
        {
            throw ConfigError(config, error);
        }
        catch (UnauthorizedAccessException error)
        {
            throw ConfigError(config, error);
        }
        catch (ArgumentException error)
        {
            throw ConfigError(config, error);
        }
        catch (NotSupportedException error)
        {
            throw ConfigError(config, error);
        }
    }

    private static InvalidDataException ConfigError(string config, Exception error)
    {
        return new InvalidDataException("Invalid FASTMEAN target configuration " + config + ". " +
            "Set " + ConfigName + " to one UTF-8 line with the full path to your existing Fastmean.exe. " +
            error.Message, error);
    }

    private static string DiscoverTarget(string baseDirectory, string localApplicationData)
    {
        string directory = FullPath(baseDirectory, "The launcher directory");
        string directoryRoot = Path.GetPathRoot(directory);
        while (directory.Length > directoryRoot.Length &&
            (directory[directory.Length - 1] == Path.DirectorySeparatorChar ||
             directory[directory.Length - 1] == Path.AltDirectorySeparatorChar))
            directory = directory.Substring(0, directory.Length - 1);
        string config = Path.Combine(directory, ConfigName);
        if (File.Exists(config) || Directory.Exists(config)) return ConfiguredTarget(config);

        string nearby = Path.Combine(directory, "Fastmean.exe");
        if (File.Exists(nearby)) return ValidateTarget(nearby);
        DirectoryInfo parent = Directory.GetParent(directory);
        if (parent != null)
        {
            nearby = Path.Combine(parent.FullName, "Fastmean.exe");
            if (File.Exists(nearby)) return ValidateTarget(nearby);
        }
        if (!String.IsNullOrWhiteSpace(localApplicationData))
        {
            string local = FullPath(localApplicationData, "The local application data directory");
            foreach (string version in new string[] { "FASTMEAN 6.1", "FASTMEAN 6.0" })
            {
                string standard = Path.Combine(Path.Combine(local, version), "Fastmean.exe");
                if (File.Exists(standard)) return ValidateTarget(standard);
            }
        }
        throw new FileNotFoundException("FASTMEAN executable was not found. " +
            "Pass the full path to Fastmean.exe, or create " + config +
            " containing that absolute path. Install FASTMEAN separately if it is absent.");
    }
}
