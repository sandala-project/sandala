from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from sandala.api.auth import require_auth_context
from sandala.api.errors import register_error_handlers
from sandala.api.payloads import require_wrapped_object, wrap_resource
from sandala.api.route_prefixes import API_V1_PREFIX


module_bp = Blueprint("module", __name__)


def register_module_routes(app, module_service, *, url_prefix: str = API_V1_PREFIX):
    register_error_handlers(app)
    app.register_blueprint(module_bp, url_prefix=url_prefix)
    app.config["module_service"] = module_service


@module_bp.get("/modules/")
def list_modules():
    service = _service()
    actor = require_auth_context()
    items = service.list_modules(actor=actor)
    return jsonify(wrap_resource("modules", items))


@module_bp.get("/modules/<module>/")
def get_module(module: str):
    service = _service()
    actor = require_auth_context()
    doc = service.get_module(module, actor=actor)
    return jsonify(wrap_resource("module", doc))


@module_bp.post("/modules/")
def create_module():
    service = _service()
    actor = require_auth_context()
    payload = require_wrapped_object("module")
    doc = service.create_module(payload, actor=actor)
    return jsonify(wrap_resource("module", doc)), 201


@module_bp.patch("/modules/<module>/")
def patch_module(module: str):
    service = _service()
    actor = require_auth_context()
    payload = require_wrapped_object("module")
    doc = service.patch_module(module, payload, actor=actor)
    return jsonify(wrap_resource("module", doc))


@module_bp.delete("/modules/<module>/")
def delete_module(module: str):
    service = _service()
    actor = require_auth_context()
    service.delete_module(module, actor=actor)
    return jsonify({"status": "ok"})


def _service():
    return current_app.config["module_service"]
