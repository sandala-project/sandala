from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
ADMIN_UI_DIR = ROOT_DIR / "admin-ui"
ADMIN_UI_DIST_DIR = ROOT_DIR / "sandala" / "admin_ui_dist"


def main() -> None:
    if shutil.which("npm") is None:
        raise RuntimeError("npm is required to build the bundled admin UI")

    shutil.rmtree(ROOT_DIR / "dist", ignore_errors=True)
    _run(["npm", "ci"], cwd=ADMIN_UI_DIR)
    _run(["npm", "run", "build"], cwd=ADMIN_UI_DIR)

    required_files = [
        ADMIN_UI_DIST_DIR / "index.html",
        ADMIN_UI_DIST_DIR / "config.js",
        ADMIN_UI_DIST_DIR / "static" / "manifest.json",
    ]
    missing_files = [str(path) for path in required_files if not path.is_file()]
    if missing_files:
        raise RuntimeError(f"Admin UI build is incomplete: {', '.join(missing_files)}")

    _run([sys.executable, "-m", "build"], cwd=ROOT_DIR)


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    main()
