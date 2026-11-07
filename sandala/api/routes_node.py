from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from sandala.api.auth import attach_optional_auth_context
from sandala.api.errors import register_error_handlers
from sandala.api.payloads import (
    get_optional_query_project,
    get_optional_wrapped_object,
    require_json_object,
    require_wrapped_object,
    wrap_resource,
)
from sandala.api.route_prefixes import API_V1_PREFIX
from sandala.core.errors import ParameterInvalidError, RequestBodyInvalidError


node_bp = Blueprint("node", __name__)


def register_node_routes(app, node_service, *, url_prefix: str = API_V1_PREFIX):
    register_error_handlers(app)
    app.register_blueprint(node_bp, url_prefix=url_prefix)
    app.config["node_service"] = node_service


@node_bp.post("/nodes/<module>/")
def create_node(module: str):
    service = _service()
    actor = attach_optional_auth_context()
    payload = require_wrapped_object("node")
    entity = payload.get("entity")
    if not isinstance(entity, str) or not entity:
        raise ParameterInvalidError("Field 'entity' must be a non-empty string")

    node = service.create(module, entity, payload, actor=actor)

    return jsonify(wrap_resource("node", node)), 201


@node_bp.patch("/nodes/<module>/<node_id>/")
def patch_node(module: str, node_id: str):
    service = _service()
    actor = attach_optional_auth_context()
    payload = require_wrapped_object("node")
    node = service.patch(module, node_id, payload, actor=actor)

    return jsonify(wrap_resource("node", node))


@node_bp.patch("/nodes/<module>/<node_id>/acl/")
def patch_node_acl(module: str, node_id: str):
    service = _service()
    actor = attach_optional_auth_context()
    body = require_json_object()
    payload = body.get("node")
    if not isinstance(payload, dict):
        raise RequestBodyInvalidError("Request body must contain 'node' object")
    recursive = body.get("recursive", False)
    if not isinstance(recursive, bool):
        raise ParameterInvalidError("Field 'recursive' must be a boolean")
    result = service.patch_acl(module, node_id, payload, recursive=recursive, actor=actor)
    return jsonify(result)


@node_bp.delete("/nodes/<module>/<node_id>/")
def delete_node(module: str, node_id: str):
    service = _service()
    actor = attach_optional_auth_context()
    deleted_count = service.delete(module, node_id, actor=actor)
    return jsonify({"deleted_count": deleted_count})


@node_bp.post("/nodes/<module>/query/")
def query_nodes(module: str):
    service = _service()
    actor = attach_optional_auth_context()
    payload = get_optional_wrapped_object("query")

    nodes = service.query(module, payload, actor=actor)
    return jsonify(wrap_resource("nodes", nodes))


@node_bp.post("/nodes/<module>/entity/<entity>/query/")
def query_entity_nodes(module: str, entity: str):
    service = _service()
    actor = attach_optional_auth_context()
    payload = get_optional_wrapped_object("query")
    nodes = service.list_entity(module, entity, payload, actor=actor)
    return jsonify(wrap_resource("nodes", nodes))


@node_bp.get("/nodes/<module>/<node_id>/")
def get_node(module: str, node_id: str):
    service = _service()
    actor = attach_optional_auth_context()
    node = service.get(module, node_id, project=get_optional_query_project("project"), actor=actor)
    return jsonify(wrap_resource("node", node))


def _service():
    return current_app.config["node_service"]
