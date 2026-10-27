# Third-party runtime and source provenance

FASTMEAN Russian UI uses the Locale Emulator native runtime. The two libraries
are dynamically loaded from the installed helper directory; ABI-compatible
replacements remain possible. This project does not convey the separately
licensed FASTMEAN application.

## Licensed components

| Component | Source and license |
| --- | --- |
| FASTMEAN Russian UI runner, path resolver and installer | This repository, LGPL-3.0-only; see [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE). |
| Runner ABI and registry-read structures adapted from Locale Emulator | Locale Emulator `LEProc/LoaderWrapper.cs` and `LEProc/LERegistryRedirector.cs` at the revision below; upstream identifies these source files as LGPL-3.0. |
| `LoaderDll.dll` and `LocaleEmulator.dll` | Unmodified files from the official Locale Emulator v2.5.0.1 binary release. Core source is published separately under LGPL-3.0 in `Loader`, `LoaderDll` and `LocaleEmulator`. |

Full license texts accompany the distribution: [GPLv3](licenses/COPYING) and
[LGPLv3](licenses/COPYING.LESSER). Preserve upstream notices in copied source.
The helper's license does not grant rights to redistribute FASTMEAN itself.

## Runtime pin

Official release:
[Locale Emulator v2.5.0.1](https://github.com/xupefei/Locale-Emulator/releases/tag/v2.5.0.1),
published 2021-08-25. The release archive is
[Locale.Emulator.2.5.0.1.zip](https://github.com/xupefei/Locale-Emulator/releases/download/v2.5.0.1/Locale.Emulator.2.5.0.1.zip).

| File | Bytes | SHA256 |
| --- | ---: | --- |
| Official release ZIP | 154135 | `808ff584426d52cc775ad6406da00622f454be95bd4c8fbca42eef4b7235ad5c` |
| `LoaderDll.dll` | 6144 | `82fae0f44f4ca0c9c37907df74cef2415eeb5fae1cf8d4f36f34ffcaf7e3cc0c` |
| `LocaleEmulator.dll` | 63488 | `c79c175fdad174aa46a72197d148316299a56f950aaab1b84930d09ee1084a88` |

The installer packages only these two verified runtime libraries. It does not
include the upstream updater, shell-extension installer or GUI executables.

## Immutable source pins

The upstream projects publish their source separately. Release source assets
include the relevant source snapshots with these immutable identifiers:

| Project | Revision | Source ZIP SHA256 |
| --- | --- | --- |
| Locale Emulator v2.5.0.1 | `db03abf6914beeca09ee975120ff5ce2091c8dca` | `c0763b7e12a9b7b4daf172ce8790afcb0bc702014c8f05186c83f6b65f1c5c39` |
| Locale Emulator Core | `ae7160dc5deb97947396abcd784f9b98b6ee38b3` | `80040eab31970ec1381bfa57a2c00b507501487efac0220dbd3cd8fb37007941` |

Source downloads:

- [Locale Emulator at the release revision](https://codeload.github.com/xupefei/Locale-Emulator/zip/db03abf6914beeca09ee975120ff5ce2091c8dca).
- [Locale Emulator Core at the pinned revision](https://codeload.github.com/xupefei/Locale-Emulator-Core/zip/ae7160dc5deb97947396abcd784f9b98b6ee38b3).
- [Upstream Core build and license information](https://github.com/xupefei/Locale-Emulator-Core/blob/ae7160dc5deb97947396abcd784f9b98b6ee38b3/README.md).

The release tag directly identifies the Locale Emulator revision. The Core
association is based on the published repository history: the pinned revision
merged the Windows 11 fix at 2021-08-23 18:43:41 UTC; the distributed libraries'
PE build timestamps are 18:52:22 and 18:54:00 UTC that day. No later Core commit
appears in the archived repository. This is a documented source-selection
inference, not an upstream binary-to-commit attestation or a demonstrated
byte-for-byte native rebuild. The binary hashes above identify the actual
unmodified files supplied.

## Release source contents

The source asset accompanies the installer on the same release page and
contains this project's preferred source, build/test scripts, notices and
licenses. It also contains the selected upstream source and native project
files described in [the source-bundle notes](docs/SOURCE-BUNDLE.md).

The Core repository also contains Microsoft toolchain/SDK material. Its README
expressly identifies modified Visual Studio tools and Windows Driver Kit
archives. `_Headers/intrin.h` carries a Microsoft copyright notice. This project
does not redistribute `_Compilers`, `_Libs`, `_WDK` or `_Headers`, nor does it
claim those items are LGPL merely because they are present upstream. Native
development tools and SDKs must be obtained separately under their own terms.
The source asset excludes generated export-object files and unrelated upstream
icons, signing keys and shell-extension resources.

LGPL/GPL source and relinking conditions remain applicable to distribution of
covered object code. Providing a reproducible source ZIP is distinct from proving
a native DLL rebuild or certifying every build prerequisite. Preserve these
limits in release notes; do not describe an unperformed native rebuild as tested.
