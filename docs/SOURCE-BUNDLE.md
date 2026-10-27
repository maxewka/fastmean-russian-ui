# Source bundle construction and verification

This note specifies the release source asset independently of the installer
payload. The installer contains the verified open source runtime DLLs and this
project's compiled helper; the source asset contains preferred modification
sources, build/test scripts, licensing and provenance.

## Source input pins

| Input | Immutable URL | SHA256 |
| --- | --- | --- |
| Locale Emulator | `https://codeload.github.com/xupefei/Locale-Emulator/zip/db03abf6914beeca09ee975120ff5ce2091c8dca` | `c0763b7e12a9b7b4daf172ce8790afcb0bc702014c8f05186c83f6b65f1c5c39` |
| Locale Emulator Core | `https://codeload.github.com/xupefei/Locale-Emulator-Core/zip/ae7160dc5deb97947396abcd784f9b98b6ee38b3` | `80040eab31970ec1381bfa57a2c00b507501487efac0220dbd3cd8fb37007941` |

The source ZIP downloads measured 179918 and 28727365 bytes respectively on
2026-10-27. Verify archive SHA256 before reading selected members. Do not bundle
the complete downloaded archives: the Core archive contains non-source
Microsoft toolchain material. Download/cache location and included release
members must be separate concerns.

## Allowlisted members

Own project:

- `src/*.cs`, `src/*.manifest`, `build.py`, `tests/*.py`;
- `README.md`, `NOTICE.md`, `THIRD_PARTY.md`, `AGENTS.md`, license texts,
  technical docs and the build workflow;
- generated public version/source-manifest records containing no private paths.

Locale Emulator source at the pinned release revision:

- `COPYING`, `COPYING.LESSER`, `README.md`;
- source/project text from `LEProc` and `LECommonLibrary`: `.cs`, `.csproj`,
  `.resx`, `.xml`, `.config`, `.manifest` and `.settings`;
- the preserved `LocaleEmulator.sln`, with a note that this upstream solution
  also references unrelated projects outside the selected source subset.

This selection contains 28 files and 146901 bytes. It provides the original
runner ABI/registry structures and their supporting source. It is not advertised
as a complete distribution of every upstream GUI/updater/shell-extension project.
Our modified runner is built from this repository's complete `src` directory.

Locale Emulator Core at the pinned revision:

- all source/build text under `Loader`, `LoaderDll` and `LocaleEmulator`,
  including `.sln`, `.vcxproj`, `.vcxproj.filters`, `.def`, headers, C++ and
  generator scripts;
- `README.md`, `LICENSE-GPL.txt` and `LICENSE-LGPL.txt`;
- exclude the compiled `LoaderDll/LoaderDll.exp` export object.

This selection contains 37 files and 2289012 bytes. In particular it includes
`LocaleEmulator/ml.h` and `ml.cpp`, not just the short loader wrapper. Original
bytes and license notices should remain unchanged in the `upstream` portion.

Never include `.git`, caches, downloaded binary/source archives, runtime target
configuration, private logs, SCMs, native FASTMEAN files or arbitrary files
found by recursively walking an output directory. Upstream `_Compilers`,
`_Libs`, `_WDK` and `_Headers` stay excluded. The two allowed runtime DLLs belong
to the installer payload, not this source tree selection.

## Deterministic ZIP and audit record

Sort archive paths, use `/` separators, fixed ZIP member timestamps and fixed
file modes, and avoid host usernames, absolute paths or build-time timestamps
in source contents. Retain the upstream bytes rather than rewriting their
newlines. Reject absolute/traversal/link member names when reading an archive.

Record each selected file's size and SHA256, the upstream revision and archive
hash, the excluded categories, and this project's source revision/version.
Place that public manifest in the source asset. Publish SHA256 for the completed
installer and source asset on the same release page. Source-ZIP determinism does
not imply a byte-identical C# or native DLL rebuild.

## Native rebuild prerequisites and limits

The upstream Core README describes Visual Studio 2013/2015. The pinned project
files additionally specify `v141`/`v141_xp`, Windows SDK 8.1/10.0.16299 and paths
to WDK 7.1/8.0 headers/import libraries. Its build settings reference a modified
Microsoft toolchain and import libraries outside the three licensed source
directories. Those prerequisites are not supplied by this project.

Obtain development tools through Microsoft's own licensing/download channels:
[older Visual Studio downloads](https://visualstudio.microsoft.com/vs/older-downloads/)
and [other WDK downloads](https://learn.microsoft.com/en-us/windows-hardware/drivers/other-wdk-downloads).
Use appropriately licensed local toolchain/SDK headers and import libraries and
adapt their locations when rebuilding. Such an adapted native rebuild has not
been demonstrated here. Do not claim the pinned source/PE timestamp association
is cryptographic evidence that upstream binaries were built without unpublished
changes; see [the provenance statement](../THIRD_PARTY.md).

The full [GPLv3 source provisions](../licenses/COPYING) and
[LGPLv3 combined-work provisions](../licenses/COPYING.LESSER) govern covered
distributions. The helper uses external replaceable DLL files and publishes its
complete source/build instructions. Preserve notices, source availability and
the ability to use an interface-compatible modified library; packaging checks
must not become a restriction on that replacement at runtime.
