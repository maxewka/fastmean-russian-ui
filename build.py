"""Build a self-contained per-user installer; no native FASTMEAN is bundled."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from assets.make_icon import icon_bytes

ROOT = Path(__file__).resolve().parent
RUNTIME_URL = "https://github.com/xupefei/Locale-Emulator/releases/download/v2.5.0.1/Locale.Emulator.2.5.0.1.zip"
RUNTIME_SHA256 = "808ff584426d52cc775ad6406da00622f454be95bd4c8fbca42eef4b7235ad5c"
DLL_HASHES = {
    "LoaderDll.dll": "82fae0f44f4ca0c9c37907df74cef2415eeb5fae1cf8d4f36f34ffcaf7e3cc0c",
    "LocaleEmulator.dll": "c79c175fdad174aa46a72197d148316299a56f950aaab1b84930d09ee1084a88",
}
SOURCE_PINS = {
    "Locale-Emulator": "db03abf6914beeca09ee975120ff5ce2091c8dca",
    "Locale-Emulator-Core": "ae7160dc5deb97947396abcd784f9b98b6ee38b3",
}
SOURCE_HASHES = {
    "Locale-Emulator": "c0763b7e12a9b7b4daf172ce8790afcb0bc702014c8f05186c83f6b65f1c5c39",
    "Locale-Emulator-Core": "80040eab31970ec1381bfa57a2c00b507501487efac0220dbd3cd8fb37007941",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str, destination: Path, expected: str | None = None) -> bytes:
    if destination.exists():
        data = destination.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "FASTMEAN-RussianUI-build"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("Upstream archive exceeds the bounded download size")
        if expected and digest(data) != expected:
            raise ValueError("Upstream archive SHA256 mismatch; nothing will be compiled")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    if expected and digest(data) != expected:
        raise ValueError(f"SHA256 mismatch in {destination.name}; remove the invalid build cache explicitly")
    return data


def archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            target.writestr(info, data)
    return buffer.getvalue()


def own_sources() -> dict[str, bytes]:
    names = {"README.md", "LICENSE", "NOTICE.md", "AGENTS.md", "THIRD_PARTY.md", ".gitignore", "build.py"}
    paths = [ROOT / name for name in names if (ROOT / name).is_file()]
    for folder in ("src", "licenses", "docs", "tests", ".github", "assets"):
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".exe", ".dll"})
    return {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in paths}


def upstream_sources(cache: Path) -> tuple[dict[str, bytes], dict]:
    files, provenance = {}, {}
    for repository, commit in SOURCE_PINS.items():
        url = f"https://codeload.github.com/xupefei/{repository}/zip/{commit}"
        raw = fetch(url, cache / (repository + "-" + commit + ".zip"), SOURCE_HASHES[repository])
        provenance[repository] = {"revision": commit, "url": url, "archive_sha256": digest(raw)}
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            for entry in source.infolist():
                parts = Path(entry.filename).parts[1:]
                if not parts or entry.is_dir():
                    continue
                relative = Path(*parts)
                # Microsoft toolchains/SDK binaries supplied by upstream are
                # prerequisites, not redistributable source assets of our app.
                if repository.endswith("-Core"):
                    if parts[0] not in {"Loader", "LoaderDll", "LocaleEmulator", "README.md", "LICENSE-GPL.txt", "LICENSE-LGPL.txt"}:
                        continue
                else:
                    if parts[0] not in {"LEProc", "LECommonLibrary", "COPYING", "COPYING.LESSER", "README.md", "LocaleEmulator.sln"}:
                        continue
                    if len(parts) > 1 and relative.suffix.lower() not in {".cs", ".csproj", ".config", ".resx", ".settings", ".xml", ".manifest"}:
                        continue
                if relative.suffix.lower() in {".exe", ".dll", ".lib", ".obj", ".exp", ".pdb", ".7z", ".zip", ".pdf", ".ttf", ".fon"}:
                    continue
                if entry.file_size > 4 * 1024 * 1024:
                    raise ValueError("Unexpected oversized upstream source file")
                files[f"upstream/{repository}/{relative.as_posix()}"] = source.read(entry)
    return files, provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", default="1.0.1")
    parser.add_argument("--runtime-archive", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        parser.error("version must contain three numeric components")
    if os.name != "nt":
        parser.error("Use Windows with its existing .NET Framework compiler")
    compiler = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
    if not compiler.is_file():
        parser.error("Existing .NET Framework 4.x C# compiler was not found")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / ".cache"
    runtime = (args.runtime_archive.read_bytes() if args.runtime_archive else
               fetch(RUNTIME_URL, cache / "Locale.Emulator.2.5.0.1.zip", RUNTIME_SHA256))
    if digest(runtime) != RUNTIME_SHA256:
        raise ValueError("Pinned runtime archive SHA256 mismatch")
    sources = own_sources()
    upstream, provenance = upstream_sources(cache)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    source_notice = {
        "version": args.version, "runtime_release": RUNTIME_URL,
        "runtime_archive_sha256": RUNTIME_SHA256, "upstream_sources": provenance,
        "project_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "project_sources_dirty": bool(status.stdout.strip()),
        "core_revision_relation": "Final upstream source is supplied; timestamp relation to release DLLs is documented, not a reproducible-build attestation",
        "native_fastmean_included": False,
    }
    sources.update(upstream)
    source_notice["files"] = [{"path": name, "size": len(data), "sha256": digest(data)}
                              for name, data in sorted(sources.items())]
    sources["SOURCE-PROVENANCE.json"] = (json.dumps(source_notice, indent=2) + "\n").encode()
    source_zip = archive(sources)
    with tempfile.TemporaryDirectory(prefix="fastmean-russianui-build-") as temporary:
        stage = Path(temporary)
        icon_path = stage / "FastmeanRussianUI.ico"
        icon_path.write_bytes(icon_bytes())
        assembly_info = stage / "AssemblyInfo.cs"
        assembly_info.write_text('using System.Reflection;\n'
            '[assembly: AssemblyTitle("FASTMEAN Russian UI")]\n'
            '[assembly: AssemblyDescription("Per-user Russian locale support for separately installed FASTMEAN")]\n'
            f'[assembly: AssemblyVersion("{args.version}.0")]\n'
            f'[assembly: AssemblyFileVersion("{args.version}.0")]\n', encoding="utf-8")
        runner = stage / "FastmeanRuRunner.exe"
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x86", "/optimize+",
                        "/reference:System.Windows.Forms.dll", "/out:" + str(runner),
                        "/win32icon:" + str(icon_path),
                        "/win32manifest:" + str(ROOT / "src/FastmeanRuRunner.manifest"),
                        str(ROOT / "src/FastmeanRuRunner.cs"), str(ROOT / "src/FastmeanLaunchPaths.cs"), str(assembly_info)], check=True)
        payload = {"FastmeanRuRunner.exe": runner.read_bytes()}
        with zipfile.ZipFile(io.BytesIO(runtime)) as source:
            for name, expected in DLL_HASHES.items():
                matches = [e for e in source.infolist() if e.filename == name]
                if len(matches) != 1:
                    raise ValueError("Unexpected upstream runtime structure")
                data = source.read(matches[0])
                if digest(data) != expected:
                    raise ValueError(name + " SHA256 mismatch")
                payload[name] = data
        for name, data in own_sources().items():
            payload["source/" + name] = data
        payload["SOURCE-PROVENANCE.json"] = sources["SOURCE-PROVENANCE.json"]
        manifest = {"format": "fastmean-russianui-payload-v1", "version": args.version,
                    "files": [{"name": name, "sha256": digest(data), "size": len(data)}
                              for name, data in sorted(payload.items())]}
        payload["payload-manifest.json"] = json.dumps(manifest, separators=(",", ":")).encode()
        payload_path = stage / "payload.zip"
        payload_path.write_bytes(archive(payload))
        installer = output / "FASTMEAN-RussianUI-Setup.exe"
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x86", "/optimize+",
                        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
                        "/reference:System.Web.Extensions.dll", "/reference:System.IO.Compression.dll",
                        "/reference:System.IO.Compression.FileSystem.dll", "/out:" + str(installer),
                        "/win32manifest:" + str(ROOT / "src/FastmeanRuRunner.manifest"),
                        "/win32icon:" + str(icon_path),
                        "/resource:" + str(icon_path) + ",FastmeanRussianUI.Branding.Icon",
                        "/resource:" + str(payload_path) + ",FastmeanRussianUI.Payload",
                        str(ROOT / "src/Installer.cs"), str(ROOT / "src/FastmeanLaunchPaths.cs"),
                        str(ROOT / "src/UnicodeShortcut.cs"), str(ROOT / "src/AppBranding.cs"),
                        str(ROOT / "src/HelperAssociation.cs"), str(assembly_info)], check=True)
    (output / "FASTMEAN-RussianUI-Source.zip").write_bytes(source_zip)
    products = [installer, output / "FASTMEAN-RussianUI-Source.zip"]
    (output / "SHA256SUMS.txt").write_text("".join(digest(p.read_bytes()) + "  " + p.name + "\n" for p in products), encoding="ascii")
    result = {"version": args.version, "native_fastmean_included": False,
              "files": [{"name": p.name, "size": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in products],
              "payload_files": len(manifest["files"]), "upstream_sources": provenance}
    (output / "build-manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
