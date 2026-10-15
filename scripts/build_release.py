"""Build an installation ZIP using only the integration and its notices."""

import argparse
import zipfile

from check_repository import ROOT, check_repository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="Local preview only; permit unfinished GitHub metadata",
    )
    args = parser.parse_args()
    manifest = check_repository(release=not args.allow_unconfigured)
    destination = ROOT / "dist" / f"meest-{manifest['version']}.zip"
    destination.parent.mkdir(exist_ok=True)
    source = ROOT / "custom_components/meest"
    paths = sorted(
        p
        for p in source.rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".png"} and "__pycache__" not in p.parts
    )
    paths.extend(ROOT / name for name in ["LICENSE", "NOTICE.md", "README.md"])
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt ZIP")
        assert "custom_components/meest/manifest.json" in archive.namelist()
    print(f"Built {destination.name} ({len(paths)} files)")


if __name__ == "__main__":
    main()
