import importlib.util
import json
from pathlib import Path

import pytest


def _load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _version_files(root, version="0.1.0"):
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    admin = root / "admin-ui"
    admin.mkdir()
    (admin / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (admin / "package-lock.json").write_text(
        json.dumps({"version": version, "packages": {"": {"version": version}}}), encoding="utf-8",
    )


@pytest.mark.parametrize("tag", [None, "v0.1.0"])
def test_distribution_version_matches_all_manifests(tmp_path, tag):
    _version_files(tmp_path)
    assert _load_script("check_version").check_version(tmp_path, tag=tag) == "0.1.0"


@pytest.mark.parametrize("tag", ["v0.2.0", "0.1.0", "v0.1.0-extra", ""])
def test_distribution_version_rejects_mismatched_tag(tmp_path, tag):
    _version_files(tmp_path)
    with pytest.raises(RuntimeError, match="Release tag"):
        _load_script("check_version").check_version(tmp_path, tag=tag)


@pytest.mark.parametrize("source", ["package", "lock", "lock_root"])
def test_distribution_version_rejects_mismatched_manifest(tmp_path, source):
    _version_files(tmp_path)
    path = tmp_path / "admin-ui" / ("package.json" if source == "package" else "package-lock.json")
    manifest = json.loads(path.read_text())
    if source == "lock_root":
        manifest["packages"][""]["version"] = "0.2.0"
    else:
        manifest["version"] = "0.2.0"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Version mismatch"):
        _load_script("check_version").check_version(tmp_path)


@pytest.mark.parametrize("version", ["0.1.0a1", "v0.1.0", "0.1", "00.1.0"])
def test_distribution_version_requires_normal_semver_release(tmp_path, version):
    _version_files(tmp_path, version=version)
    with pytest.raises(RuntimeError, match="MAJOR.MINOR.PATCH"):
        _load_script("check_version").check_version(tmp_path)


def test_distribution_verification_runs_outside_checkout(tmp_path, monkeypatch):
    script = _load_script("verify_distribution")
    monkeypatch.setattr(script, "ROOT_DIR", tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "sandala-0.1.0-py3-none-any.whl"
    wheel.touch()
    monkeypatch.setattr(script.venv.EnvBuilder, "create", lambda *_: None)
    calls = []
    monkeypatch.setattr(script.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))

    script.main()

    assert len(calls) == 2
    assert all(call[1]["check"] for call in calls)
    assert all(Path(call[1]["cwd"]) != tmp_path for call in calls)
    assert calls[0][1]["cwd"] == calls[1][1]["cwd"]
    assert str(wheel) in calls[0][0]
    assert "is_relative_to(Path(sys.prefix).resolve())" in calls[1][0][-1]
