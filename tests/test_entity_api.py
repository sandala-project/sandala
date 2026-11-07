from __future__ import annotations

from flask import Flask

from sandala.api.routes_entity import register_entity_routes
from sandala.core.errors import AuthenticationError, AuthorizationError, SchemaValidationError


class StubEntityService:
    def __init__(self):
        self.schemas = {}

    def _require_superuser(self, actor):
        role = actor.get("role") if isinstance(actor, dict) else None
        if not (isinstance(role, str) and role.strip().lower() == "superuser"):
            raise AuthorizationError("Only superuser can access entity operations")

    def list_entities(self, module, actor=None):
        role = actor.get("role") if isinstance(actor, dict) else None
        if role not in {"admin", "superuser"}:
            raise AuthorizationError("Only admin or superuser can access entity operations")
        return [{"title": key[1], "description": "desc"} for key in self.schemas if key[0] == module]

    def get_schema(self, module, entity, actor=None):
        role = actor.get("role") if isinstance(actor, dict) else None
        if role not in {"admin", "superuser"}:
            raise AuthorizationError("Only admin or superuser can access entity operations")
        return self.schemas[(module, entity)]

    def create(self, module, entity, schema, actor=None):
        self._require_superuser(actor)
        if schema.get("_error") == "schema_validation":
            raise SchemaValidationError(
                "Invalid schema at 'properties.name': 'type' is a required property",
                details={
                    "field_errors": [
                        {
                            "location": ["properties", "name", "type"],
                            "message": "'type' is a required property",
                            "keyword": "required",
                        }
                    ]
                },
            )
        if schema.get("_error") == "schema_validation_multi":
            raise SchemaValidationError(
                "Schema contains multiple validation errors",
                details={
                    "field_errors": [
                        {
                            "location": ["additionalProperties"],
                            "message": "Field 'additionalProperties' is required",
                            "keyword": "required",
                        },
                        {
                            "location": ["x-meta", "perm"],
                            "message": "Field 'perm' is required",
                            "keyword": "required",
                        },
                    ]
                },
            )
        schema["title"] = entity
        self.schemas[(module, entity)] = schema
        return schema

    def update(self, module, entity, schema, actor=None):
        self._require_superuser(actor)
        self.schemas[(module, entity)] = schema
        return schema

    def delete(self, module, entity, actor=None):
        self._require_superuser(actor)
        self.schemas.pop((module, entity), None)


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


def test_api_create_get_list_delete():
    app = Flask(__name__)
    service = StubEntityService()
    register_entity_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    payload = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            }
        },
        "required": ["name"],
    }

    headers = {"Authorization": "Bearer super"}

    resp = client.post("/modules/library/entities/Book/", json={"entity": payload}, headers=headers)
    assert resp.status_code == 201
    assert resp.get_json()["entity"]["title"] == "Book"

    resp = client.get("/modules/library/entities/Book/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["entity"]["title"] == "Book"

    resp = client.get("/modules/library/entities/", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["entities"][0]["title"] == "Book"

    resp = client.delete("/modules/library/entities/Book/", headers=headers)
    assert resp.status_code == 200


def test_entity_api_requires_superuser():
    app = Flask(__name__)
    service = StubEntityService()
    register_entity_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    payload = {"type": "object", "additionalProperties": False, "properties": {}, "required": []}

    resp = client.get("/modules/library/entities/")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication_error"

    resp = client.get("/modules/library/entities/", headers={"Authorization": "Token bad"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication_error"

    service.schemas[("library", "Book")] = {"title": "Book", "type": "object", "properties": {}, "required": []}
    resp = client.get("/modules/library/entities/", headers={"Authorization": "Bearer admin"})
    assert resp.status_code == 200

    resp = client.get("/modules/library/entities/Book/", headers={"Authorization": "Bearer admin"})
    assert resp.status_code == 200

    resp = client.get("/modules/library/entities/", headers={"Authorization": "Bearer user"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "access_denied"

    resp = client.get("/modules/library/entities/Book/", headers={"Authorization": "Bearer user"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "access_denied"

    resp = client.post(
        "/modules/library/entities/Book/",
        json={"entity": payload},
        headers={"Authorization": "Bearer admin"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "access_denied"


def test_entity_api_returns_schema_validation_details():
    app = Flask(__name__)
    service = StubEntityService()
    register_entity_routes(app, service, url_prefix="")
    app.config["auth_service"] = StubAuthService()
    client = app.test_client()

    resp = client.post(
        "/modules/library/entities/Book/",
        json={"entity": {"_error": "schema_validation"}},
        headers={"Authorization": "Bearer super"},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "schema_validation_failed"
    assert body["error_description"].startswith("Invalid schema")
    assert body["details"]["field_errors"][0]["location"] == ["properties", "name", "type"]
    assert body["details"]["field_errors"][0]["keyword"] == "required"

    resp = client.post(
        "/modules/library/entities/Book/",
        json={"entity": {"_error": "schema_validation_multi"}},
        headers={"Authorization": "Bearer super"},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "schema_validation_failed"
    assert body["error_description"] == "Schema contains multiple validation errors"
    assert len(body["details"]["field_errors"]) == 2
