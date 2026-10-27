# Attribution and release contents

FASTMEAN Russian UI is an optional helper for a separately installed FASTMEAN.
This source is distributed under **LGPL-3.0-only**. The complete LGPLv3 text is
in LICENSE and licenses/COPYING.LESSER; its GPLv3 terms are in licenses/COPYING.

`src/FastmeanRuRunner.cs` adapts the native loader ABI and registry-read
redirection structures from the Locale Emulator v2.5.0.1 project by the
[Locale Emulator contributors](https://github.com/xupefei/Locale-Emulator/tree/v2.5.0.1):

- [LoaderWrapper.cs](https://github.com/xupefei/Locale-Emulator/blob/v2.5.0.1/LEProc/LoaderWrapper.cs)
- [LERegistryRedirector.cs](https://github.com/xupefei/Locale-Emulator/blob/v2.5.0.1/LEProc/LERegistryRedirector.cs)
- [Locale Emulator v2.5.0.1 source](https://github.com/xupefei/Locale-Emulator/tree/v2.5.0.1)
- [Locale Emulator core source](https://github.com/xupefei/Locale-Emulator-Core)

Local changes include a minimal x86 runner, Russian ANSI/OEM/charset settings,
timezone preservation, two exact in-memory file-type-label read replacements,
SCM-only Windows Open with arguments, validated executable discovery,
configuration and no-launch diagnostic checks. This standalone project adds a
per-user one-click installer and source/release build orchestration. It was
separated from FASTMEAN MCP on 2026-10-27.

The builder uses the unmodified official v2.5.0.1 Locale Emulator release and
verifies pinned SHA256 values before packaging `LoaderDll.dll` and
`LocaleEmulator.dll`. Generated binaries are not tracked by Git. Licensed release
assets may include these two open source DLLs and the helper/installer EXEs,
together with corresponding source, license texts, provenance and checksums.
Runtime libraries remain dynamically replaceable with ABI-compatible builds.

FASTMEAN native executables, solvers, fonts, manuals and user circuits are not
part of this repository or its releases. FASTMEAN is separately licensed and is
not covered by this helper's license. No compatibility guarantee overrides an
enforced Windows policy; blocked components require the owner's approved
deployment process, without security-policy changes by this project.
