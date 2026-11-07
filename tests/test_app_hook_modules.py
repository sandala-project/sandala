from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from sandala.api import app as app_module
from sandala.api.routes_admin import _default_admin_ui_dist


def _container_stub() -> dict:
    return {
        "config": {"HOOK_MODULES": []},
        "auth_service": object(),
        "module_service": object(),
        "entity_service": object(),
        "node_service": object(),
        "asset_service": object(),
    }


def test_create_app_skips_hook_loading_when_hook_modules_empty(monkeypatch):
    monkeypatch.setattr(app_module, "build_container", lambda config: _container_stub())

    imported: list[str] = []

    def fake_import(module_name: str):
        imported.append(module_name)
        raise AssertionError("No imports expected when HOOK_MODULES is empty")

    monkeypatch.setattr(app_module.importlib, "import_module", fake_import)

    app = app_module.create_app()

    assert app is not None
    assert imported == []


def test_create_app_separates_versioned_api_from_asset_delivery(monkeypatch):
    monkeypatch.setattr(app_module, "build_container", lambda config: _container_stub())

    app = app_module.create_app()
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/api/v1/auth/login/" in routes
    assert "/api/v1/nodes/<module>/" in routes
    assert "/api/v1/uploads/assets/images/" in routes
    assert "/assets/<path:key_tail>" in routes
    assert all(route.endswith("/") for route in routes if route.startswith("/api/v1/"))
    assert "/auth/login/" not in routes
    assert "/uploads/assets/images/" not in routes


def test_create_app_serves_admin_ui_from_configured_dist(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("admin index", encoding="utf-8")
    (tmp_path / "config.js").write_text("window.__SANDALA_RUNTIME_CONFIG__ = {};", encoding="utf-8")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "app.js").write_text("console.log('app');", encoding="utf-8")
    other_dist = tmp_path / "other-dist"
    other_dist.mkdir()
    (other_dist / "index.html").write_text("other admin index", encoding="utf-8")
    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda config: {**_container_stub(), "config": {"HOOK_MODULES": [], **(config or {})}},
    )

    client = app_module.create_app({"ADMIN_UI_DIST": str(tmp_path)}).test_client()
    other_client = app_module.create_app({"ADMIN_UI_DIST": str(other_dist)}).test_client()

    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/_app/nodes/tree").get_data(as_text=True) == "admin index"
    assert client.get("/admin/config.js").status_code == 200
    assert client.get("/admin/static/app.js").status_code == 200
    assert other_client.get("/admin/").get_data(as_text=True) == "other admin index"
    assert client.get("/admin/").get_data(as_text=True) == "admin index"


def test_default_admin_ui_dist_is_inside_sandala_package():
    assert _default_admin_ui_dist() == Path(__file__).resolve().parents[1] / "sandala" / "admin_ui_dist"


def test_create_app_loads_hook_modules_in_configured_order(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda config: {**_container_stub(), "config": {"HOOK_MODULES": ["pkg.hooks_one", "pkg.hooks_two"]}},
    )

    module_calls: list[str] = []

    module_one = ModuleType("pkg.hooks_one")
    module_one.register_hooks = lambda app, container: module_calls.append("pkg.hooks_one")

    module_two = ModuleType("pkg.hooks_two")
    module_two.register_hooks = lambda app, container: module_calls.append("pkg.hooks_two")

    def fake_import(module_name: str):
        if module_name == "pkg.hooks_one":
            return module_one
        if module_name == "pkg.hooks_two":
            return module_two
        raise AssertionError(f"Unexpected module import: {module_name}")

    monkeypatch.setattr(app_module.importlib, "import_module", fake_import)

    app_module.create_app()

    assert module_calls == ["pkg.hooks_one", "pkg.hooks_two"]


def test_create_app_fails_when_hook_module_contract_is_invalid(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda config: {**_container_stub(), "config": {"HOOK_MODULES": ["pkg.invalid"]}},
    )

    invalid_module = ModuleType("pkg.invalid")
    monkeypatch.setattr(app_module.importlib, "import_module", lambda module_name: invalid_module)

    with pytest.raises(RuntimeError, match="must define callable register_hooks"):
        app_module.create_app()


def test_create_app_fails_fast_when_hook_module_import_crashes(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda config: {**_container_stub(), "config": {"HOOK_MODULES": ["pkg.broken"]}},
    )

    def fake_import(module_name: str):
        raise ImportError("boom")

    monkeypatch.setattr(app_module.importlib, "import_module", fake_import)

    with pytest.raises(RuntimeError, match="Failed to import hook module 'pkg.broken'"):
        app_module.create_app()
