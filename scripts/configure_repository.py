"""Set real GitHub metadata without publishing or modifying Git remotes."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="GitHub owner/repository")
    parser.add_argument("--maintainer", help="GitHub username; defaults to repository owner")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Expected a GitHub owner/repository, not a URL")
    owner, name = args.repository.split("/")
    maintainer = args.maintainer or owner
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", maintainer):
        parser.error("Invalid maintainer username")
    if owner.upper() == "OWNER" or name.upper() == "REPOSITORY":
        parser.error("Replace the example with your actual GitHub repository")
    path = ROOT / "custom_components/meest/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf8"))
    manifest.update(
        documentation=f"https://github.com/{args.repository}",
        issue_tracker=f"https://github.com/{args.repository}/issues",
        codeowners=[f"@{maintainer}"],
    )
    ordered = {
        key: manifest[key]
        for key in ["domain", "name"]
        + sorted(key for key in manifest if key not in ("domain", "name"))
    }
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf8")
    (ROOT / ".github/CODEOWNERS").write_text(f"* @{maintainer}\n", encoding="utf8")
    print(f"Configured {args.repository}; maintainer @{maintainer}. Nothing was published.")


if __name__ == "__main__":
    main()
