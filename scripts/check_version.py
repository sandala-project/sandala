from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tomllib


ROOT_DIR = Path(__file__).resolve().parents[1]


def check_version(root: Path, tag: str | None = None) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    if not isinstance(version, str) or re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version) is None:
        raise RuntimeError("Expected a release version in MAJOR.MINOR.PATCH format")

    package = json.loads((root / "admin-ui" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "admin-ui" / "package-lock.json").read_text(encoding="utf-8"))
    versions = {
        "admin-ui/package.json": package.get("version"),
        "admin-ui/package-lock.json": lock.get("version"),
        "admin-ui/package-lock.json packages['']": lock.get("packages", {}).get("", {}).get("version"),
    }
    for source, candidate in versions.items():
        if candidate != version:
            raise RuntimeError(f"Version mismatch in {source}: expected {version!r}, got {candidate!r}")

    if tag is not None and tag != f"v{version}":
        raise RuntimeError(f"Release tag must be 'v{version}', got {tag!r}")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Python, admin UI, and optional release-tag versions.")
    parser.add_argument("--tag", help="Expected Git release tag, for example v0.1.0")
    args = parser.parse_args()
    try:
        print(check_version(ROOT_DIR, tag=args.tag))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
