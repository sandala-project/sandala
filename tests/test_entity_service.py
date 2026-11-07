from __future__ import annotations

import copy
from typing import Any

import pytest

from sandala.core.errors import (
    AuthorizationError,
    ConflictError,
    DocumentValidationError,
    NotFoundError,
    SchemaValidationError,
    ValidationError,
)
from sandala.core.services.entity_service import EntityService
from sandala.core.users.schemas import group_schema, user_schema
from sandala.core.validation.schema_validator import SYSTEM_FIELDS, SYSTEM_PROPERTIES


TEST_DEFAULT_ENTITY_PERM = {
    "owner": {"r": True, "w": True, "p": True},
    "group": {"r": False, "w": False, "p": False},
    "others": {"r": False, "w": False, "p": False},
}
ADMIN_ACTOR = {"role": "admin"}
NONE_ROLE_ACTOR = {"role": "none"}
USER_ACTOR = {"role": "all"}
SUPERUSER_ACTOR = {"role": "superuser"}


def _entity_service(entity_repo, node_repo, module_repo=None):
    return EntityService(entity_repo, node_repo, module_repo or InMemoryModuleRepo(entity_repo, node_repo))


def _assert_error_contains(exc_info: pytest.ExceptionInfo[ValidationError], *parts: str) -> None:
    message = str(exc_info.value)
    details = exc_info.value.details or {}
    validation_errors = details.get("validation_errors", [])
    fragments = [message]
    for item in validation_errors:
        path = ".".join(str(part) for part in item.get("path", []))
        if path:
            fragments.append(path)
        raw_message = item.get("raw_message")
        if isinstance(raw_message, str):
            fragments.append(raw_message)
        validator = item.get("validator")
        if isinstance(validator, str):
            fragments.append(validator)
    haystack = "\n".join(fragments)
    for part in parts:
        assert part in haystack


def test_entity_read_operations_require_admin_or_superuser_actor():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)

    with pytest.raises(TypeError):
        svc.list_entities("library")
    entities = svc.list_entities("library", actor=ADMIN_ACTOR)
    assert entities[0]["title"] == "Book"
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.list_entities("library", actor=USER_ACTOR)
    with pytest.raises(TypeError):
        svc.get_schema("library", "Book")

    schema = svc.get_schema("library", "Book", actor=ADMIN_ACTOR)
    assert schema["title"] == "Book"
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.get_schema("library", "Book", actor=USER_ACTOR)
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.list_entities("library", actor=NONE_ROLE_ACTOR)
    with pytest.raises(AuthorizationError, match="Only admin or superuser"):
        svc.get_schema("library", "Book", actor=NONE_ROLE_ACTOR)


class InMemoryEntityRepo:
    def __init__(self):
        self.docs = []
        self.next_id = 1

    def list_entities(self, module):
        result = []
        for doc in self.docs:
            if doc["module"] == module:
                result.append(
                    {
                        "title": doc["schema"].get("title", ""),
                        "description": doc["schema"].get("description", ""),
                    }
                )
        return result

    def get_schema(self, module, entity):
        for doc in self.docs:
            if doc["module"] == module and doc["entity"] == entity:
                return copy.deepcopy(doc["schema"])
        return None

    def entity_exists(self, module, entity):
        return self.get_schema(module, entity) is not None

    def module_exists(self, module):
        return any(doc["module"] == module for doc in self.docs)

    def create(self, module, entity, schema):
        self.docs.append({"_id": self.next_id, "module": module, "entity": entity, "schema": copy.deepcopy(schema)})
        self.next_id += 1

    def update(self, module, entity, schema):
        for doc in self.docs:
            if doc["module"] == module and doc["entity"] == entity:
                doc["schema"] = copy.deepcopy(schema)
                return

    def delete(self, module, entity):
        self.docs = [doc for doc in self.docs if not (doc["module"] == module and doc["entity"] == entity)]

    def iter_all(self):
        return copy.deepcopy(self.docs)

    def replace_schema(self, doc_id, schema):
        for doc in self.docs:
            if doc["_id"] == doc_id:
                doc["schema"] = copy.deepcopy(schema)


class InMemoryNodeRepo:
    def __init__(self):
        self.nodes = {}

    def count_active_in_entity(self, module, entity):
        return sum(1 for node in self.nodes.get(module, []) if node.get("entity") == entity and not node.get("deleted", False))

    def iter_by_entity(self, module, entity):
        for node in self.nodes.get(module, []):
            if node.get("entity") == entity:
                yield copy.deepcopy(node)


class InMemoryModuleRepo:
    def __init__(self, entity_repo: InMemoryEntityRepo, node_repo: InMemoryNodeRepo):
        self._entity_repo = entity_repo
        self._node_repo = node_repo
        self.docs: dict[str, dict[str, Any]] = {}

    def module_exists(self, module: str) -> bool:
        return self.get_module(module) is not None

    def get_module(self, module: str) -> dict[str, Any] | None:
        doc = self.docs.get(module)
        if doc is not None:
            return copy.deepcopy(doc)
        if self._entity_repo.module_exists(module) or module in self._node_repo.nodes:
            return {
                "name": module,
                "description": module,
                "root_owner": "11111111-1111-4111-8111-111111111111",
                "root_group": "22222222-2222-4222-8222-222222222222",
                "root_children_entities": [],
                "root_perm": {
                    "owner": {"p": True},
                    "group": {"p": True},
                    "others": {"p": True},
                },
            }
        return None

    def update_module(self, module: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_module(module)
        if current is None:
            return None
        current.update(copy.deepcopy(patch))
        self.docs[module] = current
        return copy.deepcopy(current)


def _base_schema(entity="Book"):
    return {
        "title": entity,
        "description": "Book",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {
                "type": "string",
                "description": "Name",
                "x-meta": {
                    "semantic-type": "String", "visibility-mode": "all", "write-mode": "all",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            }
        },
        "required": ["name"],
        "x-meta": {"children": {"entities": []}, "perm": {"default": copy.deepcopy(TEST_DEFAULT_ENTITY_PERM)}},
    }


def _author_schema():
    schema = _base_schema("Author")
    schema["description"] = "Author"
    return schema


def _valid_media_field_schema(semantic_type: str) -> dict[str, Any]:
    properties = {
        "url": {"type": "string"},
        "mime-type": {"type": "string"},
        "size": {"type": "integer"},
    }
    required = ["url", "mime-type", "size"]
    if semantic_type == "Image":
        properties["width"] = {"type": "integer"}
        properties["height"] = {"type": "integer"}
        required.extend(["width", "height"])
    elif semantic_type == "File":
        required = ["url"]

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
        "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": "all"},
    }


def test_create_and_get_entity():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)

    created = svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)

    assert created["title"] == "Book"
    assert svc.get_schema("library", "Book", actor=SUPERUSER_ACTOR)["description"] == "Book"
    assert created["properties"]["name"]["x-meta"]["visibility-mode"] == "all"
    assert created["properties"]["name"]["x-meta"]["write-mode"] == "all"
    assert created["x-meta"]["perm"]["default"] == TEST_DEFAULT_ENTITY_PERM
    for field in SYSTEM_FIELDS:
        assert field in created["properties"]
        assert field in created["required"]


def test_create_accepts_schema_without_root_required():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)
    schema = _base_schema()
    schema.pop("required")

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert entity_repo.get_schema("library", "Book")["required"] == []
    assert set(SYSTEM_FIELDS).issubset(created["required"])


def test_create_accepts_root_ui_label_templates_and_rejects_unknown_ui_options():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["x-ui"] = {
        "labels": {
            "tree": "📚 {{name}}",
            "reference": "{{name}} ({{year}})",
        },
    }

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["x-ui"] == schema["x-ui"]

    invalid_schema = _base_schema()
    invalid_schema["x-ui"] = {"labels": {"unknown": "{{name}}"}}
    with pytest.raises(SchemaValidationError) as exc_info:
        svc.create("library", "Magazine", invalid_schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "x-ui", "Additional properties")


def test_create_rejects_when_x_meta_perm_block_missing():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)
    schema = _base_schema()
    schema["x-meta"] = {"children": {"entities": []}}

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "Invalid schema", "x-meta", "required property")


def test_create_returns_all_schema_validation_errors():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)
    schema = {
        "type": "object",
        "properties": {},
        "required": [],
        "x-meta": {},
    }

    with pytest.raises(SchemaValidationError, match="Schema contains multiple validation errors") as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    validation_errors = exc_info.value.details["validation_errors"]
    assert len(validation_errors) >= 2
    assert any(item["path"] == ["additionalProperties"] and item["validator"] == "required" for item in validation_errors)
    assert any(item["path"] == ["x-meta", "children"] and item["validator"] == "required" for item in validation_errors)
    assert any(item["path"] == ["x-meta", "perm"] and item["validator"] == "required" for item in validation_errors)


def test_create_fails_when_link_points_to_unknown_entity():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["library"] = []
    svc = _entity_service(entity_repo, node_repo)

    schema = _base_schema()
    schema["properties"]["author"] = {
        "type": "string",
        "format": "uuid",
        "description": "Author",
        "x-meta": {
            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
            "visibility-mode": "all",
            "write-mode": "all",
            "link": {"module": "library", "entities": ["Author"]},
        },
    }

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "references unknown entity", "author")


def test_create_accepts_explicit_system_fields_with_valid_perm_shape():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"].update(copy.deepcopy(SYSTEM_PROPERTIES))
    schema["required"].extend(SYSTEM_FIELDS)

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    # Stored entity schemas remain user-only, but returned schema is enriched.
    assert "perm" in created["properties"]
    assert created["properties"]["perm"]["required"] == ["owner", "group", "others"]


def test_create_rejects_invalid_perm_system_field_shape():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"].update(copy.deepcopy(SYSTEM_PROPERTIES))
    schema["required"].extend(SYSTEM_FIELDS)
    schema["properties"]["perm"]["properties"]["owner"]["required"] = ["r", "w"]

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "System field 'perm'", "invalid schema")


def test_create_rejects_invalid_x_meta_perm_default_shape():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["x-meta"]["perm"] = {"default": {"owner": {"r": True, "w": True}}}

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "x-meta.perm.default", "required")


def test_update_rejects_schema_without_x_meta_perm_default():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)

    updated_schema = _base_schema()
    updated_schema["x-meta"]["perm"] = {}
    with pytest.raises(ValidationError) as exc_info:
        svc.update("library", "Book", updated_schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "x-meta.perm", "required property")


def test_create_allows_empty_link_entities_array():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["library"] = []
    svc = _entity_service(entity_repo, node_repo)

    schema = _base_schema()
    schema["properties"]["author"] = {
        "type": "string",
        "format": "uuid",
        "description": "Author",
        "x-meta": {
            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
            "visibility-mode": "all",
            "write-mode": "all",
            "link": {"module": "library", "entities": []},
        },
    }
    schema["required"].append("author")

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    assert created["properties"]["author"]["x-meta"]["link"]["entities"] == []


def test_update_validates_existing_nodes_against_new_schema():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)

    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    node_repo.nodes["library"] = [
        {
            "id": "a",
            "entity": "Book",
            "parent": None,
            "depth": 0,
            "ancestors": [],
            "deleted": False,
            "cdate": "2025-01-01T00:00:00Z",
            "mdate": "2025-01-01T00:00:00Z",
            "name": "A",
        }
    ]

    stricter = _base_schema()
    stricter["properties"]["name"]["minLength"] = 3

    with pytest.raises(ValidationError):
        svc.update("library", "Book", stricter, actor=SUPERUSER_ACTOR)


def test_update_validates_existing_datetime_values_with_rfc3339_checker():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)

    schema = _base_schema()
    schema["properties"]["published_at"] = {
        "type": "string",
        "format": "date-time",
        "x-meta": {"semantic-type": "DateTime", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("published_at")
    svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    node_repo.nodes["library"] = [
        {
            "id": "a",
            "entity": "Book",
            "parent": None,
            "depth": 0,
            "ancestors": [],
            "deleted": False,
            "cdate": "2025-01-01T00:00:00Z",
            "mdate": "2025-01-01T00:00:00Z",
            "name": "A",
            "published_at": "2025-01-01T12:00:00",
        }
    ]

    with pytest.raises(DocumentValidationError):
        svc.update("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_update_persists_access_modes():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)

    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    updated_schema = _base_schema()
    updated_schema["properties"]["name"]["x-meta"]["visibility-mode"] = "admin"
    updated_schema["properties"]["name"]["x-meta"]["write-mode"] = "superuser"

    updated = svc.update("library", "Book", updated_schema, actor=SUPERUSER_ACTOR)

    assert updated["properties"]["name"]["x-meta"]["visibility-mode"] == "admin"
    assert updated["properties"]["name"]["x-meta"]["write-mode"] == "superuser"


def test_update_rejects_mutation_of_protected_users_user_field():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)
    svc.create("users", "user", user_schema(), actor=SUPERUSER_ACTOR)

    mutated = user_schema()
    mutated["properties"]["username"]["minLength"] = 4

    with pytest.raises(ValidationError, match="is immutable"):
        svc.update("users", "user", mutated, actor=SUPERUSER_ACTOR)


def test_update_allows_adding_custom_field_to_users_user_entity():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)
    svc.create("users", "user", user_schema(), actor=SUPERUSER_ACTOR)

    updated_schema = user_schema()
    updated_schema["properties"]["nickname"] = {
        "type": "string",
        "x-meta": {
            "semantic-type": "String",
            "visibility-mode": "all",
            "write-mode": "all",
        },
    }
    updated_schema["required"].append("nickname")

    updated = svc.update("users", "user", updated_schema, actor=SUPERUSER_ACTOR)
    assert "nickname" in updated["properties"]


def test_update_allows_changing_description_of_protected_users_user_field():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)
    svc.create("users", "user", user_schema(), actor=SUPERUSER_ACTOR)

    updated_schema = user_schema()
    updated_schema["properties"]["username"]["description"] = "User login"

    updated = svc.update("users", "user", updated_schema, actor=SUPERUSER_ACTOR)
    assert updated["properties"]["username"]["description"] == "User login"


def test_update_rejects_mutation_of_protected_users_group_field():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)

    mutated = group_schema()
    mutated["properties"]["groupname"]["minLength"] = 3

    with pytest.raises(ValidationError, match="is immutable"):
        svc.update("users", "group", mutated, actor=SUPERUSER_ACTOR)


def test_update_allows_adding_custom_field_to_users_group_entity():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)

    updated_schema = group_schema()
    updated_schema["properties"]["display_order"] = {
        "type": "integer",
        "x-meta": {
            "semantic-type": "Integer",
            "visibility-mode": "admin",
            "write-mode": "admin",
        },
    }

    updated = svc.update("users", "group", updated_schema, actor=SUPERUSER_ACTOR)
    assert "display_order" in updated["properties"]


def test_update_allows_changing_description_of_protected_users_group_field():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["users"] = []
    svc = _entity_service(entity_repo, node_repo)

    svc.create("users", "group", group_schema(), actor=SUPERUSER_ACTOR)

    updated_schema = group_schema()
    updated_schema["properties"]["groupname"]["description"] = "Public name"

    updated = svc.update("users", "group", updated_schema, actor=SUPERUSER_ACTOR)
    assert updated["properties"]["groupname"]["description"] == "Public name"


def test_delete_rejects_when_active_nodes_exist():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    svc = _entity_service(entity_repo, node_repo)

    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    node_repo.nodes["library"] = [{"entity": "Book", "deleted": False}]

    with pytest.raises(ConflictError):
        svc.delete("library", "Book", actor=SUPERUSER_ACTOR)


def test_delete_cleans_references_from_children_and_links():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["library"] = []
    module_repo = InMemoryModuleRepo(entity_repo, node_repo)
    module_repo.docs["library"] = {
        "name": "library",
        "description": "library",
        "root_owner": "11111111-1111-4111-8111-111111111111",
        "root_group": "22222222-2222-4222-8222-222222222222",
        "root_children_entities": ["Author", "Book"],
        "root_perm": {
            "owner": {"p": True},
            "group": {"p": True},
            "others": {"p": True},
        },
    }
    svc = _entity_service(entity_repo, node_repo, module_repo)

    svc.create("library", "Author", _author_schema(), actor=SUPERUSER_ACTOR)

    book_schema = _base_schema("Book")
    book_schema["x-meta"]["children"]["entities"] = ["Author"]

    library_schema = _base_schema("Library")
    library_schema["properties"]["favorite"] = {
        "type": "string",
        "format": "uuid",
        "description": "Favorite",
        "x-meta": {
            "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
            "visibility-mode": "all",
            "write-mode": "all",
            "link": {"module": "library", "entities": ["Author", "Book"]},
        },
    }

    svc.create("library", "Book", book_schema, actor=SUPERUSER_ACTOR)
    library_schema["properties"]["favorites"] = {
        "type": "array", "items": {"type": "string", "format": "uuid"},
        "x-meta": {"semantic-type": "LinkArray", "visibility-mode": "all", "write-mode": "all",
                   "link": {"module": "library", "entities": ["Author", "Book"]}},
    }
    svc.create("library", "Library", library_schema, actor=SUPERUSER_ACTOR)

    svc.delete("library", "Author", actor=SUPERUSER_ACTOR)

    updated_book = svc.get_schema("library", "Book", actor=SUPERUSER_ACTOR)
    assert "Author" not in updated_book["x-meta"]["children"]["entities"]

    updated_library = svc.get_schema("library", "Library", actor=SUPERUSER_ACTOR)
    entities = updated_library["properties"]["favorite"]["x-meta"]["link"]["entities"]
    assert "Author" not in entities
    assert updated_library["properties"]["favorites"]["x-meta"]["link"]["entities"] == ["Book"]
    assert updated_library["properties"]["favorites"]["items"] == {"type": "string", "format": "uuid"}
    assert module_repo.docs["library"]["root_children_entities"] == ["Book"]


@pytest.mark.parametrize("depth", [1, 3])
@pytest.mark.parametrize("null_first", [False, True])
def test_delete_cleans_links_inside_nullable_array_objects(depth, null_first):
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes = {"library": [], "archive": []}
    svc = _entity_service(entity_repo, node_repo)

    def nullable(schema):
        variants = [{"type": "null"}, schema] if null_first else [schema, {"type": "null"}]
        return {"anyOf": variants}

    def archive_schema(target_entities):
        fields = {}
        for name, semantic, target_module in (
            ("author", "Link", "library"),
            ("authors", "LinkArray", "library"),
            ("external_author", "Link", "archive"),
            ("external_authors", "LinkArray", "archive"),
        ):
            field = {
                "type": "string",
                "format": "uuid",
                "x-meta": {
                    "semantic-type": semantic,
                    "visibility-mode": "all",
                    "write-mode": "all",
                    "link": {
                        "module": target_module,
                        "entities": list(target_entities) if target_module == "library" else ["Author"],
                    },
                },
            }
            if semantic == "LinkArray":
                field.pop("format")
                field["type"] = "array"
                field["items"] = {"type": "string", "format": "uuid"}
            fields[name] = nullable(field)

        for _ in range(depth):
            item = {
                "type": "object",
                "additionalProperties": False,
                "properties": fields,
                "x-meta": {
                    "semantic-type": "Object",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            }
            fields = {"sections": nullable(_array_field(nullable(item)))}

        schema = _base_schema("Archive")
        schema["properties"].update(fields)
        return schema

    svc.create("library", "Author", _author_schema(), actor=SUPERUSER_ACTOR)
    svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    svc.create("archive", "Author", _author_schema(), actor=SUPERUSER_ACTOR)
    for module in ("library", "archive"):
        svc.create(module, "Archive", archive_schema(["Author", "Book"]), actor=SUPERUSER_ACTOR)

    svc.delete("library", "Author", actor=SUPERUSER_ACTOR)

    for module in ("library", "archive"):
        assert entity_repo.get_schema(module, "Archive") == archive_schema(["Book"])
    assert entity_repo.get_schema("archive", "Author") is not None
    assert entity_repo.get_schema("library", "Author") is None


def test_system_fields_must_be_all_or_none_and_in_both_sections():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()

    schema["properties"]["id"] = {"type": "string"}
    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "system fields", "properties")

    schema = _base_schema()
    schema["required"].append("id")
    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "system fields", "required")


def test_not_found_errors():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    with pytest.raises(NotFoundError):
        svc.get_schema("x", "y", actor=SUPERUSER_ACTOR)


@pytest.mark.parametrize(
    "field_schema",
    [
        (
            {
                "type": "integer",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "string",
                "x-meta": {"semantic-type": "Integer", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "string",
                "format": "date-time",
                "x-meta": {"semantic-type": "Date", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "string",
                "format": "date",
                "x-meta": {"semantic-type": "DateTime", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "string",
                "format": "date",
                "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "array",
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "object",
                "properties": {},
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
        (
            {
                "type": "object",
                "items": {
                    "type": "string",
                    "x-meta": {"semantic-type": "String", "visibility-mode": "all", "write-mode": "all"},
                },
                "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
            },
        ),
    ],
)
def test_invalid_semantic_type_combinations(field_schema):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["bad"] = field_schema
    schema["required"].append("bad")

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "properties.bad")


@pytest.mark.parametrize("semantic_type", ["Text", "RichText"])
def test_non_enum_string_semantic_types_allow_string_constraints(semantic_type):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["content"] = {
        "type": "string",
        "pattern": ".+",
        "minLength": 1,
        "maxLength": 1000,
        "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("content")

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["content"]["x-meta"]["semantic-type"] == semantic_type


@pytest.mark.parametrize("semantic_type", ["Password", "Text", "RichText"])
def test_non_enum_string_semantic_types_reject_enum_constraint(semantic_type):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["content"] = {
        "type": "string",
        "enum": ["draft", "published"],
        "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("content")

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "properties.content")


def test_password_semantic_type_is_allowed_in_object_and_array_items():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    password_meta = {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"}
    schema["properties"]["credentials"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "password": {"type": "string", "x-meta": password_meta},
        },
        "required": [],
        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["properties"]["previous_passwords"] = {
        "type": "array",
        "items": {"type": "string", "x-meta": password_meta},
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
    }

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["credentials"]["properties"]["password"]["x-meta"]["semantic-type"] == "Password"
    assert created["properties"]["previous_passwords"]["items"]["x-meta"]["semantic-type"] == "Password"


@pytest.mark.parametrize(
    ("container", "required_path"),
    [
        ("root", "password"),
        ("object", "credentials.password"),
        ("array_object", "credentials[].password"),
        ("array_password", "passwords"),
    ],
)
def test_password_fields_cannot_be_required(container, required_path):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    password_meta = {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"}

    if container == "root":
        schema["properties"]["password"] = {"type": "string", "x-meta": password_meta}
        schema["required"].append("password")
    elif container == "object":
        schema["properties"]["credentials"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"password": {"type": "string", "x-meta": password_meta}},
            "required": ["password"],
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
        }
    elif container == "array_object":
        schema["properties"]["credentials"] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"password": {"type": "string", "x-meta": password_meta}},
                "required": ["password"],
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            },
            "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        }
    else:
        schema["properties"]["passwords"] = {
            "type": "array",
            "items": {"type": "string", "x-meta": password_meta},
            "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
        }
        schema["required"].append("passwords")

    with pytest.raises(ValidationError, match="semantic type Password cannot be required") as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert required_path in str(exc_info.value)


def test_password_semantic_type_allows_zero_min_length():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["password"] = {
        "type": "string",
        "minLength": 0,
        "maxLength": 0,
        "x-meta": {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"},
    }

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["password"]["minLength"] == 0


def test_password_semantic_type_allows_string_constraints_when_not_required():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["password"] = {
        "type": "string",
        "pattern": ".+",
        "minLength": 1,
        "maxLength": 1000,
        "x-meta": {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"},
    }

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["password"]["pattern"] == ".+"


def test_invalid_object_nested_field_without_semantic_type():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["meta"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rank": {"type": "integer"},
        },
        "required": ["rank"],
        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("meta")

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "properties.meta")


def test_invalid_array_items_without_semantic_type():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["tags"] = {
        "type": "array",
        "items": {"type": "string"},
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("tags")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_invalid_media_schema_missing_required_fields():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["cover"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
        },
        "required": ["url"],
        "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("cover")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_invalid_media_schema_missing_required_properties_definition():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["cover"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": ["url", "mime-type", "width", "height", "size"],
        "x-meta": {"semantic-type": "Image", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("cover")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_invalid_media_schema_rejects_wrong_internal_property_types():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["video"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "size": {"type": "string"},
        },
        "required": ["url", "mime-type", "size"],
        "x-meta": {"semantic-type": "Video", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("video")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_valid_file_schema_allows_optional_internal_fields():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["attachment"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "mime-type": {"type": "string"},
            "size": {"type": "integer"},
        },
        "required": ["url"],
        "x-meta": {"semantic-type": "File", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("attachment")

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["attachment"]["required"] == ["url"]
    assert created["properties"]["attachment"]["properties"]["mime-type"]["type"] == "string"
    assert created["properties"]["attachment"]["properties"]["size"]["type"] == "integer"


@pytest.mark.parametrize(
    ("semantic_type", "missing_required_field"),
    [
        ("File", "url"),
        ("Image", "url"),
        ("Video", "url"),
    ],
)
def test_create_rejects_media_schema_without_required_descriptor_field(
    semantic_type: str,
    missing_required_field: str,
):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["media"] = _valid_media_field_schema(semantic_type)
    schema["properties"]["media"]["required"].remove(missing_required_field)
    schema["required"].append("media")

    with pytest.raises(ValidationError) as exc_info:
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    _assert_error_contains(exc_info, "properties.media", "oneOf")


def test_update_rejects_removing_required_image_url_field():
    entity_repo = InMemoryEntityRepo()
    svc = _entity_service(entity_repo, InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["cover"] = _valid_media_field_schema("Image")
    schema["required"].append("cover")
    svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    updated_schema = copy.deepcopy(schema)
    updated_schema["properties"]["cover"]["required"].remove("url")

    with pytest.raises(ValidationError) as exc_info:
        svc.update("library", "Book", updated_schema, actor=SUPERUSER_ACTOR)

    _assert_error_contains(exc_info, "properties.cover", "oneOf")


@pytest.mark.parametrize("semantic_type", ["Image", "Video"])
def test_create_allows_media_schema_with_url_as_only_required_descriptor_field(semantic_type: str):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["media"] = _valid_media_field_schema(semantic_type)
    schema["properties"]["media"]["required"] = ["url"]
    schema["required"].append("media")

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["media"]["required"] == ["url"]


def test_invalid_link_schema_wrong_type_and_missing_link_meta():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["library"] = []
    svc = _entity_service(entity_repo, node_repo)

    schema = _base_schema()
    schema["properties"]["author"] = {
        "type": "array",
        "x-meta": {"semantic-type": "Link", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("author")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_invalid_link_schema_without_link_meta():
    entity_repo = InMemoryEntityRepo()
    node_repo = InMemoryNodeRepo()
    node_repo.nodes["library"] = []
    svc = _entity_service(entity_repo, node_repo)

    schema = _base_schema()
    schema["properties"]["author"] = {
        "type": "string",
        "format": "uuid",
        "x-meta": {"semantic-type": "Link", "visibility-mode": "all", "write-mode": "all"},
    }
    schema["required"].append("author")

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_create_fails_without_visibility_mode():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    del schema["properties"]["name"]["x-meta"]["visibility-mode"]

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_create_fails_without_write_mode():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    del schema["properties"]["name"]["x-meta"]["write-mode"]

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_create_fails_for_invalid_access_modes():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["name"]["x-meta"]["visibility-mode"] = "guest"

    with pytest.raises(ValidationError):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def test_create_accepts_none_access_mode():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["password_hash"] = {
        "type": "string",
        "x-meta": {
            "semantic-type": "String",
            "visibility-mode": "none",
            "write-mode": "none",
        },
    }

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)

    assert created["properties"]["password_hash"]["x-meta"]["visibility-mode"] == "none"
    assert created["properties"]["password_hash"]["x-meta"]["write-mode"] == "none"


def test_create_fails_when_nested_modes_are_wider_than_parent():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["meta"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "internal": {
                "type": "string",
                "x-meta": {
                    "semantic-type": "String", "visibility-mode": "all", "write-mode": "all",
                    "visibility-mode": "all",
                    "write-mode": "all",
                },
            }
        },
        "required": ["internal"],
        "x-meta": {
            "semantic-type": "Object", "visibility-mode": "all", "write-mode": "all",
            "visibility-mode": "admin",
            "write-mode": "admin",
        },
    }
    schema["required"].append("meta")

    with pytest.raises(ValidationError, match="cannot be wider than parent mode"):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


@pytest.mark.parametrize(
    ("item_meta", "error_part"),
    [
        (
            {"semantic-type": "String", "visibility-mode": "admin", "write-mode": "all"},
            "Array items x-meta.visibility-mode must match",
        ),
        (
            {"semantic-type": "String", "visibility-mode": "all", "write-mode": "admin"},
            "Array items x-meta.write-mode must match",
        ),
    ],
)
def test_create_rejects_array_items_access_modes_different_from_array(
    item_meta: dict[str, str],
    error_part: str,
):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    schema["properties"]["tags"] = {
        "type": "array",
        "items": {
            "type": "string",
            "x-meta": item_meta,
        },
        "x-meta": {
            "semantic-type": "Array",
            "visibility-mode": "all",
            "write-mode": "all",
        },
    }

    with pytest.raises(ValidationError, match=error_part):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)


def _array_field(items):
    return {
        "type": "array", "items": items,
        "x-meta": {"semantic-type": "Array", "visibility-mode": "all", "write-mode": "all"},
    }


def _schema_with_field_names(names, container):
    schema = _base_schema()
    fields = {name: copy.deepcopy(schema["properties"]["name"]) for name in names}
    if container == "root":
        schema["properties"].update(fields)
        return schema
    field = {
        "type": "object", "additionalProperties": False, "properties": fields,
        "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
    }
    if container == "nullable_object":
        field = {"anyOf": [field, {"type": "null"}]}
    elif container in {"array_object", "nested_arrays"}:
        field = _array_field({"anyOf": [{"type": "null"}, field]})
        if container == "nested_arrays":
            field = _array_field({
                "type": "object", "additionalProperties": False, "properties": {"children": field},
                "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
            })
        field = {"anyOf": [field, {"type": "null"}]}
    schema["properties"]["data"] = field
    return schema


@pytest.mark.parametrize("name", ["", "a.b", "$secret", "*", "a*b", "a\x00b", "__sandala_", "__sandala_acl_raw_owner", "a.b\n"])
@pytest.mark.parametrize("container", ["root", "object", "nullable_object", "array_object", "nested_arrays"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_user_field_names_are_validated_in_meta_schema_at_every_depth(name, container, operation):
    entity_repo = InMemoryEntityRepo()
    svc = _entity_service(entity_repo, InMemoryNodeRepo())
    if operation == "update":
        svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    before = copy.deepcopy(entity_repo.docs)
    candidate = _schema_with_field_names([name], container)

    with pytest.raises(SchemaValidationError) as exc_info:
        getattr(svc, operation)("library", "Book", candidate, actor=SUPERUSER_ACTOR)
    assert exc_info.value.details["validation_errors"]
    assert exc_info.value.details["validation_errors"][0]["path"][0] == "properties"
    assert entity_repo.docs == before


@pytest.mark.parametrize("name", ["_id", "and", "or", "not"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_root_user_field_names_cannot_shadow_mongo_id_or_logical_operators(name, operation):
    entity_repo = InMemoryEntityRepo()
    svc = _entity_service(entity_repo, InMemoryNodeRepo())
    if operation == "update":
        svc.create("library", "Book", _base_schema(), actor=SUPERUSER_ACTOR)
    before = copy.deepcopy(entity_repo.docs)
    with pytest.raises(SchemaValidationError):
        getattr(svc, operation)("library", "Book", _schema_with_field_names([name], "root"), actor=SUPERUSER_ACTOR)
    assert entity_repo.docs == before


@pytest.mark.parametrize("container", ["root", "object", "nullable_object", "array_object", "nested_arrays"])
def test_user_field_names_keep_unicode_hyphens_and_noninitial_dollars(container):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    names = ["название", "书名", "mime-type", "price$", "_custom", "__sandala", "AND"]
    if container != "root":
        names.extend(["_id", "and", "or", "not", "id", "owner"])
    candidate = _schema_with_field_names(names, container)

    created = svc.create("library", "Book", candidate, actor=SUPERUSER_ACTOR)
    updated = svc.update("library", "Book", created, actor=SUPERUSER_ACTOR)

    for name, field in candidate["properties"].items():
        assert updated["properties"][name] == field


@pytest.mark.parametrize("semantic_type", ["Array", "Link", "LinkArray"])
@pytest.mark.parametrize("nullable", ["plain", "null_first", "null_last"])
@pytest.mark.parametrize("container", ["root", "object", "array_object", "nullable_array"])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_array_rejects_array_and_reference_items_in_meta_schema(semantic_type, nullable, container, operation):
    entity_repo = InMemoryEntityRepo()
    svc = _entity_service(entity_repo, InMemoryNodeRepo())
    svc.create("library", "Author", _author_schema(), actor=SUPERUSER_ACTOR)
    original = _base_schema()
    if operation == "update":
        svc.create("library", "Book", original, actor=SUPERUSER_ACTOR)
    before = copy.deepcopy(entity_repo.docs)
    if semantic_type == "Array":
        item = _array_field(copy.deepcopy(original["properties"]["name"]))
    else:
        item = {
            "x-meta": {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": "all",
                       "link": {"module": "library", "entities": ["Author"]}},
        }
        item.update({"type": "string", "format": "uuid"} if semantic_type == "Link"
                    else {"type": "array", "items": {"type": "string", "format": "uuid"}})
    if nullable != "plain":
        variants = [{"type": "null"}, item] if nullable == "null_first" else [item, {"type": "null"}]
        item = {"anyOf": variants}
    field = _array_field(item)
    if container in {"object", "array_object"}:
        field = {
            "type": "object", "additionalProperties": False, "properties": {"values": field},
            "x-meta": {"semantic-type": "Object", "visibility-mode": "all", "write-mode": "all"},
        }
        if container == "array_object":
            field = _array_field(field)
    elif container == "nullable_array":
        field = {"anyOf": [field, {"type": "null"}]}
    candidate = _base_schema()
    candidate["properties"]["data"] = field

    with pytest.raises(SchemaValidationError) as exc_info:
        getattr(svc, operation)("library", "Book", candidate, actor=SUPERUSER_ACTOR)
    _assert_error_contains(exc_info, "properties.data")
    assert entity_repo.docs == before


@pytest.mark.parametrize("semantic_type", [
    "String", "Password", "Text", "RichText", "Number", "Integer", "Boolean", "Date", "DateTime",
    "File", "Image", "Video", "Object",
])
@pytest.mark.parametrize("nullable", [False, True])
def test_array_keeps_allowed_item_types_including_nullable_variants(semantic_type, nullable):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    meta = {"semantic-type": semantic_type, "visibility-mode": "all", "write-mode": "all"}
    if semantic_type in {"File", "Image", "Video"}:
        item = _valid_media_field_schema(semantic_type)
    elif semantic_type == "Object":
        item = {"type": "object", "additionalProperties": False, "properties": {}, "x-meta": meta}
    else:
        item = {"type": {"Number": "number", "Integer": "integer", "Boolean": "boolean"}.get(semantic_type, "string"),
                "x-meta": meta}
        if semantic_type in {"Date", "DateTime"}:
            item["format"] = "date" if semantic_type == "Date" else "date-time"
    if nullable:
        item = {"anyOf": [item, {"type": "null"}]}
    schema["properties"]["values"] = _array_field(item)

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    assert created["properties"]["values"]["items"] == item


def test_array_objects_keep_nested_arrays_links_and_link_arrays():
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    svc.create("library", "Author", _author_schema(), actor=SUPERUSER_ACTOR)
    schema = _base_schema()
    single = {"type": "string", "format": "uuid", "x-meta": {
        "semantic-type": "Link", "visibility-mode": "all", "write-mode": "all",
        "link": {"module": "library", "entities": ["Author"]},
    }}
    multiple = {"type": "array", "items": {"type": "string", "format": "uuid"}, "x-meta": {
        **single["x-meta"], "semantic-type": "LinkArray",
    }}
    member = {"type": "object", "additionalProperties": False, "x-meta": {
        "semantic-type": "Object", "visibility-mode": "all", "write-mode": "all",
    }, "properties": {"author": single, "editors": multiple}}
    schema["properties"].update({
        "editors": multiple,
        "sections": _array_field({**member, "properties": {"groups": _array_field(member)}}),
    })

    created = svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
    updated = svc.update("library", "Book", created, actor=SUPERUSER_ACTOR)
    assert updated["properties"]["sections"] == schema["properties"]["sections"]
    assert updated["properties"]["editors"] == multiple


@pytest.mark.parametrize("nullable_array", [False, True])
def test_array_with_nullable_password_items_still_cannot_be_required(nullable_array):
    svc = _entity_service(InMemoryEntityRepo(), InMemoryNodeRepo())
    schema = _base_schema()
    field = _array_field({"anyOf": [{"type": "null"}, {
        "type": "string", "x-meta": {"semantic-type": "Password", "visibility-mode": "all", "write-mode": "all"},
    }]})
    schema["properties"]["passwords"] = {"anyOf": [field, {"type": "null"}]} if nullable_array else field
    schema["required"].append("passwords")

    with pytest.raises(ValidationError, match="Password cannot be required"):
        svc.create("library", "Book", schema, actor=SUPERUSER_ACTOR)
