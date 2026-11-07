from __future__ import annotations

import pytest

from sandala.config import build_config, load_config_from_env, normalize_hook_modules


def test_load_config_from_env_reads_typed_values(monkeypatch):
    monkeypatch.setenv("SANDALA_PORT", "4000")
    monkeypatch.setenv("SANDALA_AUTH_PASSWORD_PATTERN", "^.{12,}$")
    monkeypatch.setenv("SANDALA_AUTH_USERNAME_MIN_LENGTH", "4")
    monkeypatch.setenv("SANDALA_AUTH_USERNAME_PATTERN", "^[a-z]+$")
    monkeypatch.setenv("SANDALA_HOOK_MODULES", "mod.one, mod.two")
    monkeypatch.setenv("SANDALA_ADMIN_UI_DIST", "/srv/sandala-admin/dist")

    cfg = load_config_from_env()

    assert cfg["PORT"] == 4000
    assert cfg["AUTH_PASSWORD_PATTERN"] == "^.{12,}$"
    assert cfg["AUTH_USERNAME_MIN_LENGTH"] == 4
    assert cfg["AUTH_USERNAME_PATTERN"] == "^[a-z]+$"
    assert cfg["HOOK_MODULES"] == ["mod.one", "mod.two"]
    assert cfg["ADMIN_UI_DIST"] == "/srv/sandala-admin/dist"


def test_build_config_applies_override_after_env(monkeypatch):
    monkeypatch.setenv("SANDALA_PORT", "4000")

    cfg = build_config({"PORT": 5000, "HOOK_MODULES": ["x.hooks"]})

    assert cfg["PORT"] == 5000
    assert cfg["HOOK_MODULES"] == ["x.hooks"]


def test_build_config_parses_hook_modules_from_override_csv():
    cfg = build_config({"HOOK_MODULES": "a.hooks, b.hooks"})

    assert cfg["HOOK_MODULES"] == ["a.hooks", "b.hooks"]


def test_load_config_from_env_raises_for_invalid_integer(monkeypatch):
    monkeypatch.setenv("SANDALA_PORT", "oops")

    with pytest.raises(ValueError, match="SANDALA_PORT"):
        load_config_from_env()


def test_load_config_from_env_raises_for_invalid_boolean(monkeypatch):
    monkeypatch.setenv("SANDALA_ALLOW_ANONYMOUS_USER_REGISTRATION", "maybe")

    with pytest.raises(ValueError, match="SANDALA_ALLOW_ANONYMOUS_USER_REGISTRATION"):
        load_config_from_env()


def test_normalize_hook_modules_rejects_invalid_type():
    with pytest.raises(ValueError, match="HOOK_MODULES"):
        normalize_hook_modules(123)
