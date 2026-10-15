"""Offline repository checks. --release also rejects unfinished GitHub metadata."""

import argparse
import ast
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_repository(release=False):
    errors = []
    integration = ROOT / "custom_components/meest"
    manifest = json.loads((integration / "manifest.json").read_text(encoding="utf8"))
    required = {"domain", "name", "version", "documentation", "issue_tracker", "codeowners"}
    if not required <= manifest.keys():
        errors.append("Missing manifest metadata")
    if manifest.get("domain") != "meest" or not manifest.get("config_flow"):
        errors.append("Unexpected domain/config_flow")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest.get("version", "")):
        errors.append("Expected a semantic version")
    pending = "OWNER/REPOSITORY" in str(manifest) or not manifest.get("codeowners")
    if release and pending:
        errors.append(
            "Run scripts/configure_repository.py with your actual GitHub owner/repository"
        )
    dirs = sorted(
        p.name
        for p in (ROOT / "custom_components").iterdir()
        if p.is_dir() and p.name != "__pycache__"
    )
    if dirs != ["meest"]:
        errors.append("Expected exactly one integration")
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf8"))
    if hacs.get("content_in_root") is not False or hacs.get("name") != "Meest":
        errors.append("Invalid HACS layout")
    paths = []
    for folder in [
        integration,
        ROOT / "tests",
        ROOT / "scripts",
        ROOT / "examples",
        ROOT / ".github",
    ]:
        paths.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.extend(p for p in ROOT.iterdir() if p.is_file())
    secret_patterns = [
        r"gh[pousr]_[A-Za-z0-9]{20,}",
        r"github_pat_[A-Za-z0-9_]{30,}",
        r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"MGRAE[0-9]{8,}[A-Z]+",
    ]
    for path in paths:
        rel = path.relative_to(ROOT)
        if path.suffix.lower() in {".apk", ".apkm", ".db"} or path.name.startswith(
            "meest-test-report"
        ):
            errors.append(f"Private/unneeded artifact: {rel}")
        if path.suffix in {".py", ".json", ".md", ".yaml", ".yml", ".txt", ".toml"}:
            content = path.read_text(encoding="utf8")
            if path.suffix == ".py":
                ast.parse(content, filename=str(rel))
            if path.suffix == ".json":
                json.loads(content)
            if path.name != "check_repository.py" and any(
                re.search(pattern, content) for pattern in secret_patterns
            ):
                errors.append(f"Possible private data: {rel}")
    icon = (integration / "brand/icon.png").read_bytes()
    if icon[:8] != b"\x89PNG\r\n\x1a\n" or len(icon) < 24:
        errors.append("Invalid brand PNG")
    else:
        width, height = struct.unpack(">II", icon[16:24])
        if width != height:
            errors.append("Brand icon must be square")
    for name in ["LICENSE", "NOTICE.md", "README.md", "CONTRIBUTING.md", "docs/PUBLISHING.md"]:
        if not (ROOT / name).is_file():
            errors.append(f"Missing {name}")
    if errors:
        raise ValueError("\n".join(errors))
    if pending:
        print(
            "Local checks passed. GitHub owner/repository still needs configuration before release."
        )
    else:
        print("Repository checks passed. Live HACS/hassfest checks still run on GitHub.")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        check_repository(args.release)
    except (ValueError, OSError, SyntaxError) as error:
        parser.exit(1, f"Repository check failed: {error}\n")


if __name__ == "__main__":
    main()
