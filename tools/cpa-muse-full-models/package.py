"""Build the ZIP required by CLIProxy's InstallArchive and update its checksum."""
import argparse
import hashlib
import io
import json
import pathlib
import re
import struct
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(__file__).resolve().parent
    registry_path = root / "registry.json"
    registry = json.loads(registry_path.read_text())
    plugin = registry["plugins"][0]
    version = plugin["version"]
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", version):
        raise ValueError("Invalid plugin version")
    library = args.library.read_bytes()
    if len(library) < 20 or library[:6] != b"\x7fELF\x02\x01" or struct.unpack("<H", library[18:20])[0] != 183:
        raise ValueError("Expected a Linux arm64 ELF library")
    marker = ('"Name":"cpa-muse-full-models","Version":"' + version + '"').encode()
    if marker not in library:
        raise ValueError("Library registration version does not match registry")
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entry = zipfile.ZipInfo("cpa-muse-full-models.so", (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = 0o100644 << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, library, compresslevel=9)
    payload = contents.getvalue()
    filename = f"cpa-muse-full-models-v{version}-linux-arm64.zip"
    target = root / "artifacts/linux-arm64" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("Versioned archive already has different bytes; use a new version")
    target.write_bytes(payload)
    artifact = plugin["install"]["artifacts"][0]
    artifact.update({"url": artifact["url"].rsplit("/", 1)[0] + "/" + filename,
                     "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)})
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
