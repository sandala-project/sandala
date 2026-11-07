from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import re

import pytest

from sandala.api.app import create_app


@contextmanager
def mongo_app(mongo_image: str = "mongo:7.0", mongo_db: str = "sandala_it_api_errors"):
    mongodb_mod = pytest.importorskip("testcontainers.mongodb")
    wait_mod = pytest.importorskip("testcontainers.core.wait_strategies")
    MongoDbContainer = mongodb_mod.MongoDbContainer
    LogMessageWaitStrategy = wait_mod.LogMessageWaitStrategy

    class StableMongoDbContainer(MongoDbContainer):
        def _connect(self) -> None:
            LogMessageWaitStrategy(re.compile(r"waiting for connections", re.IGNORECASE)).wait_until_ready(self)

    with StableMongoDbContainer(mongo_image) as mongo:
        app = create_app(
            {
                "MONGO_URI": mongo.get_connection_url(),
                "MONGO_DB": mongo_db,
                "ROOT_USERNAME": "admin",
                "ROOT_PASSWORD": "Admin123!",
                "DEFAULT_GROUP_GROUPNAME": "default",
                "AUTH_SESSION_COOKIE_SECURE": False,
            }
        )
        yield app


@pytest.mark.integration
def test_node_create_returns_structured_document_validation_error():
    with mongo_app(mongo_db="sandala_it_api_errors_create") as app:
        client = app.test_client()
        _login_root(client)
        _seed_library_module_and_entity(app, _book_with_profile_schema())

        resp = client.post(
            "/api/v1/nodes/library/",
            json={
                "node": {
                    "entity": "Book",
                    "name": "War and Peace",
                    "profile": {"age": "not-an-integer"},
                }
            },
        )

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "document_validation_failed"
        assert body["error_description"].startswith("Node validation failed")
        assert body["details"]["field_errors"][0]["location"] == ["profile", "age"]
        assert body["details"]["field_errors"][0]["keyword"] == "type"


@pytest.mark.integration
def test_node_patch_returns_structured_document_validation_error():
    with mongo_app(mongo_db="sandala_it_api_errors_patch") as app:
        client = app.test_client()
        _login_root(client)
        _seed_library_module_and_entity(app, _book_with_profile_schema())

        created = app.config["node_service"].create(
            "library",
            "Book",
            {
                "name": "War and Peace",
                "profile": {"age": 42},
            },
            actor=_root_actor(app),
        )

        resp = client.patch(
            f"/api/v1/nodes/library/{created['id']}/",
            json={"node": {"profile": {"age": "not-an-integer"}}},
        )

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "document_validation_failed"
        assert body["error_description"].startswith("Node validation failed")
        assert body["details"]["field_errors"][0]["location"] == ["profile", "age"]
        assert body["details"]["field_errors"][0]["keyword"] == "type"


@pytest.mark.integration
def test_entity_update_returns_structured_schema_validation_error():
    with mongo_app(mongo_db="sandala_it_api_errors_schema") as app:
        client = app.test_client()
        _login_root(client)
        _seed_library_module_and_entity(app, _simple_book_schema())

        invalid_schema = _simple_book_schema()
        invalid_schema["x-meta"]["perm"] = {}

        resp = client.put("/api/v1/modules/library/entities/Book/", json={"entity": invalid_schema})

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "schema_validation_failed"
        assert body["error_description"].startswith("Invalid schema")
        assert body["details"]["field_errors"][0]["location"] == ["x-meta", "perm", "default"]
        assert body["details"]["field_errors"][0]["keyword"] == "required"


@pytest.mark.integration
def test_query_operand_types_and_boolean_pagination_fail_before_aggregation(monkeypatch):
    with mongo_app(mongo_db="sandala_it_api_errors_query_types") as app:
        client = app.test_client()
        _login_root(client)
        schema = _simple_book_schema()
        modes = {"visibility-mode": "all", "write-mode": "all"}
        schema["properties"].update({
            "tags": {"type": "array", "items": deepcopy(schema["properties"]["name"]),
                     "x-meta": {"semantic-type": "Array", **modes}},
            "profile": {"type": "object", "additionalProperties": False,
                        "properties": {"caption": deepcopy(schema["properties"]["name"])},
                        "x-meta": {"semantic-type": "Object", **modes}},
        })
        _seed_library_module_and_entity(app, schema)
        service = app.config["node_service"]
        node = service.create("library", "Book", {"name": "Alpha", "tags": [], "profile": {"caption": "known"}}, actor=_root_actor(app))
        invalid_queries = [
            {"filter": {"name": {"in": "Alpha"}}}, {"filter": {"name": {"nin": None}}},
            {"filter": {"name": {"exists": 1}}}, {"filter": {"name": {"exists": "false"}}},
            *[{"filter": {"tags": {"size": value}}} for value in (True, False, -1, 1.5, "0")],
            {"filter": {"name": {"regex": {}}}},
            {"filter": {"and": [{"or": [{"profile.caption": {"in": {}}}]}]}},
            *[{parameter: value} for parameter in ("limit", "offset") for value in (True, False, 2**63, 2**80)],
        ]

        def unexpected_aggregate(*args, **kwargs):
            pytest.fail("Invalid query reached Mongo aggregation")

        with monkeypatch.context() as patcher:
            patcher.setattr(service._node_repo, "aggregate", unexpected_aggregate)
            for query in invalid_queries:
                for url in ("/api/v1/nodes/library/query/", "/api/v1/nodes/library/entity/Book/query/"):
                    response = client.post(url, json={"query": {"project": ["id"], **query}})
                    assert response.status_code == 400
                    assert response.get_json()["error"] == "query_validation_failed"

        for query, count in [
            ({"filter": {"name": {"in": []}}}, 0), ({"filter": {"name": {"nin": []}}}, 1),
            ({"filter": {"tags": {"size": 0}}}, 1), ({"filter": {"tags": {"eq": []}}}, 1),
            ({"filter": {"name": {"regex": ""}}}, 1), ({"filter": {"name": {"exists": False}}}, 0),
            ({"filter": {"profile": {"eq": {"caption": "known"}}}}, 1),
            ({"limit": 1, "offset": 0}, 1), ({"limit": None, "offset": 0}, 1),
            ({"limit": 2**63 - 1}, 1), ({"offset": 2**63 - 1}, 0),
        ]:
            response = client.post("/api/v1/nodes/library/query/", json={"query": {"project": ["id"], **query}})
            assert response.status_code == 200
            assert response.get_json()["nodes"] == [{"id": node["id"]}] * count


@pytest.mark.integration
def test_known_mongo_query_rejections_return_400_and_unclassified_failures_remain_500(monkeypatch):
    with mongo_app(mongo_db="sandala_it_api_errors_query_execution") as app:
        client = app.test_client()
        _login_root(client)
        schema = _simple_book_schema()
        modes = {"visibility-mode": "all", "write-mode": "all"}
        scalar = schema["properties"]["name"]
        for field in ("left", "right"):
            schema["properties"][field] = {
                "type": "array", "items": deepcopy(scalar), "x-meta": {"semantic-type": "Array", **modes},
            }
        for index in range(32):
            schema["properties"][f"sort{index}"] = deepcopy(scalar)
        _seed_library_module_and_entity(app, schema)
        service = app.config["node_service"]
        service.create("library", "Book", {
            "name": "Alpha", "left": ["A", "B"], "right": ["C", "D"],
        }, actor=_root_actor(app))
        urls = ("/api/v1/nodes/library/query/", "/api/v1/nodes/library/entity/Book/query/")

        for query, message in [
            ({"filter": {"name": {"regex": "["}}}, "Query contains an invalid regular expression"),
            ({"sort": {"left": "asc", "right": "asc"}},
             "Query contains values or operations unsupported by the database"),
            ({"sort": {f"sort{index}": "asc" for index in range(32)}}, "Sort contains too many fields"),
        ]:
            for url in urls:
                response = client.post(url, json={"query": {"project": ["id"], **query}})
                assert response.status_code == 400
                assert response.get_json() == {"error": "query_validation_failed", "error_description": message}

        # A defect in the generated pipeline is not a client validation error.
        aggregate = service._node_repo.aggregate

        def invalid_pipeline(module, pipeline):
            return aggregate(module, [{"$PRIVATE_invalid_stage": {}}])

        with monkeypatch.context() as patcher:
            patcher.setattr(service._node_repo, "aggregate", invalid_pipeline)
            for url in urls:
                response = client.post(url, json={"query": {"project": ["id"]}})
                assert response.status_code == 500
                assert response.get_json() == {"error": "internal_error", "error_description": "Internal server error"}


@pytest.mark.integration
def test_node_reads_reject_mongo_id_but_preserve_user_object_id_fields():
    with mongo_app(mongo_db="sandala_it_api_errors_mongo_id") as app:
        client = app.test_client()
        _login_root(client)
        actor = _root_actor(app)
        schema = _book_with_profile_schema()
        schema["properties"]["profile"]["properties"]["_id"] = deepcopy(schema["properties"]["name"])
        schema["properties"]["profiles"] = {
            "type": "array", "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
            "items": {"type": "object", "additionalProperties": False,
                      "properties": {"_id": deepcopy(schema["properties"]["name"])},
                      "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"}},
        }
        _seed_library_module_and_entity(app, schema)
        for field, semantic in (("related", "Link"), ("references", "LinkArray")):
            reference = {"x-meta": {"semantic-type": semantic, "visibility-mode": "all", "write-mode": "all",
                                    "link": {"module": "library", "entities": ["Book"]}}}
            reference.update({"type": "string", "format": "uuid"} if semantic == "Link" else
                             {"type": "array", "items": {"type": "string", "format": "uuid"}})
            schema["properties"][field] = reference
        app.config["entity_service"].update("library", "Book", schema, actor=actor)
        service = app.config["node_service"]
        target = service.create("library", "Book", {
            "name": "Target", "profile": {"age": 42, "_id": "target-profile"}, "profiles": [{"_id": "target-array"}],
        }, actor=actor)
        source = service.create("library", "Book", {
            "name": "Source", "profile": {"age": 1, "_id": "source-profile"},
            "profiles": [{"_id": "source-array"}],
            "related": target["id"], "references": [target["id"]],
        }, actor=actor)
        query_urls = ("/api/v1/nodes/library/query/", "/api/v1/nodes/library/entity/Book/query/")
        for project in (["_id"], ["*", "_id"], ["related._id"], ["references._id"], ["related.related._id"]):
            responses = [client.get(f"/api/v1/nodes/library/{source['id']}/", query_string={"project": json.dumps(project)})]
            responses.extend(client.post(url, json={"query": {"filter": {"id": source["id"]}, "project": project}}) for url in query_urls)
            for response in responses:
                assert response.status_code == 400
                assert response.get_json()["error"] == "query_validation_failed"

        for options in ({"filter": {"id": source["id"], "related._id": {"exists": True}}},
                        {"sort": {"references._id": "asc"}}):
            response = client.post(query_urls[0], json={"query": {"project": ["*"], **options}})
            assert response.status_code == 400
            assert response.get_json()["error"] == "query_validation_failed"

        response = client.post(query_urls[0], json={"query": {
            "filter": {"id": source["id"], "related.profile._id": "target-profile"}, "sort": {"_id": "desc"},
            "project": ["id", "profile._id", "profiles._id", "related.id", "related.profile._id", "references.profile._id",
                        "related.profiles._id", "references.profiles._id"],
        }})
        assert response.status_code == 200
        assert response.get_json()["nodes"] == [{
            "id": source["id"], "profile": {"_id": "source-profile"}, "profiles": [{"_id": "source-array"}],
            "related": {"id": target["id"], "profile": {"_id": "target-profile"}, "profiles": [{"_id": "target-array"}]},
            "references": [{"profile": {"_id": "target-profile"}, "profiles": [{"_id": "target-array"}]}],
        }]
        response = client.get(f"/api/v1/nodes/library/{source['id']}/")
        assert response.status_code == 200
        row = response.get_json()["node"]
        assert "_id" not in row and "_id" not in row["related"]
        assert all("_id" not in reference for reference in row["references"])
        assert row["related"]["profile"]["_id"] == "target-profile"


@pytest.mark.integration
def test_invalid_user_field_names_return_structured_schema_errors_without_saving():
    with mongo_app(mongo_db="sandala_it_api_errors_field_names") as app:
        client = app.test_client()
        _login_root(client)
        _seed_library_module_and_entity(app, _simple_book_schema())
        original = app.config["entity_service"].get_schema("library", "Book", actor=_root_actor(app))
        for name in ("a.b", "$secret", "", "*", "a\x00b", "__sandala_tmp", "_id", "and", "or", "not"):
            schema = _simple_book_schema()
            schema["properties"][name] = deepcopy(schema["properties"]["name"])
            for method, entity in ((client.post, "InvalidBook"), (client.put, "Book")):
                resp = method(f"/api/v1/modules/library/entities/{entity}/", json={"entity": schema})
                assert resp.status_code == 400
                body = resp.get_json()
                assert body["error"] == "schema_validation_failed"
                errors = body["details"]["field_errors"]
                assert errors and errors[0]["location"] == ["properties"]
                assert errors[0]["keyword"] in {"minLength", "not"}
            assert client.get("/api/v1/modules/library/entities/InvalidBook/").status_code == 404
            assert app.config["entity_service"].get_schema("library", "Book", actor=_root_actor(app)) == original

        schema = _simple_book_schema()
        schema["properties"]["sections"] = {
            "type": "array", "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
            "items": {"anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False,
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
                "properties": {"private.token": deepcopy(schema["properties"]["name"])},
            }]},
        }
        resp = client.put("/api/v1/modules/library/entities/Book/", json={"entity": schema})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"] == "schema_validation_failed"
        assert body["details"]["field_errors"][0]["location"][:2] == ["properties", "sections"]
        assert app.config["entity_service"].get_schema("library", "Book", actor=_root_actor(app)) == original


@pytest.mark.integration
def test_entity_array_item_restrictions_return_structured_schema_errors():
    with mongo_app(mongo_db="sandala_it_api_errors_array_items") as app:
        client = app.test_client()
        _login_root(client)
        _seed_library_module_and_entity(app, _simple_book_schema())
        modes = {"visibility-mode": "all", "write-mode": "all"}
        original = app.config["entity_service"].get_schema("library", "Book", actor=_root_actor(app))
        for semantic_type in ("Array", "Link", "LinkArray"):
            if semantic_type == "Array":
                field = {"type": "array", "items": _simple_book_schema()["properties"]["name"],
                         "x-meta": {"semantic-type": "Array", **modes}}
            else:
                field = {"x-meta": {"semantic-type": semantic_type, **modes,
                                    "link": {"module": "library", "entities": ["Book"]}}}
                field.update({"type": "string", "format": "uuid"} if semantic_type == "Link"
                             else {"type": "array", "items": {"type": "string", "format": "uuid"}})
            for nullable in (False, True):
                schema = _simple_book_schema()
                schema["properties"]["values"] = {
                    "type": "array", "x-meta": {"semantic-type": "Array", **modes},
                    "items": {"anyOf": [{"type": "null"}, field]} if nullable else field,
                }
                for method, entity in ((client.post, "InvalidBook"), (client.put, "Book")):
                    resp = method(f"/api/v1/modules/library/entities/{entity}/", json={"entity": schema})
                    assert resp.status_code == 400
                    body = resp.get_json()
                    assert body["error"] == "schema_validation_failed"
                    assert body["details"]["field_errors"]
                    assert body["details"]["field_errors"][0]["location"][:2] == ["properties", "values"]
                assert client.get("/api/v1/modules/library/entities/InvalidBook/").status_code == 404
                assert app.config["entity_service"].get_schema("library", "Book", actor=_root_actor(app)) == original


@pytest.mark.integration
def test_users_user_create_returns_specific_conflict_codes_for_username_and_email():
    with mongo_app(mongo_db="sandala_it_api_errors_user_conflicts") as app:
        client = app.test_client()
        _login_root(client)

        created = client.post(
            "/api/v1/nodes/users/",
            json={
                "node": {
                    "entity": "user",
                    "username": "alice",
                    "email": "alice@example.com",
                    "password": "Abcd1234!",
                    "groups": [],
                }
            },
        )
        assert created.status_code == 201

        username_resp = client.post(
            "/api/v1/nodes/users/",
            json={
                "node": {
                    "entity": "user",
                    "username": "alice",
                    "password": "Abcd1234!",
                    "groups": [],
                }
            },
        )
        assert username_resp.status_code == 409
        assert username_resp.get_json()["error"] == "username_already_exists"

        email_resp = client.post(
            "/api/v1/nodes/users/",
            json={
                "node": {
                    "entity": "user",
                    "username": "another-alice",
                    "email": "alice@example.com",
                    "password": "Abcd1234!",
                    "groups": [],
                }
            },
        )
        assert email_resp.status_code == 409
        assert email_resp.get_json()["error"] == "email_already_exists"


def _login_root(client) -> None:
    resp = client.post("/api/v1/auth/login/", json={"credentials": {"login": "admin", "password": "Admin123!"}})
    assert resp.status_code == 200


def _seed_library_module_and_entity(app, schema: dict) -> None:
    actor = _root_actor(app)
    app.config["module_service"].create_module(
        {
            "name": "library",
            "description": "Library",
            "root_owner": actor["user_id"],
            "root_group": actor["primary_group"],
            "root_children_entities": [],
            "root_perm": {
                "owner": {"p": True},
                "group": {"p": True},
                "others": {"p": True},
            },
        },
        actor=actor,
    )
    app.config["entity_service"].create("library", "Book", deepcopy(schema), actor=actor)
    app.config["module_service"].patch_module(
        "library",
        {"root_children_entities": ["Book"]},
        actor=actor,
    )


def _root_actor(app) -> dict[str, object]:
    root_user = app.config["node_service"]._node_repo.find_one(
        "users",
        {"entity": "user", "deleted": False, "username": "admin"},
        {"_id": 0, "id": 1, "primary_group": 1, "groups": 1, "role": 1},
    )
    assert root_user is not None
    return {
        "user_id": root_user["id"],
        "primary_group": root_user["primary_group"],
        "groups": root_user["groups"],
        "role": root_user["role"],
    }


def _simple_book_schema() -> dict:
    return {
        "title": "Book",
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "x-meta": {
                    "semantic-type": "String",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            }
        },
        "required": ["name"],
        "x-meta": {
            "children": {"entities": []},
            "perm": {
                "default": {
                    "owner": {"r": True, "w": True, "p": True},
                    "group": {"r": False, "w": False, "p": False},
                    "others": {"r": False, "w": False, "p": False},
                }
            },
        },
    }


def _book_with_profile_schema() -> dict:
    schema = _simple_book_schema()
    schema["properties"]["profile"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "age": {
                "type": "integer",
                "x-meta": {
                    "semantic-type": "Integer",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            }
        },
        "required": ["age"],
        "x-meta": {
            "semantic-type": "Object",
            "visibility-mode": "all",
            "write-mode": "all",
        },
    }
    schema["required"].append("profile")
    return schema
