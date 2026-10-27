# Working on FASTMEAN Russian UI

This is a separate optional Russian-launch helper and its one-click installer.
FASTMEAN itself is proprietary, separately installed and never part of this
repository. Read README.md, docs/README.md and the relevant source before edits.
The FASTMEAN MCP adapter is a separate project and works without this helper.

## Installation and user files

- An explicit request to install this helper authorizes its normal reversible
  per-user installation. Inspect discovery and `--check` results first. Do not
  repeatedly ask for the same authorization.
- Do not change Windows locale, code pages, timezone, registry, PATH, file
  associations, PowerShell execution policy, App Control, Smart App Control,
  antivirus or UAC. Do not add policy-bypass switches, elevation fallbacks or
  alternate loaders. Stop and report the stated policy reason if execution is
  blocked.
- Preserve the separately installed native application and every user SCM.
  Do not restart or close user-owned processes with unsaved work. The installer
  must not automatically launch FASTMEAN. An explicit Open button may launch it
  only when the user chooses that action.
- Keep installation owned and reversible. Uninstallation removes only owned,
  unchanged files/shortcuts; preserve changed or unknown files and all circuits.
- Helper paths may contain spaces and Cyrillic. A sole SCM argument is a document
  passed by Windows Open with, never the target executable.

## Source and release boundaries

- All authored source is LGPL-3.0-only. Preserve upstream Locale Emulator
  attribution, full GPLv3/LGPLv3 license texts and modifications in NOTICE.md.
- Git contains reviewed source, docs and tests. Generated EXE, DLL, ZIP, runtime
  target configurations, logs and private absolute paths stay ignored.
- The user explicitly requested a downloadable installer EXE. Release assets
  may contain this licensed helper/installer EXE and verified, unmodified open
  source Locale Emulator DLLs. Include corresponding source, licenses and
  provenance with releases; keep dynamic helper libraries replaceable.
- Never publish FASTMEAN native executables/libraries, fonts, manuals, user SCMs,
  installation logs, credentials or unrelated proprietary material. The source
  repository and installer must not download FASTMEAN.
- Retrieve open source runtime files only from the pinned official upstream
  release and verify expected SHA256 values before packaging or installation.
- No native application GUI or Locale Emulator loading is required for tests.
  Use disposable nonexecutable text fixtures and the pure resolver or `--check`.
  Report genuine policy skips; do not pretend a launch or Russian-input check
  succeeded when it did not run.

## Verification

Use the existing Windows .NET Framework 4.x compiler and Python 3.12+ for build
and test orchestration. Keep runner code compatible with Framework 4 and C# 5.

```text
python -m unittest discover -s tests -v
python build.py --output dist --version 1.0.0
```

Linux CI may inspect source but must honestly skip Windows compiler tests.
Do not replace native compatibility evidence with fabricated solver/UI results.
