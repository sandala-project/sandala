from __future__ import annotations

import json

from flask import Flask

from sandala.api.routes_node import register_node_routes
from sandala.core.errors import (
    ConflictError,
    DescendantWriteForbiddenError,
    DocumentValidationError,
    FieldWriteForbiddenError,
    NotFoundError,
    ParentNodeNotFoundError,
    QueryValidationError,
    ValidationError,
)


class StubNodeService:
    def __init__(self):
        self.calls = []

    def create(self, module, entity, payload, actor=None):
        self.calls.append((module, entity, payload, actor))
        if payload.get("_error") == "crash":
            raise RuntimeError("database exploded")
        if payload.get("_error") == "not_found":
            raise NotFoundError("not found")
        if payload.get("_error") == "parent_not_found":
            raise ParentNodeNotFoundError("Parent node 'missing' not found in module 'library'")
        if payload.get("_error") == "conflict":
            raise ConflictError("conflict")
        if payload.get("_error") == "field_write_forbidden":
            raise FieldWriteForbiddenError("Field 'secret' is not writable for current actor")
        if payload.get("_error") == "document_validation":
            raise DocumentValidationError(
                "Node validation failed at 'profile.email': 'bad' is not a 'email'",
                details={
                    "field_errors": [
                        {
                            "location": ["profile", "email"],
                            "message": "'bad' is not a 'email'",
                            "keyword": "format",
                        }
                    ]
                },
            )
        if payload.get("_error") == "document_validation_nullable":
            raise DocumentValidationError(
                "Node validation failed at 'nickname': 1 is not of type 'string'",
                details={
                    "field_errors": [
                        {
                            "location": ["nickname"],
                            "message": "1 is not of type 'string'",
                            "keyword": "type",
                        }
                    ]
                },
            )
        if payload.get("_error") == "document_validation_multi":
            raise DocumentValidationError(
                "Document contains multiple validation errors",
                details={
                    "field_errors": [
                        {
                            "location": [],
                            "message": "Additional properties are not allowed ('extra' was unexpected)",
                            "keyword": "additionalProperties",
                        },
                        {
                            "location": ["profile", "age"],
                            "message": "'bad' is not of type 'integer'",
                            "keyword": "type",
                        },
                    ]
                },
            )
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        return {"id": "x", "entity": entity, "name": payload.get("name", "")}

    def query(self, module, payload, actor=None):
        if payload.get("_error") == "query_validation":
            raise QueryValidationError("filter must be an object")
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        return [{"id": "n1", "entity": "Book"}]

    def get(self, module, node_id, *, project=None, actor=None):
        self.calls.append(("get", module, node_id, project, actor))
        if node_id == "missing":
            raise NotFoundError("not found")
        return {"id": node_id, "entity": "Book"}

    def list_entity(self, module, entity, payload, *, actor=None):
        self.calls.append(("list_entity", module, entity, payload, actor))
        if entity == "missing":
            raise NotFoundError("not found")
        return [{"id": "n1", "entity": entity}]

    def patch(self, module, node_id, payload, actor=None):
        self.calls.append((module, node_id, payload, actor))
        if payload.get("_error") == "not_found":
            raise NotFoundError("not found")
        if payload.get("_error") == "conflict":
            raise ConflictError("conflict")
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        return {"id": node_id, "entity": "Book", "name": payload.get("name", "")}

    def patch_acl(self, module, node_id, payload, *, recursive=False, actor=None):
        self.calls.append(("acl", module, node_id, payload, recursive, actor))
        if payload.get("_error") == "not_found":
            raise NotFoundError("not found")
        if payload.get("_error") == "validation":
            raise ValidationError("bad")
        return {
            "node": {"id": node_id, "entity": "Book"},
            "updated_count": 3 if recursive else 1,
        }

    def delete(self, module, node_id, actor=None):
        self.calls.append((module, node_id, actor))
        if node_id == "missing":
            raise NotFoundError("not found")
        if node_id == "descendant-denied":
            raise DescendantWriteForbiddenError()
        return 3


def test_node_api_create_success_and_errors():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "name": "A"}})
    assert resp.status_code == 201
    assert resp.get_json()["node"]["entity"] == "Book"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "not_found"}})
    assert resp.status_code == 404

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "conflict"}})
    assert resp.status_code == 409

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "parent_not_found"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parent_node_not_found"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "field_write_forbidden"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "field_write_forbidden"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_error"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "document_validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "document_validation_failed"
    assert resp.get_json()["details"]["field_errors"][0]["location"] == ["profile", "email"]
    assert resp.get_json()["details"]["field_errors"][0]["keyword"] == "format"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "document_validation_nullable"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "document_validation_failed"
    assert resp.get_json()["error_description"] == "Node validation failed at 'nickname': 1 is not of type 'string'"
    assert resp.get_json()["details"]["field_errors"][0]["location"] == ["nickname"]
    assert resp.get_json()["details"]["field_errors"][0]["keyword"] == "type"

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "document_validation_multi"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "document_validation_failed"
    assert resp.get_json()["error_description"] == "Document contains multiple validation errors"
    assert len(resp.get_json()["details"]["field_errors"]) == 2

    resp = client.post("/nodes/library/", data="not-json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"

    resp = client.post("/nodes/library/", json={"node": {"name": "A"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parameter_invalid"


def test_node_api_query_success_and_errors():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.post("/nodes/library/query/", json={"query": {}})
    assert resp.status_code == 200
    assert resp.get_json()["nodes"][0]["id"] == "n1"

    resp = client.post("/nodes/library/query/", json={"query": {"_error": "validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_error"

    resp = client.post("/nodes/library/query/", json={"query": {"_error": "query_validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "query_validation_failed"

    resp = client.post("/nodes/library/query/", data="x", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"

    resp = client.post("/nodes/library/query/", json={"filter": {"entity": "Book"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"


def test_node_api_get_node_parses_optional_project():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.get("/nodes/library/book-1/", query_string={"project": json.dumps(["name", "author.*"])})

    assert resp.status_code == 200
    assert resp.get_json()["node"]["id"] == "book-1"
    assert service.calls[-1] == ("get", "library", "book-1", ["name", "author.*"], None)

    raw_wildcard = client.get("/nodes/library/book-1/", query_string={"project": "*"})
    assert raw_wildcard.status_code == 200
    assert service.calls[-1] == ("get", "library", "book-1", "*", None)

    json_wildcard = client.get("/nodes/library/book-1/", query_string={"project": json.dumps("*")})
    assert json_wildcard.status_code == 200
    assert service.calls[-1] == ("get", "library", "book-1", "*", None)

    invalid = client.get("/nodes/library/book-1/", query_string={"project": json.dumps({"name": 1})})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "parameter_invalid"


def test_node_api_query_entity_parses_query_wrapper():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.post(
        "/nodes/library/entity/Book/query/",
        json={
            "query": {
                "project": ["name", "author.*"],
                "filter": {"year": {"gte": 2020}},
                "sort": {"name": "asc"},
                "limit": 20,
                "offset": 5,
            }
        },
    )

    assert resp.status_code == 200
    assert resp.get_json()["nodes"] == [{"id": "n1", "entity": "Book"}]
    assert service.calls[-1] == (
        "list_entity",
        "library",
        "Book",
        {
            "project": ["name", "author.*"],
            "filter": {"year": {"gte": 2020}},
            "sort": {"name": "asc"},
            "limit": 20,
            "offset": 5,
        },
        None,
    )

    invalid = client.post("/nodes/library/entity/Book/query/", json={"filter": {"year": 2020}})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "request_body_invalid"


def test_node_api_patch_success_and_errors():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.patch("/nodes/library/book-1/", json={"node": {"name": "A"}})
    assert resp.status_code == 200
    assert resp.get_json()["node"]["id"] == "book-1"

    resp = client.patch("/nodes/library/book-1/", json={"node": {"_error": "not_found"}})
    assert resp.status_code == 404

    resp = client.patch("/nodes/library/book-1/", json={"node": {"_error": "conflict"}})
    assert resp.status_code == 409

    resp = client.patch("/nodes/library/book-1/", json={"node": {"_error": "validation"}})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "validation_error"

    resp = client.patch("/nodes/library/book-1/", data="not-json", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "request_body_invalid"


def test_node_api_acl_patch_success_and_errors():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.patch(
        "/nodes/library/book-1/acl/",
        json={"node": {"perm": {"owner": {"r": True}}}, "recursive": True},
    )
    assert resp.status_code == 200
    assert resp.get_json()["updated_count"] == 3
    assert service.calls[-1][4] is True

    resp = client.patch(
        "/nodes/library/book-1/acl/",
        json={"node": {"perm": {}}, "recursive": "invalid"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "parameter_invalid"

    resp = client.patch("/nodes/library/book-1/acl/", json={"node": {"_error": "not_found"}})
    assert resp.status_code == 404


def test_node_api_delete_success_and_not_found():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.delete("/nodes/library/book-1/")
    assert resp.status_code == 200
    assert resp.get_json()["deleted_count"] == 3

    resp = client.delete("/nodes/library/missing/")
    assert resp.status_code == 404

    resp = client.delete("/nodes/library/descendant-denied/")
    assert resp.status_code == 400
    assert resp.get_json() == {
        "error": "descendant_write_forbidden",
        "error_description": "Write to one or more descendants is not allowed",
    }


def test_node_api_optional_auth_header_validation():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.post(
        "/nodes/library/",
        json={"node": {"entity": "Book", "name": "A"}},
        headers={"Authorization": "Token x"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "authentication_error"


def test_node_api_hides_unexpected_internal_errors():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.post("/nodes/library/", json={"node": {"entity": "Book", "_error": "crash"}})

    assert resp.status_code == 500
    body = resp.get_json()
    assert body == {
        "error": "internal_error",
        "error_description": "Internal server error",
    }


def test_node_api_preserves_framework_404():
    app = Flask(__name__)
    service = StubNodeService()
    register_node_routes(app, service, url_prefix="")
    client = app.test_client()

    resp = client.get("/missing")

    assert resp.status_code == 404
