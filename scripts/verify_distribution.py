from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import venv


ROOT_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    wheel_path = _find_wheel()

    with tempfile.TemporaryDirectory(prefix="sandala-wheel-check-") as temp_dir:
        environment_dir = Path(temp_dir) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment_dir)
        python = _venv_python(environment_dir)

        subprocess.run([str(python), "-m", "pip", "install", str(wheel_path)], cwd=temp_dir, check=True)
        subprocess.run(
            [
                str(python),
                "-c",
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import sys",
                        "import sandala",
                        "assert Path(sandala.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())",
                        "from flask import Flask",
                        "from sandala.api.routes_admin import register_admin_ui_routes",
                        "app = Flask(__name__)",
                        "register_admin_ui_routes(app)",
                        "client = app.test_client()",
                        "assert client.get('/admin/').status_code == 200",
                        "assert client.get('/admin/_app/nodes/tree').status_code == 200",
                        "assert client.get('/admin/config.js').status_code == 200",
                        "assert client.get('/admin/static/manifest.json').status_code == 200",
                        "manifest = client.get('/admin/static/manifest.json').get_json()",
                        "assert isinstance(manifest, dict) and manifest",
                        "for entry in manifest.values():",
                        "    for asset in [entry['file'], *entry.get('css', []), *entry.get('assets', [])]:",
                        "        assert client.get('/admin/' + asset).status_code == 200, asset",
                    ]
                ),
            ],
            cwd=temp_dir,
            check=True,
        )


def _find_wheel() -> Path:
    wheels = sorted((ROOT_DIR / "dist").glob("sandala-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected exactly one Sandala wheel in {ROOT_DIR / 'dist'}")
    return wheels[0]


def _venv_python(environment_dir: Path) -> Path:
    if sys.platform == "win32":
        return environment_dir / "Scripts" / "python.exe"
    return environment_dir / "bin" / "python"


if __name__ == "__main__":
    main()
