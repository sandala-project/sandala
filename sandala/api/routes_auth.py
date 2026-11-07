from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from sandala.api.auth import get_auth_session_cookie_renewal, require_auth_context
from sandala.api.errors import register_error_handlers
from sandala.api.payloads import require_wrapped_object, wrap_resource
from sandala.api.route_prefixes import API_V1_PREFIX
from sandala.core.errors import AuthenticationError, NotFoundError


auth_bp = Blueprint("auth", __name__)


def register_auth_routes(app, auth_service, node_service, *, url_prefix: str = API_V1_PREFIX):
    register_error_handlers(app)
    app.register_blueprint(auth_bp, url_prefix=url_prefix)
    app.config["auth_service"] = auth_service
    app.config["node_service"] = node_service
    app.after_request(_apply_session_cookie_renewal)


@auth_bp.post("/auth/login/")
def login():
    service = _service()
    payload = require_wrapped_object("credentials")
    result = service.login(payload)

    response = jsonify(
        {
            "status": result["status"],
            "user": _load_user_profile(result["actor"]),
        }
    )
    _set_session_cookie(response, result["session_id"])
    return response


@auth_bp.post("/auth/logout/")
def logout():
    service = _service()
    service.logout(request.cookies.get(_cookie_name()))
    response = jsonify({"status": "ok"})
    _clear_session_cookie(response)
    return response


@auth_bp.get("/auth/me/")
def me():
    actor = require_auth_context()
    profile = _load_user_profile(actor)
    return jsonify(wrap_resource("user", profile))


@auth_bp.post("/auth/pats/")
def create_pat():
    service = _service()
    actor = require_auth_context()
    payload = require_wrapped_object("pat")
    pat_doc = service.create_pat(payload, actor=actor)

    return jsonify(wrap_resource("pat", pat_doc)), 201


@auth_bp.get("/auth/pats/")
def list_pats():
    service = _service()
    actor = require_auth_context()
    items = service.list_pats(actor=actor)
    return jsonify(wrap_resource("pats", items))


@auth_bp.get("/auth/pats/<pat_id>/")
def get_pat(pat_id: str):
    service = _service()
    actor = require_auth_context()
    item = service.get_pat(pat_id, actor=actor)
    return jsonify(wrap_resource("pat", item))


@auth_bp.post("/auth/pats/<pat_id>/revoke/")
def revoke_pat(pat_id: str):
    service = _service()
    actor = require_auth_context()
    item = service.revoke_pat(pat_id, actor=actor)
    return jsonify(wrap_resource("pat", item))


@auth_bp.post("/auth/pats/<pat_id>/rotate/")
def rotate_pat(pat_id: str):
    service = _service()
    actor = require_auth_context()
    item = service.rotate_pat(pat_id, actor=actor)
    return jsonify(wrap_resource("pat", item))


def _service():
    return current_app.config["auth_service"]


def _node_service():
    node_service = current_app.config.get("node_service")
    if node_service is None:
        raise AuthenticationError("Node service is not configured")
    return node_service


def _load_user_profile(actor: dict[str, object]) -> dict[str, object]:
    user_id = actor.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise AuthenticationError("Authenticated user is not active")

    try:
        return _node_service().get("users", user_id, actor=actor)
    except NotFoundError as error:
        raise AuthenticationError("Authenticated user is not active") from error


def _cookie_name() -> str:
    return current_app.config["sandala_config"]["AUTH_SESSION_COOKIE_NAME"]


def _cookie_settings() -> dict[str, Any]:
    cfg = current_app.config["sandala_config"]
    return {
        "domain": cfg.get("AUTH_SESSION_COOKIE_DOMAIN"),
        "path": cfg.get("AUTH_SESSION_COOKIE_PATH", "/"),
        "secure": bool(cfg.get("AUTH_SESSION_COOKIE_SECURE", True)),
        "httponly": bool(cfg.get("AUTH_SESSION_COOKIE_HTTPONLY", True)),
        "samesite": cfg.get("AUTH_SESSION_COOKIE_SAMESITE", "Lax"),
        "max_age": int(cfg.get("AUTH_SESSION_IDLE_TTL_SECONDS", 1209600)),
    }


def _set_session_cookie(response, session_id: str) -> None:
    settings = _cookie_settings()
    response.set_cookie(
        _cookie_name(),
        session_id,
        domain=settings["domain"],
        path=settings["path"],
        secure=settings["secure"],
        httponly=settings["httponly"],
        samesite=settings["samesite"],
        max_age=settings["max_age"],
    )


def _clear_session_cookie(response) -> None:
    settings = _cookie_settings()
    response.delete_cookie(
        _cookie_name(),
        domain=settings["domain"],
        path=settings["path"],
        secure=settings["secure"],
        httponly=settings["httponly"],
        samesite=settings["samesite"],
    )


def _apply_session_cookie_renewal(response):
    session_id = get_auth_session_cookie_renewal()
    if isinstance(session_id, str) and session_id:
        _set_session_cookie(response, session_id)
        g.auth_session_cookie_renewal = None
    return response
