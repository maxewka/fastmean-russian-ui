# Build, runtime and installation notes

This repository packages only the optional Russian-launch helper. The native
FASTMEAN installation remains separate. Normal installation is per user and
does not require Python on the receiving computer.

## Installer

Launching `FASTMEAN-RussianUI-Setup.exe` performs the normal installation and
shows its result. An optional Open action starts the helper only after the user
chooses it. Existing FASTMEAN windows and unsaved documents are left alone.

Supported automation interface:

```text
FASTMEAN-RussianUI-Setup.exe --check
FASTMEAN-RussianUI-Setup.exe --install --app-dir "C:\Apps\FASTMEAN" --destination "C:\Tools\FastmeanRussianUI" --no-shortcuts --json
FASTMEAN-RussianUI-Setup.exe --install --no-association-update --json
FASTMEAN-RussianUI-Setup.exe --uninstall --destination "C:\Tools\FastmeanRussianUI" --json
```

`--check` validates discovery/payload and reports the existing helper-association
plan (`file_association_status`, `file_association_would_change`) without writes.
It does not install, launch the native application or test Cyrillic rendering. Keep automation results and
installation receipts private; they can contain machine paths.

Uninstallation is limited to the installer's owned files and shortcuts.
Modified or unknown files and every user circuit must be preserved. File
associations remain a user choice through Windows Open with. On an upgrade the
installer repairs only the existing current-user
`Software\Classes\Applications\FastmeanRuRunner.exe\shell\open\command` when
`.scm` already selects that helper and the old command matches a recognized
helper installation. Native FASTMEAN and other application choices are retained;
`UserChoice`, `UserChoiceLatest` and their hashes are never written. The command
quotes both the new helper path and `%1`, preserving spaces and Cyrillic.

Before the write, a durable private backup is saved in the installation's
`association-backups/` directory and ownership is recorded in `installation.json`.
Upgrade rollback restores the immediately preceding value. Uninstall restores
the original command only if it still equals the installer's owned command;
later user changes and private backups are preserved. `--no-association-update`
opts out of association writes during installation or removal. JSON results report the actual change and
backup path, rather than claiming a default was created for a different app.

Run the downloaded installer normally from Windows Explorer. A packaged host's
redirected registry/AppData view can differ from Explorer's user settings, so a
headless check in that host alone does not prove the desktop association changed.

Both EXEs contain an original helper icon built from the licensed source in
`assets/`. The completion window and desktop shortcut read the separately
installed FASTMEAN icon at runtime, with the embedded helper icon as fallback.
No native FASTMEAN image is included in the payload or release source.

## Runner resolution

The installed `FASTMEAN_EXE.txt` contains one UTF-8 line with the absolute path
to the existing `Fastmean.exe`. An explicit EXE argument takes precedence over
this configuration. A present invalid configuration fails clearly rather than
silently choosing another application.

When the configuration is absent, discovery checks `Fastmean.exe` beside the
helper, its parent directory, then standard per-user `FASTMEAN 6.1` and
`FASTMEAN 6.0` directories in that order. CLI-relative paths resolve before the
helper changes its working directory. Spaces and Unicode are retained.

Supported forms:

```text
FastmeanRuRunner.exe
FastmeanRuRunner.exe "C:\Circuits\фильтр.scm"
FastmeanRuRunner.exe "C:\Apps\FASTMEAN\Fastmean.exe"
FastmeanRuRunner.exe "C:\Apps\FASTMEAN\Fastmean.exe" "C:\Circuits\example.scm"
FastmeanRuRunner.exe --check "C:\Circuits\example.scm"
```

The check path is separate from native-loader code. Tests compile the actual
x86 WinExe and supply text fixtures named EXE/DLL/SCM; they must never load those
files as native code. The pure resolver harness needs no Locale Emulator files.

## Build and verification

```text
python -m unittest discover -s tests -v
python build.py --output dist --version 1.0.1
```

The builder uses the existing Windows .NET Framework compiler, C# 5-compatible
source and pinned official Locale Emulator runtime hashes. It never fetches
FASTMEAN. Release artifacts include the installer EXE, source bundle, licensing,
provenance and SHA256 checksums. Keep generated binaries outside Git.

CI builds and runs non-native checks on Windows. A successful build or
`--check` does not prove that local Windows policies permit a native locale
launch or that typing into FASTMEAN was visually verified. Report that evidence
separately when an actual user-authorized runtime check has occurred.

The helper sets Russian ANSI/OEM code pages and charset for its native child
through Locale Emulator. Its two exact file-type-label registry-read overrides
exist only in process memory. The runner preserves timezone and does not write
registry settings, install fonts, alter security or change system locale. The
installer's narrowly owned command repair above is separate from the runner.
