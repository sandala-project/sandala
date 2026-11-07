from __future__ import annotations

import importlib
from types import ModuleType

from flask import Flask

from sandala.api.errors import register_error_handlers
from sandala.api.routes_assets import register_asset_routes
from sandala.api.routes_admin import register_admin_ui_routes
from sandala.api.routes_auth import register_auth_routes
from sandala.api.routes_entity import register_entity_routes
from sandala.api.routes_module import register_module_routes
from sandala.api.routes_node import register_node_routes
from sandala.api.route_prefixes import API_V1_PREFIX
from sandala.bootstrap import build_container


def create_app(config: dict | None = None):
    app = Flask(__name__)
    app.json.sort_keys = False
    register_error_handlers(app)
    container = build_container(config)
    cfg = container["config"]
    app.config["sandala_config"] = cfg
    register_admin_ui_routes(app, cfg.get("ADMIN_UI_DIST"))
    register_auth_routes(app, container["auth_service"], container["node_service"], url_prefix=API_V1_PREFIX)
    register_module_routes(app, container["module_service"], url_prefix=API_V1_PREFIX)
    register_entity_routes(app, container["entity_service"], url_prefix=API_V1_PREFIX)
    register_node_routes(app, container["node_service"], url_prefix=API_V1_PREFIX)
    register_asset_routes(app, container["asset_service"], url_prefix=API_V1_PREFIX)
    _load_hook_modules(app, container, cfg.get("HOOK_MODULES"))
    return app


def _load_hook_modules(app: Flask, container: dict, module_names: list[str]) -> None:
    for module_name in module_names:
        module = _import_hook_module(module_name)
        register_hooks = getattr(module, "register_hooks", None)
        if not callable(register_hooks):
            raise RuntimeError(
                f"Hook module '{module_name}' must define callable register_hooks(app, container)"
            )
        register_hooks(app, container)


def _import_hook_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to import hook module '{module_name}': {exc}") from exc
