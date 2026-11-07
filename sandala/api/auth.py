from __future__ import annotations

from flask import current_app, g, request

from sandala.core.errors import AuthenticationError


def get_auth_context():
    return getattr(g, "auth_context", None)


def get_auth_session_cookie_renewal():
    return getattr(g, "auth_session_cookie_renewal", None)


def attach_optional_auth_context():
    header = request.headers.get("Authorization")
    cfg = current_app.config.get("sandala_config", {})
    cookie_name = cfg.get("AUTH_SESSION_COOKIE_NAME", "sandala_session")
    bearer_token = _extract_bearer_token(header) if header else None
    session_id = request.cookies.get(cookie_name)

    if bearer_token is None and session_id is None:
        g.auth_context = None
        return None

    auth_service = current_app.config.get("auth_service")
    if auth_service is None:
        raise AuthenticationError("Authentication is not configured")

    auth_result = auth_service.authenticate_request(
        bearer_token=bearer_token,
        session_id=session_id,
    )
    if auth_result is None:
        g.auth_context = None
        g.auth_session_cookie_renewal = None
        return None

    actor = auth_result["actor"]
    g.auth_context = actor
    if auth_result.get("renew_session") and isinstance(auth_result.get("session_id"), str):
        g.auth_session_cookie_renewal = auth_result["session_id"]
    else:
        g.auth_session_cookie_renewal = None
    return actor


def require_auth_context():
    actor = attach_optional_auth_context()
    if actor is None:
        raise AuthenticationError("Authentication required")
    return actor


def _extract_bearer_token(header: str) -> str:
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError("Invalid authorization header")
    return parts[1].strip()
