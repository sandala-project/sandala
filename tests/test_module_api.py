from __future__ import annotations

from flask import Flask

from sandala.api.routes_module import register_module_routes
from sandala.core.errors import AuthenticationError, AuthorizationError, ConflictError, NotFoundError, ValidationError


class StubModuleService:
    def __init__(self):
        self.docs = {
            "library": {
                "name": "library",
                "description": "Library",
                "root_owner": "00000000-0000-4000-8000-000000000001",
            "root_group": "00000000-0000-4000-8000-000000000002",
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": False},
            },
            }
        }

    def list_modules(self, *, actor=None):
        if actor.get("role") not in {"admin", "superuser"}:
            raise AuthorizationError("forbidden")
        return list(self.docs.values())

    def get_module(self, name, *, actor=None):
        if actor.get("role") not in {"admin", "superuser"}:
            raise AuthorizationError("forbidden")
        if name not in self.docs:
            raise NotFoundError("missing")
        return self.docs[name]

    def create_module(self, payload, *, actor=None):
        if actor.get("role") != "superuser":
            raise AuthorizationError("forbidden")
        if payload.get("name") in self.docs:
            raise ConflictError("exists")
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        self.docs[payload["name"]] = payload
        return payload

    def patch_module(self, name, payload, *, actor=None):
        if actor.get("role") != "superuser":
            raise AuthorizationError("forbidden")
        if name not in self.docs:
            raise NotFoundError("missing")
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        self.docs[name].update(payload)
        return self.docs[name]

    def delete_module(self, name, *, actor=None):
        if actor.get("role") != "superuser":
            raise AuthorizationError("forbidden")
        if name not in self.docs:
            raise NotFoundError("missing")
        del self.docs[name]


class StubAuthService:
    def authenticate_request(self, *, bearer_token=None, session_id=None):
        if bearer_token == "super":
            return {"actor": {"user_id": "root", "role": "superuser"}, "renew_session": False, "session_id": None}
        if bearer_token == "admin":
            return {"actor": {"user_id": "admin-1", "role": "admin"}, "renew_session": False, "session_id": None}
        if bearer_token == "user":
            return {"actor": {"user_id": "user-1", "role": "all"}, "renew_session": False, "session_id": None}
        if bearer_token is None and session_id is None:
            return None
        raise AuthenticationError("Invalid access token")


def test_module_api_crud():
    app = Flask(__name__)
    register_module_routes(app, StubModuleService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    headers = {"Authorization": "Bearer super"}
    resp = client.get("/modules/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["modules"][0]["name"] == "library"

    payload = {
        "name": "catalog",
        "description": "Catalog",
        "root_owner": "00000000-0000-4000-8000-000000000003",
        "root_group": "00000000-0000-4000-8000-000000000004",
        "root_children_entities": [],
        "root_perm": {
            "owner": {"p": True},
            "group": {"p": False},
            "others": {"p": False},
        },
    }
    resp = client.post("/modules/", json={"module": payload}, headers=headers)
    assert resp.status_code == 201
    assert resp.get_json()["module"]["name"] == "catalog"
    resp = client.get("/modules/catalog/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["module"]["name"] == "catalog"
    resp = client.patch("/modules/catalog/", json={"module": {"description": "Catalog 2"}}, headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["module"]["description"] == "Catalog 2"
    resp = client.delete("/modules/catalog/", headers=headers)
    assert resp.status_code == 200


def test_module_api_read_requires_admin_or_superuser():
    app = Flask(__name__)
    register_module_routes(app, StubModuleService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.get("/modules/", headers={"Authorization": "Bearer admin"})
    assert resp.status_code == 200

    resp = client.get("/modules/library/", headers={"Authorization": "Bearer admin"})
    assert resp.status_code == 200
    assert resp.get_json()["module"]["name"] == "library"

    resp = client.get("/modules/", headers={"Authorization": "Bearer user"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "access_denied"

    resp = client.get("/modules/library/", headers={"Authorization": "Bearer user"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "access_denied"


def test_module_api_request_body_errors_use_machine_codes():
    app = Flask(__name__)
    register_module_routes(app, StubModuleService(), url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post("/modules/", data="bad", content_type="text/plain", headers={"Authorization": "Bearer super"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"

    resp = client.patch("/modules/library/", data="bad", content_type="text/plain", headers={"Authorization": "Bearer super"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"
