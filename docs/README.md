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
FASTMEAN-RussianUI-Setup.exe --uninstall --destination "C:\Tools\FastmeanRussianUI" --json
```

`--check` is discovery/payload validation only. It does not install, launch the
native application or test Cyrillic rendering. Keep automation results and
installation receipts private; they can contain machine paths.

Uninstallation is limited to the installer's owned files and shortcuts.
Modified or unknown files and every user circuit must be preserved. File
associations are a user choice through Windows Open with and are not registered
by this installer.

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
python build.py --output dist --version 1.0.0
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
registry settings, install fonts, alter security or change system locale.
