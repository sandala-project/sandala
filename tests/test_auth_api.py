from __future__ import annotations

from flask import Flask

from sandala.api.routes_auth import register_auth_routes
from sandala.core.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError


class StubAuthService:
    def authenticate_request(self, *, bearer_token=None, session_id=None):
        if bearer_token == "valid-pat":
            return {
                "actor": {
                    "user_id": "user-1",
                    "primary_group": "g1",
                    "groups": ["g1"],
                    "role": "all",
                    "auth_type": "pat",
                },
                "renew_session": False,
                "session_id": None,
            }
        if session_id == "valid-session":
            return {
                "actor": {
                    "user_id": "user-1",
                    "primary_group": "g1",
                    "groups": ["g1"],
                    "role": "all",
                    "auth_type": "session",
                },
                "renew_session": False,
                "session_id": "valid-session",
            }
        if session_id == "renew-session":
            return {
                "actor": {
                    "user_id": "user-1",
                    "primary_group": "g1",
                    "groups": ["g1"],
                    "role": "all",
                    "auth_type": "session",
                },
                "renew_session": True,
                "session_id": "renew-session",
            }
        if bearer_token is not None or session_id is not None:
            raise AuthenticationError("bad auth")
        return None

    def login(self, payload):
        marker = payload.get("_error")
        if marker == "crash":
            raise RuntimeError("sensitive backend failure")
        if marker == "validation":
            raise ValidationError("bad request")
        if marker == "auth":
            raise AuthenticationError("bad credentials")
        return {
            "status": "ok",
            "session_id": "valid-session",
            "actor": {
                "user_id": "user-1",
                "primary_group": "g1",
                "groups": ["g1"],
                "role": "all",
                "auth_type": "session",
            },
        }

    def logout(self, session_id):
        self.last_logout = session_id

    def create_pat(self, payload, *, actor):
        marker = payload.get("_error")
        if marker == "validation":
            raise ValidationError("bad request")
        if marker == "authorization":
            raise AuthorizationError("denied")
        return {
            "id": "pat-1",
            "subject_id": actor["user_id"],
            "name": payload["name"],
            "expires_at": None,
            "revoked_at": None,
            "token": "pat-1.secret",
            "created_by": actor["user_id"],
            "cdate": "2026-01-01T00:00:00Z",
            "mdate": "2026-01-01T00:00:00Z",
        }

    def list_pats(self, *, actor):
        return [
            {
                "id": "pat-1",
                "subject_id": actor["user_id"],
                "name": "CLI",
                "expires_at": None,
                "revoked_at": None,
                "created_by": actor["user_id"],
                "cdate": "2026-01-01T00:00:00Z",
                "mdate": "2026-01-01T00:00:00Z",
            }
        ]

    def get_pat(self, pat_id, *, actor):
        if pat_id == "missing":
            raise NotFoundError("PAT not found")
        if pat_id == "denied":
            raise AuthorizationError("denied")
        return {
            "id": pat_id,
            "subject_id": actor["user_id"],
            "name": "CLI",
            "expires_at": None,
            "revoked_at": None,
            "created_by": actor["user_id"],
            "cdate": "2026-01-01T00:00:00Z",
            "mdate": "2026-01-01T00:00:00Z",
        }

    def revoke_pat(self, pat_id, *, actor):
        if pat_id == "missing":
            raise NotFoundError("PAT not found")
        return {
            "id": pat_id,
            "revoked_at": "2026-01-01T00:00:00Z",
            "mdate": "2026-01-01T00:00:00Z",
        }

    def rotate_pat(self, pat_id, *, actor):
        if pat_id == "missing":
            raise NotFoundError("PAT not found")
        if pat_id == "revoked":
            raise ValidationError("PAT is revoked")
        return {
            "id": pat_id,
            "token": f"{pat_id}.new-secret",
            "mdate": "2026-01-01T00:00:00Z",
        }


class StubNodeService:
    def __init__(self):
        self.last_get = None

    def get(self, module, node_id, *, actor=None):
        self.last_get = {"module": module, "node_id": node_id, "actor": actor}
        if module != "users":
            raise ValidationError("bad module")
        if node_id != "user-1":
            raise NotFoundError("User not found")
        return {"id": "user-1", "username": "alice"}


def _app():
    app = Flask(__name__)
    app.config["sandala_config"] = {
        "AUTH_SESSION_COOKIE_NAME": "sandala_session",
        "AUTH_SESSION_COOKIE_DOMAIN": None,
        "AUTH_SESSION_COOKIE_PATH": "/",
        "AUTH_SESSION_COOKIE_SECURE": True,
        "AUTH_SESSION_COOKIE_HTTPONLY": True,
        "AUTH_SESSION_COOKIE_SAMESITE": "Lax",
        "AUTH_SESSION_IDLE_TTL_SECONDS": 3600,
    }
    register_auth_routes(app, StubAuthService(), StubNodeService(), url_prefix="")
    return app


def test_login_success_and_error_mapping():
    app = _app()
    client = app.test_client()

    resp = client.post("/auth/login/", json={"credentials": {"login": "alice", "password": "secret"}})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    assert "sandala_session=" in resp.headers["Set-Cookie"]
    assert app.config["node_service"].last_get == {
        "module": "users",
        "node_id": "user-1",
        "actor": {
            "user_id": "user-1",
            "primary_group": "g1",
            "groups": ["g1"],
            "role": "all",
            "auth_type": "session",
        },
    }

    resp = client.post("/auth/login/", json={"credentials": {"_error": "validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_error"
    assert resp.get_json()["error_description"] == "bad request"

    resp = client.post("/auth/login/", json={"credentials": {"_error": "auth"}})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication_error"
    assert resp.get_json()["error_description"] == "bad credentials"

    resp = client.post("/auth/login/", data="bad", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"
    assert resp.get_json()["error_description"] == "Request body must be a JSON object"


def test_auth_me_supports_bearer_and_session_cookie():
    client = _app().test_client()

    resp = client.get("/auth/me/")
    assert resp.status_code == 401

    resp = client.get("/auth/me/", headers={"Authorization": "Token xxx"})
    assert resp.status_code == 401

    resp = client.get("/auth/me/", headers={"Authorization": "Bearer valid-pat"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == "user-1"

    resp = client.get("/auth/me/", headers={"Authorization": "bearer valid-pat"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == "user-1"

    resp = client.get("/auth/me/", headers={"Authorization": "BEARER valid-pat"})
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == "user-1"

    client.set_cookie("sandala_session", "valid-session")
    resp = client.get("/auth/me/")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["id"] == "user-1"


def test_auth_me_reissues_cookie_when_session_is_renewed():
    client = _app().test_client()
    client.set_cookie("sandala_session", "renew-session")

    resp = client.get("/auth/me/")

    assert resp.status_code == 200
    assert "sandala_session=renew-session" in resp.headers["Set-Cookie"]


def test_logout_clears_cookie():
    client = _app().test_client()
    client.set_cookie("sandala_session", "valid-session")

    resp = client.post("/auth/logout/")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_pat_endpoints_work_and_map_errors():
    client = _app().test_client()
    headers = {"Authorization": "Bearer valid-pat"}

    resp = client.post("/auth/pats/", json={"pat": {"subject_id": "user-1", "name": "CLI"}}, headers=headers)
    assert resp.status_code == 201
    assert resp.get_json()["pat"]["token"].startswith("pat-1.")

    resp = client.get("/auth/pats/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["pats"][0]["id"] == "pat-1"

    resp = client.get("/auth/pats/pat-1/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["pat"]["id"] == "pat-1"

    resp = client.post("/auth/pats/pat-1/revoke/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["pat"]["id"] == "pat-1"

    resp = client.post("/auth/pats/pat-1/rotate/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["pat"]["token"].startswith("pat-1.")

    resp = client.get("/auth/pats/missing/", headers=headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"

    resp = client.post("/auth/pats/revoked/rotate/", headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_error"


def test_auth_api_hides_unexpected_internal_errors():
    client = _app().test_client()

    resp = client.post("/auth/login/", json={"credentials": {"_error": "crash"}})

    assert resp.status_code == 500
    body = resp.get_json()
    assert body == {
        "error": "internal_error",
        "error_description": "Internal server error",
    }
