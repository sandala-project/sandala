from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from sandala.api.auth import require_auth_context
from sandala.api.errors import register_error_handlers
from sandala.api.payloads import require_wrapped_object, wrap_resource
from sandala.api.route_prefixes import API_V1_PREFIX


entity_bp = Blueprint("entity", __name__)


def register_entity_routes(app, entity_service, *, url_prefix: str = API_V1_PREFIX):
    register_error_handlers(app)
    app.register_blueprint(entity_bp, url_prefix=url_prefix)
    app.config["entity_service"] = entity_service


@entity_bp.get("/modules/<module>/entities/")
def list_entities(module: str):
    service = _service()
    actor = require_auth_context()
    items = service.list_entities(module, actor=actor)
    return jsonify(wrap_resource("entities", items))


@entity_bp.get("/modules/<module>/entities/<entity>/")
def get_entity(module: str, entity: str):
    service = _service()
    actor = require_auth_context()
    schema = service.get_schema(module, entity, actor=actor)
    return jsonify(wrap_resource("entity", schema))


@entity_bp.post("/modules/<module>/entities/<entity>/")
def create_entity(module: str, entity: str):
    service = _service()
    actor = require_auth_context()
    payload = require_wrapped_object("entity")
    schema = service.create(module, entity, payload, actor=actor)
    return jsonify(wrap_resource("entity", schema)), 201


@entity_bp.put("/modules/<module>/entities/<entity>/")
def update_entity(module: str, entity: str):
    service = _service()
    actor = require_auth_context()
    payload = require_wrapped_object("entity")
    schema = service.update(module, entity, payload, actor=actor)
    return jsonify(wrap_resource("entity", schema))


@entity_bp.delete("/modules/<module>/entities/<entity>/")
def delete_entity(module: str, entity: str):
    service = _service()
    actor = require_auth_context()
    service.delete(module, entity, actor=actor)
    return jsonify({"status": "ok"})


def _service():
    return current_app.config["entity_service"]
